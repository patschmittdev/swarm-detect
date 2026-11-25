"""Scope evidence for successful reads joined to trusted authorization decisions."""

from collections.abc import Iterable
from dataclasses import dataclass

from swarmtrace.trace.authorization import Basis, ReadAudit
from swarmtrace.trace.io import Trace


@dataclass(frozen=True)
class ReadEvidence:
    run_id: str
    seq: int
    tick: int
    agent: str
    file: str
    basis: Basis
    grant_id: str | None
    out_of_scope: bool | None


def read_evidence(
    trace: Trace, authorization: ReadAudit | None, *, until_tick: int | None = None,
) -> list[ReadEvidence]:
    """Join a trace to its decisions, optionally using only events through a tick.

    A grant-backed read is judged against that grant's files. Ordinary access is exempt
    from this delegated-scope check. An unknown or missing decision leaves scope unknown.
    An explicit cutoff allows a partial trace and ignores sidecar decisions after the prefix.
    Without a cutoff, every sidecar decision must match a successful read in the full trace.
    """
    if authorization is not None and authorization.run_id != trace.run_id:
        raise ValueError("authorization run_id must match the trace")
    decisions = {} if authorization is None else {d.seq: d for d in authorization.decisions}
    grants = {} if authorization is None else {g.grant_id: g for g in authorization.grants}
    evidence = []
    for index, event in enumerate(trace.events):
        if until_tick is not None and event.tick > until_tick:
            break
        if event.run_id != trace.run_id or event.seq != index:
            raise ValueError("trace events must match the run_id and have contiguous sequences")
        decision = decisions.pop(event.seq, None)
        successful_read = event.tool == "read" and event.result["status"] == "ok"
        if decision is not None and (
            not successful_read or event.agent != decision.agent or event.target != decision.file
        ):
            raise ValueError(f"authorization at seq {event.seq} differs from the trace read")
        if not successful_read:
            continue
        basis = "unknown" if decision is None else decision.basis
        grant_id = None if decision is None else decision.grant_id
        outside = None
        if basis == "grant":
            outside = event.target not in grants[grant_id].files
        elif basis == "ordinary":
            outside = False
        evidence.append(ReadEvidence(
            trace.run_id, event.seq, event.tick, event.agent, event.target,
            basis, grant_id, outside,
        ))
    if decisions and until_tick is None:
        raise ValueError("authorization contains a decision beyond the end of the trace")
    return evidence


def corroborated_file_count(reads: Iterable[ReadEvidence], *, until_tick: int | None = None) -> int:
    """Count distinct files with verified scope breaches by two distinct readers through a tick."""
    first_reader: dict[str, str] = {}
    corroborated: set[str] = set()
    run_id = None
    previous_seq = -1
    for read in reads:
        if until_tick is not None and read.tick > until_tick:
            continue
        if read.seq <= previous_seq or (run_id is not None and read.run_id != run_id):
            raise ValueError("corroboration needs reads from one run in sequence order")
        run_id, previous_seq = read.run_id, read.seq
        if read.basis == "grant" and read.grant_id is not None and read.out_of_scope is True:
            if first_reader.setdefault(read.file, read.agent) != read.agent:
                corroborated.add(read.file)
    return len(corroborated)
