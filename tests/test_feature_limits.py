from itertools import product

import numpy as np
import pandas as pd
import pytest

from swarmtrace.eval.feature_limits import feature_ceiling


def test_hindsight_limits_match_every_deterministic_rule_on_five_patterns():
    values = [0, 0, 0, 1, 1, 1, 1, 2, 2, 3, 4]
    positive = [True, True, False, True, True, True, False, True, False, True, False]
    small = [True, True, False, False, False, False, False, True, False, True, False]
    data = pd.DataFrame({"value": values})
    for budget in range(6):
        all_options, small_options, errors = [], [], []
        for choices in product([False, True], repeat=5):
            alerts = [choices[value] for value in values]
            false = sum(flag and not target for flag, target in zip(alerts, positive))
            errors.append(sum(flag != target for flag, target in zip(alerts, positive)))
            if false <= budget:
                all_options.append(sum(flag and truth for flag, truth in zip(alerts, positive)))
                small_options.append(sum(flag and truth for flag, truth in zip(alerts, small)))
        result = feature_ceiling(data, positive, small, budget)
        assert result["max_true_positives"] == max(all_options)
        assert result["max_small_true_positives"] == max(small_options)
        assert result["min_errors"] == min(errors) == 3
        assert result["mixed_patterns"] == 3 and result["mixed_runs"] == 9
        assert result["mixed_controls"] == result["mixed_small_positives"] == 3
    # At one false alert, the pattern with the most positives contains no small positives.
    result = feature_ceiling(data, positive, small, 1)
    assert (result["max_true_positives"], result["max_small_true_positives"]) == (4, 3)


def test_exact_grouping_keeps_missing_positions_nearby_floats_and_large_integers_distinct():
    larger = 2**53 + 1
    data = pd.DataFrame({
        "a": pd.Series([1.0, 1, np.nextafter(1., 2.), pd.NA, None, float(larger), larger], dtype=object),
        "b": pd.Series([None, np.nan, pd.NA, 1, 1., 1, 1], dtype=object),
    })
    flags = [True, False, True, True, False, True, False]
    result = feature_ceiling(data, flags, flags, 0)
    assert result["unique_patterns"] == 5 and result["mixed_patterns"] == 2
    assert result["max_true_positives"] == 2 and result["min_errors"] == 2


def test_indivisible_multi_control_groups_can_beat_a_greedy_selection():
    # A buys three hits for two controls. B and C buy four hits for three controls each.
    table = pd.DataFrame({"pattern": [0] * 5 + [1] * 7 + [2] * 7})
    labels = ([True] * 3 + [False] * 2) + ([True] * 4 + [False] * 3) * 2
    assert feature_ceiling(table, labels, labels, 1)["max_true_positives"] == 0
    assert feature_ceiling(table, labels, labels, 2)["max_true_positives"] == 3
    assert feature_ceiling(table, labels, labels, 6)["max_true_positives"] == 8


def test_empty_cohort_and_no_feature_columns_have_well_defined_limits():
    empty = feature_ceiling(pd.DataFrame(), [], [], 3)
    assert empty["false_budget"] == 3
    assert all(count == 0 for name, count in empty.items() if name != "false_budget")
    no_columns = pd.DataFrame(index=["a", "b", "c"])
    positive, small = [True, True, False], [False, True, False]
    tight = feature_ceiling(no_columns, positive, small, 0)
    assert tight["unique_patterns"] == tight["mixed_patterns"] == tight["min_errors"] == 1
    assert tight["max_true_positives"] == tight["max_small_true_positives"] == 0
    assert feature_ceiling(no_columns, positive, small, 1)["max_true_positives"] == 2


def test_labels_preserve_row_identity_and_require_actual_booleans():
    table = pd.DataFrame({"a": [7.0, 7.0]}, index=["first", "second"])
    aligned = pd.Series([False, True], index=table.index)
    assert feature_ceiling(table, aligned, np.array([False, False]), np.int64(1))["positives"] == 1
    with pytest.raises(ValueError, match="indices"):
        feature_ceiling(table, aligned.iloc[::-1], aligned, 0)
    for invalid in ([False], [0, 1], ["False", "True"], [pd.NA, True]):
        with pytest.raises(ValueError, match="boolean"):
            feature_ceiling(table, invalid, aligned, 0)
    with pytest.raises(ValueError, match="subset"):
        feature_ceiling(table, [False, False], aligned, 0)
    with pytest.raises(ValueError, match="unique"):
        feature_ceiling(table.set_axis(["same", "same"]), aligned, aligned, 0)
    with pytest.raises(ValueError, match="unique"):
        feature_ceiling(pd.concat([table, table], axis=1), aligned, aligned, 0)


@pytest.mark.parametrize("budget", [-1, True, np.bool_(False), 0.5])
def test_invalid_false_alert_budgets_are_rejected(budget):
    with pytest.raises(ValueError, match="nonnegative integer"):
        feature_ceiling(pd.DataFrame(), [], [], budget)


@pytest.mark.parametrize("cell", ["1", object(), complex(1, 2), np.inf, -np.inf])
def test_invalid_observation_types_are_rejected(cell):
    with pytest.raises(ValueError, match="real numbers|finite"):
        feature_ceiling(pd.DataFrame({"x": [cell]}), [True], [True], 0)
