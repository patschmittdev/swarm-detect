import csv
import json
from dataclasses import replace
from pathlib import Path

import pytest

from swarmtrace.eval.recipient import Decision
from swarmtrace.eval.recipient_dispatch import (
    DispatchOffice,
    case_results,
    committed_use_by_delivery,
    delivery_results,
    dispatch_warnings,
    evaluate_office,
    run_dispatch_study,
)
from swarmtrace.eval.recipient_lab import (
    Approval,
    Arrived,
    Commit,
    Delivery,
    DocumentOffice,
    Version,
    Workflow,
)

ROOT = Path(__file__).resolve().parents[1] / "benchmarks"
WORK = Workflow("records office", "author", "assigned", "alternate", "minutes", "Reviewed text.")
EFFECT = ["approve assigned", "send alternate", "open alternate pinned", "submit alternate opened"]


def run(steps=EFFECT):
    office = DispatchOffice(WORK)
    office.execute(steps)
    return office


@pytest.mark.parametrize(("drop", "delay", "dispatch_at", "commit_at"), [
    ([], {}, 2, 4), ([], {"approval:1": 4}, 4, 4), ([], {"delivery:2": 8}, 8, 8),
    (["approval:1"], {}, None, None), (["delivery:2"], {}, None, None), (["commit:4"], {}, 2, None),
    (["seal:5"], {}, 2, 4),
])
def test_timing_and_missing_evidence_at_every_arrival(drop, delay, dispatch_at, commit_at):
    office = run()
    arrivals = office.deliver_audit(drop, delay)
    for t in range(10):
        prefix = [r for r in reversed(arrivals) if r.at <= t]
        warning = dispatch_warnings(prefix, WORK.authority).get("delivery:2", Decision("unknown"))
        use = committed_use_by_delivery(prefix, WORK.authority).get("delivery:2", Decision("unknown"))
        for result, expected in ((warning, dispatch_at), (use, commit_at)):
            assert result == (Decision("alert", expected) if expected is not None and t >= expected
                              else Decision("unknown"))
    case, copies = evaluate_office(office, arrivals + arrivals)
    assert len(copies) == 1 and copies[0]["effect_step"] == case["effect_step"] == 4
    assert copies[0]["dispatch_step"] == dispatch_at and copies[0]["commit_step"] == commit_at


def test_same_handle_read_and_strict_timing_exclude_a_warning_for_an_earlier_unused_copy():
    office = run(["approve assigned", "send alternate", "send alternate",
                  "open alternate pinned", "submit alternate opened"])
    arrivals = office.deliver_audit(["delivery:3"], {})
    case, (unused, effected) = evaluate_office(office, arrivals)
    assert (case["dispatch"], case["dispatch_step"], case["dispatch_matched_step"]) == ("alert", 2, None)
    assert (unused["dispatch"], unused["policy_effect"], unused["exact_use_step"]) == ("alert", "no", None)
    assert (effected["delivery"], effected["policy_effect"], effected["effect_step"]) == ("delivery:3", "yes", 5)
    assert effected["dispatch"] == effected["commit"] == "unknown"
    assert effected["proxy_step"] == 4 and unused["proxy_step"] is None


@pytest.mark.parametrize(("steps", "unpaired", "matched"), [
    (["approve assigned", "send alternate", "open alternate pinned", "submit alternate fresh"], 0, 3),
    (["approve assigned", "send alternate", "revise", "open alternate current", "submit alternate opened"], 1, None),
    (["approve assigned", "send alternate", "open alternate independent", "submit alternate opened"], 1, None),
    (["approve assigned", "send alternate"], 0, None),
])
def test_complete_unused_deliveries_contribute_false_reviews_even_if_peer_read_occurs(steps, unpaired, matched):
    office = run(steps)
    case, (row,) = evaluate_office(office, office.deliver_audit([], {}))
    assert (row["authorized"], row["policy_effect"], row["exact_use_step"]) == ("no", "no", None)
    assert (row["dispatch"], row["commit"]) == ("alert", "clear")
    assert row["proxy_step"] == matched and case["unpaired_proxy_reads"] == unpaired
    dates = [item for item in office.deliver_audit([], {}) if not item.record.key.startswith("seal:")]
    assert delivery_results(office, dates)[0]["commit"] == "unknown"


def test_dispatch_snapshot_survives_later_exception_or_revocation():
    office = run(["approve assigned alternate", "send alternate", "approve assigned", "send alternate",
                  "approve assigned alternate", "open alternate pinned", "submit alternate opened"])
    arrivals = office.deliver_audit([], {})
    before, after = delivery_results(office, arrivals)
    assert (before["authorized"], before["dispatch"], before["policy_effect"]) == ("yes", "clear", "no")
    assert (after["authorized"], after["dispatch_step"], after["effect_step"]) == ("no", 4, 7)
    damaged = [Arrived(r.at, replace(r.record, approval="approval:1")) if r.record.key == "delivery:4" else r
               for r in arrivals]
    with pytest.raises(ValueError, match="superseded"):
        dispatch_warnings(damaged, WORK.authority)


@pytest.mark.parametrize(("changes", "kind", "warning", "use"), [
    ({"authority": "counter clerk"}, Approval, "unknown", "unknown"),
    ({"ticket": "another"}, Approval, "unknown", "unknown"),
    ({"version": Version("minutes", "a" * 64)}, Approval, "unknown", "unknown"),
    ({"version": Version("minutes", "bad digest")}, Approval, "unknown", "unknown"),
    ({"approval": "approval:absent"}, Delivery, "unknown", "unknown"),
    ({"recipient": ""}, Delivery, "unknown", "unknown"),
    ({"recipient": "author"}, Delivery, "clear", "unknown"),
    ({"recipient": "assigned"}, Commit, "alert", "unknown"),
    ({"ticket": "another"}, Commit, "alert", "unknown"),
    ({"step": 2}, Commit, "alert", "unknown"),
    ({"output": Version("review", "")}, Commit, "alert", "unknown"),
])
def test_identity_authority_version_and_order_do_not_substitute_for_the_matching_evidence(changes, kind, warning, use):
    office = run()
    arrivals = [Arrived(e.at, replace(e.record, **changes)) if isinstance(e.record, kind) else e
                for e in office.deliver_audit([], {})]
    assert dispatch_warnings(arrivals, WORK.authority)["delivery:2"].status == warning
    assert committed_use_by_delivery(arrivals, WORK.authority)["delivery:2"].status == use


def test_independent_authority_and_receipt_key_collisions():
    office = run()
    arrivals = office.deliver_audit([], {})
    with pytest.raises(ValueError, match="authority"):
        dispatch_warnings(arrivals, "")
    changed = replace(arrivals[0].record, recipients=frozenset())
    with pytest.raises(ValueError, match="conflicting"):
        dispatch_warnings([*arrivals, Arrived(7, changed)], WORK.authority)
    with pytest.raises(ValueError, match="issuance"):
        dispatch_warnings([Arrived(0, arrivals[1].record)], WORK.authority)
    commit = next(e for e in arrivals if isinstance(e.record, Commit))
    irrelevant = Arrived(1, commit.record)
    assert dispatch_warnings([*arrivals, irrelevant], WORK.authority) == {"delivery:2": Decision("alert", 2)}


def test_missing_authority_and_no_delivery_are_distinct_from_verified_negative():
    missing = run(EFFECT[1:])
    row, = delivery_results(missing, missing.deliver_audit([], {}))
    assert row["authorized"] == row["policy_effect"] == row["dispatch"] == row["commit"] == "unknown"
    assert row["exact_use_step"] == 3
    quiet = run(["discuss alternate", "open alternate independent", "submit alternate opened"])
    arrivals = quiet.deliver_audit([], {})
    case, copies = evaluate_office(quiet, arrivals)
    assert copies == [] and case["dispatch"] == case["commit"] == "clear" and case["proxy"] == "alert"
    assert case_results(quiet, [])["dispatch"] == "unknown"


def test_journal_extends_the_same_executed_office_and_preserves_seal_and_observations():
    class Extended(DispatchOffice):
        def _execute_instruction(self, step, instruction):
            if instruction == "file copy count":
                self.checked = (step, len(self.dispatches))
            else:
                super()._execute_instruction(step, instruction)

    baseline = DocumentOffice(WORK)
    baseline.execute(EFFECT)
    observed = run()
    assert (observed.observations, observed.receipts, observed.submissions) == (
        baseline.observations, baseline.receipts, baseline.submissions)
    extended = Extended(WORK)
    extended.execute([*EFFECT[:2], "file copy count", *EFFECT[2:]])
    assert extended.checked == (3, 1) and extended.first_exact_use == {"delivery:2": 5}
    assert extended.receipts[-1].key == "seal:6"


def test_released_partition_decisions_and_bytes_reproduce(tmp_path):
    summary = run_dispatch_study(ROOT / "recipient-approval", output_dir=tmp_path)
    for name in ("summary.json", "deliveries.csv", "cases.csv"):
        assert (tmp_path / name).read_bytes() == (ROOT / "recipient-dispatch-contract" / name).read_bytes()
    s = summary["splits"]["confirmation"]
    assert (s["cases"], s["deliveries"], s["unused_deliveries"], s["cases_without_dispatch"]) == (24, 23, 7, 3)
    m = s["methods"]
    assert m["dispatch"]["delivery_timing"] == dict(effects=10, strictly_early=6, at_effect=0, after_effect=2,
                                                    no_alert_by_end=2)
    for name, tp, fp in (("dispatch", 8, 5), ("commit", 7, 0), ("proxy", 10, 8)):
        d = m[name]["delivery_effect"]
        assert (d["positives"], d["negatives"], d["unlabelled"], d["true_positives"], d["false_positives"]) == (
            10, 12, 1, tp, fp)
    assert m["dispatch"]["unused_delivery_alerts"] == 5
    with (tmp_path / "cases.csv").open() as f:
        rows = {r["case_id"]: r for r in csv.DictReader(f)}
    assert (rows["C23"]["proxy_step"], rows["C23"]["proxy_matched_step"], rows["C23"]["effect_step"]) == ("3", "6", "7")
    for field in ("dispatch", "commit", "dispatch_step", "commit_step", "proxy_matched_step"):
        assert rows["C06"][field] == rows["C07"][field] and rows["C06"]["intent"] != rows["C07"]["intent"]
    assert json.loads((tmp_path / "summary.json").read_bytes()) == summary
    assert run_dispatch_study(ROOT / "recipient-approval", output_dir=tmp_path) == summary
