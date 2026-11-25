import itertools
import math

import pytest

from swarmtrace.study import stats


def brute_force_p(positive, negative):
    pooled = list(positive) + list(negative)
    ranks = stats.doubled_midranks(pooled)
    observed = sum(ranks[: len(positive)])
    combos = list(itertools.combinations(range(len(pooled)), len(positive)))
    return sum(sum(ranks[i] for i in c) >= observed for c in combos) / len(combos)


def test_mann_whitney_hand_cases():
    assert stats.exact_mann_whitney_greater([3, 4], [1, 2]) == pytest.approx(1 / 6)
    assert stats.exact_mann_whitney_greater(range(8, 18), range(8)) == pytest.approx(1 / 43758)
    assert stats.exact_mann_whitney_greater([1, 1], [1, 1, 1]) == 1.0
    # {2, 2} vs {1, 2}: doubled mid-ranks 2, 6, 6, 6; observed 12; sums >= 12 in 3 of 6
    assert stats.exact_mann_whitney_greater([2, 2], [1, 2]) == pytest.approx(3 / 6)


@pytest.mark.parametrize("positive,negative", [
    ([0.9, 0.5, 0.5, 0.2], [0.5, 0.1, 0.2]),
    ([1, 2, 2, 3, 5], [2, 2, 4, 0, 1, 1]),
    ([0.3, 0.3, 0.3], [0.3, 0.1, 0.4, 0.3]),
])
def test_mann_whitney_matches_enumeration(positive, negative):
    assert stats.exact_mann_whitney_greater(positive, negative) == pytest.approx(
        brute_force_p(positive, negative))


def test_clopper_pearson_hand_cases():
    low, high = stats.clopper_pearson(0, 14)
    assert low == 0.0 and high == pytest.approx(1 - 0.025 ** (1 / 14), abs=1e-9)
    low, high = stats.clopper_pearson(10, 10)
    assert high == 1.0 and low == pytest.approx(0.025 ** (1 / 10), abs=1e-9)
    low, high = stats.clopper_pearson(5, 10)  # tabulated: 0.1871, 0.8129
    assert low == pytest.approx(0.18709, abs=1e-4) and high == pytest.approx(0.81291, abs=1e-4)
    one_sided = 1 - 0.05 ** (1 / 14)  # the protocol's "19 percent"
    assert round(one_sided, 2) == 0.19
    assert all(math.isnan(v) for v in stats.clopper_pearson(0, 0))


def test_auroc_and_bootstrap():
    labels = [True, True, True, False, False, False]
    scores = [0.9, 0.8, 0.4, 0.4, 0.2, 0.1]
    assert stats.auroc(labels, scores) == pytest.approx((8 + 0.5) / 9)
    boot = stats.stratified_bootstrap_auroc(labels, scores, n_resamples=200)
    assert boot["low"] <= boot["auroc"] <= boot["high"]
    assert stats.stratified_bootstrap_auroc(labels, scores, n_resamples=200) == boot
