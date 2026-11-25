"""Measure dependence on benign credential sharing with the existing experiment machinery."""

import hashlib
import math
import multiprocessing
import os
from collections import Counter
from collections.abc import Mapping
from concurrent.futures import ProcessPoolExecutor
from contextlib import ExitStack
from dataclasses import dataclass, replace
from difflib import unified_diff
from pathlib import Path
from shutil import copyfile
from tempfile import TemporaryDirectory

import numpy as np
import pandas as pd
from sklearn.utils.parallel import _get_threadpool_controller

from swarmtrace.detect import RULE
from swarmtrace.eval.data import TierData, build_tier_data, load_runs
from swarmtrace.eval.harness import (
    REPORTED_DETECTORS,
    SEED_INDEX,
    SEED_KEY,
    EvalConfig,
    MetricRow,
    SplitResult,
    child_seed,
    evaluate_split,
    family_data,
)
from swarmtrace.eval.metrics import auroc, bootstrap
from swarmtrace.eval.recorded import load_recorded, load_run_table, write_recorded
from swarmtrace.eval.report import _cell
from swarmtrace.eval.splits import CALIBRATION_FRACTION, Split, calibration_split, split_by_run
from swarmtrace.features import feature_columns
from swarmtrace.sim.runner import Condition
from swarmtrace.sim.sweep import condition_grid
from swarmtrace.trace.tiers import Tier

from .config import ReproduceConfig, RunJob, make_jobs
from .pipeline import _markdown, _rate, _simulate, _write_text
from .verify import SHARING_HASH_HEADER, SHARING_HASH_START, SHARING_PATHS

RATES = (0, 5, 10, 30)
NAMESPACE = 91
REVISION = 2
MIN_CALIBRATION_CONTROLS = 19
MAX_DATA_BYTES = 20_000_000
METHODS = (RULE, *(method for method in REPORTED_DETECTORS if method not in {"volume", RULE}))
INTERVAL_RULE = (
    "Containment uses unrounded overall AUROC bounds and is undefined with fewer than "
    "two sharing test controls or a withheld interval."
)
"""Fixed before generating the runs being measured; never adjusted to their results."""
REPLACEMENT_HISTORY = (
    "A first sweep of 792 runs (one positive replicate, 8 control repeats) was too small "
    "to distinguish 1 - q/2 from 1 - q at rates 5 and 10 and was replaced by this one "
    "before any conclusion was written."
)
MATCHED_HEADING = "## Matched on the number of sharing-like teams"
MATCHED_NOTE = (
    "The one-team and two-or-more rows above compare runs with different numbers of "
    "sharing-like teams; this table matches them."
)
POOLED_RULE = (
    "pooled over all runs of the rate (fitting, calibration and test); rule only, "
    "legitimate only because the rule has no fitted parameters"
)


@dataclass(frozen=True)
class SharingSweepConfig:
    """Control repeats count runs per condition, independent of positive replicates.

    Shorter grids, horizons and bootstrap counts are intended for tests. Only full-trace
    measurements are reported, so the default extraction has one final checkpoint.
    """

    seed: int = ReproduceConfig.seed
    workers: int = ReproduceConfig.workers
    conditions: tuple[Condition, ...] | None = None
    runs_per_condition: int = 3
    control_repeats: int = 90
    n_ticks: int = ReproduceConfig.n_ticks
    checkpoint_every: int = ReproduceConfig.n_ticks
    n_bootstrap: int = ReproduceConfig.n_bootstrap

    def __post_init__(self) -> None:
        # Keep integer/range validation consistent with reproduce, including bool rejection.
        if type(self.control_repeats) is not int or self.control_repeats < 1:
            raise ValueError("control_repeats must be a positive integer")
        _reproduce_config(self, self.seed, self.conditions)
        if self.conditions is not None:
            if any(not isinstance(condition, Condition) for condition in self.conditions):
                raise ValueError("conditions must contain only Condition instances")
            if len(set(self.conditions)) != len(self.conditions):
                raise ValueError("conditions must not contain duplicates")


@dataclass(frozen=True)
class SharingRatePlan:
    rate: int
    rate_index: int
    jobs: tuple[RunJob, ...]
    config: ReproduceConfig
    split_seed: int
    evaluation_seed: int
    calibration_controls: int


def _reproduce_config(
    config: SharingSweepConfig, seed: int, conditions: tuple[Condition, ...] | None,
) -> ReproduceConfig:
    resolved = ReproduceConfig(
        seed=seed, workers=config.workers, conditions=conditions,
        runs_per_condition=config.runs_per_condition, control_repeats=1,
        n_ticks=config.n_ticks, checkpoint_every=config.checkpoint_every,
        n_bootstrap=config.n_bootstrap, hold_out=(),
    )
    # make_jobs multiplies its repeat count by positive replicates. Round up here,
    # then trim only excess controls so arbitrary explicit counts remain exact.
    return replace(resolved, control_repeats=(config.control_repeats + config.runs_per_condition - 1)
                   // config.runs_per_condition)


def _split_counts(
    labels: Mapping[str, bool], split_seed: int, evaluation_seed: int,
) -> tuple[Split, tuple[int, ...]]:
    """Use the production stratified splits, including the harness's calibration subkey."""
    ids = sorted(labels)
    split = split_by_run(ids, [labels[run] for run in ids], EvalConfig.test_fraction, split_seed)
    fitting, calibration = calibration_split(
        split.train, [labels[run] for run in split.train], CALIBRATION_FRACTION,
        child_seed(evaluation_seed, SEED_KEY + 1, 0),
    )
    counts = tuple(sum(labels[run] == positive for run in group)
                   for group in (fitting, calibration, split.test) for positive in (False, True))
    return split, counts


def plan_sharing_sweep(config: SharingSweepConfig) -> tuple[SharingRatePlan, ...]:
    """Preflight every rate without I/O, using opaque job ids for stratified class counts.

    Real run ids differ from job-directory names; stratification fixes the counts regardless
    of those identities. Execution repeats this check on actual run ids before fitting.
    """
    grid = config.conditions if config.conditions is not None else condition_grid(
        n_ticks=config.n_ticks,
    )
    if not any(condition.offensive_group_size == 0 for condition in grid):
        raise ValueError("sharing sweep needs control conditions for calibration")
    if not any(condition.offensive_group_size > 0 for condition in grid):
        raise ValueError("sharing sweep needs positive conditions for fitting and testing")
    plans = []
    for rate_index, rate in enumerate(RATES):
        # Simulation children are spawned by make_jobs beneath this disjoint root. The
        # harness owns all fit/calibration/bootstrap descendants of evaluation_seed.
        simulation_seed = child_seed(config.seed, NAMESPACE, rate_index, REVISION, 0)
        split_seed = child_seed(config.seed, NAMESPACE, rate_index, REVISION, 1)
        evaluation_seed = child_seed(config.seed, NAMESPACE, rate_index, REVISION, 2)
        conditions = tuple(replace(condition, benign_credential_sharing=rate)
                           for condition in grid)
        resolved = _reproduce_config(config, simulation_seed, conditions)
        chosen = []
        controls: Counter[Condition] = Counter()
        for job in make_jobs(resolved):
            if job.dataset != "main":
                continue
            if job.condition.offensive_group_size == 0:
                controls[job.condition] += 1
                if controls[job.condition] > config.control_repeats:
                    continue
            chosen.append(job)
        jobs = tuple(chosen)
        _, counts = _split_counts(
            {job.directory: job.condition.offensive_group_size > 0 for job in jobs},
            split_seed, evaluation_seed,
        )
        if counts[2] < MIN_CALIBRATION_CONTROLS:
            raise ValueError(f"rate {rate}: needs >=19 calibration controls; got {counts[2]}; "
                             "increase control_repeats")
        if min(counts[0], counts[1]) < 2:
            raise ValueError(f"rate {rate}: needs at least two fitting runs per class; "
                             "increase runs_per_condition")
        if min(counts[4], counts[5]) < 2:
            raise ValueError(f"rate {rate}: needs at least two test runs per class for AUROC "
                             "intervals; increase runs_per_condition")
        plans.append(SharingRatePlan(rate, rate_index, jobs, resolved, split_seed,
                                     evaluation_seed, counts[2]))
    return tuple(plans)


def _restricted_auroc(
    metric: MetricRow, labels: np.ndarray, scores: np.ndarray, controls: np.ndarray,
    n_bootstrap: int, seed: int,
) -> MetricRow:
    """Reuse scores, all positive test runs and the existing run-bootstrap implementation."""
    controls = controls & ~labels
    selected = labels | controls
    estimate = bootstrap(
        lambda idx: auroc(labels[idx], scores[idx]),
        [np.flatnonzero(labels), np.flatnonzero(controls)], n_bootstrap, seed,
    )
    return replace(
        metric, metric="restricted_auroc", value=estimate.value,
        low=estimate.low, high=estimate.high, n=int(selected.sum()), total=int(selected.sum()),
        requested=estimate.requested, valid=estimate.valid, note=estimate.note,
        positive_runs=int(labels.sum()), control_runs=int(controls.sum()),
    )


def _sharing_undefined(rate: int, count: int) -> str | None:
    if count >= 2:
        return None
    if rate == 0:
        return "undefined: no sharing controls"
    return f"undefined: {count} sharing control{'s' if count != 1 else ''}"


def _contains(metric: MetricRow, target: float, missing: str | None) -> str:
    if missing is not None:
        return missing
    if not math.isfinite(metric.low) or not math.isfinite(metric.high):
        return "undefined: interval withheld"
    return "yes" if metric.low <= target <= metric.high else "no"


def _threshold(value: float) -> str:
    if math.isnan(value) or value == -math.inf:
        raise ValueError("invalid calibrated threshold")
    return "inf" if value == math.inf else f"{value:.6f}"


def _matched_rows(
    data: TierData, split: Split, result: SplitResult, config: SharingSweepConfig,
    plan: SharingRatePlan,
) -> list[dict[str, object]]:
    """Compare equal sharing-like team counts; only the parameter-free rule may be pooled."""
    if plan.rate == 0:
        return []
    matrix = family_data(data, "aggregation").runs
    rows = []
    for population, operation, ids, methods in (
        ("test split", 4, split.test, METHODS),
        (POOLED_RULE, 5, tuple(data.records), (RULE,)),
    ):
        labels = np.array([data.records[run].positive for run in ids], dtype=bool)
        teams = np.array([data.records[run].condition["benign_sharing_teams"] for run in ids])
        sharing_like = teams + labels.astype(int)
        for method in methods:
            scores = result.fitted[method].score(matrix.loc[list(ids)])
            metric = next(row for row in result.rows
                          if row.method == method and row.metric == "auroc")
            for k_index, name in enumerate((1, 2, "3-or-more")):
                selected = sharing_like >= 3 if k_index == 2 else sharing_like == k_index + 1
                positive = int((selected & labels).sum())
                control = int((selected & ~labels).sum())
                seed = child_seed(config.seed, NAMESPACE, plan.rate_index, REVISION,
                                  operation, SEED_INDEX[method], k_index)
                missing = []
                if positive < 2:
                    missing.append(f"{positive} relay run{'s' if positive != 1 else ''}")
                if control < 2:
                    missing.append(f"{control} sharing control{'s' if control != 1 else ''}")
                if missing:
                    cell = "undefined: " + "; ".join(missing)
                else:
                    matched = _restricted_auroc(metric, labels[selected], scores[selected],
                                                ~labels[selected], config.n_bootstrap, seed)
                    cell = _cell(replace(matched, metric="matched_auroc"))
                rows.append({
                    "rate": plan.rate, "detector": method, "sharing-like teams K": name,
                    "relay test runs (positives) k": positive, "sharing test controls k": control,
                    "AUROC (matched)": cell, "population": population,
                })
    return rows


def _result_rows(
    data: TierData, split: Split, result: SplitResult, config: SharingSweepConfig,
    plan: SharingRatePlan,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    controls = [run for run in split.test if not data.records[run].positive]
    sharing = [data.records[run].condition["benign_sharing_teams"] > 0 for run in controls]
    q = sum(sharing) / len(controls)
    expected = 1 - q / 2
    missing = _sharing_undefined(plan.rate, sum(sharing))
    positive_runs = sum(record.positive for record in data.records.values())
    labels = np.array([data.records[run].positive for run in split.test], dtype=bool)
    teams = np.array([data.records[run].condition["benign_sharing_teams"] for run in split.test])
    matrix = family_data(data, "aggregation").runs.loc[list(split.test)]
    rows, subgroups = [], []
    for method in METHODS:
        measured = {row.metric: row for row in result.rows if row.method == method}
        metric = measured["auroc"]
        scores = result.fitted[method].score(matrix)

        def restricted(mask: np.ndarray, key: int) -> MetricRow:
            return _restricted_auroc(metric, labels, scores, mask, config.n_bootstrap,
                                     child_seed(config.seed, NAMESPACE, plan.rate_index,
                                                REVISION, 3, SEED_INDEX[method], key))

        nonsharing = (~labels) & (teams == 0)
        complement = (_cell(restricted(nonsharing, 0)) if nonsharing.any()
                      else "undefined: no non-sharing controls")
        fit_c, fit_p, cal_c, cal_p, test_c, test_p = metric.split_counts
        rows.append({
            "detector": method, "rate": plan.rate,
            "runs": (f"{len(data.records)} ({positive_runs} positive, "
                     f"{len(data.records) - positive_runs} control)"),
            "fitting (positive, control)": f"{fit_p} positive, {fit_c} control",
            "calibration (positive, control)": f"{cal_p} positive, {cal_c} control",
            "test (positive, control)": f"{test_p} positive, {test_c} control",
            "sharing test controls (q)": _rate(sharing),
            "A_s": missing or _cell(measured["sharing_control_auroc"]),
            "AUROC vs non-sharing controls": complement, "overall AUROC": _cell(metric),
            "expected 1 - q/2": expected,
            "interval contains 1 - q/2": _contains(metric, expected, missing),
            "interval contains 1 - q": _contains(metric, 1 - q, missing),
            "detection rate": _cell(measured["detection_rate"]),
            "FPR": _cell(measured["false_positive_rate"]),
            "calibration controls": cal_c, "threshold": _threshold(result.thresholds[method]),
        })
        for key, name, mask in ((1, "one team", (~labels) & (teams == 1)),
                                (2, "two or more", (~labels) & (teams >= 2))):
            count = int(mask.sum())
            note = _sharing_undefined(plan.rate, count)
            subgroups.append({
                "rate": plan.rate, "detector": method, "sharing teams": name,
                "sharing controls k of n": f"{count} of {sum(sharing)}",
                "A_s": note or _cell(restricted(mask, key)),
            })
    # Carry the new section in the existing per-rate row bundle, keeping the two-list
    # interface used by render-only callers. The writer removes this non-column payload.
    subgroups[0]["_matched_rows"] = _matched_rows(data, split, result, config, plan)
    return rows, subgroups


def _evaluate_rate(
    data: TierData, plan: SharingRatePlan, config: SharingSweepConfig, *, run_only: bool = False,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    split, counts = _split_counts({run: record.positive for run, record in data.records.items()},
                                  plan.split_seed, plan.evaluation_seed)
    if counts[2] != plan.calibration_controls or counts[2] < MIN_CALIBRATION_CONTROLS:
        raise ValueError(f"rate {plan.rate}: actual calibration controls differ from preflight")
    evaluation = EvalConfig(tiers=(Tier.V1,), seed=config.seed, n_bootstrap=config.n_bootstrap,
                            families=("aggregation",), checkpoint_every=config.checkpoint_every)
    options = {"run_only": True} if run_only else {}
    result = evaluate_split(data, split, evaluation, plan.evaluation_seed,
                            family="aggregation", **options)
    if any(row.split_counts != counts for row in result.rows):
        raise ValueError(f"rate {plan.rate}: evaluation split counts differ from preflight")
    return _result_rows(data, split, result, config, plan)


def _run_rate(
    plan: SharingRatePlan, config: SharingSweepConfig, temporary: Path, publish: Path,
    pool: ProcessPoolExecutor | None,
) -> tuple[list[dict[str, object]], list[dict[str, object]], dict[str, str]]:
    raw = temporary / "raw" / f"rate-{plan.rate}"
    tasks = [(job, raw) for job in plan.jobs]
    if pool is None:
        for task in tasks:
            _simulate(task)
    else:
        list(pool.map(_simulate, tasks))
    records = load_runs(raw / "main")
    data = build_tier_data(records, Tier.V1, workers=config.workers,
                           checkpoint_every=config.checkpoint_every, retain_traces=False)
    archive = temporary / "recorded" / f"rate-{plan.rate}"
    # Reuse the portable writer's metadata joins and numerical serialization. Auxiliary
    # tables and its manifest exist only in this temporary archive, never in the output.
    write_recorded(archive, data)
    data = load_recorded(archive, Tier.V1)
    rows, subgroups = _evaluate_rate(data, plan, config)
    relative = SHARING_PATHS[plan.rate_index]
    destination = publish / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    copyfile(archive / "V1" / "runs.csv.gz", destination)
    digest = hashlib.sha256(destination.read_bytes()).hexdigest()
    print(f"rate={plan.rate}; positive={sum(record.positive for record in records)}; "
          f"control={sum(not record.positive for record in records)}; "
          f"calibration_controls={plan.calibration_controls}", flush=True)
    return rows, subgroups, {"path": relative, "sha256": digest}


def _write_report(
    report: Path, config: SharingSweepConfig, plans: tuple[SharingRatePlan, ...],
    rows: list[dict[str, object]], subgroups: list[dict[str, object]],
    hashes: list[dict[str, str]],
) -> None:
    inventory = [{"rate": plan.rate, "runs_per_condition": config.runs_per_condition,
                  "control_repeats": config.control_repeats,
                  "calibration_controls": plan.calibration_controls,
                  "simulation_seed": plan.config.seed, "split_seed": plan.split_seed,
                  "evaluation_seed": plan.evaluation_seed} for plan in plans]
    text = (
        "# Benign credential-sharing sweep\n\n"
        f"Seed: {config.seed}. Rates are percentages of benign teams.\n\n"
        f"{REPLACEMENT_HISTORY}\n\n"
        f"Predeclared rule: {INTERVAL_RULE}\n\n"
        "V1, aggregation features, by-run split. Each rate has independently seeded runs "
        "and its own fitted models and calibrated thresholds. Training, calibration and "
        "test runs are disjoint. The test fraction and calibration fraction of training "
        "runs are both 0.3, stratified by class. Thresholds target FPR 0.05 and flag "
        "strictly greater scores. q counts test controls with at least one sharing team.\n\n"
        "The calibrated threshold is the conformal quantile of the calibration-control "
        "scores, with the number of calibration controls in each row; once more than "
        "about 5 percent of controls contain a sharing team the threshold falls inside "
        "the sharing-score range.\n\n"
        f"{config.n_ticks} ticks; {config.n_bootstrap} bootstrap resamples. AUROC intervals "
        "use the existing stratified bootstrap over runs; rates use 95% Wilson intervals "
        "and print k of n. Withheld intervals retain their reason. A_s compares all "
        "positive test runs with sharing test controls only. The non-sharing AUROC and "
        "the one-team and two-or-more-team A_s rows use the same positive test runs and "
        "their named control subset, without refitting. Subgroup counts are out of all "
        "sharing test controls.\n\n"
        "Identity: overall AUROC = 1 - q(1 - A_s) when non-sharing controls are "
        "perfectly separated.\n\n"
        "Simulation, split and evaluation roots use child_seed(seed, 91, rate_index, 2, "
        "0/1/2), respectively. make_jobs spawns simulation children; the unchanged "
        "harness derives calibration, fit and bootstrap seeds from the evaluation root "
        "with distinct subkeys. Restricted-control bootstrap seeds use "
        "child_seed(seed, 91, rate_index, 2, 3, detector_index, subset_index), with subset "
        "indices 0 (non-sharing), 1 (one team) and 2 (two or more teams). All child_seed "
        "keys contain at least two elements.\n\n"
        + _markdown(inventory)
    )
    for method in METHODS:
        table = [{key: value for key, value in row.items() if key != "detector"}
                 for row in rows if row["detector"] == method]
        text += f"\n## {method}\n\n" + _markdown(table)
    visible_subgroups = [{key: value for key, value in row.items() if key != "_matched_rows"}
                         for row in subgroups]
    matched = [item for row in subgroups for item in row.get("_matched_rows", [])]
    text += "\n## A_s by sharing-team count\n\n" + _markdown(visible_subgroups)
    text += "\n" + MATCHED_HEADING + "\n\n" + _markdown(matched)
    text += "\n" + MATCHED_NOTE + "\n"
    text += (
        "Bootstrap keys: child_seed(config.seed, NAMESPACE, rate_index, REVISION, 4, "
        "detector_index, k_index) for test rows and child_seed(config.seed, NAMESPACE, "
        "rate_index, REVISION, 5, detector_index, k_index) for pooled rule rows; "
        "NAMESPACE = 91, REVISION = 2, detector_index = SEED_INDEX[method], "
        "k_index = 0/1/2 for K = 1/2/3-or-more; "
        "K counts the relay group as one sharing-like team.\n"
    )
    text += "\n## Recorded V1 run tables\n\n" + SHARING_HASH_START + "\n"
    text += SHARING_HASH_HEADER + "\n"
    text += "".join(f"{row['path']} | {row['sha256']}\n" for row in hashes)
    _write_text(report, text + "```\n")


def _table_data(path: Path, checkpoint_every: int) -> TierData:
    """Restore run features with the same Python float parser as load_recorded.

    TableRecord supplies positive and condition facts without inventing agent labels or
    objective outcomes. Empty auxiliary matrices are only structural inputs to family_data;
    evaluate_split(run_only=True) never fits or scores them.
    """
    table = load_run_table(path)
    runs = table.features.sort_index()
    if not runs.index.is_unique:
        raise ValueError(f"duplicate run ids in {path}")
    columns = feature_columns("run", Tier.V1)
    if set(columns) - set(runs.columns):
        raise ValueError(f"missing V1 run features in {path}")
    records = {record.run_id: record
               for record in sorted(table.records, key=lambda row: row.run_id)}
    pair_index = pd.MultiIndex.from_arrays([[], [], []], names=["run_id", "agent_a", "agent_b"])
    prefix_index = pd.MultiIndex.from_arrays([[], []], names=["run_id", "tick"])
    return TierData(
        tier=Tier.V1, records=records, traces={}, runs=runs,
        volume=pd.DataFrame(index=runs.index),
        pairs=pd.DataFrame(index=pair_index, columns=feature_columns("pair", Tier.V1), dtype=float),
        pair_labels=np.empty(0, dtype=bool),
        prefix_runs=pd.DataFrame(index=prefix_index, columns=runs.columns, dtype=float),
        prefix_volume=pd.DataFrame(index=prefix_index), checkpoint_every=checkpoint_every,
    )


def _without_matched_section(content: bytes) -> bytes:
    heading = MATCHED_HEADING.encode("utf-8")
    if heading not in content:
        return content
    if content.count(heading) != 1 or b"## Recorded V1 run tables" not in content:
        raise ValueError("malformed matched section in sharing-sweep.md")
    start = content.index(heading)
    end = content.index(b"## Recorded V1 run tables", start)
    return content[:start] + content[end:]


def render_sharing_sweep_from_tables(data_dir: str | Path, config: SharingSweepConfig) -> Path:
    """Rebuild the report from the four run tables, without simulation or auxiliary data.

    If a report exists, refuse to replace it when any pre-existing line would change,
    and include the exact line differences in the error. Table bytes are never written.
    """
    data_dir = Path(data_dir)
    report = data_dir / "sharing-sweep.md"
    plans = plan_sharing_sweep(config)
    names = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")
    previous = {name: os.environ.get(name) for name in names}
    rows, subgroups, hashes = [], [], []
    try:
        os.environ.update(dict.fromkeys(names, "1"))
        with _get_threadpool_controller().limit(limits=1):
            for plan in plans:
                relative = SHARING_PATHS[plan.rate_index]
                path = data_dir / relative
                data = _table_data(path, config.checkpoint_every)
                if (len(data.records) != len(plan.jobs) or any(
                    record.condition["benign_credential_sharing"] != plan.rate
                    for record in data.records.values()
                )):
                    raise ValueError(f"rate {plan.rate}: recorded table differs from sweep plan")
                measured, grouped = _evaluate_rate(data, plan, config, run_only=True)
                rows.extend(measured)
                subgroups.extend(grouped)
                hashes.append({"path": relative,
                               "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
            with TemporaryDirectory(prefix="swarmtrace-sharing-render-", dir=data_dir) as temporary:
                candidate = Path(temporary) / report.name
                _write_report(candidate, config, plans, rows, subgroups, hashes)
                if report.exists():
                    before = _without_matched_section(report.read_bytes())
                    after = _without_matched_section(candidate.read_bytes())
                    if before != after:
                        difference = "".join(unified_diff(
                            before.decode("utf-8").splitlines(keepends=True),
                            after.decode("utf-8").splitlines(keepends=True),
                            fromfile="existing sharing-sweep.md",
                            tofile="rendered sharing-sweep.md",
                        ))
                        raise ValueError("render would change pre-existing sharing-sweep.md lines; "
                                         "report left unchanged:\n" + difference)
                candidate.replace(report)
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
    return report


def run_sharing_sweep(out: str | Path, config: SharingSweepConfig) -> Path:
    """Publish four V1 run tables and their report, leaving existing main artifacts untouched."""
    plans = plan_sharing_sweep(config)
    out = Path(out)
    report = out / "sharing-sweep.md"
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        raise ValueError(f"output already contains artifacts: {out}; choose a fresh directory")
    out.mkdir(parents=True, exist_ok=True)
    print(f"seed={config.seed}; sharing rates={RATES}; workers={config.workers}", flush=True)
    print(INTERVAL_RULE, flush=True)
    names = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")
    previous = {name: os.environ.get(name) for name in names}
    rows, subgroups, hashes = [], [], []
    try:
        os.environ.update(dict.fromkeys(names, "1"))
        with ExitStack() as stack:
            # sklearn is already imported in API callers. Its installed controller also
            # limits those loaded libraries, which environment variables alone cannot do.
            stack.enter_context(_get_threadpool_controller().limit(limits=1))
            temporary = Path(stack.enter_context(TemporaryDirectory(
                prefix="swarmtrace-sharing-", dir=out,
            ))).resolve()
            publish = temporary / "publish"
            pool = (stack.enter_context(ProcessPoolExecutor(
                max_workers=config.workers, mp_context=multiprocessing.get_context("spawn"),
            )) if config.workers > 1 else None)
            for plan in plans:
                measured, grouped, hashed = _run_rate(plan, config, temporary, publish, pool)
                rows.extend(measured)
                subgroups.extend(grouped)
                hashes.append(hashed)
            _write_report(publish / report.name, config, plans, rows, subgroups, hashes)
            existing_bytes = sum(path.stat().st_size for path in out.rglob("*")
                                 if path.is_file() and not path.resolve().is_relative_to(temporary))
            added_bytes = sum(path.stat().st_size for path in publish.rglob("*") if path.is_file())
            if existing_bytes + added_bytes >= MAX_DATA_BYTES:
                raise ValueError("sharing sweep would exceed the <20 MB total data budget: "
                                 f"{existing_bytes + added_bytes} bytes")
            (publish / "sharing-sweep").replace(out / "sharing-sweep")
            (publish / report.name).replace(report)
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
    return report
