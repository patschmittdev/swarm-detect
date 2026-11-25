import json
from dataclasses import replace

import pandas as pd
import pytest

from swarmtrace.reproduce import assignment_support as support
from swarmtrace.trace.authorization import ReadAudit, ReadDecision, ReadGrant
from swarmtrace.trace.io import RunPaths, Trace
from swarmtrace.trace.schema import TraceEvent
from swarmtrace.trace.tiers import Tier

RUN, HOST, FILE = "f" * 16, "h-00000000", "f-00000000"
A, B, CA, CB, IA, IB = (f"a-{i:08x}" for i in range(6))


def capture(specs, grants):
    events, decisions = [], []
    for seq, (tick, actor, tool, target, grant) in enumerate(sorted(specs)):
        args = {"size": 1, "digest": "0" * 16} if tool in ("write", "send", "recv") else {}
        events.append(TraceEvent(1, RUN, seq, tick, actor, tool, target, args,
                                 {"size": 1, "status": "ok"}, None, None))
        if tool == "read" and grant != "missing":
            basis, selected = ("unknown", None) if grant == "unknown" else ("grant", grant)
            decisions.append(ReadDecision(seq, actor, target, HOST, basis, selected))
    return Trace(RUN, Tier.V1, tuple(events)), ReadAudit(RUN, tuple(grants), tuple(decisions))


def example(family="record_check", *, basis="native-a", new_version=False, acknowledgment=True,
            missing_clerk=False):
    def ticket(id_, sender, receiver):
        return ReadGrant(id_, sender, receiver, HOST, (FILE,), ("c-00000000",))

    grants = [ticket("native-a", IA, A), ticket("native-b", IB, B)]
    source = [(1, A, "read", FILE, basis), (2, B, "read", FILE, "native-b"),
              (8, A, "scan", HOST, None), (22, B, "scan", HOST, None)]
    if new_version:
        source.append((3, IA, "write", FILE, None))
    native, audit = capture(source, grants)
    mgr_a, mgr_b = (IA, IB) if family == "record_check" else (CA, CB)
    grants += [ticket("pa", IA, CA), ticket("pb", IB, CB), ticket("a1", mgr_a, A),
               ticket("a2", mgr_a, A), ticket("b1", mgr_b, B)]
    extra = [(5, CB, "read", FILE, "pb"), (11, CA, "read", FILE, "missing" if missing_clerk else "pa"),
             (15, A, "read", FILE, "a1"), (16, A, "read", FILE, "a2"), (23, B, "read", FILE, "b1")]
    if family == "clerical_handoff":
        extra += [(6, CB, "send", B, None), (9, B, "recv", CB, None), (12, CA, "send", A, None)]
        if acknowledgment:
            extra.append((14, A, "recv", CA, None))
    view, combined = capture(source + extra, grants)
    meta = dict(family=family, shared_verified_documents=int(not new_version),
                shared_reads_before_component_end=1, office_tickets=5,
                exercised_office_tickets=5 - int(missing_clerk), office_unknown_reads=0,
                office_missing_decisions=int(missing_clerk))
    return native, audit, view, combined, meta, family


@pytest.mark.parametrize("family", support.WORKFLOWS)
def test_same_native_object_and_clerk_must_match_the_actual_focal_reviewer_and_case(family):
    frozen = support._observation(*example(family))
    a = support._attribute(frozen, frozenset({A}))
    b = support._attribute(frozen, frozenset({B}))
    assert a["focal_link_status"] == b["focal_link_status"] == "observed"
    assert a["focal_multiple_ticket_keys"] == 1 and b["focal_multiple_ticket_keys"] == 0
    assert a["focal_matched_office_tickets"] == 2 and b["focal_matched_office_tickets"] == 1
    # The unrelated clerk read the same object before A's last action. A's clerk arrived later.
    assert a["focal_last_native_tick"] == 8 and a["focal_matched_clerk_reads"] == 1
    assert a["focal_timing_status"] == "none_observed" and a["focal_clerk_reads_before_end"] == 0
    assert b["focal_last_native_tick"] == 22 and b["focal_timing_status"] == "observed"
    assert a["focal_witnesses"] != b["focal_witnesses"] and b["focal_documents_with_early_clerk"] == 1
    # The later original event of another actual focal member does extend team time.
    team = support._attribute(frozen, frozenset({A, B}))
    assert team["focal_matched_keys"] == 2 and team["focal_matched_documents"] == 1
    assert team["focal_clerk_reads_before_end"] == 2


def test_final_version_receipt_and_strict_timing_are_independent():
    older = support._attribute(support._observation(*example(new_version=True)), frozenset({B}))
    assert older["focal_native_verified_keys"] == older["focal_matched_keys"] == 0
    assert older["focal_link_status"] == "none_observed"
    no_handshake = support._observation(*example("clerical_handoff", acknowledgment=False))
    a = support._attribute(no_handshake, frozenset({A, IA}))
    assert a["focal_link_status"] == "observed" and a["focal_matched_clerk_reads"] == 0
    frozen = support._observation(*example())
    at_end = support._attribute(replace(frozen, ends={B: 5}), frozenset({B}))
    assert at_end["focal_timing_status"] == "none_observed"  # same tick is not earlier


@pytest.mark.parametrize("basis", ("unknown", "missing"))
def test_unknown_missing_and_no_roster_preserve_distinct_denominators(basis):
    frozen = support._observation(*example(basis=basis, missing_clerk=True))
    a = support._attribute(frozen, frozenset({A}))
    assert a["focal_link_status"] == a["focal_timing_status"] == "unknown"
    assert a["focal_native_unknown_reads"] == 1 and a["focal_matched_keys"] == 0
    assert a["focal_native_missing_decisions"] == int(basis == "missing")
    absent = support._attribute(frozen, None)
    assert absent["focal_link_status"] == "unknown" and absent["focal_matched_keys"] is None
    assert absent["focal_last_native_tick"] is None and absent["focal_witnesses"] is None
    b = support._attribute(frozen, frozenset({B}))
    assert b["focal_link_status"] == b["focal_timing_status"] == "observed"


def test_changed_native_decision_is_rejected():
    trace, audit, view, extended, metadata, family = example()
    first = replace(extended.decisions[0], basis="unknown", grant_id=None)
    wrong = replace(extended, decisions=(first, *extended.decisions[1:]))
    with pytest.raises(ValueError, match="changed a native event or its authorization"):
        support._observation(trace, audit, view, wrong, metadata, family)


def publish_smoke(study, jobs, root):
    folder = study / "workflow"
    folder.mkdir(parents=True)
    (study / "protocol.json").write_text(json.dumps(dict(confirmation_seeds=[412], primary_view="workflow",
                                                       candidate=support.study_round.CANDIDATE)), encoding="utf-8")
    rows = []
    for job in jobs:
        paths = RunPaths(support.run_one(job.condition, job.seed, root / job.directory, capture_authorization=True))
        trace, ctx, audit = support.study_round._read(paths)
        _, _, _, meta = support.make_assignment_view(trace, ctx, audit, family="record_check")
        truth = support.grant_round._truth(paths, trace.run_id)
        rows.extend(dict(grid=412, task="scope", test_set="independent", detector=arm, view="workflow",
                         family="record_check", run_id=trace.run_id, score="unread", threshold="unread",
                         **{k: truth[k] for k in support.FLAGS}, **{k: meta[k] for k in support.PUBLISHED_COUNTS})
                    for arm in support.ARMS)
    pd.DataFrame(rows).to_csv(folder / "412.csv.gz", index=False)
    card = [dict(reference=support.study_round.REFERENCE, candidate=support.study_round.CANDIDATE,
                 population=p, source=s, positives=1, controls=2, small_positives=1, hard_controls=1)
            for p, s in (("grid", "412.csv.gz"), ("pooled", ""))]
    pd.DataFrame(card).to_csv(folder / "scorecard.csv", index=False)


def test_summary_and_complete_atomic_publication_after_all_observation_joins(tmp_path, monkeypatch):
    jobs = support.read_round._jobs(412, ("preplanned",))
    chosen = [next(j for j in jobs if (j.condition.offensive_group_size, j.condition.violation_size) == pair)
              for pair in ((0, 0), (2, 0), (2, 1))]
    monkeypatch.setattr(support.study_round, "CONFIRMATION_SEEDS", (412,))
    monkeypatch.setattr(support.read_round, "_jobs", lambda *_: chosen)
    study = tmp_path / "published"
    out = tmp_path / "secondary"
    with pytest.raises(ValueError, match="published workflow scorecard"):
        support.audit_assignment_support(study, out)
    assert not out.exists()
    publish_smoke(study, chosen, tmp_path / "originals")
    parallel = tmp_path / "parallel"
    support.audit_assignment_support(study, parallel, 2)
    phases = []
    observe, attribute = support._freeze_job, support._label_job

    def record_phase(phase, operation):
        def do(task):
            phases.append(phase)
            return operation(task)
        return do

    monkeypatch.setattr(support, "_freeze_job", record_phase("observation", observe))
    monkeypatch.setattr(support, "_label_job", record_phase("role", attribute))
    support.audit_assignment_support(study, out, 1)
    assert phases == ["observation"] * 3 + ["role"] * 3
    assert all((parallel / name).read_bytes() == (out / name).read_bytes()
               for name in ("runs.csv.gz", "summary.csv"))
    rows = pd.read_csv(out / "runs.csv.gz", dtype={"run_id": str})
    summary = pd.read_csv(out / "summary.csv")
    assert len(rows) == rows.run_id.nunique() == 3 and rows.focal_link_status.eq("observed").all()
    assert set(rows.columns).isdisjoint({"score", "threshold", "detector"})
    pooled = summary.loc[summary.family.eq("pooled")].set_index("run_class")
    assert pooled.loc["control", "runs"] == 2 and pooled.loc["positive", "runs"] == 1
    assert pooled.loc["all", "link_observed_runs"] == 3 and pooled.loc["in_scope_control", "runs"] == 1
    absent_family = summary.loc[summary.family.eq("clerical_handoff") & summary.run_class.eq("all")].iloc[0]
    assert absent_family.runs == 0 and pd.isna(absent_family.link_observed_fraction_of_all_runs)
    with pytest.raises(ValueError, match="separate, new"):
        support.audit_assignment_support(study, study / "forbidden", 1)
    corrupt = rows.copy()
    corrupt.loc[0, "office_tickets"] += 1
    with pytest.raises(ValueError, match="replayed IDs, strict labels or support counts"):
        support._validate(study, corrupt, (412,))
    card = pd.read_csv(study / "workflow/scorecard.csv", keep_default_na=False)
    card.loc[0, "controls"] += 1
    card.to_csv(study / "workflow/scorecard.csv", index=False)
    with pytest.raises(ValueError, match="strict population counts"):
        support.audit_assignment_support(study, tmp_path / "bad", 1)
    assert not (tmp_path / "bad").exists()
