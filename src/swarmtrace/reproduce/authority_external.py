"""Audit commit-time ticket witnesses and separately paired human coordination judgments."""

import argparse
import io
import json
from collections import Counter, defaultdict
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.request import Request, urlopen

from swarmtrace.reproduce.public_tickets import digest

CTA = "https://anonymous.4open.science/api/repo/commit-time-authorization/file/studies/local-specificity-v1/evidence"
SALT = "https://huggingface.co/datasets/SALT-NLP/agent-collusion/resolve/2eba8f3771e8fbcc0f49f6cbbfd2111b939a117a/data"
POLICY = "revocation-after-issuance-v1.json"
ASSETS = {
    POLICY: (CTA, 104984, "eb860c29c48d324d02f9d8a4698bf560c9f9b6add7e410080c6a3d4c4cc9bf54"),
    "human_samples.parquet": (SALT, 119113, "c36b3a8011d4ac8665d55d0e4676d6e1508170c1d973b05ea83f8c143912ff70"),
    "human_annotations.parquet": (SALT, 9697, "5d1eddecd79e3a22301fdd468c82298070328950aad4a3cef478e60019141611"),
    "human_answers.parquet": (SALT, 3519, "d51a2f92195d518973c71c13e3328ad28d466751a24fa7363850db9e3fd5ab33"),
}


def _publish(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temp = Path(stream.name)
        stream.write(payload)
    try:
        try:
            path.hardlink_to(temp)
        except FileExistsError:
            if path.is_symlink() or path.read_bytes() != payload:
                raise ValueError(f"conflicting file {path.name}") from None
    finally:
        temp.unlink(missing_ok=True)


def _source(directory, name, fetch):
    base, size, expected = ASSETS[name]
    path = directory / name
    try:
        with path.open("rb") as stream:
            payload = stream.read(size + 1)
    except FileNotFoundError:
        if not fetch:
            raise ValueError(f"missing {name}, supply --source-dir or use --fetch") from None
        request = Request(f"{base}/{name}", headers={"User-Agent": "swarmtrace-evidence-research"})
        with urlopen(request, timeout=45) as response:
            payload = response.read(size + 1)
    if len(payload) != size or digest(payload) != expected:
        raise ValueError(f"original source size or SHA-256 differs for {name}")
    if fetch:
        _publish(path, payload)
    return payload


def _policy(rows):
    groups = defaultdict(Counter)
    attempts = Counter()
    coverage = Counter()
    seen = set()
    for row in rows:
        identity = row["case"], row["defense"]
        if identity in seen or row["agent_action_source"] != "deterministic constructor (no model)":
            raise ValueError("unexpected service case or action source")
        seen.add(identity)
        s = row["sink_record"]
        action = row["agent_action"]
        if (set(action) != {"approval_id", "new_status", "observed_approval_epoch", "observed_ticket_version", "ticket_id"}
                or not all(isinstance(action[k], str) and action[k] for k in ("approval_id", "new_status", "ticket_id"))
                or not all(type(action[k]) is int for k in ("observed_approval_epoch", "observed_ticket_version"))):
            raise ValueError("expected the versioned ticket operation from the publisher's constructor")
        coverage["ticket_operation_with_observed_version_and_approval_epoch"] += 1
        coverage["observed_ticket_version_matches_precommit"] += int(
            action["observed_ticket_version"] == s["ticket_version_before_commit"])
        coverage["rows_with_sink_attempts"] += int(bool(row["commit_attempts"]))
        delta = s["ticket_version_after_commit"] - s["ticket_version_before_commit"]
        if (type(s["applied"]) is not bool or delta != int(s["applied"])
                or s["ticket_version_after_commit"] != row["ticket_state_at_end"]["version"]):
            raise ValueError("the ticket state disagrees with the applied effect")
        # Reconstruct the row label from measured state change and the service's own oracle.
        outcome = "S" if delta == 0 else "A" if s["oracle_authorized"] else "U"
        if outcome != row["sink_outcome"] or row["commit_attempt_count"] != len(row["commit_attempts"]):
            raise ValueError("published outcome or attempt count disagrees with the sink")
        groups[row["group"]][outcome] += 1
        for attempt in row["commit_attempts"]:
            attempts["recorded"] += 1
            attempts["applied"] += int(attempt["sink_applied"])
            grant = attempt["derived_grant"]
            if grant is not None:
                if all(grant["conditions"].values()) != grant["valid"]:
                    raise ValueError("derived permission disagrees with the recorded consumption checks")
                attempts["valid_reservation_consumed_after_source_lost"] += int(
                    grant["valid"] and not attempt["source"]["source_grant_live"] and attempt["sink_applied"])
                for condition in ("unconsumed", "unexpired"):
                    attempts[f"refused_failed_{condition}"] += int(not grant["conditions"][condition] and not attempt["sink_applied"])
    return {"rows": len(seen), "field_coverage": coverage, "service_outcomes_by_group": groups, "attempts": attempts,
            "outcome_labels": {"A": "authorized applied", "U": "unauthorized applied", "S": "safe non-completion"}}


def _human(samples, annotations, answers):
    def index(rows):
        keyed = {(r["sample_id"], r["signal"]): r for r in rows}
        if len(rows) != len(keyed):
            raise ValueError("duplicate human item")
        return keyed

    samples, answers = index(samples), index(answers)
    reviewers = defaultdict(dict)
    for row in annotations:
        raters = reviewers[row["sample_id"], row["signal"]]
        if row["annotator"] in raters or type(row["label"]) is not bool:
            raise ValueError("duplicate reviewer or invalid human rating")
        raters[row["annotator"]] = row["label"]
    if not (samples.keys() == answers.keys() == reviewers.keys()):
        raise ValueError("human and adjudicated responses must reference the same sample and signal")
    output = defaultdict(Counter)
    episodes = defaultdict(set)
    for key, row in samples.items():
        signal = row["signal"]
        votes = list(reviewers[key].values())
        gold = answers[key]["gold_label"]
        if (len(votes) != 2 or type(gold) is not bool or type(row["llm_label"]) is not bool
                or votes[0] == votes[1] and votes[0] != gold):
            raise ValueError("invalid paired human votes or adjudication")
        episodes[signal].add((row["run_id"], row["episode_index"]))
        counts = output[signal]
        counts["paired_samples"] += 1
        counts["agree"] += int(votes[0] == votes[1])
        counts["disagree"] += int(votes[0] != votes[1])
        counts["gold_yes" if gold else "gold_no"] += 1
        counts["upstream_judge_matches_gold"] += int(row["llm_label"] == gold)
    for signal, pointers in episodes.items():
        output[signal]["distinct_run_episode_pairs"] = len(pointers)
    return dict(output)


def run_external_authority(source_dir: Path, out: Path, *, fetch=False) -> dict:
    """Recompute each source's endpoint using source-specific identities; emit aggregate counts."""
    try:
        import pyarrow.parquet as pq
    except ImportError:
        raise ValueError("external authority replay needs optional pyarrow, tested with pyarrow==21.0.0") from None
    source_dir = Path(source_dir)
    service = json.loads(_source(source_dir, POLICY, fetch))
    columns = {
        "samples": ["sample_id", "signal", "run_id", "episode_index", "llm_label"],
        "annotations": ["sample_id", "signal", "annotator", "label"],
        "answers": ["sample_id", "signal", "gold_label"],
    }
    tables = {}
    for name, selected in columns.items():
        payload = _source(source_dir, f"human_{name}.parquet", fetch)
        tables[name] = pq.read_table(io.BytesIO(payload), columns=selected).to_pylist()
    report = {
        "sources": {name: {"url": f"{base}/{name}", "bytes": size, "sha256": sha}
                    for name, (base, size, sha) in ASSETS.items()},
        "policy": _policy(service["rows"]), "human_signals": _human(**tables),
        "common_endpoint": {
            "cases_with_operation_time_approval_consumed_document_and_human_motive": 0,
            "independent_swarm_accuracy_rounds": 0,
            "reason": "Ticket-service cases have constructed actions and no human motive judgments. Human sample IDs identify grading conversations or reflections with no corresponding ticket-service or document-use record.",
        },
    }
    _publish(Path(out) / "external-evidence.json", (json.dumps(report, sort_keys=True, indent=2) + "\n").encode())
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--fetch", action="store_true")
    args = parser.parse_args()
    run_external_authority(args.source_dir, args.out, fetch=args.fetch)
