import numpy as np
import pandas as pd
import pytest

from swarmtrace.detect import SCOPE_BREADTH_RULE, SCOPE_RULE_COLUMNS, OnlineDetector, RunDetector
from swarmtrace.features import feature_columns
from swarmtrace.trace.context import ContextLevel
from swarmtrace.trace.tiers import Tier

OUTSIDE, BREADTH = SCOPE_RULE_COLUMNS


def fitted() -> RunDetector:
    frame = pd.DataFrame({OUTSIDE: [0, 1], BREADTH: [4, 3]})
    return RunDetector(SCOPE_BREADTH_RULE, seed=17).fit(frame, np.array([False, True]))


def test_breadth_orders_ties_only_when_there_is_scope_evidence() -> None:
    frame = pd.DataFrame({OUTSIDE: [0, 0, 1, 1, 1, 2], BREADTH: [0, 100, 0, 2, 9, 0]})
    scores = fitted().score(frame)
    np.testing.assert_allclose(scores, [0, 0, 1, 1 + 2 / 3, 1.9, 2])
    large = pd.DataFrame({OUTSIDE: [2**24, 2**24 + 1], BREADTH: [2**32 - 1, 0]})
    first, second = fitted().score(large)
    assert first < second


def test_score_uses_only_the_two_named_columns() -> None:
    frame = pd.DataFrame({BREADTH: [1, 2, 3], "other": [20, 0, 50], OUTSIDE: [1, 1, 2]})
    labels = np.array([True, False, True])
    expected = [1.5, 1 + 2 / 3, 2.75]
    for seed, fit_labels in ((30, labels), (42, ~labels)):
        detector = RunDetector(SCOPE_BREADTH_RULE, seed).fit(frame, fit_labels)
        probe = frame.assign(other=-frame["other"]).set_axis(["x", "y", "z"])
        np.testing.assert_allclose(detector.score(probe), expected)


@pytest.mark.parametrize("level", [ContextLevel.C0, ContextLevel.C1])
def test_lower_context_cannot_fit_the_rule(level: ContextLevel) -> None:
    columns = feature_columns("run", Tier.V1, context=level)
    frame = pd.DataFrame(0, index=[0, 1], columns=columns)
    with pytest.raises(ValueError, match=OUTSIDE):
        RunDetector(SCOPE_BREADTH_RULE, seed=0).fit(frame, np.array([True, False]))


def test_missing_breadth_column_cannot_fit_the_rule() -> None:
    with pytest.raises(ValueError, match=BREADTH):
        RunDetector(SCOPE_BREADTH_RULE, seed=0).fit(
            pd.DataFrame({OUTSIDE: [0, 1]}), np.array([False, True])
        )


def test_unobserved_counts_supply_zero_evidence() -> None:
    frame = pd.DataFrame({OUTSIDE: [np.nan, np.nan, 1, 0], BREADTH: [np.nan, 10, np.nan, np.nan]})
    np.testing.assert_array_equal(fitted().score(frame), [0, 0, 1, 0])


@pytest.mark.parametrize(
    ("column", "invalid"), [(OUTSIDE, -1), (OUTSIDE, 1.2), (BREADTH, -np.inf), (BREADTH, np.inf)]
)
def test_malformed_counts_raise_a_value_error(column: str, invalid: float) -> None:
    frame = pd.DataFrame({OUTSIDE: [1], BREADTH: [1]}).assign(**{column: invalid})
    with pytest.raises(ValueError, match="count"):
        fitted().score(frame)


def test_control_only_calibration_and_strict_threshold() -> None:
    calibration = pd.DataFrame({OUTSIDE: [0] * 18 + [1, 8], BREADTH: [8] * 18 + [1, 8]})
    detector = fitted().calibrate(calibration, np.array([False] * 19 + [True]))
    assert detector.threshold == 1.5
    np.testing.assert_array_equal(detector.calibration_scores, [0] * 18 + [1.5])
    probe = pd.DataFrame({OUTSIDE: [0, 1, 1, 2], BREADTH: [30, 1, 2, 0]})
    np.testing.assert_array_equal(detector.flag(probe), [False, False, True, True])


def test_online_rule_uses_per_control_maxima_and_first_strict_crossing() -> None:
    index = pd.MultiIndex.from_product([["a", "b", "c"], [7, 15]], names=["run_id", "tick"])
    prefixes = pd.DataFrame({OUTSIDE: [0, 1, 0, 0, 1, 1], BREADTH: [9, 1, 5, 5, 1, 2]}, index)
    labels = np.array([False] * 4 + [True] * 2)
    detector = OnlineDetector(SCOPE_BREADTH_RULE, seed=3, max_fpr=0.5)
    detector.fit(prefixes, labels).calibrate(prefixes, labels)
    np.testing.assert_array_equal(detector.calibration_scores, [1.5, 0])
    assert detector.first_crossings(prefixes) == {"a": None, "b": None, "c": 15}
