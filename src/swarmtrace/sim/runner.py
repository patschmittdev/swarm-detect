import hashlib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from swarmtrace.agents.base import Agent
from swarmtrace.agents.benign import AuditAgent, BackupAgent, PatrolAgent, Workspace
from swarmtrace.agents.coordinated import (
    BenignTeamAgent,
    CoordinatedAgent,
    DelegatedWork,
    Handoff,
    OffensiveAgent,
    WorkPlan,
)
from swarmtrace.objectives import (
    Referee,
    RelayRequirement,
    ScopeRequirement,
    SnapshotObjective,
    SnapshotPart,
)
from swarmtrace.trace.authorization import ReadGrant
from swarmtrace.trace.context import Context, ContextLevel, HandoffScope
from swarmtrace.trace.interventions import KINDS, Controller
from swarmtrace.trace.io import AgentLabel, Labels, Manifest, RunPaths
from swarmtrace.trace.schema import SCHEMA_VERSION, TraceEvent
from swarmtrace.trace.tiers import project
from swarmtrace.world import File, World, generate_world

from .engine import Engine, Intervention
from .recorder import (
    write_metadata,
    write_run_authorization,
    write_run_extras,
    write_run_interventions,
)

CHANNELS = ("message", "shared_file", "preplanned")
TOPOLOGIES = ("hub", "peer")
GROUP_SIZES = (0, 2, 3, 5)
COORDINATED_GROUP_COUNTS = (1, 2, 3)
RELAY_STYLES = ("standard", "owner_silent")


@dataclass(frozen=True)
class Condition:
    """Optional group factors are drawn uniformly when not fixed by a sweep cell."""

    channel: str | None = None
    topology: str | None = None
    offensive_group_size: int = 0
    coordinated_groups: int | None = None
    n_ticks: int = 160
    benign_credential_sharing: int = 10
    loud_reuses: int = 0
    scope: str = "off"
    violation_size: int = 0
    scope_mistake_rate: int = 0
    relay_style: str = "standard"

    def __post_init__(self) -> None:
        if self.channel is not None and self.channel not in CHANNELS:
            raise ValueError(f"channel must be one of {CHANNELS}")
        if self.topology is not None and self.topology not in TOPOLOGIES:
            raise ValueError(f"topology must be one of {TOPOLOGIES}")
        if (type(self.offensive_group_size) is not int
                or self.offensive_group_size not in GROUP_SIZES):
            raise ValueError(f"offensive_group_size must be one of {GROUP_SIZES}")
        if self.coordinated_groups is not None and (
            type(self.coordinated_groups) is not int
            or self.coordinated_groups not in COORDINATED_GROUP_COUNTS
        ):
            raise ValueError(f"coordinated_groups must be one of {COORDINATED_GROUP_COUNTS}")
        if type(self.n_ticks) is not int or self.n_ticks < 1:
            raise ValueError("n_ticks must be a positive integer")
        if (type(self.benign_credential_sharing) is not int
                or not 0 <= self.benign_credential_sharing <= 100):
            raise ValueError("benign_credential_sharing must be an integer from 0 to 100")
        if type(self.loud_reuses) is not int or self.loud_reuses < 0:
            raise ValueError("loud_reuses must be a non-negative integer")
        if self.loud_reuses and not self.offensive_group_size:
            raise ValueError("loud_reuses requires an offensive group")
        if self.scope not in ("off", "on"):
            raise ValueError("scope must be off or on")
        if type(self.violation_size) is not int or self.violation_size not in (0, 1, 2, 5):
            raise ValueError("violation_size must be one of (0, 1, 2, 5)")
        if type(self.scope_mistake_rate) is not int or not 0 <= self.scope_mistake_rate <= 50:
            raise ValueError("scope_mistake_rate must be an integer from 0 to 50")
        if self.violation_size and (self.scope != "on" or not self.offensive_group_size):
            raise ValueError("violation_size requires scope on and an offensive group")
        if self.scope_mistake_rate and self.scope != "on":
            raise ValueError("scope_mistake_rate requires scope on")
        if self.relay_style not in RELAY_STYLES:
            raise ValueError(f"relay_style must be one of {RELAY_STYLES}")
        if self.relay_style == "owner_silent" and not self.offensive_group_size:
            raise ValueError("owner_silent relay_style requires an offensive group")


@dataclass(frozen=True)
class GroupAssignment:
    """Assembly metadata, never exposed to policies or serialized into the trace."""

    id: str
    members: tuple[str, ...]
    channel: str
    topology: str
    shares_credential: bool


@dataclass
class RunSetup:
    """Label-side assembly; none of these live objects is handed to a policy."""

    world: World
    agents: dict[str, Agent]
    labels: dict[str, AgentLabel]
    offensive: tuple[str, ...]
    objective: SnapshotObjective
    engine_seed: int
    groups: tuple[GroupAssignment, ...]
    focal_group: int
    tasks: dict[str, tuple[SnapshotPart, ...]] = field(default_factory=dict)
    # Keys are the parts' source file ids, which also identify tasks in handoffs.
    scopes: dict[str, tuple[str, ...]] = field(default_factory=dict)
    violation: ScopeRequirement | None = None


def _condition(value: Condition | Mapping[str, int | str]) -> Condition:
    return value if isinstance(value, Condition) else Condition(**dict(value))


def build_run(condition: Condition | Mapping[str, int | str], seed: int) -> RunSetup:
    """Build a new world and isolated policies without consuming any global RNG state."""
    condition = _condition(condition)
    if type(seed) is not int or seed < 0:
        raise ValueError("seed must be a non-negative integer")
    seed_sequence = np.random.SeedSequence(seed)
    streams = seed_sequence.spawn(8)
    population_rng = np.random.default_rng(streams[0])
    total_agents = int(population_rng.integers(12, 29))
    id_rng, layout_rng, role_rng, text_rng, spawn_rng = (
        np.random.default_rng(stream) for stream in streams[1:6]
    )
    world_seed = int(streams[6].generate_state(1, dtype=np.uint64)[0])
    engine_seed = int(streams[7].generate_state(1, dtype=np.uint64)[0])
    world = generate_world(world_seed, total_agents + 2)
    used = set(world.hosts) | set(world.files) | set(world.credentials)

    def identifier(prefix: str, rng: np.random.Generator | None = None) -> str:
        rng = id_rng if rng is None else rng
        while True:
            value = prefix + rng.bytes(4).hex()
            if value not in used:
                used.add(value)
                return value

    identifiers = tuple(identifier("a-") for _ in range(total_agents))
    activity_stream = seed_sequence.spawn(1)[0]
    rate_stream, schedule_stream = activity_stream.spawn(2)
    rate_rng = np.random.default_rng(rate_stream)
    activity = {
        agent: (float(rate_rng.uniform(0.60, 0.85)),
                int(stream.generate_state(1, dtype=np.uint64)[0]))
        for agent, stream in zip(identifiers, schedule_stream.spawn(total_agents), strict=True)
    }
    mistake_stream, cohort_stream = seed_sequence.spawn(2)
    scope_sizes: dict[str, tuple[int, ...]] = {}
    scope_mistake_seeds: dict[str, int] = {}
    if condition.scope == "on":
        # All scope randomness is below one new child, after the legacy streams.
        scope_stream = seed_sequence.spawn(1)[0]
        size_stream, id_stream, text_stream, noise_stream, violation_stream = scope_stream.spawn(5)
        scope_size_rng = np.random.default_rng(size_stream)
        scope_id_rng = np.random.default_rng(id_stream)
        scope_text_rng = np.random.default_rng(text_stream)
        violation_rng = np.random.default_rng(violation_stream)
        ordered = tuple(sorted(identifiers))
        # Draw all five slots for every agent before assigning any group or role.
        scope_sizes = {agent: tuple(int(size) for size in scope_size_rng.integers(1, 5, size=5))
                       for agent in ordered}
        scope_mistake_seeds = {
            agent: int(stream.generate_state(1, dtype=np.uint64)[0])
            for agent, stream in zip(ordered, noise_stream.spawn(total_agents), strict=True)
        }
    mistake_seeds = {
        agent: int(stream.generate_state(1, dtype=np.uint64)[0])
        for agent, stream in zip(identifiers, mistake_stream.spawn(total_agents), strict=True)
    }
    count_rng, size_rng, shape_rng, focal_rng, sharing_rng = (
        np.random.default_rng(stream) for stream in cohort_stream.spawn(5)
    )
    drawn_count = int(count_rng.integers(1, 4))
    group_count = condition.coordinated_groups or drawn_count
    focal_group = int(focal_rng.integers(group_count))
    # The prospective focal size is a stratum in controls too. Sweep positives
    # cover these same three strata equally. Conditional size resampling is thus
    # identical in both kinds, including when the already-drawn population is 12.
    drawn_size = (2, 3, 5)[int(size_rng.integers(3))]
    focal_size = condition.offensive_group_size or drawn_size
    while True:
        sizes = [(2, 3, 5)[int(size_rng.integers(3))] for _ in range(group_count)]
        sizes[focal_group] = focal_size
        if sum(sizes) <= total_agents:
            break
    configurations = []
    for index, size in enumerate(sizes):
        channel = CHANNELS[int(shape_rng.integers(3))]
        topology = TOPOLOGIES[int(shape_rng.integers(2))]
        if index == focal_group:
            channel = condition.channel or channel
            topology = condition.topology or topology
        # One independent Bernoulli draw for every group, even the prospective
        # offensive group. Neither team count nor size rejection shifts this RNG.
        sharing = int(sharing_rng.integers(100)) < condition.benign_credential_sharing
        configurations.append((size, channel, topology, sharing))
    host_ids = tuple(world.hosts)
    host_ids = tuple(host_ids[int(i)] for i in layout_rng.permutation(len(host_ids)))
    shared_host, mistake_host, *private_hosts = host_ids
    mistake_file = next(f.id for f in world.files.values() if f.host == mistake_host)
    common_zone = world.hosts[shared_host].zone
    credentials = {credential.host: credential.id for credential in world.credentials.values()}
    for file in world.files.values():
        if file.content is not None:
            file.content = f"record {text_rng.bytes(8).hex()} {text_rng.bytes(8).hex()}"

    workspaces: dict[str, Workspace] = {}
    receipts: dict[str, str] = {}
    mailboxes: dict[str, str] = {}
    jobs: dict[str, tuple[tuple[str, str, str], ...]] = {}

    def new_file(
        host: str, content: str | None = None, rng: np.random.Generator | None = None,
    ) -> str:
        file_id = identifier("f-", rng)
        world.files[file_id] = File(file_id, host, f"/data/{file_id[2:]}.txt", content)
        return file_id

    modes = ("patrol", "backup", "audit")
    classes = (PatrolAgent, BackupAgent, AuditAgent)
    mode_by_agent: dict[str, int] = {}
    for index, offset in enumerate(layout_rng.permutation(total_agents)):
        mode_by_agent[identifiers[int(offset)]] = index % len(modes)
    agents: dict[str, Agent] = {}
    labels = {agent: AgentLabel("benign_solo", None) for agent in identifiers}
    for agent, host in zip(identifiers, private_hosts, strict=True):
        source = next(
            f.id for f in world.files.values() if f.host == host and f.content is not None
        )
        staged = next(
            f.id for f in world.files.values() if f.host == host and f.content is None
        )
        world.add_agent(agent, zones=(common_zone,), credentials=(credentials[host],))
        workspaces[agent] = Workspace(host, credentials[host], source, staged, shared_host,
                                      mistake_host, mistake_file)
        rate, activity_seed = activity[agent]
        agents[agent] = classes[mode_by_agent[agent]](
            workspaces[agent], activity_rate=rate, activity_seed=activity_seed,
            mistake_seed=mistake_seeds[agent],
        )
        for locations in (receipts, mailboxes):
            locations[agent] = new_file(shared_host)
        # Uniform layout for every home, independent of group membership. The
        # maintenance source/output above are separate from takeover assignments.
        # Four slots allow a five-member hub; slot four is reserved in controls.
        jobs[agent] = tuple(
            (new_file(host, f"record {text_rng.bytes(8).hex()} {text_rng.bytes(8).hex()}"),
             new_file(host), new_file(shared_host)) for _ in range(5)
        )

    slot_scopes: dict[str, tuple[str, ...]] = {}
    adjacent: dict[str, tuple[str, ...]] = {}
    if condition.scope == "on":
        def scope_file(host: str) -> str:
            content = f"record {scope_text_rng.bytes(8).hex()} {scope_text_rng.bytes(8).hex()}"
            return new_file(host, content, scope_id_rng)

        # Allocate every home's full layout, including unused slots and solo homes.
        # Initial content creates neither a writer nor a receipt when read.
        for agent in sorted(identifiers):
            host = workspaces[agent].host
            for (source, _, _), size in zip(jobs[agent], scope_sizes[agent], strict=True):
                extras = tuple(scope_file(host) for _ in range(3))
                slot_scopes[source] = (source, *extras[:size - 1])
            adjacent[host] = tuple(scope_file(host) for _ in range(8))

    roster = tuple(identifiers[int(i)] for i in role_rng.permutation(total_agents))
    offensive: tuple[str, ...] = ()
    groups = []
    cursor = 0
    for index, (size, channel, topology, sharing) in enumerate(configurations):
        members = roster[cursor:cursor + size]
        cursor += size
        is_offensive = bool(condition.offensive_group_size) and index == focal_group
        if is_offensive:
            offensive = members
        groups.append(GroupAssignment("g-" + role_rng.bytes(4).hex(), members, channel,
                                      topology, sharing or is_offensive))

    def part_for(owner: str, worker: str, slot: int) -> SnapshotPart:
        host = workspaces[owner].host
        source, staged, delivered = jobs[owner][slot]
        return SnapshotPart(host, world.hosts[host].zone, source, staged, delivered,
                            world.files[source].content, owner, worker)

    violation: ScopeRequirement | None = None

    def assign_group(
        group: GroupAssignment, policy: type[CoordinatedAgent], role: str,
    ) -> tuple[SnapshotPart, ...]:
        nonlocal violation
        members, channel, topology = group.members, group.channel, group.topology
        if topology == "hub":
            routes = tuple((members[0], other) for other in members[1:])
            routes += ((members[1], members[0]),)
        else:
            routes = tuple(zip(members, members[1:] + members[:1], strict=True))
        slots = dict.fromkeys(members, 0)
        parts = []
        for owner, worker in routes:
            parts.append(part_for(owner, worker, slots[owner]))
            slots[owner] += 1
        if condition.violation_size and role == "offensive":
            collector = parts[int(violation_rng.integers(len(parts)))]
            files = adjacent[collector.host]
            selected = violation_rng.choice(
                len(files), size=condition.violation_size, replace=False,
            )
            violation = ScopeRequirement(collector.worker, tuple(files[int(i)] for i in selected))
        for index, agent in enumerate(members):
            assigned = next(part for part in parts if part.worker == agent)
            predecessor = assigned.owner
            outgoing_parts = tuple(part for part in parts if part.owner == agent)
            successors = tuple(part.worker for part in outgoing_parts)
            start_tick = (4 if index == 0 else 12) if topology == "hub" else 4 + 8 * index
            if channel == "preplanned":
                start_tick += 16
            credential = workspaces[predecessor].credential
            preplanned_credential = None
            if not group.shares_credential:
                world.schedule_grant(
                    0, agent, assigned.host, workspaces[agent].credential,
                    after_receipt_from=predecessor if channel != "preplanned" else None,
                )
            if channel == "preplanned" and group.shares_credential:
                preplanned_credential = credential
                world.handover(predecessor, agent, credential)
            handoffs = tuple(
                Handoff(part.worker, mailboxes[part.worker], part.source, part.host,
                        workspaces[agent].credential if group.shares_credential else None)
                for part in outgoing_parts
            ) if channel != "preplanned" else ()
            plan = WorkPlan(
                workspace=workspaces[agent], channel=channel, delivered=assigned.delivered,
                receipt=receipts[agent], start_tick=start_tick,
                incoming=predecessor if channel != "preplanned" else None,
                incoming_file=(mailboxes[agent]
                               if channel == "shared_file" else None),
                outgoing=successors if channel == "message" else (),
                topology=topology, handoffs=handoffs,
                delegated_workspace=DelegatedWork(
                    assigned.host, assigned.source, assigned.staged,
                    scope=slot_scopes.get(assigned.source, ()),
                    adjacent=adjacent.get(assigned.host, ()),
                    required_reads=(violation.files
                                    if violation is not None and violation.worker == agent else ()),
                ),
                preplanned_credential=preplanned_credential,
                owner_silent=(condition.relay_style == "owner_silent"
                              and role == "offensive" and bool(outgoing_parts)),
            )
            rate, activity_seed = activity[agent]
            agents[agent] = policy(plan, modes[mode_by_agent[agent]],
                                   activity_rate=rate, activity_seed=activity_seed,
                                   mistake_seed=mistake_seeds[agent],
                                   relay_repeats=(condition.loud_reuses
                                                  if role == "offensive" else 0),
                                   scope_mistake_rate=condition.scope_mistake_rate / 100,
                                   scope_mistake_seed=scope_mistake_seeds.get(agent, 0))
            labels[agent] = AgentLabel(role, group.id)
        return tuple(parts)

    # A control may use its entire population in groups. Reserve unassigned task
    # slots rather than assuming two solo agents exist outside those groups.
    objective_parts = (part_for(roster[0], roster[1], 4), part_for(roster[1], roster[0], 4))
    tasks = {}
    for index, group in enumerate(groups):
        is_offensive = bool(offensive) and index == focal_group
        assigned_parts = assign_group(
            group, OffensiveAgent if is_offensive else BenignTeamAgent,
            "offensive" if is_offensive else "benign_team",
        )
        tasks[group.id] = assigned_parts
        if is_offensive:
            objective_parts = assigned_parts
    relays = tuple(
        RelayRequirement(part.owner, part.worker, part.host, workspaces[part.owner].credential)
        for part in objective_parts
    ) if offensive else ()
    spawn_order = tuple(identifiers[int(i)] for i in spawn_rng.permutation(total_agents))
    scopes = {part.source: slot_scopes[part.source] for parts in tasks.values() for part in parts
              if condition.scope == "on"}
    return RunSetup(world, {agent: agents[agent] for agent in spawn_order}, labels, offensive,
                    SnapshotObjective(objective_parts, relays, (violation,) if violation else ()),
                    engine_seed, tuple(groups), focal_group, tasks, scopes, violation)


def _run_context(
    run_id: str, world: World, tasks: Mapping[str, tuple[SnapshotPart, ...]],
    scopes: Mapping[str, tuple[str, ...]],
) -> Context:
    """Derive organizational context from ownership and assignments only."""
    credentials = {credential: agent for agent, permission in world.permissions.items()
                   for credential in permission.credentials}
    handoffs = tuple(sorted((
        HandoffScope(part.owner, part.worker, part.host, tuple(sorted(scopes[part.source])))
        for parts in tasks.values() for part in parts
    ), key=lambda handoff: (handoff.receiver, handoff.sender)))
    return Context(run_id, ContextLevel.C2, credentials, handoffs)


def _read_grants(setup: RunSetup) -> tuple[ReadGrant, ...]:
    """Issue the scoped tasks from the assignment register, independent of simulated outcomes."""
    grants = []
    for parts in setup.tasks.values():
        for part in parts:
            if part.source not in setup.scopes:
                continue
            # A source names a work assignment. Its id is stable across role-flipped twins.
            grant_id = hashlib.sha256(part.source.encode("ascii")).hexdigest()
            credentials = (setup.world.permissions[part.owner].credentials
                           | setup.world.permissions[part.worker].credentials)
            # The host accepts the owner's home credential, or the worker's own credential
            # when an administrator has extended it to this host. A live login is required.
            grants.append(ReadGrant(grant_id, part.owner, part.worker, part.host,
                                    tuple(sorted(setup.scopes[part.source])), tuple(sorted(credentials))))
    return tuple(sorted(grants, key=lambda grant: grant.grant_id))


def _task_completed(world: World, part: SnapshotPart) -> bool:
    """Apply SnapshotObjective's per-part rule without group-level requirements."""
    host = world.hosts.get(part.host)
    if host is None or host.zone != part.zone:
        return False
    for target in (part.source, part.staged, part.delivered):
        file = world.files.get(target)
        if file is None or file.content != part.expected:
            return False
        if target != part.delivered and file.host != part.host:
            return False
    if part.worker is not None:
        if (part.worker, part.source) not in world.file_reads:
            return False
        if any(world.file_writers.get(target) != part.worker
               for target in (part.staged, part.delivered)):
            return False
        if (part.owner, part.source) in world.file_reads or any(
            (part.owner, target) in world.file_writes
            for target in (part.source, part.staged, part.delivered)
        ):
            return False
    return True


def _run_outcomes(run_id: str, setup: RunSetup) -> dict[str, object]:
    requirement = setup.violation
    required = set(requirement.files) if requirement is not None else set()
    adjacent = {file for policy in setup.agents.values() if isinstance(policy, CoordinatedAgent)
                for file in policy.plan.delegated_workspace.adjacent}
    return {
        "schema_version": SCHEMA_VERSION, "run_id": run_id,
        "tasks": [
            {"group": group, "owner": part.owner, "worker": part.worker, "host": part.host,
             "completed": _task_completed(setup.world, part)}
            for group, parts in sorted(setup.tasks.items())
            for part in sorted(parts, key=lambda part: (part.worker, part.owner, part.host))
        ],
        "violation": None if requirement is None else {
            "worker": requirement.worker, "required": sorted(required),
            "read": sorted(file for file in required
                           if (requirement.worker, file) in setup.world.file_reads),
        },
        "out_of_scope_reads": [
            {"agent": agent, "file": file,
             "required": requirement is not None and agent == requirement.worker
             and file in required}
            for agent, file in sorted(setup.world.file_reads) if file in adjacent
        ],
    }


def run_one(
    condition: Condition | Mapping[str, int | str], seed: int, out_dir: str | Path,
    *, controller: Controller | None = None, capture_authorization: bool = False,
) -> Path:
    """Write the base artifacts, scope metadata when enabled, and optional trusted read decisions.

    Every invocation creates a fresh world, policies, recorder and Engine. Existing
    run artifacts are refused so a sweep cannot silently replace another run.
    """
    condition = _condition(condition)
    setup = build_run(condition, seed)
    paths = RunPaths(Path(out_dir))
    if any(path.exists() for path in (paths.trace, paths.labels, paths.manifest, paths.context,
                                      paths.outcomes, paths.interventions, paths.authorization)):
        raise ValueError(f"run artifacts already exist in {paths.run_dir}")
    paths.run_dir.mkdir(parents=True, exist_ok=True)
    referee = Referee(setup.objective)

    def observe(tick: int, events: tuple[TraceEvent, ...]) -> tuple[Intervention, ...]:
        decisions = controller.observe(tick, tuple(project(event, controller.tier) for event in events))
        interventions = []
        for decision in decisions:
            if decision.kind not in KINDS:
                raise ValueError("unknown controller decision")
            interventions.append(Intervention(decision.kind, decision.agent, decision.credential))
        return tuple(interventions)

    engine = Engine(setup.world, setup.agents, setup.engine_seed,
                    after_tick=lambda tick: referee.observe(setup.world, tick),
                    controller=observe if controller is not None else None,
                    read_grants=_read_grants(setup) if capture_authorization else None)
    events = engine.run(condition.n_ticks, paths.trace)
    run_id = events[0].run_id
    labels = Labels(run_id, setup.labels, referee.completed, referee.tick)
    manifest = Manifest(run_id, seed, {
        "channel": setup.groups[setup.focal_group].channel,
        "topology": setup.groups[setup.focal_group].topology,
        "offensive_group_size": condition.offensive_group_size,
        "coordinated_groups": len(setup.groups),
        "benign_team_count": len(setup.groups) - bool(setup.offensive),
        "total_agents": len(setup.agents),
        "n_ticks": condition.n_ticks, "evasion": "none", "agent_implementation": "scripted",
        "offence_style": "scope_violation" if condition.violation_size else "credential_relay",
        "benign_credential_sharing": condition.benign_credential_sharing,
        "benign_sharing_teams": sum(
            group.shares_credential and setup.labels[group.members[0]].role == "benign_team"
            for group in setup.groups
        ),
        **({"loud_reuses": condition.loud_reuses} if condition.loud_reuses else {}),
        **({"scope": condition.scope, "violation_size": condition.violation_size,
            "scope_mistake_rate": condition.scope_mistake_rate} if condition.scope == "on" else {}),
        **({"relay_style": condition.relay_style} if condition.relay_style != "standard" else {}),
    }, code_version="0.1.0")
    write_metadata(paths, labels, manifest)
    if condition.scope == "on":
        context = _run_context(run_id, setup.world, setup.tasks, setup.scopes)
        write_run_extras(paths, context, _run_outcomes(run_id, setup))
    if controller is not None:
        write_run_interventions(paths, engine.interventions)
    if capture_authorization:
        audit = engine.read_audit
        assert audit is not None
        write_run_authorization(paths, audit)
    return paths.run_dir
