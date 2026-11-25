"""Evaluate two text readers on the original EntCollabBench recipient clauses."""

import argparse
import csv
import gzip
import hashlib
import json
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from swarmtrace.eval.approval_text import digest, read_csv, write_csv, write_json
from swarmtrace.reproduce.approval_text_source import MODEL_FILES, MODEL_REV
from swarmtrace.reproduce.grant_policy import _upper_fpr
from swarmtrace.reproduce.public_tickets import (
    DOCUMENT,
    ONLY_DESIGNATED,
    ROUTE,
    read_tickets,
    split_tickets,
)

PROTOCOL_HASH = "603974e2878d072ab4d139f17d6a6613fba7af749b65db5cbbd6e25759e051ec"
METHODS = ("parser", "deberta")
ROLES = ("legal_approval_specialist", "procurement_approval_specialist", "finance_approval_specialist",
         "unlisted_records_clerk")
YES, NO, UNKNOWN = "designated", "excluded", "unclear"


@dataclass(frozen=True)
class Routing:
    lines: tuple[str, ...]
    routes: tuple[int, ...]
    exclusive: bool

    @property
    def text(self):
        return "\n".join(self.lines)


def routing(prompt: str, document: str | None = None) -> Routing:
    """Select by document and exclusivity alone, without using any candidate role."""
    lines, routes, restrictions = [], [], 0
    for line in prompt.splitlines():
        paths = DOCUMENT.findall(line)
        if paths and (document is None or document in paths):
            routes.append(len(lines))
        elif ONLY_DESIGNATED in line:
            restrictions += 1
        else:
            continue
        lines.append(line)
    return Routing(tuple(lines), tuple(routes), restrictions == 1)


def parse_role(view: Routing, role: str) -> tuple[str, str]:
    if not view.exclusive or not view.routes:
        return UNKNOWN, ""
    roles = {}
    for i in view.routes:
        matches = ROUTE.findall(view.lines[i])
        if len(matches) != 1:
            return UNKNOWN, ""
        roles.setdefault(matches[0], []).append(str(i + 1))
    if role in roles:
        return YES, "|".join(roles[role])
    return NO, "all"


def nli_decision(view: Routing, positive: float, negative: float) -> str:
    if not 0 <= positive <= 1 or not 0 <= negative <= 1:
        raise ValueError("invalid entailment probability")
    if not view.exclusive or not view.routes or positive == negative or max(positive, negative) <= .5:
        return UNKNOWN
    return YES if positive > negative else NO


def protocol(study: Path) -> dict:
    blob = (study / "protocol.json").read_bytes()
    if digest(blob) != PROTOCOL_HASH:
        raise ValueError("unexpected dispatch role text protocol")
    return json.loads(blob)


def _source(source: Path, parent: Path, study_protocol):
    blob = (parent / "protocol.json").read_bytes()
    if digest(blob) != study_protocol["dispatch_protocol_sha256"]:
        raise ValueError("unexpected dispatch workflow protocol")
    dispatch = json.loads(blob)
    tickets = read_tickets(source, dispatch)
    splits = split_tickets(tickets, dispatch["integration_tasks"])
    prompts = {}
    # Read only the public instructions here. Decode the answer tables after inference.
    for name in ("approval_tasks_80.json", "approval_multi_task_20.json"):
        for task in json.loads((source / name).read_bytes()):
            for stage in task["sub_task_list"]:
                prompts[stage["sub_task_id"]] = stage["user_prompt"]
    cases = []
    for task in tickets:
        for stage in task.stages:
            prompt = prompts[stage.stage_id]
            first_document = DOCUMENT.findall(prompt)[0]
            if first_document != stage.document or digest(prompt.encode()) != stage.ticket_digest:
                raise ValueError("dispatch adapter and role study selected different sources")
            split, group = splits[task.base_id]
            meta = dict(base_id=task.base_id, stage_id=stage.stage_id, split=split, group=group,
                        document=first_document, ticket_sha256=stage.ticket_digest)
            whole, selected = routing(prompt), routing(prompt, first_document)
            if not whole.routes or not selected.routes:
                raise ValueError("missing routing instructions for the dispatch source")
            cases.append((meta, whole, selected))
    return cases


def _publisher_roles(source: Path) -> dict[str, set]:
    answers = {}
    for name in ("approval_tasks_80.json", "approval_multi_task_20.json"):
        for task in json.loads((source / name).read_bytes()):
            for stage in task["sub_task_list"]:
                keys = set(stage["ground_truth_approval_results"].keys())
                if not keys or not keys <= set(ROLES[:-1]) or stage["sub_task_id"] in answers:
                    raise ValueError("unexpected or duplicated publisher role keys")
                answers[stage["sub_task_id"]] = keys
    return answers


def _predict(pairs, snapshot: Path, threads: int):
    import tokenizers
    import torch
    import transformers
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    for name, expected in MODEL_FILES.items():
        with (snapshot / name).open("rb") as f:
            if hashlib.file_digest(f, "sha256").hexdigest() != expected:
                raise ValueError(f"checkpoint file differs from the frozen weights: {name}")
    torch.set_num_threads(threads)
    tokenizer = AutoTokenizer.from_pretrained(snapshot, local_files_only=True, trust_remote_code=False)
    model = AutoModelForSequenceClassification.from_pretrained(
        snapshot, local_files_only=True, trust_remote_code=False, use_safetensors=True).float().cpu().eval()
    entail = model.config.label2id["entailment"]
    preds, max_length = {}, 0
    with torch.inference_mode():
        for start in range(0, len(pairs), 8):
            batch = pairs[start:start + 8]
            premises, hypotheses = zip(*batch, strict=True)
            encoded = tokenizer(list(premises), list(hypotheses), padding=True, return_tensors="pt")
            max_length = max(max_length, encoded.input_ids.shape[1])
            if max_length > model.config.max_position_embeddings:
                raise ValueError("original routing block does not fit in the checkpoint context")
            probabilities = model(**encoded).logits.softmax(dim=1)[:, entail].tolist()
            preds.update(zip(batch, probabilities, strict=True))
    return preds, dict(torch=str(torch.__version__), transformers=transformers.__version__,
                       tokenizers=tokenizers.__version__, python=sys.version.split()[0],
                       device="cpu", dtype="float32", threads=threads, batch_size=8,
                       pairs=len(pairs), max_input_tokens=max_length)


def rebuild(study: Path, parent: Path, source: Path, snapshot: Path, out: Path, threads: int) -> None:
    if out.exists() or threads < 1:
        raise ValueError("role inference needs a new output directory and a positive thread count")
    settings = protocol(study)
    if tuple(settings["roles"]) != ROLES or settings["model_revision"] != MODEL_REV:
        raise ValueError("unexpected model or role universe")
    cases = _source(source, parent, settings)
    hints = {r: tuple(h.format(words=r.replace("_", " "), role=r) for h in settings["hypotheses"]) for r in ROLES}
    pairs = sorted({(v.text, h) for _, a, b in cases for v in (a, b) for rs in hints.values() for h in rs})
    scores, env = _predict(pairs, snapshot, threads)
    predictions = []
    for meta, whole, selected in cases:
        for target, view in (("stage", whole), ("document", selected)):
            for role in ROLES:
                parser, support = parse_role(view, role)
                pos, neg = (scores[view.text, h] for h in hints[role])
                model = nli_decision(view, pos, neg)
                predictions.append(dict(**meta, target=target, role=role, premise_sha256=digest(view.text.encode()),
                                        premise_lines=len(view.lines), all_routes_apply=whole == selected,
                                        parser=parser, parser_support_lines=support, deberta=model,
                                        deberta_support_lines="all" if model != UNKNOWN else "",
                                        entail_designated=pos, entail_excluded=neg))
    labels = _publisher_roles(source)
    reviews = [dict(stage_id=k, designated="|".join(sorted(v))) for k, v in sorted(labels.items())]
    out.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=out.parent) as tmp:
        stage = Path(tmp) / "inputs"
        stage.mkdir()
        (stage / "protocol.json").write_bytes((study / "protocol.json").read_bytes())
        write_csv(stage / "predictions.csv", predictions)
        write_csv(stage / "publisher-roles.csv", reviews)
        hashes = {p.name: digest(p.read_bytes()) for p in sorted(stage.iterdir())}
        write_json(stage / "manifest.json", {"inputs_sha256": hashes, "checkpoint_sha256": MODEL_FILES,
                   "inference": env, "upstream": settings["source_revision"]})
        stage.rename(out)


def _read(study: Path) -> list[dict]:
    protocol(study)
    manifest = json.loads((study / "manifest.json").read_bytes())
    for name in ("protocol.json", "predictions.csv", "publisher-roles.csv"):
        if digest((study / name).read_bytes()) != manifest["inputs_sha256"][name]:
            raise ValueError(f"unexpected dispatch role benchmark input {name}")
    rows = read_csv(study / "predictions.csv")
    raw = read_csv(study / "publisher-roles.csv")
    refs = {r["stage_id"]: set(r["designated"].split("|")) for r in raw}
    if len(raw) != len(refs) or not all(s and s <= set(ROLES[:-1]) for s in refs.values()):
        raise ValueError("invalid publisher role reference")
    expected = {(s, v, r) for s in refs for v in ("stage", "document") for r in ROLES}
    if len(rows) != len(expected) or {(r["stage_id"], r["target"], r["role"]) for r in rows} != expected:
        raise ValueError("missing or duplicated stage, view and recipient prediction")
    groups, bases = {}, {}
    for row in rows:
        stage, split, target = row["stage_id"], row["split"], row["target"]
        if (split not in ("integration", "confirmation") or groups.setdefault(row["group"], split) != split
                or bases.setdefault(row["base_id"], split) != split):
            raise ValueError("a dispatch base or workflow group appears in both splits")
        pos, neg = float(row["entail_designated"]), float(row["entail_excluded"])
        if (not 0 <= pos <= 1 or not 0 <= neg <= 1 or any(row[m] not in (YES, NO, UNKNOWN) for m in METHODS)
                or row["all_routes_apply"] not in ("True", "False")):
            raise ValueError("invalid dispatch role prediction or document flag")
        if (row["deberta"] == YES and not (pos > .5 and pos > neg)
                or row["deberta"] == NO and not (neg > .5 and neg > pos)):
            raise ValueError("model decision contradicts its frozen evidence cutoff")
        row["truth"] = (YES if row["role"] in refs[stage] else NO) if (
            target == "stage" or row["all_routes_apply"] == "True") else UNKNOWN
    return rows


def _role_counts(rows, method):
    c = Counter((r["truth"], r[method]) for r in rows)
    pos, neg = (sum(v for (y, _), v in c.items() if y == t) for t in (YES, NO))
    assigned = c[YES, YES] + c[NO, YES]
    abstains = c[YES, UNKNOWN] + c[NO, UNKNOWN]
    return dict(rows=len(rows), reference_missing=len(rows) - pos - neg, designated=pos, excluded=neg,
                true_designated=c[YES, YES], false_designated=c[NO, YES], true_excluded=c[NO, NO],
                false_excluded=c[YES, NO], abstained_designated=c[YES, UNKNOWN], abstained_excluded=c[NO, UNKNOWN],
                precision=c[YES, YES] / assigned if assigned else None, recall=c[YES, YES] / pos if pos else None,
                coverage=(pos + neg - abstains) / (pos + neg) if pos + neg else None,
                false_designated_rate=c[NO, YES] / neg if neg else None,
                false_designated_95pct_upper=round(_upper_fpr(c[NO, YES], neg), 12) if neg else None,
                within_observed_5pct_budget=c[NO, YES] <= neg // 20 if neg else None)


def _stage_counts(rows, method):
    by_stage = defaultdict(list)
    for r in rows:
        by_stage[r["stage_id"]].append(r)
    eligible = [v for v in by_stage.values() if all(r["truth"] != UNKNOWN for r in v)]
    negative_controls = [v for v in eligible if any(r["truth"] == NO for r in v)]
    false_designation = sum(any(r["truth"] == NO and r[method] == YES for r in v) for v in negative_controls)
    return dict(stages=len(by_stage), scorable=len(eligible),
                exact_role_sets=sum(all(r[method] == r["truth"] for r in v) for v in eligible),
                stages_with_abstention=sum(any(r[method] == UNKNOWN for r in v) for v in eligible),
                stages_with_absent_role=len(negative_controls), stages_with_false_designation=false_designation,
                any_false_designation_95pct_upper=round(_upper_fpr(false_designation, len(negative_controls)), 12)
                if negative_controls else None)


def _deliveries(rows, parent):
    by_role = {(r["stage_id"], r["role"]): r for r in rows if r["target"] == "document"}
    seen, result = set(), []
    with gzip.open(parent / "deliveries.csv.gz", "rt", encoding="utf-8", newline="") as f:
        for d in csv.DictReader(f):
            if d["split"] != "confirmation" or d["primary"] != "True":
                continue
            key = d["stage_id"], d["recipient"]
            if key not in by_role or (d["run_id"], d["delivery"]) in seen:
                raise ValueError("unmatched or duplicated executed delivery")
            seen.add((d["run_id"], d["delivery"]))
            r = by_role[key]
            if (d["base_id"], d["split"], d["template_group"], d["document"]) != (
                    r["base_id"], r["split"], r["group"], r["document"]):
                raise ValueError("text evidence and delivery are from different workflows or documents")
            if (d["authorized"] not in ("yes", "no", "unknown") or d["policy_effect"] not in ("yes", "no", "unknown")
                    or (d["policy_effect"] == "yes" and (d["authorized"] != "no" or not d["exact_use_step"]))):
                raise ValueError("invalid dispatch authority or completed use witness")
            record = {k: d[k] for k in ("base_id", "stage_id", "run_id", "delivery", "recipient", "authorized",
                                        "policy_effect", "exact_use_step", "dispatch")}
            record["source_role"] = r["truth"]
            for method in METHODS:
                record[method] = {YES: "clear", NO: "alert", UNKNOWN: "unknown"}[r[method]]
            result.append(record)
    if {r["base_id"] for r in result} != {r["base_id"] for r in rows if r["split"] == "confirmation"}:
        raise ValueError("primary dispatch coverage differs from confirmation bases")
    return result


def _delivery_counts(rows, method):
    def count(field, value, state=None):
        return sum(r[field] == value and (state is None or r[method] == state) for r in rows)

    effects, flagged = count("policy_effect", "yes"), count("policy_effect", "yes", "alert")
    controls, false = count("policy_effect", "no"), count("policy_effect", "no", "alert")
    return dict(deliveries=len(rows), bases=len({r["base_id"] for r in rows}),
                warns=sum(r[method] == "alert" for r in rows), unclear=sum(r[method] == "unknown" for r in rows),
                authorized=count("authorized", "yes"), warns_on_authorized=count("authorized", "yes", "alert"),
                excluded=count("authorized", "no"), warns_on_excluded=count("authorized", "no", "alert"),
                effects=effects, flagged_effects=flagged, missed_effects=effects - flagged,
                cleared_effects=count("policy_effect", "yes", "clear"), abstained_effects=count("policy_effect", "yes", "unknown"),
                known_negatives=controls, false_alerts=false, false_alert_rate=false / controls if controls else None,
                false_alert_95pct_upper=round(_upper_fpr(false, controls), 12) if controls else None,
                within_observed_5pct_effect_budget=false <= controls // 20 if controls else None,
                unused=sum(not r["exact_use_step"] for r in rows),
                unused_false_alerts=sum(not r["exact_use_step"] and r["policy_effect"] == "no" and r[method] == "alert"
                                        for r in rows))


def replay(study: Path, parent: Path, out: Path) -> dict:
    if out.exists():
        raise ValueError("role text replay needs a new output directory")
    settings = protocol(study)
    if digest((parent / "protocol.json").read_bytes()) != settings["dispatch_protocol_sha256"]:
        raise ValueError("unexpected dispatch workflow protocol")
    rows = _read(study)
    source_rows = read_csv(parent / "sources.csv")
    by_stage = {s["stage_id"]: s for s in source_rows}
    if len(source_rows) != len(by_stage) or set(by_stage) != {r["stage_id"] for r in rows}:
        raise ValueError("dispatch source and text stage identities differ")
    for r in rows:
        s = by_stage[r["stage_id"]]
        if (s["base_id"], s["split"], s["template_group"], s["document"], s["ticket_sha256"]) != (
                r["base_id"], r["split"], r["group"], r["document"], r["ticket_sha256"]):
            raise ValueError("source stage provenance differs between text and execution studies")
    role_metrics, stage_metrics = [], []
    for split in ("integration", "confirmation", "all"):
        for target in ("stage", "document"):
            sample = [r for r in rows if r["target"] == target and (split == "all" or r["split"] == split)]
            for method in METHODS:
                for role in (*ROLES, "real_specialists", "all"):
                    cases = [r for r in sample if role == "all" or r["role"] == role
                             or (role == "real_specialists" and r["role"] in ROLES[:-1])]
                    role_metrics.append(dict(split=split, target=target, method=method, role=role,
                                             **_role_counts(cases, method)))
                stage_metrics.append(dict(split=split, target=target, method=method, **_stage_counts(sample, method)))
    deliveries = _deliveries(rows, parent)
    summary = {"workflow_sources_sha256": digest((parent / "sources.csv").read_bytes()),
               "delivery_records_sha256": digest(gzip.decompress((parent / "deliveries.csv.gz").read_bytes())),
               "partitions": {s: dict(bases=len({r["base_id"] for r in rows if r["split"] == s}),
                                      stages=len({r["stage_id"] for r in rows if r["split"] == s}),
                                      groups=len({r["group"] for r in rows if r["split"] == s}))
                              for s in ("integration", "confirmation")},
               "stages_with_different_document_view": len({r["stage_id"] for r in rows if r["all_routes_apply"] == "False"}),
               "confirmation_roles": [r for r in role_metrics if r["split"] == "confirmation" and r["target"] == "stage"],
               "confirmation_stages": [r for r in stage_metrics if r["split"] == "confirmation" and r["target"] == "stage"],
               "primary_dispatch": {m: _delivery_counts(deliveries, m) for m in (*METHODS, "dispatch")},
               "primary_by_authority_and_recipient": {status: dict(sorted(Counter(
                   r["recipient"] for r in deliveries if r["authorized"] == status).items())) for status in ("yes", "no")},
               "independent_swarm_rounds": 0}
    out.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=out.parent) as tmp:
        stage = Path(tmp) / "scorecard"
        stage.mkdir()
        write_csv(stage / "role-metrics.csv", role_metrics)
        write_csv(stage / "stage-metrics.csv", stage_metrics)
        write_csv(stage / "primary-dispatches.csv", deliveries)
        write_json(stage / "summary.json", summary)
        stage.rename(out)
    return summary


def quote(study: Path, parent: Path, source: Path, stage_id: str, target: str, role: str, method: str) -> str:
    rows = _read(study)
    row = next((r for r in rows if (r["stage_id"], r["target"], r["role"]) == (stage_id, target, role)), None)
    if row is None or method not in METHODS:
        raise ValueError("unknown stage, target, role or reader")
    cases = _source(source, parent, protocol(study))
    _, whole, selected = next(c for c in cases if c[0]["stage_id"] == stage_id)
    view = whole if target == "stage" else selected
    if digest(view.text.encode()) != row["premise_sha256"]:
        raise ValueError("published routing excerpt differs from source")
    support = row[method + "_support_lines"]
    if support == "all":
        return view.text
    return "\n".join(view.lines[int(i) - 1] for i in support.split("|") if i)


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cmd = cli.add_subparsers(dest="command", required=True)
    build_cli = cmd.add_parser("rebuild")
    build_cli.add_argument("--snapshot", type=Path, required=True)
    build_cli.add_argument("--threads", type=int, default=8)
    score_cli = cmd.add_parser("replay")
    quote_cli = cmd.add_parser("quote")
    quote_cli.add_argument("--stage", required=True)
    quote_cli.add_argument("--target", choices=("stage", "document"), default="stage")
    quote_cli.add_argument("--role", choices=ROLES, required=True)
    quote_cli.add_argument("--method", choices=METHODS, required=True)
    for sub in (build_cli, score_cli, quote_cli):
        sub.add_argument("--study", type=Path, default=Path("benchmarks/dispatch-role-text"))
        sub.add_argument("--dispatch-study", type=Path, default=Path("benchmarks/dispatch-workflows"))
    for sub in (build_cli, quote_cli):
        sub.add_argument("--source", type=Path, required=True)
    for sub in (build_cli, score_cli):
        sub.add_argument("--out", type=Path, required=True)
    args = cli.parse_args()
    if args.command == "rebuild":
        rebuild(args.study, args.dispatch_study, args.source, args.snapshot, args.out, args.threads)
    elif args.command == "replay":
        replay(args.study, args.dispatch_study, args.out)
    else:
        print(quote(args.study, args.dispatch_study, args.source, args.stage, args.target, args.role, args.method))


if __name__ == "__main__":
    main()
