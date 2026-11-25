from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np

IN_DISTRIBUTION = "in-distribution"
HELD_OUT = "held-out"
CALIBRATION_FRACTION = 0.3


@dataclass(frozen=True)
class Split:
    name: str
    kind: str
    train: tuple[str, ...]
    test: tuple[str, ...]

    def __post_init__(self) -> None:
        if set(self.train) & set(self.test):
            raise ValueError(f"split {self.name!r} has runs in both train and test")


def _stratified(
    run_ids: Sequence[str], positives: Sequence[bool], fraction: float, seed: int
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if not 0.0 < fraction < 1.0:
        raise ValueError(f"fraction must be strictly between 0 and 1, got {fraction}")
    if len(run_ids) != len(positives) or len(set(run_ids)) != len(run_ids):
        raise ValueError("run_ids must be unique and aligned with positives")
    rng = np.random.default_rng(np.random.SeedSequence(seed))
    kept: list[str] = []
    held: list[str] = []
    for value in (False, True):
        members = sorted(run for run, positive in zip(run_ids, positives) if positive == value)
        order = [members[i] for i in rng.permutation(len(members))]
        cut = round(fraction * len(members))
        held.extend(order[:cut])
        kept.extend(order[cut:])
    return tuple(sorted(kept)), tuple(sorted(held))


def split_by_run(
    run_ids: Sequence[str], positives: Sequence[bool], test_fraction: float, seed: int
) -> Split:
    """Stratified split of whole runs: ``round(test_fraction * n)`` runs of each class go to test.

    Within each class, runs are taken in sorted-id order and permuted by a generator seeded from
    ``seed``.
    """
    train, test = _stratified(run_ids, positives, test_fraction, seed)
    return Split("by run", IN_DISTRIBUTION, train, test)


def calibration_split(
    run_ids: Sequence[str], positives: Sequence[bool], fraction: float, seed: int
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Split training runs into ``(fitting, calibration)``, holding out ``round(fraction * n)``
    runs of each class for calibration, by the same stratified rule as ``split_by_run``."""
    return _stratified(run_ids, positives, fraction, seed)


def split_by_stratum(
    run_ids: Sequence[str], strata: Sequence[str], fraction: float, seed: int
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Split whole runs into ``(kept, held)``: ``round(fraction * n)`` runs of each stratum held.

    Strata are visited in sorted order; within each, runs are taken in sorted-id order and
    permuted by one generator seeded from ``seed``. The result depends only on the set of
    ``(run, stratum)`` pairs, never on input order or on labels.
    """
    if not 0.0 < fraction < 1.0:
        raise ValueError(f"fraction must be strictly between 0 and 1, got {fraction}")
    if len(run_ids) != len(strata) or len(set(run_ids)) != len(run_ids):
        raise ValueError("run_ids must be unique and aligned with strata")
    rng = np.random.default_rng(np.random.SeedSequence(seed))
    kept: list[str] = []
    held: list[str] = []
    for name in sorted(set(strata)):
        members = sorted(run for run, stratum in zip(run_ids, strata) if stratum == name)
        order = [members[i] for i in rng.permutation(len(members))]
        cut = round(fraction * len(members))
        held.extend(order[:cut])
        kept.extend(order[cut:])
    return tuple(sorted(kept)), tuple(sorted(held))


def _sort_key(value: int | str) -> tuple[str, int | str]:
    return (type(value).__name__, value)


def held_out_splits(
    conditions: Mapping[str, Mapping[str, int | str]], factor: str
) -> list[Split]:
    """One split per value of ``factor``: test is every run with that value, train every other run.

    Train and test therefore share no value of the factor. Every run must state the factor, and the
    factor must take at least two values.
    """
    missing = sorted(run for run, condition in conditions.items() if factor not in condition)
    if missing:
        raise ValueError(f"{len(missing)} runs do not state condition factor {factor!r}")
    values = sorted({condition[factor] for condition in conditions.values()}, key=_sort_key)
    if len(values) < 2:
        raise ValueError(f"condition factor {factor!r} takes fewer than two values")
    splits = []
    for value in values:
        test = sorted(run for run, condition in conditions.items() if condition[factor] == value)
        train = sorted(run for run, condition in conditions.items() if condition[factor] != value)
        splits.append(Split(f"held-out {factor}={value}", HELD_OUT, tuple(train), tuple(test)))
    return splits
