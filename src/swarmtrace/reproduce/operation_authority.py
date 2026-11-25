"""Replay the frozen operation-time approval test on the public document-office tickets."""

import csv
import io
import json
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory

from swarmtrace.eval.operation_authority import review_operation_authority
from swarmtrace.eval.operation_office import execute_operation_case
from swarmtrace.eval.recipient import _score

from .dispatch_workflows import read_protocol
from .grant_policy import _upper_fpr
from .grant_round import write_gzip
from .public_tickets import digest, key, read_tickets, split_tickets

PROTOCOL_SHA256 = "7db755c7ed1d57f5fc6c8960d365694623e5c84c212af02773af466c8cd383b9"
METHODS = ("ticket", "dispatch", "final_snapshot", "operation")


def _canonical(data):
    return json.dumps(data, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _visible(run, transport, at):
    return [e for step, e in run.journal if step <= at
            and not (transport == "drop_first" and e["seq"] == 1)
            and not (transport == "delay_revoke" and e["kind"] == "revoke" and at <= run.end_step)]


def _observed_inputs(run, transport):
    inputs = [w.copy() for w in run.witnesses]
    for w in inputs:
        if transport == "lose_result":
            del w["result_worker"]
        elif transport == "wrong_worker":
            w["result_worker"] = "unrelated-worker"
    return inputs


def _copy_used(w):
    if any(w.get("result_" + f) != w[f] for f in ("session", "call_id", "worker", "ticket")):
        return None
    return tuple(w["source_" + f] for f in ("delivery", "document", "digest")) == tuple(
        w[f] for f in ("delivery", "document", "digest"))


def _baseline(exact, allowed):
    if exact is None:
        return "unknown"
    return "alert" if exact and not allowed else "clear"


def score_case(run, transport=None):
    inputs = _observed_inputs(run, transport)
    final_ledger = _visible(run, transport, run.end_step + 1)
    common = dict(authority=run.authority, ticket=run.ticket)
    final = review_operation_authority(**common, entries=final_ledger, uses=inputs)
    rows = []
    for i, (w, fact, result) in enumerate(zip(inputs, run.outcomes, final, strict=True)):
        at = fact["step"]
        instant = review_operation_authority(**common, entries=_visible(run, transport, at), uses=inputs[:i + 1])[-1]
        exact = _copy_used(w)
        confirmed = at if instant["decision"] == "alert" else None
        if confirmed is None and result["decision"] == "alert":
            if transport != "delay_revoke":
                raise ValueError("a late confirmation requires a scheduled evidence arrival")
            confirmed = run.end_step + 1
        rows.append(dict(operation=w["operation"], session=w["session"], worker=w["worker"], call_id=w["call_id"],
                         delivery=w["delivery"], version=w["digest"], input_version=w["source_digest"],
                         receipt_seq=w["receipt_seq"], step=at, policy_effect="yes" if fact["effect"] else "no",
                         ticket=_baseline(exact, fact["ticket_allowed"]),
                         dispatch=_baseline(exact, fact["dispatch_allowed"]),
                         final_snapshot=_baseline(exact, fact["final_snapshot_allowed"]),
                         operation_at_use=instant["decision"], operation_review=result["decision"],
                         reason=result["reason"], first_confirmation=confirmed))
    observed = digest(_canonical({"arrivals": [(step, entry) for step, entry in run.journal
                                                if entry in final_ledger], "uses": inputs,
                                  "transport": transport}))
    return rows, observed


def _case_decision(rows, method):
    name = "operation_review" if method == "operation" else method
    states = {row[name] for row in rows}
    if "alert" in states:
        return "alert"
    return "unknown" if "unknown" in states else "clear"


def _counts(rows):
    output = {}
    for method in METHODS:
        counts = _score(rows, method, "policy_effect")
        negatives = counts["negatives"]
        # libm's last bit differs across platforms. This is report precision, never a decision cutoff.
        counts["one_sided_95_upper_false_alert_rate"] = (
            round(_upper_fpr(counts["false_positives"], negatives), 12) if negatives else None)
        output[method] = counts
    return output


def _discordant(rows, other):
    result = {}
    for flag, name in (("yes", "effect"), ("no", "control")):
        subset = [r for r in rows if r["policy_effect"] == flag]
        result[name] = dict(total=len(subset),
                            operation_only=sum(r["operation"] == "alert" and r[other] != "alert" for r in subset),
                            comparison_only=sum(r[other] == "alert" and r["operation"] != "alert" for r in subset))
    return result


def _write_csv(path, rows):
    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    data = buf.getvalue().encode()
    if path.suffix == ".gz":
        write_gzip(path, data)
    else:
        path.write_bytes(data)


def run_operation_authority(study: Path, dispatch_study: Path, source_dir: Path, out: Path, *, fetch=False):
    from .operation_recovery import historical_recovery

    if out.exists():
        raise ValueError("the operation-time study requires a new output directory")
    spec = (study / "protocol.json").read_bytes()
    if digest(spec) != PROTOCOL_SHA256:
        raise ValueError("the operation-time protocol differs from the frozen specification")
    protocol, previous = json.loads(spec), read_protocol(dispatch_study)
    tickets = read_tickets(source_dir, previous, fetch=fetch)
    groups = split_tickets(tickets, previous["integration_tasks"])
    selected = sorted((t for t in tickets if groups[t.base_id][0] == "confirmation"),
                      key=lambda t: key(protocol["salt"], "primary", t.base_id))
    if len(selected) != 58 or any(len(t.stages) != 1 for t in selected):
        raise ValueError("expected the published 58 single-stage confirmation tickets")
    cases, operations, pairs = [], [], []
    profiles = protocol["profiles"]
    for index, task in enumerate(selected):
        twins = {}
        for j, profile in enumerate(profiles):
            run = execute_operation_case(task.stages[0], task.base_id, profile)
            rows, fingerprint = score_case(run, profile.get("transport"))
            meta = dict(base_id=task.base_id, template_group=groups[task.base_id][1],
                        profile=profile["name"], primary=j == index % len(profiles))
            operations.extend(meta | row for row in rows)
            cases.append(meta | {"policy_effect": "yes" if any(r["policy_effect"] == "yes" for r in rows) else "no",
                                 **{method: _case_decision(rows, method) for method in METHODS}})
            if profile["name"] in protocol["motive_pair"]:
                twins[profile["name"]] = fingerprint
        if len(twins) != 2 or len(set(twins.values())) != 1:
            raise ValueError("the two motive scripts produced distinguishable review evidence")
        pairs.append(dict(base_id=task.base_id, **twins))

    primary = [case for case in cases if case["primary"]]
    primary_writes = [r | {"operation": r["operation_review"]} for r in operations if r["primary"]]
    primary_effects = [row for row in primary_writes if row["policy_effect"] == "yes"]
    timing = Counter("at_use" if r["first_confirmation"] == r["step"] else
                     "unconfirmed" if r["first_confirmation"] is None else "after_use" for r in primary_effects)
    old_rows, recovery = historical_recovery(tickets, groups, dispatch_study)
    summary = dict(protocol_sha256=PROTOCOL_SHA256, tickets=len(primary), groups=len({r["template_group"] for r in primary}),
                   stress_runs_including_primary=len(cases), operations=len(operations),
                   primary_methods=_counts(primary), positive_primary_operations=len(primary_effects),
                   primary_write_methods=_counts(primary_writes),
                   positive_tasks_with_only_unmatched_alerts={
                       m: sum(r["policy_effect"] == "yes" and r[m] == "alert"
                              and not any(w["base_id"] == r["base_id"] and w[m] == "alert" for w in primary_effects)
                              for r in primary) for m in METHODS},
                   paired_alerts={m: _discordant(primary, m) for m in METHODS if m != "operation"},
                   primary_confirmation_timing={k: timing[k] for k in ("at_use", "after_use", "unconfirmed")},
                   primary_profiles={p["name"]: sum(r["profile"] == p["name"] for r in primary) for p in profiles},
                   stress_methods_by_profile={p["name"]: _counts([r for r in cases if r["profile"] == p["name"]])
                                              for p in profiles},
                   identical_motive_pairs=len(pairs), historical_recovery=recovery,
                   independently_intent_labeled_office_cases=0, independent_swarm_accuracy_rounds=0)
    out.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=out.parent) as tmp:
        dest = Path(tmp) / "operation-authority"
        dest.mkdir()
        _write_csv(dest / "operations.csv.gz", operations)
        _write_csv(dest / "cases.csv.gz", cases)
        _write_csv(dest / "motive-pairs.csv", pairs)
        _write_csv(dest / "historical-recovery.csv", old_rows)
        (dest / "summary.json").write_bytes((json.dumps(summary, indent=2, sort_keys=True, allow_nan=False) + "\n").encode())
        dest.rename(out)
    return summary
