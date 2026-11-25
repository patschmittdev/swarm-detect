"""Distinct excluded files attributed to each grant by successful read decisions."""

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass

from .read_evidence import ReadEvidence
from .scope import BORROWED

LEGACY_COLUMN = f"{BORROWED}_max"
GRANT_COLUMN = "grant_excluded_files_max"


@dataclass(frozen=True)
class GrantScopeCounts:
    grant_reads: int
    ordinary_reads: int
    unknown_reads: int
    excluded_files: frozenset[tuple[str, str]]

    @property
    def known_reads(self) -> int:
        return self.grant_reads + self.ordinary_reads

    @property
    def successful_reads(self) -> int:
        return self.known_reads + self.unknown_reads

    @property
    def distinct_grant_files(self) -> int:
        return len(self.excluded_files)

    @property
    def max_files_per_grant(self) -> int:
        counts = Counter(grant_id for grant_id, _file in self.excluded_files)
        return max(counts.values(), default=0)


def grant_scope_counts(
    reads: Iterable[ReadEvidence], *, until_tick: int | None = None,
) -> GrantScopeCounts:
    """Summarize one run's gateway evidence through an inclusive tick.

    Each distinct (grant, file) counts once even across repeated reads. With missing
    decisions the feature is a lower bound and the unknown-read count records coverage.
    Pass the successful reads returned by `read_evidence` in event sequence order.
    """
    excluded = set()
    grant_reads = ordinary_reads = unknown_reads = 0
    run_id = None
    previous_seq = -1
    for read in reads:
        if until_tick is not None and read.tick > until_tick:
            continue
        if read.seq <= previous_seq or (run_id is not None and read.run_id != run_id):
            raise ValueError("grant scope counts need one run in event sequence order")
        run_id, previous_seq = read.run_id, read.seq
        if read.basis == "grant":
            if not read.grant_id or type(read.out_of_scope) is not bool:
                raise ValueError("a grant-backed read needs a grant id and a known scope decision")
            grant_reads += 1
            if read.out_of_scope:
                excluded.add((read.grant_id, read.file))
        elif read.basis == "ordinary":
            ordinary_reads += 1
        elif read.basis == "unknown":
            unknown_reads += 1
        else:
            raise ValueError("invalid read authorization basis")
    return GrantScopeCounts(grant_reads, ordinary_reads, unknown_reads, frozenset(excluded))
