import math
from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np
import pandas as pd

from swarmtrace.detect import RULE, RULE_COLUMN, OnlineDetector, PairScorer, RunDetector
from swarmtrace.features import feature_columns
from swarmtrace.trace.tiers import Tier

from .data import TierData, build_tier_data, load_runs
from .groups import WRONG_CATEGORIES, reconstruction, wrongly_named
from .metrics import (
    attribution_counts,
    auroc,
    bootstrap,
    conditional_time_to_detection,
    detected_at_completion,
    detected_strictly_before_completion,
    detection_coverage,
    false_positive_rate,
    pooled_ratio,
    wilson,
)
from .splits import CALIBRATION_FRACTION, Split, calibration_split, held_out_splits, split_by_run

DETECTORS = ("volume", "logistic", "boosted")
"""Fitted detectors. Their order fixes their seeds, so new detectors are never added here."""
REPORTED_DETECTORS = (*DETECTORS, RULE)
"""Every detector in the results tables: the fitted ones, then the no-parameter rule baseline."""
SEED_KEY = 3
"""Spawn key of the pair scorer (``SEED_KEY``) and the calibration split (``SEED_KEY + 1``).

It was ``len(DETECTORS)`` when the three fitted detectors were the only ones; it is fixed so that
no detector added later changes a seed of an existing one.
"""
SEED_INDEX = {"volume": 0, "logistic": 1, "boosted": 2, RULE: SEED_KEY + 2}
"""Per-detector spawn key, distinct from the pair scorer's and the calibration split's."""
NOT_AVAILABLE_TIER = "not available at this tier"
NOT_AVAILABLE_FAMILY = "not available without aggregation features"
NOT_AVAILABLE = frozenset({NOT_AVAILABLE_TIER, NOT_AVAILABLE_FAMILY})
FEATURE_SETS = ("generic", "aggregation", "all")
ATTRIBUTION = "pairs"
FULL_TRACE_METRICS = ("auroc", "detection_rate", "false_positive_rate")
ONLINE_METRICS = (
    "online_false_positive_rate",
    "detection_coverage",
    "detected_strictly_before_completion",
    "detected_at_completion",
    "time_to_detection",
)
ONLINE_SUFFIX = "-online"
SPLIT_ROW = "split"
SPLIT_METRICS = ("fitting_runs", "calibration_runs", "calibration_controls", "test_runs")
THRESHOLD_METRICS = ("full_trace_threshold", "online_threshold")
TOO_SMALL = "calibration set too small for the target rate; the detector never fires"
ATTRIBUTION_METRICS = ("attribution_precision", "attribution_recall")
"""Per-agent k of n, with intervals from the stratified bootstrap over runs."""
GROUP_METRICS = ("group_jaccard", "group_exact")
"""Per positive run: Jaccard overlap of the proposed group, and the fraction reconstructed exactly."""
ROLE_METRICS = ("wrong_benign_solo", "wrong_team_sharing", "wrong_team_not_sharing",
                "wrong_team_unresolved", "wrong_team_no_metadata")
"""Counts of wrongly named agents, one per ``groups.WRONG_CATEGORIES`` entry, in that order."""
ROLE_CATEGORIES = dict(zip(ROLE_METRICS, WRONG_CATEGORIES, strict=True))
ATTRIBUTION_ROWS = (*ATTRIBUTION_METRICS, *GROUP_METRICS, *ROLE_METRICS)
ATTRIBUTION_BOOTSTRAP_KEYS = (13, 14, 15, 16)
"""Second spawn keys, after a method's index, of the bootstrap for attribution precision,
attribution recall, group Jaccard and exact reconstruction. No other stream uses 13 to 16."""
AT_COMPLETION_KEY = 17
"""Second spawn key of ``detected_at_completion``; Wilson rates consume no seed."""
RATE_METRICS = frozenset({
    "detection_rate", "false_positive_rate", "online_false_positive_rate",
    "detection_coverage", "detected_strictly_before_completion", "detected_at_completion",
    *(f"detection_rate_size_{size}" for size in (2, 3, 5)),
})
"""Rates over runs with Wilson intervals. Attribution rates are not here: agents in one run are
not independent, so their intervals bootstrap runs."""
_MODELS = {"volume": "logistic", "logistic": "logistic", "boosted": "boosted", RULE: RULE}


@dataclass(frozen=True)
class EvalConfig:
    tiers: tuple[Tier, ...] = (Tier.V0, Tier.V1, Tier.V2)
    seed: int = 0
    test_fraction: float = 0.3
    hold_out: tuple[str, ...] = ()
    n_bootstrap: int = 1000
    confidence: float = 0.95
    max_fpr: float = 0.05
    n_folds: int = 5
    families: tuple[str, ...] = ("all",)
    workers: int = 1
    checkpoint_every: int = 8


@dataclass(frozen=True)
class MetricRow:
    tier: str
    split: str
    kind: str
    method: str
    metric: str
    value: float
    low: float
    high: float
    n: int
    """Numerator for a rate (runs or agents); otherwise the runs ``value`` is taken over."""
    total: int
    """Rate denominator in ``unit``, or runs in the metric's population."""
    requested: int
    """Bootstrap resamples requested."""
    valid: int
    """Bootstrap resamples on which the metric was defined."""
    note: str
    """Why the interval is withheld; empty when it is given."""
    family: str = "all"
    checkpoint_every: int = 8
    interval: str = "bootstrap"
    unit: str = "runs"
    seed: int = 0
    split_counts: tuple[int, ...] = ()
    """Fitting C/P, calibration C/P, test C/P counts, in that order."""
    positive_runs: int = 0
    control_runs: int = 0


@dataclass(frozen=True)
class SplitResult:
    rows: tuple[MetricRow, ...]
    thresholds: Mapping[str, float]
    fitted: Mapping[str, RunDetector | OnlineDetector | PairScorer]
    fitting: tuple[str, ...]
    """Training runs the detectors were fitted on."""
    calibration: tuple[str, ...]
    """Training runs held out to set the detection thresholds."""


def child_seed(seed: int, *key: int) -> int:
    return int(np.random.SeedSequence(seed, spawn_key=key).generate_state(1)[0])


def rule_unavailable(columns: Collection[str], tier: Tier) -> str | None:
    """Why the rule baseline cannot be scored on a matrix with ``columns``, or None if it can."""
    if RULE_COLUMN in columns:
        return None
    return (NOT_AVAILABLE_TIER if RULE_COLUMN not in feature_columns("run", tier)
            else NOT_AVAILABLE_FAMILY)


def _matrix(data: TierData, method: str) -> pd.DataFrame:
    return data.volume if method == "volume" else data.runs


def _prefix_matrix(data: TierData, method: str) -> pd.DataFrame:
    return data.prefix_volume if method == "volume" else data.prefix_runs


def _rows_of(frame: pd.DataFrame, runs: list[str]) -> pd.DataFrame:
    return frame[frame.index.get_level_values("run_id").isin(runs)]


class _Rows:
    def __init__(self, data: TierData, split: Split, config: EvalConfig, seed: int) -> None:
        self.data, self.split, self.config, self.seed = data, split, config, seed
        self.rows: list[MetricRow] = []

    def add(
        self, method: str, metric: str, statistic: Callable[[np.ndarray], float],
        strata: list[np.ndarray], n: int, total: int, key: tuple[int, ...],
        *, unit: str = "runs", positive_runs: int = 0, control_runs: int = 0,
    ) -> None:
        rate = metric in RATE_METRICS
        estimate = wilson(n, total, self.config.confidence) if rate else bootstrap(
            statistic, strata, self.config.n_bootstrap, child_seed(self.seed, *key),
            self.config.confidence,
        )
        self.rows.append(MetricRow(
            self.data.tier.value, self.split.name, self.split.kind, method, metric,
            estimate.value, estimate.low, estimate.high, n, total,
            estimate.requested, estimate.valid, estimate.note,
            interval="Wilson" if rate else "bootstrap", unit=unit,
            positive_runs=positive_runs, control_runs=control_runs,
        ))

    def fact(self, method: str, metric: str, value: float, count: int, note: str = "") -> None:
        self.rows.append(MetricRow(
            self.data.tier.value, self.split.name, self.split.kind, method, metric,
            value, math.nan, math.nan, count, count, 0, 0, note,
        ))

    def count(self, method: str, metric: str, count: int, total: int) -> None:
        """An agent count out of ``total``, with no interval."""
        self.rows.append(MetricRow(
            self.data.tier.value, self.split.name, self.split.kind, method, metric,
            float(count), math.nan, math.nan, count, total, 0, 0, "",
            interval="count", unit="agents",
        ))

    def missing(self, method: str, metrics: tuple[str, ...], reason: str) -> None:
        for metric in metrics:
            rate, counted = metric in RATE_METRICS, metric in ROLE_METRICS
            self.rows.append(MetricRow(
                self.data.tier.value, self.split.name, self.split.kind, method, metric,
                math.nan, math.nan, math.nan, 0, 0,
                0 if rate or counted else self.config.n_bootstrap, 0, reason,
                interval="Wilson" if rate else "count" if counted else "bootstrap",
                unit="agents" if metric in ATTRIBUTION_METRICS or counted else "runs",
            ))


def family_data(data: TierData, family: str) -> TierData:
    """Restrict learned detectors and attribution; the volume reference is family-independent."""
    if family not in FEATURE_SETS:
        raise ValueError(f"unknown feature family {family!r}")
    families = None if family == "all" else (family,)
    runs = list(feature_columns("run", data.tier, families))
    pairs = list(feature_columns("pair", data.tier, families))
    return replace(data, runs=data.runs[runs], pairs=data.pairs[pairs],
                   prefix_runs=data.prefix_runs[runs])


def _classes(labels: np.ndarray) -> list[np.ndarray]:
    return [np.flatnonzero(labels), np.flatnonzero(~labels)]


def evaluate_split(
    data: TierData, split: Split, config: EvalConfig, seed: int, *, family: str = "all",
    run_only: bool = False,
) -> SplitResult:
    """Fit every detector and the pair scorer on ``split.train`` and measure them on ``split.test``.

    Training runs are split by run into a fitting set and a calibration set. Detectors are
    fitted on the fitting set and thresholded on the calibration set's control runs; test runs
    reach neither. A model whose fitting runs lack what it needs gets NaN rows with ``n == 0``
    and a note. The rule baseline needs ``RULE_COLUMN``: without it (at V0, or in the generic
    family) its rows carry ``NOT_AVAILABLE_TIER`` or ``NOT_AVAILABLE_FAMILY`` instead of values.

    ``run_only`` evaluates full-trace run features only, without the volume reference,
    pairs, online models or completion metadata. Records then need only run_id, positive
    and condition, as supplied by recorded run tables. Existing fit/calibration/metric
    seed keys are unchanged; absent measurements are never synthesized.
    """
    data = family_data(data, family)
    unknown = set(split.train + split.test) - set(data.records)
    if unknown:
        raise ValueError(f"split {split.name!r} names {len(unknown)} runs not in the data")
    train, test = list(split.train), list(split.test)
    y_train = np.array([data.records[run].positive for run in train], dtype=bool)
    y_test = np.array([data.records[run].positive for run in test], dtype=bool)
    rows = _Rows(data, split, config, seed)
    thresholds: dict[str, float] = {}
    fitted: dict[str, RunDetector | OnlineDetector | PairScorer] = {}
    offensive = [] if run_only else [data.records[run].offensive for run in test]

    key = SEED_KEY
    fitting, calibration = calibration_split(
        train, y_train.tolist(), CALIBRATION_FRACTION, child_seed(seed, key + 1, 0)
    )
    proposed: dict[str, list[frozenset[str]]] | None = None
    train_pairs = data.pairs.index.get_level_values("run_id").isin(fitting)
    pair_y = data.pair_labels[train_pairs]
    positive_runs = data.pairs.index.get_level_values("run_id")[train_pairs][pair_y].nunique()
    if not run_only and positive_runs >= 2 and not pair_y.all():
        scorer = PairScorer(child_seed(seed, key, 0), config.n_folds).fit(
            data.pairs[train_pairs], pair_y
        )
        fitted[ATTRIBUTION], thresholds[ATTRIBUTION] = scorer, scorer.threshold
        test_pairs = data.pairs.index.get_level_values("run_id").isin(test)
        proposed = scorer.propose(data.pairs[test_pairs])

    def attribution(method: str, gate: np.ndarray, index: int) -> None:
        if proposed is None:
            rows.missing(method, ATTRIBUTION_ROWS,
                         "not fitted: training runs lack coordinated pairs in two runs")
            return
        named = [proposed.get(run, []) if flag else [] for run, flag in zip(test, gate)]
        counts = np.array([
            attribution_counts(groups, truth) for groups, truth in zip(named, offensive)
        ]).reshape(len(test), 3)
        tp, fp, fn = counts[:, 0], counts[:, 1], counts[:, 2]
        precision_key, recall_key, jaccard_key, exact_key = ATTRIBUTION_BOOTSTRAP_KEYS
        rows.add(method, "attribution_precision", pooled_ratio(tp, tp + fp),
                 _classes(y_test), int(tp.sum()), int(tp.sum() + fp.sum()),
                 (index, precision_key), unit="agents")
        rows.add(method, "attribution_recall", pooled_ratio(tp, tp + fn),
                 _classes(y_test), int(tp.sum()), int(tp.sum() + fn.sum()),
                 (index, recall_key), unit="agents")
        scored = [reconstruction(groups, truth)
                  for groups, truth, positive in zip(named, offensive, y_test) if positive]
        overlap = np.array([score for score, _ in scored], dtype=float)
        exact = np.array([hit for _, hit in scored], dtype=bool)
        everyone = [np.arange(len(scored))]

        def mean(values: np.ndarray) -> Callable[[np.ndarray], float]:
            return lambda idx: float(values[idx].mean()) if idx.size else math.nan

        rows.add(method, "group_jaccard", mean(overlap), everyone, len(scored), len(scored),
                 (index, jaccard_key))
        rows.add(method, "group_exact", mean(exact), everyone, int(exact.sum()), len(scored),
                 (index, exact_key))
        wrong = dict.fromkeys(WRONG_CATEGORIES, 0)
        for run, groups in zip(test, named):
            record = data.records[run]
            for category, number in wrongly_named(groups, record.labels, record.condition,
                                                  data.shared_logins.get(run)).items():
                wrong[category] += number
        for metric, category in ROLE_CATEGORIES.items():
            rows.count(method, metric, wrong[category], int(fp.sum()))

    positives = [run for run, positive in zip(test, y_test) if positive]
    controls = [run for run, positive in zip(test, y_test) if not positive]
    objective = np.array([] if run_only else [
        data.records[run].labels.objective_tick or math.nan for run in positives
    ], dtype=float)
    eligible = ~np.isnan(objective) & (objective > 0)
    y_fit = np.array([data.records[run].positive for run in fitting], dtype=bool)
    y_cal = np.array([data.records[run].positive for run in calibration], dtype=bool)
    for metric, count in (
        ("fitting_runs", len(fitting)), ("calibration_runs", len(calibration)),
        ("calibration_controls", int((~y_cal).sum())), ("test_runs", len(test)),
    ):
        rows.fact(SPLIT_ROW, metric, float(count), count)

    def threshold_row(method: str, metric: str, threshold: float) -> None:
        note = "" if math.isfinite(threshold) else TOO_SMALL
        rows.fact(method, metric, threshold, 0, note)

    for method in REPORTED_DETECTORS:
        if run_only and method == "volume":
            continue
        index = SEED_INDEX[method]
        reason = rule_unavailable(data.runs.columns, data.tier) if method == RULE else None
        if reason is not None:
            rows.missing(method, FULL_TRACE_METRICS + ONLINE_METRICS + ATTRIBUTION_ROWS, reason)
            continue
        if min(y_fit.sum(), (~y_fit).sum()) < 2:
            reason = "not fitted: fitting runs have fewer than 2 runs of a class"
            rows.missing(method, FULL_TRACE_METRICS + ONLINE_METRICS, reason)
            rows.missing(method, ATTRIBUTION_ROWS, reason)
            continue
        matrix = _matrix(data, method)
        detector = RunDetector(_MODELS[method], child_seed(seed, index, 0), config.max_fpr)
        detector.fit(matrix.loc[list(fitting)], y_fit)
        detector.calibrate(matrix.loc[list(calibration)], y_cal)
        fitted[method], thresholds[method] = detector, detector.threshold
        threshold_row(method, "full_trace_threshold", detector.threshold)
        scores = detector.score(matrix.loc[test])
        flags = scores > detector.threshold
        rows.add(method, "auroc", lambda idx: auroc(y_test[idx], scores[idx]),
                 _classes(y_test), len(test), len(test), (index, 1),
                 positive_runs=int(y_test.sum()), control_runs=int((~y_test).sum()))
        rows.add(method, "detection_rate", lambda idx: float(flags[idx].mean()),
                 [np.flatnonzero(y_test)], int(flags[y_test].sum()), int(y_test.sum()), (index, 10))
        rows.add(method, "false_positive_rate",
                 lambda idx: false_positive_rate(y_test[idx], flags[idx]),
                 [np.flatnonzero(~y_test)], int(flags[~y_test].sum()), int((~y_test).sum()),
                 (index, 2))
        if data.tier == Tier.V1 and family == "aggregation" and split.name == "by run":
            for size in (2, 3, 5):
                members = np.array([
                    data.records[run].positive
                    and data.records[run].condition.get("offensive_group_size") == size
                    for run in test
                ], dtype=bool)
                rows.add(method, f"detection_rate_size_{size}",
                         lambda idx: float(flags[idx].mean()), [np.flatnonzero(members)],
                         int(flags[members].sum()), int(members.sum()), (index, 11, size))
            if all("benign_sharing_teams" in data.records[run].condition for run in test):
                sharing = np.array([
                    not data.records[run].positive
                    and data.records[run].condition["benign_sharing_teams"] > 0 for run in test
                ], dtype=bool)
                selected = y_test | sharing
                rows.add(method, "sharing_control_auroc",
                         lambda idx: auroc(y_test[idx], scores[idx]),
                         [np.flatnonzero(y_test), np.flatnonzero(sharing)],
                         int(selected.sum()), int(selected.sum()), (index, 12),
                         positive_runs=int(y_test.sum()), control_runs=int(sharing.sum()))
            else:
                rows.missing(method, ("sharing_control_auroc",),
                             "missing benign_sharing_teams metadata; regenerate recorded data")
        if run_only:
            continue
        prefix = _prefix_matrix(data, method)

        def prefix_rows(runs: tuple[str, ...]) -> tuple[pd.DataFrame, np.ndarray]:
            frame = _rows_of(prefix, list(runs))
            labels = np.array([
                data.records[run].positive for run in frame.index.get_level_values("run_id")
            ], dtype=bool)
            return frame, labels

        online = OnlineDetector(_MODELS[method], child_seed(seed, index, 8), config.max_fpr)
        online.fit(*prefix_rows(fitting)).calibrate(*prefix_rows(calibration))
        fitted[f"{method}{ONLINE_SUFFIX}"] = online
        thresholds[f"{method}{ONLINE_SUFFIX}"] = online.threshold
        threshold_row(method, "online_threshold", online.threshold)
        crossings = online.first_crossings(_rows_of(prefix, test))

        def first_ticks(runs: list[str]) -> np.ndarray:
            return np.array([
                math.nan if crossings[run] is None else float(crossings[run]) for run in runs
            ], dtype=float)

        control_first, first = first_ticks(controls), first_ticks(positives)
        crossed = ~np.isnan(control_first)
        rows.add(method, "online_false_positive_rate",
                 lambda idx: detection_coverage(control_first[idx]),
                 [np.arange(len(controls))], int(crossed.sum()), len(controls), (index, 9))
        detected = ~np.isnan(first)
        known = np.nan_to_num(objective, nan=-1.0)
        before = detected & eligible & (first < known)
        at = detected & eligible & (first == known)
        rows.add(method, "detection_coverage", lambda idx: detection_coverage(first[idx]),
                 [np.arange(len(positives))], int(detected.sum()), len(positives), (index, 3))
        rows.add(method, "detected_strictly_before_completion",
                 lambda idx: detected_strictly_before_completion(first[idx], objective[idx]),
                 [np.flatnonzero(eligible)], int(before.sum()), int(eligible.sum()), (index, 6))
        rows.add(method, "detected_at_completion",
                 lambda idx: detected_at_completion(first[idx], objective[idx]),
                 [np.flatnonzero(eligible)], int(at.sum()), int(eligible.sum()),
                 (index, AT_COMPLETION_KEY))
        rows.add(method, "time_to_detection",
                 lambda idx: conditional_time_to_detection(first[idx], objective[idx]),
                 [np.flatnonzero(eligible & detected)], int((eligible & detected).sum()),
                 int(eligible.sum()), (index, 7))
        attribution(method, flags, index)
    if not run_only:
        attribution(ATTRIBUTION, np.ones(len(test), dtype=bool), key)
    class_counts = (int((~y_fit).sum()), int(y_fit.sum()), int((~y_cal).sum()), int(y_cal.sum()),
                    int((~y_test).sum()), int(y_test.sum()))
    annotated = tuple(replace(row, family=family, checkpoint_every=data.checkpoint_every,
                              seed=config.seed, split_counts=class_counts)
                      for row in rows.rows)
    return SplitResult(annotated, thresholds, fitted, fitting, calibration)


def evaluate(root: str | Path, config: EvalConfig) -> list[MetricRow]:
    """Every tier, on the by-run split and on each held-out value of each ``hold_out`` factor.

    Splits and fit seeds are the same across tiers, so tiers are compared on the same runs.
    """
    from .recorded import is_recorded, load_recorded, recorded_root

    root = recorded_root(root)
    recorded = is_recorded(root)
    records = (list(load_recorded(root, config.tiers[0]).records.values()) if recorded
               else load_runs(root))
    ids = [record.run_id for record in records]
    splits = [split_by_run(
        ids, [record.positive for record in records], config.test_fraction,
        child_seed(config.seed, 0),
    )]
    conditions = {record.run_id: record.condition for record in records}
    for factor in config.hold_out:
        splits.extend(held_out_splits(conditions, factor))
    rows: list[MetricRow] = []
    for tier in config.tiers:
        data = (load_recorded(root, tier) if recorded else build_tier_data(
            records, tier, workers=config.workers, checkpoint_every=config.checkpoint_every,
            retain_traces=False,
        ))
        for index, split in enumerate(splits):
            for family in config.families:
                rows.extend(evaluate_split(
                    data, split, config, child_seed(config.seed, 1, index), family=family,
                ).rows)
    return rows
