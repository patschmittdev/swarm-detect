import csv
import gzip
import json
import sqlite3
from collections import Counter
from contextlib import closing
from pathlib import Path

import pytest

from swarmtrace import cli
from swarmtrace.eval.operation_office import PolicyStore, _OperationOffice, execute_operation_case
from swarmtrace.eval.recipient_lab import Commit, Version
from swarmtrace.reproduce import operation_authority as replay
from swarmtrace.reproduce.public_tickets import Stage, digest

STUDY = Path(__file__).resolve().parents[1] / "benchmarks" / "operation-authority"
SPEC = json.loads((STUDY / "protocol.json").read_bytes())
STAGE = Stage("a1", "routine review", "editor", "example.md", ("legal_approval_specialist",),
              "An original office document.", "ticket")
PROFILES = {p["name"]: p for p in SPEC["profiles"]}


@pytest.mark.parametrize("profile", SPEC["profiles"], ids=lambda p: p["name"])
def test_native_write_observes_the_predeclared_effect_without_exposing_policy_labels(profile):
    run = execute_operation_case(STAGE, "ticket", profile)
    rows, _ = replay.score_case(run, profile.get("transport"))
    assert [r["policy_effect"] == "yes" for r in rows] == profile["effects"]
    assert len({(w["session"], w["call_id"]) for w in run.witnesses}) == len(rows)
    for w, row in zip(run.witnesses, rows, strict=True):
        assert "effect" not in w and w["call_id"] == w["result_call_id"]
        assert row["version"] == digest(STAGE.text.encode())
    if profile.get("transport") in ("wrong_worker", "lose_result"):
        assert all(rows[0][n] == "unknown" for n in ("dispatch", "ticket", "final_snapshot", "operation_review"))
    elif profile.get("transport") == "drop_first":
        assert rows[0]["operation_review"] == "unknown"
    else:
        assert [r["operation_review"] for r in rows] == ["alert" if p else "clear" for p in profile["effects"]]


def test_past_snapshot_and_operation_time_answer_different_questions():
    def rows(name):
        p = PROFILES[name]
        return replay.score_case(execute_operation_case(STAGE, "ticket", p), p.get("transport"))[0]

    first, second = rows("one_use_repeated")
    assert (first["final_snapshot"], first["operation_review"], second["operation_review"]) == ("alert", "clear", "alert")
    assert first["receipt_seq"] < second["receipt_seq"]
    delayed, = rows("delayed_revocation")
    assert (delayed["operation_at_use"], delayed["operation_review"]) == ("unknown", "alert")
    assert delayed["first_confirmation"] == delayed["step"] + 1
    direct, = rows("independent_same_bytes")
    assert direct["version"] == direct["input_version"] and direct["operation_review"] == "clear"
    other_version, = rows("different_version")
    assert other_version["version"] != other_version["input_version"] and other_version["operation_review"] == "clear"


def test_one_use_check_and_consumption_share_a_write_lock_and_rollback(tmp_path):
    file = tmp_path / "authority.db"
    version = Version("source", "a" * 64)
    with closing(sqlite3.connect(file)) as db, closing(sqlite3.connect(file, timeout=0)) as rival:
        store = PolicyStore(db, "issuer", "ticket")
        store.change(0, "once", "worker", version)
        with pytest.raises(RuntimeError, match="failed write"), store.operation():
            store.consume(1, "worker", version, "session", "failed", "delivery")
            raise RuntimeError("failed write")
        assert store.permission("worker", version) == "once" and len(store.journal()) == 1
        with store.operation():
            assert store.permission("worker", version) == "once"
            with pytest.raises(sqlite3.OperationalError, match="locked"):
                rival.execute("BEGIN IMMEDIATE")
            store.consume(2, "worker", version, "session", "first", "delivery")
        with rival:
            rival.execute("BEGIN IMMEDIATE")
            assert rival.execute("SELECT count(*) FROM grants").fetchone() == (0,)
            assert rival.execute("SELECT count(*) FROM ledger").fetchone() == (2,)


@pytest.mark.parametrize("failure", ["authority_write", "output_storage"])
def test_failed_publication_leaves_the_editor_and_the_single_use_grant_retryable(failure, monkeypatch):
    with closing(sqlite3.connect(":memory:")) as db:
        office = _OperationOffice(STAGE, "fault-test", "named", db)
        office.run(["once", "send"])
        if failure == "output_storage":
            db.execute("CREATE TRIGGER fail_edit BEFORE INSERT ON edits BEGIN SELECT RAISE(ABORT,'disk fault'); END")
        with monkeypatch.context() as changes:
            if failure == "authority_write":
                def unavailable(*args):
                    raise sqlite3.OperationalError("disk fault")
                changes.setattr(office.store, "consume", unavailable)
            with pytest.raises(sqlite3.DatabaseError, match="disk fault"):
                office._edit("use")
        assert not office.witnesses and not office.submissions
        assert not any(isinstance(receipt, Commit) for receipt in office.receipts)
        assert not any(e.tool == "write" and e.agent == office.worker for e in office._recorder.events)
        assert db.execute("SELECT count(*) FROM edits").fetchone() == (0,)
        assert not any(e["kind"] == "use" for _, e in office.store.journal())
        assert office.store.permission(office.worker, office.current) == "once"
        db.execute("DROP TRIGGER IF EXISTS fail_edit")
        office._edit("use")
        content, = db.execute("SELECT content FROM edits").fetchone()
        assert content.endswith(STAGE.text.encode()) and len(office.submissions) == 1
        assert office.store.permission(office.worker, office.current) is None


def test_archived_results_have_one_primary_per_ticket_and_distinct_call_witnesses():
    assert digest((STUDY / "protocol.json").read_bytes()) == replay.PROTOCOL_SHA256
    dest = STUDY / "results"
    summary = json.loads((dest / "summary.json").read_bytes())
    with gzip.open(dest / "cases.csv.gz", "rt", encoding="utf-8", newline="") as stream:
        cases = list(csv.DictReader(stream))
    primary = [r for r in cases if r["primary"] == "True"]
    assert len(cases) == 1044 and len(primary) == len({r["base_id"] for r in primary}) == 58
    assert len({r["template_group"] for r in primary}) == 43
    assert replay._counts(primary) == summary["primary_methods"]
    with gzip.open(dest / "operations.csv.gz", "rt", encoding="utf-8", newline="") as stream:
        ops = list(csv.DictReader(stream))
    assert len(ops) == len({(r["base_id"], r["profile"], r["session"], r["call_id"]) for r in ops}) == 1160
    writes = [r | {"operation": r["operation_review"]} for r in ops if r["primary"] == "True"]
    assert len(writes) == 64 and replay._counts(writes) == summary["primary_write_methods"]
    assert summary["primary_write_methods"]["final_snapshot"]["false_positives"] == 16
    assert summary["primary_write_methods"]["operation"]["false_positives"] == 0
    positive = [r for r in ops if r["policy_effect"] == "yes" and r["primary"] == "True"]
    times = Counter("unconfirmed" if not r["first_confirmation"] else
                    "at_use" if r["step"] == r["first_confirmation"] else "after_use" for r in positive)
    assert times == summary["primary_confirmation_timing"] == {"at_use": 17, "after_use": 3, "unconfirmed": 6}
    with (dest / "motive-pairs.csv").open(encoding="utf-8", newline="") as stream:
        pairs = list(csv.DictReader(stream))
    assert len(pairs) == 58 and all(r["clerical_misroute"] == r["coordinated_misroute"] for r in pairs)


def test_cli_forwards_input_output_and_explicit_fetch(tmp_path, monkeypatch):
    calls = []
    def record(*paths, fetch):
        calls.append((paths, fetch))
    monkeypatch.setattr(replay, "run_operation_authority", record)
    cmd = ["operation-authority", "--study", "spec", "--dispatch-study", "prior", "--source-dir", "input",
           "--out", str(tmp_path)]
    cli.main(cmd)
    cli.main([*cmd, "--fetch"])
    assert calls == [((Path("spec"), Path("prior"), Path("input"), tmp_path), flag) for flag in (False, True)]
