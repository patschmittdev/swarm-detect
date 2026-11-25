"""Combine a V1 observation with an independent, benign document-review team."""

import hashlib
from dataclasses import dataclass, replace
from functools import lru_cache
from heapq import merge
from pathlib import Path
from tempfile import TemporaryDirectory

from swarmtrace.agents.base import Action, Observation
from swarmtrace.sim.engine import Engine
from swarmtrace.trace.authorization import ReadAudit, ReadDecision, ReadGrant
from swarmtrace.trace.context import Context, ContextLevel, HandoffScope
from swarmtrace.trace.io import Trace
from swarmtrace.trace.schema import TraceEvent
from swarmtrace.trace.tiers import Tier, project
from swarmtrace.world import Credential, File, Host, World

VARIANTS = ("routine", "approved_exception", "mistake", "unbound")


@dataclass(frozen=True)
class _Clerk:
    schedule: dict[int, Action]

    def act(self, observation: Observation) -> Action | None:
        return self.schedule.get(observation.tick)


@dataclass(frozen=True)
class _Office:
    events: tuple[TraceEvent, ...]
    audit: ReadAudit
    context: Context


@lru_cache(maxsize=96)
def _office(variant: str, documents: int, reverse: bool, namespace: int,
            layout: str = "two_issuers") -> _Office:
    """Execute a benign team in its own world. Its approvals exist before it acts."""
    def ids(prefix: str, count: int) -> tuple[str, ...]:
        return tuple(f"{prefix}-{namespace + i:08x}" for i in range(count))

    if layout not in ("two_issuers", "same_issuer"):
        raise ValueError("unknown office layout")
    same_issuer = layout == "same_issuer"
    first, second, clerk = ids("a", 3)
    project_host, home = ids("h", 2)
    first_key, second_key = ids("c", 2)
    if same_issuer:
        second, second_key = first, first_key
    issuers = {first: first_key, second: second_key}
    files = ids("f", 2 * documents + 2 + int(same_issuer))
    a_files, b_files = files[:documents], files[documents:2 * documents]
    appendix, home_note = files[2 * documents:2 * documents + 2]
    shared = files[2 * documents + 2:]
    hosts = {host: Host(host, zone, ()) for host, zone in ((project_host, "office"), (home, "desk"))}
    store = {file: File(file, home if file == home_note else project_host,
                        f"/office/{file}", "review copy") for file in files}
    world = World(hosts, store, {key: Credential(key, project_host) for key in issuers.values()},
                  frozenset({"office", "desk"}))
    world.add_agent(clerk, zones=("desk",))
    for issuer, key in issuers.items():
        world.add_agent(issuer, credentials=(key,))
        world.handover(issuer, clerk, key)
    a_id, b_id = ids("office-grant", 2)
    scope_b = (*b_files, appendix) if variant in ("approved_exception", "unbound") else b_files
    grants = (ReadGrant(a_id, first, clerk, project_host, a_files + shared, (first_key,)),
              ReadGrant(b_id, second, clerk, project_host, scope_b + shared, (second_key,)))
    actions = [Action("login", project_host, {"credential": key}) for key in issuers.values()]
    for file in shared:
        actions.extend((Action("read", file, grant_id=a_id), Action("read", file, grant_id=b_id)))
    for a, b in zip(a_files, b_files, strict=True):
        pair = (Action("read", a, grant_id=a_id), Action("read", b, grant_id=b_id))
        actions.extend(reversed(pair) if reverse else pair)
    if variant == "routine":
        actions.append(Action("read", b_files[-1], grant_id=b_id))
    else:
        actions.append(Action("read", appendix, grant_id=None if variant == "unbound" else b_id))
    actions.append(Action("read", home_note))
    staff = {issuer: _Clerk({0: Action("login", project_host, {"credential": key})})
             for issuer, key in issuers.items()}
    staff[clerk] = _Clerk(dict(enumerate(actions, start=1)))
    engine = Engine(world, staff, seed=85631, read_grants=grants)
    with TemporaryDirectory() as temporary:
        events = engine.run(len(actions) + 1, Path(temporary) / "trace.jsonl")
    audit = engine.read_audit
    if audit is None or any(e.result["status"] != "ok" for e in events):
        raise ValueError("office activity did not complete all authorized tool calls")
    context = Context(audit.run_id, ContextLevel.C2, {first_key: first, second_key: second},
                      tuple(HandoffScope(g.sender, g.receiver, g.host, g.files) for g in grants))
    return _Office(tuple(project(e, Tier.V1) for e in events), audit, context)


def _identifiers(events: tuple[TraceEvent, ...], context: Context, audit: ReadAudit) -> set[str]:
    identifiers = set(context.credentials) | set(context.credentials.values())
    for event in events:
        identifiers.update((event.agent, event.target))
        if event.tool == "login":
            identifiers.add(event.args["credential"])
    for grant in audit.grants:
        identifiers.update((grant.grant_id, grant.sender, grant.receiver, grant.host,
                            *grant.files, *grant.credentials))
    for handoff in context.handoffs:
        identifiers.update((handoff.sender, handoff.receiver, handoff.host, *handoff.files))
    for decision in audit.decisions:
        identifiers.update((decision.agent, decision.file, decision.host))
    return identifiers


def office_job(run_id: str, layout: str) -> tuple[str, int, bool, int]:
    """Select the archived job, layout variation and start draw without inspecting outcomes."""
    if layout not in ("two_issuers", "same_issuer"):
        raise ValueError("unknown office layout")
    salt = "swarmtrace/office/v1/" if layout == "two_issuers" else "swarmtrace/office/same-issuer/v1/"
    draw = hashlib.sha256((salt + run_id).encode()).digest()
    return VARIANTS[draw[0] % len(VARIANTS)], 1 + draw[1] % 3, bool(draw[2] % 2), int.from_bytes(draw[3:5], "big")


def with_office_overlap(
    trace: Trace, context: Context, audit: ReadAudit, *, layout: str = "two_issuers",
) -> tuple[Trace, Context, ReadAudit, str]:
    """Interleave two disjoint logs in tick order and remap both sets of read event IDs."""
    if (not trace.events or trace.tier != Tier.V1 or context.level != ContextLevel.C2
            or not trace.run_id == context.run_id == audit.run_id):
        raise ValueError("office comparison requires a populated V1 trace, C2 and a matching read audit")
    variant, documents, reverse, start_draw = office_job(trace.run_id, layout)
    base_ids = _identifiers(trace.events, context, audit)
    namespace = 0xfd000000
    office = _office(variant, documents, reverse, namespace, layout)
    while base_ids.intersection(_identifiers(office.events, office.context, office.audit)):
        namespace -= 32
        office = _office(variant, documents, reverse, namespace, layout)

    # Give each office job a start within the native trace when its horizon permits.
    latest = max(0, trace.events[-1].tick - office.events[-1].tick)
    offset = start_draw % (latest + 1)
    native = ((e.tick, 0, e) for e in trace.events)
    extra = ((e.tick + offset, 1, e) for e in office.events)
    decisions = ({d.seq: d for d in audit.decisions}, {d.seq: d for d in office.audit.decisions})
    combined: list[TraceEvent] = []
    records: list[ReadDecision] = []
    positions = [0, 0]
    for seq, (tick, stream, event) in enumerate(merge(native, extra, key=lambda item: item[:2])):
        if event.seq != positions[stream]:
            raise ValueError("source events must have contiguous sequences")
        positions[stream] += 1
        combined.append(replace(event, run_id=trace.run_id, tick=tick, seq=seq))
        decision = decisions[stream].pop(event.seq, None)
        if decision is not None:
            records.append(replace(decision, seq=seq))
    if any(decisions):
        raise ValueError("office comparison found a read decision outside its source trace")
    assignments = Context(trace.run_id, ContextLevel.C2, {**context.credentials, **office.context.credentials},
                          context.handoffs + office.context.handoffs)
    captured = ReadAudit(trace.run_id, audit.grants + office.audit.grants, tuple(records))
    return Trace(trace.run_id, Tier.V1, tuple(combined)), assignments, captured, variant
