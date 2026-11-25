import json
from copy import deepcopy
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from swarmtrace.eval.assignment_round import COUNT_COLUMNS, FAMILIES, FLAG_COLUMNS
from swarmtrace.features.assignment import ASSIGNMENT_COLUMNS
from swarmtrace.reproduce import assignment_margin as study
from swarmtrace.reproduce import assignment_round as original
from swarmtrace.reproduce import read_calibration

BENCHMARKS = Path(__file__).resolve().parents[1] / "benchmarks"
ORIGINAL = BENCHMARKS / "assignment"
MARGINS = {"native": (1.5414546633478383, 1.477519040365805),
           "workflow": (57.58078938969106, 31.023514919995613)}


@pytest.fixture(scope="module")
def prepared(tmp_path_factory):
    folder = tmp_path_factory.mktemp("margin-calibration")
    return folder, study._prepare(ORIGINAL, BENCHMARKS, folder)


def test_published_fresh_scores_replay_from_raw_whole_run_and_assignment_inputs(prepared):
    root = BENCHMARKS / "assignment-margin"
    protocol = json.loads((root / "protocol.json").read_bytes())
    _, (models, local, historical, replay_protocol) = prepared
    assert protocol["unique_ids_including_confirmation"] == 25488
    for view in original.VIEWS:
        old_ids = set(pd.read_csv(ORIGINAL / view / "calibration-controls.csv.gz", usecols=["run_id"], dtype=str).run_id)
        for grid in original.CONFIRMATION_SEEDS:
            old_ids.update(pd.read_csv(ORIGINAL / view / f"{grid}.csv.gz", usecols=["run_id"], dtype=str).run_id)
        raw = pd.concat([pd.read_csv(root / view / f"{grid}.csv.gz", dtype=str, keep_default_na=False)
                         for grid in study.CONFIRMATION_SEEDS])
        base = raw.loc[raw.detector == study.REFERENCE].set_index("run_id").sort_index()
        assert base.index.is_unique and len(base) == 3780
        assert set(base.index).isdisjoint(historical | old_ids)
        scores = study._whole_scores(base, models)
        bags = pd.read_csv(root / view / "independent-assignments.csv.gz", dtype=str, keep_default_na=False)
        assert not bags.duplicated(["run_id", "grant_id"]).any()
        inputs = bags[list(ASSIGNMENT_COLUMNS)].apply(lambda col: col.map(float))
        grouped = inputs.groupby(bags.run_id)
        np.testing.assert_array_equal(grouped.size().reindex(base.index, fill_value=0), base.assignment_count.map(int))
        scores[study.CANDIDATE] = grouped.apply(lambda g: local.score(g.to_numpy())).reindex(
            base.index, fill_value=0.).to_numpy()
        points = pd.read_csv(root / view / "operating-points.csv")
        for arm, expected in scores.items():
            actual = raw.loc[raw.detector == arm].set_index("run_id").sort_index()
            assert actual.index.equals(base.index)
            archived = actual.score.map(float).to_numpy()
            np.testing.assert_allclose(expected, archived, atol=study.SCORE_TOLERANCE, rtol=0.)
            cutoff = protocol["cutoffs"][view][arm]
            assert actual.threshold.map(float).eq(cutoff).all()
            flagged = expected > replay_protocol["cutoffs"][view][arm]
            np.testing.assert_array_equal(flagged, archived > cutoff)
            pooled = points.loc[points.family.eq("pooled") & points.detector.eq(arm)].iloc[0]
            assert pooled.true_positives == (flagged & base.positive.eq("True")).sum()
            assert pooled.one_file_detections == (flagged & base.small_positive.eq("True")).sum()
            assert pooled.false_positives == (flagged & base.positive.eq("False")).sum()
            assert pooled.hard_false_positives == (flagged & base.hard_control.eq("True")).sum()


def test_original_controls_and_strict_alert_ids_replay_before_fresh(prepared):
    tmp_path, (_, _, seen, protocol) = prepared
    assert len(seen) == 16200 + 1728 + 3780
    assert json.loads((tmp_path / "calibration.json").read_bytes()) == protocol
    assert protocol["history_counts"]["reserved_before_fresh"] == 21708
    assert len(protocol["assignment_study_input_sha256"]) == 25
    published = json.loads((ORIGINAL / "protocol.json").read_bytes())
    for view in original.VIEWS:
        archived = pd.read_csv(ORIGINAL / view / "calibration-controls.csv.gz", dtype=str)
        release = pd.read_csv(BENCHMARKS / "assignment-margin" / view / "calibration-controls.csv.gz", dtype=str)
        replay = pd.read_csv(tmp_path / view / "calibration-controls.csv.gz", dtype=str)
        assert set(replay.run_id) == set(archived.run_id) <= seen
        assert len(replay) == 5 * replay.run_id.nunique() == 8640
        for arm in (original.REFERENCE, original.VERIFIED, study.CANDIDATE):
            actual = replay[replay.detector == arm].set_index("run_id").score.map(float).sort_index()
            expected = archived[archived.detector == arm].set_index("run_id").score.map(float).sort_index()
            assert actual.index.equals(expected.index)
            np.testing.assert_allclose(actual, expected, atol=study.SCORE_TOLERANCE, rtol=0.)
            effective = protocol["cutoffs"][view][arm]
            assert sorted(actual)[1659] == effective
            assert (actual > effective).equals(expected > published["cutoffs"][view][arm])
            checks = protocol["original_score_replay"][view][arm]
            assert checks["bitwise_equal_archived_scores"] == int((actual == expected).sum())
            assert checks["scores_equal_one"] == int(actual.eq(1.).sum())
        for arm, threshold in zip((study.REFERENCE, study.VERIFIED_MARGIN), MARGINS[view], strict=True):
            rows = replay[replay.detector == arm].set_index("run_id").sort_index()
            expected = release[release.detector == arm].set_index("run_id").sort_index()
            effective = protocol["cutoffs"][view][arm]
            assert effective == sorted(rows.score.map(float))[1659]
            assert rows.threshold.map(float).eq(effective).all() and expected.threshold.map(float).eq(threshold).all()
            assert rows.index.equals(expected.index)
            np.testing.assert_allclose(rows.score.map(float), expected.score.map(float), rtol=0.,
                                       atol=study.SCORE_TOLERANCE)
            assert (rows.score.map(float) > effective).equals(expected.score.map(float) > threshold)
        source = f"{view}/calibration-controls.csv.gz"
        assert protocol["assignment_study_input_sha256"][source] == read_calibration._sha256(ORIGINAL / source)
    with pytest.raises(ValueError, match="disjoint"):
        read_calibration._reserve(pd.Index([next(iter(seen))]), seen)


def test_operating_replay_rejects_one_ulp_reassignment_of_a_control_alert(monkeypatch):
    monkeypatch.setattr(study, "RANK", 2)
    arm = original.REFERENCE
    ids = pd.Index(["a", "b", "c"])
    high = np.nextafter(.5, np.inf)
    saved = np.array([.1, .5, high])
    arms = {arm: pd.DataFrame({"score": saved, "threshold": [.5] * 3}, index=ids)}
    # All three scores meet the numerical tolerance. Swapping a tie changes who is flagged.
    with pytest.raises(ValueError, match="strict control flags"):
        study._control_parity({arm: saved[[0, 2, 1]]}, {arm: .5}, arms, {arm: .5}, ids, "native")


def test_provenance_tolerates_only_bounded_numerical_diagnostics():
    saved = {"prior_score_error_tolerance": study.SCORE_TOLERANCE, "fit_sha256": "original",
             "prior_parity": {"fit": {"rows": 50, "alert_count": 4, "max_abs_score_error": 0.}}}
    live = deepcopy(saved)
    live["prior_parity"]["fit"]["max_abs_score_error"] = 1e-15
    study._check_provenance(saved, live)
    for key, changed in (("alert_count", 5), ("rows", 49), ("max_abs_score_error", 1e-9),
                         ("max_abs_score_error", float("nan"))):
        altered = deepcopy(live)
        altered["prior_parity"]["fit"][key] = changed
        with pytest.raises(ValueError):
            study._check_provenance(saved, altered)
    with pytest.raises(ValueError):
        study._check_provenance(saved, {**live, "fit_sha256": "different"})


def test_invalid_assignment_scales_and_original_protocol_are_rejected():
    prior = json.loads((ORIGINAL / "protocol.json").read_bytes())
    with pytest.raises(ValueError, match="frozen"):
        study._restore_local({**prior, "rank_one_based": 1659})
    prior["model"]["scale"][0] = 0
    with pytest.raises(ValueError):
        study._restore_local(prior)


def test_strict_alerts_include_a_one_ulp_margin_gain_and_the_exact_fpr_bound():
    frame = pd.DataFrame({
        "family": [FAMILIES[0], FAMILIES[0], FAMILIES[1], FAMILIES[1]],
        "positive": [True, False, True, False], "small_positive": [True, False, True, False],
        "hard_control": [False, True, False, True],
    })
    cutoff = 51.
    scores = np.array([np.nextafter(cutoff, np.inf), cutoff, cutoff, np.nextafter(cutoff, np.inf)])
    card = study._operating_points(frame, {"margin": scores}, {"margin": cutoff}).set_index("family")
    pooled = card.loc["pooled"]
    assert (pooled.true_positives, pooled.false_positives, pooled.hard_false_positives) == (1, 1, 1)
    assert pooled.exact_fpr_upper == study.grant_policy._upper_fpr(1, 2)
    assert not pooled.exact_fpr_bound_met and card.loc[FAMILIES[0]].false_positives == 0


def test_runner_exports_and_reports_only_artificial_cases_without_opening_grid_seeds(tmp_path, monkeypatch):
    seeds = (81, 82)
    monkeypatch.setattr(study, "CONFIRMATION_SEEDS", seeds)
    monkeypatch.setattr(study, "ORIGINAL_TEST_COUNT", 8)
    ids = {f"{i:016x}" for i in range(8)}

    class Scores:
        columns = ("feature",)

        def score(self, data):
            return 1 / (1 + np.exp(-data.feature.to_numpy()))

        def score_margin(self, data):
            return data.feature.to_numpy()

    class Local:
        def score(self, bag):
            return float(bag[0, 0])

    def prepare(_study, _benchmarks, stage):
        arms = (original.REFERENCE, original.VERIFIED, study.REFERENCE, study.VERIFIED_MARGIN, study.CANDIDATE)
        calibration = {"cutoffs": {v: dict.fromkeys(arms, .5) for v in original.VIEWS},
                       "family_by_grid": dict(zip(map(str, seeds), FAMILIES, strict=True)),
                       "history_counts": {"reserved_before_fresh": 1}}
        (stage / "calibration.json").write_text(json.dumps(calibration))
        return {arm: Scores() for arm in study.WHOLE_RUN}, Local(), {"previous-id"}, calibration

    def sample(requested, controls_only, workers, seen):
        assert requested == seeds and not controls_only and workers == 1
        read_calibration._reserve(pd.Index(sorted(ids)), seen)
        samples = []
        for i, run in enumerate(sorted(ids)):
            group = i // 4
            positive = i % 2 == 0
            row = dict(run_id=run, feature=float(positive), positive=positive, small_positive=positive,
                       hard_control=not positive, grid=seeds[group], family=FAMILIES[group],
                       **dict.fromkeys(COUNT_COLUMNS, 1), **dict.fromkeys(FLAG_COLUMNS, False))
            samples.append(original._Sample(row, ("grant",), np.full((1, 5), float(positive))))
        return {view: samples for view in original.VIEWS}

    monkeypatch.setattr(study, "_prepare", prepare)
    monkeypatch.setattr(original, "_sample", sample)
    out = tmp_path / "fresh-fake"
    study.run_assignment_margin(ORIGINAL, BENCHMARKS, out, workers=1)
    report = json.loads((out / "protocol.json").read_bytes())
    assert report["unique_ids_including_confirmation"] == 9
    assert report["decisions"]["workflow"]["reference"] == study.REFERENCE
    assert report["decisions"]["native"]["round_evidence"] == "descriptive_transfer"
    for view in original.VIEWS:
        table = pd.read_csv(out / view / "81.csv.gz")
        assert len(table) == 4 * 5
        assert set(table.detector) == {study.CANDIDATE, original.REFERENCE, original.VERIFIED,
                                      study.REFERENCE, study.VERIFIED_MARGIN}
        for name in ("scorecard", "families", "support", "review-budgets", "operating-points"):
            assert (out / view / f"{name}.csv").is_file()
    with pytest.raises(ValueError, match="new output"):
        study.run_assignment_margin(ORIGINAL, BENCHMARKS, out, workers=1)
