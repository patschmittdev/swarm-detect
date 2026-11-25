import csv
import gzip
import shutil
from dataclasses import replace
from pathlib import Path

import pytest

from swarmtrace.eval.recipient_lab import Approval, Arrived, Version, Workflow
from swarmtrace.reproduce import dispatch_workflows as workflow
from swarmtrace.reproduce.operation_recovery import (
    IssuerArchiveOffice,
    historical_recovery,
    recover_at_end,
)
from swarmtrace.reproduce.public_tickets import Stage, Ticket, digest

DISPATCH = Path(__file__).resolve().parents[1] / "benchmarks" / "dispatch-workflows"


def office(steps):
    job = Workflow("office", "author", "proofreader", "deputy", "minutes", "A revised agenda.")
    run = IssuerArchiveOffice(job, run_id="aaaabbbb12345678")
    run.execute(steps)
    return run


EFFECT = ["approve assigned", "send alternate", "open alternate pinned", "submit alternate opened"]


def test_issuer_copy_remembers_the_selected_issuance_after_policy_supersession_and_transport_loss():
    run = office([*EFFECT[:2], "approve assigned alternate", *EFFECT[2:]])
    received = run.deliver_audit(["approval:1"], {})
    earlier = run.lookup("office", run.ticket, "approval:1", run.current, 2)
    later = run.lookup("office", run.ticket, "approval:3", run.current, 4)
    assert isinstance(earlier.approval, Approval) and later.approval.recipients > earlier.approval.recipients
    assert earlier.dispatch_step == 2 and later.dispatch_step == 4
    assert run.lookup("office", run.ticket, "approval:1", run.current, 4) is None
    assert run.lookup("office", run.ticket, "approval:1", run.current, 1) is None
    assert run.lookup("another-office", run.ticket, "approval:1", run.current, 2) is None
    assert run.lookup("office", "other-ticket", "approval:1", run.current, 2) is None
    assert run.lookup("office", run.ticket, "approval:1", Version("minutes", "b" * 64), 2) is None
    # Only the separately issued copy and transport arrivals are available to subsequent recovery.
    run._policies.clear()
    run.receipts.clear()
    assert recover_at_end(received, "office", run.lookup, end=run.step + 1) == ("alert", 1, 1)
    assert recover_at_end(received, "office", lambda *_: None, end=run.step + 1) == ("unknown", 1, 0)


@pytest.mark.parametrize("fields", [
    {"key": "approval:another"}, {"authority": "outsider"}, {"ticket": "another-ticket"},
    {"version": Version("another-file", "0" * 64)}, {"version": Version("minutes", "b" * 64)},
    {"recipients": ["proofreader"]}, {"step": 2},
])
def test_wrong_handle_issuer_ticket_bytes_recipient_schema_or_issuance_time_remains_unknown(fields):
    run = office(EFFECT)
    received = run.deliver_audit(["approval:1"], {})
    authentic = run.lookup("office", run.ticket, "approval:1", run.current, 2)
    wrong = replace(authentic, approval=replace(authentic.approval, **fields))
    assert recover_at_end(received, "office", lambda *_: wrong, end=50) == ("unknown", 1, 0)


@pytest.mark.parametrize("lost", [["approval:1"], ["approval:1", "approval:2"]])
def test_issuer_detects_a_stale_handle_even_if_both_it_and_its_superseder_were_lost(lost):
    run = office(["approve assigned", "approve assigned alternate", "send alternate", "open alternate pinned",
                  "submit alternate opened"])
    # The worker was authorized at delivery 3, but its wire handle identifies an older grant.
    received = [Arrived(a.at, replace(a.record, approval="approval:1")) if a.record.key == "delivery:3" else a
                for a in run.deliver_audit(lost, {})]
    assert recover_at_end(received, "office", run.lookup, end=10) == ("unknown", 1, 0)
    assert recover_at_end(received, "office", lambda *_: None, end=10) == ("unknown", 1, 0)


@pytest.mark.parametrize(("early_mode", "expected"), [("fresh", "unknown"), ("opened", "alert")])
def test_one_old_handle_is_valid_for_the_early_delivery_and_stale_for_the_later_one(early_mode, expected):
    run = office(["approve assigned", "send alternate", "open alternate pinned", f"submit alternate {early_mode}",
                  "approve assigned alternate", "send alternate", "open alternate pinned", "submit alternate opened"])
    received = [Arrived(a.at, replace(a.record, approval="approval:1")) if a.record.key == "delivery:6" else a
                for a in run.deliver_audit(["approval:1", "approval:5"], {})]
    assert recover_at_end(received, "office", run.lookup, end=10) == (expected, 1, 1)
    # Replaying the early, correctly scoped issuer response at the later dispatch must not restore it there.
    earlier = run.lookup("office", run.ticket, "approval:1", run.current, 2)
    assert recover_at_end(received, "office", lambda *_: earlier, end=10) == (expected, 1, 1)
    assert recover_at_end(received, "office", lambda *_: None, end=10) == ("unknown", 1, 0)


def test_queries_only_missing_handles_named_by_a_received_delivery_and_deduplicates_retries():
    run = office(["approve assigned", "send alternate", "send alternate", "open alternate pinned",
                  "submit alternate opened"])
    queries = []

    def lookup(*request):
        queries.append(request)
        return run.lookup(*request)

    complete = run.deliver_audit([], {})
    assert recover_at_end(complete, "office", lookup, end=20) == ("alert", 0, 0)
    assert queries == []
    missing = run.deliver_audit(["approval:1"], {})
    assert recover_at_end(missing + missing, "office", lookup, end=20) == ("alert", 1, 1)
    assert queries == [("office", run.ticket, "approval:1", run.current, step) for step in (2, 3)]
    lost = run.deliver_audit(["approval:1", "delivery:2", "delivery:3"], {})
    assert recover_at_end(lost, "office", lookup, end=20) == ("unknown", 0, 0)
    assert len(queries) == 2


def miniature(root):
    # Locally authored source and baseline, using the published deterministic schedule assignment.
    shutil.copyfile(DISPATCH / "protocol.json", root / "protocol.json")
    settings = workflow.read_protocol(root)
    selected = {}
    for i in range(200):
        title = f"record-{i}"
        raw = f"Updated {i} expense items."
        stage = Stage(title + "-stage", "expenses", "author", "submission/notes.md", ("legal",), raw,
                      digest(f"Designate legal for record {i}".encode()))
        task = Ticket(title, "expenses", (stage,))
        profile = workflow.design(task, settings)[2]
        if profile in ("missing_approval", "late_clerical_slip", "routine"):
            selected.setdefault(profile, task)
        if len(selected) == 3:
            break
    assert len(selected) == 3
    source_rows, run_rows = [], []
    for profile, task in selected.items():
        s, = task.stages
        source_rows.append(dict(base_id=task.base_id, stage_id=s.stage_id, split="confirmation", document=s.document,
                                document_sha256=digest(s.text.encode()), ticket_sha256=s.ticket_digest,
                                named_recipients="legal"))
        run_rows.append(dict(base_id=task.base_id, split="confirmation", primary="True", profile=profile,
                             template_group="expense", policy_effect="no" if profile == "routine" else "yes",
                             commit={"routine": "clear", "missing_approval": "unknown", "late_clerical_slip": "alert"}[profile]))
    with (root / "sources.csv").open("w", encoding="utf-8", newline="") as sf:
        w = csv.DictWriter(sf, source_rows[0].keys())
        w.writeheader()
        w.writerows(source_rows)
    with gzip.open(root / "runs.csv.gz", "wt", encoding="utf-8", newline="") as rf:
        w = csv.DictWriter(rf, run_rows[0].keys())
        w.writeheader()
        w.writerows(run_rows)
    return list(selected.values()), {t.base_id: ("confirmation", "expense") for t in selected.values()}


def test_source_office_replays_exact_membership_archive_decisions_and_compares_case_end_counts(tmp_path):
    tasks, groups = miniature(tmp_path)
    rows, summary = historical_recovery(tasks, groups, tmp_path)
    assert [r["base_id"] for r in rows] == sorted(t.base_id for t in tasks)
    assert (summary["cases"], summary["positives"], summary["controls"], summary["requested_approvals"],
            summary["recovered_approvals"], summary["newly_detected_effects"]) == (3, 2, 1, 1, 1, 1)
    arm = summary["methods"]
    assert arm["original_commit"] == arm["empty_issuer_commit"] == dict(
        detections=1, false_alerts=0, unknown_positive=1, unknown_control=0)
    assert arm["issuer_commit"] == dict(detections=2, false_alerts=0, unknown_positive=0, unknown_control=0)
    assert summary["independent_swarm_rounds"] == 0
    with pytest.raises(ValueError, match="membership"):
        historical_recovery(tasks[:2], groups, tmp_path)
    task = tasks[0]
    other_version = replace(task, stages=(replace(task.stages[0], text="Independent version"),))
    with pytest.raises(ValueError, match="document version"):
        historical_recovery([other_version, *tasks[1:]], groups, tmp_path)
    damaged = gzip.decompress((tmp_path / "runs.csv.gz").read_bytes()).replace(b",unknown", b",clear")
    (tmp_path / "runs.csv.gz").write_bytes(gzip.compress(damaged))
    with pytest.raises(ValueError, match="committed-use decision differs"):
        historical_recovery(tasks, groups, tmp_path)
