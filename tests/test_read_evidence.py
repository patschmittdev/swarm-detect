from dataclasses import replace

import pytest

from swarmtrace.features.read_evidence import corroborated_file_count, read_evidence
from swarmtrace.trace.authorization import ReadAudit, ReadDecision, ReadGrant
from swarmtrace.trace.io import Trace
from swarmtrace.trace.schema import TraceEvent
from swarmtrace.trace.tiers import Tier

RUN = "0123456789abcdef"
A, B, OWNER = "a-00000001", "a-00000002", "a-00000003"
H, F, EXTRA = "h-00000001", "f-00000001", "f-00000002"
G1, G2 = "grant-a", "grant-b"


def event(seq, tick, agent, target, *, tool="read", status="ok"):
    return TraceEvent(1, RUN, seq, tick, agent, tool, target, {},
                      {"status": status, "size": 0}, None, None)


def observed():
    events = (
        event(0, 1, A, F),
        event(1, 2, A, F),
        event(2, 3, B, F, status="denied"),
        event(3, 4, B, F),
        event(4, 5, B, F),
        event(5, 6, B, F),
        event(6, 6, A, EXTRA),
        event(7, 6, B, EXTRA),
    )
    audit = ReadAudit(RUN, (
        ReadGrant(G1, OWNER, A, H, ()),
        ReadGrant(G2, OWNER, B, H, (EXTRA,)),
    ), (
        ReadDecision(0, A, F, H, "grant", G1),
        ReadDecision(1, A, F, H, "grant", G1),
        # No decision was captured at seq 3.
        ReadDecision(4, B, F, H, "ordinary"),
        ReadDecision(5, B, F, H, "grant", G2),
        ReadDecision(6, A, EXTRA, H, "grant", G1),
        ReadDecision(7, B, EXTRA, H, "grant", G2),
    ))
    return Trace(RUN, Tier.V1, events), audit


def test_only_verified_distinct_readers_of_the_same_excluded_file_corroborate():
    trace, audit = observed()
    reads = read_evidence(trace, audit)
    assert [read.seq for read in reads] == [0, 1, 3, 4, 5, 6, 7]
    assert [(read.basis, read.out_of_scope) for read in reads] == [
        ("grant", True), ("grant", True), ("unknown", None), ("ordinary", False),
        ("grant", True), ("grant", True), ("grant", False),
    ]
    assert corroborated_file_count(reads, until_tick=5) == 0
    assert corroborated_file_count(reads, until_tick=6) == 1
    assert corroborated_file_count(reads) == 1
    for tick in range(-1, 9):
        prefix = read_evidence(trace, audit, until_tick=tick)
        assert prefix == [r for r in reads if r.tick <= tick]
        assert corroborated_file_count(prefix) == corroborated_file_count(reads, until_tick=tick)


def test_absent_or_empty_stream_keeps_all_successful_reads_unknown():
    trace, audit = observed()
    for incomplete in (None, replace(audit, decisions=())):
        reads = read_evidence(trace, incomplete)
        assert len(reads) == 7
        assert all(r.basis == "unknown" and r.out_of_scope is None for r in reads)
        assert corroborated_file_count(reads) == 0


def test_streaming_prefix_cannot_use_a_future_decision_to_change_an_earlier_result():
    trace, audit = observed()
    prefix = replace(trace, events=trace.events[:2])
    expected = read_evidence(trace, audit, until_tick=2)
    assert read_evidence(prefix, audit, until_tick=2) == expected
    damaged = replace(audit, decisions=(*audit.decisions[:-1],
                                        replace(audit.decisions[-1], file=F)))
    assert read_evidence(trace, damaged, until_tick=2) == expected
    with pytest.raises(ValueError, match="trace read"):
        read_evidence(trace, damaged)
    with pytest.raises(ValueError, match="beyond the end"):
        read_evidence(prefix, audit)


@pytest.mark.parametrize(("seq", "agent", "file"), [
    (2, B, F), (0, B, F), (0, A, EXTRA), (8, B, F),
])
def test_sidecar_decisions_must_join_to_the_specific_successful_read(seq, agent, file):
    trace, audit = observed()
    changed = replace(audit, decisions=(ReadDecision(seq, agent, file, H, "ordinary"),))
    with pytest.raises(ValueError, match="trace"):
        read_evidence(trace, changed)


def test_wrong_run_broken_trace_order_and_decisions_attached_to_a_nonread_are_rejected():
    trace, audit = observed()
    with pytest.raises(ValueError, match="run_id"):
        read_evidence(trace, replace(audit, run_id="1111111111111111"))
    with pytest.raises(ValueError, match="sequences"):
        read_evidence(replace(trace, events=trace.events[1:]), audit)
    with pytest.raises(ValueError, match="trace read"):
        read_evidence(replace(trace, events=(replace(trace.events[0], tool="scan", target=H),
                                             *trace.events[1:])), audit)


def test_corroboration_rejects_reused_event_positions_and_mixed_runs():
    trace, audit = observed()
    first, *_, second = read_evidence(trace, audit)
    with pytest.raises(ValueError, match="sequence order"):
        corroborated_file_count([first, replace(second, seq=first.seq)])
    with pytest.raises(ValueError, match="one run"):
        corroborated_file_count([first, replace(second, run_id="other")])


def test_distinct_files_count_once_each_independent_of_read_order_within_one_tick():
    trace, audit = observed()
    updated = replace(audit, grants=(audit.grants[0], replace(audit.grants[1], files=())))
    reads = read_evidence(trace, updated)
    assert corroborated_file_count(reads, until_tick=5) == 0
    assert corroborated_file_count(reads, until_tick=6) == 2
