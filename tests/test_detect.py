import ast
import inspect
import math
import subprocess
import sys
import typing
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import swarmtrace.detect as detect
from swarmtrace.detect import (
    CHECKPOINT_EVERY,
    RULE,
    RULE_COLUMN,
    RUN_MODELS,
    VOLUME_COLUMNS,
    OnlineDetector,
    PairScorer,
    RunDetector,
    checkpoints,
    conformal_threshold,
    first_detection_tick,
    propose_groups,
    volume_features,
)
from swarmtrace.features import (
    PAIR_FEATURES,
    THRESHOLDS,
    agent_features,
    feature_columns,
    pair_features,
    run_features,
)
from swarmtrace.trace.io import Labels, Manifest, Trace, read_trace
from swarmtrace.trace.schema import TraceEvent
from swarmtrace.trace.tiers import Tier

BLOCKED = ("swarmtrace.sim", "swarmtrace.world", "swarmtrace.agents", "swarmtrace.objectives")


def run_matrix(seed: int, n: int = 120, separation: float = 2.0) -> tuple[pd.DataFrame, np.ndarray]:
    rng = np.random.default_rng(seed)
    labels = np.arange(n) % 2 == 0
    frame = pd.DataFrame(
        {
            "signal": rng.normal(size=n) + separation * labels,
            "noise": rng.normal(size=n),
            "sparse": np.where(rng.random(n) < 0.4, np.nan, rng.normal(size=n)),
            "empty": np.full(n, np.nan),
        },
        index=pd.Index([f"{i:016x}" for i in range(n)], name="run_id"),
    )
    return frame, labels


def test_volume_features_from_agent_frame(fixtures_dir: Path) -> None:
    trace = read_trace(fixtures_dir / "messaging_pair" / "trace.jsonl", Tier.V0)
    agents = agent_features(trace)
    frame = volume_features(agents, trace.run_id)
    assert tuple(frame.columns) == VOLUME_COLUMNS
    assert list(frame.index) == [trace.run_id]
    counts = agents["n_events"].to_numpy(dtype=float)
    row = frame.iloc[0]
    assert row["n_agents"] == len(agents)
    assert row["n_events"] == counts.sum()
    assert row["events_per_agent_mean"] == pytest.approx(counts.mean())
    assert row["events_per_agent_max"] == counts.max()
    assert row["events_per_agent_std"] == pytest.approx(counts.std())


def test_volume_features_of_empty_prefix_are_zero(fixtures_dir: Path) -> None:
    trace = read_trace(fixtures_dir / "all_benign" / "trace.jsonl", Tier.V0)
    frame = volume_features(agent_features(trace, until_tick=-1), trace.run_id)
    assert frame.iloc[0].tolist() == [0.0] * len(VOLUME_COLUMNS)


def test_conformal_threshold_is_the_finite_sample_quantile_of_controls() -> None:
    scores = np.arange(1.0, 20.0)
    assert conformal_threshold(scores, 0.05) == 19.0
    scores = np.arange(1.0, 40.0)
    assert conformal_threshold(scores, 0.05) == 38.0
    assert conformal_threshold(np.arange(1.0, 11.0), 0.05) == math.inf
    assert conformal_threshold(np.array([]), 0.05) == math.inf
    assert conformal_threshold(np.array([0.3, 0.1, 0.2]), 0.5) == 0.2
    with pytest.raises(ValueError):
        conformal_threshold(scores, 1.5)


def calibrated(model: str, seed: int, fit: int, calibration: int) -> RunDetector:
    train, train_y = run_matrix(fit)
    held, held_y = run_matrix(calibration)
    return RunDetector(model, seed=seed).fit(train, train_y).calibrate(held, held_y)


@pytest.mark.parametrize("model", RUN_MODELS)
def test_run_detector_separates_planted_signal_without_warnings(model: str) -> None:
    test, test_y = run_matrix(2)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        detector = calibrated(model, 3, 1, 10)
        scores = detector.score(test)
    assert np.all(np.isfinite(scores))
    assert scores[test_y].mean() > scores[~test_y].mean()
    assert math.isfinite(detector.threshold)


@pytest.mark.parametrize("model", RUN_MODELS)
def test_run_detector_is_deterministic_given_seed(model: str) -> None:
    train, _ = run_matrix(4)
    first, second = calibrated(model, 7, 4, 11), calibrated(model, 7, 4, 11)
    np.testing.assert_array_equal(first.score(train), second.score(train))
    assert first.threshold == second.threshold


@pytest.mark.parametrize("model", RUN_MODELS)
def test_run_detector_threshold_is_conformal_on_calibration_controls(model: str) -> None:
    held, held_y = run_matrix(12)
    detector = calibrated(model, 1, 5, 12)
    assert detector.threshold == conformal_threshold(detector.score(held)[~held_y], 0.05)
    np.testing.assert_array_equal(detector.calibration_scores, detector.score(held)[~held_y])


def test_run_detector_never_fires_with_a_tiny_calibration_set() -> None:
    train, train_y = run_matrix(6)
    held, held_y = run_matrix(13, n=20)
    detector = RunDetector("logistic", seed=0).fit(train, train_y).calibrate(held, held_y)
    assert detector.threshold == math.inf
    assert not detector.flag(train * 1000).any()


def test_run_detector_state_depends_only_on_fitting_and_calibration_data() -> None:
    test, _ = run_matrix(7)
    detector = calibrated("boosted", 0, 6, 14)
    threshold, scores = detector.threshold, detector.score(test).copy()
    detector.score(test * 1000)
    assert detector.threshold == threshold
    np.testing.assert_array_equal(detector.score(test), scores)


def test_run_detector_rejects_other_columns_single_class_and_uncalibrated_use() -> None:
    train, train_y = run_matrix(8)
    detector = RunDetector("logistic", seed=0).fit(train, train_y)
    with pytest.raises(ValueError):
        detector.flag(train)
    with pytest.raises(ValueError):
        detector.score(train.drop(columns="noise"))
    with pytest.raises(ValueError):
        RunDetector("logistic", seed=0).fit(train, np.zeros(len(train), dtype=bool))
    with pytest.raises(ValueError):
        RunDetector("forest", seed=0)


def test_run_detector_flags_scores_strictly_above_threshold() -> None:
    train, _ = run_matrix(9)
    detector = calibrated("logistic", 0, 9, 15)
    np.testing.assert_array_equal(
        detector.flag(train), detector.score(train) > detector.threshold
    )


def pair_frame(seed: int, runs: int = 30) -> tuple[pd.DataFrame, np.ndarray]:
    rng = np.random.default_rng(seed)
    columns = feature_columns("pair", Tier.V0)
    rows, index, labels = [], [], []
    for run in range(runs):
        agents = [f"a-{run:04x}{i:04x}" for i in range(6)]
        group = set(agents[:3]) if run % 2 == 0 else set()
        for i in range(6):
            for j in range(i + 1, 6):
                positive = agents[i] in group and agents[j] in group
                row = {column: rng.normal() for column in columns}
                row["handoff_latency_mean"] = (
                    rng.uniform(0, 1) if positive else rng.choice([np.nan, rng.uniform(3, 6)])
                )
                row["target_overlap"] = rng.uniform(0.5, 1.0) if positive else rng.uniform(0, 0.4)
                rows.append(row)
                index.append((f"{run:016x}", agents[i], agents[j]))
                labels.append(positive)
    frame = pd.DataFrame(
        rows,
        columns=list(columns),
        index=pd.MultiIndex.from_tuples(index, names=["run_id", "agent_a", "agent_b"]),
    )
    return frame, np.array(labels)


def test_pair_scorer_respects_declared_directions_and_nan_is_no_evidence() -> None:
    train, labels = pair_frame(1)
    scorer = PairScorer(seed=0).fit(train, labels)
    base = train.iloc[[0]].copy()
    base["target_overlap"] = 0.5
    latencies = [0.0, 1.0, 3.0, 6.0, np.nan]
    probes = pd.concat([base.assign(handoff_latency_mean=value) for value in latencies])
    scores = scorer.score(probes)
    assert all(a >= b for a, b in zip(scores, scores[1:]))
    assert scores[0] > scores[-1]
    overlaps = pd.concat([base.assign(target_overlap=value) for value in [0.0, 0.3, 0.6, 0.9]])
    by_overlap = scorer.score(overlaps)
    assert all(a <= b for a, b in zip(by_overlap, by_overlap[1:]))
    directions = {spec.name: spec.direction for spec in PAIR_FEATURES}
    assert directions["handoff_latency_mean"] == "lower"


def test_pair_scorer_attributes_planted_groups_and_ignores_test_data() -> None:
    train, labels = pair_frame(2)
    test, test_labels = pair_frame(3)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        scorer = PairScorer(seed=0).fit(train, labels)
    threshold = scorer.threshold
    scores = scorer.score(test)
    assert scores[test_labels].mean() > scores[~test_labels].mean()
    scorer.score(test * 0)
    assert scorer.threshold == threshold
    groups = scorer.propose(test)
    flagged = {agent for run_groups in groups.values() for group in run_groups for agent in group}
    planted = {
        agent
        for (_, a, b), positive in zip(test.index, test_labels)
        if positive
        for agent in (a, b)
    }
    assert len(flagged & planted) / len(flagged) > 0.8
    assert len(flagged & planted) / len(planted) > 0.8
    assert set(groups) == set(test.index.get_level_values("run_id"))


def test_pair_scorer_is_deterministic() -> None:
    train, labels = pair_frame(4)
    first = PairScorer(seed=5).fit(train, labels)
    second = PairScorer(seed=5).fit(train, labels)
    assert first.threshold == second.threshold
    np.testing.assert_array_equal(first.score(train), second.score(train))


def test_propose_groups_returns_connected_components_above_threshold() -> None:
    index = pd.MultiIndex.from_tuples(
        [("a", "b"), ("b", "c"), ("c", "d"), ("e", "f"), ("g", "h")],
        names=["agent_a", "agent_b"],
    )
    scores = pd.Series([0.9, 0.8, 0.1, 0.7, 0.5], index=index)
    assert propose_groups(scores, 0.5) == [frozenset("abc"), frozenset("ef")]
    assert propose_groups(scores, 0.95) == []


def test_first_detection_tick_is_lazy_and_strict() -> None:
    seen: list[int] = []

    def score_at(tick: int) -> float:
        seen.append(tick)
        return [0.1, 0.5, 0.6, 0.9][tick]

    assert first_detection_tick(score_at, range(4), 0.5) == 2
    assert seen == [0, 1, 2]
    assert first_detection_tick(score_at, range(4), 0.95) is None


def test_detect_imports_without_simulation_packages() -> None:
    script = f"""
import sys
for name in {BLOCKED!r}:
    sys.modules[name] = None
import swarmtrace.detect
assert "swarmtrace.eval" not in sys.modules
"""
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_detect_never_touches_label_side() -> None:
    package = Path(detect.__file__).parent
    for path in package.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        for forbidden in ("labels.json", "manifest.json", "read_labels", "read_manifest",
                          "Labels", "Manifest", "RunPaths", "read_trace", "open("):
            assert forbidden not in source, (path.name, forbidden)
        for node in ast.walk(ast.parse(source)):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            for name in names:
                assert not name.startswith(BLOCKED + ("swarmtrace.eval",)), (path.name, name)


def test_detect_public_functions_are_typed_and_label_free() -> None:
    def mentions(hint: object) -> bool:
        if hint in (Labels, Manifest):
            return True
        return any(mentions(argument) for argument in typing.get_args(hint))

    members = [getattr(detect, name) for name in detect.__all__]
    callables = [m for m in members if inspect.isfunction(m)]
    callables += [
        method
        for m in members if inspect.isclass(m)
        for name, method in inspect.getmembers(m, inspect.isfunction)
        if not name.startswith("_") or name == "__init__"
    ]
    assert callables
    for function in callables:
        hints = typing.get_type_hints(function)
        parameters = set(inspect.signature(function).parameters) - {"self"}
        assert parameters | {"return"} <= set(hints) | {"return"}, function.__qualname__
        assert "return" in hints or function.__name__ == "__init__", function.__qualname__
        assert not any(mentions(hint) for hint in hints.values()), function.__qualname__


def test_pair_scorer_spreads_positive_runs_across_folds() -> None:
    pairs, labels = pair_frame(6, runs=20)
    runs = pairs.index.get_level_values("run_id")
    keep = np.isin(runs, sorted(set(runs[labels]))[:2]) | ~np.isin(runs, sorted(set(runs[labels])))
    for seed in range(8):
        scorer = PairScorer(seed=seed).fit(pairs[keep], labels[keep])
        assert math.isfinite(scorer.threshold)


def test_pair_scorer_imputes_each_fold_from_its_own_training_runs() -> None:
    pairs, labels = pair_frame(7, runs=20)
    assert pairs["handoff_latency_mean"].isna().sum() > 10
    baseline = PairScorer(seed=2).fit(pairs, labels)
    runs = pairs.index.get_level_values("run_id")
    outlier_run = runs[0]
    row = int(np.flatnonzero(runs == outlier_run)[0])
    shifted = pairs.copy()
    shifted.iloc[row, shifted.columns.get_loc("handoff_latency_mean")] = 1e6
    changed = PairScorer(seed=2).fit(shifted, labels)
    np.testing.assert_array_equal(baseline.folds, changed.folds)
    same_fold = baseline.folds == baseline.folds[row]
    same_fold[row] = False
    np.testing.assert_array_equal(baseline.oof_scores[same_fold], changed.oof_scores[same_fold])
    outlier_fold = baseline.folds[row]
    np.testing.assert_array_equal(
        baseline.fold_fills[outlier_fold], changed.fold_fills[outlier_fold]
    )
    other = (outlier_fold + 1) % len(changed.fold_fills)
    assert changed.fold_fills[other][list(changed.columns).index("handoff_latency_mean")] == -1e6
    assert changed.fill[list(changed.columns).index("handoff_latency_mean")] == -1e6


def prefix_matrix(seed: int, runs: int = 80) -> tuple[pd.DataFrame, np.ndarray]:
    rng = np.random.default_rng(seed)
    rows, index, labels = [], [], []
    for run in range(runs):
        positive = run % 2 == 0
        for step, tick in enumerate((7, 15, 23)):
            rows.append({
                "signal": rng.normal() + (1.5 * (step + 1) if positive else 0.0),
                "noise": rng.normal(),
                "sparse": np.nan if step == 0 else rng.normal(),
            })
            index.append((f"{run:016x}", tick))
            labels.append(positive)
    frame = pd.DataFrame(
        rows, index=pd.MultiIndex.from_tuples(index, names=["run_id", "tick"])
    )
    return frame, np.array(labels)


def test_checkpoints_follow_a_fixed_cadence_plus_the_final_tick() -> None:
    assert CHECKPOINT_EVERY == 8
    assert checkpoints(15) == (7, 15)
    assert checkpoints(20) == (7, 15, 20)
    assert checkpoints(3) == (3,)
    assert checkpoints(23, every=4) == (3, 7, 11, 15, 19, 23)
    with pytest.raises(ValueError):
        checkpoints(-1)


def test_online_threshold_is_conformal_on_calibration_control_run_maxima() -> None:
    train, train_y = prefix_matrix(1)
    held, held_y = prefix_matrix(3)
    for model in RUN_MODELS:
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            detector = OnlineDetector(model, seed=0).fit(train, train_y).calibrate(held, held_y)
        runs = held.index.get_level_values("run_id")
        run_max = pd.Series(detector.score(held), index=runs).groupby(level=0).max()
        run_label = pd.Series(held_y, index=runs).groupby(level=0).first()
        assert detector.threshold == conformal_threshold(run_max[~run_label].to_numpy(), 0.05)
        pd.testing.assert_series_equal(detector.run_scores(held), run_max, check_names=False)


def test_online_detector_never_fires_with_a_tiny_calibration_set() -> None:
    train, train_y = prefix_matrix(1)
    held, held_y = prefix_matrix(3, runs=10)
    detector = OnlineDetector("logistic", seed=0).fit(train, train_y).calibrate(held, held_y)
    assert detector.threshold == math.inf
    assert set(detector.first_crossings(train).values()) == {None}


def test_online_detector_first_crossings_and_training_only_state() -> None:
    train, train_y = prefix_matrix(4)
    held, held_y = prefix_matrix(7)
    test, _ = prefix_matrix(5, runs=20)
    detector = OnlineDetector("boosted", seed=1).fit(train, train_y).calibrate(held, held_y)
    threshold = detector.threshold
    assert math.isfinite(threshold)
    crossings = detector.first_crossings(test)
    assert set(crossings) == set(test.index.get_level_values("run_id"))
    scores = pd.Series(detector.score(test), index=test.index)
    for run, tick in crossings.items():
        above = scores.loc[run][scores.loc[run] > threshold]
        assert tick == (int(above.index.min()) if len(above) else None)
    detector.score(test * 1e6)
    assert detector.threshold == threshold
    again = OnlineDetector("boosted", seed=1).fit(train, train_y).calibrate(held, held_y)
    assert again.threshold == threshold


def test_online_detector_rejects_labels_that_vary_within_a_run() -> None:
    prefixes, labels = prefix_matrix(6)
    labels = labels.copy()
    labels[0] = ~labels[0]
    with pytest.raises(ValueError):
        OnlineDetector("logistic", seed=0).fit(prefixes, labels)
    good, good_y = prefix_matrix(6)
    with pytest.raises(ValueError):
        OnlineDetector("logistic", seed=0).fit(good, good_y).calibrate(prefixes, labels)


@pytest.mark.parametrize("kind", ["run", "online"])
def test_refit_clears_calibration_until_recalibrated(kind: str) -> None:
    if kind == "run":
        first, first_y = run_matrix(20)
        held, held_y = run_matrix(21)
        second, second_y = run_matrix(22)
        detector = RunDetector("logistic", seed=0)

        def detect() -> object:
            return detector.flag(held)
    else:
        first, first_y = prefix_matrix(20)
        held, held_y = prefix_matrix(21)
        second, second_y = prefix_matrix(22)
        detector = OnlineDetector("logistic", seed=0)

        def detect() -> object:
            return detector.first_crossings(held)

    detector.fit(first, first_y).calibrate(held, held_y)
    assert math.isfinite(detector.threshold)
    detect()
    detector.fit(second, second_y)
    assert math.isnan(detector.threshold)
    assert detector.calibration_scores.size == 0
    with pytest.raises(ValueError, match="calibrate"):
        detect()
    detector.calibrate(held, held_y)
    assert math.isfinite(detector.threshold)
    detect()


def rule_matrix(counts: list[int]) -> pd.DataFrame:
    rng = np.random.default_rng(len(counts))
    return pd.DataFrame(
        {"noise": rng.normal(size=len(counts)), RULE_COLUMN: np.array(counts, dtype="int64")},
        index=pd.Index([f"{i:016x}" for i in range(len(counts))], name="run_id"),
    )


def test_rule_column_counts_pairs_with_a_shared_login(fixtures_dir: Path) -> None:
    assert RULE_COLUMN == "shared_credential_logins_n_above"
    assert THRESHOLDS["shared_credential_logins"] == 0.0
    a, b, c, d = "a-00000001", "a-00000002", "a-00000003", "a-00000004"
    rows = [
        (0, a, "c-00000001"), (1, b, "c-00000001"), (2, b, "c-00000001"),
        (3, c, "c-00000001"), (4, c, "c-00000002"), (5, d, "c-00000002"),
        (6, d, "c-00000003"),
    ]
    events = [
        TraceEvent(schema_version=1, run_id="0123456789abcdef", seq=seq, tick=tick, agent=agent,
                   tool="login", target="h-00000001", args={"credential": credential},
                   result={"status": "ok", "size": 0}, content=None, provenance=None)
        for seq, (tick, agent, credential) in enumerate(rows)
    ]
    built = Trace("0123456789abcdef", Tier.V1, tuple(events))
    relay = read_trace(fixtures_dir / "credential_relay" / "trace.jsonl", Tier.V1)
    benign = read_trace(fixtures_dir / "benign_team" / "trace.jsonl", Tier.V1)
    seen = []
    for trace in (built, relay, benign):
        logins = pair_features(trace)["shared_credential_logins"]
        expected = int((logins >= 1).sum())
        assert run_features(trace).loc[trace.run_id, RULE_COLUMN] == expected
        seen.append((expected, int(logins.max()), int((logins == 0).sum())))
    # The built trace has pairs with one and with two shared logins, and pairs with none.
    assert seen[0] == (3, 2, 3)
    assert seen[1][0] >= 1


def test_rule_detector_scores_the_column_without_fitted_parameters() -> None:
    train = rule_matrix([0, 3, 0, 1, 0, 2, 0, 0])
    labels = np.array([False, True, False, True, False, True, False, False])
    held = rule_matrix([2, 0, 5, 1])
    for detector in (RunDetector(RULE, seed=0), RunDetector(RULE, seed=99)):
        detector.fit(train, labels)
        np.testing.assert_array_equal(detector.score(held), [2.0, 0.0, 5.0, 1.0])
        assert detector.columns == tuple(train.columns)
    shuffled = RunDetector(RULE, seed=0).fit(train, labels[::-1])
    np.testing.assert_array_equal(shuffled.score(held), [2.0, 0.0, 5.0, 1.0])
    with pytest.raises(ValueError, match=RULE_COLUMN):
        RunDetector(RULE, seed=0).fit(train.drop(columns=RULE_COLUMN), labels)
    with pytest.raises(ValueError):
        RunDetector(RULE, seed=0).fit(train, labels).score(held.drop(columns="noise"))
    assert RULE not in RUN_MODELS


def test_rule_detector_ties_use_the_strict_threshold_rule() -> None:
    controls = [0] * 30 + [1] * 8 + [2]
    calibration = rule_matrix(controls + [3, 4])
    labels = np.array([False] * len(controls) + [True, True])
    detector = RunDetector(RULE, seed=0).fit(calibration, labels).calibrate(calibration, labels)
    assert detector.threshold == conformal_threshold(np.array(controls, dtype=float), 0.05)
    assert detector.threshold == 1.0
    np.testing.assert_array_equal(detector.calibration_scores, controls)
    test = rule_matrix([0, 1, 1, 2, 7])
    np.testing.assert_array_equal(detector.flag(test), [False, False, False, True, True])


def test_online_rule_detector_uses_the_prefix_count() -> None:
    index = pd.MultiIndex.from_tuples(
        [(run, tick) for run in ("r0", "r1", "r2", "r3") for tick in (7, 15)],
        names=("run_id", "tick"),
    )
    counts = [0, 0, 0, 1, 1, 2, 0, 0]
    prefixes = pd.DataFrame({"noise": np.arange(8.0), RULE_COLUMN: counts}, index=index)
    labels = np.array([False, False, True, True, True, True, False, False])
    detector = OnlineDetector(RULE, seed=0, max_fpr=0.5).fit(prefixes, labels)
    np.testing.assert_array_equal(detector.score(prefixes), counts)
    detector.calibrate(prefixes, labels)
    assert detector.threshold == conformal_threshold(np.array([0.0, 0.0]), 0.5)
    assert detector.first_crossings(prefixes) == {"r0": None, "r1": 15, "r2": 7, "r3": None}


def scope_matrix(columns: dict[str, list[float]]) -> pd.DataFrame:
    rows = len(next(iter(columns.values())))
    return pd.DataFrame(
        {"noise": np.arange(rows, dtype=float), RULE_COLUMN: np.zeros(rows, dtype="int64"),
         **{name: np.array(values, dtype=float) for name, values in columns.items()}},
        index=pd.Index([f"{i:016x}" for i in range(rows)], name="run_id"),
    )


def test_scope_rule_scores_its_column_without_fitted_parameters() -> None:
    from swarmtrace.detect import SCOPE_RULE, SCOPE_RULE_COLUMNS

    assert SCOPE_RULE == "scope_rule"
    assert SCOPE_RULE_COLUMNS == ("out_of_scope_reads_borrowed_max", "borrowed_session_breadth_max")
    assert SCOPE_RULE not in RUN_MODELS
    labels = np.array([False, True, False, True])
    breadth = [0.0, 4.0, 1.0, 6.0]
    out_of_scope = [0.0, 2.0, 0.0, 5.0]
    c0 = scope_matrix({"borrowed_session_breadth_max": breadth})
    c2 = scope_matrix({"borrowed_session_breadth_max": breadth,
                       "out_of_scope_reads_borrowed_max": out_of_scope})
    for seed in (0, 99):
        np.testing.assert_array_equal(
            RunDetector(SCOPE_RULE, seed=seed).fit(c0, labels).score(c0), breadth)
        np.testing.assert_array_equal(
            RunDetector(SCOPE_RULE, seed=seed).fit(c2, labels[::-1]).score(c2), out_of_scope)
    calibrated = RunDetector(SCOPE_RULE, seed=0).fit(c0, labels).calibrate(c0, labels)
    np.testing.assert_array_equal(calibrated.calibration_scores, [0.0, 1.0])
    assert calibrated.threshold == conformal_threshold(np.array([0.0, 1.0]), 0.05)
    with pytest.raises(ValueError, match="borrowed_session_breadth_max"):
        RunDetector(SCOPE_RULE, seed=0).fit(scope_matrix({"other": breadth}), labels)


def test_rule_is_unchanged_by_scope_columns() -> None:
    frame = scope_matrix({"borrowed_session_breadth_max": [5.0, 0.0, 3.0, 1.0],
                          "out_of_scope_reads_borrowed_max": [9.0, 9.0, 9.0, 9.0]})
    frame[RULE_COLUMN] = np.array([0, 2, 0, 1], dtype="int64")
    detector = RunDetector(RULE, seed=0).fit(frame, np.array([False, True, False, True]))
    np.testing.assert_array_equal(detector.score(frame), [0.0, 2.0, 0.0, 1.0])


def test_files_rule_scores_only_its_column_without_fitted_parameters() -> None:
    from swarmtrace.detect import FILES_RULE, FILES_RULE_COLUMN

    assert FILES_RULE == "files_rule" and FILES_RULE_COLUMN == "distinct_files_read_max"
    assert FILES_RULE not in RUN_MODELS
    frame = scope_matrix({FILES_RULE_COLUMN: [0, 4, 1, 6],
                          "borrowed_session_breadth_max": [90, 80, 70, 60]})
    labels = np.array([False, True, False, True])
    for seed in (0, 99):
        model = RunDetector(FILES_RULE, seed).fit(frame, labels).calibrate(frame, labels)
        np.testing.assert_array_equal(model.score(frame), [0, 4, 1, 6])
        np.testing.assert_array_equal(model.calibration_scores, [0, 1])
    with pytest.raises(ValueError, match="distinct_files_read_max"):
        RunDetector(FILES_RULE, 0).fit(frame.drop(columns=FILES_RULE_COLUMN), labels)
