from math import comb

import numpy as np


def permutation_pvalue(
    numerator: list[float] | np.ndarray, denominator: list[float] | np.ndarray,
    labels: list[bool] | np.ndarray, blocks: list[int] | np.ndarray, *, seed: int,
    permutations: int = 1999,
) -> float:
    """Two-sided difference of weighted means, permuting whole groups within runs.

    Run-level tests instead use matched positive/control pairs as blocks. Keeping
    the assignment unit intact avoids treating cooperating members as independent.
    The plus-one correction includes the observed assignment in the reference set.
    """
    values, weights = np.asarray(numerator, dtype=float), np.asarray(denominator, dtype=float)
    assigned, strata = np.asarray(labels, dtype=bool), np.asarray(blocks)
    assert values.shape == weights.shape == assigned.shape == strata.shape
    assert assigned.any() and (~assigned).any() and np.all(weights > 0)
    observed = abs(values[assigned].sum() / weights[assigned].sum()
                   - values[~assigned].sum() / weights[~assigned].sum())
    rng = np.random.default_rng(np.random.SeedSequence(seed).spawn(1)[0])
    shuffled = np.broadcast_to(assigned, (permutations, len(values))).copy()
    for block in np.unique(strata):
        indices = np.flatnonzero(strata == block)
        count = int(assigned[indices].sum())
        ranks = rng.random((permutations, len(indices))).argsort(axis=1).argsort(axis=1)
        shuffled[:, indices] = ranks < count
    positive_weight = shuffled @ weights
    positive_sum = shuffled @ values
    differences = np.abs(positive_sum / positive_weight
                         - (values.sum() - positive_sum) / (weights.sum() - positive_weight))
    return float((1 + np.count_nonzero(differences >= observed - 1e-12)) / (permutations + 1))


def binomial_pvalue(successes: int, trials: int, probability: float) -> float:
    """Exact probability-ordered, two-sided binomial test."""
    probabilities = [comb(trials, k) * probability ** k * (1 - probability) ** (trials - k)
                     for k in range(trials + 1)]
    threshold = probabilities[successes]
    return min(1.0, sum(value for value in probabilities if value <= threshold + 1e-15))
