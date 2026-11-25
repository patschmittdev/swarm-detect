import hashlib
import json
import multiprocessing
import os
from collections.abc import Mapping, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

from swarmtrace.detect import RULE
from swarmtrace.eval.data import RunRecord, TierData, build_tier_data, load_runs
from swarmtrace.eval.harness import (
    FEATURE_SETS,
    REPORTED_DETECTORS,
    SEED_KEY,
    EvalConfig,
    MetricRow,
    SplitResult,
    child_seed,
    evaluate_split,
    family_data,
    rule_unavailable,
)
from swarmtrace.eval.headline import format_readme_headline, write_headline
from swarmtrace.eval.metrics import wilson
from swarmtrace.eval.recorded import load_recorded, write_gzip, write_json, write_recorded
from swarmtrace.eval.report import write_report
from swarmtrace.eval.splits import (
    CALIBRATION_FRACTION,
    Split,
    calibration_split,
    held_out_splits,
    split_by_run,
)
from swarmtrace.sim.runner import run_one
from swarmtrace.trace.tiers import Tier

from .config import ReproduceConfig, RunJob, make_jobs
from .controls import (
    LOUD_GATING_BARS,
    NOT_GATED,
    LoudFlags,
    above_calibration_controls,
    loud_bar_rows,
    negative_control,
    require_loud_detection,
)
from .verify import provenance_digests

MAX_BYTES = 15_000_000
SEPARATE_ARTIFACTS = frozenset({"README.md", "split-stability.md"})


def _splits(
    labels: Mapping[str, bool], conditions: Mapping[str, Mapping[str, int | str]],
    config: ReproduceConfig,
) -> list[Split]:
    ids = sorted(labels)
    splits = [split_by_run(ids, [labels[run] for run in ids], 0.3, child_seed(config.seed, 0))]
    for factor in config.hold_out:
        splits.extend(held_out_splits(conditions, factor))
    return splits


def _inventory(
    labels: Mapping[str, bool], splits: Sequence[Split], seed: int,
) -> list[dict[str, str | int]]:
    rows = []
    for index, split in enumerate(splits):
        split_seed = child_seed(seed, 1, index)
        fitting, calibration = calibration_split(
            split.train, [labels[run] for run in split.train], CALIBRATION_FRACTION,
            child_seed(split_seed, SEED_KEY + 1, 0),
        )
        counts: dict[str, str | int] = {"split": split.name}
        for label, runs in (("fitting", fitting), ("calibration", calibration),
                            ("test", split.test)):
            counts[f"{label}_controls"] = sum(not labels[run] for run in runs)
            counts[f"{label}_positive"] = sum(labels[run] for run in runs)
        rows.append(counts)
    return rows


def split_inventory(jobs: Sequence[RunJob], config: ReproduceConfig) -> list[dict[str, str | int]]:
    """Preflight class counts, without simulating. Run identities cannot change these counts."""
    labels = {job.directory: job.condition.offensive_group_size > 0
              for job in jobs if job.dataset == "main"}
    conditions = {job.directory: asdict(job.condition) for job in jobs if job.dataset == "main"}
    return _inventory(labels, _splits(labels, conditions, config), config.seed)


def _simulate(job: tuple[RunJob, Path]) -> Path:
    run, root = job
    return run_one(run.condition, run.seed, root / run.dataset / run.directory)


def _markdown(rows: Sequence[Mapping[str, object]]) -> str:
    if not rows:
        return "No rows.\n"
    columns = tuple(rows[0])
    lines = ["| " + " | ".join(columns) + " |", "| " + " | ".join("---" for _ in columns) + " |"]
    for row in rows:
        values = [
            (format(row[key], ".17g" if key in {
                "calibration_max", "nonsharing_calibration_max", "sharing_calibration_max",
                "threshold", "loud_min",
            } else ".4f")
             if isinstance(row[key], float) else str(row[key]))
            for key in columns
        ]
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines) + "\n"


def _write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="\n")


def _sample(records: Sequence[RunRecord], count: int) -> list[RunRecord]:
    buckets: dict[tuple[bool, str], list[RunRecord]] = {}
    for record in records:
        key = (record.positive, str(record.condition["channel"]))
        buckets.setdefault(key, []).append(record)
    chosen = []
    while buckets and len(chosen) < count:
        for key in sorted(tuple(buckets)):
            chosen.append(buckets[key].pop(0))
            if not buckets[key]:
                del buckets[key]
            if len(chosen) == count:
                break
    return chosen


def _rate(flags: Sequence[bool]) -> str:
    estimate = wilson(sum(flags), len(flags))
    return (f"{sum(flags)} of {len(flags)}; {estimate.value:.3f} "
            f"[{estimate.low:.3f}, {estimate.high:.3f}] Wilson")


def _maximum(values: np.ndarray) -> float:
    return float(np.max(values)) if values.size else float("nan")


def _control_rows(
    result: SplitResult, benign: TierData, loud: TierData, family: str, config: ReproduceConfig,
    *, main: TierData,
) -> tuple[list[dict[str, object]], LoudFlags]:
    benign, loud = family_data(benign, family), family_data(loud, family)
    rows = []
    flags: LoudFlags = {}
    # RunDetector retains calibration scores in split order, with positive runs removed.
    calibration_controls = [main.records[run] for run in result.calibration
                            if not main.records[run].positive]
    sharing_counts = [record.condition.get("benign_sharing_teams")
                      for record in calibration_controls]
    if any(type(value) is not int or value < 0 for value in sharing_counts):
        raise ValueError("benign_sharing_teams is missing or invalid for calibration controls; "
                         "regenerate the recorded main dataset")
    nonsharing = np.asarray([value == 0 for value in sharing_counts], dtype=bool)
    names = ("fitting_controls", "fitting_positive", "calibration_controls",
             "calibration_positive", "test_controls", "test_positive")
    counts = dict(zip(names, result.rows[0].split_counts, strict=True))
    for method in REPORTED_DETECTORS:
        note = rule_unavailable(benign.runs.columns, benign.tier) if method == RULE else None
        if note is not None:
            # Same keys as the detector rows; measured cells say why there is no measurement.
            rows.extend({key: value if key in _CONTROL_ROW_IDENTITY else note
                         for key, value in template.items()} | {"detector": RULE}
                        for template in rows[-2:])
            continue
        detector = result.fitted[method]
        online = result.fitted[f"{method}-online"]
        matrix = benign.volume if method == "volume" else benign.runs
        loud_matrix = loud.volume if method == "volume" else loud.runs
        full_flags = detector.flag(matrix)
        loud_scores = detector.score(loud_matrix)
        calibration_scores = detector.calibration_scores
        if calibration_scores.shape != (len(calibration_controls),):
            raise ValueError("calibration-control scores are not aligned with main run metadata")
        bars = {
            "calibrated_threshold": (np.isfinite(loud_scores)
                                     & (loud_scores > detector.threshold)).tolist(),
            "nonsharing_controls": above_calibration_controls(
                loud_scores, calibration_scores[nonsharing]),
            "all_controls": above_calibration_controls(loud_scores, calibration_scores),
        }
        if method == RULE:
            # Diagnostic only: kept out of the gate's flags and given no required bars.
            required_met: int | str = NOT_GATED
            required_rate = NOT_GATED
        else:
            flags[method] = bars
            required = np.logical_and.reduce([
                bars[bar] for bar in LOUD_GATING_BARS.get(method, LOUD_GATING_BARS["boosted"])
            ]).tolist()
            required_met, required_rate = sum(required), _rate(required)
        prefix = benign.prefix_volume if method == "volume" else benign.prefix_runs
        online_flags = np.array([tick is not None
                                 for tick in online.first_crossings(prefix).values()])
        for label, values in (("full-trace", full_flags), ("online", online_flags)):
            estimate = wilson(int(values.sum()), len(values))
            rate = (f"{int(values.sum())} of {len(values)}; {estimate.value:.3f} "
                    f"[{estimate.low:.3f}, {estimate.high:.3f}] Wilson")
            rows.append({"seed": config.seed, "split": "by run (main model)",
                         "tier": benign.tier.value, "family": family,
                         "detector": ("volume (family-independent)" if method == "volume"
                                      else method),
                         "mode": label, "benign_flagged": int(values.sum()),
                         "benign_runs": len(values),
                         "FPR": estimate.value, "low": estimate.low, "high": estimate.high,
                         "benign_rate": rate, "loud_rate": _rate(bars["all_controls"]),
                         "loud_at_calibrated_threshold": _rate(bars["calibrated_threshold"]),
                         "loud_at_calibrated_threshold_count": sum(bars["calibrated_threshold"]),
                         "loud_above_all_calibration_controls": sum(bars["all_controls"]),
                         "loud_above_nonsharing_controls": sum(bars["nonsharing_controls"]),
                         "loud_nonsharing_rate": _rate(bars["nonsharing_controls"]),
                         "loud_required_met": required_met, "loud_required_rate": required_rate,
                         "loud_runs": len(loud_scores), "threshold": detector.threshold,
                         "nonsharing_calibration_controls": int(nonsharing.sum()),
                         "nonsharing_calibration_max": _maximum(calibration_scores[nonsharing]),
                         "sharing_calibration_max": _maximum(calibration_scores[~nonsharing]),
                         "calibration_max": _maximum(calibration_scores),
                         "loud_min": (float(np.min(loud_scores)) if loud_scores.size
                                      else float("nan")), **counts})
    return rows, flags


_CONTROL_ROW_IDENTITY = frozenset({
    "seed", "split", "tier", "family", "mode", "benign_runs", "loud_runs",
    "nonsharing_calibration_controls", "fitting_controls", "fitting_positive",
    "calibration_controls", "calibration_positive", "test_controls", "test_positive",
})


def _evaluate_job(
    task: tuple[Path, Tier, str, int, Split, ReproduceConfig],
) -> tuple[list[MetricRow], list[dict[str, object]], LoudFlags]:
    out, tier, family, index, split, config = task
    data = load_recorded(out / "dataset" / "main", tier)
    evaluation = EvalConfig(seed=config.seed, n_bootstrap=config.n_bootstrap)
    result = evaluate_split(data, split, evaluation, child_seed(config.seed, 1, index),
                            family=family)
    if index:
        return list(result.rows), [], {}
    benign = load_recorded(out / "dataset" / "benign", tier)
    loud = load_recorded(out / "dataset" / "loud", tier)
    rows, flags = _control_rows(result, benign, loud, family, config, main=data)
    return list(result.rows), rows, flags


def _negative_job(
    task: tuple[Path, Tier, str, ReproduceConfig],
) -> list[dict[str, str | int | float]]:
    out, tier, family, config = task
    data = load_recorded(out / "dataset" / "main", tier)
    return negative_control(data, family, config.seed, config.shuffle_repeats)


def _fit_tier(
    out: Path, tier: Tier, splits: Sequence[Split], config: ReproduceConfig,
) -> tuple[
    list[MetricRow], list[dict[str, object]], list[dict[str, object]], LoudFlags,
]:
    # Fresh model processes inherit fixed native thread limits before NumPy or sklearn loads.
    # This also prevents BLAS/OpenMP oversubscription with multiple process workers.
    names = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")
    previous = {name: os.environ.get(name) for name in names}
    tasks = [(out, tier, family, index, split, config)
             for family in FEATURE_SETS for index, split in enumerate(splits)]
    metrics, controls, negative, loud_flags = [], [], [], {}
    try:
        os.environ.update(dict.fromkeys(names, "1"))
        with ProcessPoolExecutor(max_workers=config.workers,
                                 mp_context=multiprocessing.get_context("spawn")) as pool:
            results = pool.map(_evaluate_job, tasks)
            for task, (rows, control, flags) in zip(tasks, results, strict=True):
                metrics.extend(rows)
                controls.extend(control)
                _, _, family, index, split, _ = task
                print(f"Evaluated {tier.value}, {family}, {split.name}", flush=True)
                if tier == Tier.V1 and family == "aggregation" and index == 0:
                    loud_flags = flags
            negative_tasks = [(out, tier, family, config) for family in FEATURE_SETS]
            for rows in pool.map(_negative_job, negative_tasks):
                negative.extend(rows)
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
    return metrics, controls, negative, loud_flags


def render_readme(readme: Path, headline: Path) -> None:
    """Embed a short block; the full headline and reports remain linked artifacts."""
    start, end = "<!-- BEGIN GENERATED RESULTS -->", "<!-- END GENERATED RESULTS -->"
    text = readme.read_text(encoding="utf-8")
    if text.count(start) != 1 or text.count(end) != 1 or text.index(start) > text.index(end):
        raise ValueError("the target Markdown file must contain one ordered pair of "
                         "generated-results markers")
    before, rest = text.split(start)
    _, after = rest.split(end)
    tables = format_readme_headline(headline.read_text(encoding="utf-8"))
    _write_text(readme, before + start + "\n\n" + tables + "\n" + end + after)


def _write_experiment(out: Path, manifest: Mapping[str, object]) -> None:
    artifacts = {
        path.relative_to(out).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(out.rglob("*"))
        if path.is_file() and path.name not in SEPARATE_ARTIFACTS
    }
    write_json(out / "experiment.json", {**manifest, "artifacts_sha256": artifacts,
                                         **provenance_digests()})


def reproduce(
    out: str | Path, config: ReproduceConfig, *, readme: Path | None = None,
) -> list[Path]:
    """Simulate, archive, fit, measure controls, and fail closed on an undetected loud run."""
    out = Path(out)
    jobs = make_jobs(config)
    planned_counts = split_inventory(jobs, config)
    if any(row["calibration_controls"] < 19 for row in planned_counts):
        raise ValueError("every reported split needs >=19 calibration controls; "
                         "increase --control-repeats or --runs-per-condition")
    if any(min(row["fitting_controls"], row["fitting_positive"]) < 2 for row in planned_counts):
        raise ValueError("every split needs at least two fitting runs per class")
    if out.exists() and any(path.name not in SEPARATE_ARTIFACTS for path in out.iterdir()):
        raise ValueError(f"output directory already contains artifacts: {out}; "
                         "choose a fresh directory")
    out.mkdir(parents=True, exist_ok=True)
    command = (
        f"swarmtrace reproduce --seed {config.seed} --out DIR "
        f"--runs-per-condition {config.runs_per_condition} "
        f"--control-repeats {config.control_repeats} "
        f"--ticks {config.n_ticks} --checkpoint-every {config.checkpoint_every} "
        f"--bootstrap {config.n_bootstrap} --shuffle-repeats {config.shuffle_repeats} "
        f"--sample-runs {config.sample_runs} --hold-out {' '.join(config.hold_out)}"
    ).rstrip()
    executed = command.replace("--out DIR", f'--out "{out}"') + f" --workers {config.workers}"
    if readme is not None:
        executed += f' --readme "{readme}"'
    print(f"seed={config.seed}; command={executed}", flush=True)
    metrics: list[MetricRow] = []
    controls: list[dict[str, object]] = []
    negative: list[dict[str, object]] = []
    loud_flags = {}
    run_metadata = []
    class_counts = []
    with TemporaryDirectory(prefix="swarmtrace-", dir=out) as temporary:
        raw = Path(temporary)
        tasks = [(job, raw) for job in jobs]
        if config.workers == 1:
            for task in tasks:
                _simulate(task)
        else:
            with ProcessPoolExecutor(max_workers=config.workers) as pool:
                list(pool.map(_simulate, tasks))
        records = {name: load_runs(raw / name) for name in ("main", "benign", "loud")}
        for name, group in records.items():
            class_counts.append({"dataset": name, "positive": sum(r.positive for r in group),
                                 "controls": sum(not r.positive for r in group)})
            print(f"{name}: {sum(r.positive for r in group)} positive, "
                  f"{sum(not r.positive for r in group)} control runs", flush=True)
            count = (config.sample_runs if name == "main"
                     else len(group) if name == "loud" else 1)
            for record in _sample(group, count):
                for filename in ("trace.jsonl", "labels.json", "manifest.json"):
                    write_gzip(out / "raw" / name / record.run_id / f"{filename}.gz",
                               (record.trace_path.parent / filename).read_bytes())
        for job in jobs:
            source = json.loads((raw / job.dataset / job.directory / "manifest.json").read_text())
            run_metadata.append({"dataset": job.dataset, "seed": job.seed,
                                 "requested_condition": asdict(job.condition), **source})
        labels = {r.run_id: r.positive for r in records["main"]}
        splits = _splits(labels, {r.run_id: r.condition for r in records["main"]}, config)
        counts = _inventory(labels, splits, config.seed)
        if any(row["calibration_controls"] < 19 for row in counts):
            raise ValueError("actual splits have fewer than 19 calibration controls")
        print(_markdown(counts), flush=True)
        for tier in Tier:
            print(f"Extracting {tier.value} at cadence {config.checkpoint_every}", flush=True)
            for name, group in records.items():
                extracted = build_tier_data(group, tier, workers=config.workers,
                                             checkpoint_every=config.checkpoint_every,
                                             retain_traces=False)
                write_recorded(out / "dataset" / name, extracted)
            # Fit the exact representation that offline eval will load.
            rows, control_rows, shuffled, flags = _fit_tier(out, tier, splits, config)
            metrics.extend(rows)
            controls.extend(control_rows)
            negative.extend(shuffled)
            if flags:
                loud_flags = flags
    reports = [out / "inventory.md", *write_report(metrics, out),
               out / "controls.md", out / "negative-control.md",
               write_headline(metrics, controls, negative, out)]
    _write_text(reports[0], f"# Reproduction inventory\n\nSeed: {config.seed}\n\n"
                f"Command template: `{command}`\n\n"
                f"Checkpoint cadence: {config.checkpoint_every} ticks.\n\n"
                + _markdown(class_counts) + "\n"
                + "Per-class counts below are disjoint fitting, calibration, and test runs.\n\n"
                + _markdown(counts))
    _write_text(out / "controls.md", "# Independent controls\n\n"
                "Models and thresholds are from the main by-run split; neither control sweep "
                "is used for fitting or calibration. Every k-of-n rate uses a 95% Wilson "
                "interval. Each row names seed, main split and its fitting/calibration/test "
                "class counts. Independent benign test runs are all controls; independent "
                "loud test runs are all positive. BOTH V1 aggregation detectors must flag "
                "every loud run at the calibrated threshold and score it strictly above "
                "every calibration control with benign_sharing_teams == 0. Logistic must "
                "also beat every calibration control. Boosted's all-controls strict bar "
                "is non-gating and is reported separately below with its measured outcome. "
                "The rule baseline has no gating bars: its rows, including its three bar "
                "comparisons, are diagnostics, and it never affects the reproduce exit status. "
                "Ties fail each strict comparison. Sharing metadata is taken only from "
                "recorded main-run conditions to select comparison controls after fitting "
                "and calibration; it never enters a detector. All loud scores and bars "
                "are full-trace measurements, including when repeated beside online benign FPR. "
                "Other tier/family rows are diagnostics.\n\n"
                "## V1 aggregation loud bars\n\n" + _markdown(loud_bar_rows(controls))
                + "\n## All control measurements\n\n" + _markdown(controls))
    _write_text(out / "negative-control.md", "# Shuffled-label negative control\n\n"
                f"{config.shuffle_repeats} seeded permutations of labels across whole main runs; "
                "models refitted for each permutation. By-run splits only. AUROC mean, "
                "standard error (sample SD / sqrt(permutations)), and range describe "
                "permutation variability on this fixed dataset. They are not uncertainty "
                "estimates over new runs. No pass/fail criterion is applied: the overlapping "
                "splits reuse one dataset, and the SE alone does not justify a general "
                "no-signal test. Split class counts are identical across permutations. "
                "The volume reference "
                "is family-independent. Attribution and timing are not interpreted "
                "for fake labels.\n\n"
                + _markdown(negative))
    semantic = asdict(config)
    semantic.pop("workers")
    manifest = {"format": "swarmtrace-experiment-v1", "config": semantic,
                "command": command, "run_metadata": run_metadata, "class_counts": class_counts,
                "splits": [{"name": split.name, "train": split.train, "test": split.test}
                           for split in splits], "counts": counts,
                "loud_flags_V1_aggregation": loud_flags}
    _write_experiment(out, manifest)
    size = sum(path.stat().st_size for path in out.rglob("*") if path.is_file())
    if size >= MAX_BYTES:
        raise ValueError(f"recorded output is {size} bytes, exceeding the <15 MB budget")
    print(f"Recorded output: {size} bytes. "
          f"Tables: {', '.join(p.name for p in reports)}", flush=True)
    require_loud_detection(loud_flags)
    if readme is not None:
        render_readme(readme, out / "headline.md")
    return reports
