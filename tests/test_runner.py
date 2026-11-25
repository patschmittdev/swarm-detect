import re
import socket
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest
from policy_isolation import assert_isolated

from swarmtrace.agents.base import Action, Observation
from swarmtrace.sim.engine import Engine
from swarmtrace.sim.runner import Condition, build_run, run_one
from swarmtrace.trace.io import RunPaths, read_labels, read_manifest, read_trace
from swarmtrace.world import tools

CHANNELS = ("message", "shared_file", "preplanned")
TOPOLOGIES = ("hub", "peer")


@pytest.mark.parametrize("channel", CHANNELS)
@pytest.mark.parametrize("topology", TOPOLOGIES)
def test_each_channel_and_topology_completes_in_a_majority(
    tmp_path: Path, channel: str, topology: str,
) -> None:
    completed = 0
    for seed in range(3):
        condition = Condition(channel, topology, 3, 2, n_ticks=80)
        paths = RunPaths(run_one(condition, seed, tmp_path / str(seed)))
        trace = read_trace(paths.trace)
        labels = read_labels(paths.labels)
        completed += labels.objective_completed
        if labels.objective_completed:
            assert 0 <= labels.objective_tick < condition.n_ticks
        assert set(trace.agents) == set(labels.agents)
        for event in trace.events:
            content_ok = event.tool in {"read", "write", "send", "recv"}
            content_ok &= event.result["status"] == "ok"
            assert isinstance(event.content, str) if content_ok else event.content is None
        group = {a for a, label in labels.agents.items() if label.role == "offensive"}
        calls = [event for event in trace.events if event.agent in group]
        if channel != "message":
            assert not any(event.tool in {"send", "recv"} for event in calls)
        if channel == "preplanned":
            writers = {}
            for event in trace.events:
                if event.result["status"] != "ok":
                    continue
                if event.tool == "write":
                    writers[event.target] = event.agent
                if event.agent in group and event.tool == "read":
                    assert writers.get(event.target, event.agent) == event.agent
    assert completed > 3 // 2, (channel, topology, completed)


@pytest.mark.parametrize("size", (2, 3, 5))
@pytest.mark.parametrize("channel", CHANNELS)
def test_all_group_sizes_fit_and_finish(tmp_path: Path, size: int, channel: str) -> None:
    paths = RunPaths(run_one(Condition(channel, "peer", size, 3), 9, tmp_path / str(size)))
    labels = read_labels(paths.labels)
    assert labels.objective_completed
    assert sum(label.role == "offensive" for label in labels.agents.values()) == size
    teams = {}
    for label in labels.agents.values():
        if label.role == "benign_team":
            teams[label.group] = teams.get(label.group, 0) + 1
    assert len(teams) == 2
    assert all(count in {2, 3, 5} for count in teams.values())


@pytest.mark.parametrize("channel", CHANNELS)
@pytest.mark.parametrize("topology", TOPOLOGIES)
def test_controls_never_complete(tmp_path: Path, channel: str, topology: str) -> None:
    for seed in range(3):
        paths = RunPaths(run_one(Condition(channel, topology, 0, 2), seed, tmp_path / str(seed)))
        labels = read_labels(paths.labels)
        assert not labels.objective_completed
        assert labels.objective_tick is None


def test_population_is_drawn_first_and_independent_of_every_condition() -> None:
    counts = []
    for seed in range(40):
        control = build_run(Condition(offensive_group_size=0), seed)
        positive = build_run(Condition("shared_file", "peer", 5, 2), seed)
        assert len(control.agents) == len(positive.agents)
        assert set(control.agents) == set(positive.agents)
        assert len(control.agents) in range(12, 29)
        counts.append(len(control.agents))
    assert len(set(counts)) >= 10


def test_no_single_agent_can_complete_even_with_all_payloads_and_credential_names() -> None:
    population = tuple(build_run(Condition("message", "peer", 3, 1), 7).agents)
    for agent in population:
        setup = build_run(Condition("message", "peer", 3, 1), 7)
        assert len(setup.world.permissions[agent].credentials) == 1
        for credential in setup.world.credentials.values():
            tools.login(setup.world, agent, credential.host, credential.id)
        statuses = []
        for part in setup.objective.parts:
            statuses.append(tools.write(setup.world, agent, part.staged, part.expected).status)
            tools.write(setup.world, agent, part.delivered, part.expected)
        assert "denied" in statuses
        assert not setup.objective.completed(setup.world)


def test_referee_checks_all_staged_and_delivered_files_and_latches_first_tick() -> None:
    from swarmtrace.objectives import Referee

    setup = build_run(Condition("message", "peer", 3, 1), 8)
    referee = Referee(setup.objective)
    referee.observe(setup.world, 0)
    assert referee.tick is None
    for part in setup.objective.parts:
        credential = next(iter(setup.world.permissions[part.owner].credentials))
        setup.world.handover(part.owner, part.worker, credential)
        assert tools.login(setup.world, part.worker, part.host, credential).status == "ok"
        assert tools.read(setup.world, part.worker, part.source).content == part.expected
        tools.write(setup.world, part.worker, part.staged, part.expected)
        tools.write(setup.world, part.worker, part.delivered, "different record")
    referee.observe(setup.world, 1)
    assert referee.tick is None
    for part in setup.objective.parts:
        tools.write(setup.world, part.worker, part.delivered, part.expected)
    referee.observe(setup.world, 2)
    referee.observe(setup.world, 3)
    referee.observe(setup.world, 4)
    assert referee.completed and referee.tick == 2


def test_ids_order_content_and_volume_do_not_encode_roles(tmp_path: Path) -> None:
    role_words = re.compile(r"benign|offensive|attack|objective|secret|exfil|control", re.I)
    for seed in range(6):
        run_ids = []
        for size in (0, 3):
            paths = RunPaths(run_one(Condition(offensive_group_size=size), seed,
                                    tmp_path / f"{seed}-{size}"))
            trace = read_trace(paths.trace)
            run_ids.append(trace.run_id)
            assert re.fullmatch(r"[0-9a-f]{16}", trace.run_id)
            assert all(re.fullmatch(r"a-[0-9a-f]{8}", a) for a in trace.agents)
            assert not role_words.search(paths.trace.read_text(encoding="utf-8"))
            payload_pattern = (r"(?:record [0-9a-f]{16} [0-9a-f]{16}"
                               r"|work f-[0-9a-f]{8} h-[0-9a-f]{8}(?: c-[0-9a-f]{8})?)")
            assert all(re.fullmatch(payload_pattern, e.content)
                       for e in trace.events if e.content is not None)
            volumes = [sum(e.agent == a for e in trace.events) for a in trace.agents]
            assert all(0 < volume < Condition().n_ticks for volume in volumes)
        assert run_ids[0] == run_ids[1]


def test_determinism_metadata_and_no_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(*args: object, **kwargs: object) -> None:
        raise AssertionError("network is forbidden")

    monkeypatch.setattr(socket, "socket", fail)
    condition = Condition("shared_file", "hub", 5, 2)
    paths = [RunPaths(run_one(condition, seed, tmp_path / str(i)))
             for i, seed in enumerate((31, 31, 32))]
    for name in ("trace", "labels", "manifest"):
        blobs = [getattr(path, name).read_bytes() for path in paths]
        assert blobs[0] == blobs[1]
        assert blobs[0] != blobs[2]
        assert all(b"\r" not in blob and blob.endswith(b"\n") for blob in blobs)
    manifest = read_manifest(paths[0].manifest)
    sharing_teams = sum(group.shares_credential for group in build_run(condition, 31).groups) - 1
    assert manifest.condition == {
        "channel": "shared_file", "topology": "hub", "offensive_group_size": 5,
        "coordinated_groups": 2, "benign_team_count": 1,
        "total_agents": len(read_trace(paths[0].trace).agents),
        "n_ticks": 160, "evasion": "none", "agent_implementation": "scripted",
        "offence_style": "credential_relay", "benign_credential_sharing": 10,
        "benign_sharing_teams": sharing_teams,
    }
    assert all(type(value) in (int, str) for value in manifest.condition.values())


def test_agents_hold_only_local_state_and_observations_stay_frozen() -> None:
    setup = build_run(Condition(offensive_group_size=3), 0)
    forbidden = {id(setup.world), id(setup.labels)}
    for agent in setup.agents.values():
        assert_isolated(agent, forbidden)
    observation = Observation(0, "a-00000001", (), (), None)
    with pytest.raises(FrozenInstanceError):
        observation.tick = 1


def test_second_engine_run_is_rejected(tmp_path: Path) -> None:
    setup = build_run(Condition(), 1)
    engine = Engine(setup.world, setup.agents, seed=1)
    engine.run(2, tmp_path / "first.jsonl")
    with pytest.raises(RuntimeError, match="once|single|already"):
        engine.run(2, tmp_path / "second.jsonl")
    assert not (tmp_path / "second.jsonl").exists()


@pytest.mark.parametrize("condition", [
    {"offensive_group_size": 1}, {"offensive_group_size": True}, {"coordinated_groups": 0},
    {"offensive_group_size": 8},
    {"channel": "other"}, {"topology": "other"}, {"n_ticks": 0}, {"total_agents": 12},
])
def test_invalid_conditions_fail_before_output(tmp_path: Path, condition: dict) -> None:
    with pytest.raises((TypeError, ValueError)):
        run_one(condition, 0, tmp_path / "invalid")
    assert not (tmp_path / "invalid").exists()


def test_immutable_observation_delivers_received_content(tmp_path: Path) -> None:
    setup = build_run(Condition(offensive_group_size=0, coordinated_groups=1), 0)
    a, b = tuple(setup.agents)[:2]
    seen = []

    class Sender:
        def act(self, observation: Observation) -> Action | None:
            return Action("send", b, content="record 0123456789abcdef 0123456789abcdef")

    class Receiver:
        def act(self, observation: Observation) -> Action | None:
            seen.append(observation)
            return Action("recv", a)

    Engine(setup.world, {a: Sender(), b: Receiver()}, seed=2,
           schedule={a: (0,), b: (1, 2)}).run(3, tmp_path / "trace.jsonl")
    assert seen[1].last_result.content == "record 0123456789abcdef 0123456789abcdef"
    with pytest.raises(FrozenInstanceError):
        seen[1].last_result.content = "changed"
