"""The scope sweep and the byte-identical, role-flipped twin gate."""

import hashlib
import multiprocessing
import os
from collections.abc import Callable, Iterator, Sequence
from concurrent.futures import ProcessPoolExecutor
from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
from itertools import product
from pathlib import Path
from shutil import copytree
from tempfile import TemporaryDirectory
from time import perf_counter

import pandas as pd

from swarmtrace.detect import FILES_RULE, FILES_RULE_COLUMN, RULE, SCOPE_RULE
from swarmtrace.eval.data import RunRecord, load_runs
from swarmtrace.eval.harness import child_seed
from swarmtrace.eval.metrics import wilson
from swarmtrace.eval.recorded import TableRecord, load_run_table, write_run_table
from swarmtrace.eval.scope import (
    CONTEXTS,
    LABELLINGS,
    REFERENCE,
    SCOPE_DETECTORS,
    SPLIT_ROW,
    THRESHOLD,
    CalibrationRow,
    ScopeRecord,
    ScopeRow,
    evaluate_scope,
    labels_for,
    run_kind,
    scope_split,
    scope_table,
)
from swarmtrace.sim.runner import (
    CHANNELS,
    COORDINATED_GROUP_COUNTS,
    GROUP_SIZES,
    TOPOLOGIES,
    Condition,
    build_run,
    run_one,
)
from swarmtrace.trace.io import Trace, read_manifest, read_trace
from swarmtrace.trace.tiers import Tier

from .config import RunJob
from .pipeline import _simulate, _write_text

MAX_DATA_BYTES = 20_000_000
SCOPE_SEED_KEY, IDENTICAL_SEED_KEY = 95, 96
VIOLATIONS = (0, 1, 2, 5)
SAMPLE_CELL = ("coordinated_groups", "channel", "topology", "offensive_group_size",
               "scope_mistake_rate")


@dataclass(frozen=True)
class ScopeConfig:
    seed: int = 20261120
    workers: int = 4
    coordinated_groups: tuple[int, ...] = COORDINATED_GROUP_COUNTS
    channels: tuple[str, ...] = CHANNELS
    topologies: tuple[str, ...] = TOPOLOGIES
    group_sizes: tuple[int, ...] = GROUP_SIZES[1:]
    mistake_rates: tuple[int, ...] = (0, 2, 5)
    control_repeats: int = 9
    offensive_repeats: int = 1
    identical_repeats: int = 2
    n_ticks: int = 160
    n_bootstrap: int = 200

    def __post_init__(self) -> None:
        if type(self.seed) is not int or self.seed < 0:
            raise ValueError("seed must be a non-negative integer")
        for name in ("workers", "control_repeats", "offensive_repeats", "identical_repeats",
                     "n_ticks", "n_bootstrap"):
            value = getattr(self, name)
            if type(value) is not int or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        for name, allowed in (("coordinated_groups", COORDINATED_GROUP_COUNTS),
                              ("channels", CHANNELS), ("topologies", TOPOLOGIES),
                              ("group_sizes", GROUP_SIZES[1:]), ("mistake_rates", (0, 2, 5))):
            values = getattr(self, name)
            if (not values or len(set(values)) != len(values)
                    or any(value not in allowed or type(value) is not type(allowed[0])
                           for value in values)):
                raise ValueError(f"{name} must be a nonempty, unique subset of {allowed}")


def _cells(config: ScopeConfig) -> list[Condition]:
    return [Condition(channel=channel, topology=topology, coordinated_groups=groups,
                      n_ticks=config.n_ticks, benign_credential_sharing=10, scope="on",
                      scope_mistake_rate=rate)
            for groups, channel, topology, rate in product(
                config.coordinated_groups, config.channels, config.topologies,
                config.mistake_rates)]


def make_scope_jobs(config: ScopeConfig) -> tuple[RunJob, ...]:
    """Assign each simulation its own (95, i) stream before dispatch."""
    cells = _cells(config)
    conditions = [cell for cell in cells for _ in range(config.control_repeats)]
    conditions.extend(replace(cell, offensive_group_size=size, violation_size=violation)
                      for cell in cells for size in config.group_sizes for violation in VIOLATIONS
                      for _ in range(config.offensive_repeats))
    return tuple(RunJob("scope", f"scope-{i:04d}", child_seed(config.seed, SCOPE_SEED_KEY, i), cell)
                 for i, cell in enumerate(conditions))


def make_identical_jobs(config: ScopeConfig) -> tuple[RunJob, ...]:
    """One job per pair; both twins use the pair's (96, i) seed."""
    conditions = [replace(cell, benign_credential_sharing=100)
                  for cell in _cells(config) for _ in range(config.identical_repeats)]
    return tuple(RunJob("identical", f"identical-{i:04d}",
                        child_seed(config.seed, IDENTICAL_SEED_KEY, i), cell)
                 for i, cell in enumerate(conditions))


def _counts(records: Sequence[ScopeRecord], seed: int) -> dict[str, tuple[int, ...]]:
    split = scope_split(records, seed)
    counts = {}
    for labelling in LABELLINGS:
        labels = labels_for(records, labelling)
        counts[labelling] = tuple(count for ids in (split.fitting, split.calibration, split.test)
                                  for count in (sum(not labels[run] for run in ids),
                                                sum(labels[run] for run in ids)))
    return counts


def _require_calibration(counts: dict[str, tuple[int, ...]]) -> None:
    # Check legacy first: it has the smaller control population.
    for labelling in reversed(LABELLINGS):
        if counts[labelling][2] < 19:
            raise ValueError(f"{labelling} needs at least 19 calibration controls; "
                             f"grid supplies {counts[labelling][2]}")


def preflight(config: ScopeConfig) -> dict[str, tuple[int, ...]]:
    """Use the evaluator's stratum split before simulating. Identities affect membership,
    but cannot change the counts within each stratum under either labelling.
    """
    records = [TableRecord(job.directory, bool(job.condition.offensive_group_size), {
        **asdict(job.condition), "benign_sharing_teams": 0,
        "offence_style": "scope_violation" if job.condition.violation_size else "credential_relay",
    }) for job in make_scope_jobs(config)]
    counts = _counts(records, config.seed)
    _require_calibration(counts)
    return counts


def _fresh_output(out: str | Path) -> Path:
    out = Path(out)
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        raise ValueError(f"output directory already contains artifacts: {out}; "
                         "choose a fresh directory")
    out.mkdir(parents=True, exist_ok=True)
    return out


@contextmanager
def _worker_threads() -> Iterator[None]:
    # Models always run in a fresh spawned process so these limits take effect before import.
    names = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")
    previous = {name: os.environ.get(name) for name in names}
    try:
        os.environ.update(dict.fromkeys(names, "1"))
        yield
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def _map(function: Callable, tasks: Sequence, workers: int) -> list:
    if workers == 1:
        return [function(task) for task in tasks]
    with ProcessPoolExecutor(max_workers=workers,
                             mp_context=multiprocessing.get_context("spawn")) as pool:
        return list(pool.map(function, tasks))


@dataclass(frozen=True)
class TwinResult:
    pair: str
    seed: int
    mismatches: tuple[str, ...]


def _identical_pair(
    task: tuple[RunJob, Path], *, capture_authorization: bool = False,
) -> TwinResult:
    job, root = task
    setup = build_run(job.condition, job.seed)
    twin = replace(job.condition,
                   offensive_group_size=len(setup.groups[setup.focal_group].members))
    pair_root = root / job.dataset / job.directory
    options = {"capture_authorization": True} if capture_authorization else {}
    control = run_one(job.condition, job.seed, pair_root / "control", **options)
    relay = run_one(twin, job.seed, pair_root / "relay", **options)
    files = ("trace.jsonl", "context.json")
    if capture_authorization:
        files += ("authorization.json",)
    mismatches = tuple(name for name in files
                       if (control / name).read_bytes() != (relay / name).read_bytes())
    return TwinResult(job.directory, job.seed, mismatches)


def _identical_report(results: Sequence[TwinResult], seed: int) -> str:
    failed = [result for result in results if result.mismatches]
    lines = ["# Scope identical-policy gate", "", f"Seed: {seed}; dataset: identical.", "",
             "Gate: byte comparison of trace.jsonl and context.json in every role-flipped pair.",
             "", f"{len(results) - len(failed)} of {len(results)} identical.", ""]
    if failed:
        lines += ["FAILED. The scope sweep was not run.", "",
                  "| Pair | Seed | Mismatched files |", "| --- | --- | --- |"]
        lines.extend(f"| {result.pair} | {result.seed} | {', '.join(result.mismatches)} |"
                     for result in failed)
    else:
        lines += ["AUROC is exactly 0.5 at every context level (aggregation-only reference, "
                  "C0, C1, C2): each score has an identical opposite-label twin.",
                  "This is a consequence of byte identity, not an estimated AUROC interval."]
    return "\n".join(lines) + "\n"


def distinct_files_read_max(trace: Trace) -> int:
    """Maximum distinct successful read targets per agent, using only V0 fields."""
    files: dict[str, set[str]] = {}
    for event in trace.events:
        if event.tool == "read" and event.result["status"] == "ok":
            files.setdefault(event.agent, set()).add(event.target)
    return max((len(targets) for targets in files.values()), default=0)


def _experiment_row(record: RunRecord) -> pd.DataFrame:
    frame = scope_table([record])
    trace = read_trace(record.trace_path, Tier.V0)
    frame[FILES_RULE_COLUMN] = pd.Series([distinct_files_read_max(trace)],
                                       index=frame.index, dtype="int64")
    return frame


def build_scope_table(records: Sequence[RunRecord], workers: int = 1) -> pd.DataFrame:
    """The unchanged scope feature frame plus one opt-in, non-family diagnostic column."""
    if workers < 1 or not records:
        raise ValueError("scope table needs records and positive workers")
    ordered = sorted(records, key=lambda record: record.run_id)
    return pd.concat(_map(_experiment_row, ordered, workers))


def _evaluate_table(
    path: Path, seed: int, n_bootstrap: int,
) -> tuple[list[ScopeRow], list[CalibrationRow]]:
    recorded = load_run_table(path)
    calibration = []
    rows = evaluate_scope(recorded.features, recorded.records, seed, n_bootstrap,
                          diagnostics=recorded.diagnostics, calibration_rows=calibration)
    return rows, calibration


def _number(value: float) -> str:
    return f"{value:.4f}"


def _measurement(row: ScopeRow | None) -> str:
    if row is None:
        return "not applicable"
    if row.detector == SPLIT_ROW:
        return str(row.n)
    value = _number(row.value)
    if row.metric != THRESHOLD:
        interval = f"[{_number(row.low)}, {_number(row.high)}] {row.interval}"
        if "auroc" in row.metric:
            value = (f"{value} {interval}; {row.positive_runs} positive / "
                     f"{row.control_runs} control; bootstrap {row.valid} of {row.requested}")
        else:
            value = f"{row.n} of {row.total}; {value} {interval}"
    return "; ".join(part for part in (value, row.note, row.status) if part)


def _classes(counts: tuple[int, ...]) -> str:
    return "; ".join(f"{name} {counts[i]} C / {counts[i + 1]} P"
                     for name, i in (("fit", 0), ("cal", 2), ("test", 4)))


def _calibration_count(count: int | None, total: int) -> str:
    if count is None:
        return "not available"
    estimate = wilson(count, total)
    return (f"{count} of {total}; {_number(estimate.value)} "
            f"[{_number(estimate.low)}, {_number(estimate.high)}] Wilson")


def _added_report_sections(
    rows: Sequence[ScopeRow], calibration: Sequence[CalibrationRow], table: pd.DataFrame,
    records: Sequence[ScopeRecord], seed: int,
) -> list[str]:
    c0 = table.filter(regex="__C0$").rename(columns=lambda name: name.removesuffix("__C0"))
    c1 = table.filter(regex="__C1$").rename(columns=lambda name: name.removesuffix("__C1"))
    if c0.empty or not c0.equals(c1):
        raise ValueError("C0 and C1 scope columns are not identical")
    lines = ["", "## Calibration diagnostics", "", f"Seed: {seed}; split: by run; V1.", "",
             "Conformal rank: ceil((n+1)*0.95) of n calibration controls.", "",
             "| Labelling | Context | Detector | Rank | Threshold | Calibration controls | "
             "Control kind | Kind controls | Score > 0 | Score >= threshold | "
             "Class counts | Note |",
             "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for row in calibration:
        context = "aggregation-only reference" if row.context == REFERENCE else row.context
        cells = [row.labelling, context, row.detector,
                 f"{row.rank} of {row.calibration_controls}", _number(row.threshold),
                 str(row.calibration_controls), row.control_kind, str(row.total),
                 _calibration_count(row.above_zero, row.total),
                 _calibration_count(row.at_or_above_threshold, row.total),
                 _classes(row.split_counts), row.note]
        lines.append("| " + " | ".join(cells) + " |")
    lines += ["", "At C2 under the strict labelling the threshold is set by in-scope relays "
              "that made an out-of-scope mistake read.", "",
              "C0 and C1 scope columns are identical in every run; their rows differ only "
              "in bootstrap seed.", "", "## Observed borrowed-session breadth", "",
              f"Seed: {seed}; population: all scope runs; "
              "column: borrowed_session_breadth_max__C0.",
              "", "| Population | Runs | Minimum | Median | Maximum |",
              "| --- | --- | --- | --- | --- |"]
    for name, members in (
        ("in-scope relays", [record.run_id for record in records
                             if run_kind(record) == "in_scope"]),
        ("benign controls", [record.run_id for record in records if not record.positive]),
    ):
        values = table.loc[members, "borrowed_session_breadth_max__C0"]
        lines.append(f"| {name} | {len(members)} | {_number(values.min())} | "
                     f"{_number(values.median())} | {_number(values.max())} |")
    lines += ["", "## Strict detection by violation size", "",
              f"Seed: {seed}; split: by run; V1; labelling: strict.", "",
              "| Context | Detector | Size 1 | Size 2 | Size 5 | "
              "Calibration controls | Class counts |",
              "| --- | --- | --- | --- | --- | --- | --- |"]
    lookup = {(row.context, row.detector, row.metric): row for row in rows
              if row.labelling == "strict"}
    for context in ("C0", "C2"):
        for detector in (SCOPE_RULE, FILES_RULE, "logistic", "boosted"):
            selected = [lookup[context, detector, f"detection_rate_violation_size_{size}"]
                        for size in (1, 2, 5)]
            cells = [context, detector, *(_measurement(row) for row in selected),
                     str(selected[0].split_counts[2]), _classes(selected[0].split_counts)]
            lines.append("| " + " | ".join(cells) + " |")
    return lines


def _report(rows: Sequence[ScopeRow], records: Sequence[ScopeRecord], config: ScopeConfig,
            out: Path, *, calibration: Sequence[CalibrationRow] = (),
            table: pd.DataFrame | None = None) -> str:
    split = scope_split(records, config.seed)
    test = [record for record in records if record.run_id in split.test]
    sharing = sum(not record.positive and record.condition["benign_sharing_teams"] > 0
                  for record in test)
    in_scope = sum(run_kind(record) == "in_scope" for record in test)
    lines = ["# Scope experiment", "", f"Seed: {config.seed}; dataset: scope; tier: V1.", "",
             f"Command: `swarmtrace scope --seed {config.seed} --out DIR --workers N`.",
             "DIR and N are execution choices and do not change recorded bytes.", "",
             "Split: by run, stratified by kind and mistake rate; test fraction 0.3000; "
             "calibration fraction of training 0.3000; target FPR 0.0500.",
             "Split and evaluation seeds use child_seed(seed, 97, ...). "
             f"Bootstrap replicates: {config.n_bootstrap}; confidence: 0.9500.", "",
             f"Realised test set sharing controls: {sharing}; in-scope relays: {in_scope}.", "",
             "Strict: scope violations are positive; in-scope relays are controls. "
             "Legacy: every relay is positive.", "",
             "Grid: " + "; ".join(f"{name}={getattr(config, name)}" for name in (
                 "coordinated_groups", "channels", "topologies", "group_sizes", "mistake_rates",
                 "control_repeats", "offensive_repeats", "identical_repeats", "n_ticks")) + ".",
             "Sharing rate: 10 percent; scope: on.", "",
             "| Partition | Benign controls | Sharing controls | In-scope relays | "
             "Violation 1 | Violation 2 | Violation 5 |",
             "| --- | --- | --- | --- | --- | --- | --- |"]
    for name, ids in (("all", tuple(record.run_id for record in records)),
                      ("fitting", split.fitting), ("calibration", split.calibration),
                      ("test", split.test)):
        members = [record for record in records if record.run_id in ids]
        counts = [sum(not record.positive for record in members),
                  sum(not record.positive and record.condition["benign_sharing_teams"] > 0
                      for record in members),
                  *(sum(run_kind(record) == kind for record in members)
                    for kind in ("in_scope", "violation_1", "violation_2", "violation_5"))]
        lines.append(f"| {name} | " + " | ".join(map(str, counts)) + " |")
    counts = _counts(records, config.seed)
    by_key = {(row.labelling, row.context, row.detector, row.metric): row for row in rows}
    # Display the new baseline beside the rules without changing existing detector seed indices.
    display = (RULE, SCOPE_RULE, FILES_RULE, *SCOPE_DETECTORS[2:-1])
    for context, detector in [("all", SPLIT_ROW), *product(CONTEXTS, display)]:
        metrics = list(dict.fromkeys(row.metric for row in rows
                                     if row.context == context and row.detector == detector))
        context_name = "aggregation-only reference" if context == REFERENCE else context
        lines += ["", f"## {context_name}: {detector}", "",
                  f"Seed: {config.seed}; split: by run; V1.", "",
                  "| Metric | Strict | Legacy | Strict calibration controls | "
                  "Legacy calibration controls | Strict class counts | Legacy class counts |",
                  "| --- | --- | --- | --- | --- | --- | --- |"]
        for metric in metrics:
            pair = [by_key.get((labelling, context, detector, metric)) for labelling in LABELLINGS]
            row_counts = [row.split_counts if row else counts[labelling]
                          for row, labelling in zip(pair, LABELLINGS, strict=True)]
            cells = [metric, *(_measurement(row) for row in pair),
                     *(str(value[2]) for value in row_counts),
                     *(_classes(value) for value in row_counts)]
            lines.append("| " + " | ".join(cells) + " |")
    if table is not None:
        lines.extend(_added_report_sections(rows, calibration, table, records, config.seed))
    paths = [out / "scope" / "runs.csv.gz",
             *sorted(path for path in (out / "scope" / "raw").rglob("*") if path.is_file())]
    lines += ["", "```text"]
    lines.extend(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  "
                 f"{path.relative_to(out).as_posix()}" for path in paths)
    return "\n".join([*lines, "```", ""])


def _samples(records: Sequence[RunRecord]) -> tuple[RunRecord, RunRecord]:
    ordered = sorted(records, key=lambda record: record.run_id)
    relay = next(record for record in ordered if run_kind(record) == "in_scope")
    violation = next(record for record in ordered if run_kind(record) == "violation_5"
                     and all(record.condition[key] == relay.condition[key] for key in SAMPLE_CELL))
    return relay, violation


def _check_data_budget(out: Path) -> None:
    """Count the proposed output alongside existing repository data, without double counting."""
    data = Path(__file__).resolve().parents[3] / "data"
    output = out.resolve()
    existing = sum(path.stat().st_size for path in data.rglob("*")
                   if path.is_file() and not path.resolve().is_relative_to(output))
    added = sum(path.stat().st_size for path in out.rglob("*") if path.is_file())
    if existing + added >= MAX_DATA_BYTES:
        raise ValueError(f"data budget exceeded: {existing + added} bytes; "
                         f"must stay under {MAX_DATA_BYTES}")


def run_scope(out: str | Path, config: ScopeConfig) -> list[Path]:
    """Preflight, gate, simulate, archive V1, and report. No main results on gate failure."""
    planned = preflight(config)
    out = _fresh_output(out)
    jobs, identical = make_scope_jobs(config), make_identical_jobs(config)
    print(f'seed={config.seed}; command=swarmtrace scope --seed {config.seed} '
          f'--out "{out}" --workers {config.workers}', flush=True)
    with _worker_threads(), TemporaryDirectory(prefix="scope-", dir=out) as temporary:
        raw = Path(temporary)
        twins = _map(_identical_pair, [(job, raw) for job in identical], config.workers)
        _write_text(out / "scope-identical.md", _identical_report(twins, config.seed))
        failed = [result.pair for result in twins if result.mismatches]
        if failed:
            raise ValueError("identical-policy gate failed: " + ", ".join(failed)
                             + "; see scope-identical.md")
        print(f"{len(twins)} of {len(twins)} identical; starting scope sweep", flush=True)
        _map(_simulate, [(job, raw) for job in jobs], config.workers)
        records = load_runs(raw / "scope")
        actual = _counts(records, config.seed)
        _require_calibration(actual)
        if actual != planned:
            raise ValueError("actual scope split counts differ from preflight")
        table = build_scope_table(records, workers=config.workers)
        table_records = [replace(record, condition={
            **record.condition, "dataset": "scope",
            "seed": read_manifest(record.trace_path.parent / "manifest.json").seed,
        }) for record in records]
        outcomes = {record.run_id: {
            "objective_completed": int(record.labels.objective_completed),
            "objective_tick": (record.labels.objective_tick
                               if record.labels.objective_tick is not None else "none"),
        } for record in records}
        table_path = out / "scope" / "runs.csv.gz"
        write_run_table(table_path, table, table_records, extra=outcomes)
        # Fit the recorded representation with one native thread, even for --workers 1.
        with ProcessPoolExecutor(max_workers=1,
                                 mp_context=multiprocessing.get_context("spawn")) as pool:
            rows, calibration = pool.submit(_evaluate_table, table_path, config.seed,
                                            config.n_bootstrap).result()
        for record in _samples(records):
            copytree(record.trace_path.parent, out / "scope" / "raw" / record.run_id)
        _write_text(out / "scope.md", _report(rows, table_records, config, out,
                                            calibration=calibration, table=table))
    _check_data_budget(out)
    return [out / "scope.md", out / "scope-identical.md", out / "scope" / "runs.csv.gz"]


def time_scope_runs(
    out: str | Path, config: ScopeConfig, count: int = 50,
) -> dict[str, float | int]:
    """Time a spread of scope cells without publishing results or running the experiment.

    Projection covers simulations only, including both twins per identical job. It excludes
    feature extraction, fitting and report generation. Elapsed times never enter artifacts.
    """
    jobs = make_scope_jobs(config)
    if type(count) is not int or not 1 <= count <= len(jobs):
        raise ValueError(f"time-runs must be between 1 and {len(jobs)}")
    out = _fresh_output(out)
    selected = [jobs[i * len(jobs) // count] for i in range(count)]
    with _worker_threads(), TemporaryDirectory(prefix="scope-timing-", dir=out) as temporary:
        start = perf_counter()
        _map(_simulate, [(job, Path(temporary)) for job in selected], config.workers)
        elapsed = perf_counter() - start
    simulations = len(jobs) + 2 * len(make_identical_jobs(config))
    projected = elapsed * simulations / count
    print(f"Timed {count} runs in {elapsed:.4f} seconds with {config.workers} workers. "
          f"Projected {simulations} simulations: {projected:.4f} seconds "
          f"({projected / 60:.4f} minutes); excludes feature extraction, fitting and reporting.",
          flush=True)
    return {"runs": count, "seconds": elapsed, "simulations": simulations,
            "projected_seconds": projected}
