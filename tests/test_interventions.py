import ast
import json
from collections.abc import Sequence
from dataclasses import asdict, fields, replace
from pathlib import Path

import pytest

from swarmtrace.agents.base import Action, Observation
from swarmtrace.sim.engine import Engine, cut_channel
from swarmtrace.sim.recorder import write_run_interventions
from swarmtrace.sim.runner import Condition, run_one
from swarmtrace.trace.interventions import (
    KINDS,
    Controller,
    Decision,
    InterventionRecord,
    read_interventions,
    write_interventions,
)
from swarmtrace.trace.io import RunPaths, read_trace
from swarmtrace.trace.schema import TraceEvent
from swarmtrace.trace.tiers import Tier, project
from swarmtrace.world import generate_world


class Observer:
    tier = Tier.V1

    def __init__(self) -> None:
        self.calls: list[tuple[int, tuple[TraceEvent, ...]]] = []

    def observe(self, tick: int, events: tuple[TraceEvent, ...]) -> Sequence[Decision]:
        assert type(tick) is int and isinstance(events, tuple)
        assert all(type(event) is TraceEvent and event.tick == tick for event in events)
        self.calls.append((tick, events))
        return ()


def test_neutral_intervention_contract() -> None:
    assert KINDS == ("quarantine", "revoke_credential", "halt_all")
    assert [field.name for field in fields(Decision)] == ["kind", "agent", "credential"]
    assert [field.name for field in fields(InterventionRecord)] == [
        "tick", "effective_tick", "kind", "agent", "credential",
    ]
    assert Decision("halt_all") == Decision("halt_all", None, None)
    controller: Controller = Observer()
    assert controller.tier is Tier.V1
    assert controller.observe(0, ()) == ()


def test_interventions_round_trip_in_canonical_format(tmp_path: Path) -> None:
    records = (
        InterventionRecord(7, 8, "quarantine", "a-00000001", None),
        InterventionRecord(7, 8, "revoke_credential", None, "c-00000001"),
        InterventionRecord(15, 16, "halt_all", None, None),
    )
    path = tmp_path / "interventions.jsonl"
    write_interventions(path, records)
    expected = b"".join(
        (json.dumps(asdict(record), sort_keys=True, separators=(",", ":")) + "\n").encode()
        for record in records
    )
    assert path.read_bytes() == expected
    assert b"\r" not in expected
    assert read_interventions(path) == records
    write_interventions(path, ())
    assert path.read_bytes() == b""
    assert read_interventions(path) == ()


@pytest.mark.parametrize("hook", ["monitor", "controller"])
def test_recorded_channel_cut_round_trips_through_recorder(tmp_path: Path, hook: str) -> None:
    agent = "a-00000001"
    world = generate_world(5, 1)
    world.add_agent(agent)

    class Sender:
        def act(self, observation: Observation) -> Action:
            return Action("send", agent, content="message")

    hooks = (
        {"monitor": lambda event: cut_channel() if event.tick == 0 else None}
        if hook == "monitor" else
        {"controller": lambda tick, events: (cut_channel(),) if tick == 0 else ()}
    )
    paths = RunPaths(tmp_path)
    engine = Engine(world, {agent: Sender()}, seed=4, **hooks)
    events = engine.run(2, paths.trace)
    assert [event.result["status"] for event in events] == ["ok", "denied"]
    records = (InterventionRecord(0, 1, "cut_channel", None, None),)
    assert tuple(engine.interventions) == records
    write_run_interventions(paths, engine.interventions)
    assert read_interventions(paths.interventions) == records
    assert paths.interventions.read_bytes() == (
        b'{"agent":null,"credential":null,"effective_tick":1,"kind":"cut_channel","tick":0}\n'
    )


@pytest.mark.parametrize("field,value", [
    ("tick", 7.0), ("effective_tick", 8.0), ("tick", True),
    ("agent", 1.5), ("credential", 1.5), ("kind", 1.5), ("kind", "unknown"),
])
def test_intervention_io_rejects_invalid_values(
    tmp_path: Path, field: str, value: object,
) -> None:
    record = InterventionRecord(7, 8, "quarantine", "a-00000001", None)
    path = tmp_path / "interventions.jsonl"
    path.write_bytes(b"keep")
    with pytest.raises(ValueError):
        write_interventions(path, (record, replace(record, **{field: value})))
    assert path.read_bytes() == b"keep"
    path.write_text(json.dumps({**asdict(record), field: value}) + "\n", encoding="utf-8")
    with pytest.raises(ValueError):
        read_interventions(path)


@pytest.fixture(scope="module")
def twins(tmp_path_factory: pytest.TempPathFactory) -> tuple[Condition, RunPaths, RunPaths, Observer]:
    root = tmp_path_factory.mktemp("intervention-twins")
    condition = Condition("message", "peer", 2, 1, n_ticks=40, scope="on", violation_size=1)
    observer = Observer()
    plain = RunPaths(run_one(condition, 31, root / "plain"))
    watched = RunPaths(run_one(condition, 31, root / "watched", controller=observer))
    return condition, plain, watched, observer


def test_passive_controller_leaves_every_twin_artifact_byte_identical(twins: tuple) -> None:
    _, plain, watched, observer = twins
    names = {"trace.jsonl", "labels.json", "manifest.json", "context.json", "outcomes.json"}
    assert {path.name for path in plain.run_dir.iterdir()} == names
    assert {path.name for path in watched.run_dir.iterdir()} == names | {"interventions.jsonl"}
    for name in names:
        assert (plain.run_dir / name).read_bytes() == (watched.run_dir / name).read_bytes()
    assert watched.interventions.read_bytes() == b""
    assert [tick for tick, _ in observer.calls] == list(range(40))


def test_v1_controller_receives_only_projected_events(twins: tuple) -> None:
    _, plain, _, observer = twins
    full = read_trace(plain.trace).events
    assert any(event.content is not None for event in full)
    assert any(event.provenance is not None for event in full)
    seen = tuple(event for _, events in observer.calls for event in events)
    assert seen == tuple(project(event, Tier.V1) for event in full)
    assert all(event.content is None and event.provenance is None for event in seen)
    assert set(vars(observer)) == {"calls"}
    expected = {field.name for field in fields(TraceEvent)}
    assert all(set(vars(event)) == expected for event in seen)


@pytest.mark.parametrize("tier", [Tier.V0, Tier.V2])
def test_runner_respects_declared_tier_and_isolates_controller_mutations(
    twins: tuple, tmp_path: Path, tier: Tier,
) -> None:
    condition, plain, _, _ = twins
    full = read_trace(plain.trace).events

    class MutatingObserver:
        def observe(self, tick: int, events: tuple[TraceEvent, ...]) -> Sequence[Decision]:
            assert events == tuple(project(event, tier) for event in full if event.tick == tick)
            for event in events:
                event.args["tampered"] = "value"
                event.result["status"] = "denied"
            return ()

    controller = MutatingObserver()
    controller.tier = tier
    paths = RunPaths(run_one(condition, 31, tmp_path, controller=controller))
    for baseline in plain.run_dir.iterdir():
        assert (paths.run_dir / baseline.name).read_bytes() == baseline.read_bytes()
    assert paths.interventions.read_bytes() == b""


@pytest.mark.parametrize("kind", KINDS)
def test_decision_preserves_twin_prefix_and_records_effective_tick(
    twins: tuple, tmp_path: Path, kind: str,
) -> None:
    condition, plain, _, _ = twins

    class CheckpointController(Observer):
        def observe(self, tick: int, events: tuple[TraceEvent, ...]) -> Sequence[Decision]:
            super().observe(tick, events)
            if tick != 7:
                return ()
            prefix = [event for _, batch in self.calls for event in batch]
            if kind == "quarantine":
                self.decision = Decision(kind, agent=prefix[0].agent)
            elif kind == "revoke_credential":
                login = next(event for event in prefix
                             if event.tool == "login" and event.result["status"] == "ok")
                self.decision = Decision(kind, credential=login.args["credential"])
            else:
                self.decision = Decision(kind)
            return (self.decision,)

    controller = CheckpointController()
    paths = RunPaths(run_one(condition, 31, tmp_path, controller=controller))
    twin = read_trace(plain.trace).events
    contained = read_trace(paths.trace).events
    assert tuple(event for event in contained if event.tick <= 7) == tuple(
        event for event in twin if event.tick <= 7
    )
    assert read_interventions(paths.interventions) == (
        InterventionRecord(7, 8, kind, controller.decision.agent, controller.decision.credential),
    )
    if kind in ("halt_all", "quarantine"):
        affected = [event for event in contained if event.tick >= 8
                    and (kind == "halt_all" or event.agent == controller.decision.agent)]
        assert affected and all(event.result["status"] == "denied" for event in affected)


def test_scope_off_preserves_file_set_and_last_tick_decision_is_not_written(tmp_path: Path) -> None:
    class LastTickController(Observer):
        def observe(self, tick: int, events: tuple[TraceEvent, ...]) -> Sequence[Decision]:
            super().observe(tick, events)
            return (Decision("halt_all"),) if tick == 1 else ()

    condition = Condition(n_ticks=2)
    plain = RunPaths(run_one(condition, 5, tmp_path / "plain"))
    watched = RunPaths(run_one(condition, 5, tmp_path / "watched", controller=LastTickController()))
    names = {"trace.jsonl", "labels.json", "manifest.json"}
    assert {path.name for path in plain.run_dir.iterdir()} == names
    assert {path.name for path in watched.run_dir.iterdir()} == names | {"interventions.jsonl"}
    for name in names:
        assert (plain.run_dir / name).read_bytes() == (watched.run_dir / name).read_bytes()
    assert watched.interventions.read_bytes() == b""


def test_runner_rejects_unknown_decision_kind(tmp_path: Path) -> None:
    class InvalidController(Observer):
        def observe(self, tick: int, events: tuple[TraceEvent, ...]) -> Sequence[Decision]:
            return (Decision("cut_channel"),)

    with pytest.raises(ValueError):
        run_one(Condition(n_ticks=2), 5, tmp_path, controller=InvalidController())


def test_only_sim_recorder_calls_write_interventions() -> None:
    root = Path(__file__).parents[1] / "src" / "swarmtrace"
    callers = set()
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        names = {"write_interventions"}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                names.update(alias.asname or alias.name for alias in node.names
                             if alias.name == "write_interventions")
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = getattr(node.func, "id", getattr(node.func, "attr", ""))
                if name in names:
                    callers.add(path.relative_to(root).as_posix())
    assert callers == {"sim/recorder.py"}
