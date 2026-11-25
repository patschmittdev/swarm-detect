import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from swarmtrace.reproduce import grant_policy as policy

GR = policy.prior_round
PRIOR = Path(__file__).resolve().parents[1] / "benchmarks" / "grant-scope"


def test_exact_tolerance_rank_and_local_profile_confidence_boundary():
    rank = policy._tolerance_rank(1296)
    assert rank == 1247
    assert policy._binomial_cdf(1296 - rank, 1296, .05) == pytest.approx(.02216276623981486)
    assert policy._binomial_cdf(1296 - rank + 1, 1296, .05) == pytest.approx(.03054687787293784)
    assert policy._upper_fpr(91, 2160) == pytest.approx(.04994763440274275)
    assert policy._upper_fpr(92, 2160) == pytest.approx(.05044717507366104)
    assert policy._upper_fpr(0, 100) == pytest.approx(1 - .05 ** .01)
    assert policy._upper_fpr(4, 4) == 1.
    assert policy._upper_fpr(3, 4) == pytest.approx(.95 ** .25)
    with pytest.raises(ValueError, match="too few controls"):
        policy._tolerance_rank(30)


def test_published_fits_and_decisions_replay_from_original_scores():
    models, cutoff, seen, details = policy._restore(PRIOR)
    assert models[policy.REFERENCE].columns == GR.BASE_COLUMNS
    assert models[GR.CANDIDATE].columns == GR.CANDIDATE_COLUMNS
    assert (details["fitting_runs"], len(seen), cutoff) == (256, 11124, 0.768038747411531)
    assert all(row["rows"] == 378 and row["max_abs_score_error"] <= 1e-12
               for row in details["prior_parity"].values())
    assert sum(row["rows"] for row in details["prior_parity"].values()) == 1512


def test_published_policy_replays_from_individual_controls_and_paired_scores():
    root = PRIOR.with_name("grant-policy")
    protocol = json.loads((root / "protocol.json").read_bytes())
    numeric_text = {"run_id": str, "score": str, "threshold": str}
    columns = [*numeric_text, "detector", "positive", "small_positive", "hard_control", "routed_to_overlap"]
    view_ids = []
    for view in ("native", policy.LAYOUT):
        folder = root / view
        cal = pd.read_csv(folder / "calibration-controls.csv.gz", usecols=columns, dtype=numeric_text)
        fresh = pd.concat([pd.read_csv(folder / f"{grid}.csv.gz", usecols=columns, dtype=numeric_text)
                           for grid in protocol["confirmation_seeds"]], ignore_index=True)
        assert not cal.positive.any() and set(cal.run_id).isdisjoint(fresh.run_id)
        assert fresh.routed_to_overlap.eq(view == policy.LAYOUT).all()
        saved = pd.read_csv(folder / "scorecard.csv").iloc[-1]
        predictions = {}
        for arm in ("reference", "candidate"):
            detector = protocol[arm]
            controls = cal[cal.detector == detector]
            runs = fresh[fresh.detector == detector].set_index("run_id").sort_index()
            assert len(controls) == controls.run_id.nunique() == 1296
            assert len(runs) == runs.index.nunique() == 3780
            cutoff = protocol["native_cutoff"]
            if view == policy.LAYOUT:
                cutoff = sorted(controls.score.map(float))[1246]
                assert cutoff == protocol["overlap_thresholds"][detector]
            assert runs.threshold.map(float).eq(cutoff).all()
            alert = runs.score.map(float) > cutoff
            for metric, mask in (("small_true_positives", runs.small_positive),
                                 ("false_positives", ~runs.positive), ("hard_false_positives", runs.hard_control)):
                assert saved[f"{arm}_{metric}"] == (mask & alert).sum()
            predictions[arm] = alert
        pd.testing.assert_index_equal(predictions["reference"].index, predictions["candidate"].index)
        if view == "native":
            pd.testing.assert_series_equal(predictions["reference"], predictions["candidate"])
        view_ids.append(set(predictions["candidate"].index))
    assert view_ids[0] == view_ids[1]


def test_corrupt_fit_boolean_refused_before_other_archives(tmp_path):
    raw = pd.read_csv(PRIOR / "fitting.csv.gz", dtype=str, keep_default_na=False)
    raw.loc[0, "positive"] = "False "
    GR._write_table(tmp_path / "fitting.csv.gz", raw)
    (tmp_path / "protocol.json").write_bytes((PRIOR / "protocol.json").read_bytes())
    with pytest.raises(ValueError, match="invalid prior boolean"):
        policy._restore(tmp_path)


def test_same_issuer_smoke_has_exercised_overlaps_under_both_base_labels():
    jobs = GR.read_round._jobs(412, ("preplanned",))
    chosen = [next(j for j in jobs if j.condition.offensive_group_size == 0),
              next(j for j in jobs if j.condition.violation_size == 1)]
    rows = GR._collect([(412, job, False) for job in chosen], 1, layout=policy.LAYOUT)
    native, office = (rows[rows.population == v].set_index("run_id") for v in ("native", "overlap"))
    assert native.positive.equals(office.positive) and int(native.positive.sum()) == 1
    assert (native.exercised_overlap_pairs == 0).all() and (office.exercised_overlap_pairs > 0).all()


class Scalar:
    def __init__(self, name):
        self.columns = (name,)

    def score(self, features):
        return features.iloc[:, 0].to_numpy(dtype=float)


def models():
    return {policy.REFERENCE: Scalar("before"), GR.CANDIDATE: Scalar("after")}


def test_routing_uses_exercised_grants_on_each_run_and_preserves_fallback_ties():
    rows = pd.DataFrame({"before": [.5, .6, .7, .7], "after": [1., .9, 0., .8],
                         "exercised_overlap_pairs": [0, 1, 0, 2]})
    thresholds = {policy.REFERENCE: .65, policy.CANDIDATE: .8}
    result = policy._routed(rows, models(), .5, thresholds)
    base, routed = (result[result.detector == n] for n in (policy.REFERENCE, policy.CANDIDATE))
    assert base.score.tolist() == [.5, .6, .7, .7] and routed.score.tolist() == [.5, .9, .7, .8]
    assert base.threshold.tolist() == [.5, .65, .5, .65] and routed.threshold.tolist() == [.5, .8, .5, .8]
    assert (routed.score > routed.threshold).tolist() == [False, True, True, False]


def _fake_view(seed, view, controls_only, alerts):
    controls = 216
    i = np.arange(controls if controls_only else 378)
    positive = i >= controls
    one_file = (i >= controls) & (i < controls + 54)
    if controls_only:
        before, after = .4 + (i % 100) / 200, .2 + (i % 100) / 200
    else:
        before = np.where(positive, (~one_file | (i % 2 == 0)) * .99, i < alerts)
        after = np.where(positive, .99, i < alerts)
    return pd.DataFrame({
        "run_id": [f"{seed}-{x}" for x in i], "grid": seed, "population": view,
        "exercised_overlap_pairs": int(view == policy.LAYOUT), "positive": positive,
        "hard_control": i < 54, "small_positive": one_file,
        "two_agent_positive": positive & ~one_file & (i < 324),
        "sharing_control": ~positive & (i >= 54) & (i < 75), "topology": "hub",
        "scope_mistake_rate": 0, "before": before, "after": after,
    })


@pytest.mark.parametrize(("alerts", "decision"), [(6, "qualified_local_profile"),
                                                   (10, "insufficient_fpr_confidence")])
def test_frozen_cutoffs_rank_gain_and_exact_budget_are_separate_gates(tmp_path, monkeypatch, alerts, decision):
    monkeypatch.setattr(policy, "CALIBRATION_SEEDS", tuple(range(101, 107)))
    monkeypatch.setattr(policy, "CONFIRMATION_SEEDS", tuple(range(108, 118)))
    monkeypatch.setattr(policy, "_restore", lambda *_: (models(), .6, set(), {}))
    phases = []

    def sample(seeds, controls_only, workers, seen):
        phases.append((seeds, controls_only))
        return {view: pd.concat([_fake_view(s, view, controls_only, alerts) for s in seeds],
                                ignore_index=True) for view in ("native", policy.LAYOUT)}

    monkeypatch.setattr(policy, "_sample", sample)
    output = tmp_path / "study"
    policy.run_grant_policy(output, tmp_path, 1)
    assert phases == [(policy.CALIBRATION_SEEDS, True), (policy.CONFIRMATION_SEEDS, False)]
    p = json.loads((output / "protocol.json").read_bytes())
    assert p["calibration_rank_one_based"] == 1247 and p["max_calibration_scores_strictly_above_cutoff"] == 49
    study = p["decisions"][policy.LAYOUT]
    assert study["round_evidence"] == decision and study["paired_evidence"] == "promising"
    assert study["qualified_local_profile"] is (alerts == 6)
    assert study["grids_gaining"] == 10 and study["one_file_runs"] == 540
    assert p["decisions"]["native"]["native_fallback_parity_verified"]
    raw = pd.read_csv(output / policy.LAYOUT / "calibration-controls.csv.gz")
    assert not raw.positive.any()
    for arm in (policy.REFERENCE, policy.CANDIDATE):
        rows = raw[raw.detector == arm]
        assert np.sort(rows.score)[1246] == pytest.approx(p["overlap_thresholds"][arm])
        assert p["overlap_calibration_alerts"][arm] == (rows.score > rows.threshold).sum()
    stats = pd.read_csv(output / policy.LAYOUT / "diagnostics.csv").set_index(["grid", "detector"])
    assert stats.loc[("pooled", policy.CANDIDATE), "false_positives"] == alerts * 10
    card = pd.read_csv(output / policy.LAYOUT / "scorecard.csv").iloc[-1]
    assert card.primary_gained == 270 and card.primary_lost == 0


def test_failed_layout_or_calibration_cannot_open_confirmation_or_publish(tmp_path, monkeypatch):
    monkeypatch.setattr(policy, "CALIBRATION_SEEDS", (301,))
    monkeypatch.setattr(policy, "CONFIRMATION_SEEDS", (303,))
    monkeypatch.setattr(policy, "_restore", lambda *_: (models(), .6, set(), {}))

    def sample(seeds, controls_only, workers, seen):
        assert controls_only
        return {view: _fake_view(seeds[0], view, False, 6) for view in ("native", policy.LAYOUT)}

    monkeypatch.setattr(policy, "_sample", sample)
    with pytest.raises(ValueError, match="strict controls"):
        policy.run_grant_policy(tmp_path / "result", tmp_path, 1)
    assert not (tmp_path / "result").exists()
