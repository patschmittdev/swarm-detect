"""Statistics for the pilot: AUROC, exact Mann-Whitney p-value, bootstrap and Clopper-Pearson.

These are written here rather than imported from ``swarmtrace.eval.metrics`` because importing
that package also imports pandas and scikit-learn; the study code uses the standard library and
numpy only. ``auroc`` and ``bootstrap`` follow the same definitions as those in
``swarmtrace.eval.metrics``.
"""

import math
from collections.abc import Callable, Sequence

import numpy as np

BOOTSTRAP_RESAMPLES = 2000
BOOTSTRAP_SEED = 20260602


def auroc(labels: Sequence[bool], scores: Sequence[float]) -> float:
    """Probability that a random positive outscores a random negative, ties counting half.

    NaN unless both classes are present.
    """
    labels = np.asarray(labels, dtype=bool)
    scores = np.asarray(scores, dtype=float)
    positive, negative = scores[labels], scores[~labels]
    if positive.size == 0 or negative.size == 0:
        return math.nan
    greater = (positive[:, None] > negative[None, :]).mean()
    ties = (positive[:, None] == negative[None, :]).mean()
    return float(greater + 0.5 * ties)


def doubled_midranks(values: Sequence[float]) -> list[int]:
    """Twice the mid-rank of every value (ranks start at 1), as integers."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + 1) + (j + 1)
        i = j + 1
    return ranks


def exact_mann_whitney_greater(positive: Sequence[float], negative: Sequence[float]) -> float:
    """One-sided exact p-value as a float, for display; see exact_mann_whitney_counts."""
    counts = exact_mann_whitney_counts(positive, negative)
    return math.nan if counts is None else counts[0] / counts[1]


def exact_mann_whitney_counts(positive: Sequence[float], negative: Sequence[float]
                              ) -> tuple[int, int] | None:
    """One-sided exact p-value that positives rank above negatives, as (hits, total).

    The statistic is the sum of the positives' doubled mid-ranks in the pooled sample (ties get
    mid-ranks, doubled so every value is an integer). Its null distribution is the exact
    permutation distribution: every one of the C(N, n1) ways to choose which n1 of the N pooled
    values are positive is equally likely, with the observed tie pattern kept. The number of
    choices giving each sum is counted by dynamic programming over the pooled values, which gives
    the same counts as listing every combination. p = hits / total with hits the choices with
    sum >= observed and total = C(N, n1). None unless both groups are non-empty and finite.
    """
    n1, n2 = len(positive), len(negative)
    if n1 == 0 or n2 == 0:
        return None
    pooled = [float(v) for v in positive] + [float(v) for v in negative]
    if any(not math.isfinite(v) for v in pooled):
        return None
    ranks = doubled_midranks(pooled)
    observed = sum(ranks[:n1])
    # counts[k][s]: number of k-subsets of the values seen so far with doubled rank sum s
    total = sum(ranks)
    counts = [[0] * (total + 1) for _ in range(n1 + 1)]
    counts[0][0] = 1
    for r in ranks:
        for k in range(n1, 0, -1):
            row, below = counts[k], counts[k - 1]
            for s in range(total, r - 1, -1):
                if below[s - r]:
                    row[s] += below[s - r]
    return sum(counts[n1][observed:]), math.comb(n1 + n2, n1)


def binom_cdf(k: int, n: int, p: float) -> float:
    """P(X <= k) for X ~ Binomial(n, p)."""
    if k < 0:
        return 0.0
    if k >= n:
        return 1.0
    return float(sum(math.comb(n, i) * p**i * (1 - p) ** (n - i) for i in range(k + 1)))


def _bisect(f: Callable[[float], float], target: float, increasing: bool) -> float:
    low, high = 0.0, 1.0
    for _ in range(200):
        mid = (low + high) / 2
        if (f(mid) < target) == increasing:
            low = mid
        else:
            high = mid
    return (low + high) / 2


def clopper_pearson(k: int, n: int, confidence: float = 0.95) -> tuple[float, float]:
    """Exact two-sided binomial interval for k successes in n trials.

    The lower bound is the p at which P(X >= k) = (1 - confidence) / 2 (0 when k = 0); the upper
    bound is the p at which P(X <= k) = (1 - confidence) / 2 (1 when k = n). Both are found by
    bisection on the binomial CDF, which is monotone in p. (NaN, NaN) when n = 0.
    """
    if n == 0:
        return math.nan, math.nan
    tail = (1.0 - confidence) / 2.0
    low = 0.0 if k == 0 else _bisect(lambda p: 1.0 - binom_cdf(k - 1, n, p), tail, True)
    high = 1.0 if k == n else _bisect(lambda p: binom_cdf(k, n, p), tail, False)
    return low, high


def proportion(k: int, n: int) -> dict:
    low, high = clopper_pearson(k, n)
    return {"flagged": k, "of": n, "rate": (k / n) if n else None,
            "ci95_low": None if n == 0 else low, "ci95_high": None if n == 0 else high}


def stratified_bootstrap_auroc(labels: Sequence[bool], scores: Sequence[float],
                               n_resamples: int = BOOTSTRAP_RESAMPLES,
                               seed: int = BOOTSTRAP_SEED, confidence: float = 0.95) -> dict:
    """Percentile interval of AUROC, resampling positives and negatives separately.

    Each resample draws the positive runs and the negative runs with replacement, each to its own
    size, so the class counts stay fixed. The interval is withheld when a class has fewer than
    two runs.
    """
    labels = np.asarray(labels, dtype=bool)
    scores = np.asarray(scores, dtype=float)
    value = auroc(labels, scores)
    pos, neg = np.flatnonzero(labels), np.flatnonzero(~labels)
    result = {"auroc": value, "low": None, "high": None, "resamples": n_resamples, "seed": seed}
    if pos.size < 2 or neg.size < 2 or np.isnan(scores).any():
        result["note"] = "interval withheld: a class has fewer than 2 runs or a score is missing"
        return result
    rng = np.random.default_rng(np.random.SeedSequence(seed))
    reps = np.empty(n_resamples)
    for i in range(n_resamples):
        p = scores[pos[rng.integers(0, pos.size, pos.size)]]
        q = scores[neg[rng.integers(0, neg.size, neg.size)]]
        reps[i] = (p[:, None] > q[None, :]).mean() + 0.5 * (p[:, None] == q[None, :]).mean()
    tail = (1.0 - confidence) / 2.0
    low, high = np.quantile(reps, [tail, 1.0 - tail])
    result.update(low=float(low), high=float(high))
    return result
