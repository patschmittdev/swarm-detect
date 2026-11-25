from dataclasses import replace

import pytest

from swarmtrace.features.grant_scope import grant_scope_counts
from swarmtrace.features.read_evidence import read_evidence
from swarmtrace.reproduce.office_overlap import VARIANTS, _office, with_office_overlap
from swarmtrace.trace.io import Trace
from swarmtrace.trace.schema import validate_trace
from swarmtrace.trace.tiers import Tier


@pytest.mark.parametrize("variant", VARIANTS)
@pytest.mark.parametrize(("documents", "reverse"), [(1, False), (3, True)])
def test_background_truth_and_active_grants(variant, documents, reverse):
    case = _office(variant, documents, reverse, 0xfd000000)
    reads = read_evidence(Trace(case.audit.run_id, Tier.V1, case.events), case.audit)
    stats = grant_scope_counts(reads)
    assert {r.grant_id for r in reads if r.basis == "grant"} == {g.grant_id for g in case.audit.grants}
    assert stats.max_files_per_grant == int(variant == "mistake")
    assert stats.unknown_reads == int(variant == "unbound")
    assert stats.ordinary_reads == 1 and stats.successful_reads == 2 * documents + 2


@pytest.mark.parametrize("variant", VARIANTS)
def test_new_layout_uses_one_issuer_and_shared_approved_document(variant):
    office = _office(variant, 2, False, 0xfd000000, "same_issuer")
    first, second = office.audit.grants
    assert (first.sender, first.receiver, first.credentials) == (second.sender, second.receiver, second.credentials)
    shared, = set(first.files).intersection(second.files)
    reads = read_evidence(Trace(office.audit.run_id, Tier.V1, office.events), office.audit)
    uses = [r for r in reads if r.file == shared]
    assert {r.grant_id for r in uses} == {first.grant_id, second.grant_id}
    assert all(r.out_of_scope is False for r in uses)
    stats = grant_scope_counts(reads)
    assert stats.max_files_per_grant == int(variant == "mistake")
    assert stats.unknown_reads == int(variant == "unbound")


def test_merging_disjoint_teams_preserves_native_reads_and_missing_decisions():
    # Giving the native team the template's default namespace forces collision resolution.
    native = _office("routine", 2, True, 0xfd000000)
    trace = Trace(native.audit.run_id, Tier.V1, native.events)
    partial = replace(native.audit, decisions=native.audit.decisions[1:])
    observed, context, audit, variant = with_office_overlap(trace, native.context, partial)
    assert (observed, context, audit, variant) == with_office_overlap(trace, native.context, partial)
    validate_trace(observed.events, tier=Tier.V1)
    native_actors = set(trace.agents)
    actual = [e for e in observed.events if e.agent in native_actors]
    assert tuple(replace(e, seq=i) for i, e in enumerate(actual)) == native.events
    assert len(set(observed.agents) - native_actors) == 3
    assert len(context.handoffs) == len(audit.grants) == 4
    original = read_evidence(trace, partial)
    recovered = [r for r in read_evidence(observed, audit) if r.agent in native_actors]
    assert [replace(r, seq=e.seq) for r, e in zip(recovered, original, strict=True)] == original


def test_composition_rejects_unmatched_or_malformed_observations():
    office = _office("approved_exception", 1, False, 0xfd000000)
    trace = Trace(office.audit.run_id, Tier.V1, office.events)
    with pytest.raises(ValueError, match="matching"):
        with_office_overlap(trace, replace(office.context, run_id="elsewhere"), office.audit)
    with pytest.raises(ValueError, match="contiguous"):
        with_office_overlap(replace(trace, events=trace.events[1:]), office.context, office.audit)
