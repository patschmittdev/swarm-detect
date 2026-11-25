"""Paired evaluation of assignment-local and whole-run scope scores."""

import json
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import pandas as pd

from swarmtrace.detect import RunDetector
from swarmtrace.detect.assignment import TEMPERATURE, AssignmentLogistic
from swarmtrace.eval.containment import _required_read
from swarmtrace.eval.recorded import load_run_table, write_json
from swarmtrace.features import run_features
from swarmtrace.features.assignment import ASSIGNMENT_COLUMNS, assignment_features
from swarmtrace.features.grant_scope import GRANT_COLUMN
from swarmtrace.sim.runner import run_one
from swarmtrace.trace.authorization import read_authorization
from swarmtrace.trace.context import read_context
from swarmtrace.trace.io import RunPaths, read_trace
from swarmtrace.trace.tiers import Tier

from . import grant_policy, grant_round, read_calibration, read_round
from .scope import ScopeConfig, _identical_pair, _map, _worker_threads, make_identical_jobs

REFERENCE = grant_round.REFERENCE
VERIFIED = grant_round.CANDIDATE
CANDIDATE = "assignment-logistic"
POOLED = "grant-column-max-logistic"
SHARED_WEIGHTS = "assignment-weights-pooled-evidence"
CALIBRATION_SEEDS = tuple(range(20270101, 20270109))
CONFIRMATION_SEEDS = tuple(range(20270111, 20270121))
VIEWS = ("native", "workflow")


@dataclass
class _Sample:
    row: dict
    grants: tuple[str, ...]
    bag: np.ndarray


def _read(paths: RunPaths):
    return read_trace(paths.trace, Tier.V1), read_context(paths.context), read_authorization(paths.authorization)


def _observation(trace, context, audit, support: dict) -> _Sample:
    bag = assignment_features(trace, context, audit)
    counters = run_features(trace, context=context).loc[trace.run_id, list(grant_round.BASE_COLUMNS)].to_dict()
    counters[GRANT_COLUMN] = int(bag.features.excluded_files.max()) if len(bag.features) else 0
    row = dict(run_id=trace.run_id, **counters, **support, assignment_count=len(bag.features),
               successful_reads=bag.successful_reads, grant_reads=bag.grant_reads,
               ordinary_reads=bag.ordinary_reads, unknown_reads=bag.unknown_reads,
               missing_decisions=bag.missing_reads, capture_present=bag.capture_present)
    return _Sample(row, tuple(bag.features.index), bag.features.to_numpy(dtype=float))


def _observe(task) -> list[_Sample]:
    grid, job, family = task
    with TemporaryDirectory() as temp:
        paths = RunPaths(run_one(job.condition, job.seed, temp, capture_authorization=True))
        trace, context, audit = _read(paths)
        support = dict(family=family or "development", support_kind="native", native_components=0,
                       anchored_components=0, office_tickets=0, exercised_office_tickets=0,
                       shared_verified_documents=0, shared_reviewer_host_pairs=0, office_reads=0,
                       office_unknown_reads=0, office_missing_decisions=0, office_reads_before_native_end=0,
                       shared_reads_before_component_end=0, no_safe_interleave=False, fallback=False,
                       message_handoffs=0)
        views = {"native": _observation(trace, context, audit, support)}
        if family is not None:
            from .assignment_workflows import make_assignment_view

            views["workflow"] = _observation(*make_assignment_view(trace, context, audit, family=family))
        truth = grant_round._truth(paths, trace.run_id)
        outcomes = json.loads(paths.outcomes.read_bytes())
        if outcomes["run_id"] != trace.run_id:
            raise ValueError("completion audit must match the observed run")
        required, completed = _required_read(outcomes)
        truth.update(designated_files=required, completed_required_files=completed)
        for view, sample in views.items():
            sample.row.update(truth, grid=grid, view=view)
        return list(views.values())


def _twins(job):
    from .assignment_workflows import WORKFLOWS, make_assignment_view

    with TemporaryDirectory() as directory:
        root = Path(directory)
        twins = _identical_pair((job, root), capture_authorization=True)
        if twins.mismatches:
            raise ValueError(f"native role twins differ on {twins.pair}")
        pair = [_read(RunPaths(root / job.dataset / job.directory / name)) for name in ("control", "relay")]
        results = []
        for family in WORKFLOWS:
            left, right = (make_assignment_view(*item, family=family) for item in pair)
            if left != right:
                raise ValueError(f"{family} has a role-dependent observation on {twins.pair}")
            results.append(dict(pair=twins.pair, seed=twins.seed, family=family, identical=True))
        return results


def _previous(benchmarks: Path):
    first, latest = benchmarks / "grant-scope", benchmarks / "grant-policy"
    models, _, seen, provenance = grant_policy._restore(first)
    protocol = json.loads((latest / "protocol.json").read_bytes())
    if (protocol["provenance"]["protocol_sha256"] != provenance["protocol_sha256"]
            or protocol["calibration_seeds"] != list(grant_policy.CALIBRATION_SEEDS)
            or protocol["confirmation_seeds"] != list(grant_policy.CONFIRMATION_SEEDS)):
        raise ValueError("grant-policy history does not match its frozen inputs")
    for name in ("calibration-controls", *grant_policy.CONFIRMATION_SEEDS):
        matches = None
        for view in ("native", grant_policy.LAYOUT):
            rows = pd.read_csv(latest / view / f"{name}.csv.gz", dtype=str,
                               usecols=["run_id", "detector", "positive", "grid"])
            arms = [rows[rows.detector == arm].set_index("run_id")[["grid", "positive"]].sort_index()
                    for arm in (REFERENCE, grant_policy.CANDIDATE)]
            if (len(rows) != 2 * len(arms[0]) or not arms[0].index.is_unique or not arms[0].equals(arms[1])
                    or (matches is not None and not matches.equals(arms[0]))):
                raise ValueError("previous policy views or arms differ in IDs or labels")
            matches = arms[0]
        expected = (protocol["calibration_controls_per_view"] if name == "calibration-controls"
                    else read_calibration.CONTROLS_PER_GRID + read_calibration.POSITIVES_PER_GRID)
        if len(matches) != expected:
            raise ValueError("previous policy population size differs from its protocol")
        read_calibration._reserve(matches.index, seen)
    provenance["grant_policy_protocol_sha256"] = read_calibration._sha256(latest / "protocol.json")
    provenance["reserved_ids"] = len(seen)
    return models, seen, provenance


def _frame(samples):
    return pd.DataFrame([sample.row for sample in samples])


def _bags(path, samples):
    rows = ((s.row["run_id"], grant, *values) for s in samples
            for grant, values in zip(s.grants, s.bag, strict=True))
    grant_round._write_table(path, pd.DataFrame(rows, columns=("run_id", "grant_id", *ASSIGNMENT_COLUMNS)))


def _maxima(samples):
    return pd.DataFrame([s.bag.max(axis=0, initial=0.) for s in samples], columns=ASSIGNMENT_COLUMNS)


def _fit(stage, prior, data, workers, seed):
    original = pd.read_csv(prior / "fitting.csv.gz", dtype=str, keep_default_na=False)
    ids = list(original.run_id)
    tasks = [(grid, job, None) for grid, job, _ in grant_round._fitting_tasks(
        load_run_table(data / "scope/runs.csv.gz"), ids)]
    samples = [pair[0] for pair in _map(_observe, tasks, workers)]
    frame = _frame(samples)
    inputs = (*grant_round.BASE_COLUMNS, GRANT_COLUMN)
    if (list(frame.run_id) != ids or not np.array_equal(frame[list(inputs)],
            grant_policy._features(original, inputs), equal_nan=True)
            or not frame.positive.equals(original.positive.map({"True": True, "False": False}))):
        raise ValueError("replayed fitting IDs, inputs or strict labels differ from the published fit")
    selected = frame.assignment_count.gt(0)
    pooled = RunDetector(REFERENCE, seed).fit(_maxima(samples).loc[selected], frame.loc[selected, "positive"])
    model = AssignmentLogistic.fit([s.bag for s in samples], frame.positive)
    grant_round._write_table(stage / "fitting.csv.gz", frame)
    _bags(stage / "fitting-assignments.csv.gz", samples)
    return model, pooled, int(selected.sum())


def _sample(seeds, controls_only, workers, seen):
    from .assignment_workflows import WORKFLOWS

    tasks = [(grid, job, WORKFLOWS[index % len(WORKFLOWS)]) for index, grid in enumerate(seeds)
             for job in read_round._jobs(grid, (read_round.CONFIRMATION_CHANNEL,))
             if not controls_only or job.condition.violation_size == 0]
    observed = _map(_observe, tasks, workers)
    views = {v: sorted((s for pair in observed for s in pair if s.row["view"] == v),
                       key=lambda s: (s.row["grid"], s.row["run_id"])) for v in VIEWS}
    frame = _frame(views["native"])
    metadata = ["run_id", "grid", "family", *grant_round.LABEL_COLUMNS]
    if not frame[metadata].equals(_frame(views["workflow"])[metadata]):
        raise ValueError("native and augmented views need the same underlying IDs and truth")
    read_calibration._reserve(pd.Index(frame.run_id), seen)
    for grid in seeds:
        part = frame[frame.grid == grid]
        if (int((~part.positive).sum()) != read_calibration.CONTROLS_PER_GRID
                or int(part.positive.sum()) != (0 if controls_only else read_calibration.POSITIVES_PER_GRID)
                or int(part.small_positive.sum()) != (0 if controls_only else read_calibration.IN_SCOPE_PER_GRID)
                or int(part.hard_control.sum()) != read_calibration.IN_SCOPE_PER_GRID):
            raise ValueError("unexpected calibration or confirmation population")
    return views


def _scores(samples, models, local, pooled):
    frame = _frame(samples)
    maxima = _maxima(samples)
    scores = grant_round._scores(frame, models)
    available = frame.assignment_count.gt(0).to_numpy()
    scores[POOLED] = np.where(available, pooled.score(maxima), 0.)
    scores[SHARED_WEIGHTS] = np.array([local.pooled_evidence_score(s.bag) for s in samples])
    scores[CANDIDATE] = np.array([local.score(s.bag) for s in samples])
    if not all(np.isfinite(v).all() for v in scores.values()):
        raise ValueError("assignment round produced a nonfinite score")
    return scores


def _export(path, samples, scores, cutoffs, *, calibration):
    frame = _frame(samples)
    name = "calibration" if calibration else "independent"
    scored = pd.concat([frame.assign(task="scope", test_set=name, split_seed=read_round.ARCHIVE_SEED,
                                     detector=k, score=v, threshold=cutoffs[k]) for k, v in scores.items()],
                       ignore_index=True)
    _bags(path / f"{name}-assignments.csv.gz", samples)
    if calibration:
        grant_round._write_table(path / "calibration-controls.csv.gz", scored)
        return []
    files = []
    for seed, rows in scored.groupby("grid", sort=True):
        dest = path / f"{seed}.csv.gz"
        grant_round._write_table(dest, rows)
        files.append(dest)
    return files


def run_assignment_round(out: Path, benchmarks: Path, data: Path, workers: int = 4, *, checks_only=False):
    from swarmtrace.eval.assignment_round import report_assignment_round

    if type(workers) is not int or workers < 1 or out.exists():
        raise ValueError("assignment round requires a positive worker count and a new output directory")
    out.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=out.parent) as temp, _worker_threads():
        stage = Path(temp) / "assignment"
        stage.mkdir()
        pairs = _map(_twins, make_identical_jobs(ScopeConfig(seed=read_round.ARCHIVE_SEED)), workers)
        pd.DataFrame([row for pair in pairs for row in pair]).to_csv(stage / "role-twins.csv", index=False,
                                                                    lineterminator="\n")
        if checks_only:
            stage.rename(out)
            return
        models, seen, provenance = _previous(benchmarks)
        local, pooled, eligible = _fit(stage, benchmarks / "grant-scope", data, workers, provenance["fit_seed"])
        controls = _sample(CALIBRATION_SEEDS, True, workers, seen)
        cutoffs = {}
        for view, samples in controls.items():
            scores = _scores(samples, models, local, pooled)
            rank = grant_policy._tolerance_rank(len(samples))
            cutoffs[view] = {arm: float(np.sort(s)[rank - 1]) for arm, s in scores.items()}
            _export(stage / view, samples, scores, cutoffs[view], calibration=True)
        confirmation = _sample(CONFIRMATION_SEEDS, False, workers, seen)
        decisions = {}
        for view, samples in confirmation.items():
            scores = _scores(samples, models, local, pooled)
            folder = stage / view
            files = _export(folder, samples, scores, cutoffs[view], calibration=False)
            decisions[view] = report_assignment_round(
                folder, files, candidate=CANDIDATE, reference=REFERENCE,
                alternatives=(VERIFIED, POOLED, SHARED_WEIGHTS), primary=view == "workflow")
        write_json(stage / "protocol.json", {
            "reference": REFERENCE, "candidate": CANDIDATE, "primary_view": "workflow",
            "assignment_columns": list(ASSIGNMENT_COLUMNS), "fit_nonempty_runs": eligible,
            "model": {"center": local.center.tolist(), "scale": local.scale.tolist(),
                      "weights": local.weights.tolist(), "intercept": local.intercept, "temperature": TEMPERATURE},
            "calibration_seeds": list(CALIBRATION_SEEDS), "confirmation_seeds": list(CONFIRMATION_SEEDS),
            "calibration_controls_per_view": len(controls["workflow"]), "rank_one_based": rank,
            "cutoffs": cutoffs, "provenance": provenance, "decisions": decisions,
        })
        stage.rename(out)
