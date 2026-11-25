"""Empirical limits for deterministic full-run decisions on exact observed features."""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from math import inf
from numbers import Integral, Real

import numpy as np
import pandas as pd


@dataclass
class _Pattern:
    positives: int = 0
    small_positives: int = 0
    controls: int = 0


def _value(value: object) -> object:
    """Use one missing sentinel and preserve each numeric value's exact precision."""
    if value is pd.NA or value is None:
        return None
    if isinstance(value, (Integral, np.bool_)):
        return int(value)
    if not isinstance(value, (Real, Decimal)):
        raise ValueError("feature observations must be real numbers or missing")
    if isinstance(value, Decimal) and value.is_nan():
        return None
    if value != value:
        return None
    if value in (-inf, inf):
        raise ValueError("feature observations must be finite or missing")
    # NumPy's mixed integer/float comparisons can promote the integer to a float.
    # An integer numerator and denominator preserve distinctions even above 2**53.
    numerator, denominator = value.as_integer_ratio()
    return int(numerator) if denominator == 1 else (int(numerator), int(denominator))


def _labels(values: Iterable[bool], index: pd.Index) -> list[bool]:
    if isinstance(values, pd.Series) and not values.index.equals(index):
        raise ValueError("label indices must match feature rows in order")
    labels = list(values)
    if len(labels) != len(index) or any(not isinstance(label, (bool, np.bool_)) for label in labels):
        raise ValueError("each feature row needs one boolean value per label")
    return labels


def feature_ceiling(
    features: pd.DataFrame, positive: Iterable[bool], small_positive: Iterable[bool], false_budget: int,
) -> dict[str, int]:
    """Give hindsight upper bounds on detections for this finite set of observed runs.

    A deterministic decision function flags all or none of each group with identical
    numeric feature values, including the positions of missing values. Each group costs
    its number of controls when flagged. The two objectives independently maximize all
    positive hits and small-positive hits at the supplied false-alert budget. Minimum
    errors counts the smaller class in each group without a budget constraint.
    """
    if not isinstance(features, pd.DataFrame) or not features.index.is_unique or not features.columns.is_unique:
        raise ValueError("features must be a table with unique run ids and column names")
    if isinstance(false_budget, (bool, np.bool_)) or not isinstance(false_budget, Integral) or false_budget < 0:
        raise ValueError("false_budget must be a nonnegative integer")
    false_budget = int(false_budget)
    labels, small = _labels(positive, features.index), _labels(small_positive, features.index)
    groups: dict[tuple, _Pattern] = defaultdict(_Pattern)
    for row, target, one_file in zip(features.itertuples(index=True, name=None), labels, small, strict=True):
        if one_file and not target:
            raise ValueError("small_positive must be a subset of positive")
        pattern = groups[tuple(_value(value) for value in row[1:])]
        if target:
            pattern.positives += 1
            pattern.small_positives += int(one_file)
        else:
            pattern.controls += 1

    positives, small_positives = int(sum(labels)), int(sum(small))
    mixed = [p for p in groups.values() if p.positives and p.controls]
    mixed_positives = sum(p.positives for p in mixed)
    mixed_small = sum(p.small_positives for p in mixed)
    mixed_controls = sum(p.controls for p in mixed)
    max_all, max_small = positives, small_positives
    if false_budget < mixed_controls:
        all_hits = [0] * (false_budget + 1)
        small_hits = [0] * (false_budget + 1)
        for pattern in mixed:
            # Descending capacities ensure each pattern can enter a solution only once.
            for capacity in range(false_budget, pattern.controls - 1, -1):
                remaining = capacity - pattern.controls
                all_hits[capacity] = max(all_hits[capacity], all_hits[remaining] + pattern.positives)
                small_hits[capacity] = max(small_hits[capacity], small_hits[remaining] + pattern.small_positives)
        max_all = positives - mixed_positives + all_hits[false_budget]
        max_small = small_positives - mixed_small + small_hits[false_budget]
    return {
        "runs": len(features), "positives": positives, "small_positives": small_positives,
        "controls": len(features) - positives, "false_budget": false_budget,
        "unique_patterns": len(groups), "mixed_patterns": len(mixed),
        "mixed_runs": mixed_positives + mixed_controls, "mixed_positives": mixed_positives,
        "mixed_small_positives": mixed_small, "mixed_controls": mixed_controls,
        "max_small_true_positives": max_small, "max_true_positives": max_all,
        "min_errors": sum(min(p.positives, p.controls) for p in mixed),
    }
