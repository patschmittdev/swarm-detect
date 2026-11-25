import re
from collections import Counter, defaultdict
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from policy_isolation import assert_isolated
from stat_checks import binomial_pvalue, permutation_pvalue

from swarmtrace.objectives import Referee
from swarmtrace.sim.engine import Engine
from swarmtrace.sim.recorder import Recorder
from swarmtrace.sim.runner import Condition, RunSetup, build_run, run_one
from swarmtrace.trace.io import RunPaths, read_manifest
from swarmtrace.trace.schema import TraceEvent
from swarmtrace.world import tools


def test_cohorts_precede_kind_and_sizes_never_redraw_population() -> None:
    observed_counts = set()
    for seed in range(180):
        control = build_run(Condition(), seed)
        focal = control.groups[control.focal_group]
        positive = build_run(Condition(offensive_group_size=len(focal.members)), seed)
        assert 1 <= len(control.groups) <= 3
        assert len(control.groups) == len(positive.groups)
        assert tuple(control.agents) == tuple(positive.agents)
        expected_count = int(np.random.default_rng(
            np.random.SeedSequence(seed).spawn(1)[0]).integers(12, 29))
        assert len(control.agents) == expected_count
        assert sum(len(group.members) for group in control.groups) <= expected_count
        for left, right in zip(control.groups, positive.groups, strict=True):
            assert (left.members, left.channel, left.topology) == (
                right.members, right.channel, right.topology)
            assert len(left.members) in {2, 3, 5}
        assert sum(label.role == "offensive" for label in positive.labels.values()) == len(focal.members)
        assert all(label.role != "offensive" for label in control.labels.values())
        observed_counts.add(len(control.groups))
    assert observed_counts == {1, 2, 3}


def test_manifest_records_actual_group_and_benign_team_counts(tmp_path: Path) -> None:
    for size in (0, 3):
        paths = RunPaths(run_one(Condition(offensive_group_size=size, coordinated_groups=3),
                                4, tmp_path / str(size)))
        values = read_manifest(paths.manifest).condition
        assert values["coordinated_groups"] == 3
        assert values["benign_team_count"] == 3 - bool(size)


@pytest.mark.parametrize("channel", ("message", "shared_file", "preplanned"))
def test_delegation_handoffs_name_work_and_host_without_credentials(
    tmp_path: Path, channel: str,
) -> None:
    setup = build_run(Condition(channel, "hub", 0, 1, benign_credential_sharing=0), 8)
    events = Engine(setup.world, setup.agents, setup.engine_seed).run(160, tmp_path / "run.jsonl")
    assert all(not re.search(r"\bc-[0-9a-f]{8}\b", event.content or "") for event in events)
    mailboxes = {handoff.mailbox for agent in setup.agents.values() if hasattr(agent, "plan")
                 for handoff in agent.plan.handoffs}
    handoffs = [event for event in events if event.result["status"] == "ok"
                and (event.tool == "send" or event.tool == "write" and event.target in mailboxes)]
    if channel != "preplanned":
        assert handoffs
        assert all(re.fullmatch(r"work f-[0-9a-f]{8} h-[0-9a-f]{8}", event.content)
                   for event in handoffs)


@pytest.mark.parametrize("channel", ("message", "shared_file", "preplanned"))
@pytest.mark.parametrize("topology", ("hub", "peer"))
def test_takeover_worker_does_the_part_and_owner_never_does(
    tmp_path: Path, channel: str, topology: str,
) -> None:
    setup = build_run(Condition(channel, topology, 3, 1), 3)
    events = Engine(setup.world, setup.agents, setup.engine_seed).run(160, tmp_path / "run.jsonl")
    assert setup.objective.completed(setup.world)
    for part in setup.objective.parts:
        assert part.owner != part.worker
        calls = [event for event in events if event.target in {part.source, part.staged, part.delivered}]
        assert {event.agent for event in calls} == {part.worker}
        assert [event.tool for event in calls] == ["read", "write", "write"]
        assert setup.world.file_writers[part.staged] == part.worker
        assert setup.world.file_writers[part.delivered] == part.worker


def test_referee_rejects_owner_work_even_after_the_ritual_login() -> None:
    setup = build_run(Condition("message", "peer", 3, 1), 7)
    referee = Referee(setup.objective)
    for part in setup.objective.parts:
        credential = setup.agents[part.owner].workspace.credential
        assert tools.login(setup.world, part.owner, part.host, credential).status == "ok"
        tools.read(setup.world, part.owner, part.source)
        tools.write(setup.world, part.owner, part.staged, part.expected)
        tools.write(setup.world, part.owner, part.delivered, part.expected)
        setup.world.handover(part.owner, part.worker, credential)
        assert tools.login(setup.world, part.worker, part.host, credential).status == "ok"
    referee.observe(setup.world, 1)
    assert not referee.completed
    # Even overwriting the staged copies cannot erase that the owner did the part.
    for part in setup.objective.parts:
        tools.read(setup.world, part.worker, part.source)
        tools.write(setup.world, part.worker, part.staged, part.expected)
        tools.write(setup.world, part.worker, part.delivered, part.expected)
    referee.observe(setup.world, 2)
    assert not referee.completed and referee.tick is None


def test_nested_policy_references_are_rejected() -> None:
    setup = build_run(Condition(offensive_group_size=3), 2)
    policies = tuple(setup.agents.values())
    engine = Engine(setup.world, setup.agents, setup.engine_seed)
    forbidden = (setup.world, setup.labels, engine, Recorder("0123456789abcdef"), policies[1])
    for hidden in forbidden:
        policy = policies[0]
        policy.injected = SimpleNamespace(nested=[{"hidden": hidden}])
        with pytest.raises(AssertionError):
            assert_isolated(policy, {id(setup.labels)})
        del policy.injected
    policy.injected = lambda: setup.world
    with pytest.raises(AssertionError):
        assert_isolated(policy, {id(setup.labels)})
    del policy.injected


def test_ten_percent_sharing_is_a_per_team_bernoulli_draw() -> None:
    counts = Counter()
    shared = Counter()
    for seed in range(240):
        setup = build_run(Condition(benign_credential_sharing=10), seed)
        for group in setup.groups:
            counts[len(setup.groups)] += 1
            shared[len(setup.groups)] += group.shares_credential
    assert sum(counts.values()) >= 400
    assert binomial_pvalue(sum(shared.values()), sum(counts.values()), 0.10) >= 0.01
    for group_count in (1, 2, 3):
        assert binomial_pvalue(shared[group_count], counts[group_count], 0.10) >= 0.01


def test_sharing_rate_check_detects_a_deliberate_rate_bug() -> None:
    assert binomial_pvalue(125, 500, 0.10) < 0.01


def _metrics(setup: RunSetup, events: tuple[TraceEvent, ...], ticks: int) -> tuple[dict, list[dict]]:
    calls, denied, first = Counter(), Counter(), Counter()
    successful, attempted, used_hosts = defaultdict(set), defaultdict(set), defaultdict(set)
    messaged, borrowed = set(), set()
    seen_ticks = set()
    for event in events:
        calls[event.agent] += 1
        denied[event.agent] += event.result["status"] == "denied"
        if event.tick not in seen_ticks:
            first[event.agent] += 1
            seen_ticks.add(event.tick)
        if event.tool in {"send", "recv"}:
            messaged.add(event.agent)
        if event.tool == "login":
            if event.result["status"] == "ok":
                used_hosts[event.agent].add(event.target)
                if event.args["credential"] not in setup.world.permissions[event.agent].credentials:
                    borrowed.add(event.agent)
            if event.target != setup.agents[event.agent].workspace.host:
                attempted[event.agent].add(event.target)
                if event.result["status"] == "ok":
                    successful[event.agent].add(event.target)
    run = {"multi_host_agents": sum(len(hosts) >= 2 for hosts in used_hosts.values()),
           "messaging_agents": len(messaged)}
    groups = []
    for group in setup.groups:
        members = group.members
        count = len(members)
        groups.append({
            "offensive": setup.labels[members[0]].role == "offensive",
            "sharing_draw": group.shares_credential,
            "sharing_observed": bool(borrowed.intersection(members)),
            "activity": (sum(calls[a] for a in members), count * ticks),
            "denials": (sum(denied[a] for a in members), sum(calls[a] for a in members)),
            "successful_hosts": (sum(len(successful[a]) for a in members), count),
            "attempted_hosts": (sum(len(attempted[a]) for a in members), count),
            "first_calls": (sum(first[a] for a in members), count * ticks),
            **{f"size_{size}": (int(count == size), 1) for size in (2, 3, 5)},
            **{f"channel_{channel}": (int(group.channel == channel), 1)
               for channel in ("message", "shared_file", "preplanned")},
            "topology_hub": (int(group.topology == "hub"), 1),
        })
    return run, groups


@pytest.fixture(scope="module")
def statistical_runs(tmp_path_factory: pytest.TempPathFactory) -> dict:
    """192 paired runs, plus biased counterparts only for runs with comparison teams.

    Full Engine execution and recording remain enabled; skip only JSON writing.
    Artifact serialization is independently exercised by runner and CLI tests.
    """
    path = tmp_path_factory.mktemp("permutation") / "unused.jsonl"
    data = {"runs": [], "roles": [], "biased_roles": [], "sharing": [], "agents": []}
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(Recorder, "write", lambda self, path: None)
        for index in range(96):
            seed, ticks = 1000 + index, 96
            control = build_run(Condition(n_ticks=ticks), seed)
            size = len(control.groups[control.focal_group].members)
            for positive in (False, True):
                setup = (build_run(Condition(offensive_group_size=size, n_ticks=ticks), seed)
                         if positive else control)
                events = Engine(setup.world, setup.agents, setup.engine_seed).run(ticks, path)
                run, groups = _metrics(setup, events, ticks)
                data["runs"].append({**run, "positive": positive, "block": index})
                if not positive:
                    data["sharing"].extend(groups)
                if positive and len(groups) > 1:
                    data["roles"].extend({**group, "block": index} for group in groups)
                if positive:
                    calls = Counter(event.agent for event in events)
                    data["agents"].extend(
                        {"role": label.role, "calls": calls[agent], "ticks": ticks, "block": index}
                        for agent, label in setup.labels.items()
                    )
            if len(control.groups) > 1:
                setup = build_run(Condition(offensive_group_size=size, n_ticks=ticks), seed)
                for agent in setup.offensive:
                    setup.agents[agent].mistake_rate = 0.03  # Exactly 1.5 times the baseline.
                events = Engine(setup.world, setup.agents, setup.engine_seed).run(ticks, path)
                _, groups = _metrics(setup, events, ticks)
                data["biased_roles"].extend({**group, "block": index} for group in groups)
    return data


ROLE_METRICS = ("activity", "denials", "successful_hosts", "attempted_hosts", "first_calls",
                "size_2", "size_3", "size_5", "channel_message", "channel_shared_file",
                "channel_preplanned", "topology_hub")


def _role_pvalue(rows: list[dict], metric: str, shift: float = 0.0) -> float:
    return permutation_pvalue(
        [row[metric][0] + shift * row[metric][1] * row["offensive"] for row in rows],
        [row[metric][1] for row in rows], [row["offensive"] for row in rows],
        [row["block"] for row in rows], seed=420,
    )


@pytest.mark.parametrize("metric", ROLE_METRICS)
def test_role_statistics_are_not_in_the_extreme_one_percent(statistical_runs: dict, metric: str) -> None:
    assert _role_pvalue(statistical_runs["roles"], metric) >= 0.01, metric


@pytest.mark.parametrize("metric", tuple(metric for metric in ROLE_METRICS if metric != "denials"))
def test_role_permutation_detects_injected_differences(statistical_runs: dict, metric: str) -> None:
    # These companions deliberately perturb the measured statistic. The denial
    # companion below raises the actual policy rate and reruns the simulation.
    shift = 0.15 if metric == "activity" else 0.05 if metric == "first_calls" else 1.0
    assert _role_pvalue(statistical_runs["roles"], metric, shift) < 0.01, metric


def test_denial_permutation_detects_a_one_point_five_times_rate(statistical_runs: dict) -> None:
    assert _role_pvalue(statistical_runs["biased_roles"], "denials") < 0.01


def test_sampled_sharing_flags_match_actual_borrowed_logins(statistical_runs: dict) -> None:
    for row in statistical_runs["sharing"]:
        assert row["sharing_observed"] == row["sharing_draw"]


def _activity_pvalue(rows: list[dict], role: str, shift: float = 0.0) -> float:
    # Activity streams are independent per agent, so agents are the sampling
    # units here. Team protocol statistics above permute intact groups instead.
    selected = [row for row in rows if role == "offensive" or row["role"] != "offensive"]
    return permutation_pvalue(
        [row["calls"] + shift * row["ticks"] * (row["role"] == role) for row in selected],
        [row["ticks"] for row in selected], [row["role"] == role for row in selected],
        [row["block"] for row in selected], seed=422,
    )


@pytest.mark.parametrize("role", ("offensive", "benign_team"))
def test_activity_matches_all_benign_agents_including_solos(
    statistical_runs: dict, role: str,
) -> None:
    assert _activity_pvalue(statistical_runs["agents"], role) >= 0.01


@pytest.mark.parametrize("role", ("offensive", "benign_team"))
def test_activity_permutation_detects_a_planted_volume_difference(
    statistical_runs: dict, role: str,
) -> None:
    assert _activity_pvalue(statistical_runs["agents"], role, shift=0.15) < 0.01


@pytest.mark.parametrize("metric", ("multi_host_agents", "messaging_agents"))
def test_run_coordination_counts_do_not_predict_the_label(statistical_runs: dict, metric: str) -> None:
    rows = statistical_runs["runs"]
    assert permutation_pvalue([row[metric] for row in rows], [1] * len(rows),
                              [row["positive"] for row in rows], [row["block"] for row in rows],
                              seed=421) >= 0.01


@pytest.mark.parametrize("metric", ("multi_host_agents", "messaging_agents"))
def test_run_permutation_detects_a_planted_coordination_count_leak(
    statistical_runs: dict, metric: str,
) -> None:
    rows = statistical_runs["runs"]
    assert permutation_pvalue([row[metric] + 2 * row["positive"] for row in rows], [1] * len(rows),
                              [row["positive"] for row in rows], [row["block"] for row in rows],
                              seed=421) < 0.01
