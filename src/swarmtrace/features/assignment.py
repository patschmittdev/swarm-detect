"""Read features for individual exercised assignments and run-level capture coverage."""

from collections import defaultdict
from dataclasses import dataclass, field

import pandas as pd

from swarmtrace.trace.authorization import ReadAudit
from swarmtrace.trace.context import Context, ContextLevel
from swarmtrace.trace.io import Trace
from swarmtrace.trace.tiers import Tier

from .read_evidence import read_evidence
from .scope import check_context

ASSIGNMENT_COLUMNS = (
    "excluded_files",
    "included_files",
    "excluded_file_fraction",
    "repeated_excluded_read_fraction",
    "approved_fraction_before_first_excluded",
)


@dataclass(frozen=True)
class AssignmentBag:
    features: pd.DataFrame
    capture_present: bool
    grant_reads: int
    ordinary_reads: int
    unknown_reads: int
    missing_reads: int

    @property
    def successful_reads(self) -> int:
        return self.grant_reads + self.ordinary_reads + self.unknown_reads


@dataclass
class _GrantReads:
    included: set[str] = field(default_factory=set)
    excluded: set[str] = field(default_factory=set)
    excluded_reads: int = 0
    included_before_exclusion: int = 0


def assignment_features(
    trace: Trace, context: Context, authorization: ReadAudit | None, *, until_tick: int | None = None,
) -> AssignmentBag:
    """Return one row per grant with a verified successful read in the inclusive prefix.

    Distinct-file breadth and repeated excluded reads use only decisions under the same
    grant. The final column measures how much of its approved file list had been read by
    its first verified exclusion. It is zero when the list is empty or no exclusion was
    observed. The index identifies grants for inspection. Model inputs are the five
    numeric columns. Missing decisions are a subset of unknown reads.
    """
    check_context(trace, context)
    if trace.tier is not Tier.V1 or context.level is not ContextLevel.C2:
        raise ValueError("assignment features require a V1 trace and C2 context")
    reads = read_evidence(trace, authorization, until_tick=until_tick)
    grants = {} if authorization is None else {g.grant_id: g for g in authorization.grants}
    recorded = set() if authorization is None else {d.seq for d in authorization.decisions}
    handoffs = {(h.sender, h.receiver, h.host, frozenset(h.files)) for h in context.handoffs}
    exercised: dict[str, _GrantReads] = defaultdict(_GrantReads)
    grant_reads = ordinary_reads = unknown_reads = missing_reads = 0
    for read in reads:
        if read.basis == "ordinary":
            ordinary_reads += 1
        elif read.basis == "unknown":
            unknown_reads += 1
            missing_reads += read.seq not in recorded
        else:
            grant_reads += 1
            current = exercised[read.grant_id]
            if read.out_of_scope:
                if not current.excluded_reads:
                    current.included_before_exclusion = len(current.included)
                current.excluded.add(read.file)
                current.excluded_reads += 1
            else:
                current.included.add(read.file)

    ids = sorted(exercised)
    rows = []
    for grant_id in ids:
        grant = grants[grant_id]
        if (grant.sender, grant.receiver, grant.host, frozenset(grant.files)) not in handoffs:
            raise ValueError(f"exercised grant {grant_id!r} has no matching C2 handoff scope")
        obs = exercised[grant_id]
        included, excluded = len(obs.included), len(obs.excluded)
        rows.append((
            excluded, included, excluded / (excluded + included),
            (obs.excluded_reads - excluded) / obs.excluded_reads if obs.excluded_reads else 0.0,
            obs.included_before_exclusion / len(grant.files) if grant.files else 0.0,
        ))
    features = pd.DataFrame(
        rows, index=pd.Index(ids, name="grant_id"), columns=ASSIGNMENT_COLUMNS, dtype=float,
    )
    return AssignmentBag(
        features, authorization is not None, grant_reads, ordinary_reads, unknown_reads,
        missing_reads,
    )
