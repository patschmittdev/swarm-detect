import hashlib
from collections import Counter
from dataclasses import FrozenInstanceError, fields, replace
from pathlib import Path

import numpy as np
import pytest
from policy_isolation import assert_isolated
from stat_checks import permutation_pvalue

from swarmtrace.agents.base import Observation
from swarmtrace.agents.coordinated import CoordinatedAgent, DelegatedWork
from swarmtrace.objectives import Referee, ScopeRequirement
from swarmtrace.sim.engine import Engine, Intervention, quarantine
from swarmtrace.sim.recorder import Recorder
from swarmtrace.sim.runner import CHANNELS, TOPOLOGIES, Condition, RunSetup, build_run, run_one
from swarmtrace.trace.io import RunPaths, read_manifest
from swarmtrace.trace.schema import TraceEvent
from swarmtrace.trace.tiers import Tier, project
from swarmtrace.world import ToolResult, tools


# Supplied pre-change digests, recorded before this task's source edits.
@pytest.mark.parametrize("size,seed,digests", [
    (5, 31, (
        "fc2aed3227d3971da62ad285be0b104b0787265cd31c3257425592e9ad92279c",
        "e37994974afce00fa78efb71841c67838b8839fff5c62e3ae079b168bafd2a20",
        "65b7d6d9b3fcc7464dc4564a161e18debb9b7ad38cbf61fa110536fe424bf6d2",
    )),
    (5, 32, (
        "c3a133695e2ecec8c6c95b0f9d10d94ebe3015fe20eaefa76df7d1f4f429ef5a",
        "335d8520e8da42135bbe60651b2188c352a46fb6a955dacc83dc6e0a70da955e",
        "af1055c269e1dce30f2fca8b557794f8d2218e8b3d36a9e5f14c56f0603c4291",
    )),
    (0, 31, (
        "306616cf9aa98cfc64bfb63fce3a344ae61403d85076acadf3e0da63bd69949f",
        "56214bc13c4cb8bd53add69522e9c0a12079988d2e5a13098f17ad8f8ccae9e1",
        "9cebbc6b67b44d462cbb13a9e57cae1db73b2d0ecdbf14ef859f3912a2e7fb72",
    )),
])
def test_scope_off_preserves_recorded_bytes(
    tmp_path: Path, size: int, seed: int, digests: tuple[str, ...],
) -> None:
    paths = RunPaths(run_one(Condition("shared_file", "hub", size, 2), seed, tmp_path))
    for name, expected in zip(("trace", "labels", "manifest"), digests, strict=True):
        assert hashlib.sha256(getattr(paths, name).read_bytes()).hexdigest() == expected, name
    assert {path.name for path in tmp_path.iterdir()} == {
        "trace.jsonl", "labels.json", "manifest.json",
    }


def _seed(index: int) -> int:
    return int(np.random.SeedSequence(20261120, spawn_key=(195, index)).generate_state(1)[0])


def _run(setup: RunSetup, path: Path, ticks: int = 160) -> tuple[TraceEvent, ...]:
    return Engine(setup.world, setup.agents, setup.engine_seed).run(ticks, path)


def _work(setup: RunSetup) -> dict[str, DelegatedWork]:
    return {agent: policy.plan.delegated_workspace for agent, policy in setup.agents.items()
            if isinstance(policy, CoordinatedAgent)}


def _adjacent(setup: RunSetup) -> set[str]:
    return {file for work in _work(setup).values() for file in work.adjacent}


@pytest.mark.parametrize("channel", CHANNELS)
@pytest.mark.parametrize("topology", TOPOLOGIES)
def test_scopes_cover_finished_work_and_match_role_flipped_twins(
    tmp_path: Path, channel: str, topology: str,
) -> None:
    condition = Condition(channel, topology, 0, 2, scope="on", benign_credential_sharing=100)
    control = build_run(condition, _seed(0))
    size = len(control.groups[control.focal_group].members)
    positive = build_run(replace(condition, offensive_group_size=size), _seed(0))
    assert control.scopes == positive.scopes
    assert control.tasks == positive.tasks
    assert control.world.files == positive.world.files
    assert control.violation is positive.violation is None
    traces = []
    for index, setup in enumerate((control, positive)):
        assert set(setup.tasks) == {group.id for group in setup.groups}
        assert set(setup.scopes) == {
            part.source for parts in setup.tasks.values() for part in parts
        }
        events = _run(setup, tmp_path / f"{index}.jsonl")
        traces.append((tmp_path / f"{index}.jsonl").read_bytes())
        for group in setup.groups:
            parts = setup.tasks[group.id]
            assert {part.worker for part in parts} == set(group.members)
            for part in parts:
                work = _work(setup)[part.worker]
                scope = setup.scopes[part.source]
                assert work.scope == scope and scope[0] == part.source
                assert 1 <= len(scope) <= 4 and len(set(scope)) == len(scope)
                assert len(work.adjacent) == len(set(work.adjacent)) == 8
                assert not set(work.adjacent).intersection(
                    file for files in setup.scopes.values() for file in files
                )
                assert all(setup.world.files[file].host == part.host
                           for file in (*scope, *work.adjacent))
                writes = [event for event in events if event.agent == part.worker
                          and event.tool == "write" and event.target == part.staged
                          and event.result["status"] == "ok"]
                assert writes, "the fixed horizon must include finished receivers"
                reads = [event for event in events if event.agent == part.worker
                         and event.tool == "read" and event.target in scope
                         and event.result["status"] == "ok"]
                assert tuple(event.target for event in reads) == scope
                assert reads[-1].seq < writes[0].seq
                assert setup.world.files[part.delivered].content == part.expected
    assert traces[0] == traces[1]
    assert positive.objective.completed(positive.world)
    assert not control.objective.completed(control.world)


def test_scope_files_are_initial_records_and_never_receipts_or_write_targets(
    tmp_path: Path,
) -> None:
    condition = Condition("shared_file", "hub", 5, 2)
    baseline = build_run(condition, _seed(1))
    setup = build_run(replace(condition, scope="on", violation_size=5, scope_mistake_rate=50),
                      _seed(1))
    extra = set(setup.world.files) - set(baseline.world.files)
    assert len(extra) == len(setup.agents) * (5 * 3 + 8)
    assert {file: setup.world.files[file] for file in baseline.world.files} == baseline.world.files
    for policy in setup.agents.values():
        host = policy.workspace.host
        assert sum(setup.world.files[file].host == host for file in extra) == 23
    initial = {file: setup.world.files[file].content for file in extra}
    assert all(content.startswith("record ") for content in initial.values())
    assert all(file not in setup.world.file_writers for file in extra)
    # Direct reads of every new file cannot establish a receipt or transfer a token.
    for agent, policy in setup.agents.items():
        host = policy.workspace.host
        assert tools.login(setup.world, agent, host, policy.workspace.credential).status == "ok"
        for file in extra:
            if setup.world.files[file].host == host:
                assert tools.read(setup.world, agent, file).status == "ok"
    assert not setup.world.receipts and not setup.world.file_writers
    assert not any(setup.world.received_credentials.values())
    events = _run(setup, tmp_path / "trace.jsonl")
    assert any(event.tool == "read" and event.target in extra for event in events)
    assert not any(event.tool == "write" and event.target in extra for event in events)
    extra_read_seqs = {event.seq for event in events if event.tool == "read"
                       and event.target in extra and event.result["status"] == "ok"}
    assert not any(event.provenance in extra_read_seqs for event in events)
    assert initial == {file: setup.world.files[file].content for file in extra}


@pytest.mark.parametrize("size", (1, 2, 5))
def test_violation_reads_are_required_and_quarantine_blocks_completion(
    tmp_path: Path, size: int,
) -> None:
    condition = Condition("shared_file", "hub", 5, 2, scope="on", violation_size=size)
    setup = build_run(condition, _seed(2))
    requirement = setup.violation
    assert isinstance(requirement, ScopeRequirement)
    assert setup.objective.violations == (requirement,)
    assert len(requirement.files) == len(set(requirement.files)) == size
    assert requirement.worker in setup.offensive
    work = _work(setup)[requirement.worker]
    assert work.required_reads == requirement.files
    assert set(requirement.files) <= set(work.adjacent)
    assert all(not assigned.required_reads for agent, assigned in _work(setup).items()
               if agent != requirement.worker)
    assert all(setup.world.files[file].host == work.host for file in requirement.files)
    referee = Referee(setup.objective)
    events = Engine(setup.world, setup.agents, setup.engine_seed,
                    after_tick=lambda tick: referee.observe(setup.world, tick)).run(
                        160, tmp_path / "complete.jsonl")
    adjacent = _adjacent(setup)
    reads = [event for event in events if event.tool == "read"
             and event.target in adjacent and event.result["status"] == "ok"]
    assert tuple(event.target for event in reads) == requirement.files
    assert {event.agent for event in reads} == {requirement.worker}
    borrowed = [event for event in events if event.agent == requirement.worker
                and event.tool == "login" and event.target == work.host
                and event.result["status"] == "ok"
                and event.args["credential"] not in
                setup.world.permissions[requirement.worker].credentials]
    assert len(borrowed) == 1 and borrowed[0].seq < reads[0].seq
    scoped = [event for event in events if event.agent == requirement.worker
              and event.tool == "read" and event.target in work.scope
              and event.result["status"] == "ok"]
    assert tuple(event.target for event in scoped) == work.scope
    assert scoped[-1].seq < reads[0].seq
    assert referee.completed and referee.tick >= reads[-1].tick
    assert requirement.completed(setup.world)
    other = next(agent for agent in setup.agents if agent != requirement.worker)
    missing = ScopeRequirement(other, requirement.files)
    assert not missing.completed(setup.world)
    assert not replace(setup.objective, violations=(requirement, missing)).completed(setup.world)
    # Isolate the requirement from unfinished writes: the old objective is complete.
    setup.world.file_reads.remove((requirement.worker, requirement.files[-1]))
    assert replace(setup.objective, violations=()).completed(setup.world)
    assert not requirement.completed(setup.world)
    assert not setup.objective.completed(setup.world)

    blocked = build_run(condition, _seed(2))
    blocked_referee = Referee(blocked.objective)
    trigger = requirement.files[-2] if size > 1 else work.scope[-1]
    interventions = []

    def monitor(event: TraceEvent) -> Intervention | None:
        if (event.agent == requirement.worker and event.tool == "read"
                and event.target == trigger and event.result["status"] == "ok"):
            interventions.append(event.tick)
            return quarantine(requirement.worker)
        return None

    denied = Engine(blocked.world, blocked.agents, blocked.engine_seed, monitor=monitor,
                    after_tick=lambda tick: blocked_referee.observe(blocked.world, tick)).run(
                        160, tmp_path / "blocked.jsonl")
    assert len(interventions) == 1
    assert requirement.worker in blocked.world.quarantined
    assert sum((requirement.worker, file) in blocked.world.file_reads
               for file in requirement.files) == size - 1
    assert any(event.agent == requirement.worker and event.tool == "read"
               and event.target == requirement.files[-1] and event.result["status"] == "denied"
               for event in denied)
    assert not blocked_referee.completed and blocked_referee.tick is None


def test_scope_requirement_is_frozen_and_checks_every_worker_file_pair() -> None:
    setup = build_run(Condition(), _seed(3))
    worker, other = tuple(setup.agents)[:2]
    files = tuple(setup.world.files)[:2]
    requirement = ScopeRequirement(worker, files)
    assert ScopeRequirement(worker, ()).completed(setup.world)
    with pytest.raises(FrozenInstanceError):
        requirement.worker = other
    setup.world.file_reads.update((other, file) for file in files)
    assert not requirement.completed(setup.world)
    setup.world.file_reads.add((worker, files[0]))
    assert not requirement.completed(setup.world)
    setup.world.file_reads.add((worker, files[1]))
    assert requirement.completed(setup.world)


@pytest.mark.parametrize("sharing", (0, 100))
def test_zero_rate_control_has_no_adjacent_reads(tmp_path: Path, sharing: int) -> None:
    setup = build_run(Condition(coordinated_groups=2, scope="on",
                                benign_credential_sharing=sharing), _seed(4))
    events = _run(setup, tmp_path / "trace.jsonl")
    adjacent = _adjacent(setup)
    assert not any(event.tool == "read" and event.target in adjacent for event in events)


def test_mistakes_use_own_and_borrowed_credentials_but_never_solo_agents(tmp_path: Path) -> None:
    observed = Counter()
    for index in range(8):
        condition = Condition("shared_file", "hub", 3, 2, scope="on",
                              scope_mistake_rate=50, benign_credential_sharing=0)
        setup = build_run(condition, _seed(10 + index))
        events = _run(setup, tmp_path / f"{index}.jsonl")
        sessions = {}
        adjacent = _adjacent(setup)
        assert any(label.role == "benign_solo" for label in setup.labels.values())
        for event in events:
            if event.tool == "login" and event.result["status"] == "ok":
                sessions[event.agent, event.target] = event.args["credential"]
            if event.tool != "read" or event.target not in adjacent:
                continue
            assert event.result["status"] == "ok"
            assert setup.labels[event.agent].role != "benign_solo"
            work = _work(setup)[event.agent]
            assert event.target in work.adjacent
            credential = sessions[event.agent, setup.world.files[event.target].host]
            own = credential in setup.world.permissions[event.agent].credentials
            observed["own" if own else "borrowed"] += 1
    assert observed["own"] > 0 and observed["borrowed"] > 0


@pytest.fixture(scope="module")
def scope_statistics(tmp_path_factory: pytest.TempPathFactory) -> dict:
    """48 runs plus actual biased counterparts; retain Engine and Recorder execution."""
    path = tmp_path_factory.mktemp("scope-statistics") / "unused.jsonl"
    rows = {"roles": [], "biased_roles": []}
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(Recorder, "write", lambda self, path: None)
        for index in range(48):
            seed = _seed(100 + index)
            control = build_run(Condition(coordinated_groups=2, scope="on"), seed)
            size = len(control.groups[control.focal_group].members)
            condition = Condition(offensive_group_size=size, coordinated_groups=2,
                                  scope="on", scope_mistake_rate=50, n_ticks=96)
            for biased in (False, True):
                setup = build_run(condition, seed)
                if biased:
                    for agent, policy in setup.agents.items():
                        if setup.labels[agent].role == "benign_team":
                            policy.scope_mistake_rate = 0.0
                work = _work(setup)
                events = _run(setup, path, condition.n_ticks)
                mistakes, reads = Counter(), Counter()
                for event in events:
                    if (event.agent not in work or event.tool != "read"
                            or event.result["status"] != "ok"):
                        continue
                    assigned = work[event.agent]
                    mistakes[event.agent] += event.target in assigned.adjacent
                    reads[event.agent] += event.target in (*assigned.scope, *assigned.adjacent)
                for group in setup.groups:
                    members = group.members
                    rows["biased_roles" if biased else "roles"].append({
                        "offensive": setup.labels[members[0]].role == "offensive",
                        "block": index,
                        "scope_size": (sum(len(work[a].scope) for a in members), len(members)),
                        "mistakes": (sum(mistakes[a] for a in members),
                                     sum(reads[a] for a in members)),
                    })
    return rows


def _role_pvalue(rows: list[dict], metric: str, shift: float = 0.0) -> float:
    return permutation_pvalue(
        [row[metric][0] + shift * row[metric][1] * row["offensive"] for row in rows],
        [row[metric][1] for row in rows], [row["offensive"] for row in rows],
        [row["block"] for row in rows], seed=_seed(1000),
    )


@pytest.mark.parametrize("metric", ("scope_size", "mistakes"))
def test_scope_statistics_are_not_in_the_extreme_one_percent(
    scope_statistics: dict, metric: str,
) -> None:
    assert _role_pvalue(scope_statistics["roles"], metric) >= 0.01, metric


def test_scope_permutation_detects_a_planted_size_difference(scope_statistics: dict) -> None:
    assert _role_pvalue(scope_statistics["roles"], "scope_size", shift=1.0) < 0.01


def test_scope_permutation_detects_an_actual_role_dependent_mistake_rate(
    scope_statistics: dict,
) -> None:
    assert _role_pvalue(scope_statistics["biased_roles"], "mistakes") < 0.01


@pytest.mark.parametrize("channel", CHANNELS)
@pytest.mark.parametrize("topology", TOPOLOGIES)
def test_scope_on_delegation_and_sharing_are_identical_at_v0(
    tmp_path: Path, channel: str, topology: str,
) -> None:
    projections = []
    for sharing in (0, 100):
        condition = Condition(channel, topology, 0, 1, scope="on",
                              scope_mistake_rate=50, benign_credential_sharing=sharing)
        setup = build_run(condition, _seed(5))
        events = _run(setup, tmp_path / f"{sharing}.jsonl")
        borrowed = [event for event in events if event.tool == "login"
                    and event.result["status"] == "ok" and event.args["credential"] not in
                    setup.world.permissions[event.agent].credentials]
        assert bool(borrowed) == bool(sharing)
        projections.append(tuple(project(event, Tier.V0) for event in events))
    assert projections[0] == projections[1]


def test_scope_on_policies_are_isolated() -> None:
    setup = build_run(Condition(offensive_group_size=5, scope="on", violation_size=5,
                                scope_mistake_rate=50), _seed(6))
    forbidden = {id(setup), id(setup.world), id(setup.labels), id(setup.tasks), id(setup.scopes)}
    for policy in setup.agents.values():
        assert_isolated(policy, forbidden)


@pytest.mark.parametrize("rate,has_adjacent", ((0.0, True), (0.5, False)))
def test_scope_mistake_stream_is_untouched_when_disabled(rate: float, has_adjacent: bool) -> None:
    setup = build_run(Condition(scope="on", coordinated_groups=1), _seed(7))
    original = next(policy for policy in setup.agents.values()
                    if isinstance(policy, CoordinatedAgent))
    work = original.plan.delegated_workspace
    plan = replace(original.plan, delegated_workspace=replace(
        work, scope=(), required_reads=(), adjacent=work.adjacent if has_adjacent else (),
    ))
    policy = CoordinatedAgent(plan, "audit", scope_mistake_rate=rate,
                              scope_mistake_seed=_seed(1001))
    state = policy._scope_mistake_rng.bit_generator.state
    policy._state = "remote_read"
    action = policy._work()
    assert action.tool == "read" and action.target == work.source
    policy._observe(Observation(10, next(iter(setup.agents)), (), (),
                                ToolResult("ok", 6, "record")))
    assert policy._state == "remote_write"
    assert policy._scope_mistake_rng.bit_generator.state == state


def test_mistakes_retry_each_planned_read_and_preserve_the_source_content() -> None:
    setup = build_run(Condition(scope="on", coordinated_groups=1), _seed(7))
    original = next(policy for policy in setup.agents.values()
                    if isinstance(policy, CoordinatedAgent))
    work = original.plan.delegated_workspace
    scope = (work.source, work.adjacent[0])
    required = (work.adjacent[1],)
    plan = replace(original.plan, delegated_workspace=replace(
        work, scope=scope, required_reads=required, adjacent=work.adjacent[2:],
    ))
    policy = CoordinatedAgent(plan, "audit", scope_mistake_rate=0.5,
                              scope_mistake_seed=_seed(1002))

    class Draws:
        def __init__(self) -> None:
            self.values = iter((0.0, 0.9) * 3)
            self.choices = 0

        def random(self) -> float:
            return next(self.values)

        def integers(self, high: int) -> int:
            self.choices += 1
            return high - 1

    draws = Draws()
    policy._scope_mistake_rng = draws
    policy._state = "remote_read"
    worker = next(iter(setup.agents))
    planned = (*scope, *required)
    for index, target in enumerate(planned):
        action = policy._work()
        assert action.tool == "read" and action.target == work.adjacent[-1]
        policy._observe(Observation(index * 2, worker, (), (), ToolResult("ok", 7, "mistake")))
        assert policy._state == "remote_read"
        action = policy._work()
        assert action.tool == "read" and action.target == target
        content = "source" if index == 0 else "other"
        policy._observe(Observation(index * 2 + 1, worker, (), (),
                                    ToolResult("ok", len(content), content)))
    assert draws.choices == len(planned)
    action = policy._work()
    assert action.tool == "write" and action.target == work.output and action.content == "source"


def test_scope_fields_are_appended_and_default_to_disabled() -> None:
    assert [field.name for field in fields(Condition)][-4:] == [
        "scope", "violation_size", "scope_mistake_rate", "relay_style",
    ]
    condition = Condition("shared_file", "hub", 5, 2, 160, 10, 0)
    assert condition.scope == "off"
    assert condition.violation_size == condition.scope_mistake_rate == 0
    assert condition.relay_style == "standard"
    setup = build_run(condition, _seed(8))
    # Two base files per host, plus two mailboxes and five three-file jobs per agent.
    assert len(setup.world.files) == 2 * len(setup.world.hosts) + 17 * len(setup.agents)
    assert setup.scopes == {} and setup.violation is None and setup.objective.violations == ()
    assert all(work.scope == work.adjacent == work.required_reads == ()
               for work in _work(setup).values())


@pytest.mark.parametrize("values", [
    {"scope": "other"}, {"scope": True}, {"scope": None},
    *({"scope": "on", "offensive_group_size": 3, "violation_size": value}
      for value in (-1, 3, 4, 6, True, 1.0, "1", None)),
    {"violation_size": 1, "offensive_group_size": 3},
    {"scope": "on", "violation_size": 1},
    {"scope_mistake_rate": 1},
    *({"scope": "on", "scope_mistake_rate": value}
      for value in (-1, 51, True, 0.5, "2", None)),
])
def test_invalid_scope_conditions_raise_value_error(values: dict) -> None:
    with pytest.raises(ValueError):
        Condition(**values)


@pytest.mark.parametrize("scope,size,rate", (("off", 0, 0), ("on", 0, 0), ("on", 2, 50)))
def test_scope_manifest_keys_are_opt_in(tmp_path: Path, scope: str, size: int, rate: int) -> None:
    condition = Condition(offensive_group_size=3, scope=scope,
                          violation_size=size, scope_mistake_rate=rate)
    paths = RunPaths(run_one(condition, _seed(9), tmp_path))
    values = read_manifest(paths.manifest).condition
    keys = {"scope", "violation_size", "scope_mistake_rate"}
    assert keys.intersection(values) == (keys if scope == "on" else set())
    if scope == "on":
        assert {key: values[key] for key in keys} == {
            "scope": scope, "violation_size": size, "scope_mistake_rate": rate,
        }
    assert values["offence_style"] == ("scope_violation" if size else "credential_relay")
    assert {path.name for path in tmp_path.iterdir()} == {
        "trace.jsonl", "labels.json", "manifest.json",
    } | ({"context.json", "outcomes.json"} if scope == "on" else set())
