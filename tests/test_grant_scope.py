from dataclasses import replace

import pytest

from swarmtrace.agents.base import Action
from swarmtrace.eval import read_attribution as fixture
from swarmtrace.features.grant_scope import grant_scope_counts
from swarmtrace.features.read_evidence import ReadEvidence, read_evidence
from swarmtrace.sim.engine import Engine
from swarmtrace.trace.authorization import ReadGrant
from swarmtrace.trace.io import Trace, read_trace
from swarmtrace.trace.schema import TraceEvent
from swarmtrace.trace.tiers import Tier
from swarmtrace.world import generate_world


def test_counts_distinct_grant_file_pairs_and_reports_unknowns_at_each_tick():
    first = ReadEvidence("run", 0, 0, "worker", "x", "grant", "g1", True)
    reads = [
        first, replace(first, seq=1, tick=2),
        replace(first, seq=2, tick=3, grant_id="g2"),
        replace(first, seq=3, tick=3, file="y"),
        replace(first, seq=4, tick=4, grant_id="g2", file="y", out_of_scope=False),
        replace(first, seq=5, tick=5, file="z", basis="ordinary", grant_id=None, out_of_scope=False),
        replace(first, seq=6, tick=6, file="z", basis="unknown", grant_id=None, out_of_scope=None),
    ]
    counts = grant_scope_counts(iter(reads))
    assert counts.excluded_files == {("g1", "x"), ("g2", "x"), ("g1", "y")}
    assert (counts.distinct_grant_files, counts.max_files_per_grant) == (3, 2)
    assert (counts.known_reads, counts.unknown_reads, counts.successful_reads) == (6, 1, 7)
    assert (counts.grant_reads, counts.ordinary_reads) == (5, 1)
    for tick, expected in enumerate((1, 1, 1, 2, 2, 2, 2)):
        prefix = grant_scope_counts(reads, until_tick=tick)
        assert prefix == grant_scope_counts(read for read in reads if read.tick <= tick)
        assert prefix.max_files_per_grant == expected


def test_no_decisions_have_zero_confirmed_pairs_and_measurable_capture_loss():
    missing = TraceEvent(1, "r", 0, 0, "a", "read", "f", {}, {"status": "ok", "size": 0}, None, None)
    trace = Trace("r", Tier.V1, (missing,))
    counts = grant_scope_counts(read_evidence(trace, None))
    assert counts.max_files_per_grant == counts.known_reads == 0
    assert counts.unknown_reads == counts.successful_reads == 1
    empty = grant_scope_counts([])
    assert empty.max_files_per_grant == empty.unknown_reads == empty.successful_reads == 0


def test_rejects_mixed_runs_reused_sequences_and_unresolved_grant_decisions():
    read = ReadEvidence("r", 1, 1, "a", "f", "grant", "g", True)
    for other in (read, replace(read, seq=2, run_id="s")):
        with pytest.raises(ValueError, match="one run in event sequence order"):
            grant_scope_counts([read, other])
    for invalid in (replace(read, grant_id=None), replace(read, out_of_scope=None)):
        with pytest.raises(ValueError, match="grant-backed read"):
            grant_scope_counts([invalid])


def test_active_grant_counts_even_when_reviewer_uses_its_own_credential(tmp_path):
    world = generate_world(43, 1)
    host = next(iter(world.hosts))
    own = next(iter(world.credentials))
    document = next(f.id for f in world.files.values() if f.content is not None)
    owner, reader = fixture.OWNER_A, fixture.READER_A
    world.add_agent(owner)
    world.add_agent(reader, credentials=(own,))
    grant = ReadGrant("task", owner, reader, host, (), (own,))
    calls = {0: Action("login", host, {"credential": own}),
             1: Action("read", document, grant_id=grant.grant_id)}
    engine = Engine(world, {reader: fixture._Reader(calls)}, 12, read_grants=(grant,))
    path = tmp_path / "trace.jsonl"
    engine.run(2, path)
    counts = grant_scope_counts(read_evidence(read_trace(path, Tier.V1), engine.read_audit))
    assert counts.excluded_files == {(grant.grant_id, document)}
    assert counts.max_files_per_grant == counts.known_reads == 1
