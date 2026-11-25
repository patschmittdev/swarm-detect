import math
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from statistics import NormalDist

import numpy as np


def auroc(labels: np.ndarray, scores: np.ndarray) -> float:
    """Probability that a random positive run outscores a random negative one, ties counting half.

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


def false_positive_rate(labels: np.ndarray, flags: np.ndarray) -> float:
    """Fraction of control runs (label False) flagged; NaN without control runs."""
    labels = np.asarray(labels, dtype=bool)
    controls = np.asarray(flags, dtype=bool)[~labels]
    return float(controls.mean()) if controls.size else math.nan


def attribution_counts(
    proposed: Iterable[frozenset[str]], offensive: frozenset[str]
) -> tuple[int, int, int]:
    """Per-agent ``(true positives, false positives, false negatives)`` for one run.

    An agent is predicted offensive when it is in any proposed group. Benign agents, including
    benign-team members, are negatives.
    """
    flagged = set().union(*proposed)
    return len(flagged & offensive), len(flagged - offensive), len(offensive - flagged)


def ratio(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else math.nan


def pooled_ratio(
    numerators: np.ndarray, denominators: np.ndarray,
) -> Callable[[np.ndarray], float]:
    """Statistic for ``bootstrap``: per-run counts summed over the resampled runs, then divided.

    On every run it is the pooled k of n, so resampling runs (not agents) keeps each run's
    agents together.
    """
    numerators, denominators = np.asarray(numerators), np.asarray(denominators)
    return lambda idx: ratio(numerators[idx].sum(), denominators[idx].sum())


def detection_fraction(first_tick: int | None, objective_tick: int | None) -> float:
    """``first_tick / objective_tick``; NaN if undetected or the objective tick is absent or 0."""
    if first_tick is None or not objective_tick:
        return math.nan
    return first_tick / objective_tick


def detection_coverage(first_ticks: np.ndarray) -> float:
    """Fraction of positive runs detected at any tick; ``first_ticks`` is NaN where undetected."""
    first = np.asarray(first_ticks, dtype=float)
    return float((~np.isnan(first)).mean()) if first.size else math.nan


def _eligible(objective_ticks: np.ndarray) -> np.ndarray:
    objective = np.asarray(objective_ticks, dtype=float)
    return ~np.isnan(objective) & (objective > 0)


def _completion_fraction(
    first_ticks: np.ndarray, objective_ticks: np.ndarray,
    compare: Callable[[np.ndarray, np.ndarray], np.ndarray],
) -> float:
    first = np.asarray(first_ticks, dtype=float)
    objective = np.asarray(objective_ticks, dtype=float)
    eligible = _eligible(objective)
    if not eligible.any():
        return math.nan
    first, objective = first[eligible], objective[eligible]
    detected = ~np.isnan(first)
    hits = np.zeros(first.size, dtype=bool)
    hits[detected] = compare(first[detected], objective[detected])
    return float(np.mean(hits))


def detected_before_completion(first_ticks: np.ndarray, objective_ticks: np.ndarray) -> float:
    """Among runs with an objective tick above 0, the fraction first detected at or before it.

    The sum of ``detected_strictly_before_completion`` and ``detected_at_completion``, which
    are the rates reported. An undetected run counts as not detected before completion. NaN
    without such runs.
    """
    return _completion_fraction(first_ticks, objective_ticks, np.less_equal)


def detected_strictly_before_completion(
    first_ticks: np.ndarray, objective_ticks: np.ndarray,
) -> float:
    """Among runs with an objective tick above 0, the fraction first detected strictly before it.

    An undetected run counts as not detected. NaN without such runs.
    """
    return _completion_fraction(first_ticks, objective_ticks, np.less)


def detected_at_completion(first_ticks: np.ndarray, objective_ticks: np.ndarray) -> float:
    """Among runs with an objective tick above 0, the fraction first detected exactly at it.

    An undetected run counts as not detected. NaN without such runs.
    """
    return _completion_fraction(first_ticks, objective_ticks, np.equal)


def conditional_time_to_detection(first_ticks: np.ndarray, objective_ticks: np.ndarray) -> float:
    """Mean of first-detection tick over objective tick, over detected runs with an objective tick
    above 0 (conditional on detection). NaN without such runs."""
    first = np.asarray(first_ticks, dtype=float)
    objective = np.asarray(objective_ticks, dtype=float)
    used = _eligible(objective) & ~np.isnan(first)
    return float(np.mean(first[used] / objective[used])) if used.any() else math.nan


MIN_VALID_FRACTION = 0.9
MIN_STRATUM_RUNS = 2


@dataclass(frozen=True)
class Estimate:
    value: float
    low: float
    high: float
    requested: int
    valid: int
    """Resamples on which the statistic was defined."""
    note: str
    """Why the interval is withheld; empty when it is given."""


def wilson(k: int, n: int, confidence: float = 0.95) -> Estimate:
    """Wilson score interval for a binomial count, including boundary proportions."""
    if not 0 <= k <= n or not 0 < confidence < 1:
        raise ValueError("Wilson interval needs 0 <= k <= n and 0 < confidence < 1")
    if not n:
        return Estimate(math.nan, math.nan, math.nan, 0, 0, "empty denominator")
    p = k / n
    z2 = NormalDist().inv_cdf((1 + confidence) / 2) ** 2
    denominator = 1 + z2 / n
    center = (p + z2 / (2 * n)) / denominator
    half = math.sqrt(z2 * (p * (1 - p) / n + z2 / (4 * n * n))) / denominator
    low = 0.0 if k == 0 else max(0.0, center - half)
    high = 1.0 if k == n else min(1.0, center + half)
    return Estimate(p, low, high, 0, 0, "")


def bootstrap(
    statistic: Callable[[np.ndarray], float],
    strata: Sequence[np.ndarray],
    n_resamples: int,
    seed: int,
    confidence: float = 0.95,
) -> Estimate:
    """Stratified percentile bootstrap over runs.

    ``strata`` are arrays of run positions; each resample draws every stratum with replacement
    to its own size and concatenates them, so class counts are fixed. ``statistic`` maps the
    positions to a value, NaN when undefined. The interval is withheld (NaN, with a note) when a
    stratum has fewer than 2 runs or fewer than 90% of the requested resamples are defined.
    """
    strata = [np.asarray(stratum, dtype=int) for stratum in strata]
    value = float(statistic(np.concatenate(strata)))
    if any(stratum.size < MIN_STRATUM_RUNS for stratum in strata):
        return Estimate(value, math.nan, math.nan, n_resamples, 0,
                        f"fewer than {MIN_STRATUM_RUNS} runs in a resampling stratum")
    rng = np.random.default_rng(np.random.SeedSequence(seed))
    replicates = np.array([
        statistic(np.concatenate([
            stratum[rng.integers(0, stratum.size, stratum.size)] for stratum in strata
        ]))
        for _ in range(n_resamples)
    ], dtype=float)
    defined = replicates[~np.isnan(replicates)]
    if defined.size < MIN_VALID_FRACTION * n_resamples or defined.size == 0:
        return Estimate(value, math.nan, math.nan, n_resamples, int(defined.size),
                        f"only {defined.size} of {n_resamples} resamples defined")
    tail = (1.0 - confidence) / 2.0
    low, high = np.quantile(defined, [tail, 1.0 - tail])
    return Estimate(value, float(low), float(high), n_resamples, int(defined.size), "")
