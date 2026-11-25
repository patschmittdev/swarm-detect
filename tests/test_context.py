import json
import re
from dataclasses import replace
from pathlib import Path

import pytest

from swarmtrace.agents.coordinated import CoordinatedAgent
from swarmtrace.eval.harness import child_seed
from swarmtrace.sim import runner
from swarmtrace.sim.engine import Engine, Intervention, quarantine
from swarmtrace.sim.recorder import write_run_extras
from swarmtrace.sim.runner import CHANNELS, TOPOLOGIES, Condition, RunSetup, build_run, run_one
from swarmtrace.trace.context import (
    Context,
    ContextLevel,
    HandoffScope,
    project_context,
    read_context,
    write_context,
)
from swarmtrace.trace.io import RunPaths, read_labels
from swarmtrace.trace.schema import SCHEMA_VERSION, TraceEvent

SEED = child_seed(20261120, 195, 2000)
ROLE_WORDS = re.compile(r"benign|offensive|attack|objective|secret|exfil|control", re.I)


def _canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
            + "\n").encode("utf-8")


def _read_json(path: Path) -> dict:
    raw = path.read_bytes()
    record = json.loads(raw)
    assert raw == _canonical(record)
    assert raw.endswith(b"\n") and b"\r" not in raw

    def no_floats(value: object) -> None:
        assert not isinstance(value, float)
        if isinstance(value, dict):
            for item in value.values():
                no_floats(item)
        elif isinstance(value, list):
            for item in value:
                no_floats(item)

    no_floats(record)
    return record


@pytest.fixture
def context() -> Context:
    return Context("0123456789abcdef", ContextLevel.C2,
                   {"c-00000002": "a-00000002", "c-00000001": "a-00000001"}, (
                       HandoffScope("a-00000001", "a-00000002", "h-00000001",
                                    ("f-00000002", "f-00000001")),
                       HandoffScope("a-00000002", "a-00000001", "h-00000002",
                                    ("f-00000003",)),
                   ))


def test_context_serialization_and_round_trip(tmp_path: Path, context: Context) -> None:
    path = tmp_path / "context.json"
    write_context(path, context)
    record = _read_json(path)
    assert record == {
        "schema_version": SCHEMA_VERSION, "run_id": context.run_id,
        "credentials": dict(context.credentials),
        "handoffs": [
            {"sender": "a-00000002", "receiver": "a-00000001", "host": "h-00000002",
             "files": ["f-00000003"]},
            {"sender": "a-00000001", "receiver": "a-00000002", "host": "h-00000001",
             "files": ["f-00000001", "f-00000002"]},
        ],
    }
    loaded = read_context(path)
    assert loaded.level is ContextLevel.C2
    assert loaded.run_id == context.run_id and loaded.credentials == context.credentials
    assert isinstance(loaded.handoffs, tuple)
    assert all(isinstance(handoff.files, tuple) for handoff in loaded.handoffs)
    second = tmp_path / "copy.json"
    write_context(second, loaded)
    assert second.read_bytes() == path.read_bytes()


@pytest.mark.parametrize("level", list(ContextLevel))
def test_context_projection(tmp_path: Path, context: Context, level: ContextLevel) -> None:
    path = tmp_path / "context.json"
    write_context(path, context)
    full = read_context(path)
    projected = project_context(full, level)
    assert projected == read_context(path, level)
    assert projected.run_id == full.run_id and projected.level is level
    assert projected.credentials == ({} if level is ContextLevel.C0 else full.credentials)
    assert projected.handoffs == (full.handoffs if level is ContextLevel.C2 else ())
    assert full.credentials and full.handoffs
    assert Context.empty(full.run_id) == project_context(full, ContextLevel.C0)
    if level is not ContextLevel.C2:
        with pytest.raises(ValueError, match="C2"):
            write_context(path, projected)
        assert read_context(path) == full


@pytest.mark.parametrize("level", (ContextLevel.C1, ContextLevel.C2))
def test_missing_context_raises(tmp_path: Path, level: ContextLevel) -> None:
    with pytest.raises(FileNotFoundError):
        read_context(tmp_path / "context.json", level)


def test_missing_context_at_c0_has_no_known_run_id(tmp_path: Path) -> None:
    assert read_context(tmp_path / "context.json", ContextLevel.C0) == Context.empty("")


@pytest.mark.parametrize("field,value", [
    ("schema_version", 1.0), ("schema_version", True), ("schema_version", 2),
    ("credentials", {"c-00000001": 0.5}), ("handoffs", [{"files": [0.5]}]),
    ("unexpected", "value"),
])
def test_context_reader_rejects_invalid_records_before_projection(
    tmp_path: Path, context: Context, field: str, value: object,
) -> None:
    path = tmp_path / "context.json"
    write_context(path, context)
    record = json.loads(path.read_bytes())
    record[field] = value
    path.write_bytes(_canonical(record))
    with pytest.raises(ValueError):
        read_context(path, ContextLevel.C0)


def test_context_writer_rejects_floats_before_truncating(tmp_path: Path, context: Context) -> None:
    path = tmp_path / "context.json"
    path.write_bytes(b"keep")
    with pytest.raises(ValueError):
        write_context(path, replace(context, credentials={"c-00000001": 0.5}))
    assert path.read_bytes() == b"keep"


def _assert_context(paths: RunPaths, setup: RunSetup) -> None:
    record = _read_json(paths.context)
    assert set(record) == {"schema_version", "run_id", "credentials", "handoffs"}
    assert record["schema_version"] == SCHEMA_VERSION
    assert record["run_id"] == read_labels(paths.labels).run_id
    assert not ROLE_WORDS.search(paths.context.read_text(encoding="utf-8"))
    assert record["credentials"] == {
        credential: agent for agent, permission in setup.world.permissions.items()
        for credential in permission.credentials
    }
    expected = sorted((
        {"sender": part.owner, "receiver": part.worker, "host": part.host,
         "files": sorted(setup.scopes[part.source])}
        for parts in setup.tasks.values() for part in parts
    ), key=lambda handoff: (handoff["receiver"], handoff["sender"]))
    assert record["handoffs"] == expected
    assert len(expected) == sum(len(group.members) for group in setup.groups)
    assert {path.name for path in paths.run_dir.iterdir()} == {
        "trace.jsonl", "labels.json", "manifest.json", "context.json", "outcomes.json",
    }
    if not setup.offensive:
        reserved = {part.source for part in setup.objective.parts}
        assert reserved.isdisjoint(file for row in expected for file in row["files"])


@pytest.mark.parametrize("channel", CHANNELS)
@pytest.mark.parametrize("topology", TOPOLOGIES)
def test_context_schema_and_invariants_7_and_8(
    tmp_path: Path, channel: str, topology: str,
) -> None:
    # Reuse the same controls for both invariants to bound added simulation time.
    control_condition = Condition(channel, topology, 0, 2, scope="on",
                                  benign_credential_sharing=100)
    control = build_run(control_condition, SEED)
    size = len(control.groups[control.focal_group].members)
    conditions = {
        "sharing": control_condition,
        "delegation": replace(control_condition, benign_credential_sharing=0),
        "violation_sharing": replace(control_condition, offensive_group_size=size,
                                     violation_size=5),
        "violation_delegation": replace(control_condition, offensive_group_size=size,
                                        violation_size=5, benign_credential_sharing=0),
        "relay": replace(control_condition, offensive_group_size=size),
    }
    runs = {}
    for name, condition in conditions.items():
        paths = RunPaths(run_one(condition, SEED, tmp_path / name))
        _assert_context(paths, control)
        runs[name] = paths
    assert len({paths.context.read_bytes() for paths in runs.values()}) == 1
    for sharing in ("sharing", "delegation"):
        assert runs[sharing].trace.read_bytes() != runs[f"violation_{sharing}"].trace.read_bytes()
    assert runs["sharing"].trace.read_bytes() != runs["delegation"].trace.read_bytes()
    assert runs["sharing"].trace.read_bytes() == runs["relay"].trace.read_bytes()
    assert runs["sharing"].labels.read_bytes() != runs["relay"].labels.read_bytes()
    if (channel, topology) == ("shared_file", "hub"):
        small = RunPaths(run_one(replace(conditions["relay"], violation_size=1), SEED,
                                 tmp_path / "one-read"))
        assert small.context.read_bytes() == runs["sharing"].context.read_bytes()
        assert small.trace.read_bytes() != runs["sharing"].trace.read_bytes()


def _capture_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, blocked: bool = False,
) -> tuple[RunPaths, RunSetup]:
    condition = Condition("shared_file", "hub", 5, 2, scope="on", violation_size=5)
    setup = build_run(condition, SEED)
    monkeypatch.setattr(runner, "build_run", lambda condition, seed: setup)
    if blocked:
        requirement = setup.violation
        assert requirement is not None

        def monitor(event: TraceEvent) -> Intervention | None:
            if (event.agent == requirement.worker and event.tool == "read"
                    and event.target == requirement.files[-2] and event.result["status"] == "ok"):
                return quarantine(requirement.worker)
            return None

        def monitored_engine(*args: object, **kwargs: object) -> Engine:
            return Engine(*args, **kwargs, monitor=monitor)

        monkeypatch.setattr(runner, "Engine", monitored_engine)
    return RunPaths(run_one(condition, SEED, tmp_path)), setup


def _adjacent(setup: RunSetup) -> set[str]:
    return {file for policy in setup.agents.values() if isinstance(policy, CoordinatedAgent)
            for file in policy.plan.delegated_workspace.adjacent}


@pytest.mark.parametrize("blocked", (False, True))
def test_outcomes_use_final_world_and_collector_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, blocked: bool,
) -> None:
    paths, setup = _capture_run(tmp_path, monkeypatch, blocked=blocked)
    record = _read_json(paths.outcomes)
    requirement = setup.violation
    assert requirement is not None
    assert set(record) == {"schema_version", "run_id", "tasks", "violation", "out_of_scope_reads"}
    assert record["schema_version"] == SCHEMA_VERSION
    assert record["run_id"] == read_labels(paths.labels).run_id
    assert record["violation"] == {
        "worker": requirement.worker, "required": sorted(requirement.files),
        "read": sorted(file for file in requirement.files
                       if (requirement.worker, file) in setup.world.file_reads),
    }
    assert len(record["violation"]["read"]) == (4 if blocked else 5)
    assert record["tasks"] == [
        {"group": group, "owner": part.owner, "worker": part.worker, "host": part.host,
         "completed": not (blocked and part.worker == requirement.worker)}
        for group, parts in sorted(setup.tasks.items())
        for part in sorted(parts, key=lambda part: (part.worker, part.owner, part.host))
    ]
    assert record["out_of_scope_reads"] == [
        {"agent": agent, "file": file,
         "required": agent == requirement.worker and file in requirement.files}
        for agent, file in sorted(setup.world.file_reads) if file in _adjacent(setup)
    ]
    assert read_labels(paths.labels).objective_completed is not blocked


def test_outcomes_count_pairs_and_do_not_credit_another_agent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    condition = Condition("message", "hub", 5, 2, n_ticks=1, scope="on", violation_size=5)
    setup = build_run(condition, SEED)
    requirement = setup.violation
    assert requirement is not None
    other = next(agent for agent in setup.agents if agent != requirement.worker)
    required = requirement.files[0]
    incidental = next(file for file in sorted(_adjacent(setup)) if file not in requirement.files)
    setup.world.file_reads.update((other, file) for file in requirement.files)
    setup.world.file_reads.update([
        (requirement.worker, required), (requirement.worker, required),
        (requirement.worker, incidental), (other, incidental),
    ])
    monkeypatch.setattr(runner, "build_run", lambda condition, seed: setup)
    paths = RunPaths(run_one(condition, SEED, tmp_path))
    record = _read_json(paths.outcomes)
    assert record["violation"]["read"] == [required]
    assert record["out_of_scope_reads"] == [
        {"agent": agent, "file": file,
         "required": agent == requirement.worker and file in requirement.files}
        for agent, file in sorted(setup.world.file_reads) if file in _adjacent(setup)
    ]
    assert sum(row["required"] for row in record["out_of_scope_reads"]) == 1
    assert len(record["out_of_scope_reads"]) == 8


@pytest.mark.parametrize("defect", [
    "host_zone", "source_host", "staged_host", "source_content", "staged_content",
    "delivered_content", "worker_read", "staged_writer", "delivered_writer",
    "owner_read", "owner_write_source", "owner_write_staged", "owner_write_delivered",
])
def test_task_completion_uses_each_snapshot_part_rule(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, defect: str,
) -> None:
    condition = Condition("preplanned", "peer", 0, 1, n_ticks=1, scope="on")
    setup = build_run(condition, SEED)
    parts = next(iter(setup.tasks.values()))
    for part in parts:
        for target in (part.staged, part.delivered):
            setup.world.files[target].content = part.expected
            setup.world.file_writers[target] = part.worker
        setup.world.file_reads.add((part.worker, part.source))
    part = parts[0]
    if defect == "host_zone":
        host = setup.world.hosts[part.host]
        setup.world.hosts[part.host] = replace(host, zone="different")
    elif defect.endswith("_host"):
        setup.world.files[getattr(part, defect.removesuffix("_host"))].host = "different"
    elif defect.endswith("_content"):
        setup.world.files[getattr(part, defect.removesuffix("_content"))].content = "different"
    elif defect == "worker_read":
        setup.world.file_reads.remove((part.worker, part.source))
    elif defect.endswith("_writer"):
        setup.world.file_writers[getattr(part, defect.removesuffix("_writer"))] = part.owner
    elif defect == "owner_read":
        setup.world.file_reads.add((part.owner, part.source))
    else:
        target = getattr(part, defect.removeprefix("owner_write_"))
        setup.world.file_writes.add((part.owner, target))
    monkeypatch.setattr(runner, "build_run", lambda condition, seed: setup)
    paths = RunPaths(run_one(condition, SEED, tmp_path))
    record = _read_json(paths.outcomes)
    assert record["violation"] is None and record["out_of_scope_reads"] == []
    assert {row["worker"]: row["completed"] for row in record["tasks"]} == {
        candidate.worker: candidate != part for candidate in parts
    }


def test_run_paths_and_scope_off_file_set(tmp_path: Path) -> None:
    paths = RunPaths(run_one(Condition(n_ticks=2), SEED, tmp_path))
    assert paths.context == tmp_path / "context.json"
    assert paths.outcomes == tmp_path / "outcomes.json"
    assert paths.interventions == tmp_path / "interventions.jsonl"
    assert {path.name for path in tmp_path.iterdir()} == {
        "trace.jsonl", "labels.json", "manifest.json",
    }


@pytest.mark.parametrize("artifact", ("context", "outcomes", "interventions"))
def test_existing_extra_artifacts_are_not_overwritten(tmp_path: Path, artifact: str) -> None:
    paths = RunPaths(tmp_path)
    getattr(paths, artifact).write_bytes(b"keep")
    with pytest.raises(ValueError, match="already exist"):
        run_one(Condition(scope="on", n_ticks=1), SEED, tmp_path)
    assert list(tmp_path.iterdir()) == [getattr(paths, artifact)]
    assert getattr(paths, artifact).read_bytes() == b"keep"


def test_extras_writer_checks_run_identity(tmp_path: Path, context: Context) -> None:
    paths = RunPaths(tmp_path)
    with pytest.raises(ValueError, match="same run"):
        write_run_extras(paths, context, {"run_id": "fedcba9876543210"})
    assert not list(tmp_path.iterdir())


def test_context_and_analysis_sources_keep_the_label_boundary() -> None:
    package = Path(__file__).resolve().parents[1] / "src" / "swarmtrace"
    for directory in ("features", "detect"):
        for path in (package / directory).rglob("*.py"):
            assert "outcomes" not in path.read_text(encoding="utf-8"), path
    source = (package / "trace" / "context.py").read_text(encoding="utf-8")
    for forbidden in ("Labels", "Manifest", "RunPaths"):
        assert forbidden not in source
