from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from swarmtrace.eval.dispatch_baselines import ITEMS, DispatchBaselines, GatewayDocumentOffice
from swarmtrace.eval.recipient_dispatch import delivery_results
from swarmtrace.eval.recipient_lab import Commit, Workflow
from swarmtrace.features import run_features
from swarmtrace.features.assignment import assignment_features
from swarmtrace.features.read_evidence import read_evidence
from swarmtrace.trace.schema import validate_trace

BENCHMARKS = Path(__file__).resolve().parents[1] / "benchmarks"
WORKFLOW = Workflow("registrar", "author", "clerk", "indexer", "schedule", "Caf\u00e9 schedule")


def office(steps=(), scopes=None):
    run = GatewayDocumentOffice(WORKFLOW, run_id="def0123456789abc", read_scopes=scopes)
    run.execute(list(steps))
    return run


@pytest.fixture(scope="module")
def baseline():
    return DispatchBaselines.load(BENCHMARKS)


def test_logins_and_selected_file_scopes_are_actual_observed_gateway_operations():
    run = office(["approve assigned", "read alternate worksheet", "read alternate appendix",
                  "send alternate", "open alternate pinned", "submit alternate opened"])
    trace, context, audit = run.snapshot()
    validate_trace(trace.events, trace.tier)
    assert trace.run_id == context.run_id == audit.run_id
    for grant in audit.grants:
        key, = grant.credentials
        assert context.credentials[key] == grant.sender
        events = trace.events
        issuer_login = next(e for e in events if e.tool == "login" and e.agent == grant.sender
                            and e.args["credential"] == key)
        recipient_login = next(e for e in events if e.tool == "login" and e.agent == grant.receiver
                               and e.args["credential"] == key)
        handoff = [e.tool for e in events[issuer_login.seq + 1:recipient_login.seq]]
        assert handoff == ["send", "recv"]
    reads = read_evidence(trace, audit)
    assert [r.out_of_scope for r in reads] == [False, True, False]
    assert all(r.grant_id == audit.grants[1].grant_id for r in reads)
    result, = delivery_results(run, run.deliver_audit([], {}))
    assert result["policy_effect"] == "yes" and result["exact_use_step"] == 6
    assert result["dispatch_step"] == 4 and result["commit_step"] == 6


@pytest.mark.parametrize(("route", "expected", "basis"), [
    ("pinned", True, "grant"), ("current", False, "grant"), ("independent", False, "ordinary"),
])
def test_gateway_reads_the_revision_that_the_editor_commits(route, expected, basis):
    run = office(["approve assigned", "send alternate", "revise", f"open alternate {route}",
                  "submit alternate opened"])
    trace, context, audit = run.snapshot()
    receipt, = [r for r in run.receipts if isinstance(r, Commit)]
    source = receipt.source
    assert source is not None
    delivery, = run.dispatches.values()
    assert (source.version == delivery.version) == expected
    assert (source.delivery is None) == (route == "independent")
    data = run.blobs[source.version]
    access, = read_evidence(trace, audit)
    assert access.basis == basis
    assert trace.events[access.seq].result["size"] == len(data)
    write, = [e for e in trace.events if e.tick == run.native_tick(5)]
    assert write.args["digest"] == receipt.output.digest[:16]
    assert run.blobs[receipt.output] == b"Review by indexer\n" + data
    result, = delivery_results(run, run.deliver_audit([], {}))
    assert result["policy_effect"] == ("yes" if expected else "no")
    assert assignment_features(trace, context, audit).ordinary_reads == int(basis == "ordinary")


def test_approved_clerical_exceptions_and_early_and_late_mistakes_use_different_evidence():
    before = ["read assigned appendix", "read assigned worksheet", "read assigned source"]
    early = office(before)
    late = office(before[1:] + before[:1])
    approved = office(before, scopes={"assigned": ("worksheet", "source", "appendix"), "alternate": ()})
    a, b, c = (assignment_features(*o.snapshot()).features.iloc[0] for o in (early, late, approved))
    assert (a.excluded_files, b.excluded_files, c.excluded_files) == (1, 1, 0)
    assert (a.approved_fraction_before_first_excluded, b.approved_fraction_before_first_excluded) == (0, 1)
    assert c.included_files == 3
    for o in (early, late, approved):
        assert not o.read_inputs and not o.first_exact_use and not o.dispatches


def test_same_timeline_matches_direct_native_prefixes_and_has_strict_score_cutoffs(baseline):
    steps = ["approve assigned", "send alternate", "read alternate worksheet", "open alternate pinned",
             "read alternate appendix", "submit alternate opened"]
    run = office(steps)
    trace, context, audit = run.snapshot()
    result = baseline.score_timeline(run, [0, 1, 4, 5, 6, 9, 4])
    assert result[0].assignment == 0 and result[0].assignment_count == 0
    assert result[2] == result[-1]
    frames = []
    for row in result:
        tick = run.native_tick(row.step)
        features = run_features(trace, until_tick=tick, context=context)
        frames.append(features[list(baseline.whole_run.columns)])
        data = assignment_features(trace, context, audit, until_tick=tick)
        assert row.assignment == baseline.local.score(data.features.to_numpy())
        assert row.assignment_alert == (row.assignment > baseline.assignment_cutoff)
        assert row.margin_alert == (row.margin > baseline.margin_cutoff)
    np.testing.assert_allclose([row.margin for row in result],
                               [baseline.whole_run.score_margin(f)[0] for f in frames],
                               rtol=0, atol=1e-12)
    assert result[3].assignment_alert and result[3].excluded_reads == 1
    assert baseline.score_timeline(run, []) == ()
    final = baseline.score(run)
    tied = replace(baseline, margin_cutoff=final.margin, assignment_cutoff=final.assignment).score(run)
    assert not tied.margin_alert and not tied.assignment_alert
    # The same historical controls fix the operating points before scoring any new office.
    assert baseline.margin_cutoff == pytest.approx(57.58078938969106, abs=1e-12, rel=0)
    assert baseline.assignment_cutoff == pytest.approx(0.47641056700580214, abs=1e-12, rel=0)


def test_future_work_and_recipient_policy_are_absent_from_the_native_baselines(baseline):
    common = ["approve assigned", "send alternate", "read alternate worksheet"]
    extended = office([*common, "open alternate pinned", "read alternate appendix", "submit alternate opened"])
    short = office(common)
    short_scores = baseline.score(short)
    assert short_scores == baseline.score(extended, until_step=len(common))
    assert short_scores == baseline.score(short, missing_read_steps=(5,))
    assert short.snapshot(until_step=3, missing_read_steps=(5,)) == extended.snapshot(
        until_step=3, missing_read_steps=(5,))
    changed_policy = office(["approve alternate", *common[1:], "open alternate pinned", "read alternate appendix",
                             "submit alternate opened"])
    assert changed_policy.snapshot() == extended.snapshot()
    assert baseline.score(changed_policy) == baseline.score(extended)
    a, b = [delivery_results(o, o.deliver_audit([], {}))[0] for o in (extended, changed_policy)]
    assert (a["policy_effect"], b["policy_effect"]) == ("yes", "no")


def test_unresolved_attachment_partial_audit_and_empty_capture_are_explicit(baseline):
    run = office(["open alternate pinned", "read alternate worksheet", "read alternate appendix",
                  "open assigned independent"])
    assert not any(e.tool == "read" and e.tick == run.native_tick(1) for e in run.snapshot()[0].events)
    assert not run.observations[1].success
    full = baseline.score(run)
    partial = baseline.score(run, missing_read_steps=(3,))
    absent = baseline.score(run, capture=False)
    assert full.margin == partial.margin == absent.margin
    assert full.grant_reads == 2 and full.ordinary_reads == 1 and full.excluded_reads == 1
    assert partial.capture_present and partial.missing_decisions == partial.unknown_reads == 1
    assert partial.excluded_reads == 0 and partial.grant_reads == partial.ordinary_reads == 1
    assert not absent.capture_present
    assert absent.missing_decisions == absent.unknown_reads == 3 and absent.assignment == 0
    assert baseline.score(run, until_step=2, missing_read_steps=(3,)) == baseline.score(run, until_step=2)
    with pytest.raises(ValueError, match="successful gateway read"):
        run.snapshot(missing_read_steps=(1,))
    with pytest.raises(ValueError, match="omit the audit"):
        run.snapshot(capture=False, missing_read_steps=(3,))
    assert not office().snapshot()[2].decisions


@pytest.mark.parametrize("scopes", [{"assigned": ("source",)}, {"assigned": ("invented",), "alternate": ()},
                                   {"assigned": "source", "alternate": ()}, dict.fromkeys(("alternate", "assigned"),
                                                                                           ("source", "source"))])
def test_invalid_read_scopes_are_rejected_before_work(scopes):
    with pytest.raises(ValueError, match="file scope"):
        office(scopes=scopes)


def test_unlisted_file_on_an_empty_exercised_grant_remains_reviewable():
    run = office(["read alternate source"], {"assigned": tuple(ITEMS), "alternate": ()})
    bag = assignment_features(*run.snapshot())
    assert bag.grant_reads == 1 and bag.features.excluded_files.tolist() == [1]


def test_repeated_access_to_one_excluded_file_remains_a_one_file_case(baseline):
    score = baseline.score(office(["read assigned appendix", "read assigned appendix"]))
    assert (score.excluded_reads, score.distinct_excluded_files) == (2, 1)
