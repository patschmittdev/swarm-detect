import ast
import hashlib
import inspect
import socket
from copy import deepcopy
from pathlib import Path

import pytest

from swarmtrace.agents.base import Action, Observation
from swarmtrace.agents.random_walk import RandomWalkAgent
from swarmtrace.sim.engine import (
    Engine,
    Intervention,
    cut_channel,
    halt_all,
    quarantine,
    revoke_credential,
)
from swarmtrace.sim.recorder import Recorder
from swarmtrace.trace import io
from swarmtrace.trace.interventions import InterventionRecord
from swarmtrace.trace.schema import TOOLS, TraceEvent, validate_trace
from swarmtrace.world import ToolResult, generate_world, tools

A = "a-00000001"
B = "a-00000002"


class ScriptedAgent:
    def __init__(self, actions: dict[int, Action]) -> None:
        self.actions = actions
        self.observations: list[Observation] = []

    def act(self, observation: Observation) -> Action | None:
        self.observations.append(observation)
        return self.actions.get(observation.tick)


def test_scripted_exchange_tracks_only_most_recent_successful_receipt(tmp_path: Path) -> None:
    world = generate_world(42, 1)
    host = next(iter(world.hosts))
    file = next(f.id for f in world.files.values() if f.content is not None)
    for agent in (A, B):
        world.add_agent(agent, zones=tuple(world.zones))
    agents = {
        A: ScriptedAgent({
            0: Action("write", file, content=""),
            3: Action("send", B, content=""),
            7: Action("read", file),
            8: Action("scan", host),
            9: Action("send", A, content="self"),
            10: Action("recv", A),
            11: Action("scan", host),
        }),
        B: ScriptedAgent({
            1: Action("read", file),
            2: Action("scan", host),
            4: Action("recv", A),
            5: Action("write", file, content="reply"),
            6: Action("read", file),
            12: Action("recv", A),
            13: Action("scan", host),
        }),
    }
    path = tmp_path / "trace.jsonl"
    events = Engine(world, agents, seed=19).run(14, path)
    assert [event.seq for event in events] == list(range(14))
    assert [event.tick for event in events] == list(range(14))
    assert [event.provenance for event in events] == [
        None, None, 1, None, 1, 4, 4, None, 7, 7, 7, 7, 4, 4,
    ]
    assert events[12].result["status"] == "not_found"
    assert events[0].content == events[1].content == events[3].content == events[4].content == ""
    assert events[3].args == events[4].args
    assert io.read_trace(path).events == events
    validate_trace(events)
    assert b"\r" not in path.read_bytes()
    assert path.read_bytes().endswith(b"\n")


@pytest.mark.parametrize("status", ["denied", "not_found", "error"])
def test_failed_write_and_receipt_do_not_change_provenance(tmp_path: Path, status: str) -> None:
    recorder = Recorder("0123456789abcdef")
    file = "f-00000001"
    script = [
        (A, Action("write", file, content="x"), ToolResult("ok", 1, "x")),
        (B, Action("read", file), ToolResult("ok", 1, "x")),
        (B, Action("write", file, content="y"), ToolResult(status, 0)),
        (B, Action("read", file), ToolResult(status, 0)),
        (B, Action("read", file), ToolResult("ok", 1, "x")),
        (B, Action("scan", "h-00000001"), ToolResult("ok", 0)),
    ]
    for tick, (agent, action, result) in enumerate(script):
        recorder.record(tick, agent, action, result)
    assert [event.provenance for event in recorder.events] == [None, None, 1, 1, 1, 4]
    assert recorder.events[2].content is recorder.events[3].content is None
    recorder.write(tmp_path / "trace.jsonl")
    validate_trace(recorder.events)


def test_reading_initial_content_is_not_a_receipt(tmp_path: Path) -> None:
    world = generate_world(42, 1)
    world.add_agent(A, zones=tuple(world.zones))
    file = next(f.id for f in world.files.values() if f.content is not None)
    agent = ScriptedAgent({0: Action("read", file), 1: Action("read", file)})
    events = Engine(world, {A: agent}, seed=1).run(2, tmp_path / "trace.jsonl")
    assert [event.provenance for event in events] == [None, None]


def test_monitor_quarantine_waits_until_next_tick_and_logs_all_calls(tmp_path: Path) -> None:
    world = generate_world(42, 1)
    file = next(iter(world.files))
    host = next(iter(world.hosts))
    credential = next(iter(world.credentials))
    actions = [
        Action("scan", host), Action("login", host, {"credential": credential}),
        Action("list", host, {"prefix": ""}), Action("read", file),
        Action("write", file, content="secret"), Action("send", B, content="secret"),
        Action("recv", B),
    ]
    for agent in (A, B):
        world.add_agent(agent, zones=tuple(world.zones), credentials=(credential,))
    agents = {
        agent: ScriptedAgent({0: Action("scan", host), **dict(enumerate(actions, 1))})
        for agent in (A, B)
    }
    seen: list[TraceEvent] = []
    victim: list[str] = []

    def monitor(event: TraceEvent) -> Intervention | None:
        seen.append(event)
        if not victim:
            victim.append(B if event.agent == A else A)
            return quarantine(victim[0])
        return None

    events = Engine(world, agents, seed=3, monitor=monitor).run(8, tmp_path / "trace.jsonl")
    assert tuple(seen) == events
    assert len(events) == 16
    assert all(event.result["status"] == "ok" for event in events if event.tick == 0)
    denied = [event for event in events if event.agent == victim[0] and event.tick > 0]
    assert {event.tool for event in denied} == set(TOOLS)
    assert all(event.result == {"status": "denied", "size": 0} for event in denied)
    assert all(event.content is None for event in denied)
    validate_trace(events)


def test_channel_cut_applies_next_tick_to_send_and_queued_recv(tmp_path: Path) -> None:
    world = generate_world(5, 1)
    for agent in (A, B):
        world.add_agent(agent)
    agents = {
        A: ScriptedAgent({0: Action("send", B, content="first"), 1: Action("recv", B)}),
        B: ScriptedAgent({0: Action("send", A, content="second"), 1: Action("send", A)}),
    }
    events = Engine(world, agents, seed=4, monitor=lambda event: cut_channel()).run(
        2, tmp_path / "trace.jsonl"
    )
    assert [event.result["status"] for event in events] == ["ok", "ok", "denied", "denied"]
    assert all(event.content is None for event in events[2:])


def test_failed_and_exceptional_tools_are_recorded_and_observed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    world = generate_world(5, 1)
    world.add_agent(A)
    host = next(iter(world.hosts))
    failure = tools.SimulatedToolError("simulated tool failure")

    def broken_scan(*args: object) -> ToolResult:
        raise failure

    monkeypatch.setattr(tools, "scan", broken_scan)
    agent = ScriptedAgent({
        0: Action("read", "f-ffffffff"), 1: Action("list", host, {"prefix": ""}),
        2: Action("scan", host), 3: Action("recv", A),
    })
    events = Engine(world, {A: agent}, seed=4).run(5, tmp_path / "trace.jsonl")
    assert [event.result["status"] for event in events] == [
        "not_found", "denied", "error", "not_found",
    ]
    assert agent.observations[0].last_result is None
    assert [obs.last_result.status for obs in agent.observations[1:]] == [
        "not_found", "denied", "error", "not_found",
    ]
    assert all(event.content is None for event in events)


def test_unexpected_tool_exception_propagates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    world = generate_world(5, 1)
    world.add_agent(A, zones=tuple(world.zones))
    host = next(iter(world.hosts))
    failure = KeyError("broken simulator")

    def broken_scan(*args: object) -> ToolResult:
        raise failure

    monkeypatch.setattr(tools, "scan", broken_scan)
    agent = ScriptedAgent({0: Action("scan", host)})
    path = tmp_path / "trace.jsonl"
    with pytest.raises(KeyError) as caught:
        Engine(world, {A: agent}, seed=4).run(1, path)
    assert caught.value is failure
    assert not path.exists()


def test_monitor_cannot_change_recorded_args_or_result(tmp_path: Path) -> None:
    world = generate_world(5, 1)
    world.add_agent(A, zones=tuple(world.zones))
    host = next(iter(world.hosts))
    agent = ScriptedAgent({0: Action("list", host, {"prefix": "/data/"})})
    expected_size = tools.list(world, A, host, "/data/").size

    def monitor(event: TraceEvent) -> None:
        event.args["prefix"] = "tampered"
        event.result["status"] = "denied"
        event.result["size"] = 999

    path = tmp_path / "trace.jsonl"
    events = Engine(world, {A: agent}, seed=4, monitor=monitor).run(1, path)
    assert events[0].args == {"prefix": "/data/"}
    assert events[0].result == {"status": "ok", "size": expected_size}
    assert io.read_trace(path).events == events


@pytest.mark.parametrize("accessor", ["record", "events"])
def test_recorder_exposed_events_cannot_change_stored_records(tmp_path: Path, accessor: str) -> None:
    recorder = Recorder("0123456789abcdef")
    event = recorder.record(
        0, A, Action("list", "h-00000001", {"prefix": "/data/"}), ToolResult("ok", 1),
    )
    if accessor == "events":
        event = recorder.events[0]
    event.args["prefix"] = "tampered"
    event.result["status"] = "denied"
    event.result["size"] = 999
    path = tmp_path / "trace.jsonl"
    recorder.write(path)
    stored = io.read_trace(path).events[0]
    assert stored.args == {"prefix": "/data/"}
    assert stored.result == {"status": "ok", "size": 1}
    assert recorder.events == (stored,)


def test_schedule_calls_only_due_agents_and_none_does_not_emit(tmp_path: Path) -> None:
    world = generate_world(6, 1)
    host = next(iter(world.hosts))
    for agent in (A, B):
        world.add_agent(agent, zones=tuple(world.zones))
    agents = {
        A: ScriptedAgent({0: Action("scan", host), 4: Action("scan", host)}),
        B: ScriptedAgent({1: Action("scan", host), 3: Action("scan", host)}),
    }
    events = Engine(world, agents, seed=8, schedule={A: (0, 2, 4), B: (1, 3)}).run(
        5, tmp_path / "trace.jsonl"
    )
    assert [obs.tick for obs in agents[A].observations] == [0, 2, 4]
    assert [obs.tick for obs in agents[B].observations] == [1, 3]
    assert [event.tick for event in events] == [0, 1, 3, 4]


def test_full_run_is_deterministic_by_hash_and_opens_no_sockets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    def no_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("simulation must not open sockets")

    monkeypatch.setattr(socket, "socket", no_network)
    hashes = []
    for index, seed in enumerate((42, 42, 43)):
        world = generate_world(seed, 4)
        agents = {}
        for offset in range(4):
            agent = f"a-{offset:08x}"
            world.add_agent(agent, zones=tuple(world.zones))
            agents[agent] = RandomWalkAgent(seed + offset)
        path = tmp_path / f"run-{index}.jsonl"
        events = Engine(world, agents, seed=seed).run(16, path)
        assert len(events) == 64
        validate_trace(events)
        assert io.read_trace(path).events == events
        assert all(event.result["status"] == "ok" for event in events)
        orders = {tuple(event.agent for event in events if event.tick == tick) for tick in range(16)}
        assert len(orders) > 1
        hashes.append(hashlib.sha256(path.read_bytes()).hexdigest())
    assert hashes[0] == hashes[1]
    assert hashes[0] != hashes[2]


def test_recorder_is_only_simulation_writer_and_agents_receive_no_internal_objects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    world = generate_world(7, 1)
    world.add_agent(A, zones=tuple(world.zones))
    agent = ScriptedAgent({0: Action("scan", next(iter(world.hosts)))})
    writes: list[str] = []
    original = io.write_trace

    def spy(path: str | Path, events: tuple[TraceEvent, ...]) -> None:
        writes.append(inspect.currentframe().f_back.f_globals["__name__"])
        original(path, events)

    monkeypatch.setattr(io, "write_trace", spy)
    Engine(world, {A: agent}, seed=9).run(2, tmp_path / "trace.jsonl")
    assert writes == ["swarmtrace.sim.recorder"]
    assert set(vars(agent)) == {"actions", "observations"}
    observation = agent.observations[0]
    assert set(vars(observation)) == {"tick", "agent", "hosts", "agents", "last_result"}
    assert observation.agent == A
    assert observation.hosts == tuple(sorted(world.hosts))
    assert observation.agents == (A,)
    root = Path(__file__).parents[1] / "src" / "swarmtrace"
    for package in ("world", "sim", "agents"):
        for path in (root / package).rglob("*.py"):
            if path.name == "recorder.py":
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    name = getattr(node.func, "id", getattr(node.func, "attr", ""))
                    assert name not in {"TraceEvent", "write_trace", "write_labels", "read_labels"}


def test_intervention_factories_keep_the_existing_positional_fields() -> None:
    assert Intervention("quarantine", A).credential is None
    assert revoke_credential("c-00000001") == Intervention("revoke_credential", None, "c-00000001")
    assert halt_all() == Intervention("halt_all", None, None)


def test_tick_controller_runs_after_after_tick_with_independent_tick_copies(tmp_path: Path) -> None:
    world = generate_world(5, 1)
    world.add_agent(A, zones=tuple(world.zones))
    host = next(iter(world.hosts))
    agent = ScriptedAgent({0: Action("list", host, {"prefix": "/data/"}),
                           2: Action("scan", host)})
    order = []
    seen = []
    retained = []

    def monitor(event: TraceEvent) -> None:
        order.append(("monitor", event.tick))
        event.args["tampered"] = "monitor"
        event.result["status"] = "denied"

    def controller(tick: int, events: tuple[TraceEvent, ...]) -> tuple[Intervention, ...]:
        assert order[-1] == ("after_tick", tick)
        assert isinstance(events, tuple)
        assert all(event.tick == tick and "tampered" not in event.args for event in events)
        order.append(("controller", tick))
        seen.append((tick, deepcopy(events)))
        retained.extend(events)
        for event in retained:
            event.args["tampered"] = "controller"
            event.result["status"] = "denied"
        return ()

    engine = Engine(world, {A: agent}, seed=4, monitor=monitor, controller=controller,
                    after_tick=lambda tick: order.append(("after_tick", tick)))
    events = engine.run(4, tmp_path / "trace.jsonl")
    assert [tick for tick, _ in seen] == [0, 1, 2, 3]
    assert seen == [(tick, tuple(event for event in events if event.tick == tick))
                    for tick in range(4)]
    assert all(event.result["status"] == "ok" for event in events)
    assert not engine.interventions
    assert io.read_trace(tmp_path / "trace.jsonl").events == events


def test_tick_decisions_join_monitor_pending_list_and_all_apply_next_tick(tmp_path: Path) -> None:
    world = generate_world(5, 1)
    credential = next(iter(world.credentials))
    host = world.credentials[credential].host
    for agent in (A, B):
        world.add_agent(agent, credentials=(credential,))
    agents = {agent: ScriptedAgent({0: Action("login", host, {"credential": credential}),
                                    1: Action("scan", host),
                                    2: Action("login", host, {"credential": credential})})
              for agent in (A, B)}

    def controller(tick: int, events: tuple[TraceEvent, ...]) -> tuple[Intervention, ...]:
        return (quarantine(A), revoke_credential(credential)) if tick == 0 else ()

    engine = Engine(world, agents, seed=4, controller=controller,
                    monitor=lambda event: cut_channel() if event.seq == 0 else None)
    events = engine.run(3, tmp_path / "trace.jsonl")
    assert [event.result["status"] for event in events] == ["ok", "ok"] + ["denied"] * 4
    assert world.channel_cut and world.quarantined == {A}
    assert world.revoked_credentials == {credential}
    assert tuple(engine.interventions) == (
        InterventionRecord(0, 1, "cut_channel", None, None),
        InterventionRecord(0, 1, "quarantine", A, None),
        InterventionRecord(0, 1, "revoke_credential", None, credential),
    )


def test_revocation_ends_only_sessions_without_another_successful_valid_login(tmp_path: Path) -> None:
    world = generate_world(5, 2)
    first, second = world.credentials.values()
    file = next(file.id for file in world.files.values()
                if file.host == first.host and file.content is not None)
    for agent in (A, B):
        world.add_agent(agent, credentials=(first.id, second.id))
    world.grant_access(B, first.host, second.id)
    actions = {
        0: Action("login", first.host, {"credential": first.id}),
        2: Action("read", file), 3: Action("scan", first.host),
        4: Action("list", first.host, {"prefix": ""}), 5: Action("read", file),
        6: Action("write", file, content="updated"),
        7: Action("login", first.host, {"credential": first.id}),
        8: Action("scan", second.host), 9: Action("scan", first.host),
    }
    agents = {
        A: ScriptedAgent({**actions, 1: Action("login", second.host, {"credential": second.id})}),
        B: ScriptedAgent({**actions, 1: Action("login", first.host, {"credential": second.id})}),
    }
    snapshots = {}
    earlier = []

    def controller(tick: int, events: tuple[TraceEvent, ...]) -> tuple[Intervention, ...]:
        snapshots[tick] = set(world.sessions)
        if tick <= 2:
            earlier.extend(deepcopy(events))
        if tick == 2:
            return (revoke_credential(first.id),)
        if tick == 8:
            return (revoke_credential(second.id),)
        return ()

    engine = Engine(world, agents, seed=4, controller=controller)
    events = engine.run(10, tmp_path / "trace.jsonl")
    assert tuple(earlier) == tuple(event for event in events if event.tick <= 2)
    assert all(event.result["status"] == "ok" for event in earlier)
    assert snapshots[2] == {(A, first.host), (A, second.host), (B, first.host)}
    assert snapshots[3] == {(A, second.host), (B, first.host)}
    for event in events:
        if 3 <= event.tick <= 6:
            assert event.result["status"] == ("denied" if event.agent == A else "ok")
        if event.tick in (7, 9):
            assert event.result["status"] == "denied"
        if event.tick == 8 and event.agent == A:
            assert event.result["status"] == "ok"
    assert not world.sessions
    assert world.successful_logins == {
        (A, first.host, first.id), (A, second.host, second.id),
        (B, first.host, first.id), (B, first.host, second.id),
    }
    assert tuple(engine.interventions) == (
        InterventionRecord(2, 3, "revoke_credential", None, first.id),
        InterventionRecord(8, 9, "revoke_credential", None, second.id),
    )


def test_revoked_login_preserves_not_found_order_and_independent_zone_access() -> None:
    world = generate_world(5, 1)
    credential = next(iter(world.credentials.values()))
    world.add_agent(A, credentials=(credential.id,))
    world.add_agent(B, zones=tuple(world.zones), credentials=(credential.id,))
    assert tools.login(world, A, credential.host, credential.id).status == "ok"
    assert tools.login(world, B, credential.host, credential.id).status == "ok"
    world.revoke(credential.id)
    world.revoke(credential.id)
    assert world.revoked_credentials == {credential.id}
    assert not world.sessions
    assert tools.login(world, A, "h-ffffffff", credential.id).status == "not_found"
    assert tools.login(world, A, credential.host, "c-ffffffff").status == "not_found"
    assert tools.login(world, A, credential.host, credential.id).status == "denied"
    assert tools.scan(world, A, credential.host).status == "denied"
    assert tools.scan(world, B, credential.host).status == "ok"
    with pytest.raises(ValueError):
        world.revoke("c-ffffffff")
    assert world.revoked_credentials == {credential.id}


def test_halt_all_denies_every_tool_for_every_agent_from_next_tick(tmp_path: Path) -> None:
    world = generate_world(5, 1)
    host = next(iter(world.hosts))
    file = next(iter(world.files))
    credential = next(iter(world.credentials))
    actions = [
        Action("scan", host), Action("login", host, {"credential": credential}),
        Action("list", host, {"prefix": ""}), Action("read", file),
        Action("write", file, content="value"), Action("send", B), Action("recv", B),
    ]
    for agent in (A, B):
        world.add_agent(agent, zones=tuple(world.zones), credentials=(credential,))
    agents = {agent: ScriptedAgent({0: Action("scan", host), **dict(enumerate(actions, 1))})
              for agent in (A, B)}
    engine = Engine(world, agents, seed=4,
                    controller=lambda tick, events: (halt_all(),) if tick == 0 else ())
    events = engine.run(8, tmp_path / "trace.jsonl")
    assert all(event.result["status"] == "ok" for event in events if event.tick == 0)
    assert world.quarantined == {A, B}
    for agent in (A, B):
        denied = [event for event in events if event.agent == agent and event.tick > 0]
        assert {event.tool for event in denied} == set(TOOLS)
        assert all(event.result == {"status": "denied", "size": 0} for event in denied)
        assert all(event.content is None for event in denied)
    validate_trace(events)


@pytest.mark.parametrize("intervention", [
    Intervention("unknown"), quarantine("a-ffffffff"), Intervention("quarantine"),
    revoke_credential("c-ffffffff"), Intervention("revoke_credential"),
    Intervention("halt_all", "a-ffffffff"), Intervention("halt_all", None, "c-ffffffff"),
])
def test_tick_controller_rejects_unknown_targets_even_at_last_tick(
    tmp_path: Path, intervention: Intervention,
) -> None:
    world = generate_world(5, 1)
    world.add_agent(A, zones=tuple(world.zones))
    agent = ScriptedAgent({0: Action("scan", next(iter(world.hosts)))})
    engine = Engine(world, {A: agent}, seed=4,
                    controller=lambda tick, events: (intervention,))
    with pytest.raises(ValueError):
        engine.run(1, tmp_path / "trace.jsonl")
    assert not world.quarantined and not world.revoked_credentials
    assert not engine.interventions


def test_final_tick_decisions_are_pending_not_applied(tmp_path: Path) -> None:
    world = generate_world(5, 1)
    world.add_agent(A, zones=tuple(world.zones))
    agent = ScriptedAgent({0: Action("scan", next(iter(world.hosts)))})
    engine = Engine(world, {A: agent}, seed=4, controller=lambda tick, events: (halt_all(),))
    events = engine.run(1, tmp_path / "trace.jsonl")
    assert events[0].result["status"] == "ok"
    assert not world.quarantined and not engine.interventions
