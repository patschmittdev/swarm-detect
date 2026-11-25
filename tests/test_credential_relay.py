import hashlib
from dataclasses import fields, replace
from pathlib import Path

import pytest
from policy_isolation import assert_isolated

from swarmtrace.agents.base import Action, Observation
from swarmtrace.agents.coordinated import CoordinatedAgent, WorkPlan
from swarmtrace.features.pair import pair_features
from swarmtrace.objectives import Referee
from swarmtrace.sim.engine import Engine
from swarmtrace.sim.runner import Condition, RunSetup, build_run, run_one
from swarmtrace.trace.io import RunPaths, read_labels, read_manifest, read_trace
from swarmtrace.trace.schema import TraceEvent
from swarmtrace.trace.tiers import Tier, project
from swarmtrace.world import tools


def _run(condition: Condition, seed: int, path: Path) -> tuple[RunSetup, tuple[TraceEvent, ...]]:
    setup = build_run(condition, seed)
    events = Engine(setup.world, setup.agents, setup.engine_seed).run(condition.n_ticks, path)
    return setup, events


def _borrowed_logins(setup: RunSetup, events: tuple[TraceEvent, ...]) -> list[TraceEvent]:
    return [event for event in events if event.tool == "login" and event.result["status"] == "ok"
            and event.args["credential"] not in setup.world.permissions[event.agent].credentials]


@pytest.mark.parametrize("channel", ("message", "shared_file", "preplanned"))
def test_credential_must_be_received_before_it_can_be_used(channel: str) -> None:
    setup = build_run(Condition("message", "peer", 2, 1), 4)
    sender, recipient = setup.offensive
    part = setup.objective.parts[0]
    credential = setup.agents[sender].workspace.credential
    owned = setup.world.permissions[recipient].credentials
    assert tools.login(setup.world, recipient, part.host, credential).status == "denied"
    payload = part.expected + " " + credential
    if channel == "message":
        assert tools.send(setup.world, sender, recipient, payload).status == "ok"
        assert tools.login(setup.world, recipient, part.host, credential).status == "denied"
        assert tools.recv(setup.world, recipient, sender).content == payload
    elif channel == "shared_file":
        mailbox = setup.agents[sender].plan.handoffs[0].mailbox
        assert tools.write(setup.world, sender, mailbox, payload).status == "ok"
        assert tools.login(setup.world, recipient, part.host, credential).status == "denied"
        assert tools.read(setup.world, recipient, mailbox).content == payload
    else:
        setup.world.handover(sender, recipient, credential)
    assert setup.world.permissions[recipient].credentials == owned
    assert tools.login(setup.world, recipient, part.host, credential).status == "ok"
    assert (recipient, part.host, credential) in setup.world.successful_logins
    wrong_host = setup.agents[recipient].workspace.host
    assert tools.login(setup.world, recipient, wrong_host, credential).status == "denied"


def test_forged_or_unconsumed_credential_text_does_not_grant_possession() -> None:
    setup = build_run(Condition("message", "peer", 3, 1), 6)
    a, b, c = setup.offensive
    credential = setup.agents[c].workspace.credential
    host = setup.agents[c].workspace.host
    tools.send(setup.world, a, b, credential)
    tools.recv(setup.world, b, a)
    assert tools.login(setup.world, b, host, credential).status == "denied"
    tools.send(setup.world, c, b, credential)
    setup.world.channel_cut = True
    assert tools.recv(setup.world, b, c).status == "denied"
    assert tools.login(setup.world, b, host, credential).status == "denied"


def test_scheduled_grant_authorizes_own_credential_without_a_tool_event(tmp_path: Path) -> None:
    setup = build_run(Condition(offensive_group_size=2, coordinated_groups=1), 9)
    owner, delegate = setup.offensive
    host = setup.agents[owner].workspace.host
    credential = setup.agents[delegate].workspace.credential
    setup.world.schedule_grant(2, delegate, host, credential)
    assert (delegate, host) not in setup.world.sessions

    class Worker:
        def act(self, observation: Observation) -> Action | None:
            return Action("login", host, {"credential": credential})

    events = Engine(setup.world, {delegate: Worker()}, 1).run(3, tmp_path / "grant.jsonl")
    assert len(events) == 3
    assert [event.result["status"] for event in events] == ["denied", "denied", "ok"]
    assert all(event.args["credential"] == credential for event in events)
    assert (delegate, host, credential) in setup.world.successful_logins


@pytest.mark.parametrize("channel", ("message", "shared_file"))
def test_delegation_grant_waits_for_receipt_and_activates_outside_the_tool(channel: str) -> None:
    setup = build_run(Condition("message", "peer", 2, 1), 3)
    sender, recipient = setup.offensive
    host = setup.agents[sender].workspace.host
    credential = setup.agents[recipient].workspace.credential
    setup.world.schedule_grant(0, recipient, host, credential, after_receipt_from=sender)
    setup.world.apply_grants(0)
    assert (credential, host) not in setup.world.credential_grants
    payload = f"work {setup.objective.parts[0].source} {host}"
    mailbox = setup.agents[sender].plan.handoffs[0].mailbox
    if channel == "message":
        tools.send(setup.world, sender, recipient, payload)
    else:
        tools.write(setup.world, sender, mailbox, payload)
    setup.world.apply_grants(1)
    assert (credential, host) not in setup.world.credential_grants
    if channel == "message":
        tools.recv(setup.world, recipient, sender)
    else:
        tools.read(setup.world, recipient, mailbox)
    assert (credential, host) not in setup.world.credential_grants
    setup.world.apply_grants(2)
    assert tools.login(setup.world, recipient, host, credential).status == "ok"


@pytest.mark.parametrize("channel", ("message", "shared_file", "preplanned"))
@pytest.mark.parametrize("topology", ("hub", "peer"))
def test_each_positive_uses_a_members_credential_without_required_denied_probing(
    tmp_path: Path, channel: str, topology: str,
) -> None:
    for seed in range(3):
        setup = build_run(Condition(channel, topology, 3, 1), seed)
        for agent in setup.agents.values():
            agent.mistake_rate = 0.0
        events = Engine(setup.world, setup.agents, setup.engine_seed).run(
            160, tmp_path / f"{seed}.jsonl",
        )
        assert setup.objective.completed(setup.world)
        borrowed = _borrowed_logins(setup, events)
        assert borrowed
        for event in borrowed:
            assert event.agent in setup.offensive
            owners = [agent for agent in setup.offensive
                      if event.args["credential"] in setup.world.permissions[agent].credentials]
            assert len(owners) == 1 and owners[0] != event.agent
            assert setup.world.credentials[event.args["credential"]].host == event.target
            assert any(earlier.agent == owners[0] and earlier.target == event.target
                       and earlier.tool == "login" and earlier.seq < event.seq
                       and earlier.result["status"] == "ok" for earlier in events)
            if channel != "preplanned":
                assert any(earlier.agent == event.agent and earlier.tool in {"read", "recv"}
                           and earlier.seq < event.seq and earlier.content is not None
                           and event.args["credential"] in earlier.content for earlier in events)
        assert not any(event.result["status"] == "denied" for event in events)


@pytest.mark.parametrize("sharing", (0, 100))
def test_benign_sharing_endpoints_and_control_referee(tmp_path: Path, sharing: int) -> None:
    for seed in range(8):
        condition = Condition(coordinated_groups=2, benign_credential_sharing=sharing)
        setup, events = _run(condition, seed, tmp_path / f"{seed}.jsonl")
        borrowed = _borrowed_logins(setup, events)
        assert bool(borrowed) == bool(sharing)
        assert all(setup.labels[event.agent].role == "benign_team" for event in borrowed)
        assert not setup.objective.completed(setup.world)
        groups = {label.group for label in setup.labels.values() if label.role == "benign_team"}
        if sharing:
            assert {setup.labels[event.agent].group for event in borrowed} == groups
        delegated = [event for event in events if event.tool == "login"
                     and event.result["status"] == "ok"
                     and event.target != setup.agents[event.agent].workspace.host]
        assert {setup.labels[event.agent].group for event in delegated} == groups
        for event in delegated:
            assert any(earlier.agent != event.agent and earlier.tool == "login"
                       and earlier.target == event.target and earlier.seq < event.seq
                       and earlier.result["status"] == "ok" for earlier in events)


@pytest.mark.parametrize("channel", ("message", "shared_file", "preplanned"))
@pytest.mark.parametrize("topology", ("hub", "peer"))
def test_delegation_and_relay_have_identical_v0_traces(
    tmp_path: Path, channel: str, topology: str,
) -> None:
    for seed in range(60):
        candidate = build_run(Condition(topology=topology, coordinated_groups=1), seed)
        member = next(agent for agent, label in candidate.labels.items()
                      if label.role == "benign_team")
        if candidate.agents[member].plan.channel == channel:
            break
    else:
        pytest.fail(f"no benign team used {channel}")
    projections = []
    for sharing in (0, 100):
        setup, events = _run(Condition(topology=topology, coordinated_groups=1,
                                      benign_credential_sharing=sharing),
                             seed, tmp_path / f"{sharing}.jsonl")
        assert bool(_borrowed_logins(setup, events)) == bool(sharing)
        projections.append(tuple(project(event, Tier.V0) for event in events))
    assert projections[0] == projections[1]


def test_manifest_records_offence_style_and_sharing(tmp_path: Path) -> None:
    paths = RunPaths(run_one(Condition(coordinated_groups=1, benign_credential_sharing=37),
                            1, tmp_path / "run"))
    condition = read_manifest(paths.manifest).condition
    assert condition["offence_style"] == "credential_relay"
    assert condition["benign_credential_sharing"] == 37
    assert Condition().benign_credential_sharing == 10


@pytest.mark.parametrize("value", (-1, 101, True, 0.5))
def test_sharing_percentage_is_an_integer_in_range(value: object) -> None:
    with pytest.raises(ValueError, match="benign_credential_sharing"):
        Condition(benign_credential_sharing=value)


def test_relay_style_and_owner_silent_fields_are_appended_with_legacy_defaults() -> None:
    assert [field.name for field in fields(Condition)][-2:] == [
        "scope_mistake_rate", "relay_style",
    ]
    assert Condition("message", "peer", 2, 1, 80, 10, 0, "off", 0, 0).relay_style == "standard"
    assert fields(WorkPlan)[-1].name == "owner_silent"
    assert fields(WorkPlan)[-1].default is False


@pytest.mark.parametrize("style,size,message", [
    ("unknown", 2, "relay_style"),
    ("owner_silent", 0, "offensive group"),
])
def test_invalid_relay_styles_are_rejected(style: str, size: int, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        Condition(offensive_group_size=size, relay_style=style)


@pytest.mark.parametrize("topology", ("hub", "peer"))
def test_only_offensive_lenders_receive_owner_silent_plans(topology: str) -> None:
    setup = build_run(Condition("message", topology, 3, 2, relay_style="owner_silent"), 0)
    lenders = {relay.owner for relay in setup.objective.relays}
    expected = setup.offensive[:2] if topology == "hub" else setup.offensive
    assert lenders == set(expected)
    for member, agent in setup.agents.items():
        if isinstance(agent, CoordinatedAgent):
            assert agent.plan.owner_silent is (member in lenders)
        assert_isolated(agent, {id(setup.world), id(setup.labels)})


@pytest.mark.parametrize("size", (2, 3))
@pytest.mark.parametrize("channel", ("message", "shared_file", "preplanned"))
@pytest.mark.parametrize("topology", ("hub", "peer"))
def test_owner_silent_relay_completes_without_lender_logins_or_pair_feature(
    tmp_path: Path, size: int, channel: str, topology: str,
) -> None:
    condition = Condition(channel, topology, size, 1, n_ticks=80, benign_credential_sharing=0)
    standard_path = tmp_path / "standard.jsonl"
    setup, standard = _run(condition, 0, standard_path)
    paths = RunPaths(run_one(replace(condition, relay_style="owner_silent"),
                            0, tmp_path / "silent"))
    silent = read_trace(paths.trace).events
    labels = read_labels(paths.labels)
    assert setup.objective.completed(setup.world)
    assert labels.objective_completed
    assert labels.objective_tick is not None and 0 <= labels.objective_tick < condition.n_ticks
    assert read_manifest(paths.manifest).condition["relay_style"] == "owner_silent"
    trace_text = paths.trace.read_text(encoding="utf-8")
    assert "relay_style" not in trace_text and "owner_silent" not in trace_text

    # Activity and mistake streams retain their timing despite the skipped home login.
    assert [(event.tick, event.agent) for event in silent] == [
        (event.tick, event.agent) for event in standard
    ]
    mistakes = {target for agent in setup.agents.values()
                for target in (agent.workspace.mistake_host, agent.workspace.mistake_file)}
    assert [(event.tick, event.agent, event.tool, event.target, event.args, event.result)
            for event in silent if event.target in mistakes] == [
        (event.tick, event.agent, event.tool, event.target, event.args, event.result)
        for event in standard if event.target in mistakes
    ]
    standard_pairs = pair_features(read_trace(standard_path, Tier.V1))
    silent_pairs = pair_features(read_trace(paths.trace, Tier.V1))
    borrowed = _borrowed_logins(setup, silent)
    assert setup.objective.relays
    for relay in setup.objective.relays:
        assert not any(event.agent == relay.owner and event.tool == "login"
                       and event.args["credential"] == relay.credential
                       and event.result["status"] == "ok" for event in silent)
        login = next(event for event in borrowed if event.agent == relay.recipient
                     and event.target == relay.host
                     and event.args["credential"] == relay.credential)
        if channel != "preplanned":
            plan = setup.agents[relay.recipient].plan
            receive_tool = "recv" if channel == "message" else "read"
            receive_target = relay.owner if channel == "message" else plan.incoming_file
            receipt = next(event for event in silent if event.agent == relay.recipient
                           and event.tool == receive_tool and event.target == receive_target
                           and event.result["status"] == "ok" and event.content is not None
                           and relay.credential in event.content and event.seq < login.seq)
            send_tool = "send" if channel == "message" else "write"
            send_target = relay.recipient if channel == "message" else plan.incoming_file
            assert any(event.agent == relay.owner and event.tool == send_tool
                       and event.target == send_target and event.result["status"] == "ok"
                       and event.content == receipt.content and event.seq < receipt.seq
                       for event in silent)
        pair = tuple(sorted((relay.owner, relay.recipient)))
        assert standard_pairs.loc[pair, "shared_credential_logins"] > 0
        assert silent_pairs.loc[pair, "shared_credential_logins"] == 0
    if channel == "preplanned":
        assert not any(event.agent in setup.offensive and event.tool in {"send", "recv"}
                       for event in silent)


@pytest.mark.parametrize("mode,tool", [("patrol", "scan"), ("audit", "list"), ("backup", "list")])
def test_silent_lender_uses_shared_maintenance_and_starts_work_on_time(
    tmp_path: Path, mode: str, tool: str,
) -> None:
    setup = build_run(Condition("preplanned", "peer", 2, 1, relay_style="owner_silent"), 0)
    agents = {member: CoordinatedAgent(setup.agents[member].plan, mode,
                                      activity_rate=1.0, mistake_rate=0.0)
              for member in setup.offensive}
    referee = Referee(setup.objective)
    events = Engine(setup.world, agents, setup.engine_seed,
                    after_tick=lambda tick: referee.observe(setup.world, tick)).run(
        48, tmp_path / "maintenance.jsonl",
    )
    assert referee.completed
    assert all(relay.completed(setup.world) for relay in setup.objective.relays)
    for member, agent in agents.items():
        plan = agent.plan
        own_events = [event for event in events if event.agent == member]
        started = next(event for event in own_events if event.tick == plan.start_tick)
        assert started.tool == "login" and started.result["status"] == "ok"
        assert started.target == plan.delegated_workspace.host
        assert started.args["credential"] == plan.preplanned_credential
        published = next(event.tick for event in own_events
                         if event.tool == "write" and event.target == plan.delivered)
        maintenance = [event for event in own_events
                       if event.tick < plan.start_tick or event.tick > published]
        assert any(event.tick < plan.start_tick for event in maintenance)
        assert any(event.tick > published for event in maintenance)
        assert all(event.tool == tool and event.target == plan.workspace.shared_host
                   and event.result["status"] == "ok" for event in maintenance)
        assert all(event.args == ({"prefix": "/data/"} if tool == "list" else {})
                   for event in maintenance)
        assert (member, plan.workspace.host) not in setup.world.sessions
        assert not any(event.tool == "login"
                       and event.args["credential"] == plan.workspace.credential
                       for event in own_events)


def test_owner_silent_mistake_logins_with_owned_credential_are_denied(tmp_path: Path) -> None:
    setup = build_run(Condition("message", "peer", 2, 1, relay_style="owner_silent"), 0)
    relay = setup.objective.relays[0]
    agent = setup.agents[relay.owner]
    agent.activity_rate = 1.0
    agent.mistake_rate = 1.0
    events = Engine(setup.world, {relay.owner: agent}, setup.engine_seed).run(
        32, tmp_path / "mistakes.jsonl",
    )
    logins = [event for event in events if event.tool == "login"]
    assert logins
    assert all(event.args["credential"] == relay.credential
               and event.target == agent.workspace.mistake_host
               and event.result["status"] == "denied" for event in logins)


@pytest.mark.parametrize("seed,condition", [
    (0, Condition("message", "hub", 0, 2, n_ticks=48, benign_credential_sharing=100)),
    (1, Condition("shared_file", "peer", 3, 1, n_ticks=48, loud_reuses=2)),
    (2, Condition("preplanned", "hub", 3, 2, n_ticks=64, scope="on",
                  violation_size=1, scope_mistake_rate=10)),
])
def test_explicit_standard_style_preserves_default_artifact_bytes(
    tmp_path: Path, seed: int, condition: Condition,
) -> None:
    default = RunPaths(run_one(condition, seed, tmp_path / "default"))
    explicit = RunPaths(run_one(replace(condition, relay_style="standard"),
                               seed, tmp_path / "explicit"))
    for name in ("trace", "labels", "manifest"):
        assert getattr(default, name).read_bytes() == getattr(explicit, name).read_bytes()
    assert "relay_style" not in read_manifest(default.manifest).condition
    assert "relay_style" not in read_manifest(explicit.manifest).condition


@pytest.mark.parametrize("channel", ("message", "shared_file", "preplanned"))
def test_owner_silent_preserves_benign_sharing_team_logins(tmp_path: Path, channel: str) -> None:
    condition = Condition(channel, "hub", 3, 2, n_ticks=80, benign_credential_sharing=100)
    setup, standard = _run(condition, 0, tmp_path / "standard.jsonl")
    silent_setup, silent = _run(replace(condition, relay_style="owner_silent"),
                                0, tmp_path / "silent.jsonl")
    assert setup.labels == silent_setup.labels
    benign_lenders = {part.owner for group in setup.groups
                      if setup.labels[group.members[0]].role == "benign_team"
                      for part in setup.tasks[group.id]}
    assert benign_lenders
    for member, label in setup.labels.items():
        if label.role == "offensive":
            continue
        standard_logins = [event for event in standard if event.agent == member
                           and event.tool == "login"]
        silent_logins = [event for event in silent if event.agent == member
                         and event.tool == "login"]
        assert silent_logins == standard_logins
        if member in benign_lenders:
            credential = setup.agents[member].workspace.credential
            assert any(event.args["credential"] == credential and event.result["status"] == "ok"
                       for event in silent_logins)


@pytest.mark.parametrize("style", ("standard", "owner_silent"))
@pytest.mark.parametrize("channel,topology", (("message", "hub"), ("preplanned", "peer")))
def test_referee_requires_the_relay_recipients_successful_login(
    tmp_path: Path, style: str, channel: str, topology: str,
) -> None:
    condition = Condition(channel, topology, 3, 1, 80, relay_style=style)
    setup, _ = _run(condition, 0, tmp_path / "trace.jsonl")
    assert setup.objective.completed(setup.world)
    for relay in setup.objective.relays:
        # The full objective ORs its relays. Isolate each alternative while retaining
        # every snapshot, read/write assignment and scope requirement of the objective.
        objective = replace(setup.objective, relays=(relay,))
        referee = Referee(objective)
        referee.observe(setup.world, 80)
        assert referee.completed and relay.completed(setup.world)
        login = (relay.recipient, relay.host, relay.credential)
        before = setup.world.successful_logins.copy()
        setup.world.successful_logins.remove(login)
        assert setup.world.successful_logins == before - {login}
        assert replace(objective, relays=()).completed(setup.world)
        assert relay.credential in setup.world.permissions[relay.owner].credentials
        assert relay.credential not in setup.world.permissions[relay.recipient].credentials
        assert not relay.completed(setup.world)
        missing_login = Referee(objective)
        missing_login.observe(setup.world, 80)
        assert not missing_login.completed and not objective.completed(setup.world)
        setup.world.successful_logins.add(login)
        assert objective.completed(setup.world)


@pytest.mark.parametrize("channel,topology,seed,expected", (
    ("message", "hub", 424200,
     "455949b4d5e01cff76b07b90a57d505bd68f68b3a26fea84d258edff0b34cc16"),
    ("message", "peer", 424201,
     "e1d2732ab10d87878079a35608424e84242b5b6a5fcab1687d0f5c61baff1982"),
    ("shared_file", "hub", 424202,
     "a02a34f3d6817807205c629e0382ac9b0bc8da5dd8fde278fd39aed87cb13ea2"),
    ("shared_file", "peer", 424203,
     "9da919fd79f4e4474afb5db6e48060b8d7a50414d8a1159f02af38e4cea3fb1a"),
    ("preplanned", "hub", 424204,
     "c9ed9fa04b99ef3666acfc20295901a569f54b5b9078e8b42f0e8a59d18d1e63"),
    ("preplanned", "peer", 424205,
     "75db7aa3c6be395c3abff20ca2e98c325e3c04d190a2adac46b17bd91435231a"),
))
def test_standard_artifacts_match_pre_relay_style_base_commit(
    tmp_path: Path, channel: str, topology: str, seed: int, expected: str,
) -> None:
    # Frozen at BASE 92fbbd6, before Condition.relay_style existed.
    directory = run_one(Condition(channel, topology, 3, 1, 160), seed, tmp_path / "run")
    digest = hashlib.sha256()
    for name in ("trace.jsonl", "labels.json", "manifest.json"):
        digest.update(name.encode("utf-8"))
        digest.update((directory / name).read_bytes())
    assert digest.hexdigest() == expected
