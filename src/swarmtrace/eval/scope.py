"""Scope experiment evaluation: the context axis and the strict and legacy labellings.

Context is defender-side. ``scope_table`` reads it from the ``context.json`` beside each trace
and projects it to each level before any feature sees it. Labels and the manifest condition
join here only, through each record's ``positive`` flag and ``condition``.

Under the legacy labelling a run is positive when it contains an offensive group. Under the
strict labelling a run is positive only when its manifest ``offence_style`` is
``scope_violation``; in-scope relays are controls in fitting, calibration and test. Both
labellings use one split of runs, stratified on kind by mistake rate, and are reported side
by side. Seeds: ``child_seed(seed, 97, 0)`` splits test from training, ``(97, 1)`` splits
calibration from fitting, ``(97, 2, context, detector)`` seeds fits (shared by the two
labellings, so only the labels differ), and ``(97, 3, labelling, context, detector, metric)``,
with a cell key after the metric for the per-size and per-rate cells, seeds bootstraps.
"""

import math
from collections.abc import Mapping, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np
import pandas as pd

from swarmtrace.detect import (
    FILES_RULE,
    FILES_RULE_COLUMN,
    RULE,
    SCOPE_RULE,
    SCOPE_RULE_COLUMNS,
    RunDetector,
)
from swarmtrace.features import feature_columns, run_features
from swarmtrace.features.spec import AGGREGATION, SCOPE
from swarmtrace.trace.context import ContextLevel, project_context, read_context
from swarmtrace.trace.io import RunPaths, read_trace
from swarmtrace.trace.tiers import Tier

from .harness import TOO_SMALL, child_seed, rule_unavailable
from .metrics import auroc, bootstrap, wilson
from .recorded import LABEL_SIDE_PREFIXES, RUN_ID
from .splits import CALIBRATION_FRACTION, split_by_stratum

LABELLINGS = ("strict", "legacy")
STRICT, LEGACY = LABELLINGS
REFERENCE = "none"
"""Context of the aggregation-only reference rows: no scope columns."""
CONTEXTS = (REFERENCE, *(level.value for level in ContextLevel))
SCOPE_DETECTORS = (RULE, SCOPE_RULE, "logistic", "boosted", FILES_RULE)
"""Append detectors only: positions 0 through 3 are pinned fit and bootstrap seed keys."""
SCOPE_RULE_COLUMN = {"C0": SCOPE_RULE_COLUMNS[1], "C1": SCOPE_RULE_COLUMNS[1],
                     "C2": SCOPE_RULE_COLUMNS[0]}
"""The feature column scored by ``scope_rule`` at each context."""
SEED_KEY = 97
TEST_FRACTION = 0.3
MAX_FPR = 0.05
CONFIDENCE = 0.95
SCOPE_VIOLATION = "scope_violation"
CONTROL, IN_SCOPE = "control", "in_scope"
VIOLATION_SIZES = (1, 2, 5)
SCOPE_KEYS = ("offence_style", "violation_size", "scope_mistake_rate", "benign_sharing_teams")
NOT_GATED = "reported, not gated"
"""Status of the unmatched in-scope against sharing-control AUROC. It is not structurally at
chance, so it is reported without a pass criterion; the gate is the byte-identical twin test."""
NOT_AVAILABLE_SCOPE = "not available: no scope_rule column at this context"
NOT_AVAILABLE_FILES = "not available: no distinct_files_read_max diagnostic"
NOT_FITTED = "not fitted: fitting runs have fewer than 2 runs of a class"
SPLIT_ROW, ALL_CONTEXTS = "split", "all"
AUROC_KEYS = {"auroc": 0, "sharing_control_auroc": 1, "in_scope_vs_sharing_auroc": 2,
              "violation_vs_in_scope_auroc": 3}
"""Last bootstrap spawn key of each AUROC. The violation against in-scope cells add a second
key: ``(3, size)`` for a violation size and ``(4, rate)`` for a mistake rate."""
HARDEST = "violation_vs_in_scope_auroc"
"""Strict only: scope-violation test runs against in-scope relay test runs, the same policy
minus the violation."""
SIZE_CELL, MISTAKE_CELL = 3, 4
NO_VIOLATIONS = "undefined: no scope-violation test runs in this cell"
NO_IN_SCOPE = "undefined: no in-scope relay test runs in this cell"
THRESHOLD = "full_trace_threshold"


class ScopeRecord(Protocol):
    """What scope evaluation reads of a run: a ``RunRecord`` or a run table's ``TableRecord``."""

    @property
    def run_id(self) -> str: ...
    @property
    def positive(self) -> bool: ...
    @property
    def condition(self) -> Mapping[str, int | str]: ...


@dataclass(frozen=True)
class ScopeRow:
    labelling: str
    context: str
    """``REFERENCE`` for aggregation features only, else the context level of the scope
    columns added to them; ``ALL_CONTEXTS`` on split rows."""
    detector: str
    metric: str
    value: float
    low: float
    high: float
    n: int
    """Numerator for a rate; runs in the population for an AUROC."""
    total: int
    requested: int
    valid: int
    note: str
    """Why a value or interval is withheld; empty when both are given."""
    interval: str
    status: str
    """``NOT_GATED`` on the unmatched in-scope against sharing-control AUROC, else empty."""
    seed: int
    split_counts: tuple[int, ...]
    """Fitting C/P, calibration C/P, test C/P under this row's labelling, in that order."""
    positive_runs: int = 0
    control_runs: int = 0


@dataclass(frozen=True)
class ScopeSplit:
    train: tuple[str, ...]
    test: tuple[str, ...]
    fitting: tuple[str, ...]
    calibration: tuple[str, ...]


@dataclass(frozen=True)
class CalibrationRow:
    labelling: str
    context: str
    detector: str
    control_kind: str
    rank: int
    calibration_controls: int
    threshold: float
    total: int
    above_zero: int | None
    at_or_above_threshold: int | None
    seed: int
    split_counts: tuple[int, ...]
    note: str = ""


def _calibration_rows(
    records: Sequence[ScopeRecord], labelling: str, context: str, detector: str,
    seed: int, counts: tuple[int, ...], scores: np.ndarray | None, threshold: float,
    note: str = "",
) -> list[CalibrationRow]:
    """Records and scores are the same ordered calibration controls used by the model."""
    kinds = np.array([IN_SCOPE if run_kind(record) == IN_SCOPE else
                      "sharing" if record.condition["benign_sharing_teams"] > 0 else "nonsharing"
                      for record in records], dtype=str)
    n = len(records)
    rank = math.ceil((n + 1) * (1 - MAX_FPR))
    result = []
    for kind in ("nonsharing", "sharing", *((IN_SCOPE,) if labelling == STRICT else ())):
        mask = kinds == kind
        result.append(CalibrationRow(
            labelling, context, detector, kind, rank, n, threshold, int(mask.sum()),
            None if scores is None else int((scores[mask] > 0).sum()),
            None if scores is None else int((scores[mask] >= threshold).sum()),
            seed, counts, note,
        ))
    return result


def _records(records: Sequence[ScopeRecord] | Mapping[str, ScopeRecord]) -> list[ScopeRecord]:
    found = list(records.values()) if isinstance(records, Mapping) else list(records)
    ids = [record.run_id for record in found]
    if not found or len(set(ids)) != len(ids):
        raise ValueError("scope evaluation needs at least one run and unique run ids")
    for record in found:
        missing = [key for key in SCOPE_KEYS if key not in record.condition]
        if missing:
            raise ValueError(f"run {record.run_id} lacks condition {missing}; "
                             "scope evaluation needs scope-on runs")
    return sorted(found, key=lambda record: record.run_id)


def run_kind(record: ScopeRecord) -> str:
    """``control``, ``in_scope`` or ``violation_<size>``, from the label and the manifest.

    The manifest states an offence style on control runs too, so the label decides first.
    """
    if not record.positive:
        return CONTROL
    if record.condition.get("offence_style") == SCOPE_VIOLATION:
        return f"violation_{record.condition['violation_size']}"
    return IN_SCOPE


def stratum(record: ScopeRecord) -> str:
    return f"{run_kind(record)}/mistake_{record.condition['scope_mistake_rate']}"


def labels_for(
    records: Sequence[ScopeRecord] | Mapping[str, ScopeRecord], labelling: str,
) -> dict[str, bool]:
    """Mark offensive runs positive: only scope violations under strict, all under legacy."""
    if labelling not in LABELLINGS:
        raise ValueError(f"unknown labelling {labelling!r}; expected one of {LABELLINGS}")
    found = list(records.values()) if isinstance(records, Mapping) else list(records)
    if labelling == LEGACY:
        return {record.run_id: bool(record.positive) for record in found}
    return {record.run_id: bool(record.positive)
            and record.condition.get("offence_style") == SCOPE_VIOLATION for record in found}


def scope_split(
    records: Sequence[ScopeRecord] | Mapping[str, ScopeRecord], seed: int,
) -> ScopeSplit:
    """One split shared by both labellings, stratified on run kind by mistake rate: test, then
    calibration from training, each holding ``round(0.3 n)`` runs of every stratum."""
    ordered = _records(records)
    strata = {record.run_id: stratum(record) for record in ordered}
    ids = list(strata)
    train, test = split_by_stratum(ids, [strata[run] for run in ids], TEST_FRACTION,
                                   child_seed(seed, SEED_KEY, 0))
    fitting, calibration = split_by_stratum(train, [strata[run] for run in train],
                                            CALIBRATION_FRACTION, child_seed(seed, SEED_KEY, 1))
    return ScopeSplit(train, test, fitting, calibration)


def _scope_row(job: tuple[str, Path]) -> pd.DataFrame:
    run_id, trace_path = job
    trace = read_trace(trace_path, Tier.V1)
    if trace.run_id != run_id:
        raise ValueError(f"{trace_path}: trace run_id {trace.run_id} != {run_id}")
    path = RunPaths(Path(trace_path).parent).context
    if not path.is_file():
        raise ValueError(f"{path}: no context.json beside the trace; scope_table needs "
                         "scope-on runs")
    # Read the full record once; a missing file at C0 would otherwise pass silently.
    full = read_context(path, ContextLevel.C2)
    frames = [run_features(trace)]
    for level in ContextLevel:
        frame = run_features(trace, context=project_context(full, level))
        columns = list(feature_columns("run", Tier.V1, (SCOPE,), context=level))
        frames.append(frame[columns].rename(columns={
            column: f"{column}__{level.value}" for column in columns}))
    return pd.concat(frames, axis=1)


class _Traced(ScopeRecord, Protocol):
    @property
    def trace_path(self) -> Path: ...


def scope_table(records: Sequence[_Traced], workers: int = 1) -> pd.DataFrame:
    """V1 run features of every run: the default columns once, then each scope column with
    suffix ``__C0``, ``__C1`` and ``__C2``, computed under that projection of the run's
    ``context.json``. Rows are in sorted run-id order whatever ``workers`` is."""
    if workers < 1:
        raise ValueError("workers must be positive")
    ordered = sorted(records, key=lambda record: record.run_id)
    if not ordered:
        raise ValueError("scope_table needs at least one run")
    jobs = [(record.run_id, Path(record.trace_path)) for record in ordered]
    if workers == 1 or len(jobs) < 2:
        frames = [_scope_row(job) for job in jobs]
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            frames = list(pool.map(_scope_row, jobs))
    return pd.concat(frames)


def context_matrix(table: pd.DataFrame, context: str) -> pd.DataFrame:
    """Aggregation columns, plus the scope columns of ``context`` under their plain names."""
    columns = list(feature_columns("run", Tier.V1, (AGGREGATION,)))
    matrix = table[columns]
    if context == REFERENCE:
        return matrix
    level = ContextLevel(context)
    scope = [column for column in feature_columns("run", Tier.V1, (SCOPE,), context=level)
             if f"{column}__{context}" in table]
    return pd.concat([matrix, table[[f"{column}__{context}" for column in scope]].rename(
        columns={f"{column}__{context}": column for column in scope})], axis=1)


def _metrics(labelling: str, mistakes: Sequence[int]) -> tuple[str, ...]:
    sizes = (0, *VIOLATION_SIZES) if labelling == LEGACY else VIOLATION_SIZES
    return (
        THRESHOLD, "auroc", "sharing_control_auroc", "detection_rate", "false_positive_rate",
        "fpr_nonsharing_controls", "fpr_sharing_controls",
        *(("fpr_in_scope_relays",) if labelling == STRICT else ()),
        *(f"detection_rate_violation_size_{size}" for size in sizes),
        *(f"detection_rate_mistake_rate_{rate}" for rate in mistakes),
        *(f"fpr_mistake_rate_{rate}" for rate in mistakes),
        "in_scope_vs_sharing_auroc",
        *((HARDEST, *(f"{HARDEST}_size_{size}" for size in VIOLATION_SIZES),
           *(f"{HARDEST}_mistake_rate_{rate}" for rate in mistakes))
          if labelling == STRICT else ()),
    )


def evaluate_scope(
    table: pd.DataFrame, records: Sequence[ScopeRecord] | Mapping[str, ScopeRecord],
    seed: int, n_bootstrap: int,
    *, diagnostics: pd.DataFrame | None = None,
    calibration_rows: list[CalibrationRow] | None = None,
) -> list[ScopeRow]:
    """Rows for each labelling by context by detector, on one shared split.

    ``table`` is a ``scope_table`` frame (or one loaded with ``load_run_table``). Each context's
    feature set is the aggregation family plus that level's scope columns; ``REFERENCE`` has
    the aggregation family alone. Detectors are fitted on the fitting runs and thresholded by
    split-conformal calibration at target FPR 0.05 on the calibration controls of the row's
    labelling; with fewer than 19 such controls the threshold is infinite and carries
    ``TOO_SMALL``. Sharing controls are benign control runs (no offensive group) with
    ``benign_sharing_teams > 0`` under both labellings; in-scope relays are their own
    control kind under strict. ``scope_rule`` rows carry ``NOT_AVAILABLE_SCOPE`` where its
    context-specific feature column is absent, as at ``REFERENCE``.

    ``files_rule`` selects only ``distinct_files_read_max`` from ``diagnostics`` at every
    context. Diagnostics never enter a context matrix or an existing detector. Optional
    ``calibration_rows`` receive counts from the fitted models' retained calibration scores;
    collecting them changes neither fitting nor thresholds nor any existing metric row.
    """
    ordered = _records(records)
    ids = [record.run_id for record in ordered]
    reserved = [column for column in table.columns
                if column == RUN_ID or str(column).startswith(LABEL_SIDE_PREFIXES)]
    if reserved:
        raise ValueError(f"table has label-side columns {reserved}; load it with load_run_table")
    if list(table.index) != ids:
        raise ValueError("table rows must be the records' run ids in sorted order")
    if diagnostics is not None and list(diagnostics.index) != ids:
        raise ValueError("diagnostics must be aligned with the records' run ids")
    files = (diagnostics[[FILES_RULE_COLUMN]]
             if diagnostics is not None and FILES_RULE_COLUMN in diagnostics else None)
    absent = set(feature_columns("run", Tier.V1, (AGGREGATION,))) - set(table.columns)
    if absent:
        raise ValueError(f"table lacks aggregation columns {sorted(absent)}")
    by_id = {record.run_id: record for record in ordered}
    split = scope_split(ordered, seed)
    fitting, calibration, test = list(split.fitting), list(split.calibration), list(split.test)
    mistakes = sorted({int(record.condition["scope_mistake_rate"]) for record in ordered})

    def condition(name: str) -> np.ndarray:
        return np.array([by_id[run].condition[name] for run in test])

    benign = np.array([not by_id[run].positive for run in test], dtype=bool)
    sharing_teams = condition("benign_sharing_teams").astype(int)
    sharing, nonsharing = benign & (sharing_teams > 0), benign & (sharing_teams == 0)
    kinds = np.array([run_kind(by_id[run]) for run in test])
    in_scope = kinds == IN_SCOPE
    violation = np.char.startswith(kinds.astype(str), "violation_")
    sizes, rates = condition("violation_size").astype(int), condition("scope_mistake_rate")
    rates = rates.astype(int)
    matrices = {context: context_matrix(table, context) for context in CONTEXTS}

    rows: list[ScopeRow] = []
    for labelling_index, labelling in enumerate(LABELLINGS):
        labels = labels_for(ordered, labelling)
        y_fit, y_cal, y_test = (np.array([labels[run] for run in runs], dtype=bool)
                                for runs in (fitting, calibration, test))
        counts = (int((~y_fit).sum()), int(y_fit.sum()), int((~y_cal).sum()), int(y_cal.sum()),
                  int((~y_test).sum()), int(y_test.sum()))
        metrics = _metrics(labelling, mistakes)
        calibration_controls = [by_id[run] for run in calibration if not labels[run]]

        def row(context: str, detector: str, metric: str, value: float, low: float = math.nan,
                high: float = math.nan, n: int = 0, total: int = 0, requested: int = 0,
                valid: int = 0, note: str = "", interval: str = "", positive_runs: int = 0,
                control_runs: int = 0) -> None:
            rows.append(ScopeRow(
                labelling, context, detector, metric, value, low, high, n, total, requested,
                valid, note, interval, NOT_GATED if metric == "in_scope_vs_sharing_auroc" else "",
                seed, counts, positive_runs, control_runs,
            ))

        for metric, count in (("fitting_runs", len(fitting)),
                              ("calibration_runs", len(calibration)),
                              ("calibration_controls", counts[2]), ("test_runs", len(test))):
            row(ALL_CONTEXTS, SPLIT_ROW, metric, float(count), n=count, total=count)

        for context_index, context in enumerate(CONTEXTS):
            for detector_index, detector in enumerate(SCOPE_DETECTORS):
                matrix = files if detector == FILES_RULE else matrices[context]
                reason = None
                if detector == RULE:
                    reason = rule_unavailable(matrix.columns, Tier.V1)
                elif detector == SCOPE_RULE and SCOPE_RULE_COLUMN.get(context) not in matrix:
                    reason = NOT_AVAILABLE_SCOPE
                elif detector == FILES_RULE and matrix is None:
                    reason = NOT_AVAILABLE_FILES
                if reason is None and min(y_fit.sum(), (~y_fit).sum()) < 2:
                    reason = NOT_FITTED
                if reason is not None:
                    if calibration_rows is not None:
                        calibration_rows.extend(_calibration_rows(
                            calibration_controls, labelling, context, detector, seed, counts,
                            None, math.nan, reason))
                    for metric in metrics:
                        auc = metric.endswith("auroc") or metric.startswith(HARDEST)
                        row(context, detector, metric, math.nan,
                            requested=n_bootstrap if auc else 0, note=reason,
                            interval="bootstrap" if auc else "" if metric == THRESHOLD
                            else "Wilson")
                    continue
                model = RunDetector(detector, child_seed(seed, SEED_KEY, 2, context_index,
                                                         detector_index), MAX_FPR)
                model.fit(matrix.loc[fitting], y_fit).calibrate(matrix.loc[calibration], y_cal)
                scores = model.score(matrix.loc[test])
                flags = scores > model.threshold
                row(context, detector, THRESHOLD, model.threshold,
                    note="" if math.isfinite(model.threshold) else TOO_SMALL)
                if calibration_rows is not None:
                    calibration_rows.extend(_calibration_rows(
                        calibration_controls, labelling, context, detector, seed, counts,
                        model.calibration_scores, model.threshold,
                        "" if math.isfinite(model.threshold) else TOO_SMALL))

                def separation(metric: str, positive: np.ndarray, negative: np.ndarray,
                               key: tuple[int, ...], empty: tuple[str, str] = ("", "")) -> None:
                    selected = positive | negative

                    def statistic(idx: np.ndarray) -> float:
                        return auroc(positive[idx], scores[idx])

                    estimate = bootstrap(
                        statistic, [np.flatnonzero(positive), np.flatnonzero(negative)],
                        n_bootstrap, child_seed(seed, SEED_KEY, 3, labelling_index,
                                                context_index, detector_index, *key), CONFIDENCE)
                    note = estimate.note
                    if empty[0] and not positive.any():
                        note = empty[0]
                    elif empty[1] and not negative.any():
                        note = empty[1]
                    row(context, detector, metric, estimate.value, estimate.low, estimate.high,
                        int(selected.sum()), int(selected.sum()), estimate.requested,
                        estimate.valid, note, "bootstrap",
                        int(positive.sum()), int(negative.sum()))

                def rate(metric: str, members: np.ndarray) -> None:
                    k, total = int(flags[members].sum()), int(members.sum())
                    estimate = wilson(k, total, CONFIDENCE)
                    row(context, detector, metric, estimate.value, estimate.low, estimate.high,
                        k, total, note=estimate.note, interval="Wilson")

                separation("auroc", y_test, ~y_test, (AUROC_KEYS["auroc"],))
                separation("sharing_control_auroc", y_test, sharing,
                           (AUROC_KEYS["sharing_control_auroc"],))
                rate("detection_rate", y_test)
                rate("false_positive_rate", ~y_test)
                rate("fpr_nonsharing_controls", nonsharing)
                rate("fpr_sharing_controls", sharing)
                if labelling == STRICT:
                    rate("fpr_in_scope_relays", in_scope)
                for size in ((0, *VIOLATION_SIZES) if labelling == LEGACY else VIOLATION_SIZES):
                    rate(f"detection_rate_violation_size_{size}", y_test & (sizes == size))
                for mistake in mistakes:
                    rate(f"detection_rate_mistake_rate_{mistake}", y_test & (rates == mistake))
                for mistake in mistakes:
                    rate(f"fpr_mistake_rate_{mistake}", ~y_test & (rates == mistake))
                separation("in_scope_vs_sharing_auroc", in_scope, sharing,
                           (AUROC_KEYS["in_scope_vs_sharing_auroc"],))
                if labelling == STRICT:
                    empty = (NO_VIOLATIONS, NO_IN_SCOPE)
                    separation(HARDEST, violation, in_scope, (AUROC_KEYS[HARDEST],), empty)
                    for size in VIOLATION_SIZES:
                        separation(f"{HARDEST}_size_{size}", violation & (sizes == size),
                                   in_scope, (AUROC_KEYS[HARDEST], SIZE_CELL, size), empty)
                    for mistake in mistakes:
                        separation(f"{HARDEST}_mistake_rate_{mistake}",
                                   violation & (rates == mistake), in_scope & (rates == mistake),
                                   (AUROC_KEYS[HARDEST], MISTAKE_CELL, mistake), empty)
    return rows
