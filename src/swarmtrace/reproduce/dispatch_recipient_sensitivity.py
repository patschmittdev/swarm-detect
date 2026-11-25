"""Post hoc replay replacing the unlisted clerk with an ordinary absent specialist."""

import argparse
import csv
import gzip
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory

from swarmtrace.eval.approval_text import digest, read_csv, write_csv, write_json
from swarmtrace.eval.recipient_dispatch import evaluate_office
from swarmtrace.eval.recipient_lab import Commit
from swarmtrace.reproduce import dispatch_role_text as readers
from swarmtrace.reproduce import dispatch_workflows as workflow
from swarmtrace.reproduce.public_tickets import key, read_tickets, split_tickets

SALT = "swarmtrace/dispatch-recipient-sensitivity/v1"
PURPOSE = "ordinary-absent-specialist"
CLERK = readers.ROLES[-1]
SUBSTITUTED = "ordinary_absent_specialist"
RETAINED = "approved_recipient_retained"
OMITTED = "no_eligible_absent_specialist"


def choose_recipient(base_id: str, named: tuple[str, ...], author: str) -> tuple[list[str], str | None]:
    """Sample among the sorted eligible real roles using only the immutable task ID."""
    candidates = sorted(set(readers.ROLES[:-1]) - set(named) - {author})
    if not candidates:
        return [], None
    index = int(key(SALT, PURPOSE, base_id), 16) % len(candidates)
    return candidates, candidates[index]


FACTS = ("dispatched_step", "authorized", "version", "exact_use_step", "effect_step", "policy_effect",
         "dispatch", "dispatch_step", "commit", "commit_step")
TEXT_STATUS = {readers.YES: "clear", readers.NO: "alert", readers.UNKNOWN: "unknown"}


def _fact(value, name):
    if name.endswith("_step") and value not in ("", None):
        step = float(value)
        if not step.is_integer() or step < 0:
            raise ValueError("dispatch clocks require a nonnegative integer")
        return str(int(step))
    return "" if value is None else str(value)


def _inputs(role_study: Path, dispatch: Path):
    settings = workflow.read_protocol(dispatch)
    text_settings = readers.protocol(role_study)
    if text_settings["dispatch_protocol_sha256"] != workflow.PROTOCOL_SHA256:
        raise ValueError("reader and execution protocols differ")
    text = {(r["stage_id"], r["role"]): r for r in readers._read(role_study)
            if r["target"] == "document" and r["split"] == "confirmation"}
    with gzip.open(dispatch / "deliveries.csv.gz", "rt", encoding="utf-8", newline="") as src:
        delivered = [d for d in csv.DictReader(src) if d["primary"] == "True" and d["split"] == "confirmation"]
    original = {(d["run_id"], d["delivery"]): d for d in delivered}
    if len(original) != len(delivered):
        raise ValueError("duplicate primary delivery in the dispatch archive")
    sources = {s["stage_id"]: s for s in read_csv(dispatch / "sources.csv") if s["split"] == "confirmation"}
    return settings, text, original, sources


def _shape(office, arrivals, missing):
    """Ignore worker aliases and the worker's signature on the output, retaining the committed body."""
    w = office.workflow
    names = {w.author: "author", w.assigned: "assigned", w.alternate: "alternate"}

    def name(value):
        if value.endswith("/review") and value[:-7] in names:
            return names[value[:-7]] + "/review"
        return names.get(value, value)

    operations = [(e.step, name(e.actor), e.tool, name(e.target), e.success) for e in office.observations]
    transport = [(r.record.key, r.record.step, r.at) for r in arrivals]
    committed = [(c.step, name(c.recipient), c.source, office.blobs[c.output].split(b"\n", 1)[1])
                 for c in office.receipts if isinstance(c, Commit)]
    return operations, transport, tuple(missing), committed


def _execute_task(task, profile, settings):
    stage, = task.stages
    run_id = key(settings["salt"], "gateway", task.base_id, profile, "0")[:16]
    original, received, missing = workflow._execute(stage, profile, run_id, settings)
    _, before = evaluate_office(original, received)
    if not before or any((d["recipient"] == CLERK) != (d["authorized"] == "no") for d in before):
        raise ValueError("source office must have a known primary delivery with the expected original recipient")
    candidates, chosen = choose_recipient(task.base_id, stage.recipients, stage.author)
    excluded = any(d["recipient"] == CLERK for d in before)
    selection = (SUBSTITUTED if chosen else OMITTED) if excluded else RETAINED
    alternate = chosen if selection == SUBSTITUTED else CLERK
    matched = {}
    if selection != OMITTED:
        office, arrivals, missing_after = workflow._execute(stage, profile, run_id, settings, excluded_role=alternate)
        _, after = evaluate_office(office, arrivals)
        if _shape(original, received, missing) != _shape(office, arrivals, missing_after):
            raise ValueError("changing the recipient changed the office actions, commit input or transport")
        matched = {d["delivery"]: d for d in after}
        if set(matched) != {d["delivery"] for d in before}:
            raise ValueError("changing the recipient changed delivery coverage")
    rows = []
    for d in before:
        other = matched.get(d["delivery"])
        if other and (any(other[k] != d[k] for k in FACTS)
                      or other["recipient"] != (alternate if d["recipient"] == CLERK else d["recipient"])):
            raise ValueError("changing the recipient changed authorization, the effected copy or an alert")
        rows.append(dict(base_id=task.base_id, stage_id=stage.stage_id, run_id=run_id, profile=profile,
                         delivery=d["delivery"], document=d["document"], source_author=stage.author,
                         eligible_specialists="|".join(candidates), selection=selection,
                         original_recipient=d["recipient"], matched_recipient=other["recipient"] if other else "",
                         **{k: _fact(d[k], k) for k in FACTS}))
    return rows


def _check(rows, text, original, sources, *, fill_scores):
    keys = [(r["run_id"], r["delivery"]) for r in rows]
    if len(keys) != len(set(keys)) or set(keys) != set(original):
        raise ValueError("sensitivity must account for every original held-out primary delivery exactly once")
    for r, k in zip(rows, keys, strict=True):
        d = original[k]
        s = sources.get(r["stage_id"])
        if s is None:
            raise ValueError("unknown confirmation stage")
        names = tuple(s["named_recipients"].split("|"))
        candidates, chosen = choose_recipient(r["base_id"], names, r["source_author"])
        if (any(r[c] != d[c] for c in ("base_id", "stage_id", "profile", "document"))
                or s["base_id"] != r["base_id"] or r["version"] != s["document_sha256"]
                or any(r[c] != _fact(d[c], c) for c in FACTS) or r["original_recipient"] != d["recipient"]
                or r["eligible_specialists"] != "|".join(candidates)):
            raise ValueError("sensitivity delivery or eligible roles differ from the source office")
        change = d["recipient"] == CLERK
        expected = (SUBSTITUTED if chosen else OMITTED) if change else RETAINED
        recipient = (chosen or "") if change else d["recipient"]
        if r["selection"] != expected or r["matched_recipient"] != recipient:
            raise ValueError("a matched recipient differs from the fixed source-only choice")
        for arm in ("original", "matched"):
            role = r[f"{arm}_recipient"]
            prediction = text[r["stage_id"], role] if role else None
            if prediction and (prediction["document"] != r["document"] or prediction["ticket_sha256"] != s["ticket_sha256"]
                               or prediction["base_id"] != r["base_id"]
                               or prediction["truth"] != (readers.YES if role in names else readers.NO)):
                raise ValueError("reader premise or source role reference differs from the executed document")
            for method in readers.METHODS:
                value = TEXT_STATUS[prediction[method]] if prediction else ""
                field = f"{arm}_{method}"
                if fill_scores:
                    r[field] = value
                elif r[field] != value:
                    raise ValueError("sensitivity decision differs from the frozen reader prediction")


def _results(rows):
    """Use identical observations and denominators for both readings of each eligible delivery."""
    def counts(method):
        values = readers._delivery_counts(rows, method)
        del values["false_alert_95pct_upper"], values["within_observed_5pct_effect_budget"]
        values["resolved"] = len(rows) - values["unclear"]
        values["coverage"] = values["resolved"] / len(rows) if rows else None
        values["clears_on_excluded"] = sum(r["authorized"] == "no" and r[method] == "clear" for r in rows)
        values["abstains_on_excluded"] = sum(r["authorized"] == "no" and r[method] == "unknown" for r in rows)
        return values

    results = {}
    for arm in ("original", "matched"):
        results[arm] = {m: counts(f"{arm}_{m}") for m in readers.METHODS}
    results["structured"] = {m: counts(m) for m in ("dispatch", "commit")}
    return results


def summarize(rows):
    selection_counts = {}
    for k in (SUBSTITUTED, RETAINED, OMITTED):
        targets = [r for r in rows if r["selection"] == k]
        selection_counts[k] = dict(bases=len({r["base_id"] for r in targets}), deliveries=len(targets),
                                   effects=sum(r["policy_effect"] == "yes" for r in targets),
                                   unused=sum(not r["exact_use_step"] for r in targets))
    paired = [r for r in rows if r["selection"] != OMITTED]
    changed = [r for r in paired if r["selection"] == SUBSTITUTED]
    roles = {role: _results([r for r in changed if r["matched_recipient"] == role])
             for role in sorted({r["matched_recipient"] for r in changed})}
    transitions = {}
    for method in readers.METHODS:
        transitions[method] = dict(sorted(Counter(f"{r['original_' + method]} to {r['matched_' + method]}"
                                                  for r in changed).items()))
    return dict(design="post hoc matched-recipient sensitivity", salt=SALT, hash_purpose=PURPOSE,
                original_bases=len({r["base_id"] for r in rows}), original_deliveries=len(rows),
                selection=selection_counts, paired_primary=_results(paired),
                paired_excluded_recipients=_results(changed), by_replacement_role=roles,
                changed_role_decision_pairs=transitions, added_independent_swarm_rounds=0)


def run(role_study: Path, dispatch: Path, out: Path, *, source: Path | None = None):
    """Rebuild all office actions from pinned sources, or replay the published paired table offline."""
    if out.exists():
        raise ValueError("sensitivity requires a new output directory")
    settings, text, original, sources = _inputs(role_study, dispatch)
    if source is None:
        rows = read_csv(role_study / "sensitivity" / "deliveries.csv")
    else:
        tasks = read_tickets(source, settings)
        groups = split_tickets(tasks, settings["integration_tasks"])
        rows = []
        for task in tasks:
            if groups[task.base_id][0] != "confirmation":
                continue
            if len(task.stages) != 1:
                raise ValueError("frozen confirmation set requires one stage per primary task")
            _, _, profile = workflow.design(task, settings)
            rows.extend(_execute_task(task, profile, settings))
    _check(rows, text, original, sources, fill_scores=source is not None)
    summary = summarize(rows)
    summary["role_predictions_sha256"] = digest((role_study / "predictions.csv").read_bytes())
    summary["source_manifest_sha256"] = digest((dispatch / "sources.csv").read_bytes())
    summary["dispatch_journal_sha256"] = digest(gzip.decompress((dispatch / "deliveries.csv.gz").read_bytes()))
    out.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=out.parent) as temp:
        staged = Path(temp) / "result"
        staged.mkdir()
        write_csv(staged / "deliveries.csv", rows)
        write_json(staged / "summary.json", summary)
        staged.rename(out)
    return summary


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--source", type=Path, help="Locally cached pinned public assets for fresh office executions")
    cli.add_argument("--study", type=Path, default=Path("benchmarks/dispatch-role-text"))
    cli.add_argument("--dispatch-study", type=Path, default=Path("benchmarks/dispatch-workflows"))
    cli.add_argument("--out", type=Path, required=True)
    args = cli.parse_args()
    run(args.study, args.dispatch_study, args.out, source=args.source)


if __name__ == "__main__":
    main()
