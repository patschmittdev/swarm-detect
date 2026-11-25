import socket
import subprocess
import sys
from collections import deque
from pathlib import Path
from statistics import mean

import pytest

from swarmtrace.trace.io import RunPaths, read_labels, read_manifest, read_trace
from swarmtrace.trace.schema import TraceEvent, validate_trace
from swarmtrace.trace.synthetic import generate_synthetic_runs


def same_target_rates(events: tuple[TraceEvent, ...]) -> dict[str, float]:
    recent = deque()
    matches: dict[str, list[bool]] = {}
    for event in events:
        while recent and recent[0].tick < event.tick - 3:
            recent.popleft()
        matches.setdefault(event.agent, []).append(
            any(previous.agent != event.agent and previous.target == event.target for previous in recent)
        )
        recent.append(event)
    return {agent: mean(values) for agent, values in matches.items()}


def snapshot(root: Path) -> dict[str, bytes]:
    return {str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()}


def test_synthetic_determinism_and_validity(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def no_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("synthetic generation must not open sockets")

    monkeypatch.setattr(socket, "socket", no_network)
    first, second = tmp_path / "first", tmp_path / "second"
    paths = generate_synthetic_runs(first, 12, 42, signal=65)
    assert generate_synthetic_runs(second, 12, 42, signal=65)
    assert snapshot(first) == snapshot(second)
    assert len(paths) == 12
    for directory in paths:
        paths_for_run = RunPaths(directory)
        trace = read_trace(paths_for_run.trace)
        labels = read_labels(paths_for_run.labels)
        manifest = read_manifest(paths_for_run.manifest)
        validate_trace(trace.events)
        content_events = [e for e in trace.events if e.tool in ("read", "write", "send", "recv")]
        assert content_events
        for event in trace.events:
            if event.result["status"] == "ok" and event.tool in ("read", "write", "send", "recv"):
                assert isinstance(event.content, str)
            else:
                assert event.content is None
        assert trace.run_id == labels.run_id == manifest.run_id
        assert set(trace.agents) == set(labels.agents)
        assert 12 <= len(trace.agents) <= 28
        offensive = [a for a, label in labels.agents.items() if label.role == "offensive"]
        assert not offensive or 2 <= len(offensive) <= 8
        for agent, label in labels.agents.items():
            assert label.role in ("offensive", "benign_solo")
            assert (label.group is not None) == (agent in offensive)
        for path in (paths_for_run.trace, paths_for_run.labels, paths_for_run.manifest):
            assert b"\r" not in path.read_bytes()


def test_agent_count_is_independent_of_label_over_400_runs(tmp_path: Path) -> None:
    counts: dict[bool, list[int]] = {False: [], True: []}
    for directory in generate_synthetic_runs(tmp_path, 400, 2026, signal=0):
        trace = read_trace(directory / "trace.jsonl")
        labels = read_labels(directory / "labels.json")
        positive = any(label.role == "offensive" for label in labels.agents.values())
        counts[positive].append(len(trace.agents))
    assert min(map(len, counts.values())) >= 150
    assert abs(mean(counts[True]) - mean(counts[False])) < 1.5
    assert set(counts[True] + counts[False]) == set(range(12, 29))


def test_zero_signal_actions_do_not_depend_on_labels(tmp_path: Path) -> None:
    negative = generate_synthetic_runs(tmp_path / "negative", 20, 91, 0, positive_percent=0)
    positive = generate_synthetic_runs(tmp_path / "positive", 20, 91, 0, positive_percent=100)
    for left, right in zip(negative, positive, strict=True):
        assert (left / "trace.jsonl").read_bytes() == (right / "trace.jsonl").read_bytes()
        assert all(label.role == "benign_solo" for label in read_labels(left / "labels.json").agents.values())
        assert any(label.role == "offensive" for label in read_labels(right / "labels.json").agents.values())


@pytest.mark.parametrize("signal", [0, 50, 100])
def test_planted_same_target_signal(tmp_path: Path, signal: int) -> None:
    offensive, benign = [], []
    for directory in generate_synthetic_runs(tmp_path, 60, 123, signal, positive_percent=100):
        trace = read_trace(directory / "trace.jsonl")
        labels = read_labels(directory / "labels.json")
        rates = same_target_rates(trace.events)
        for agent, rate in rates.items():
            (offensive if labels.agents[agent].role == "offensive" else benign).append(rate)
    difference = mean(offensive) - mean(benign)
    if signal == 0:
        assert abs(difference) < 0.05
    elif signal == 50:
        assert 0.20 < difference < 0.65
    else:
        assert difference > 0.65
        assert mean(offensive) > 0.85


@pytest.mark.parametrize(
    "kwargs",
    [{"signal": -1}, {"signal": 101}, {"signal": 1.5}, {"signal": True},
     {"positive_percent": -1}, {"positive_percent": 101}, {"positive_percent": 0.5},
     {"n_runs": -1}, {"n_runs": 1.5}, {"seed": -1}],
)
def test_invalid_generator_arguments(tmp_path: Path, kwargs: dict[str, object]) -> None:
    arguments = {"out_dir": tmp_path, "n_runs": 1, "seed": 1, "signal": 50, **kwargs}
    with pytest.raises(ValueError):
        generate_synthetic_runs(**arguments)


def test_zero_runs(tmp_path: Path) -> None:
    assert generate_synthetic_runs(tmp_path, 0, 1, 0) == []


def test_synthetic_cli(tmp_path: Path) -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "swarmtrace.cli", "synthetic", "--out", str(tmp_path),
         "--runs", "2", "--seed", "9", "--signal", "100"],
        capture_output=True, text=True, check=False,
    )
    assert completed.returncode == 0, completed.stderr
    traces = list(tmp_path.glob("*/trace.jsonl"))
    assert len(traces) == 2
    for path in traces:
        read_trace(path)
