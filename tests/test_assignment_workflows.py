from dataclasses import replace

import pytest

from swarmtrace.agents.base import Action
from swarmtrace.features.read_evidence import read_evidence
from swarmtrace.reproduce.assignment_workflows import WORKFLOWS, make_assignment_view
from swarmtrace.reproduce.grant_round import _overlap_counts
from swarmtrace.reproduce.office_overlap import _Clerk
from swarmtrace.reproduce.read_round import _jobs
from swarmtrace.sim.engine import Engine
from swarmtrace.sim.runner import run_one
from swarmtrace.trace.authorization import ReadAudit, ReadGrant, read_authorization
from swarmtrace.trace.context import Context, ContextLevel, HandoffScope, read_context
from swarmtrace.trace.io import RunPaths, Trace, read_trace
from swarmtrace.trace.schema import validate_trace
from swarmtrace.trace.tiers import Tier, project
from swarmtrace.world import Credential, File, Host, World
from swarmtrace.world.authorization import ReadGateway


def native_case(path, *, components=1, basis="grant", rewrite=False):
    hosts, files, keys, directory, owners, staff, grants = {}, {}, {}, {}, {}, {}, []
    for i in range(components):
        h, f, k = (f"{prefix}-{i:08x}" for prefix in ("h", "f", "c"))
        issuer, reviewer = (f"a-{2 * i + j:08x}" for j in range(2))
        hosts[h], keys[k] = Host(h, "records", ()), Credential(k, h)
        files[f] = File(f, h, "/records/cover", "v1")
        issuer_work = {0: Action("scan", h), 29: Action("scan", h)}
        review_work = {1: Action("login", h, {"credential": k}), 3: Action("read", f),
                       21: Action("scan", h)}
        if rewrite:
            issuer_work[6] = Action("write", f, content="revised record")
            review_work[8] = Action("read", f)
        if basis == "grant":
            grants.append(ReadGrant(f"native-{i}", issuer, reviewer, h, (f,), (k,)))
        owner = reviewer if basis == "ordinary" else issuer
        directory[k] = owner
        owners[issuer, reviewer] = (owner, k)
        staff[issuer], staff[reviewer] = _Clerk(issuer_work), _Clerk(review_work)
    world = World(hosts, files, keys, frozenset({"records"}))
    for (issuer, reviewer), (owner, key) in owners.items():
        world.add_agent(issuer, zones=("records",), credentials=(key,) if owner == issuer else ())
        world.add_agent(reviewer, credentials=(key,) if owner == reviewer else ())
        if owner == issuer:
            world.handover(issuer, reviewer, key)
    engine = Engine(world, staff, 412, read_grants=tuple(grants))
    events = engine.run(30, path)
    audit = engine.read_audit
    context = Context(audit.run_id, ContextLevel.C2, directory,
                      tuple(HandoffScope(g.sender, g.receiver, g.host, g.files) for g in grants))
    return Trace(audit.run_id, Tier.V1, tuple(project(e, Tier.V1) for e in events)), context, audit


def verify_native(trace, audit, view, extended):
    validate_trace(view.events, Tier.V1)
    got = {(e.agent, e.tick): e for e in view.events}
    assert len(got) == len(view.events)
    positions = [got[e.agent, e.tick] for e in trace.events]
    assert [e.seq for e in positions] == sorted(e.seq for e in positions)
    assert tuple(replace(e, seq=i) for i, e in enumerate(positions)) == trace.events
    records = {d.seq: d for d in extended.decisions}
    original = {d.seq: d for d in audit.decisions}
    for native, restored in enumerate(positions):
        if native in original:
            assert replace(records[restored.seq], seq=native) == original[native]
        else:
            assert restored.seq not in records
    original_calls = {(e.agent, e.tick) for e in trace.events}
    return [e for e in view.events if (e.agent, e.tick) not in original_calls]


@pytest.mark.parametrize("family", WORKFLOWS)
def test_interleaves_actual_gateway_reads_with_every_native_component(tmp_path, monkeypatch, family):
    trace, context, audit = native_case(tmp_path / "base", components=2, rewrite=True)
    calls = []
    gateway_read = ReadGateway.read

    def observe(self, seq, agent, file, selected):
        calls.append((agent, file, selected))
        return gateway_read(self, seq, agent, file, selected)

    monkeypatch.setattr(ReadGateway, "read", observe)
    view, assignments, extended, support = make_assignment_view(trace, context, audit, family=family)
    added = verify_native(trace, audit, view, extended)
    extra_grants = extended.grants[len(audit.grants):]
    by_id = {g.grant_id: g for g in extra_grants}
    records = [d for d in extended.decisions if d.grant_id in by_id]
    assert sorted(calls) == sorted((d.agent, d.file, d.grant_id) for d in records)
    assert len(calls) == support["office_reads"] == len([e for e in added if e.tool == "read"])
    assert {d.grant_id for d in records} == set(by_id)
    assert all(d.file in by_id[d.grant_id].files for d in records)
    assert len(assignments.handoffs) == len(extended.grants)
    assert support["native_components"] == support["anchored_components"] == 2
    assert support["shared_verified_documents"] == support["shared_reviewer_host_pairs"] == 2
    assert support["exercised_office_tickets"] == support["office_tickets"] == len(by_id)
    assert support["support_kind"] == "native_grant"
    assert not support["fallback"] and not support["no_safe_interleave"]
    assert support["office_unknown_reads"] == support["office_missing_decisions"] == 0
    assert support["office_reads_before_native_end"] >= support["witnessed_reads_before_component_end"]
    assert support["witnessed_reads_before_component_end"] == support["shared_reads_before_component_end"] >= 2
    assert _overlap_counts(view, extended)[2] >= 2
    assert not {e.target for e in added if e.tool == "write"}.intersection(g.files[0] for g in audit.grants)
    native_ends = {a: max(e.tick for e in trace.events if e.agent == a) for a in trace.agents}
    assert all(e.tick > native_ends[e.agent] for e in added if e.agent in native_ends)
    for native in audit.grants:
        # Every new read sees the covered, revised version after its native witness.
        same_file = [e for e in added if e.tool == "read" and e.target == native.files[0]]
        assert min(e.tick for e in same_file) > 8
        assert {e.result["size"] for e in same_file} == {len("revised record")}
        focal = [g for g in extra_grants if (g.receiver, g.host) == (native.receiver, native.host)]
        assert 2 <= len(focal) <= 4
        assert all(any(d.grant_id == g.grant_id and d.file == native.files[0] for d in records) for g in focal)
    assert all(r.out_of_scope is False for r in read_evidence(view, extended))
    # The native read basis before and after the inserted clerk calls survived byte-for-byte.
    assert extended.grants[:len(audit.grants)] == audit.grants


def test_receipt_and_written_memo_connect_the_clerk_and_native_reviewer(tmp_path):
    trace, context, audit = native_case(tmp_path / "base")
    view, _, extended, support = make_assignment_view(trace, context, audit, family="clerical_handoff")
    added = verify_native(trace, audit, view, extended)
    memo, = [e for e in added if e.tool == "write"]
    sent, = [e for e in added if e.tool == "send"]
    receipt, = [e for e in added if e.tool == "recv"]
    assert memo.agent == sent.agent == receipt.target
    assert receipt.agent == sent.target == audit.grants[0].receiver
    assert memo.tick < sent.tick < receipt.tick
    assert sent.args == receipt.args and sent.result == receipt.result
    use = [e for e in added if e.tool == "read" and e.target == memo.target]
    assert len(use) >= 2 and all(e.agent == receipt.agent and e.tick > receipt.tick for e in use)
    assert support["message_handoffs"] == 1
    record, _, _, status = make_assignment_view(trace, context, audit, family="record_check")
    assert status["message_handoffs"] == 0 and all(e.tool not in ("send", "recv") for e in record.events)


def test_missing_evidence_and_no_safe_window_are_explicit(tmp_path):
    trace, context, audit = native_case(tmp_path / "base")
    short = replace(trace, events=tuple(e for e in trace.events if e.tick <= 3))
    partial = replace(audit, decisions=())
    view, _, extended, support = make_assignment_view(short, context, partial, family="record_check")
    added = verify_native(short, partial, view, extended)
    assert view.events[:len(short.events)] == short.events
    assert min(e.tick for e in added) > short.events[-1].tick
    assert support["no_safe_interleave"] and support["office_reads_before_native_end"] == 0
    assert support["support_kind"] == "native_grant" and support["shared_verified_documents"] == 0
    assert read_evidence(view, extended)[0].basis == "unknown"


def test_a_dormant_grant_does_not_establish_native_support(tmp_path):
    trace, context, audit = native_case(tmp_path / "base", basis="ordinary")
    source = audit.decisions[0]
    dormant = ReadGrant("inactive", trace.events[0].agent, source.agent, source.host,
                        (source.file,), ("c-ffffffff",))
    _, _, _, support = make_assignment_view(trace, context, replace(audit, grants=(dormant,)),
                                             family="record_check")
    assert support["native_components"] == 1 and support["anchored_components"] == 0
    assert support["fallback"] and support["support_kind"] == "ordinary_read"


def test_finds_safe_window_when_another_permitted_document_arrives_late(tmp_path):
    trace, context, audit = native_case(tmp_path / "base")
    original = audit.decisions[0]
    existing = trace.events[original.seq]
    late = replace(existing, target="f-12345678", tick=28, seq=trace.events[-1].seq)
    trace = replace(trace, events=(*trace.events[:-1], late, replace(trace.events[-1], seq=late.seq + 1)))
    grant = replace(audit.grants[0], files=(original.file, late.target))
    audit = replace(audit, grants=(grant,), decisions=(original, replace(original, seq=late.seq, file=late.target)))
    for key in ("one", "two", "three"):
        view, _, extended, support = make_assignment_view(trace, context, audit, family="record_check", variant_key=key)
        added = verify_native(trace, audit, view, extended)
        assert any(e.tool == "read" and e.target == original.file and e.tick < 28 for e in added)
        assert not support["no_safe_interleave"] and support["shared_reads_before_component_end"] > 0


@pytest.mark.parametrize(("basis", "expected"), [("ordinary", "ordinary_read"), ("unknown", "witnessed_read")])
def test_no_registered_grant_still_shares_a_witnessed_native_object(tmp_path, basis, expected):
    trace, context, audit = native_case(tmp_path / "base", basis=basis)
    view, _, extended, support = make_assignment_view(trace, context, audit, family="record_check")
    verify_native(trace, audit, view, extended)
    assert support["fallback"] and support["support_kind"] == expected
    assert support["native_components"] == support["anchored_components"] == support["shared_verified_documents"] == 0
    assert support["shared_reviewer_host_pairs"] == 1
    assert support["witnessed_reads_before_component_end"] > 0 and support["shared_reads_before_component_end"] == 0
    assert support["office_unknown_reads"] == 0 and read_evidence(view, extended)[0].basis == basis


@pytest.mark.parametrize(("original_tool", "kind"), [("scan", "actor_host"), ("read", "actor_only")])
def test_without_hosted_document_preserves_coverage_limits(tmp_path, original_tool, kind):
    trace, context, _ = native_case(tmp_path / "base")
    e = next(e for e in trace.events if e.tool == original_tool)
    trace = replace(trace, events=(replace(e, seq=0),))
    audit = ReadAudit(trace.run_id, (), ())
    view, _, recovered, support = make_assignment_view(trace, replace(context, handoffs=()), audit,
                                                       family="clerical_handoff")
    verify_native(trace, audit, view, recovered)
    assert support["support_kind"] == kind and support["fallback"]
    assert support["no_safe_interleave"] and not support["shared_verified_documents"]
    assert support["shared_reviewer_host_pairs"] == int(kind == "actor_host")


@pytest.mark.parametrize("family", WORKFLOWS)
def test_label_blind_ticket_load_varies_on_the_same_native_input(tmp_path, family):
    trace, context, audit = native_case(tmp_path / "base")
    before = (trace, context, audit)
    counts = set()
    for i in (0, 1, 3, 8, 38):
        v = make_assignment_view(*before, family=family, variant_key=str(i))
        counts.add(v[-1]["office_tickets"])
        if i == 0:
            assert v == make_assignment_view(*before, family=family, variant_key=str(i))
    assert len(counts) == 3
    assert not set(context.credentials).intersection(
        credential for grant in v[2].grants[len(audit.grants):] for credential in grant.credentials)


def test_mismatched_ambiguous_or_broken_source_is_rejected(tmp_path):
    trace, context, audit = native_case(tmp_path / "base")
    with pytest.raises(ValueError, match="unknown assignment family"):
        make_assignment_view(trace, context, audit, family="anything")
    with pytest.raises(ValueError, match="matching read audit"):
        make_assignment_view(trace, replace(context, run_id="other"), audit, family="record_check")
    with pytest.raises(ValueError, match="differs from the trace"):
        make_assignment_view(trace, context, replace(audit, decisions=(replace(audit.decisions[0], seq=0),)),
                             family="record_check")
    e = trace.events[-1]
    extra = replace(e, seq=len(trace.events))
    with pytest.raises(ValueError, match="one call per actor"):
        make_assignment_view(replace(trace, events=(*trace.events, extra)), context, audit, family="record_check")


def test_both_families_on_native_preplanned_development_examples(tmp_path):
    jobs = _jobs(412, ("preplanned",))
    for group_size, violation in ((0, 0), (2, 1)):
        job = next(j for j in jobs if (j.condition.offensive_group_size, j.condition.violation_size)
                   == (group_size, violation))
        paths = RunPaths(run_one(job.condition, job.seed, tmp_path / job.directory, capture_authorization=True))
        trace, context = read_trace(paths.trace, Tier.V1), read_context(paths.context)
        audit = read_authorization(paths.authorization)
        for family in WORKFLOWS:
            view, _, extended, support = make_assignment_view(trace, context, audit, family=family)
            verify_native(trace, audit, view, extended)
            assert support["shared_verified_documents"] > 0 and support["shared_reads_before_component_end"] > 0
            assert support["exercised_office_tickets"] == support["office_tickets"]
