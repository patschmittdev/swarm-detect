from dataclasses import replace

import pandas as pd
import pytest

from swarmtrace.eval.grant_challenge import _approved_engine
from swarmtrace.features.assignment import ASSIGNMENT_COLUMNS, assignment_features
from swarmtrace.trace.authorization import ReadAudit, ReadDecision, ReadGrant
from swarmtrace.trace.context import Context, ContextLevel, HandoffScope
from swarmtrace.trace.io import Trace, read_trace
from swarmtrace.trace.schema import TraceEvent
from swarmtrace.trace.tiers import Tier


def _context(audit):
    return Context(audit.run_id, ContextLevel.C2, {}, tuple(
        HandoffScope(g.sender, g.receiver, g.host, g.files) for g in audit.grants))


def _inputs():
    a = ReadGrant("A", "issuer", "reader", "h", ("a", "c", "unread"))
    b = ReadGrant("B", "issuer", "reader", "h", ("x", "b"))
    idle = ReadGrant("idle", "issuer", "reader", "h", ())
    docs = ("a", "x", "c", "x", "x", "y", "ordinary", "a", "unknown", "missing", "denied")
    events = tuple(TraceEvent(
        1, "run", seq, seq, "reader", "read", file, {},
        {"status": "denied" if file == "denied" else "ok", "size": 0}, None, None,
    ) for seq, file in enumerate(docs))
    grants = ("A", "A", "A", "A", "B", "A", None, "B", None)
    decisions = tuple(ReadDecision(
        seq, "reader", docs[seq], "h", "grant" if grant else ("unknown" if seq == 8 else "ordinary"), grant,
    ) for seq, grant in enumerate(grants))
    audit = ReadAudit("run", (a, b, idle), decisions)
    return Trace("run", Tier.V1, events), _context(audit), audit


def test_each_exercised_grant_uses_local_distinct_files_repeat_reads_and_read_order():
    trace, context, audit = _inputs()
    bag = assignment_features(trace, context, audit)
    assert list(bag.features.columns) == list(ASSIGNMENT_COLUMNS)
    assert list(bag.features.index) == ["A", "B"]
    assert tuple(bag.features.loc["A"]) == pytest.approx((2, 2, .5, 1 / 3, 1 / 3))
    assert tuple(bag.features.loc["B"]) == pytest.approx((1, 1, .5, 0, .5))
    assert bag.capture_present
    assert (bag.grant_reads, bag.ordinary_reads, bag.unknown_reads, bag.missing_reads) == (7, 1, 2, 1)
    assert bag.successful_reads == 10


def test_unrelated_interleaved_grant_from_same_people_leaves_old_rows_identical():
    trace, context, audit = _inputs()
    baseline = assignment_features(trace, context, audit).features
    # An independently selected job uses the same reader, host, file and sender.
    unrelated = ReadGrant("other", "issuer", "reader", "h", ("x",))
    old_events = [replace(e, seq=e.seq + (e.seq >= 2)) for e in trace.events]
    old_events.insert(2, replace(trace.events[1], seq=2))
    old_decisions = [replace(d, seq=d.seq + (d.seq >= 2)) for d in audit.decisions]
    old_decisions.insert(2, ReadDecision(2, "reader", "x", "h", "grant", "other"))
    augmented = replace(audit, grants=(*audit.grants, unrelated), decisions=tuple(old_decisions))
    result = assignment_features(replace(trace, events=tuple(old_events)), _context(augmented), augmented)
    pd.testing.assert_frame_equal(baseline, result.features.loc[baseline.index])
    assert result.features.loc["other"].tolist() == [0, 1, 0, 0, 0]


def test_ordinary_ambiguous_and_absent_decisions_cannot_create_or_inflate_grant_rows():
    trace, context, audit = _inputs()
    recorded = replace(audit, decisions=(audit.decisions[6], audit.decisions[8]))
    for observed, present, ordinary, unknown, missing in (
        (None, False, 0, 10, 10), (replace(audit, decisions=()), True, 0, 10, 10),
        (recorded, True, 1, 9, 8),
    ):
        bag = assignment_features(trace, context, observed)
        assert bag.features.empty and tuple(bag.features) == ASSIGNMENT_COLUMNS
        assert bag.capture_present is present
        assert (bag.ordinary_reads, bag.unknown_reads, bag.missing_reads) == (ordinary, unknown, missing)
    complete = replace(audit, decisions=(audit.decisions[6],))
    event = replace(trace.events[6], seq=0)
    audit_ordinary = replace(complete, decisions=(replace(complete.decisions[0], seq=0),))
    bag = assignment_features(replace(trace, events=(event,)), context, audit_ordinary)
    assert bag.features.empty and bag.capture_present and bag.unknown_reads == bag.missing_reads == 0


def test_prefixes_use_only_observed_grants_and_keep_later_approval_out_of_earlier_rows():
    trace, context, audit = _inputs()
    for tick in range(-1, 11):
        full = assignment_features(trace, context, audit, until_tick=tick)
        prefix = replace(trace, events=tuple(e for e in trace.events if e.tick <= tick))
        observed = assignment_features(prefix, context, audit, until_tick=tick)
        pd.testing.assert_frame_equal(full.features, observed.features)
        assert (full.successful_reads, full.missing_reads) == (observed.successful_reads, observed.missing_reads)
    first = assignment_features(trace, context, audit, until_tick=0)
    assert first.features.index.tolist() == ["A"] and first.features.loc["A"].tolist() == [0, 1, 0, 0, 0]
    at_exclusion = assignment_features(trace, context, audit, until_tick=1)
    assert at_exclusion.features.loc["A"].tolist() == pytest.approx([1, 1, .5, 0, 1 / 3])
    # The unrelated future grant with missing C2 coverage is checked only once exercised.
    incomplete_context = replace(context, handoffs=(context.handoffs[0],))
    assignment_features(trace, incomplete_context, audit, until_tick=2)
    with pytest.raises(ValueError, match="matching C2"):
        assignment_features(trace, incomplete_context, audit)


def test_rejects_mismatched_observations_and_groups_by_checked_grant_scope():
    trace, context, audit = _inputs()
    for other in (replace(context, run_id="another"), replace(context, level=ContextLevel.C1)):
        with pytest.raises(ValueError, match="run_id|C2"):
            assignment_features(trace, other, audit)
    with pytest.raises(ValueError, match="V1"):
        assignment_features(replace(trace, tier=Tier.V0), context, audit)
    with pytest.raises(ValueError, match="run_id"):
        assignment_features(trace, context, replace(audit, run_id="other"))
    altered = replace(audit.grants[0], files=("different",))
    with pytest.raises(ValueError, match="matching C2"):
        assignment_features(trace, context, replace(audit, grants=(altered, *audit.grants[1:])))


def test_exercised_grant_with_empty_approved_list_counts_all_its_distinct_files():
    trace, _, audit = _inputs()
    empty = replace(audit.grants[0], files=())
    observed = replace(audit, grants=(empty, *audit.grants[1:]))
    bag = assignment_features(trace, _context(observed), observed)
    assert bag.features.loc["A"].tolist() == pytest.approx([4, 0, 1, .2, 0])


def test_same_scope_under_distinct_grant_ids_stays_separate_and_ids_are_only_metadata():
    trace, _, audit = _inputs()
    identical_scope = replace(audit.grants[1], files=audit.grants[0].files)
    common = replace(audit, grants=(audit.grants[0], identical_scope, audit.grants[2]))
    bag = assignment_features(trace, _context(common), common)
    assert bag.features.loc["A"].tolist() == pytest.approx([2, 2, .5, 1 / 3, 1 / 3])
    assert bag.features.loc["B"].tolist() == pytest.approx([1, 1, .5, 0, 0])
    names = {"A": "z", "B": "y", "idle": "x"}
    renamed = replace(common, grants=tuple(replace(g, grant_id=names[g.grant_id])
                                           for g in common.grants), decisions=tuple(
        replace(d, grant_id=names[d.grant_id]) if d.grant_id else d for d in common.decisions))
    result = assignment_features(trace, _context(renamed), renamed)
    pd.testing.assert_frame_equal(bag.features.rename(index=names).sort_index(), result.features)


def test_independent_approved_overlap_workflow_is_read_through_the_normal_gateway(tmp_path):
    engine = _approved_engine()
    path = tmp_path / "trace.jsonl"
    engine.run(7, path)
    audit = engine.read_audit
    bag = assignment_features(read_trace(path, Tier.V1), _context(audit), audit)
    assert bag.ordinary_reads == 1 and bag.grant_reads == 4
    assert bag.unknown_reads == bag.missing_reads == 0
    assert bag.features.excluded_files.tolist() == [0, 0]
    assert bag.features.included_files.tolist() == [1, 2]
