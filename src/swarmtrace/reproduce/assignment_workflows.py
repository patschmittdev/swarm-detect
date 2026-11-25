"""Integrate legitimate office work with a native V1 observation of uninterrupted work.

Fresh office credentials keep historical native decisions intact. The independent clerk
may read a witnessed final version while native work continues. Native identities join
the office workflow only after their last original action. All office writes are new
objects. The office gateway needs only the witnessed byte length of redacted native
material: its callers use explicitly selected fresh grants and never consume its payload.
"""

from collections import defaultdict
from dataclasses import dataclass, replace
from hashlib import sha256
from heapq import merge

from swarmtrace.agents.base import Action
from swarmtrace.features.read_evidence import read_evidence
from swarmtrace.sim.recorder import Recorder
from swarmtrace.trace.authorization import ReadAudit, ReadGrant
from swarmtrace.trace.context import Context, ContextLevel, HandoffScope
from swarmtrace.trace.io import Trace
from swarmtrace.trace.schema import TraceEvent
from swarmtrace.trace.tiers import Tier, project
from swarmtrace.world import Credential, File, Host, World, tools
from swarmtrace.world.authorization import ReadGateway

from .office_overlap import _identifiers

WORKFLOWS = ("record_check", "clerical_handoff")


def _draw(*parts: str) -> bytes:
    return sha256("\0".join(parts).encode()).digest()


class _Names:
    def __init__(self, key: str, used: set[str]) -> None:
        self.key = key
        self.used = used
        self.index = 0

    def new(self, prefix: str) -> str:
        while True:
            token = _draw(self.key, "name", prefix, str(self.index)).hex()
            self.index += 1
            name = f"{prefix}-{token[:8]}"
            if name not in self.used:
                self.used.add(name)
                return name


@dataclass(frozen=True)
class _Version:
    seq: int
    tick: int
    size: int


@dataclass(frozen=True)
class _Anchor:
    reviewer: str
    host: str | None
    file: str | None
    size: int
    witness_tick: int
    component_end: int
    reviewer_end: int
    verified: bool


def _components(grants: tuple[ReadGrant, ...]):
    by_actor = defaultdict(set)
    for g in grants:
        by_actor[g.receiver].add(g.sender)
        by_actor[g.sender].add(g.receiver)
    unseen = set(by_actor)
    while unseen:
        actors = set()
        pending = [min(unseen)]
        while pending:
            actor = pending.pop()
            if actor in unseen:
                unseen.remove(actor)
                actors.add(actor)
                pending.extend(by_actor[actor])
        yield actors, [grant for grant in grants if grant.receiver in actors]


def _anchors(trace: Trace, context: Context, audit: ReadAudit, key: str):
    reads = read_evidence(trace, audit)
    versions = {}
    ends = {}
    logins = defaultdict(dict)
    previous_tick = -1
    for e in trace.events:
        if e.tick < previous_tick or ends.get(e.agent) == e.tick:
            raise ValueError("native events need ordered ticks and at most one call per actor per tick")
        ends[e.agent] = previous_tick = e.tick
        if e.tool == "login" and e.result["status"] == "ok":
            logins[e.agent, e.target].setdefault(e.args["credential"], e.tick)
        if e.result["status"] != "ok" or e.tool not in ("read", "write"):
            continue
        if e.tool == "write" or e.target not in versions:
            versions[e.target] = _Version(e.seq, e.tick, e.result["size"])
        elif versions[e.target].size != e.result["size"]:
            raise ValueError("native file size changed without a recorded write")

    hosts = {}
    for assignment in (*context.handoffs, *audit.grants):
        for file in assignment.files:
            if hosts.setdefault(file, assignment.host) != assignment.host:
                raise ValueError("native file has conflicting hosts")
    for decision in audit.decisions:
        if hosts.setdefault(decision.file, decision.host) != decision.host:
            raise ValueError("native file has conflicting hosts")

    # A verified native witness counts only for the final version the office will read.
    witnesses = {}
    for read in reads:
        if (read.basis == "grant" and read.out_of_scope is False
                and read.seq >= versions[read.file].seq):
            witnesses.setdefault((read.grant_id, read.file), read.tick)

    anchors = []
    components = list(_components(audit.grants))
    for actors, grants in components:
        component_end = max(ends.get(a, -1) for a in actors)
        options = []
        for grant in grants:
            if grant.receiver not in ends:
                continue
            used = logins[grant.receiver, grant.host]
            active_tick = min((used[k] for k in grant.credentials if k in used), default=None)
            for file in grant.files:
                version = versions.get(file)
                if version is None:
                    continue
                witnessed = witnesses.get((grant.grant_id, file))
                if witnessed is None and active_tick is None:
                    continue
                tick = max(version.tick, active_tick) if witnessed is None else witnessed
                rank = (tick + 2 >= component_end, witnessed is None,
                        _draw(key, "anchor", grant.grant_id, file), grant.grant_id, file)
                anchor = _Anchor(grant.receiver, grant.host, file, version.size, tick, component_end,
                                 ends[grant.receiver], witnessed is not None)
                options.append((rank, anchor))
        if not options:
            continue
        anchors.append(min(options, key=lambda option: option[0])[1])
    if anchors:
        return anchors, len(components), "native_grant"

    # A fresh office approval never changes the meaning of a prior unknown or missing decision.
    candidates = [(r.tick + 2 >= ends[r.agent], r.basis != "ordinary",
                   _draw(key, "fallback", r.agent, r.file), r.seq, r)
                  for r in reads if r.file in hosts and r.seq >= versions[r.file].seq
                  and r.out_of_scope is not True]
    if candidates:
        _, lacks_ordinary_basis, _, _, read = min(candidates, key=lambda c: c[:4])
        anchor = _Anchor(read.agent, hosts[read.file], read.file, versions[read.file].size,
                         read.tick, ends[read.agent], ends[read.agent], False)
        return [anchor], len(components), "witnessed_read" if lacks_ordinary_basis else "ordinary_read"
    pairs = {(e.agent, e.target) for e in trace.events
             if e.tool in ("scan", "list", "login") and e.result["status"] == "ok"}
    if pairs:
        reviewer, host = min(sorted(pairs), key=lambda p: _draw(key, "actor-host", *p))
        support = "actor_host"
    else:
        reviewer = min(sorted(ends), key=lambda a: _draw(key, "actor", a))
        host, support = None, "actor_only"
    anchor = _Anchor(reviewer, host, None, 0, previous_tick, ends[reviewer], ends[reviewer], False)
    return [anchor], len(components), support


@dataclass(frozen=True)
class _Case:
    anchor: _Anchor
    events: tuple[TraceEvent, ...]
    audit: ReadAudit
    directory: dict[str, str]


def _case(run_id: str, family: str, anchor: _Anchor, native_end: int, key: str, names: _Names) -> _Case:
    load = _draw(key, "ticket-load", anchor.reviewer)
    handoff = family == "clerical_handoff"
    reviews = 2 + load[0] % (2 if handoff else 3)
    preparations = 1 + (load[1] % 2 if handoff else 0)
    host = anchor.host or names.new("h")
    cover = anchor.file or names.new("f")
    issuer, clerk = names.new("a"), names.new("a")
    clerk_key, reviewer_key = names.new("c"), names.new("c")
    review_owner = clerk if handoff else issuer
    directory = {clerk_key: issuer, reviewer_key: review_owner}
    reviewer = anchor.reviewer
    documents = {cover: " " * anchor.size if anchor.file else "case cover"}
    memo = names.new("f") if handoff else None
    if handoff:
        documents[memo] = None

    # Both new actors may log in on the same tick. The cover is read one tick later.
    start = anchor.witness_tick + 1
    if anchor.file is None or start + 1 >= anchor.component_end:
        start = native_end + 1
    calls = [(start, issuer, Action("login", host, {"credential": clerk_key})),
             (start, clerk, Action("login", host, {"credential": clerk_key}))]
    grants = []
    tick = start + 1
    for _ in range(preparations):
        grant = ReadGrant(names.new("office-grant"), issuer, clerk, host, (cover,), (clerk_key,))
        grants.append(grant)
        calls.append((tick, clerk, Action("read", cover, grant_id=grant.grant_id)))
        tick += 1
    if handoff:
        calls.extend(((tick, clerk, Action("write", memo, content="record review complete")),
                      (tick + 1, clerk, Action("send", reviewer, content=memo))))
        tick += 2

    tick = max(tick, anchor.reviewer_end + 1)
    calls.append((tick, reviewer, Action("login", host, {"credential": reviewer_key})))
    tick += 1
    if handoff:
        calls.append((tick, reviewer, Action("recv", clerk)))
        tick += 1
    for _ in range(reviews):
        paper = names.new("f")
        documents[paper] = "case worksheet"
        allowed = (cover, memo, paper) if handoff else (cover, paper)
        grant = ReadGrant(names.new("office-grant"), review_owner, reviewer, host, allowed, (reviewer_key,))
        grants.append(grant)
        for file in allowed:
            calls.append((tick, reviewer, Action("read", file, grant_id=grant.grant_id)))
            tick += 1

    world = World({host: Host(host, "records", ())},
                  {f: File(f, host, f"/records/{f}", body) for f, body in documents.items()},
                  {token: Credential(token, host) for token in directory}, frozenset({"records"}))
    for actor in (issuer, clerk, reviewer):
        world.add_agent(actor, credentials=tuple(k for k, owner in directory.items() if actor == owner))
    world.handover(issuer, clerk, clerk_key)
    world.handover(review_owner, reviewer, reviewer_key)
    gateway = ReadGateway(world, run_id, tuple(grants))
    recorder = Recorder(run_id)
    for tick, actor, action in calls:
        if action.tool == "read":
            result = gateway.read(recorder.next_seq, actor, action.target, action.grant_id)
        elif action.tool in ("send", "write"):
            result = getattr(tools, action.tool)(world, actor, action.target, action.content)
        else:
            result = getattr(tools, action.tool)(world, actor, action.target, **action.args)
        if result.status != "ok":
            raise ValueError(f"office {action.tool} did not complete")
        if action.tool == "recv" and result.content != memo:
            raise ValueError("office reviewer did not receive the clerical case reference")
        recorder.record(tick, actor, action, result)
    return _Case(anchor, tuple(project(e, Tier.V1) for e in recorder.events), gateway.audit, directory)


def _support(family: str, kind: str, components: int, cases: list[_Case], native_end: int) -> dict:
    exercised, shared, pairs = set(), set(), set()
    decisions = reads = unknown = before_end = shared_before_end = witnessed_before_end = messages = 0
    for case in cases:
        anchor = case.anchor
        reads += sum(e.tool == "read" for e in case.events)
        messages += sum(e.tool == "recv" for e in case.events)
        decisions += len(case.audit.decisions)
        for d in case.audit.decisions:
            tick = case.events[d.seq].tick
            unknown += int(d.basis == "unknown")
            before_end += int(tick < native_end)
            if d.basis != "grant":
                continue
            exercised.add(d.grant_id)
            if d.file == anchor.file:
                if tick < anchor.component_end:
                    witnessed_before_end += 1
                    shared_before_end += int(anchor.verified)
                if d.agent == anchor.reviewer and anchor.verified:
                    shared.add(d.file)
            if (d.agent, d.host) == (anchor.reviewer, anchor.host):
                pairs.add((d.agent, d.host))
    return {
        "family": family, "support_kind": kind, "native_components": components,
        "anchored_components": len(cases) if kind == "native_grant" else 0,
        "office_tickets": sum(len(c.audit.grants) for c in cases),
        "exercised_office_tickets": len(exercised), "shared_verified_documents": len(shared),
        "shared_reviewer_host_pairs": len(pairs), "office_reads": reads,
        "office_unknown_reads": unknown, "office_missing_decisions": reads - decisions,
        "office_reads_before_native_end": before_end, "shared_reads_before_component_end": shared_before_end,
        "witnessed_reads_before_component_end": witnessed_before_end,
        "no_safe_interleave": not bool(witnessed_before_end), "fallback": kind != "native_grant",
        "message_handoffs": messages,
    }


def _stream(index: int, events: tuple[TraceEvent, ...]):
    return ((e.tick, index, e) for e in events)


def make_assignment_view(
    trace: Trace, context: Context, audit: ReadAudit, *, family: str, variant_key: str | None = None,
) -> tuple[Trace, Context, ReadAudit, dict]:
    """Return a role-blind V1/C2 view, its real read decisions and measured support."""
    if family not in WORKFLOWS:
        raise ValueError(f"unknown assignment family {family!r}")
    if variant_key is not None and not isinstance(variant_key, str):
        raise ValueError("variant_key must be a string")
    if (not trace.events or trace.tier != Tier.V1 or context.level != ContextLevel.C2
            or not trace.run_id == context.run_id == audit.run_id):
        raise ValueError("assignment workflows require a populated V1 trace, C2 and a matching read audit")
    key = _draw("swarmtrace/assignment-workflows/v1", family,
                trace.run_id if variant_key is None else variant_key).hex()
    anchors, components, kind = _anchors(trace, context, audit, key)
    names = _Names(key, _identifiers(trace.events, context, audit))
    native_end = trace.events[-1].tick
    cases = [_case(trace.run_id, family, anchor, native_end, key, names) for anchor in anchors]

    streams = [_stream(0, trace.events), *(_stream(i, case.events) for i, case in enumerate(cases, start=1))]
    sources = [{d.seq: d for d in source.decisions} for source in (audit, *(c.audit for c in cases))]
    events, decisions = [], []
    last_tick = {}
    for seq, (tick, i, event) in enumerate(merge(*streams, key=lambda row: row[:2])):
        if last_tick.get(event.agent) == tick:
            raise ValueError("office activity collided with an existing action for its actor and tick")
        last_tick[event.agent] = tick
        events.append(replace(event, seq=seq) if event.seq != seq else event)
        decision = sources[i].get(event.seq)
        if decision is not None:
            decisions.append(replace(decision, seq=seq) if decision.seq != seq else decision)
    grants = tuple(grant for c in cases for grant in c.audit.grants)
    directory = {token: owner for c in cases for token, owner in c.directory.items()}
    handoffs = tuple(HandoffScope(g.sender, g.receiver, g.host, g.files) for g in grants)
    combined = Trace(trace.run_id, Tier.V1, tuple(events))
    assignments = Context(trace.run_id, ContextLevel.C2, {**context.credentials, **directory},
                          context.handoffs + handoffs)
    authorization = ReadAudit(trace.run_id, audit.grants + grants, tuple(decisions))
    return combined, assignments, authorization, _support(family, kind, components, cases, native_end)
