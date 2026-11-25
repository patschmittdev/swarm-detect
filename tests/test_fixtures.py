import json
from dataclasses import asdict, replace
from importlib.resources import files
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from swarmtrace.trace.io import RunPaths, read_labels, read_manifest, read_trace
from swarmtrace.trace.schema import (
    STATUSES,
    TOOLS,
    TraceEvent,
    TraceSchemaError,
    validate_event,
    validate_trace,
)
from swarmtrace.trace.tiers import Tier

FIXTURE_NAMES = (
    "all_benign", "messaging_pair", "shared_file_trio", "benign_team", "denials", "credential_relay",
)


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_fixture_contract(fixtures_dir: Path, name: str) -> None:
    paths = RunPaths(fixtures_dir / name)
    trace, labels, manifest = read_trace(paths.trace), read_labels(paths.labels), read_manifest(
        paths.manifest
    )
    assert trace.run_id == labels.run_id == manifest.run_id
    assert set(trace.agents) == set(labels.agents)
    validate_trace(trace.events)
    schema = json.loads(
        files("swarmtrace.trace").joinpath("schema/trace-event.v1.json").read_text(encoding="utf-8")
    )
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    for line in paths.trace.read_bytes().splitlines():
        record = json.loads(line)
        validator.validate(record)
        assert line == json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8")
    for path in (paths.trace, paths.labels, paths.manifest):
        data = path.read_bytes()
        assert b"\r" not in data
        assert data.endswith(b"\n")
    for path in (paths.labels, paths.manifest):
        data = path.read_bytes()
        assert data == (
            json.dumps(json.loads(data), sort_keys=True, separators=(",", ":")) + "\n"
        ).encode("utf-8")


def test_fixture_scenarios(fixtures_dir: Path) -> None:
    runs = {name: read_trace(fixtures_dir / name / "trace.jsonl") for name in FIXTURE_NAMES}
    labels = {name: read_labels(fixtures_dir / name / "labels.json") for name in FIXTURE_NAMES}
    expected = {
        "all_benign": (4, 0, 0), "messaging_pair": (3, 0, 2),
        "shared_file_trio": (2, 0, 3), "benign_team": (3, 2, 0),
    }
    for name, counts in expected.items():
        roles = [label.role for label in labels[name].agents.values()]
        assert tuple(roles.count(role) for role in ("benign_solo", "benign_team", "offensive")) == counts
    assert 18 <= len(runs["all_benign"].events) <= 22
    for name, role in [("messaging_pair", "offensive"), ("benign_team", "benign_team")]:
        coordinated = {a for a, label in labels[name].agents.items() if label.role == role}
        assert {e.tool for e in runs[name].events if e.agent in coordinated} >= {"send", "recv"}
        groups = {labels[name].agents[a].group for a in coordinated}
        assert len(groups) == 1 and None not in groups
    trio = runs["shared_file_trio"].events
    assert not {"send", "recv"} & {e.tool for e in trio}
    assert any(e.provenance is not None for e in trio)
    assert {e.target for e in trio if e.tool == "write"} & {
        e.target for e in trio if e.tool == "read"
    }
    assert {e.result["status"] for e in runs["denials"].events} >= {"denied", "not_found", "error"}
    assert any(e.tool == "recv" and e.content == "" for e in runs["messaging_pair"].events)


@pytest.mark.parametrize("name", FIXTURE_NAMES)
@pytest.mark.parametrize("tier", [Tier.V0, Tier.V1])
def test_fixture_projection_validates_at_its_tier(
    fixtures_dir: Path, name: str, tier: Tier
) -> None:
    trace = read_trace(fixtures_dir / name / "trace.jsonl", tier=tier)
    validate_trace(trace.events, tier=tier)
    for event in trace.events:
        validate_event(event, tier=tier)
    has_stripped_fields = False
    for event in trace.events:
        stripped_content = event.result["status"] == "ok" and event.tool in (
            "read", "write", "send", "recv"
        )
        stripped_args = tier is Tier.V0 and event.tool in ("login", "list", "write", "send", "recv")
        if stripped_content or stripped_args:
            has_stripped_fields = True
            with pytest.raises(TraceSchemaError, match="args|content"):
                validate_event(event, tier=Tier.V2)
        else:
            validate_event(event, tier=Tier.V2)
    if has_stripped_fields:
        with pytest.raises(TraceSchemaError, match="args|content"):
            validate_trace(trace.events, tier=Tier.V2)
    else:
        validate_trace(trace.events, tier=Tier.V2)


@pytest.mark.parametrize("tool", TOOLS)
@pytest.mark.parametrize("status", STATUSES)
@pytest.mark.parametrize("content", [None, "", "text", 1])
def test_json_schema_enforces_v2_content(
    event: TraceEvent, tool: str, status: str, content: object
) -> None:
    target = "h-12345678"
    args = {}
    if tool == "login":
        args = {"credential": "c-12345678"}
    elif tool == "list":
        args = {"prefix": ""}
    elif tool in ("read", "write"):
        target = "f-12345678"
    elif tool in ("send", "recv"):
        target = "a-87654321"
    if tool in ("write", "send", "recv"):
        args = {"size": 0, "digest": "e3b0c44298fc1c14"}
    candidate = replace(
        event, tool=tool, target=target, args=args, content=content,
        result={"status": status, "size": 0},
    )
    schema = json.loads(
        files("swarmtrace.trace").joinpath("schema/trace-event.v1.json").read_text(encoding="utf-8")
    )
    errors = list(Draft202012Validator(schema).iter_errors(asdict(candidate)))
    needs_content = status == "ok" and tool in ("read", "write", "send", "recv")
    valid = isinstance(content, str) if needs_content else content is None
    assert (not errors) == valid


@pytest.mark.parametrize(
    ("field", "value"),
    [("schema_version", 2), ("run_id", "bad"), ("run_id", "0123456789abcdef\n"),
     ("agent", "bad"), ("agent", "a-12345678\n"), ("target", "h-12345678\n"),
     ("seq", -1), ("tick", 1.5), ("tool", "bad"), ("target", "bad"),
     ("args", {"extra": 1}), ("result", {"status": "bad", "size": 0}),
     ("content", "not on scan"), ("provenance", -1)],
)
def test_json_schema_rejects_invalid_fields(
    fixtures_dir: Path, field: str, value: object
) -> None:
    record = json.loads((fixtures_dir / "all_benign" / "trace.jsonl").read_bytes().splitlines()[0])
    schema = json.loads(
        files("swarmtrace.trace").joinpath("schema/trace-event.v1.json").read_text(encoding="utf-8")
    )
    assert list(Draft202012Validator(schema).iter_errors({**record, field: value}))
