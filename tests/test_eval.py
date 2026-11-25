import json
import math
import shutil
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from sklearn.metrics import roc_auc_score

from swarmtrace.cli import main
from swarmtrace.detect import (
    RULE_COLUMN,
    VOLUME_COLUMNS,
    checkpoints,
    conformal_threshold,
    first_detection_tick,
    volume_features,
)
from swarmtrace.eval import (
    ATTRIBUTION,
    DETECTORS,
    HELD_OUT,
    IN_DISTRIBUTION,
    EvalConfig,
    MetricRow,
    Split,
    attribution_counts,
    auroc,
    bootstrap,
    build_tier_data,
    conditional_time_to_detection,
    detected_before_completion,
    detection_coverage,
    detection_fraction,
    evaluate,
    evaluate_split,
    false_positive_rate,
    feature_table,
    held_out_splits,
    load_runs,
    pair_labels,
    split_by_run,
)
from swarmtrace.eval.harness import (
    ATTRIBUTION_BOOTSTRAP_KEYS,
    ATTRIBUTION_METRICS,
    FULL_TRACE_METRICS,
    GROUP_METRICS,
    NOT_AVAILABLE_FAMILY,
    NOT_AVAILABLE_TIER,
    ONLINE_METRICS,
    REPORTED_DETECTORS,
    ROLE_METRICS,
    RULE,
    SEED_INDEX,
    SEED_KEY,
    THRESHOLD_METRICS,
    child_seed,
)
from swarmtrace.eval.headline import format_headline
from swarmtrace.eval.metrics import (
    detected_at_completion,
    detected_strictly_before_completion,
    pooled_ratio,
    wilson,
)
from swarmtrace.eval.recorded import load_recorded
from swarmtrace.eval.report import format_tier, write_report
from swarmtrace.eval.splits import CALIBRATION_FRACTION, calibration_split
from swarmtrace.features import agent_features, feature_columns, run_features
from swarmtrace.trace.io import AgentLabel, RunPaths
from swarmtrace.trace.synthetic import generate_synthetic_runs
from swarmtrace.trace.tiers import Tier

FAST = EvalConfig(tiers=(Tier.V0,), seed=0, test_fraction=0.3, n_bootstrap=200)
AUROC_TOLERANCE = 0.15


@pytest.fixture(scope="module")
def datasets(tmp_path_factory: pytest.TempPathFactory) -> dict[int, Path]:
    root = tmp_path_factory.mktemp("synthetic")
    roots = {}
    for signal, seed in ((0, 11), (100, 12)):
        roots[signal] = root / f"signal{signal}"
        generate_synthetic_runs(roots[signal], 200, seed, signal)
    return roots


@pytest.fixture(scope="module")
def tier_data(datasets: dict[int, Path]) -> dict:
    return {signal: build_tier_data(load_runs(path), Tier.V0) for signal, path in datasets.items()}


@pytest.fixture(scope="module")
def results(tier_data: dict) -> dict:
    return {
        signal: evaluate_split(data, in_distribution(data), FAST, seed=1)
        for signal, data in tier_data.items()
    }


def rows_by(rows: list[MetricRow], metric: str, kind: str = IN_DISTRIBUTION) -> dict[str, MetricRow]:
    return {row.method: row for row in rows if row.metric == metric and row.kind == kind}


def v0_fitted_rows(rows: list[MetricRow], metric: str) -> dict[str, MetricRow]:
    """``rows_by`` for the fitted detectors at V0, where the rule baseline is not available."""
    by_method = rows_by(rows, metric)
    rule = by_method.pop(RULE)
    assert rule.note == NOT_AVAILABLE_TIER and math.isnan(rule.value), metric
    return by_method


def in_distribution(data, seed: int = 0) -> Split:
    ids = sorted(data.records)
    return split_by_run(ids, [data.records[run].positive for run in ids], 0.3, seed)


def test_auroc_is_near_chance_without_signal(tier_data: dict, results: dict) -> None:
    data = tier_data[0]
    result = results[0]
    aurocs = v0_fitted_rows(result.rows, "auroc")
    assert set(aurocs) == set(DETECTORS)
    for method, row in aurocs.items():
        assert abs(row.value - 0.5) < AUROC_TOLERANCE, (method, row.value)
        assert row.low <= row.value <= row.high
        assert row.n == row.total == len(in_distribution(data).test)


def test_planted_signal_beats_volume_baseline(results: dict) -> None:
    result = results[100]
    aurocs = rows_by(result.rows, "auroc")
    assert abs(aurocs["volume"].value - 0.5) < AUROC_TOLERANCE
    for method in ("logistic", "boosted"):
        assert aurocs[method].value > 0.85, method
        assert aurocs[method].value > aurocs["volume"].value + 0.25, method
    attribution = rows_by(result.rows, "attribution_recall")["pairs"]
    assert attribution.value > 0.5


ONLINE_FPR_TOLERANCE = 0.15


def test_online_false_positive_rate_is_near_target_without_signal(
    tier_data: dict, results: dict
) -> None:
    controls = [run for run in in_distribution(tier_data[0]).test
                if not tier_data[0].records[run].positive]
    online = v0_fitted_rows(results[0].rows, "online_false_positive_rate")
    assert set(online) == set(DETECTORS)
    for method, row in online.items():
        assert row.total == len(controls), method
        assert row.value <= FAST.max_fpr + ONLINE_FPR_TOLERANCE, (method, row.value)


def test_online_detection_catches_planted_signal_within_target(results: dict) -> None:
    online = rows_by(results[100].rows, "online_false_positive_rate")
    coverage = rows_by(results[100].rows, "detection_coverage")
    for method in ("logistic", "boosted"):
        assert coverage[method].value >= 0.8, method
        assert online[method].value <= FAST.max_fpr + ONLINE_FPR_TOLERANCE, method


FPR_SEEDS = (31, 32, 33)


@pytest.fixture(scope="module")
def control_heavy(tmp_path_factory: pytest.TempPathFactory) -> list:
    root = tmp_path_factory.mktemp("fpr")
    built = []
    for seed in FPR_SEEDS:
        generate_synthetic_runs(root / str(seed), 140, seed, 0, positive_percent=25)
        built.append(build_tier_data(load_runs(root / str(seed)), Tier.V0))
    return built


def test_pooled_false_positive_rates_are_consistent_with_target_over_seeds(
    tier_data: dict, results: dict, control_heavy: list
) -> None:
    config = replace(FAST, n_bootstrap=20)
    evaluated = [results[0]] + [
        evaluate_split(data, in_distribution(data, seed), config, seed=seed)
        for seed, data in zip(FPR_SEEDS, control_heavy)
    ]
    alpha = FAST.max_fpr
    calibration = [
        next(row.n for row in result.rows if row.metric == "calibration_controls")
        for result in evaluated
    ]
    for metric in ("false_positive_rate", "online_false_positive_rate"):
        for method in DETECTORS:
            rows = [rows_by(result.rows, metric)[method] for result in evaluated]
            flagged, controls = sum(row.n for row in rows), sum(row.total for row in rows)
            assert controls >= 100
            variance = sum(
                row.total ** 2 * (alpha * (1 - alpha) / row.total + alpha * (1 - alpha) / (n + 2))
                for row, n in zip(rows, calibration)
            ) / controls ** 2
            tolerance = 3 * math.sqrt(variance)
            assert flagged / controls <= alpha + tolerance, (metric, method, flagged, controls)
            assert alpha + tolerance < 0.159
    for result in evaluated:
        assert all(math.isfinite(value) for value in result.thresholds.values())


def test_calibration_split_is_disjoint_stratified_and_deterministic() -> None:
    runs = [f"{i:016x}" for i in range(40)]
    positives = [i % 4 == 0 for i in range(40)]
    fitting, calibration = calibration_split(runs, positives, CALIBRATION_FRACTION, seed=2)
    assert CALIBRATION_FRACTION == 0.3
    assert not set(fitting) & set(calibration)
    assert set(fitting) | set(calibration) == set(runs)
    labels = dict(zip(runs, positives))
    assert sum(labels[run] for run in calibration) == round(0.3 * 10)
    assert sum(not labels[run] for run in calibration) == round(0.3 * 30)
    assert (fitting, calibration) == calibration_split(runs, positives, 0.3, seed=2)


def test_evaluate_split_fits_calibrates_and_tests_on_disjoint_runs(
    tier_data: dict, results: dict
) -> None:
    data = tier_data[100]
    split = in_distribution(data)
    result = results[100]
    assert not set(result.fitting) & set(result.calibration)
    assert not (set(result.fitting) | set(result.calibration)) & set(split.test)
    assert set(result.fitting) | set(result.calibration) == set(split.train)
    counts = {row.metric: row.value for row in result.rows if row.method == "split"}
    assert counts == {
        "fitting_runs": len(result.fitting),
        "calibration_runs": len(result.calibration),
        "calibration_controls": sum(
            not data.records[run].positive for run in result.calibration
        ),
        "test_runs": len(split.test),
    }
    calibration = list(result.calibration)
    controls = [run for run in calibration if not data.records[run].positive]
    for method in DETECTORS:
        detector = result.fitted[method]
        matrix = data.volume if method == "volume" else data.runs
        assert detector.threshold == conformal_threshold(
            detector.score(matrix.loc[controls]), FAST.max_fpr
        )
        online = result.fitted[f"{method}-online"]
        prefix = data.prefix_volume if method == "volume" else data.prefix_runs
        maxima = online.run_scores(prefix[prefix.index.get_level_values("run_id").isin(controls)])
        assert online.threshold == conformal_threshold(maxima.to_numpy(), FAST.max_fpr)


def test_too_small_calibration_set_never_fires_and_is_reported(tier_data: dict) -> None:
    data = tier_data[100]
    ids = sorted(data.records)[:40]
    split = split_by_run(ids, [data.records[run].positive for run in ids], 0.3, 0)
    result = evaluate_split(data, split, FAST, seed=0)
    for method in DETECTORS:
        assert result.thresholds[method] == math.inf
        assert result.thresholds[f"{method}-online"] == math.inf
    thresholds = [row for row in result.rows if row.metric.endswith("threshold")]
    assert len(thresholds) == 2 * len(DETECTORS)
    assert all("calibration set too small" in row.note for row in thresholds)
    assert all(row.n == 0 for row in rows_by(result.rows, "false_positive_rate").values())
    assert all(row.n == 0 for row in rows_by(result.rows, "detection_coverage").values())
    text = format_tier(list(result.rows), "V0")
    assert "calibration set too small" in text


def test_tier_data_matrices_are_label_free_and_aligned(tier_data: dict) -> None:
    data = tier_data[100]
    ids = sorted(data.records)
    assert list(data.runs.index) == ids
    assert list(data.volume.index) == ids
    assert tuple(data.runs.columns) == feature_columns("run", Tier.V0)
    assert tuple(data.volume.columns) == VOLUME_COLUMNS
    assert data.pairs.index.names == ["run_id", "agent_a", "agent_b"]
    assert len(data.pair_labels) == len(data.pairs)
    run = ids[0]
    pd.testing.assert_frame_equal(data.runs.loc[[run]], run_features(data.traces[run]))
    for frame in (data.prefix_runs, data.prefix_volume):
        assert frame.index.names == ["run_id", "tick"]
        assert sorted(set(frame.index.get_level_values("run_id"))) == ids
        assert tuple(frame.loc[run].index) == checkpoints(
            max(event.tick for event in data.traces[run].events)
        )
    assert tuple(data.prefix_runs.columns) == feature_columns("run", Tier.V0)
    trace = data.traces[run]
    pd.testing.assert_frame_equal(
        data.prefix_runs.loc[[run]].iloc[[0]].droplevel("tick"),
        run_features(trace, until_tick=checkpoints(15)[0]),
    )


def test_split_by_run_is_disjoint_stratified_and_deterministic(tier_data: dict) -> None:
    data = tier_data[0]
    ids = sorted(data.records)
    positives = [data.records[run].positive for run in ids]
    split = split_by_run(ids, positives, 0.3, seed=5)
    assert not set(split.train) & set(split.test)
    assert set(split.train) | set(split.test) == set(ids)
    assert split.kind == IN_DISTRIBUTION
    test_positive = sum(data.records[run].positive for run in split.test)
    assert test_positive == round(0.3 * sum(positives))
    assert split == split_by_run(ids, positives, 0.3, seed=5)
    assert split != split_by_run(ids, positives, 0.3, seed=6)
    with pytest.raises(ValueError):
        split_by_run(ids, positives, 1.0, seed=5)


def test_held_out_splits_share_no_condition_value(datasets: dict[int, Path]) -> None:
    records = load_runs(datasets[0])
    conditions = {record.run_id: record.condition for record in records}
    splits = held_out_splits(conditions, "agent_count")
    values = {condition["agent_count"] for condition in conditions.values()}
    assert len(splits) == len(values)
    for split in splits:
        assert split.kind == HELD_OUT
        train_values = {conditions[run]["agent_count"] for run in split.train}
        test_values = {conditions[run]["agent_count"] for run in split.test}
        assert len(test_values) == 1
        assert not train_values & test_values
        assert not set(split.train) & set(split.test)
    with pytest.raises(ValueError):
        held_out_splits(conditions, "channel")
    with pytest.raises(ValueError):
        held_out_splits(conditions, "generator")


def test_threshold_is_never_fitted_on_test_runs(tier_data: dict) -> None:
    data = tier_data[100]
    split = in_distribution(data, seed=3)
    first = evaluate_split(data, split, FAST, seed=2)
    test = list(split.test)
    corrupted_records = dict(data.records)
    for run in test:
        record = corrupted_records[run]
        flipped = {
            agent: AgentLabel("offensive" if label.role != "offensive" else "benign_solo", "g")
            for agent, label in record.labels.agents.items()
        }
        corrupted_records[run] = replace(record, labels=replace(record.labels, agents=flipped))
    runs, volume, pairs, prefix_runs, prefix_volume = (
        frame.astype(float)
        for frame in (data.runs, data.volume, data.pairs, data.prefix_runs, data.prefix_volume)
    )
    runs.loc[test] = 1e6
    volume.loc[test] = 0.0
    pair_test = pairs.index.get_level_values("run_id").isin(test)
    pairs.loc[pair_test] = 1e6
    prefix_test = prefix_runs.index.get_level_values("run_id").isin(test)
    prefix_runs.loc[prefix_test] = 1e6
    prefix_volume.loc[prefix_test] = 1e6
    corrupted = replace(
        data, records=corrupted_records, runs=runs, volume=volume, pairs=pairs,
        pair_labels=np.where(pair_test, ~data.pair_labels, data.pair_labels),
        prefix_runs=prefix_runs, prefix_volume=prefix_volume,
    )
    second = evaluate_split(corrupted, split, FAST, seed=2)
    assert set(first.thresholds) == {
        *DETECTORS, *(f"{method}-online" for method in DETECTORS), ATTRIBUTION
    }
    assert first.thresholds == second.thresholds
    assert (first.fitting, first.calibration) == (second.fitting, second.calibration)
    assert not (set(first.fitting) | set(first.calibration)) & set(test)
    train = list(split.train)

    def train_rows(frame: pd.DataFrame) -> pd.DataFrame:
        return frame[frame.index.get_level_values("run_id").isin(train)]

    for method, fitted in first.fitted.items():
        if method == ATTRIBUTION:
            matrix = train_rows(data.pairs)
        elif method.endswith("-online"):
            matrix = train_rows(data.prefix_volume if method == "volume-online"
                                else data.prefix_runs)
        else:
            matrix = (data.volume if method == "volume" else data.runs).loc[train]
        np.testing.assert_array_equal(fitted.score(matrix), second.fitted[method].score(matrix))


def test_split_rejects_runs_in_both_train_and_test(tier_data: dict) -> None:
    ids = sorted(tier_data[0].records)
    with pytest.raises(ValueError):
        Split("bad", IN_DISTRIBUTION, tuple(ids[:100]), tuple(ids[90:]))


def test_evaluate_split_rejects_unknown_runs(tier_data: dict) -> None:
    ids = sorted(tier_data[0].records)
    with pytest.raises(ValueError):
        evaluate_split(tier_data[0], Split("bad", IN_DISTRIBUTION, tuple(ids), ("f" * 16,)),
                       FAST, seed=0)


def test_single_class_training_gives_explicit_nan_rows(tier_data: dict) -> None:
    data = tier_data[0]
    ids = sorted(data.records)
    controls = [run for run in ids if not data.records[run].positive]
    positives = [run for run in ids if data.records[run].positive]
    split = Split("controls only", HELD_OUT, tuple(controls), tuple(positives[:10]))
    result = evaluate_split(data, split, FAST, seed=0)
    metrics = [row for row in result.rows if row.method != "split"]
    assert metrics
    assert all(math.isnan(row.value) and row.n == 0 for row in metrics)


def test_auroc_matches_sklearn_and_handles_single_class() -> None:
    rng = np.random.default_rng(0)
    labels = rng.random(50) < 0.5
    scores = np.round(rng.random(50), 1)
    assert auroc(labels, scores) == pytest.approx(roc_auc_score(labels, scores))
    assert math.isnan(auroc(np.ones(5, dtype=bool), scores[:5]))


def test_false_positive_rate_counts_flagged_controls_only() -> None:
    labels = np.array([False, False, False, False, True, True])
    flags = np.array([True, False, False, False, True, False])
    assert false_positive_rate(labels, flags) == 0.25
    assert math.isnan(false_positive_rate(np.array([True]), np.array([True])))


def test_attribution_counts_treat_benign_teams_as_negatives() -> None:
    proposed = [frozenset({"a", "b"}), frozenset({"t1", "t2"})]
    offensive = frozenset({"a", "b", "c"})
    assert attribution_counts(proposed, offensive) == (2, 2, 1)
    assert attribution_counts([], frozenset()) == (0, 0, 0)


def test_pair_labels_require_same_offensive_group() -> None:
    from swarmtrace.trace.io import Labels

    labels = Labels(
        run_id="0" * 16,
        agents={
            "a": AgentLabel("offensive", "g1"), "b": AgentLabel("offensive", "g1"),
            "c": AgentLabel("offensive", "g2"), "t": AgentLabel("benign_team", "team"),
            "u": AgentLabel("benign_team", "team"), "s": AgentLabel("benign_solo", None),
        },
        objective_completed=False, objective_tick=None,
    )
    index = pd.MultiIndex.from_tuples(
        [("a", "b"), ("a", "c"), ("t", "u"), ("a", "s")], names=["agent_a", "agent_b"]
    )
    np.testing.assert_array_equal(pair_labels(index, labels), [True, False, False, False])


def test_detection_fraction() -> None:
    assert detection_fraction(5, 10) == 0.5
    assert math.isnan(detection_fraction(None, 10))
    assert math.isnan(detection_fraction(5, None))
    assert math.isnan(detection_fraction(0, 0))


def test_bootstrap_is_deterministic_and_records_resample_counts() -> None:
    values = np.arange(20, dtype=float)
    strata = [np.arange(20)]
    mean = bootstrap(lambda idx: float(values[idx].mean()), strata, 500, seed=3)
    assert mean == bootstrap(lambda idx: float(values[idx].mean()), strata, 500, seed=3)
    assert mean.value == pytest.approx(9.5)
    assert mean.low < 9.5 < mean.high
    assert (mean.requested, mean.valid, mean.note) == (500, 500, "")


def test_bootstrap_resamples_each_stratum_to_its_own_size() -> None:
    labels = np.array([True] * 3 + [False] * 17)
    seen: list[int] = []

    def positives(idx: np.ndarray) -> float:
        seen.append(int(labels[idx].sum()))
        return auroc(labels[idx], np.arange(20.0)[idx])

    strata = [np.flatnonzero(labels), np.flatnonzero(~labels)]
    estimate = bootstrap(positives, strata, 300, seed=1)
    assert set(seen) == {3}
    assert estimate.valid == estimate.requested == 300
    assert not math.isnan(estimate.low)


def test_bootstrap_withholds_interval_when_degenerate() -> None:
    flaky = bootstrap(lambda idx: float("nan") if 0 not in idx else 1.0, [np.arange(20)], 500,
                      seed=3)
    assert flaky.requested == 500 and 0 < flaky.valid < 450
    assert math.isnan(flaky.low) and math.isnan(flaky.high)
    assert "of 500 resamples" in flaky.note
    tiny = bootstrap(lambda idx: 1.0, [np.arange(5), np.arange(5, 6)], 100, seed=3)
    assert tiny.value == 1.0 and math.isnan(tiny.low)
    assert tiny.valid == 0 and "fewer than 2" in tiny.note
    empty = bootstrap(lambda idx: float("nan"), [np.arange(0)], 100, seed=3)
    assert math.isnan(empty.value) and empty.valid == 0


def test_online_metrics_on_a_mixed_detected_and_undetected_case() -> None:
    first = np.array([2.0, np.nan, 8.0, np.nan, 5.0, 3.0])
    objective = np.array([10.0, 10.0, 4.0, np.nan, 0.0, 3.0])
    assert detection_coverage(first) == pytest.approx(4 / 6)
    assert detected_before_completion(first, objective) == pytest.approx(2 / 4)
    assert detected_strictly_before_completion(first, objective) == pytest.approx(1 / 4)
    assert detected_at_completion(first, objective) == pytest.approx(1 / 4)
    assert conditional_time_to_detection(first, objective) == pytest.approx(
        (2 / 10 + 8 / 4 + 3 / 3) / 3
    )
    nothing = np.array([np.nan, np.nan])
    assert detection_coverage(nothing) == 0.0
    assert detected_before_completion(nothing, np.array([5.0, 6.0])) == 0.0
    assert math.isnan(conditional_time_to_detection(nothing, np.array([5.0, 6.0])))
    assert math.isnan(detection_coverage(np.array([])))
    assert math.isnan(detected_before_completion(first, np.full(6, np.nan)))
    for split_rate in (detected_strictly_before_completion, detected_at_completion):
        assert split_rate(nothing, np.array([5.0, 6.0])) == 0.0
        assert math.isnan(split_rate(first, np.full(6, np.nan)))


def test_a_crossing_at_the_completion_tick_counts_only_as_at_completion() -> None:
    first = np.array([3.0, 2.0, 5.0, np.nan, 7.0])
    objective = np.array([3.0, 4.0, 5.0, 6.0, 6.0])
    assert detected_strictly_before_completion(first, objective) == pytest.approx(1 / 5)
    assert detected_at_completion(first, objective) == pytest.approx(2 / 5)
    assert detected_before_completion(first, objective) == pytest.approx(3 / 5)
    assert detection_coverage(first) == pytest.approx(4 / 5)


def test_online_rows_use_objective_tick(tier_data: dict) -> None:
    base = tier_data[100]
    objectives = {}
    records = dict(base.records)
    for index, (run, record) in enumerate(sorted(records.items())):
        if record.positive:
            objectives[run] = 1 if index % 2 else 12
            records[run] = replace(record, labels=replace(
                record.labels, objective_completed=True, objective_tick=objectives[run]
            ))
    data = replace(base, records=records)
    split = in_distribution(data)
    result = evaluate_split(data, split, FAST, seed=4)
    positives = [run for run in split.test if data.records[run].positive]
    outcomes = set()
    for method in DETECTORS:
        detector = result.fitted[f"{method}-online"]
        ticks = {}
        for run in positives:
            trace = data.traces[run]

            def prefix(t: int, trace=trace, method=method) -> pd.DataFrame:
                if method == "volume":
                    return volume_features(agent_features(trace, until_tick=t), trace.run_id)
                return run_features(trace, until_tick=t)

            ticks[run] = first_detection_tick(
                lambda t, prefix=prefix: float(detector.score(prefix(t))[0]),
                checkpoints(max(event.tick for event in trace.events)),
                detector.threshold,
            )
        detected = [run for run in positives if ticks[run] is not None]
        outcomes.update(ticks[run] is not None for run in positives)
        before = [run for run in detected if ticks[run] < objectives[run]]
        at = [run for run in detected if ticks[run] == objectives[run]]
        coverage = rows_by(result.rows, "detection_coverage")[method]
        assert (coverage.n, coverage.total) == (len(detected), len(positives)), method
        assert coverage.value == pytest.approx(len(detected) / len(positives)), method
        for metric, runs in (("detected_strictly_before_completion", before),
                             ("detected_at_completion", at)):
            completion = rows_by(result.rows, metric)[method]
            assert (completion.n, completion.total) == (len(runs), len(positives)), method
            assert completion.value == pytest.approx(len(runs) / len(positives)), method
            assert completion.interval == "Wilson", method
        ttd = rows_by(result.rows, "time_to_detection")[method]
        assert (ttd.n, ttd.total) == (len(detected), len(positives)), method
        if detected:
            assert ttd.value == pytest.approx(
                sum(ticks[run] / objectives[run] for run in detected) / len(detected)
            ), method
        else:
            assert math.isnan(ttd.value), method
    assert outcomes == {True, False}


def test_online_rows_without_objective_tick(tier_data: dict, results: dict) -> None:
    data = tier_data[100]
    result = results[100]
    positives = sum(data.records[run].positive for run in in_distribution(data).test)
    for metric in ("detected_strictly_before_completion", "detected_at_completion",
                   "time_to_detection"):
        for row in v0_fitted_rows(result.rows, metric).values():
            assert math.isnan(row.value) and row.n == 0 and row.total == 0
    for row in v0_fitted_rows(result.rows, "detection_coverage").values():
        assert row.total == positives and not math.isnan(row.value)


def test_attribution_is_reported_per_detector_with_unflagged_runs_missed(
    tier_data: dict, results: dict
) -> None:
    data = tier_data[100]
    split = in_distribution(data)
    result = results[100]
    precision = v0_fitted_rows(result.rows, "attribution_precision")
    recall = v0_fitted_rows(result.rows, "attribution_recall")
    assert set(precision) == set(recall) == {*DETECTORS, ATTRIBUTION}
    test = list(split.test)
    scorer = result.fitted[ATTRIBUTION]
    test_pairs = data.pairs[data.pairs.index.get_level_values("run_id").isin(test)]
    proposed = scorer.propose(test_pairs)
    for method in DETECTORS:
        detector = result.fitted[method]
        matrix = data.volume if method == "volume" else data.runs
        flags = dict(zip(test, detector.flag(matrix.loc[test])))
        tp = fp = fn = 0
        for run in test:
            flagged = set().union(*proposed.get(run, [])) if flags[run] else set()
            offensive = data.records[run].offensive
            tp += len(flagged & offensive)
            fp += len(flagged - offensive)
            fn += len(offensive - flagged)
        assert recall[method].value == pytest.approx(tp / (tp + fn)), method
        assert (recall[method].n, recall[method].total) == (tp, tp + fn), method
        assert (precision[method].n, precision[method].total) == (tp, tp + fp), method
        if tp + fp:
            assert precision[method].value == pytest.approx(tp / (tp + fp)), method
        else:
            assert math.isnan(precision[method].value), method
    assert recall["volume"].value < recall[ATTRIBUTION].value
    for row in (*precision.values(), *recall.values()):
        assert (row.interval, row.unit, row.requested) == ("bootstrap", "agents", FAST.n_bootstrap)
    counts = []
    for run in test:
        flagged = set().union(*proposed.get(run, []))
        offensive = data.records[run].offensive
        counts.append((len(flagged & offensive), len(flagged - offensive)))
    tp_run, fp_run = (np.array(column) for column in zip(*counts))
    labels = np.array([data.records[run].positive for run in test])
    strata = [np.flatnonzero(labels), np.flatnonzero(~labels)]
    def ratio_of_sums(idx: np.ndarray) -> float:
        named = int(tp_run[idx].sum() + fp_run[idx].sum())
        return int(tp_run[idx].sum()) / named if named else math.nan

    expected = bootstrap(ratio_of_sums, strata, FAST.n_bootstrap,
                         child_seed(1, SEED_KEY, ATTRIBUTION_BOOTSTRAP_KEYS[0]), FAST.confidence)
    pairs = precision[ATTRIBUTION]
    assert (pairs.value, pairs.low, pairs.high, pairs.valid) == (
        expected.value, expected.low, expected.high, expected.valid)


def test_attribution_bootstrap_keys_are_unused_by_any_other_stream() -> None:
    used = {0, 1, 2, 3, 6, 7, 8, 9, 10, 11, 12}
    assert not used & set(ATTRIBUTION_BOOTSTRAP_KEYS)
    assert len(set(ATTRIBUTION_BOOTSTRAP_KEYS)) == len(ATTRIBUTION_BOOTSTRAP_KEYS)
    assert sorted(SEED_INDEX.values()) == [0, 1, 2, SEED_KEY + 2]


def test_run_bootstrap_is_wider_than_wilson_when_errors_share_a_run() -> None:
    tp, fp = np.array([10, 0]), np.array([0, 10])
    run_level = bootstrap(pooled_ratio(tp, tp + fp), [np.arange(2)], 500, seed=0)
    agents = wilson(int(tp.sum()), int((tp + fp).sum()))
    assert run_level.value == agents.value == 0.5
    assert run_level.note == "" and run_level.valid == 500
    assert run_level.high - run_level.low > agents.high - agents.low
    assert (run_level.low, run_level.high) == (0.0, 1.0)


def test_pooled_ratio_divides_sums_not_mean_of_ratios() -> None:
    k, n = np.array([1, 3, 0, 2]), np.array([2, 4, 0, 8])
    statistic = pooled_ratio(k, n)
    assert statistic(np.array([0, 1])) == pytest.approx(4 / 6)
    assert statistic(np.array([0, 1])) != pytest.approx((1 / 2 + 3 / 4) / 2)
    assert statistic(np.array([0, 2])) == pytest.approx(1 / 2)
    assert statistic(np.array([1, 1, 2, 3])) == pytest.approx(8 / 16)
    assert statistic(np.array([0, 3, 3])) == pytest.approx(5 / 18)
    assert math.isnan(statistic(np.array([2, 2])))
    assert statistic(np.arange(4)) == pytest.approx(6 / 14)
    seed, resamples = 7, 300
    estimate = bootstrap(statistic, [np.arange(4)], resamples, seed)
    rng = np.random.default_rng(np.random.SeedSequence(seed))
    replicates = []
    for _ in range(resamples):
        drawn = rng.integers(0, 4, 4)
        top = sum(int(k[i]) for i in drawn)
        bottom = sum(int(n[i]) for i in drawn)
        replicates.append(top / bottom if bottom else math.nan)
    defined = [value for value in replicates if not math.isnan(value)]
    assert estimate.value == pytest.approx(6 / 14)
    assert estimate.valid == len(defined)
    assert (estimate.low, estimate.high) == pytest.approx(
        tuple(np.quantile(defined, [0.025, 0.975])))


def test_group_reconstruction_and_wrongly_named_rows(tier_data: dict, results: dict) -> None:
    from swarmtrace.eval.groups import reconstruction, wrongly_named

    data = tier_data[100]
    test = list(in_distribution(data).test)
    result = results[100]
    proposed = result.fitted[ATTRIBUTION].propose(
        data.pairs[data.pairs.index.get_level_values("run_id").isin(test)])
    positives = [run for run in test if data.records[run].positive]
    by_metric = {metric: rows_by(result.rows, metric) for metric in (*GROUP_METRICS, *ROLE_METRICS)}
    for method in (*DETECTORS, ATTRIBUTION):
        if method == ATTRIBUTION:
            flags = dict.fromkeys(test, True)
        else:
            matrix = data.volume if method == "volume" else data.runs
            flags = dict(zip(test, result.fitted[method].flag(matrix.loc[test])))
        scores = [reconstruction(proposed.get(run, []) if flags[run] else [],
                                 data.records[run].offensive) for run in positives]
        overlap, exact = by_metric["group_jaccard"][method], by_metric["group_exact"][method]
        assert overlap.value == pytest.approx(np.mean([score for score, _ in scores])), method
        assert (overlap.n, overlap.total) == (len(positives), len(positives))
        assert (exact.n, exact.total) == (sum(hit for _, hit in scores), len(positives))
        assert exact.interval == overlap.interval == "bootstrap"
        assert exact.requested == FAST.n_bootstrap
        wrong = {}
        for run in test:
            groups = proposed.get(run, []) if flags[run] else []
            for category, count in wrongly_named(groups, data.records[run].labels,
                                                 data.records[run].condition,
                                                 data.shared_logins.get(run)).items():
                wrong[category] = wrong.get(category, 0) + count
        precision = rows_by(result.rows, "attribution_precision")[method]
        cells = [by_metric[metric][method] for metric in ROLE_METRICS]
        assert [cell.n for cell in cells] == list(wrong.values()), method
        assert sum(cell.n for cell in cells) == precision.total - precision.n, method
        assert all(cell.total == precision.total - precision.n for cell in cells), method


def test_crossing_at_the_completion_tick_is_reported_in_the_at_column(
    tier_data: dict, results: dict
) -> None:
    base = tier_data[100]
    split = in_distribution(base)
    first = results[100]
    positives = [run for run in split.test if base.records[run].positive]
    prefix = base.prefix_runs[base.prefix_runs.index.get_level_values("run_id").isin(positives)]
    crossings = first.fitted["logistic-online"].first_crossings(prefix)
    detected = sorted(run for run in positives if crossings[run] is not None)
    assert len(detected) >= 4
    at, before = detected[::2], detected[1::2]
    objective = {**{run: crossings[run] for run in at},
                 **{run: crossings[run] + 1 for run in before}}
    records = dict(base.records)
    for run, tick in objective.items():
        records[run] = replace(records[run], labels=replace(
            records[run].labels, objective_completed=True, objective_tick=tick))
    second = evaluate_split(replace(base, records=records), split, FAST, seed=1)
    rows = {row.metric: row for row in second.rows if row.method == "logistic"}
    assert (rows["detected_at_completion"].n, rows["detected_at_completion"].total) == (
        len(at), len(objective))
    assert rows["detected_strictly_before_completion"].n == len(before)
    assert rows["detection_coverage"].n == len(detected)
    assert rows["time_to_detection"].n == len(objective)


def test_load_runs_is_sorted_and_checks_run_ids(tmp_path: Path) -> None:
    generate_synthetic_runs(tmp_path / "runs", 6, 1, 50)
    records = load_runs(tmp_path / "runs")
    assert [record.run_id for record in records] == sorted(record.run_id for record in records)
    victim = records[0].trace_path.parent
    other = records[1].trace_path.parent
    shutil.copy(RunPaths(other).labels, RunPaths(victim).labels)
    with pytest.raises(ValueError):
        load_runs(tmp_path / "runs")


def test_feature_table_reads_traces_only(tmp_path: Path) -> None:
    generate_synthetic_runs(tmp_path, 4, 2, 50)
    for path in tmp_path.iterdir():
        RunPaths(path).labels.unlink()
        RunPaths(path).manifest.unlink()
    table = feature_table(tmp_path, "pair", Tier.V1)
    assert table.index.names == ["run_id", "agent_a", "agent_b"]
    assert tuple(table.columns) == feature_columns("pair", Tier.V1)
    runs = feature_table(tmp_path, "run", Tier.V0)
    assert list(runs.index) == sorted(path.name for path in tmp_path.iterdir())


def test_evaluate_runs_every_tier_and_held_out_factor(datasets: dict[int, Path]) -> None:
    config = EvalConfig(
        tiers=(Tier.V0, Tier.V2), seed=0, hold_out=("signal",), n_bootstrap=50, n_folds=3
    )
    root = datasets[0].parent / "mixed"
    for signal in (0, 100):
        for path in sorted(datasets[signal].iterdir())[:8]:
            shutil.copytree(path, root / path.name)
    rows = evaluate(root, config)
    assert {row.tier for row in rows} == {"V0", "V2"}
    assert {row.split for row in rows if row.kind == HELD_OUT} == {
        "held-out signal=0", "held-out signal=100"
    }
    assert {row.split for row in rows if row.kind == IN_DISTRIBUTION} == {"by run"}
    again = evaluate(root, replace(config, tiers=(Tier.V2,)))
    assert [repr(row) for row in again] == [repr(row) for row in rows if row.tier == "V2"]


def test_report_has_one_file_per_tier_and_separates_held_out(tmp_path: Path) -> None:
    def row(tier: str, split: str, kind: str, method: str, metric: str, value: float) -> MetricRow:
        return MetricRow(tier, split, kind, method, metric, value, value - 0.1, value + 0.1,
                         30, 40, 1000, 1000, "")

    fpr = wilson(1, 20)
    rows = [
        row("V0", "by run", IN_DISTRIBUTION, "logistic", "auroc", 0.9),
        row("V0", "held-out channel=files", HELD_OUT, "logistic", "auroc", 0.6),
        row("V0", "by run", IN_DISTRIBUTION, "logistic", "attribution_precision", 0.7),
        row("V0", "by run", IN_DISTRIBUTION, "pairs", "attribution_recall", 0.4),
        row("V1", "by run", IN_DISTRIBUTION, "logistic", "auroc", 0.8),
        MetricRow("V0", "by run", IN_DISTRIBUTION, "logistic", "time_to_detection",
                  math.nan, math.nan, math.nan, 0, 0, 1000, 0, "no runs"),
        MetricRow("V0", "by run", IN_DISTRIBUTION, "logistic", "false_positive_rate",
                  fpr.value, fpr.low, fpr.high, 1, 20, 0, 0, "", interval="Wilson"),
    ]
    rows += [
        MetricRow("V0", "by run", IN_DISTRIBUTION, "split", metric, value, math.nan, math.nan,
                  int(value), int(value), 0, 0, "")
        for metric, value in (("fitting_runs", 98.0), ("calibration_runs", 42.0),
                              ("calibration_controls", 21.0), ("test_runs", 60.0))
    ]
    rows.append(MetricRow("V0", "by run", IN_DISTRIBUTION, "boosted", "online_threshold",
                          math.inf, math.nan, math.nan, 0, 0, 0, 0,
                          "calibration set too small for the target rate; never fires"))
    paths = write_report(rows, tmp_path)
    assert [path.name for path in paths] == ["results-V0.md", "results-V1.md"]
    text = paths[0].read_text(encoding="utf-8")
    assert "\r" not in text
    in_dist, held = text.split("## Held-out")
    assert "## In-distribution" in in_dist
    assert "0.900 [0.800, 1.000] (30 of 40 runs; 1000/1000 resamples)" in in_dist
    assert "0.600 [0.500, 0.700]" not in in_dist
    assert "0.600 [0.500, 0.700]" in held and "0.900 [0.800, 1.000]" not in held
    assert "held-out channel=files" in held
    assert "undefined (0 of 0 runs; 0/1000 resamples; no runs)" in in_dist
    assert "0.050 [0.009, 0.236] (1 of 20 runs; Wilson)" in in_dist
    assert "conditional on detection" in in_dist
    assert "### Full-trace detection" in in_dist and "### Online detection" in in_dist
    assert "quantized to the checkpoint cadence" in text
    assert "stratified" in text
    assert "split-conformal" in text
    assert "| by run | 98 | 42 | 21 | 60 | boosted (online) |" in in_dist
    assert format_tier(rows, "V0") == text
    assert "0.800 [0.700, 0.900]" not in text


def test_cli_features_and_eval(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    main(["synthetic", "--out", str(runs), "--runs", "20", "--seed", "3", "--signal", "100"])
    main(["features", "--runs", str(runs), "--tier", "V0", "--level", "run",
          "--out", str(tmp_path / "run.csv")])
    table = pd.read_csv(tmp_path / "run.csv", index_col="run_id")
    assert len(table) == 20
    assert b"\r" not in (tmp_path / "run.csv").read_bytes()
    main(["eval", "--runs", str(runs), "--out", str(tmp_path / "report"), "--seed", "1",
          "--tiers", "V0", "--bootstrap", "20"])
    assert (tmp_path / "report" / "results-V0.md").exists()
    with pytest.raises(SystemExit):
        main(["eval", "--runs", str(runs), "--out", str(tmp_path / "r2"), "--seed", "1",
              "--hold-out", "channel"])


RECORDED = Path(__file__).resolve().parents[1] / "data" / "dataset" / "main"
RECORDED_SEED = 20261120
RECORDED_CONFIG = EvalConfig(seed=RECORDED_SEED, n_bootstrap=200)
FITTED = ("volume", "logistic", "boosted")
# Stored values of the existing detectors' rows on the recorded by-run split, which the rule
# baseline must not change, written by running the BASE 65cf195 source before the rule existed.
# For volume, logistic, boosted and the pair scorer they hold every value, interval and count of
# the full-trace, online-rate, group-size and sharing-control metrics, both thresholds, the split
# counts, and attribution k of n. Attribution intervals and online timing use definitions
# absent from this baseline, so neither is stored. Counts and notes compare exactly;
# floats to rel 1e-9.
EXISTING_ROWS = Path(__file__).parent / "fixtures" / "recorded_existing_rows.json"


def assert_matches_stored(actual: list[MetricRow], stored: list[dict], key: str) -> None:
    existing = [row for row in actual if row.method != RULE]
    wanted = {(entry["method"], entry["metric"]) for entry in stored}
    selected = [row for row in existing if (row.method, row.metric) in wanted]
    assert [(row.method, row.metric) for row in selected] == [
        (entry["method"], entry["metric"]) for entry in stored
    ], key
    for row, entry in zip(selected, stored, strict=True):
        for field, expected in entry.items():
            value = getattr(row, field)
            where = (key, row.method, row.metric, field)
            if expected is None:
                assert math.isnan(value), where
            elif field != "note" and expected == "inf":
                assert value == math.inf, where
            elif isinstance(expected, float):
                assert value == pytest.approx(expected, rel=1e-9, abs=0), where
            else:
                assert value == expected, where


@pytest.fixture(scope="module")
def recorded_rows() -> dict[tuple[str, str], list[MetricRow]]:
    rows = [*evaluate(RECORDED, replace(RECORDED_CONFIG, families=("aggregation",))),
            *evaluate(RECORDED, replace(RECORDED_CONFIG, tiers=(Tier.V1,), families=("all",)))]
    grouped: dict[tuple[str, str], list[MetricRow]] = {}
    for row in rows:
        grouped.setdefault((row.tier, row.family), []).append(row)
    return grouped


def test_rule_baseline_leaves_existing_recorded_numbers_unchanged(recorded_rows: dict) -> None:
    stored = json.loads(EXISTING_ROWS.read_text(encoding="utf-8"))["rows"]
    assert set(recorded_rows) == {tuple(key.split()) for key in stored}
    for key, entries in stored.items():
        assert_matches_stored(recorded_rows[tuple(key.split())], entries, key)
    v1 = recorded_rows["V1", "aggregation"]
    aurocs = {row.method: row.value for row in v1 if row.metric == "auroc"}
    # data/split-stability.md single_auroc for by-run V1 aggregation.
    assert f"{aurocs['volume']:.6f}" == "0.525073"
    assert f"{aurocs['logistic']:.6f}" == "0.920422"
    assert f"{aurocs['boosted']:.6f}" == "0.925509"
    # data/headline.md by-run V1 aggregation counts.
    counts = {(row.method, row.metric): (row.n, row.total) for row in v1}
    for method, detected, flagged, coverage, online in (
        ("logistic", 14, 5, 13, 5), ("boosted", 13, 5, 12, 6), ("volume", 0, 3, 3, 5),
    ):
        assert counts[method, "detection_rate"] == (detected, 32), method
        assert counts[method, "false_positive_rate"] == (flagged, 86), method
        assert counts[method, "detection_coverage"] == (coverage, 32), method
        assert counts[method, "online_false_positive_rate"] == (online, 86), method
    assert SEED_KEY == len(FITTED) == 3


def test_rule_is_reported_at_v1_and_v2_and_not_available_at_v0(recorded_rows: dict) -> None:
    metrics = (*FULL_TRACE_METRICS, *ONLINE_METRICS, *ATTRIBUTION_METRICS, *GROUP_METRICS,
               *ROLE_METRICS)
    assert REPORTED_DETECTORS == (*DETECTORS, RULE)
    assert DETECTORS == FITTED
    v0 = [row for row in recorded_rows["V0", "aggregation"] if row.method == RULE]
    assert [row.metric for row in v0] == list(metrics)
    assert all(math.isnan(row.value) and row.n == row.total == 0 for row in v0)
    assert {row.note for row in v0} == {NOT_AVAILABLE_TIER}
    assert NOT_AVAILABLE_TIER == "not available at this tier"
    for key in (("V1", "aggregation"), ("V2", "aggregation"), ("V1", "all")):
        rule = {row.metric: row for row in recorded_rows[key] if row.method == RULE}
        assert set(metrics) | set(THRESHOLD_METRICS) <= set(rule), key
        for metric in ("auroc", "detection_rate", "false_positive_rate", "detection_coverage"):
            assert math.isfinite(rule[metric].value) and rule[metric].note == "", (key, metric)
        assert rule["auroc"].n == rule["auroc"].total == 118
        assert rule["detection_rate"].total == 32 and rule["false_positive_rate"].total == 86
    v1 = {row.metric: row for row in recorded_rows["V1", "aggregation"] if row.method == RULE}
    for metric in ("detection_rate_size_2", "detection_rate_size_3", "detection_rate_size_5",
                   "sharing_control_auroc"):
        assert math.isfinite(v1[metric].value), metric


def test_rule_threshold_and_scores_use_the_shared_login_count() -> None:
    data = load_recorded(RECORDED, Tier.V1)
    ids = sorted(data.records)
    split = split_by_run(ids, [data.records[run].positive for run in ids], 0.3,
                         child_seed(RECORDED_SEED, 0))
    result = evaluate_split(data, split, RECORDED_CONFIG, child_seed(RECORDED_SEED, 1, 0),
                            family="aggregation")
    rule = result.fitted[RULE]
    counts = data.runs[RULE_COLUMN]
    np.testing.assert_array_equal(rule.score(data.runs[list(rule.columns)]),
                                  counts.to_numpy(dtype=float))
    controls = [run for run in result.calibration if not data.records[run].positive]
    assert rule.threshold == conformal_threshold(counts.loc[controls].to_numpy(dtype=float), 0.05)
    assert result.thresholds[RULE] == rule.threshold
    test = list(split.test)
    flags = counts.loc[test].to_numpy(dtype=float) > rule.threshold
    positive = np.array([data.records[run].positive for run in test])
    row = next(row for row in result.rows if row.method == RULE and row.metric == "detection_rate")
    assert (row.n, row.total) == (int(flags[positive].sum()), int(positive.sum()))
    auroc_row = next(row for row in result.rows if row.method == RULE and row.metric == "auroc")
    assert auroc_row.value == auroc(positive, counts.loc[test].to_numpy(dtype=float))
    online = result.fitted[f"{RULE}-online"]
    prefix = data.prefix_runs[list(online.columns)]
    np.testing.assert_array_equal(online.score(prefix), prefix[RULE_COLUMN].to_numpy(dtype=float))
    precision = next(row for row in result.rows
                     if row.method == RULE and row.metric == "attribution_precision")
    assert precision.note == "" and precision.total > 0


def test_rule_is_not_available_without_aggregation_features() -> None:
    data = load_recorded(RECORDED, Tier.V1)
    ids = sorted(data.records)[::3]
    split = split_by_run(ids, [data.records[run].positive for run in ids], 0.3, 5)
    result = evaluate_split(data, split, replace(RECORDED_CONFIG, n_bootstrap=20), 7,
                            family="generic")
    rule = [row for row in result.rows if row.method == RULE]
    assert rule and {row.note for row in rule} == {NOT_AVAILABLE_FAMILY}
    assert all(math.isnan(row.value) for row in rule)
    assert RULE not in result.fitted and RULE not in result.thresholds
    text = format_tier(list(result.rows), "V1")
    assert f"| by run | rule | {NOT_AVAILABLE_FAMILY} |" in text


def test_rule_rows_render_in_reports_and_headline(recorded_rows: dict) -> None:
    v0 = format_tier(recorded_rows["V0", "aggregation"], "V0")
    assert f"| by run | rule | {NOT_AVAILABLE_TIER} | {NOT_AVAILABLE_TIER} |" in v0
    assert "| by run | rule | 0.000" not in v0
    assert "shared_credential_logins_n_above" in v0
    for key in (("V1", "aggregation"), ("V2", "aggregation"), ("V1", "all")):
        text = format_tier(recorded_rows[key], key[0])
        lines = [line for line in text.splitlines() if line.startswith("| by run | rule | ")]
        assert len(lines) == 5, key
        assert NOT_AVAILABLE_TIER not in "\n".join(lines)
    rows = [row for group in recorded_rows.values() for row in group]
    headline = format_headline(rows, [], [])
    by_run = headline.split("## V1 aggregation: offensive group size")[0]
    for tier, family in recorded_rows:
        assert f"| by run | {tier} | {family} | rule | " in by_run, (tier, family)
    assert f"| by run | V0 | aggregation | rule | {NOT_AVAILABLE_TIER} |" in by_run
    sizes = headline.split("## V1 aggregation: offensive group size")[1].split("## ")[0]
    assert "\n| rule | " in sizes and "not computed" not in sizes
    sharing = headline.split("## V1 aggregation: positives versus sharing controls")[1]
    assert "\n| rule | " in sharing.split("## ")[0]


def test_rule_is_reported_in_v2_all_and_held_out_splits() -> None:
    v2 = load_recorded(RECORDED, Tier.V2)
    ids = sorted(v2.records)[::3]
    split = split_by_run(ids, [v2.records[run].positive for run in ids], 0.3, 5)
    v1 = load_recorded(RECORDED, Tier.V1)
    held_out = held_out_splits({run: record.condition for run, record in v1.records.items()},
                               "channel")[0]
    config = replace(RECORDED_CONFIG, n_bootstrap=20)
    for data, chosen, family in ((v2, split, "all"), (v1, held_out, "aggregation")):
        result = evaluate_split(data, chosen, config, 7, family=family)
        rule = {row.metric: row for row in result.rows if row.method == RULE}
        assert RULE in result.fitted and f"{RULE}-online" in result.fitted, chosen.name
        for metric in ("auroc", "detection_rate", "false_positive_rate", "detection_coverage"):
            assert math.isfinite(rule[metric].value), (chosen.name, metric)
            assert rule[metric].note == "", (chosen.name, metric)
        text = format_tier(list(result.rows), data.tier.value)
        assert f"| {chosen.name} | rule | " in text


def test_new_attribution_tables_on_recorded_data(recorded_rows: dict) -> None:
    for key, rows in recorded_rows.items():
        for method in (*DETECTORS, ATTRIBUTION):
            by_metric = {row.metric: row for row in rows
                         if row.method == method and row.split == "by run"}
            precision = by_metric["attribution_precision"]
            assert precision.interval == "bootstrap" and precision.requested == 200, key
            wrong = [by_metric[metric] for metric in ROLE_METRICS]
            assert sum(cell.n for cell in wrong) == precision.total - precision.n, (key, method)
            assert by_metric["wrong_team_unresolved"].n == 0, (key, method)
            exact = by_metric["group_exact"]
            assert exact.total == 32 and 0 <= exact.n <= 32, (key, method)
            if method != ATTRIBUTION:
                assert by_metric["detected_strictly_before_completion"].n + by_metric[
                    "detected_at_completion"].n <= by_metric["detection_coverage"].n, (key, method)
    v0 = format_tier(recorded_rows["V0", "aggregation"], "V0")
    assert "### Group reconstruction" in v0 and "### Wrongly named agents" in v0
    assert f"| by run | rule | {NOT_AVAILABLE_TIER} | {NOT_AVAILABLE_TIER} | " in (
        v0.split("### Wrongly named agents")[1])
    v1 = format_tier(recorded_rows["V1", "aggregation"], "V1")
    roles = v1.split("### Wrongly named agents")[1].split("###")[0]
    assert "| by run | rule | " in roles and NOT_AVAILABLE_TIER not in roles
    assert "Detected strictly before completion" in v1 and "Detected at completion" in v1


def test_recorded_sharing_teams_reconcile_with_the_declared_counts() -> None:
    from swarmtrace.eval.groups import SHARING, UNRESOLVED, team_sharing

    v0, v1 = load_recorded(RECORDED, Tier.V0), load_recorded(RECORDED, Tier.V1)
    assert v0.shared_logins == v1.shared_logins
    declared = observed = mixed = 0
    for run, record in v1.records.items():
        teams = {label.group for label in record.labels.agents.values()
                 if label.role == "benign_team"}
        if not teams:
            assert run not in v1.shared_logins
            continue
        categories = team_sharing(record.labels, record.condition, v1.shared_logins[run])
        assert UNRESOLVED not in categories.values(), run
        count = record.condition["benign_sharing_teams"]
        declared += count
        observed += sum(category == SHARING for category in categories.values())
        mixed += 0 < count < len(teams)
    assert declared == observed == 71
    assert mixed == 51


def test_degenerate_bootstrap_intervals_are_qualified() -> None:
    def row(metric: str, value: float, n: int, total: int) -> MetricRow:
        return MetricRow("V1", "by run", IN_DISTRIBUTION, "logistic", metric, value, value,
                         value, n, total, 200, 200, "", unit="agents")

    text = format_tier([row("attribution_recall", 0.0, 0, 97),
                        row("attribution_precision", 1.0, 97, 97),
                        replace(row("group_exact", 0.5, 16, 32), unit="runs")], "V1")
    assert ("0.000 (0 of 97 agents; 200/200 resamples; degenerate bootstrap interval "
            "[0.000, 0.000]: all valid resamples were zero; does not establish zero population "
            "recall)") in text
    assert ("1.000 (97 of 97 agents; 200/200 resamples; degenerate bootstrap interval "
            "[1.000, 1.000]: all valid resamples were one; does not establish a population "
            "precision of one)") in text
    assert ("0.500 (16 of 32 runs; 200/200 resamples; degenerate bootstrap interval "
            "[0.500, 0.500]: all valid resamples were equal; does not establish a population "
            "exact-reconstruction rate of exactly 0.500)") in text
    assert "A degenerate bootstrap interval" in text
    spread = replace(row("attribution_recall", 0.4, 39, 97), low=0.3, high=0.5)
    assert "0.400 [0.300, 0.500] (39 of 97 agents" in format_tier([spread], "V1")
    auroc_row = replace(row("auroc", 1.0, 118, 118), unit="runs")
    assert "1.000 [1.000, 1.000] (118 of 118 runs" in format_tier([auroc_row], "V1")
