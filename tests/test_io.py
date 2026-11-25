import json
from dataclasses import FrozenInstanceError, asdict, replace
from pathlib import Path

import pytest

from swarmtrace.trace.io import (
    AgentLabel,
    Labels,
    Manifest,
    RunPaths,
    read_labels,
    read_manifest,
    read_trace,
    write_labels,
    write_manifest,
    write_trace,
)
from swarmtrace.trace.schema import TraceEvent, TraceSchemaError, validate_trace
from swarmtrace.trace.tiers import Tier, project


def canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def test_trace_round_trip(event: TraceEvent, tmp_path: Path) -> None:
    events = (event, replace(event, seq=1, agent="a-00000000"))
    first, second = tmp_path / "one.jsonl", tmp_path / "two.jsonl"
    write_trace(first, iter(events))
    write_trace(second, events)
    assert first.read_bytes() == second.read_bytes() == b"".join(map(canonical, map(asdict, events)))
    assert b"\r" not in first.read_bytes()
    trace = read_trace(first)
    assert trace.events == events
    assert trace.run_id == event.run_id
    assert trace.tier is Tier.V2
    assert trace.agents == ("a-00000000", "a-12345678")
    assert isinstance(trace.events, tuple)
    with pytest.raises(FrozenInstanceError):
        trace.run_id = "fedcba9876543210"


def test_unicode_content_round_trip(event: TraceEvent, tmp_path: Path) -> None:
    full = replace(event, tool="read", target="f-12345678", content="caf\u00e9\nline")
    path = tmp_path / "trace.jsonl"
    write_trace(path, [full])
    assert read_trace(path).events == (full,)
    assert b"\r" not in path.read_bytes()


@pytest.mark.parametrize("tier", list(Tier))
def test_read_validates_before_projecting(
    event: TraceEvent, tmp_path: Path, tier: Tier
) -> None:
    path = tmp_path / "trace.jsonl"
    full = replace(
        event, tool="send", target="a-87654321", content="text",
        args={"size": 4, "digest": "0123456789abcdef"}, result={"status": "ok", "size": 4},
    )
    write_trace(path, [full])
    assert read_trace(path, tier).events == (project(full, tier),)
    assert read_trace(path, tier).tier is tier
    validate_trace(read_trace(path, tier).events, tier=tier)
    path.write_bytes(canonical({**asdict(full), "args": {}}))
    with pytest.raises(TraceSchemaError, match="args"):
        read_trace(path, tier)


@pytest.mark.parametrize("tier", list(Tier))
def test_read_rejects_stripped_content_before_projection(
    event: TraceEvent, tmp_path: Path, tier: Tier
) -> None:
    stripped = replace(event, tool="read", target="f-12345678", content=None)
    path = tmp_path / "trace.jsonl"
    path.write_bytes(canonical(asdict(stripped)))
    with pytest.raises(TraceSchemaError, match="content"):
        read_trace(path, tier=tier)


@pytest.mark.parametrize("tier", [Tier.V0, Tier.V1])
def test_write_rejects_projected_records(
    event: TraceEvent, tmp_path: Path, tier: Tier
) -> None:
    full = replace(event, tool="read", target="f-12345678", content="text")
    path = tmp_path / "trace.jsonl"
    write_trace(path, [full])
    original = path.read_bytes()
    with pytest.raises(TraceSchemaError, match="content"):
        write_trace(path, [project(full, tier)])
    assert path.read_bytes() == original


def test_write_validates_before_truncating(event: TraceEvent, tmp_path: Path) -> None:
    path = tmp_path / "trace.jsonl"
    path.write_bytes(b"keep")
    with pytest.raises(TraceSchemaError, match="tool"):
        write_trace(path, [replace(event, tool="unknown")])
    assert path.read_bytes() == b"keep"


@pytest.mark.parametrize("field", ["run_id", "content", "result"])
def test_missing_record_fields(event: TraceEvent, tmp_path: Path, field: str) -> None:
    record = asdict(event)
    del record[field]
    path = tmp_path / "trace.jsonl"
    path.write_bytes(canonical(record))
    with pytest.raises(TraceSchemaError, match=field):
        read_trace(path)


def test_extra_record_field(event: TraceEvent, tmp_path: Path) -> None:
    path = tmp_path / "trace.jsonl"
    path.write_bytes(canonical({**asdict(event), "extra": "hidden"}))
    with pytest.raises(TraceSchemaError, match="extra"):
        read_trace(path)


def test_label_and_manifest_round_trips(tmp_path: Path) -> None:
    labels = Labels(
        run_id="0123456789abcdef",
        agents={"a-12345678": AgentLabel(role="offensive", group="group-1")},
        objective_completed=True, objective_tick=7,
    )
    manifest = Manifest(
        run_id=labels.run_id, seed=42, condition={"signal": 100, "channel": "synthetic"},
        code_version="0.1.0",
    )
    for value, writer, reader, name in [
        (labels, write_labels, read_labels, "labels.json"),
        (manifest, write_manifest, read_manifest, "manifest.json"),
    ]:
        first, second = tmp_path / name, tmp_path / ("copy-" + name)
        writer(first, value)
        writer(second, value)
        assert reader(first) == value
        assert first.read_bytes() == second.read_bytes() == canonical(asdict(value))
        assert b"\r" not in first.read_bytes()
    negative = replace(labels, objective_completed=False, objective_tick=None)
    write_labels(tmp_path / "negative.json", negative)
    assert read_labels(tmp_path / "negative.json") == negative


def test_run_paths(tmp_path: Path) -> None:
    paths = RunPaths(tmp_path)
    assert paths.trace == tmp_path / "trace.jsonl"
    assert paths.labels == tmp_path / "labels.json"
    assert paths.manifest == tmp_path / "manifest.json"
