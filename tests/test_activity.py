from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from swarmtrace.agents.base import Action, Observation
from swarmtrace.agents.benign import AuditAgent, BackupAgent, PatrolAgent
from swarmtrace.agents.coordinated import BenignTeamAgent, OffensiveAgent
from swarmtrace.objectives import Referee
from swarmtrace.sim.engine import Engine
from swarmtrace.sim.runner import Condition, build_run


def test_default_horizon_matches_runner_sweep_and_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from swarmtrace.cli import main
    from swarmtrace.sim import sweep

    captured = []

    def capture(
        out_dir: Path, seed: int, *, runs_per_condition: int, conditions: tuple[Condition, ...],
    ) -> list[Path]:
        captured.extend(conditions)
        return []

    monkeypatch.setattr(sweep, "run_sweep", capture)
    main(["sweep", "--out", str(tmp_path), "--seed", "7"])
    assert Condition().n_ticks == 160
    assert {condition.n_ticks for condition in sweep.condition_grid()} == {160}
    assert len(captured) == 72
    assert {condition.n_ticks for condition in captured} == {160}


def test_new_activity_stream_preserves_existing_population_ids_and_order() -> None:
    for seed in range(8):
        legacy = np.random.SeedSequence(seed).spawn(8)
        count = int(np.random.default_rng(legacy[0]).integers(12, 29))
        id_rng = np.random.default_rng(legacy[1])
        identifiers = []
        while len(identifiers) < count:
            identifier = "a-" + id_rng.bytes(4).hex()
            if identifier not in identifiers:
                identifiers.append(identifier)
        expected_order = tuple(identifiers[int(i)] for i in
                               np.random.default_rng(legacy[5]).permutation(count))
        for size in (0, 5):
            setup = build_run(Condition(offensive_group_size=size), seed)
            assert tuple(setup.agents) == expected_order
            assert setup.engine_seed == int(legacy[7].generate_state(1, dtype=np.uint64)[0])
            rates = [agent.activity_rate for agent in setup.agents.values()]
            assert all(0.60 <= rate < 0.85 for rate in rates)
            assert len(set(rates)) == count
            assert {agent.mistake_rate for agent in setup.agents.values()} == {0.02}


@pytest.mark.parametrize("channel", ("message", "shared_file", "preplanned"))
def test_role_changes_preserve_each_agents_nonconstant_activity_series(
    tmp_path: Path, channel: str,
) -> None:
    series = []
    rates = []
    for size in (0, 5):
        setup = build_run(Condition(channel, "peer", size, 2, n_ticks=96), 23)
        events = Engine(setup.world, setup.agents, setup.engine_seed).run(
            96, tmp_path / f"{size}.jsonl",
        )
        by_agent = {agent: [0] * 96 for agent in setup.agents}
        for event in events:
            by_agent[event.agent][event.tick] += 1
        assert all(set(values) == {0, 1} for values in by_agent.values())
        series.append(by_agent)
        rates.append({agent: policy.activity_rate for agent, policy in setup.agents.items()})
    assert rates[0] == rates[1]
    assert series[0] == series[1]


@pytest.mark.parametrize("policy_type", (
    PatrolAgent, BackupAgent, AuditAgent, BenignTeamAgent, OffensiveAgent,
))
def test_activity_gate_applies_to_every_policy(policy_type: type) -> None:
    setup = build_run(Condition(offensive_group_size=2), 4)
    prototype = setup.agents[setup.offensive[0]]
    arguments = ((prototype.plan, "backup") if policy_type in (BenignTeamAgent, OffensiveAgent)
                 else (prototype.workspace,))
    inactive = policy_type(*arguments, activity_rate=0.0, activity_seed=7)
    active = policy_type(*arguments, activity_rate=1.0, activity_seed=7)
    for tick in range(16):
        observation = Observation(tick, setup.offensive[0], (), (), None)
        assert inactive.act(observation) is None
        assert active.act(observation) is not None


def test_backup_retains_results_across_inactive_ticks(tmp_path: Path) -> None:
    setup = build_run(Condition(coordinated_groups=1), 6)
    identifier = next(iter(setup.agents))
    workspace = setup.agents[identifier].workspace
    policy = BackupAgent(workspace, activity_rate=0.6, activity_seed=5, mistake_rate=0.0)
    events = Engine(setup.world, {identifier: policy}, seed=0).run(
        40, tmp_path / "backup.jsonl",
    )
    assert len(events) >= 5
    assert events[0].tool == "login"
    assert any(later.tick - earlier.tick > 1 for earlier, later in zip(events, events[1:]))
    assert all(event.result["status"] == "ok" for event in events)
    for index, event in enumerate(events[1:]):
        assert event.tool == ("read" if index % 2 == 0 else "write")
        assert event.content == setup.world.files[workspace.source].content


@pytest.mark.parametrize("channel", ("message", "shared_file"))
def test_both_team_roles_wait_and_resume_when_handoff_arrives(
    tmp_path: Path, channel: str,
) -> None:
    traces = {}
    finished = {}
    for policy_type in (BenignTeamAgent, OffensiveAgent):
        for delay in (18, 34):
            setup = build_run(Condition(channel, "peer", 2, 1), 2)
            leader, worker = setup.offensive
            plan = replace(setup.agents[worker].plan, start_tick=4)
            record = (f"work {plan.delegated_workspace.source} {plan.delegated_workspace.host} "
                      + setup.agents[leader].workspace.credential)
            action = (Action("send", worker, content=record) if channel == "message"
                      else Action("write", plan.incoming_file, content=record))

            class DelayedSender:
                def act(self, observation: Observation) -> Action | None:
                    return action if observation.tick == delay else None

            # Full activity here isolates receipt timing; the rate gate itself
            # and sparse execution are covered separately for every policy.
            recipient = policy_type(plan, "audit", activity_rate=1.0, activity_seed=0,
                                    mistake_rate=0.0)
            events = Engine(setup.world, {leader: DelayedSender(), worker: recipient}, seed=2).run(
                48, tmp_path / f"{policy_type.__name__}-{delay}.jsonl",
            )
            target = leader if channel == "message" else plan.incoming_file
            received = next(event for event in events if event.agent == worker
                            and event.tool == ("recv" if channel == "message" else "read")
                            and event.target == target
                            and event.result["status"] == "ok")
            assert received.tick >= delay
            assert any(event.agent == worker and event.result["status"] == "not_found"
                       and event.tick < received.tick for event in events)
            assert any(event.agent == worker and event.tool == "list"
                       and 4 < event.tick < received.tick for event in events)
            archive = next(event for event in events if event.tool == "write"
                           and event.target == plan.receipt)
            assert archive.content == received.content == record
            assert archive.provenance == received.seq
            publication = next(event for event in events if event.tool == "write"
                               and event.target == plan.delivered)
            assert received.tick < archive.tick < publication.tick
            traces[policy_type, delay] = events
            finished[policy_type, delay] = publication.tick
        assert finished[policy_type, 18] < finished[policy_type, 34]
    for delay in (18, 34):
        assert traces[BenignTeamAgent, delay] == traces[OffensiveAgent, delay]


def test_single_zone_worker_performs_all_possible_steps_but_referee_stays_incomplete(
    tmp_path: Path,
) -> None:
    setup = build_run(Condition("message", "peer", 3, 1), 7)
    identifier = setup.offensive[0]
    credentials = setup.world.permissions[identifier].credentials
    assert len(credentials) == 1
    credential = next(iter(credentials))
    actions = tuple(action for part in setup.objective.parts for action in (
        Action("login", part.host, {"credential": credential}),
        Action("read", part.source),
        Action("write", part.staged, content=part.expected),
        Action("write", part.delivered, content=part.expected),
    ))

    class SingleWorker:
        def act(self, observation: Observation) -> Action | None:
            return actions[observation.tick]

    referee = Referee(setup.objective)
    events = Engine(setup.world, {identifier: SingleWorker()}, seed=3,
                    after_tick=lambda tick: referee.observe(setup.world, tick)).run(
        len(actions), tmp_path / "single.jsonl",
    )
    assert {event.agent for event in events} == {identifier}
    assert len(events) == len(actions)
    assert all(event.result["status"] == "ok" for event in events[:4])
    assert all(setup.world.files[part.delivered].content == part.expected
               for part in setup.objective.parts)
    assert all(setup.world.files[part.staged].content is None
               for part in setup.objective.parts[1:])
    assert any(event.result["status"] == "denied" for event in events)
    assert not referee.completed
    assert referee.tick is None
