"""Replay the frozen recipient-approval experiment on a small instrumented document office."""

import argparse
import csv
import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from itertools import groupby
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal

from .recipient_lab import (
    Approval,
    Arrived,
    Commit,
    Delivery,
    DocumentOffice,
    Observation,
    Receipt,
    Seal,
    Workflow,
)

Status = Literal["alert", "clear", "unknown"]


@dataclass(frozen=True)
class Decision:
    status: Status
    first_alert: int | None = None


def peer_read_proxy(events: list[Observation]) -> Decision:
    """Approximate handoff with pre-existing V2 fields on successful peer receives and file reads."""
    writers: dict[str, str] = {}
    peers: dict[str, set[str]] = {}
    for event in events:
        if not event.success:
            continue
        if event.tool == "write":
            writers[event.target] = event.actor
        elif event.tool == "recv" and event.target != event.actor:
            peers.setdefault(event.actor, set()).add(event.target)
        elif event.tool == "read" and writers.get(event.target) in peers.get(event.actor, set()):
            return Decision("alert", event.step)
    return Decision("clear")


def _joined_status(records: dict[str, Receipt], authority: str) -> Status:
    uncertain = False
    for commit in records.values():
        if not isinstance(commit, Commit) or commit.source is None or commit.source.delivery is None:
            continue
        delivery = records.get(commit.source.delivery)
        if (not isinstance(delivery, Delivery) or delivery.step >= commit.step
                or (delivery.ticket, delivery.recipient) != (commit.ticket, commit.recipient)):
            uncertain = True
            continue
        if delivery.sender == commit.recipient or commit.source.version != delivery.version:
            continue
        approval = records.get(delivery.approval) if delivery.approval is not None else None
        if (not isinstance(approval, Approval) or approval.step >= delivery.step
                or (approval.authority, approval.ticket, approval.version)
                != (authority, delivery.ticket, delivery.version)):
            uncertain = True
            continue
        if commit.recipient not in approval.recipients:
            return "alert"
    seals = [record for record in records.values() if isinstance(record, Seal)]
    if not uncertain and len(seals) == 1:
        seal = seals[0]
        if (records.keys() - {seal.key} == seal.receipts
                and all(records[key].step < seal.step for key in seal.receipts)):
            return "clear"
    return "unknown"


def recipient_use(arrivals: list[Arrived], authority: str) -> Decision:
    """Use only receipts actually available to the monitor at each collection checkpoint."""
    records: dict[str, Receipt] = {}
    status: Status = "unknown"
    for at, batch in groupby(sorted(arrivals, key=lambda item: item.at), key=lambda item: item.at):
        for item in batch:
            record = item.record
            if at < record.step:
                raise ValueError("receipt delivered before issuance")
            if record.key in records and records[record.key] != record:
                raise ValueError(f"conflicting receipt for {record.key}")
            records[record.key] = record
        status = _joined_status(records, authority)
        if status == "alert":
            return Decision(status, at)
    return Decision(status)


def _replay(case: dict, workflows: dict) -> tuple[DocumentOffice, list[Arrived]]:
    office = DocumentOffice(Workflow(**workflows[case["workflow"]]))
    office.execute(case["steps"])
    return office, office.deliver_audit(case.get("drop", []), case.get("delay_to", {}))


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _score(rows: list[dict], method: str, endpoint: str) -> dict:
    counts = Counter((row[endpoint], row[method]) for row in rows)
    positive = sum(n for (label, _), n in counts.items() if label == "yes")
    negative = sum(n for (label, _), n in counts.items() if label == "no")
    tp, fp = counts["yes", "alert"], counts["no", "alert"]
    unknown_pos, unknown_neg = counts["yes", "unknown"], counts["no", "unknown"]
    return {
        "positives": positive, "negatives": negative, "unlabelled": len(rows) - positive - negative,
        "true_positives": tp, "false_positives": fp,
        "true_negatives": counts["no", "clear"], "false_negatives": positive - tp,
        "cleared_positive": counts["yes", "clear"],
        "unknown_positive": unknown_pos, "unknown_negative": unknown_neg,
        "recall_including_abstentions": _ratio(tp, positive),
        "precision": _ratio(tp, tp + fp), "false_positive_rate": _ratio(fp, negative),
        "resolved_coverage": _ratio(positive + negative - unknown_pos - unknown_neg,
                                    positive + negative),
    }


def _timing(rows: list[dict], method: str) -> dict:
    counts = dict(strictly_early=0, at_effect=0, after_effect=0, no_alert_by_end=0)
    for row in rows:
        if row["effect_step"] is None:
            continue
        at = row[f"{method}_step"]
        effect = row["effect_step"]
        if at is None:
            counts["no_alert_by_end"] += 1
        elif at < effect:
            counts["strictly_early"] += 1
        elif at == effect:
            counts["at_effect"] += 1
        else:
            counts["after_effect"] += 1
    return {"effects": sum(counts.values()), **counts}


def _read_frozen(root: Path) -> tuple[dict, dict, dict]:
    frozen = json.loads((root / "freeze.json").read_text(encoding="utf-8"))
    if set(frozen) != {"protocol.json", "fixtures.json", "labels.csv"}:
        raise ValueError("frozen inputs must include the protocol, fixtures and labels")
    for name, digest in frozen.items():
        content = (root / name).read_text(encoding="utf-8").encode()
        if hashlib.sha256(content).hexdigest() != digest:
            raise ValueError(f"{name} differs from its frozen LF-normalized SHA-256")
    fixtures = json.loads((root / "fixtures.json").read_text(encoding="utf-8"))
    protocol = json.loads((root / "protocol.json").read_text(encoding="utf-8"))
    ids = []
    splits = []
    for split in ("development", "confirmation"):
        cases = fixtures[split]
        workflows = {case["workflow"] for case in cases}
        if (len(cases) != protocol[f"{split}_cases"]
                or workflows != set(protocol[f"{split}_workflows"])):
            raise ValueError(f"{split} differs from the frozen partition")
        splits.append(workflows)
        ids.extend(case["id"] for case in cases)
    if splits[0] & splits[1] or len(ids) != len(set(ids)):
        raise ValueError("development and confirmation must be disjoint")
    return fixtures, protocol, frozen


def _already_published(target: Path, staged: Path) -> bool:
    if not target.is_symlink():
        if not target.exists():
            return False
        if target.is_file() and target.read_bytes() == staged.read_bytes():
            return True
    raise ValueError(f"conflicting benchmark output at {target}")


def _publish(destination: Path, rows: list[dict], summary: dict) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".recipient-round-", dir=destination) as temporary:
        cases, totals = (Path(temporary) / name for name in ("cases.csv", "summary.json"))
        with cases.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, list(rows[0]), lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
        totals.write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n",
                          encoding="utf-8", newline="\n")
        # Verify both destinations before exposing either result. Linking a fully written file
        # is atomic and cannot replace a concurrently published file. Publish the summary last.
        missing = [source for source in (cases, totals)
                   if not _already_published(destination / source.name, source)]
        for source in missing:
            target = destination / source.name
            try:
                target.hardlink_to(source)
            except FileExistsError:
                if not _already_published(target, source):
                    raise


def run_recipient_study(benchmark_dir: Path, *, output_dir: Path | None = None) -> dict:
    root = Path(benchmark_dir)
    fixtures, _protocol, frozen = _read_frozen(root)
    rows = []
    observations = {}
    # Finish all monitor predictions without passing adjudications, intent or case IDs to either.
    for split in ("development", "confirmation"):
        for case in fixtures[split]:
            office, audit = _replay(case, fixtures["workflows"])
            proxy = peer_read_proxy(office.observations)
            use = recipient_use(audit, office.workflow.authority)
            case_id = case["id"]
            observations[case_id] = (office.observations, audit)
            rows.append({
                "case_id": case_id, "split": split, "workflow": case["workflow"],
                "proxy": proxy.status, "proxy_step": proxy.first_alert,
                "recipient_use": use.status, "recipient_use_step": use.first_alert,
                "complete_timely_transport": not (case.get("drop") or case.get("delay_to")),
                "submissions": tuple(office.submissions),
            })
    with (root / "labels.csv").open(encoding="utf-8", newline="") as stream:
        labels = list(csv.DictReader(stream))
    by_id = {label["case_id"]: label for label in labels}
    if len(labels) != len(by_id) or by_id.keys() != observations.keys():
        raise ValueError("each replay needs one separately stored case adjudication")
    for row in rows:
        label = by_id[row["case_id"]]
        intent, policy = label["intent"], label["policy_effect"]
        effect = int(label["effect_step"]) if label["effect_step"] else None
        submissions = row.pop("submissions")
        if (intent not in {"benign", "mistake", "coordinated"} or policy not in {"yes", "no", "unknown"}
                or (policy == "yes") != (effect is not None)
                or (effect is not None and effect not in submissions)):
            raise ValueError(f"inconsistent adjudication for {row['case_id']}")
        row.update(intent=intent, intended="yes" if intent == "coordinated" else "no",
                   policy_effect=policy, effect_step=effect)
    summary = {"input_sha256": frozen, "splits": {}}
    for split in ("development", "confirmation"):
        subset = [row for row in rows if row["split"] == split]
        summary["splits"][split] = {
            "cases": len(subset), "intent_labels": dict(Counter(row["intent"] for row in subset)),
            "methods": {method: {"policy_effect": _score(subset, method, "policy_effect"),
                                 "coordination_intent": _score(subset, method, "intended"),
                                 "timing": _timing(subset, method)}
                        for method in ("proxy", "recipient_use")},
        }
    confirmation = [row for row in rows if row["split"] == "confirmation"]
    complete = [row for row in confirmation
                if row["policy_effect"] == "yes" and row["complete_timely_transport"]]
    twin_pairs = {
        f"{first}/{second}": observations[first] == observations[second]
        for first, second in (("C06", "C07"), ("C04", "C18"))
    }
    summary["conformance"] = {
        "complete_timely_policy_positives": len(complete),
        "complete_timely_policy_positives_flagged": sum(row["recipient_use"] == "alert"
                                                       for row in complete),
        "policy_negative_alerts": sum(row["policy_effect"] == "no" and row["recipient_use"] == "alert"
                                      for row in confirmation),
        "matched_opposite_intent_observations_identical": twin_pairs,
    }
    if output_dir is not None:
        _publish(Path(output_dir), rows, summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark-dir", type=Path, default=Path("benchmarks/recipient-approval"))
    parser.add_argument("--out", "--output-dir", dest="output_dir", type=Path,
                        help="Publish the two result files and verify any existing copies")
    args = parser.parse_args()
    print(json.dumps(run_recipient_study(args.benchmark_dir, output_dir=args.output_dir),
                     indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
