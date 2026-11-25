import json
from pathlib import Path

import pytest

from swarmtrace.pilot import batch as pb
from swarmtrace.pilot.__main__ import main

ROWS = [
    {"run": "dev-01", "condition": "swarm_native", "seed": 467751098, "background": False,
     "launchers": ["claude"], "models": ["sonnet"], "tasks": ["summaries"], "subagents": 4},
    {"run": "dev-02", "condition": "swarm_peers", "seed": 4262417203, "background": False,
     "launchers": ["claude", "codex", "claude"], "models": ["sonnet", "m2", "sonnet"],
     "tasks": ["cross-refs"]},
    {"run": "dev-03", "condition": "lookalike", "seed": 5, "background": True,
     "mix": ["crawler", "retry_storm"]},
]


@pytest.fixture
def protocol(tmp_path):
    path = tmp_path / "protocol.json"
    path.write_text(json.dumps({"development_runs": ROWS, "test_runs": ROWS[:1]}))
    return path


def quiet(line):
    pass


def test_row_config_matches_protocol_shape():
    peers = pb.row_config(ROWS[1], Path("x"))
    assert peers.agents == 3 and peers.launchers == ["claude", "codex", "claude"]
    assert peers.tasks == ["cross-refs"] and peers.timeout == 900.0
    assert pb.row_config(ROWS[0], Path("x")).subagents == 4
    look = pb.row_config(ROWS[2], Path("x"))
    assert look.mix == ["crawler", "retry_storm"] and look.duration == 150.0 and look.background


def test_batch_runs_and_skips(tmp_path, protocol):
    runs = tmp_path / "runs"
    lines = []
    results = pb.batch(protocol, "development", runs, parallel=2, only=["dev-01", "dev-02"],
                       dry_run=True, duration=1.0, echo=lines.append)
    assert sorted(r["run"] for r in results) == ["dev-01", "dev-02"]
    assert all(not r["skipped"] and r["timeout_hit"] is False for r in results)
    assert lines[0] == "parallel: 2" and len(lines) == 3
    assert all(line.endswith("ok") for line in lines[1:])
    for run_id in ("dev-01", "dev-02"):
        manifest = json.loads((runs / run_id / "manifest.json").read_text())
        assert manifest["batch_parallel"] == 2 and manifest["runner_versions"] == {"fake": "0"}
    again = pb.batch(protocol, "development", runs, only=["dev-01"], dry_run=True, echo=quiet)
    assert again == [{"run": "dev-01", "condition": "swarm_native", "skipped": True}]
    with pytest.raises(ValueError):
        pb.batch(protocol, "development", runs, only=["nope"], dry_run=True, echo=quiet)


def test_batch_cli_lookalike(tmp_path, protocol):
    assert main(["batch", "--protocol", str(protocol), "--set", "development", "--out",
                 str(tmp_path / "r"), "--only", "dev-03", "--dry-run"]) == 0
    labels = json.loads((tmp_path / "r" / "dev-03" / "labels.json").read_text())
    assert labels["condition"] == "lookalike" and labels["positive"] is False


def test_batch_refuses_incomplete_directory(tmp_path, protocol):
    runs = tmp_path / "runs"
    (runs / "dev-01").mkdir(parents=True)
    with pytest.raises(RuntimeError, match="dev-01"):
        pb.batch(protocol, "development", runs, only=["dev-01"], dry_run=True, echo=quiet)
    done = tmp_path / "done"
    pb.batch(protocol, "test", done, dry_run=True, echo=quiet)
    (done / "dev-01" / "FAILED.txt").write_text("DrainTimeout\n")
    with pytest.raises(RuntimeError, match="dev-01"):
        pb.batch(protocol, "test", done, dry_run=True, echo=quiet)
