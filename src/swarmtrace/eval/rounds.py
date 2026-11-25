"""Compare a candidate and incumbent on paired, held-out runs at a fixed alert budget."""

import math
from collections.abc import Sequence
from pathlib import Path

import numpy as np
import pandas as pd

from .metrics import ratio, wilson
from .scope import MAX_FPR

MINIMUM_GAIN = {"main": 0.03, "scope": 0.01}
LABELS = ["positive", "small_positive", "hard_control"]
SCORE_COLUMNS = {
    "task", "test_set", "split_seed", "run_id", "detector", "score", "threshold", *LABELS,
}


def _paired_grid(path: Path, task: str, reference: str, candidate: str) -> pd.DataFrame:
    table = pd.read_csv(path, dtype={"run_id": str, "score": str, "threshold": str},
                        keep_default_na=False)
    missing = SCORE_COLUMNS.difference(table.columns)
    if missing:
        raise ValueError(f"{path} lacks score columns {sorted(missing)}")
    rows = table.loc[(table.task == task) & table.detector.isin([reference, candidate])].copy()
    if rows.empty or not (rows.test_set == "independent").all():
        raise ValueError(f"{path} needs independent scores for {task}, {reference} and {candidate}")
    if (rows.run_id == "").any() or rows.duplicated(["run_id", "detector"]).any():
        raise ValueError(f"{path} needs one score per detector and run id")
    if rows.split_seed.nunique() != 1 or (rows.split_seed == "").any():
        raise ValueError(f"{path} needs one archive split seed for both detectors")
    bool_values = {"true": True, "false": False, "1": True, "0": False}
    for column in LABELS:
        parsed = rows[column].astype(str).str.lower().map(bool_values)
        if parsed.isna().any():
            raise ValueError(f"{path} has a missing or invalid {column} label")
        rows[column] = parsed
    if (rows.small_positive & ~rows.positive).any() or (rows.hard_control & rows.positive).any():
        raise ValueError(f"{path} contains an inconsistent subgroup label")
    # Preserve even a one-ulp difference from a frozen cutoff in the score export.
    rows["score"] = rows.score.map(float)
    rows["threshold"] = rows.threshold.map(float)
    valid_threshold = np.isfinite(rows.threshold) | np.isposinf(rows.threshold)
    if not np.isfinite(rows.score).all() or not valid_threshold.all():
        raise ValueError(f"{path} needs finite scores and finite or positive-infinite thresholds")
    left, right = (rows.loc[rows.detector == name].set_index("run_id").sort_index()
                   for name in (reference, candidate))
    if not left[LABELS].equals(right[LABELS]):
        raise ValueError(f"{path} must pair both detectors on exactly the same run ids and labels")
    return left[LABELS + ["split_seed"]].assign(
        reference_score=left.score, candidate_score=right.score,
        reference_threshold=left.threshold, candidate_threshold=right.threshold,
    )


def _budget_flags(scores: np.ndarray, positive: np.ndarray, budget: int) -> np.ndarray:
    """Maximal score prefix allowing at most budget control alerts, including whole ties."""
    controls = scores[~positive]
    index = len(controls) - budget - 1
    cutoff = np.partition(controls, index)[index]
    return scores > cutoff


def _summary(rows: pd.DataFrame, task: str, minimum: float) -> dict:
    positive = rows.positive.to_numpy()
    small = rows.small_positive.to_numpy()
    hard = rows.hard_control.to_numpy()
    primary = small if task == "scope" else positive
    n = int(primary.sum())
    controls = int((~positive).sum())
    budget = math.floor(controls * MAX_FPR)
    result = dict(
        split_seed=rows.split_seed.iloc[0],
        positives=int(positive.sum()), controls=controls, hard_controls=int(hard.sum()),
        small_positives=int(small.sum()),
        primary="one_file_recall" if task == "scope" else "relay_recall",
        primary_positives=n, minimum_gain=minimum, false_alert_budget=budget,
    )
    flags = {}
    for role in ("reference", "candidate"):
        scores = rows[f"{role}_score"].to_numpy()
        threshold = rows[f"{role}_threshold"].iloc[0]
        alerted = scores > threshold
        flags[role] = alerted
        false_positives = int(alerted[~positive].sum())
        fpr = wilson(false_positives, controls)
        ranked = _budget_flags(scores, positive, budget) if controls else None
        counts = {
            "threshold": threshold, "true_positives": int(alerted[positive].sum()),
            "false_positives": false_positives, "false_positive_rate": fpr.value,
            "false_positive_rate_low": fpr.low, "false_positive_rate_high": fpr.high,
            "hard_false_positives": int(alerted[hard].sum()),
            "small_true_positives": int(alerted[small].sum()),
            "primary_recall": ratio(int(alerted[primary].sum()), n),
            "true_positives_at_budget": int(ranked[positive].sum()) if controls else math.nan,
            "primary_hits_at_budget": int(ranked[primary].sum()) if controls else math.nan,
        }
        result.update({f"{role}_{k}": v for k, v in counts.items()})
    gained = int((primary & flags["candidate"] & ~flags["reference"]).sum())
    lost = int((primary & flags["reference"] & ~flags["candidate"]).sum())
    delta = ratio(gained - lost, n)
    # Two 97.5% Wilson intervals give approximate simultaneous 95% bounds on the
    # two discordant probabilities. Subtract their endpoints for the net paired gain.
    gains, losses = wilson(gained, n, 0.975), wilson(lost, n, 0.975)
    low, high = gains.low - losses.high, gains.high - losses.low
    rank_delta = ratio(
        result["candidate_primary_hits_at_budget"] - result["reference_primary_hits_at_budget"], n)
    calibrated = math.isfinite(result["reference_threshold"]) and math.isfinite(
        result["candidate_threshold"])
    if not n or not budget or not hard.any() or not calibrated:
        evidence = "insufficient_data"
    elif result["candidate_false_positives"] > budget:
        evidence = "over_budget"
    elif high < minimum and rank_delta < minimum:
        evidence = "below_minimum"
    elif (delta >= minimum and low > 0 and rank_delta > 0
          and result["candidate_hard_false_positives"] <= result["reference_hard_false_positives"]):
        evidence = "promising"
    else:
        evidence = "inconclusive"
    return dict(result, primary_gained=gained, primary_lost=lost, primary_recall_delta=delta,
                delta_low=low, delta_high=high, primary_recall_delta_at_budget=rank_delta,
                evidence=evidence)


def benchmark_round(
    paths: Sequence[Path], task: str, reference: str, candidate: str,
    minimum_gain: float | None = None,
) -> pd.DataFrame:
    """Report each grid and the pooled comparison for one predeclared candidate."""
    if task not in MINIMUM_GAIN or not paths or candidate == reference:
        raise ValueError("choose a task, at least one held-out grid and two distinct detectors")
    minimum = MINIMUM_GAIN[task] if minimum_gain is None else minimum_gain
    if not 0 < minimum <= 1:
        raise ValueError("minimum gain must be a recall fraction in (0, 1]")
    grids = [_paired_grid(path, task, reference, candidate) for path in paths]
    pooled = pd.concat(grids)
    if not pooled.index.is_unique:
        raise ValueError("held-out grids overlap in run ids")
    if pooled[["split_seed", "reference_threshold", "candidate_threshold"]].nunique().ne(1).any():
        raise ValueError("use the same archive split seed and frozen thresholds across every run")
    populations = [("grid", str(path), frame) for path, frame in zip(paths, grids, strict=True)]
    populations.append(("pooled", "", pooled))
    return pd.DataFrame([
        dict(task=task, reference=reference, candidate=candidate,
             population=population, source=source, **_summary(frame, task, minimum))
        for population, source, frame in populations
    ])
