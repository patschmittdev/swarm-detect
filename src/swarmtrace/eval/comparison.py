"""Compare full-trace rules against the published fits, with optional independent test runs."""

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score

from swarmtrace.detect import (
    COMPONENT_COLUMN,
    COMPONENT_RULE,
    RULE,
    SCOPE_BREADTH_RULE,
    SCOPE_LOGISTIC,
    SCOPE_RULE,
    SHARING_LOGISTIC,
    RunDetector,
)
from swarmtrace.detect.components import component_score
from swarmtrace.features import feature_columns
from swarmtrace.features.spec import AGGREGATION, SCOPE
from swarmtrace.trace.context import ContextLevel
from swarmtrace.trace.tiers import Tier

from . import scope
from .diagnostics import by_run_partitions
from .harness import SEED_INDEX, EvalConfig, child_seed
from .metrics import auroc, bootstrap, wilson
from .recorded import RunTable, TableRecord, load_recorded, load_run_table

MAIN = "main"
SCOPED = "scope"
C2 = ContextLevel.C2
PAIRED_RESAMPLES = 2_000


def _main_table(root: Path) -> RunTable:
    data = load_recorded(root / "dataset" / MAIN, Tier.V1)
    scores = {
        run: component_score(pairs.droplevel("run_id"))
        for run, pairs in data.pairs.groupby(level="run_id", sort=False)
    }
    component = pd.Series(scores, dtype=float).reindex(data.runs.index, fill_value=0.0)
    features = data.runs.assign(**{COMPONENT_COLUMN: component})
    records = tuple(TableRecord(run, record.positive, record.condition)
                    for run, record in data.records.items())
    return RunTable(features, records)


@dataclass(frozen=True)
class _Cohort:
    features: pd.DataFrame
    truth: pd.DataFrame

    def select(self, ids: tuple[str, ...]) -> "_Cohort":
        return _Cohort(self.features.loc[list(ids)], self.truth.loc[list(ids)])


def _cohort(table: RunTable, task: str) -> _Cohort:
    records = table.records
    ids = [record.run_id for record in records]
    if not ids or not table.features.index.is_unique or list(table.features.index) != ids:
        raise ValueError(f"{task} needs unique run ids aligned with the feature rows")
    for record in records:
        if task == MAIN:
            keys = ("offensive_group_size",) if record.positive else ("benign_sharing_teams",)
        else:
            keys = ("offence_style",) if record.positive else ()
            if record.positive and record.condition.get("offence_style") == scope.SCOPE_VIOLATION:
                keys += ("violation_size",)
        missing_metadata = [key for key in keys if key not in record.condition]
        if missing_metadata:
            raise ValueError(f"{task} run {record.run_id} lacks evaluation metadata "
                             f"{missing_metadata}")
    aggregation = feature_columns("run", Tier.V1, (AGGREGATION,))
    if task == MAIN:
        required = [*aggregation, COMPONENT_COLUMN]
        positive = [r.positive for r in records]
        hard = [not r.positive and r.condition["benign_sharing_teams"] > 0 for r in records]
        small = [p and r.condition["offensive_group_size"] == 2 for p, r in zip(positive, records)]
    else:
        scoped = feature_columns("run", Tier.V1, (SCOPE,), context=C2)
        required = [*aggregation, *(f"{name}__C2" for name in scoped)]
        labels = scope.labels_for(records, scope.STRICT)
        positive = [labels[run] for run in ids]
        hard = [scope.run_kind(r) == scope.IN_SCOPE for r in records]
        small = [p and r.condition["violation_size"] == 1 for p, r in zip(positive, records)]
    missing = [column for column in required if column not in table.features]
    if missing:
        raise ValueError(f"{task} table lacks required feature columns {missing}")
    features = table.features[required] if task == MAIN else scope.context_matrix(
        table.features, C2.value)
    truth = pd.DataFrame({"positive": positive, "hard_control": hard, "small_positive": small},
                         index=features.index)
    return _Cohort(features, truth)


def _measure(
    truth: pd.DataFrame, scores: np.ndarray, threshold: float, logistic_flags: np.ndarray,
    bootstrap_seed: int,
) -> dict[str, int | float]:
    positive = truth["positive"].to_numpy(dtype=bool)
    hard = truth["hard_control"].to_numpy(dtype=bool)
    small = truth["small_positive"].to_numpy(dtype=bool)
    flags = scores > threshold
    tp, fp = int(flags[positive].sum()), int(flags[~positive].sum())
    positives, controls = int(positive.sum()), int((~positive).sum())
    recall, fpr = wilson(tp, positives), wilson(fp, controls)
    correct = flags == positive
    change = correct.astype(int) - (logistic_flags == positive).astype(int)
    paired = bootstrap(lambda rows: float(change[rows].mean()),
                       [np.flatnonzero(positive), np.flatnonzero(~positive)],
                       PAIRED_RESAMPLES, bootstrap_seed)
    return {
        "threshold": threshold, "positives": positives, "controls": controls,
        "true_positives": tp, "false_positives": fp, "accuracy": correct.mean(),
        "accuracy_delta_vs_logistic": paired.value,
        "delta_low": paired.low, "delta_high": paired.high,
        "precision": tp / (tp + fp) if tp + fp else np.nan,
        "recall": recall.value, "recall_low": recall.low, "recall_high": recall.high,
        "fpr": fpr.value, "fpr_low": fpr.low, "fpr_high": fpr.high,
        "auroc": auroc(positive, scores),
        "average_precision": average_precision_score(positive, scores) if positives else np.nan,
        "hard_controls": int(hard.sum()), "hard_false_positives": int(flags[hard].sum()),
        "hard_control_auroc": auroc(positive[positive | hard], scores[positive | hard]),
        "small_positives": int(small.sum()), "small_true_positives": int(flags[small].sum()),
    }


def _compare(
    task: str, archive: RunTable, seed: int, independent: RunTable | None,
    *, score_frames: list[pd.DataFrame] | None = None,
) -> list[dict[str, str | int | float]]:
    cohort = _cohort(archive, task)
    if task == MAIN:
        fitting, calibration, test = by_run_partitions(
            cohort.truth["positive"].to_dict(), EvalConfig.test_fraction, seed)
        fit_seed = child_seed(seed, 1, 0)
        seeds = {name: child_seed(fit_seed, SEED_INDEX[name], 0)
                 for name in (RULE, "logistic", "boosted")}
        seeds[COMPONENT_RULE] = seed  # Parameter-free.
        seeds[SHARING_LOGISTIC] = seeds["logistic"]
    else:
        split = scope.scope_split(archive.records, seed)
        fitting, calibration, test = split.fitting, split.calibration, split.test
        seeds = {name: child_seed(seed, scope.SEED_KEY, 2, scope.CONTEXTS.index(C2.value),
                                  scope.SCOPE_DETECTORS.index(name))
                 for name in (SCOPE_RULE, "logistic", "boosted")}
        seeds[SCOPE_BREADTH_RULE] = seed  # Parameter-free.
        seeds[SCOPE_LOGISTIC] = seeds["logistic"]

    fit, cal = cohort.select(fitting), cohort.select(calibration)
    tests = {"archive": cohort.select(test)}
    if independent is not None:
        fresh = _cohort(independent, task)
        if not cohort.features.index.intersection(fresh.features.index).empty:
            raise ValueError(f"independent {task} table overlaps the archive in run ids")
        tests["independent"] = fresh

    y_fit = fit.truth["positive"].to_numpy()
    y_cal = cal.truth["positive"].to_numpy()
    models = {}
    for name, model_seed in seeds.items():
        columns = ([COMPONENT_COLUMN] if name == COMPONENT_RULE else
                   [c for c in fit.features if c != COMPONENT_COLUMN])
        model = RunDetector(name, model_seed, scope.MAX_FPR)
        model.fit(fit.features[columns], y_fit).calibrate(cal.features[columns], y_cal)
        models[name] = model

    rows = []
    for population, sample in tests.items():
        scores = {name: model.score(sample.features[list(model.columns)])
                  for name, model in models.items()}
        logistic_flags = scores["logistic"] > models["logistic"].threshold
        for name, model in models.items():
            if score_frames is not None and population == "independent":
                score_frames.append(sample.truth.assign(
                    task=task, test_set=population, split_seed=seed, detector=name,
                    score=scores[name], threshold=model.threshold,
                ).rename_axis("run_id").reset_index())
            rows.append({
                "task": task, "test_set": population, "detector": name, "split_seed": seed,
                "fitting_runs": len(fitting), "calibration_controls": len(model.calibration_scores),
                **_measure(sample.truth, scores[name], model.threshold, logistic_flags,
                           child_seed(seed, 120)),
            })
    return rows


def compare_detectors(
    data: Path, seed: int, test_tables: Path | None = None, *, scores_out: Path | None = None,
) -> pd.DataFrame:
    """Score each method on the same test runs at a control-calibrated 5% target.

    The optional directory holds native main/runs.csv.gz and scope/runs.csv.gz test tables.
    These runs have no role in fitting or threshold selection. Optionally export their paired
    scores and frozen thresholds for comparisons across rounds.
    """
    if scores_out is not None and test_tables is None:
        raise ValueError("score export requires independent --test-tables")
    score_frames: list[pd.DataFrame] | None = [] if scores_out is not None else None
    rows = []
    for task in (MAIN, SCOPED):
        table = _main_table(data) if task == MAIN else load_run_table(data / task / "runs.csv.gz")
        independent = (load_run_table(test_tables / task / "runs.csv.gz")
                       if test_tables is not None else None)
        rows.extend(_compare(task, table, seed, independent, score_frames=score_frames))
    if scores_out is not None and score_frames is not None:
        scores_out.parent.mkdir(parents=True, exist_ok=True)
        pd.concat(score_frames, ignore_index=True).to_csv(scores_out, index=False, lineterminator="\n")
    return pd.DataFrame(rows)
