import numpy as np
import pandas as pd
import pytest
from scipy.special import expit

from swarmtrace.detect import OnlineDetector, RunDetector


def _training():
    signal = np.tile([-2., -1., 1., 2.], 12)
    frame = pd.DataFrame({
        "signal": signal, "sparse": np.tile([np.nan, 1., 1., np.nan], 12),
        "unobserved": np.nan,
    })
    return frame, signal > 0


def _queries(signal):
    return pd.DataFrame({"signal": signal, "sparse": np.nan, "unobserved": 17.})


def test_positive_class_margin_preserves_order_inside_real_probability_ties():
    train, truth = _training()
    detector = RunDetector("logistic", 7).fit(train, truth)
    queries = _queries([-2000., -1000., 0., 1000., 1000., 2000.])
    probabilities = detector.score(queries)
    np.testing.assert_array_equal(probabilities[[0, 1, 3, 4, 5]], [0, 0, 1, 1, 1])
    margins = detector.score_margin(queries)
    assert np.isfinite(margins).all()
    assert margins[0] < margins[1] < 0 < margins[3] == margins[4] < margins[5]
    np.testing.assert_array_equal(expit(margins), probabilities)
    np.testing.assert_array_equal(detector.score_margin(queries), margins)
    np.testing.assert_array_equal(detector.score(queries), probabilities)


def test_explicit_margin_option_calibrates_its_own_units_and_keeps_true_ties():
    train, truth = _training()
    held = _queries(np.arange(1000., 1039.))
    controls = np.zeros(len(held), dtype=bool)
    probability = RunDetector("logistic", 1).fit(train, truth).calibrate(held, controls)
    margin = RunDetector("logistic_margin", 1).fit(train, truth).calibrate(held, controls)
    # The 38th of 39 independent controls is the strict split-conformal cutoff at 5%.
    probes = held.iloc[[36, 37, 37, 38]]
    assert probability.threshold == 1. and not probability.flag(probes).any()
    assert margin.threshold == margin.calibration_scores[37] > 1
    np.testing.assert_array_equal(margin.calibration_scores, probability.score_margin(held))
    np.testing.assert_array_equal(margin.score(probes), margin.score_margin(probes))
    np.testing.assert_array_equal(margin.flag(probes), [False, False, False, True])
    np.testing.assert_array_equal(probability.calibration_scores, np.ones(39))


def test_threshold_decisions_agree_when_probability_distinctions_survive_rounding():
    train, truth = _training()
    held = _queries(np.linspace(-1., 1., 39))
    controls = np.zeros(len(held), dtype=bool)
    default = RunDetector("logistic", 3).fit(train, truth).calibrate(held, controls)
    margin = RunDetector("logistic_margin", 3).fit(train, truth).calibrate(held, controls)
    probes = pd.concat([held, _queries([-2., 2., np.nan])])
    assert (default.score(probes) > 0).all() and (default.score(probes) < 1).all()
    assert default.threshold == pytest.approx(expit(margin.threshold))
    np.testing.assert_array_equal(margin.flag(probes), default.flag(probes))


def test_margin_uses_fitted_mask_imputation_and_scaling_including_missing_values(monkeypatch):
    train, truth = _training()
    detector = RunDetector("logistic", 7).fit(train, truth)
    queries = _queries([np.nan, -1., .5, 1000.])
    queries.loc[1, "sparse"] = 1.
    pipeline = detector._fitted.model
    retained = queries[["signal", "sparse"]].to_numpy()
    expected = pipeline.decision_function(retained)

    def unexpected(*args, **kwargs):
        pytest.fail("a fitted decision-function read must not refit or invert probabilities")

    monkeypatch.setattr(pipeline, "predict_proba", unexpected)
    monkeypatch.setattr(pipeline, "fit", unexpected)
    np.testing.assert_array_equal(detector.score_margin(queries), expected)
    np.testing.assert_array_equal(detector.score_margin(queries.assign(unobserved=-1e30)), expected)
    assert np.isfinite(expected).all()


def test_margin_requires_supported_fitted_detector_and_exact_column_order():
    train, truth = _training()
    with pytest.raises(ValueError, match="fit the logistic"):
        RunDetector("logistic", 3).score_margin(train)
    for model in ("boosted", "rule", "sharing_logistic", "scope_logistic"):
        with pytest.raises(ValueError, match="ordinary logistic"):
            RunDetector(model, 3).score_margin(train)
    detector = RunDetector("logistic_margin", 3).fit(train, truth)
    for frame in (train.drop(columns="sparse"), train[train.columns[::-1]], train.assign(other=3)):
        with pytest.raises(ValueError, match="expected columns"):
            detector.score_margin(frame)


def test_opt_in_online_detector_calibrates_prefix_maxima_in_log_odds():
    train, truth = _training()
    train.index = pd.MultiIndex.from_arrays([np.arange(len(train)), np.zeros(len(train), int)],
                                             names=["run_id", "tick"])
    held = _queries(np.repeat(np.arange(1000., 1039.), 2))
    held.index = pd.MultiIndex.from_product([range(39), (0, 1)], names=train.index.names)
    controls = np.zeros(len(held), bool)
    detector = OnlineDetector("logistic_margin", 3).fit(train, truth).calibrate(held, controls)
    queries = _queries([1037., 1038., 1037., 1036.])
    queries.index = pd.MultiIndex.from_product([["first", "second"], (0, 1)], names=train.index.names)
    assert detector.threshold > 1
    assert detector.first_crossings(queries) == {"first": 1, "second": None}
