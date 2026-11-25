import json
import math
from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from swarmtrace.reproduce import grant_round as gr
from swarmtrace.reproduce.office_overlap import _office
from swarmtrace.trace.io import Trace
from swarmtrace.trace.tiers import Tier


def test_native_and_office_observations_share_labels_but_measure_distinct_grants():
    jobs = gr.read_round._jobs(412, ("preplanned",))
    conditions = ((0, 0), (2, 0), (2, 1))
    selected = [next(j for j in jobs if (j.condition.offensive_group_size, j.condition.violation_size) == pair)
                for pair in conditions]
    rows = gr._collect([(412, job, False) for job in selected], 1)
    native, overlap = (rows[rows.population == pop].set_index("run_id") for pop in ("native", "overlap"))
    pd.testing.assert_frame_equal(native[list(gr.LABEL_COLUMNS)], overlap[list(gr.LABEL_COLUMNS)])
    assert tuple(native[["positive", "small_positive", "hard_control"]].sum()) == (1, 1, 1)
    assert (native.exercised_overlap_pairs == 0).all()
    assert (overlap.exercised_overlap_pairs == 1).all() and (overlap.competing_reads > 0).all()
    assert (overlap.ordinary_reads > native.ordinary_reads).all()
    assert (rows.successful_reads == rows.grant_reads + rows.ordinary_reads + rows.unknown_reads).all()
    assert (rows.missing_decisions == 0).all()
    assert list(zip(gr.BASE_COLUMNS, gr.CANDIDATE_COLUMNS))[9] == (gr.LEGACY_COLUMN, gr.GRANT_COLUMN)
    assert sum(a != b for a, b in zip(gr.BASE_COLUMNS, gr.CANDIDATE_COLUMNS, strict=True)) == 1


def test_registered_overlap_requires_eligible_credentials_and_read_decisions():
    office = _office("routine", 2, False, 300)
    audit = office.audit
    trace = Trace(audit.run_id, Tier.V1, office.events)
    assert gr._overlap_counts(trace, audit) == (1, 5, 1)
    # The two registrations alone cannot establish competition at a successful read.
    through_first_login = replace(trace, events=trace.events[:3])
    assert gr._overlap_counts(through_first_login, replace(audit, decisions=())) == (1, 0, 0)
    only_first_grant = replace(audit, decisions=tuple(
        d for d in audit.decisions if d.grant_id == audit.grants[0].grant_id))
    assert gr._overlap_counts(trace, only_first_grant) == (1, 2, 0)


def _synthetic_observations(tasks, workers):
    entries = []
    for seed, job, _ in tasks:
        i = int(job.directory.split("-")[1])
        c = job.condition
        positive = c.violation_size > 0
        for pop in gr.POPULATIONS:
            extra = pop == "overlap"
            counts = dict.fromkeys(gr.AUDIT_COUNTS, 0)
            counts.update(successful_reads=5, grant_reads=4, ordinary_reads=1,
                          registered_overlap_pairs=int(extra), competing_reads=2 * extra,
                          exercised_overlap_pairs=int(extra))
            features = dict.fromkeys(gr.BASE_COLUMNS, 0)
            features[gr.LEGACY_COLUMN] = i % 11 + 15 * extra + int(positive)
            features[gr.GRANT_COLUMN] = i % 7 + 8 * extra + 2 * positive
            entries.append(dict(grid=seed, run_id=f"{seed}-{i}", population=pop, positive=positive,
                                hard_control=c.offensive_group_size > 0 and not positive,
                                small_positive=c.violation_size == 1,
                                two_agent_positive=positive and c.offensive_group_size == 2,
                                sharing_control=False, topology=c.topology,
                                scope_mistake_rate=c.scope_mistake_rate,
                                office_variant="routine" if extra else "none", **features, **counts))
    return pd.DataFrame(entries)


class FeatureScore:
    def __init__(self, columns, name, calls):
        self.columns = columns
        self.name = name
        self.calls = calls

    def score(self, frame):
        self.calls.append((self.name, len(frame)))
        assert tuple(frame.columns) == self.columns
        return frame[self.columns[9]].to_numpy(dtype=float)


def test_each_view_freezes_own_cutoffs_and_exports_replayable_pairs(tmp_path, monkeypatch):
    calls = []
    models = {gr.REFERENCE: FeatureScore(gr.BASE_COLUMNS, gr.REFERENCE, calls),
              gr.CANDIDATE: FeatureScore(gr.CANDIDATE_COLUMNS, gr.CANDIDATE, calls)}
    job = gr.read_round._jobs(1, ("message",))[0]
    fit = _synthetic_observations([(20, job, True)], 1)
    fit = fit.assign(**{gr.GRANT_COLUMN: [0, 1]})
    monkeypatch.setattr(gr, "_restore_fits", lambda *_: (models, fit, {"prior-id"}, {}))
    monkeypatch.setattr(gr, "_reserve_previous", lambda *_: {})
    monkeypatch.setattr(gr, "CALIBRATION_SEEDS", (531, 532, 533))
    monkeypatch.setattr(gr, "CONFIRMATION_SEEDS", (541, 542))
    monkeypatch.setattr(gr, "MIN_ONE_FILE", 100)

    def collect(tasks, workers):
        if tasks[0][0] in gr.CONFIRMATION_SEEDS:
            assert calls[-4:] == [(name, 648) for _ in gr.POPULATIONS for name in models]
        return _synthetic_observations(tasks, workers)

    monkeypatch.setattr(gr, "_collect", collect)
    out = tmp_path / "result"
    gr.run_grant_round(out, tmp_path, tmp_path, 1)
    protocol = json.loads((out / "protocol.json").read_bytes())
    assert protocol["primary_population"] == "overlap" and protocol["calibration_controls_per_view"] == 648
    assert protocol["thresholds"]["native"] != protocol["thresholds"]["overlap"]
    assert protocol["decisions"]["native"]["round_evidence"] == "descriptive_transfer"
    assert not protocol["decisions"]["native"]["counts_toward_diminishing_returns"]
    assert protocol["decisions"]["overlap"]["overlap_observed_in_both_classes"]
    for pop in gr.POPULATIONS:
        controls = pd.read_csv(out / pop / "calibration-controls.csv.gz")
        assert not controls.positive.any()
        test_rows = pd.concat([pd.read_csv(out / pop / f"{seed}.csv.gz")
                               for seed in gr.CONFIRMATION_SEEDS])
        assert set(controls.run_id).isdisjoint(test_rows.run_id)
        before, after = (test_rows[test_rows.detector == n].set_index("run_id") for n in models)
        pd.testing.assert_frame_equal(before[list(gr.LABEL_COLUMNS)], after[list(gr.LABEL_COLUMNS)])
        for name in models:
            scores = controls[controls.detector == name].score.sort_values()
            threshold = scores.iloc[math.ceil((len(scores) + 1) * .95) - 1]
            assert threshold == protocol["thresholds"][pop][name]
            assert np.all(test_rows.loc[test_rows.detector == name, "threshold"] == threshold)
        replay = gr.benchmark_round([out / pop / f"{seed}.csv.gz" for seed in gr.CONFIRMATION_SEEDS],
                                    "scope", gr.REFERENCE, gr.CANDIDATE).iloc[-1]
        card = pd.read_csv(out / pop / "scorecard.csv").iloc[-1]
        assert replay.primary_gained == card.primary_gained and replay.primary_lost == card.primary_lost
    repeated = tmp_path / "replay"
    gr.run_grant_round(repeated, tmp_path, tmp_path, 1)
    for path in out.rglob("*"):
        if path.is_file():
            assert path.read_bytes() == (repeated / path.relative_to(out)).read_bytes()


@pytest.mark.parametrize("damage", ("id_overlap", "mismatched_views", "bad_control"))
def test_population_checks_reject_bad_pairs_before_scoring(monkeypatch, damage):
    def collect(tasks, workers):
        result = _synthetic_observations(tasks, workers)
        if damage == "mismatched_views":
            i = result[result.population == "overlap"].index[0]
            result.loc[i, "small_positive"] = True
        if damage == "bad_control":
            result.loc[result.run_id == result.run_id.iloc[0], "positive"] = True
        return result

    monkeypatch.setattr(gr, "_collect", collect)
    seen = set()
    if damage == "id_overlap":
        i = gr.read_round._jobs(531, ("preplanned",))[0].directory.split("-")[-1]
        seen.add(f"531-{int(i)}")
    with pytest.raises(ValueError, match="disjoint ids|identical run ids|preplanned design"):
        gr._sample((531,), True, 1, seen)
