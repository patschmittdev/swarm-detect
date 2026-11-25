import numpy as np
import pandas as pd
import pytest

from swarmtrace.detect import (
    RULE_COLUMN,
    SCOPE_LOGISTIC,
    SCOPE_RULE_COLUMNS,
    SHARING_LOGISTIC,
    OnlineDetector,
    RunDetector,
)
from swarmtrace.features import feature_columns
from swarmtrace.trace.context import ContextLevel
from swarmtrace.trace.tiers import Tier

MODELS = ((SHARING_LOGISTIC, RULE_COLUMN), (SCOPE_LOGISTIC, SCOPE_RULE_COLUMNS[0]))


@pytest.mark.parametrize(("model", "gate"), MODELS)
def test_fits_the_existing_logistic_pipeline_only_on_evidence(model: str, gate: str) -> None:
    fitting = pd.DataFrame({
        gate: [1, 2, 1, 3, 2, 1],
        "counts": [2, np.nan, 3, 4, 1, 0],
        "missing_on_eligible": [np.nan] * 6,
    })
    labels = np.array([False, True, True, True, False, False])
    extra = pd.DataFrame({
        gate: [0, np.nan, 0], "counts": [1000, -1000, 300], "missing_on_eligible": [40, 60, 90],
    })
    combined = pd.concat([fitting, extra], ignore_index=True)
    probe = fitting.assign(missing_on_eligible=700)
    ordinary = RunDetector("logistic", seed=7).fit(fitting, labels)
    candidate = RunDetector(model, seed=7).fit(combined, np.r_[labels, [True, True, False]])
    np.testing.assert_array_equal(candidate.score(probe), ordinary.score(probe))
    np.testing.assert_array_equal(candidate.score(extra), [0, 0, 0])
    assert candidate.score(probe.iloc[:0]).shape == (0,)


@pytest.mark.parametrize(("model", "gate"), MODELS)
@pytest.mark.parametrize(("counts", "labels", "expected"), [
    ([0, np.nan, 0], [False, True, True], 1 / 2),
    ([1, 0, 2], [True, False, True], 3 / 4),
    ([1, 0, 2], [False, True, False], 1 / 4),
    ([1, 2, 3], [False, False, False], 1 / 5),
])
def test_missing_eligible_class_uses_smoothed_fitting_proportion(
    model: str, gate: str, counts: list[float], labels: list[bool], expected: float,
) -> None:
    candidate = RunDetector(model, seed=5).fit(pd.DataFrame({gate: counts}), np.array(labels))
    np.testing.assert_array_equal(
        candidate.score(pd.DataFrame({gate: [np.nan, 0, 1, 200]})), [0, 0, expected, expected]
    )


@pytest.mark.parametrize(("model", "gate"), MODELS)
def test_missing_required_evidence_column_raises(model: str, gate: str) -> None:
    frame = pd.DataFrame({"other": [10, 30]})
    with pytest.raises(ValueError, match=gate):
        RunDetector(model, seed=20).fit(frame, np.array([True, False]))


def test_scope_model_requires_task_scope_context() -> None:
    for level in ContextLevel:
        columns = feature_columns("run", Tier.V1, context=level)
        frame = pd.DataFrame(0, index=[0, 1], columns=columns)
        labels = np.array([False, True])
        if level is ContextLevel.C2:
            model = RunDetector(SCOPE_LOGISTIC, seed=20).fit(frame, labels)
            np.testing.assert_array_equal(model.score(frame), [0, 0])
        else:
            with pytest.raises(ValueError, match=SCOPE_RULE_COLUMNS[0]):
                RunDetector(SCOPE_LOGISTIC, seed=20).fit(frame, labels)


def test_calibration_keeps_controls_without_evidence_in_the_denominator() -> None:
    fitting = pd.DataFrame({RULE_COLUMN: [1, 1], "breadth": [0, 1]})
    candidate = RunDetector(SHARING_LOGISTIC, seed=20).fit(fitting, np.array([False, True]))
    held = pd.DataFrame({RULE_COLUMN: [0] * 19 + [1], "breadth": [0] * 19 + [90]})
    before = candidate.score(fitting)
    candidate.calibrate(held, np.array([False] * 19 + [True]))
    np.testing.assert_array_equal(candidate.calibration_scores, np.zeros(19))
    assert candidate.threshold == 0
    np.testing.assert_array_equal(candidate.score(fitting), before)
    assert candidate.flag(held).tolist() == [False] * 19 + [True]


def test_online_fallback_uses_eligible_prefixes_in_a_single_class_fitting_batch() -> None:
    index = pd.MultiIndex.from_product([["a", "b"], [7, 15]], names=["run_id", "tick"])
    prefixes = pd.DataFrame({RULE_COLUMN: [0, 0, 0, 1]}, index=index)
    candidate = OnlineDetector(SHARING_LOGISTIC, seed=3).fit(prefixes, np.ones(4, dtype=bool))
    np.testing.assert_array_equal(candidate.score(prefixes), [0, 0, 0, 2 / 3])
