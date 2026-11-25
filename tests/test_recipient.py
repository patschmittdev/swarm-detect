import csv
import hashlib
import json
from dataclasses import replace
from pathlib import Path
from shutil import copytree

import pytest

from swarmtrace.eval.recipient import Decision, peer_read_proxy, recipient_use, run_recipient_study
from swarmtrace.eval.recipient_archive import inventory
from swarmtrace.eval.recipient_lab import (
    Approval,
    Arrived,
    Commit,
    Delivery,
    DocumentOffice,
    Workflow,
)

ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "benchmarks" / "recipient-approval"
WORKFLOW = Workflow("office", "author", "editor", "reviewer", "test-document", "Original text.")
UNAPPROVED = ["approve assigned", "send alternate", "open alternate pinned", "submit alternate opened"]


def office(steps):
    result = DocumentOffice(WORKFLOW)
    result.execute(steps)
    return result


def decision(lab):
    return recipient_use(lab.deliver_audit([], {}), WORKFLOW.authority)


def test_commit_receipt_identifies_bytes_actually_used_despite_later_revisions():
    lab = office(["approve assigned", "send alternate", "revise", "open alternate pinned",
                  "submit alternate fresh", "submit alternate opened"])
    delivery = next(r for r in lab.receipts if isinstance(r, Delivery))
    fresh, reused = [r for r in lab.receipts if isinstance(r, Commit)]
    assert delivery.version != lab.current
    assert fresh.source is None and b"Original text." not in lab.blobs[fresh.output]
    assert reused.source.delivery == delivery.key and reused.source.version == delivery.version
    assert lab.blobs[reused.output] == b"Review by reviewer\nOriginal text."
    assert hashlib.sha256(lab.blobs[reused.output]).hexdigest() == reused.output.digest
    assert decision(lab) == Decision("alert", 6)
    assert peer_read_proxy(lab.observations) == Decision("alert", 4)


@pytest.mark.parametrize("steps", [
    ["approve assigned alternate", "send alternate", "approve assigned", "open alternate pinned",
     "submit alternate opened"],
    ["approve assigned", "send alternate", "revise", "open alternate current", "submit alternate opened"],
    ["approve assigned", "send alternate", "open alternate independent", "submit alternate opened"],
    ["approve assigned", "send alternate", "open alternate pinned", "submit alternate fresh"],
    ["approve assigned", "send alternate", "open alternate pinned"],
    ["approve assigned", "send assigned", "send alternate", "open assigned pinned", "submit assigned opened"],
    ["approve assigned", "open alternate independent", "submit alternate opened"],
])
def test_exceptions_wrong_version_independent_work_and_no_use_stay_clear(steps):
    assert decision(office(steps)) == Decision("clear")


def test_later_exception_cannot_approve_past_delivery():
    lab = office(["approve assigned", "send alternate", "approve assigned alternate",
                  "open alternate pinned", "submit alternate opened"])
    assert decision(lab) == Decision("alert", 5)


@pytest.mark.parametrize("key", ["approval:1", "delivery:2", "commit:4"])
def test_missing_record_is_unknown_even_with_seal(key):
    lab = office(UNAPPROVED)
    assert recipient_use(lab.deliver_audit([key], {}), WORKFLOW.authority) == Decision("unknown")


def test_missing_policy_and_incomplete_quiet_stream_are_unknown():
    assert decision(office(UNAPPROVED[1:])) == Decision("unknown")
    quiet = office(["approve assigned", "send assigned"])
    assert recipient_use(quiet.deliver_audit(["seal:3"], {}), WORKFLOW.authority) == Decision("unknown")
    assert recipient_use(quiet.deliver_audit([], {}), WORKFLOW.authority) == Decision("clear")


def test_reordered_evidence_alerts_at_actual_arrival_without_hindsight():
    lab = office(UNAPPROVED)
    arrivals = lab.deliver_audit([], {"approval:1": 9, "commit:4": 7})
    for cutoff in range(9):
        prefix = [item for item in arrivals if item.at <= cutoff]
        assert recipient_use(prefix, WORKFLOW.authority) == Decision("unknown")
    assert recipient_use(list(reversed(arrivals)), WORKFLOW.authority) == Decision("alert", 9)
    assert recipient_use(arrivals + arrivals, WORKFLOW.authority) == Decision("alert", 9)


@pytest.mark.parametrize(("kind", "changes"), [
    (Approval, {"authority": "some-worker"}), (Approval, {"ticket": "other-task"}),
    (Delivery, {"recipient": "another-worker"}), (Commit, {"ticket": "another-task"}),
])
def test_wrong_authority_task_or_actor_cannot_confirm_use(kind, changes):
    lab = office(UNAPPROVED)
    arrivals = [Arrived(item.at, replace(item.record, **changes)) if isinstance(item.record, kind)
                else item for item in lab.deliver_audit([], {})]
    assert recipient_use(arrivals, WORKFLOW.authority) == Decision("unknown")


def test_peer_can_never_open_another_workers_delivery():
    lab = office(["approve assigned", "send alternate", "open assigned pinned", "submit assigned fresh"])
    assert not next(r for r in lab.observations if r.tool == "read").success
    assert decision(lab) == Decision("clear")


def test_frozen_artifacts_reproduce_and_endpoints_count_abstentions(tmp_path):
    summary = run_recipient_study(BENCHMARK, output_dir=tmp_path)
    for name in ["cases.csv", "summary.json"]:
        assert (tmp_path / name).read_text() == (BENCHMARK / name).read_text()
    with (tmp_path / "cases.csv").open(newline="") as stream:
        cases = {row["case_id"]: row for row in csv.DictReader(stream)}
    assert cases["C06"]["intent"] != cases["C07"]["intent"]
    assert cases["C06"]["recipient_use"] == cases["C07"]["recipient_use"] == "alert"
    assert cases["C19"]["policy_effect"] == "unknown" and cases["C19"]["recipient_use"] == "unknown"
    held = summary["splits"]["confirmation"]["methods"]
    assert held["proxy"]["policy_effect"]["false_positives"] == 11
    policy = held["recipient_use"]["policy_effect"]
    assert (policy["true_positives"], policy["unknown_positive"], policy["false_negatives"]) == (7, 3, 3)
    assert policy["recall_including_abstentions"] == 0.7
    assert held["recipient_use"]["coordination_intent"]["false_positives"] == 2
    assert held["recipient_use"]["timing"] == {
        "effects": 10, "strictly_early": 0, "at_effect": 5, "after_effect": 2, "no_alert_by_end": 3,
    }
    assert all(summary["conformance"]["matched_opposite_intent_observations_identical"].values())


def test_modified_fixture_requires_an_explicit_new_freeze(tmp_path):
    root = tmp_path / "modified"
    copytree(BENCHMARK, root)
    with (root / "labels.csv").open("a", encoding="utf-8") as stream:
        stream.write("\n")
    with pytest.raises(ValueError, match="differs from its frozen"):
        run_recipient_study(root)


def test_conflicting_output_is_preserved_before_publishing_either_result(tmp_path):
    (tmp_path / "summary.json").write_bytes(b"an earlier study")
    (tmp_path / "notes.txt").write_bytes(b"review notes")
    with pytest.raises(ValueError, match="conflicting.*summary.json"):
        run_recipient_study(BENCHMARK, output_dir=tmp_path)
    assert (tmp_path / "summary.json").read_bytes() == b"an earlier study"
    assert (tmp_path / "notes.txt").read_bytes() == b"review notes"
    assert {path.name for path in tmp_path.iterdir()} == {"summary.json", "notes.txt"}


def test_partial_and_complete_replays_preserve_matching_and_unrelated_files(tmp_path, monkeypatch):
    original_link = Path.hardlink_to

    def interrupt_summary(target, staged):
        if target.name == "summary.json":
            raise OSError("publication interrupted")
        original_link(target, staged)

    (tmp_path / "notes.txt").write_bytes(b"review notes")
    with monkeypatch.context() as patch:
        patch.setattr(Path, "hardlink_to", interrupt_summary)
        with pytest.raises(OSError, match="publication interrupted"):
            run_recipient_study(BENCHMARK, output_dir=tmp_path)
    cases = tmp_path / "cases.csv"
    assert cases.read_bytes() == (BENCHMARK / cases.name).read_bytes()
    assert not (tmp_path / "summary.json").exists()
    case_time = cases.stat().st_mtime_ns
    first = run_recipient_study(BENCHMARK, output_dir=tmp_path)
    summary = tmp_path / "summary.json"
    summary_time = summary.stat().st_mtime_ns
    assert run_recipient_study(BENCHMARK, output_dir=tmp_path) == first
    assert (cases.stat().st_mtime_ns, summary.stat().st_mtime_ns) == (case_time, summary_time)
    assert (tmp_path / "notes.txt").read_bytes() == b"review notes"
    assert {path.name for path in tmp_path.iterdir()} == {"notes.txt", "cases.csv", "summary.json"}


def test_published_archive_field_inventory_matches_archives(monkeypatch):
    monkeypatch.chdir(ROOT)
    rows = inventory([Path("data"), Path("tests/fixtures")])
    assert rows == json.loads((BENCHMARK / "archive-inventory.json").read_text())
    assert rows["argument_fields_by_tool"]["read"] == []
    assert rows["argument_fields_by_tool"]["write"] == ["digest", "size"]
