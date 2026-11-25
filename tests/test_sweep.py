from pathlib import Path

import pytest

from swarmtrace.cli import main
from swarmtrace.sim.sweep import condition_grid, run_sweep
from swarmtrace.trace.io import RunPaths, read_manifest, read_trace


def test_default_grid_matches_spec_exactly() -> None:
    grid = condition_grid()
    assert len(grid) == len(set(grid)) == 72
    assert {c.offensive_group_size for c in grid} == {0, 2, 3, 5}
    assert {c.coordinated_groups for c in grid} == {1, 2, 3}
    assert {c.benign_credential_sharing for c in grid} == {10}
    assert {c.channel for c in grid} == {"message", "shared_file", "preplanned"}
    assert {c.topology for c in grid} == {"hub", "peer"}


def test_small_sweep_is_complete_and_reproducible(tmp_path: Path) -> None:
    grid = condition_grid(group_sizes=(0, 2), coordinated_groups=(1,), channels=("message",),
                          topologies=("peer",), n_ticks=12)
    runs = run_sweep(tmp_path / "first", 6, runs_per_condition=2, conditions=grid)
    copies = run_sweep(tmp_path / "again", 6, runs_per_condition=2, conditions=grid)
    assert len(runs) == len(set(runs)) == 4
    seeds = set()
    for run, copy in zip(runs, copies, strict=True):
        paths, other = RunPaths(run), RunPaths(copy)
        assert read_trace(paths.trace).events
        seeds.add(read_manifest(paths.manifest).seed)
        for name in ("trace", "labels", "manifest"):
            assert getattr(paths, name).read_bytes() == getattr(other, name).read_bytes()
    assert len(seeds) == 4


def test_cli_sweep_and_existing_synthetic_remain_available(tmp_path: Path) -> None:
    main(["sweep", "--out", str(tmp_path / "sweep"), "--seed", "5", "--ticks", "12",
          "--group-sizes", "0", "2", "--coordinated-groups", "1", "--channels", "shared_file",
          "--topologies", "hub", "--runs-per-condition", "1",
          "--benign-credential-sharing", "37"])
    traces = list((tmp_path / "sweep").glob("*/trace.jsonl"))
    assert len(traces) == 2
    assert all(read_trace(path).events for path in traces)
    assert all(read_manifest(path.parent / "manifest.json").condition[
        "benign_credential_sharing"] == 37 for path in traces)
    main(["synthetic", "--out", str(tmp_path / "synthetic"), "--runs", "1",
          "--seed", "5", "--signal", "0"])
    assert len(list((tmp_path / "synthetic").glob("*/trace.jsonl"))) == 1


def test_cli_invalid_sweep_exits_without_writing(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as error:
        main(["sweep", "--out", str(tmp_path / "bad"), "--seed", "5", "--ticks", "0"])
    assert error.value.code == 2
    assert not (tmp_path / "bad").exists()
