from collections import defaultdict
from pathlib import Path

import pytest

from swarmtrace.agents.benign import AuditAgent, BackupAgent, PatrolAgent
from swarmtrace.agents.coordinated import OffensiveAgent
from swarmtrace.sim.engine import Engine, quarantine
from swarmtrace.sim.runner import Condition, build_run, run_one
from swarmtrace.trace.io import RunPaths, read_labels, read_trace


def test_solo_population_has_three_distinct_maintenance_behaviours(tmp_path: Path) -> None:
    setup = build_run(Condition(coordinated_groups=1), 1)
    solos = {a: p for a, p in setup.agents.items() if setup.labels[a].role == "benign_solo"}
    assert {type(agent) for agent in solos.values()} == {
        PatrolAgent, BackupAgent, AuditAgent,
    }
    events = Engine(setup.world, solos, seed=1).run(12, tmp_path / "trace.jsonl")
    for identifier, agent in solos.items():
        calls = [event for event in events if event.agent == identifier]
        tools = {event.tool for event in calls}
        if isinstance(agent, PatrolAgent):
            assert "scan" in tools
        elif isinstance(agent, AuditAgent):
            assert "list" in tools
        else:
            assert {"read", "write"} <= tools
            write = next(event for event in calls if event.tool == "write")
            assert any(event.tool == "read" and event.content == write.content
                       and event.seq < write.seq for event in calls)


def test_benign_teams_copy_received_work_or_follow_a_fixed_plan(tmp_path: Path) -> None:
    setup = build_run(Condition(coordinated_groups=2), 3)
    paths = RunPaths(run_one(Condition(coordinated_groups=2), 3, tmp_path / "teams"))
    trace, labels = read_trace(paths.trace), read_labels(paths.labels)
    groups = defaultdict(set)
    for agent, label in labels.agents.items():
        if label.role == "benign_team":
            groups[label.group].add(agent)
    assert len(groups) == 2
    for members in groups.values():
        calls = [e for e in trace.events if e.agent in members]
        copied = [e for e in calls if e.tool == "write" and e.provenance is not None
                  and trace.events[e.provenance].content == e.content]
        policy = setup.agents[next(iter(members))]
        if policy.plan.channel != "preplanned":
            assert copied
        else:
            assert not any(e.tool in {"send", "recv"} for e in calls)
        assert all(any(e.agent == member and e.tool == "write" for e in calls)
                   for member in members)


@pytest.mark.parametrize("channel", ("message", "shared_file"))
def test_handoff_stops_without_predecessor(tmp_path: Path, channel: str) -> None:
    from swarmtrace.objectives import Referee

    setup = build_run(Condition(channel, "peer", 3, 1), 5)
    referee = Referee(setup.objective)
    leader = setup.offensive[0]
    events = Engine(
        setup.world, setup.agents, seed=3,
        monitor=lambda event: quarantine(leader) if event.tick == 0 else None,
        after_tick=lambda tick: referee.observe(setup.world, tick),
    ).run(80, tmp_path / "trace.jsonl")
    assert not referee.completed
    assert any(setup.world.files[part.delivered].content is None
               for part in setup.objective.parts)
    assert any(e.result["status"] == "denied" and e.content is None for e in events)


@pytest.mark.parametrize("topology", ("hub", "peer"))
def test_message_routes_follow_the_selected_topology(tmp_path: Path, topology: str) -> None:
    setup = build_run(Condition("message", topology, 5, 1), 8)
    members = setup.offensive
    expected = ({(members[0], other) for other in members[1:]} | {(members[1], members[0])}
                if topology == "hub"
                else set(zip(members, members[1:] + members[:1], strict=True)))
    events = Engine(setup.world, setup.agents, seed=8).run(160, tmp_path / "trace.jsonl")
    sent = {(e.agent, e.target) for e in events if e.tool == "send"}
    received = {(e.target, e.agent) for e in events
                if e.tool == "recv" and e.result["status"] == "ok"}
    assert sent == received == expected
    assert setup.objective.completed(setup.world)


def test_preplanned_topologies_have_distinct_fixed_schedules() -> None:
    starts = {}
    for topology in ("hub", "peer"):
        setup = build_run(Condition("preplanned", topology, 5, 1), 8)
        policies = [setup.agents[a] for a in setup.offensive]
        assert all(isinstance(agent, OffensiveAgent) for agent in policies)
        starts[topology] = [agent.plan.start_tick for agent in policies]
        assert all(agent.plan.incoming is None and agent.plan.incoming_file is None
                   and not agent.plan.outgoing for agent in policies)
    assert starts == {"hub": [20, 28, 28, 28, 28], "peer": [20, 28, 36, 44, 52]}
