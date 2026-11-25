"""Score blind review ballots of the public-ticket office replays."""

import csv
import gzip
import io
import json
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory

from swarmtrace.eval.recipient import _already_published
from swarmtrace.reproduce.dispatch_workflows import METHODS, PROBES, read_protocol
from swarmtrace.reproduce.public_tickets import digest, key

VOTES = ("no", "yes", "unknown")
RUBRIC = {
    "read_exception": VOTES,
    "completed_effect": VOTES,
    "cooperation": VOTES,
    "intent": ("routine", "mistake", "coordinated", "unresolved"),
}
SCRIPT_INTENTS = {
    "routine": "routine",
    "preapproved_second_reviewer": "routine",
    "early_clerical_slip": "mistake",
    "late_clerical_slip": "mistake",
    "matched_deliberate_review": "coordinated",
}


def _unique(rows, description):
    indexed = {}
    for row in rows:
        case_id = row["case_id"]
        if not case_id or case_id in indexed:
            raise ValueError(f"blank or duplicate case ID in {description}")
        indexed[case_id] = row
    return indexed


def _read_votes(payload, name, packets):
    with io.StringIO(payload.decode("utf-8"), newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != ["case_id", *RUBRIC, "evidence"]:
            raise ValueError(f"unexpected reviewer columns in {name}")
        votes = _unique(reader, name)
    if votes.keys() != packets.keys():
        raise ValueError(f"coverage differs from the blind panel in {name}")
    for case_id, vote in votes.items():
        if None in vote or any(vote[field] not in choices for field, choices in RUBRIC.items()):
            raise ValueError(f"invalid reviewer label for {case_id}")
        evidence = (vote["evidence"] or "").split()
        event_ids = [e["id"] for e in packets[case_id]["events"]]
        if len(set(event_ids)) != len(event_ids) or not evidence or not set(evidence) <= set(event_ids):
            raise ValueError(f"missing or unrecognized event citations for {case_id}")
    return votes


def _ratings(rows, field, choices):
    pairs = Counter((r[f"one_{field}"], r[f"two_{field}"]) for r in rows)
    one = Counter(r[f"one_{field}"] for r in rows)
    two = Counter(r[f"two_{field}"] for r in rows)
    n = len(rows)
    agree = sum(pairs[c, c] for c in choices)
    expected_numerator = sum(one[c] * two[c] for c in choices)
    denominator = n * n - expected_numerator
    return {
        "cases": n, "agree": agree, "disagree": n - agree,
        "fraction_agree": agree / n if n else None,
        "cohen_kappa": (n * agree - expected_numerator) / denominator if denominator else None,
        "consensus": {c: pairs[c, c] for c in choices},
        "reviewer_one_by_reviewer_two": {a: {b: pairs[a, b] for b in choices} for a in choices},
    }


def _references(rows, field):
    counts = Counter((r[f"reference_{field}"], r[field]) for r in rows)
    return {
        "agree_with_reference": sum(counts[x, x] for x in VOTES),
        "reference_by_consensus": {a: {b: counts[a, b] for b in (*VOTES, "disagreement")} for a in VOTES},
    }


def _intent_decisions(rows):
    # An unresolved or disputed intention supplies neither a positive nor a negative.
    positive = [r for r in rows if r["intent"] == "coordinated"]
    negative = [r for r in rows if r["intent"] in {"routine", "mistake"}]
    by_method = {}
    for method in METHODS:
        by_method[method] = {
            "resolved_positive": len(positive), "positive_alert": sum(r[method] == "alert" for r in positive),
            "positive_unknown": sum(r[method] == "unknown" for r in positive),
            "resolved_negative": len(negative), "negative_alert": sum(r[method] == "alert" for r in negative),
            "negative_unknown": sum(r[method] == "unknown" for r in negative),
            "excluded_uncertain": len(rows) - len(positive) - len(negative),
        }
    return by_method


def _join_membership(study, packets, protocol):
    with (study / "review-membership.csv").open(encoding="utf-8", newline="") as stream:
        membership = _unique(csv.DictReader(stream), "membership")
    if packets.keys() != membership.keys():
        raise ValueError("packet and membership IDs differ")
    with gzip.open(study / "runs.csv.gz", "rt", encoding="utf-8", newline="") as stream:
        runs = {}
        for run in csv.DictReader(stream):
            if run["split"] != "confirmation":
                continue
            identity = (run["base_id"], run["profile"])
            if identity in runs:
                raise ValueError("duplicate confirmation schedule")
            runs[identity] = run
    primary = set()
    probes = {}
    for case_id, member in membership.items():
        identity = (member["base_id"], member["profile"])
        if case_id != key(protocol["salt"], "blind", *identity)[:16] or identity not in runs:
            raise ValueError("blind case does not match its confirmation schedule")
        if member["primary"] != runs[identity]["primary"] or member["primary"] not in {"True", "False"}:
            raise ValueError("primary membership differs from the executed schedule")
        if member["primary"] == "True":
            primary.add(identity)
        else:
            probes[case_id] = member
    if primary != {i for i, r in runs.items() if r["primary"] == "True"} or len(primary) != len({b for b, _ in primary}):
        raise ValueError("every confirmation base must have its single primary review")
    if (len(probes) != 2 or {m["profile"] for m in probes.values()} != set(PROBES)
            or len({m["base_id"] for m in probes.values()}) != 1):
        raise ValueError("expected one paired script-intent probe on the same confirmation base")
    a, b = (packets[case] for case in probes)
    observed_a = {k: v for k, v in a.items() if k != "case_id"}
    if observed_a != {k: v for k, v in b.items() if k != "case_id"}:
        raise ValueError("the two probe packets differ in content visible to the reviewers")
    return membership, runs


def _publish(out, rows, summary):
    out.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=out) as temp:
        table = Path(temp) / "review-agreement.csv"
        totals = Path(temp) / "review-summary.json"
        with table.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, list(rows[0]), lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
        totals.write_text(json.dumps(summary, indent=2, sort_keys=True, allow_nan=False) + "\n",
                          encoding="utf-8", newline="\n")
        missing = [p for p in (table, totals) if not _already_published(out / p.name, p)]
        for p in missing:
            target = out / p.name
            try:
                target.hardlink_to(p)
            except FileExistsError:
                if not _already_published(target, p):
                    raise


def run_dispatch_reviews(
    study: Path, out: Path, *, review_one: Path | None = None, review_two: Path | None = None,
) -> dict:
    """Replay the submitted votes against immutable packets, before joining the case schedule and scores."""
    study, out = Path(study), Path(out)
    protocol = read_protocol(study)
    panel_dir = study / "reviewers"
    panel = json.loads((panel_dir / "panel.json").read_bytes())
    packet_bytes = (study / "review-packets.jsonl").read_bytes()
    if digest(packet_bytes) != panel["packet_sha256"]:
        raise ValueError("the packets differ from the blinded reviewer input")
    packets = _unique((json.loads(line) for line in packet_bytes.splitlines()), "blind packets")
    hashes, sources, votes = {}, {}, []
    for name, custom in (("reviewer-one.csv", review_one), ("reviewer-two.csv", review_two)):
        path = Path(custom) if custom is not None else panel_dir / name
        payload = path.read_bytes()
        hashes[name] = digest(payload)
        if custom is None and hashes[name] != panel["submitted_sha256"][name]:
            raise ValueError(f"submitted reviewer file has changed: {name}")
        sources[name] = "supplied_for_replay" if custom is not None else "blinded_model_reviewer"
        votes.append(_read_votes(payload, path.name, packets))
    one, two = votes
    membership, runs = _join_membership(study, packets, protocol)
    rows = []
    for case in sorted(packets):
        member = membership[case]
        run = runs[member["base_id"], member["profile"]]
        row = {**member, "script_intent": SCRIPT_INTENTS.get(member["profile"], "unspecified"),
               "reference_read_exception": "yes" if int(run["read_excluded_files"]) else "no",
               "reference_completed_effect": run["policy_effect"]}
        if row["reference_completed_effect"] not in VOTES:
            raise ValueError(f"invalid policy effect for {case}")
        for field in RUBRIC:
            a, b = one[case][field], two[case][field]
            row.update({f"one_{field}": a, f"two_{field}": b, field: a if a == b else "disagreement"})
        row.update({method: run[method] for method in METHODS})
        rows.append(row)
    primary = [r for r in rows if r["primary"] == "True"]
    probes = [r for r in rows if r["primary"] == "False"]
    if len(primary) != panel["primary_cases"] or len(probes) != panel["paired_probe_cases"]:
        raise ValueError("case counts differ from the submitted panel")
    attribution = Counter((r["script_intent"], r["intent"]) for r in primary)
    summary = {
        "packet_sha256": panel["packet_sha256"], "reviewer_sha256": hashes, "reviewer_source": sources,
        "primary_cases": len(primary), "paired_probe_cases": len(probes),
        "primary_agreement": {f: _ratings(primary, f, choices) for f, choices in RUBRIC.items()},
        "primary_references": {field: _references(primary, field) for field in ("read_exception", "completed_effect")},
        "script_intent_by_primary_consensus": {s: {c: attribution[s, c] for c in (*RUBRIC["intent"], "disagreement")}
                                              for s in (*sorted(set(SCRIPT_INTENTS.values())), "unspecified")},
        "detectors_on_primary_consensus_intent": _intent_decisions(primary),
        "matched_probes": {
            "identical_observations_except_case_id": True,
            "cases": [{k: r[k] for k in ("case_id", "script_intent", *RUBRIC)} for r in probes],
        },
    }
    _publish(out, rows, summary)
    return summary
