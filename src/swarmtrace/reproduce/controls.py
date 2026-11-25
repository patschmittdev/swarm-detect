from collections.abc import Mapping, Sequence

import numpy as np

from swarmtrace.detect import RULE, RunDetector
from swarmtrace.eval.data import TierData
from swarmtrace.eval.harness import (
    DETECTORS,
    REPORTED_DETECTORS,
    SEED_INDEX,
    child_seed,
    family_data,
    rule_unavailable,
)
from swarmtrace.eval.metrics import auroc
from swarmtrace.eval.splits import CALIBRATION_FRACTION, calibration_split, split_by_run

LoudFlags = dict[str, dict[str, list[bool]]]
LOUD_GATING_BARS = {
    "logistic": ("calibrated_threshold", "nonsharing_controls", "all_controls"),
    "boosted": ("calibrated_threshold", "nonsharing_controls"),
}
NOT_GATED = "not gated (no bars)"
"""The rule baseline's required-bars cell: it has no loud bars, so it never gates reproduce."""
_BAR_DESCRIPTIONS = {
    "calibrated_threshold": "flagged at the calibrated threshold",
    "nonsharing_controls": "above every calibration control with benign_sharing_teams == 0",
    "all_controls": "above every calibration control",
}


def shuffled_labels(labels: Mapping[str, bool], seed: int) -> dict[str, bool]:
    """Permute labels once per run, retaining the class balance and sorted run order."""
    ids = sorted(labels)
    rng = np.random.default_rng(np.random.SeedSequence(seed))
    values = rng.permutation([labels[run] for run in ids])
    return {run: bool(value) for run, value in zip(ids, values, strict=True)}


def require_loud_detection(flags: Mapping[str, Mapping[str, Sequence[bool]]]) -> None:
    """Require the named bars on every loud run; boosted's all-controls bar is diagnostic."""
    failures = []
    expected = None
    for method, bars in LOUD_GATING_BARS.items():
        for bar in bars:
            values = np.asarray(flags.get(method, {}).get(bar, ()), dtype=bool)
            if expected is None and values.ndim == 1 and values.size:
                expected = values.size
            if (values.ndim != 1 or not values.size or values.size != expected
                    or not values.all()):
                failures.append(f"{method}: {bar} ({_BAR_DESCRIPTIONS[bar]})")
    if failures:
        raise ValueError("loud positive control failed at V1 with aggregation features; "
                         "failed gating bars: " + "; ".join(failures) + ". "
                         "See controls.md and calibration counts; "
                         "no successful reproduction claimed.")


def above_calibration_controls(
    scores: Sequence[float], calibration_scores: Sequence[float],
) -> list[bool]:
    """A strict comparison, rejecting ties, missing calibration, and non-finite scores."""
    scores = np.asarray(scores, dtype=float)
    controls = np.asarray(calibration_scores, dtype=float)
    if not controls.size or not np.isfinite(controls).all():
        return [False] * len(scores)
    return (np.isfinite(scores) & (scores > controls.max())).tolist()


def loud_bar_rows(controls: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    """Keep each V1 aggregation bar visible, including the non-gating boosted strict result.

    The rule baseline gets the same three comparisons as diagnostic rows, every one non-gating.
    """
    rows = []
    specs = (
        ("calibrated_threshold", "loud_at_calibrated_threshold_count",
         "loud_at_calibrated_threshold", "threshold", "calibrated threshold"),
        ("nonsharing_controls", "loud_above_nonsharing_controls", "loud_nonsharing_rate",
         "nonsharing_calibration_max", "highest non-sharing calibration control"),
        ("all_controls", "loud_above_all_calibration_controls", "loud_rate",
         "calibration_max", "highest calibration control"),
    )
    for row in controls:
        method = row["detector"]
        if (row["tier"] != "V1" or row["family"] != "aggregation"
                or row["mode"] != "full-trace" or method not in (*LOUD_GATING_BARS, RULE)):
            continue
        if method == RULE and isinstance(row["loud_min"], str):
            continue
        for bar, count, rate, bound, label in specs:
            met = row[count] == row["loud_runs"] and row["loud_runs"] > 0
            note = ""
            if method == RULE:
                note = "Rule baseline: no fitted parameters and no gating bars; diagnostic only."
            if method == "boosted" and bar == "all_controls":
                note = ("Boosted is not monotone in shared-login counts and is flat beyond its "
                        "fitting range, so extra re-use does not raise its score."
                        + (" A calibration control with a sharing team scores at or above a loud run."
                           if row["sharing_calibration_max"] >= row["loud_min"] else "")
                        + " Reported, not gated.")
            rows.append({
                **{key: row[key] for key in ("seed", "split", "tier", "family", "detector")},
                "bar": bar, "gating": "yes" if bar in LOUD_GATING_BARS.get(method, ())
                else "no (non-gating)",
                "outcome": (f"{'met' if met else 'not met'}: lowest loud {row['loud_min']:.4f}, "
                            f"{label} {row[bound]:.4f}"),
                "loud_rate": row[rate], "note": note,
                **{key: row[key] for key in (
                    "fitting_controls", "fitting_positive", "calibration_controls",
                    "calibration_positive", "test_controls", "test_positive",
                    "nonsharing_calibration_controls",
                )},
            })
    return rows


def negative_control(
    data: TierData, family: str, seed: int, repeats: int,
) -> list[dict[str, str | int | float]]:
    """Refit with shuffled run labels. Calibration and test rows never enter model fitting.

    The rule baseline has nothing to refit; its AUROC is its fixed count against the shuffled
    test labels. Where its column is unavailable its row says so instead of giving values.
    """
    data = family_data(data, family)
    ids = sorted(data.records)
    truth = {run: data.records[run].positive for run in ids}
    unavailable = rule_unavailable(data.runs.columns, data.tier)
    scores: dict[str, list[float]] = {method: [] for method in REPORTED_DETECTORS}
    counts = {}
    for repeat in range(repeats):
        labels = shuffled_labels(truth, child_seed(seed, 50, repeat))
        split = split_by_run(ids, [labels[run] for run in ids], 0.3, child_seed(seed, 51, repeat))
        fitting, calibration = calibration_split(
            split.train, [labels[run] for run in split.train], CALIBRATION_FRACTION,
            child_seed(seed, 52, repeat),
        )
        counts = {"fitting_controls": sum(not labels[run] for run in fitting),
                  "fitting_positive": sum(labels[run] for run in fitting),
                  "calibration_controls": sum(not labels[run] for run in calibration),
                  "calibration_positive": sum(labels[run] for run in calibration),
                  "test_controls": sum(not labels[run] for run in split.test),
                  "test_positive": sum(labels[run] for run in split.test)}
        y_fit = np.array([labels[run] for run in fitting], dtype=bool)
        y_test = np.array([labels[run] for run in split.test], dtype=bool)
        for method in REPORTED_DETECTORS:
            if method == RULE:
                if unavailable is None:
                    rule = RunDetector(RULE, child_seed(seed, 53, repeat, SEED_INDEX[RULE]))
                    rule.fit(data.runs.loc[list(fitting)], y_fit)
                    test = data.runs.loc[list(split.test)]
                    scores[RULE].append(auroc(y_test, rule.score(test)))
                continue
            index = DETECTORS.index(method)
            matrix = data.volume if method == "volume" else data.runs
            model = "boosted" if method == "boosted" else "logistic"
            detector = RunDetector(model, child_seed(seed, 53, repeat, index))
            detector.fit(matrix.loc[list(fitting)], y_fit)
            scores[method].append(auroc(y_test, detector.score(matrix.loc[list(split.test)])))

    def summary(method: str, values: list[float]) -> dict[str, str | float]:
        if method == RULE and unavailable is not None:
            return dict.fromkeys(("auroc_mean", "auroc_se", "auroc_min", "auroc_max"),
                                 unavailable)
        return {"auroc_mean": float(np.mean(values)),
                "auroc_se": (float(np.std(values, ddof=1) / np.sqrt(repeats))
                             if repeats > 1 else float("nan")),
                "auroc_min": min(values), "auroc_max": max(values)}

    return [{"seed": seed, "split": "by run (permuted)",
             "tier": data.tier.value, "family": family,
             "method": "volume (family-independent)" if method == "volume" else method,
             "repeats": repeats, **summary(method, values),
             **counts} for method, values in scores.items()]
