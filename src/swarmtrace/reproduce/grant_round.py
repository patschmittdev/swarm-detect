"""Paired full-run evaluation of a verified per-grant scope count."""

import json
import math
from collections import defaultdict
from functools import partial
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import pandas as pd

from swarmtrace.detect import RunDetector, conformal_threshold
from swarmtrace.eval import scope
from swarmtrace.eval.comparison import _cohort
from swarmtrace.eval.data import RunRecord
from swarmtrace.eval.recorded import load_run_table, write_gzip, write_json
from swarmtrace.eval.rounds import benchmark_round
from swarmtrace.features import run_features
from swarmtrace.features.grant_scope import GRANT_COLUMN, LEGACY_COLUMN, grant_scope_counts
from swarmtrace.features.read_evidence import read_evidence
from swarmtrace.sim.runner import build_run, run_one
from swarmtrace.trace.authorization import ReadAudit, read_authorization
from swarmtrace.trace.context import Context, read_context
from swarmtrace.trace.io import RunPaths, Trace, read_labels, read_manifest, read_trace
from swarmtrace.trace.tiers import Tier

from . import read_calibration as previous
from . import read_round
from .config import RunJob
from .scope import _map, _worker_threads

REFERENCE = read_round.REFERENCE
CANDIDATE = "logistic+verified-grant"
CALIBRATION_SEEDS = (20261203, 20261204, 20261205)
CONFIRMATION_SEEDS = tuple(range(20261206, 20261216))
POPULATIONS = ("overlap", "native")
MIN_ONE_FILE = 498
BASE_COLUMNS = read_round.BASE_COLUMNS
CANDIDATE_COLUMNS = tuple(GRANT_COLUMN if c == LEGACY_COLUMN else c for c in BASE_COLUMNS)
LABEL_COLUMNS = ("positive", "hard_control", "small_positive", "two_agent_positive",
                 "sharing_control", "topology", "scope_mistake_rate")
AUDIT_COUNTS = ("successful_reads", "grant_reads", "ordinary_reads", "unknown_reads",
                "missing_decisions", "distinct_grant_files", "registered_overlap_pairs",
                "competing_reads", "exercised_overlap_pairs")


def _overlap_counts(trace: Trace, audit: ReadAudit) -> tuple[int, int, int]:
    """Count multiple registered grants, concurrent eligible reads and exercised authorities.

    These simulator studies keep every successful login active for the run. Neither
    evaluation view invokes credential revocation. Only decisions with a recorded host
    can establish competition at a read.
    """
    registry = defaultdict(list)
    for grant in audit.grants:
        registry[grant.receiver, grant.host].append(grant)
    contested = {key: grants for key, grants in registry.items() if len(grants) > 1}
    if not contested:
        return 0, 0, 0
    decisions = {d.seq: d for d in audit.decisions if (d.agent, d.host) in contested}
    credentials = defaultdict(set)
    exercised = defaultdict(set)
    competing = 0
    for event in trace.events:
        if event.tool == "login" and event.result["status"] == "ok":
            key = (event.agent, event.target)
            if key in contested:
                credentials[key].add(event.args["credential"])
        decision = decisions.get(event.seq)
        if decision is not None:
            key = (decision.agent, decision.host)
            eligible = [g.grant_id for g in contested[key]
                        if not credentials[key].isdisjoint(g.credentials)]
            if len(eligible) > 1:
                competing += 1
                if decision.basis == "grant" and decision.grant_id in eligible:
                    exercised[key].add(decision.grant_id)
    return len(contested), competing, sum(len(ids) >= 2 for ids in exercised.values())


def _observation(trace: Trace, context: Context, audit: ReadAudit, variant: str) -> dict:
    full = run_features(trace, context=context).loc[trace.run_id, list(BASE_COLUMNS)].to_dict()
    counts = grant_scope_counts(read_evidence(trace, audit))
    registered, competing, exercised = _overlap_counts(trace, audit)
    return {
        **full, GRANT_COLUMN: counts.max_files_per_grant, "office_variant": variant,
        "successful_reads": counts.successful_reads, "grant_reads": counts.grant_reads,
        "ordinary_reads": counts.ordinary_reads, "unknown_reads": counts.unknown_reads,
        "missing_decisions": counts.successful_reads - len(audit.decisions),
        "distinct_grant_files": counts.distinct_grant_files, "registered_overlap_pairs": registered,
        "competing_reads": competing, "exercised_overlap_pairs": exercised,
    }


def _truth(paths: RunPaths, run_id: str) -> dict:
    labels, manifest = read_labels(paths.labels), read_manifest(paths.manifest)
    if not run_id == labels.run_id == manifest.run_id:
        raise ValueError("grant-round inputs must identify the same run")
    record = RunRecord(run_id, paths.trace, labels, manifest.condition)
    positive = scope.labels_for([record], scope.STRICT)[run_id]
    return dict(positive=positive, hard_control=scope.run_kind(record) == scope.IN_SCOPE,
                small_positive=positive and record.condition["violation_size"] == 1,
                two_agent_positive=positive and record.condition["offensive_group_size"] == 2,
                sharing_control=not record.positive and record.condition["benign_sharing_teams"] > 0,
                topology=record.condition["topology"], scope_mistake_rate=record.condition["scope_mistake_rate"])


def _observe(task: tuple[int, RunJob, bool], *, layout: str | None = None) -> list[dict]:
    grid, job, development = task
    if development:
        setup = build_run(job.condition, job.seed)
        if any(g.channel not in read_round.DEVELOPMENT_CHANNELS for g in setup.groups):
            raise ValueError("a held-out workflow entered the archived fitting replay")
    elif job.condition.channel != read_round.CONFIRMATION_CHANNEL:
        raise ValueError("fresh calibration and confirmation require preplanned focal workflows")
    with TemporaryDirectory() as temporary:
        paths = RunPaths(run_one(job.condition, job.seed, temporary, capture_authorization=True))
        trace = read_trace(paths.trace, Tier.V1)
        context, audit = read_context(paths.context), read_authorization(paths.authorization)
        views = {"native": _observation(trace, context, audit, "none")}
        if not development:
            from .office_overlap import with_office_overlap

            options = {} if layout is None else {"layout": layout}
            views["overlap"] = _observation(*with_office_overlap(trace, context, audit, **options))
        # The observations are complete before reading role and condition labels.
        truth = _truth(paths, trace.run_id)
        return [dict(grid=grid, run_id=trace.run_id, population=name, **truth, **values)
                for name, values in views.items()]


def _collect(tasks: list[tuple[int, RunJob, bool]], workers: int, *, layout: str | None = None) -> pd.DataFrame:
    observe = _observe if layout is None else partial(_observe, layout=layout)
    return pd.DataFrame([row for views in _map(observe, tasks, workers) for row in views])


def _fitting_tasks(table, fit_ids):
    by_id = {r.run_id: r for r in table.records}
    jobs = {job.seed: job for job in read_round._jobs(read_round.ARCHIVE_SEED,
                                                      read_round.DEVELOPMENT_CHANNELS)}
    return [(read_round.ARCHIVE_SEED, jobs[by_id[run_id].condition["seed"]], True) for run_id in fit_ids]


def _restore_fits(study: Path, data: Path, workers: int):
    if BASE_COLUMNS.count(LEGACY_COLUMN) != 1 or GRANT_COLUMN in BASE_COLUMNS:
        raise ValueError("the grant replacement requires exactly one inferred scope maximum")
    incumbent, _, seen, provenance = previous._restore(study, data)
    table = load_run_table(data / "scope" / "runs.csv.gz")
    fit_ids = provenance["partitions"]["fitting"]["run_ids"]
    tasks = _fitting_tasks(table, fit_ids)
    fit = _collect(tasks, workers).set_index("run_id")
    if sorted(fit.index) != sorted(fit_ids):
        raise ValueError("native fitting replay must recover exactly the original fitting ids")
    fit = fit.loc[fit_ids]
    archive = _cohort(table, "scope").select(tuple(fit_ids))
    if not np.array_equal(fit[list(BASE_COLUMNS)].to_numpy(dtype=float),
                          archive.features.to_numpy(dtype=float), equal_nan=True):
        raise ValueError("native fitting replay differs from the original ordered C2 inputs")
    if not np.array_equal(fit.positive, archive.truth.positive):
        raise ValueError("native fitting replay differs from the original strict labels")
    candidate = RunDetector(REFERENCE, provenance["fit_seed"], scope.MAX_FPR)
    candidate.fit(fit[list(CANDIDATE_COLUMNS)], fit.positive.to_numpy())
    return {REFERENCE: incumbent, CANDIDATE: candidate}, fit.reset_index(), seen, provenance


def _reserve_previous(path: Path, data: Path, seen: set[str], provenance: dict) -> dict:
    source = path / "protocol.json"
    prior = json.loads(source.read_bytes())
    if (prior["calibration_seeds"] != list(previous.CALIBRATION_SEEDS)
            or prior["confirmation_seeds"] != list(previous.CONFIRMATION_SEEDS)
            or prior["provenance"]["protocol_sha256"] != provenance["protocol_sha256"]
            or prior["provenance"]["archive_table_sha256"] != provenance["archive_table_sha256"]):
        raise ValueError("previous calibration must refer to the same archive and read study")
    for phase, seeds in (("calibration", previous.CALIBRATION_SEEDS),
                         ("confirmation", previous.CONFIRMATION_SEEDS)):
        for seed in seeds:
            ids = pd.Index(prior["samples"][phase][str(seed)]["run_ids"])
            expected = previous.CONTROLS_PER_GRID
            if phase == "confirmation":
                expected += previous.POSITIVES_PER_GRID
            if len(ids) != expected:
                raise ValueError("previous calibration study has missing run ids")
            previous._reserve(ids, seen)
    zero_shot = data.parent / "benchmarks" / "zero-shot"
    older = {}
    for scores in sorted(zero_shot.glob("*.csv.gz")):
        table = pd.read_csv(scores, usecols=["run_id", "task"], dtype=str)
        ids = table.loc[table.task == "scope", "run_id"].unique()
        previous._reserve(pd.Index(ids), seen)
        older[scores.name] = {"scope_ids": len(ids), "sha256": previous._sha256(scores)}
    return {"read_calibration_protocol_sha256": previous._sha256(source),
            "zero_shot_scores_checked": older, "prior_run_ids_reserved": len(seen)}


def _sample(seeds: tuple[int, ...], controls_only: bool, workers: int,
            seen: set[str], *, layout: str | None = None) -> dict[str, pd.DataFrame]:
    tasks = [(seed, job, False) for seed in seeds
             for job in read_round._jobs(seed, (read_round.CONFIRMATION_CHANNEL,))
             if not controls_only or job.condition.violation_size == 0]
    observed = _collect(tasks, workers) if layout is None else _collect(tasks, workers, layout=layout)
    populations = {name: observed[observed.population == name].sort_values(["grid", "run_id"])
                   .reset_index(drop=True) for name in POPULATIONS}
    native = populations["native"]
    identifiers = ["grid", "run_id", *LABEL_COLUMNS]
    if not native[identifiers].equals(populations["overlap"][identifiers]):
        raise ValueError("overlap and native views need identical run ids and strict labels")
    previous._reserve(pd.Index(native.run_id), seen)
    for seed in seeds:
        rows = native[native.grid == seed]
        positives = 0 if controls_only else previous.POSITIVES_PER_GRID
        small = 0 if controls_only else previous.IN_SCOPE_PER_GRID
        if (int((~rows.positive).sum()) != previous.CONTROLS_PER_GRID
                or int(rows.positive.sum()) != positives
                or int(rows.hard_control.sum()) != previous.IN_SCOPE_PER_GRID
                or int(rows.small_positive.sum()) != small):
            raise ValueError("native population differs from the strict preplanned design")
    return populations


def _write_table(path: Path, frame: pd.DataFrame) -> None:
    write_gzip(path, frame.to_csv(index=False, lineterminator="\n").encode("utf-8"))


def _scores(rows: pd.DataFrame, models: dict) -> dict[str, np.ndarray]:
    scores = {name: model.score(rows[list(model.columns)]) for name, model in models.items()}
    if not all(np.isfinite(values).all() for values in scores.values()):
        raise ValueError("the fitted models returned a nonfinite score")
    return scores


def _calibrate(path: Path, rows: pd.DataFrame, models: dict) -> dict[str, float]:
    if rows.positive.any():
        raise ValueError("workflow calibration accepts strict controls only")
    scores = _scores(rows, models)
    thresholds = {name: conformal_threshold(values, scope.MAX_FPR) for name, values in scores.items()}
    if not all(math.isfinite(value) for value in thresholds.values()):
        raise ValueError("workflow calibration needs finite cutoffs for both arms")
    _write_table(path / "calibration-controls.csv.gz", pd.concat([
        rows.assign(detector=name, score=values, threshold=thresholds[name])
        for name, values in scores.items()], ignore_index=True))
    return thresholds


def _support(frame: pd.DataFrame) -> dict:
    exercised = frame.exercised_overlap_pairs > 0
    return {
        **{name: int(frame[name].sum()) for name in AUDIT_COUNTS},
        "runs_with_competing_reads": int(frame.competing_reads.gt(0).sum()),
        "positives_exercising_competing_grants": int((frame.positive & exercised).sum()),
        "controls_exercising_competing_grants": int((~frame.positive & exercised).sum()),
        "runs_with_different_counts": int(frame[LEGACY_COLUMN].ne(frame[GRANT_COLUMN]).sum()),
    }


def _slices(rows: pd.DataFrame):
    yield "all", "all", rows
    for name in ("topology", "office_variant", "scope_mistake_rate"):
        for value, subset in rows.groupby(name, sort=True):
            yield name, str(value), subset


def _confirm(path: Path, rows: pd.DataFrame, models: dict, thresholds: dict,
             population: str, feature_varies: bool) -> dict:
    scores = _scores(rows, models)
    paired = pd.concat([rows.assign(detector=name, score=values, threshold=thresholds[name],
                                    task="scope", test_set="independent", split_seed=read_round.ARCHIVE_SEED)
                        for name, values in scores.items()], ignore_index=True)
    files, diagnostics = [], []
    for seed, grid in paired.groupby("grid", sort=True):
        dest = path / f"{seed}.csv.gz"
        _write_table(dest, grid)
        files.append(dest)
    for name, arm in paired.groupby("detector", sort=False):
        for grid, subset in [*arm.groupby("grid", sort=True), ("pooled", arm)]:
            for dimension, value, sample in _slices(subset):
                diagnostics.append(dict(grid=grid, detector=name, dimension=dimension, value=value,
                                        **previous._diagnose(sample, thresholds[name]), **_support(sample)))
    pd.DataFrame(diagnostics).to_csv(path / "diagnostics.csv", index=False, lineterminator="\n")
    card = benchmark_round(files, "scope", REFERENCE, CANDIDATE)
    card["source"] = card.source.replace({str(p): p.name for p in files})
    pooled = card.population == "pooled"
    paired_result = card.loc[pooled, "evidence"].item()
    support = _support(rows)
    overlap_observed = (support["positives_exercising_competing_grants"] > 0
                        and support["controls_exercising_competing_grants"] > 0)
    evidence = paired_result if feature_varies and overlap_observed else "insufficient_feature_support"
    if int(rows.small_positive.sum()) < MIN_ONE_FILE:
        evidence = "insufficient_data"
    if population == "native":
        evidence = "descriptive_transfer"
    card["round_evidence"] = ""
    card.loc[pooled, "round_evidence"] = evidence
    card.to_csv(path / "scorecard.csv", index=False, lineterminator="\n")
    return {"paired_evidence": paired_result, "round_evidence": evidence,
            "counts_toward_diminishing_returns": evidence == "below_minimum",
            "feature_varies_in_fit": feature_varies, "overlap_observed_in_both_classes": overlap_observed,
            "run_count": len(rows), "one_file_runs": int(rows.small_positive.sum()), **support}


def run_grant_round(out: Path, study: Path, data: Path, workers: int = 4, *,
                    previous_calibration: Path = Path("benchmarks/read-calibration")) -> None:
    """Publish paired native and overlap views of one held-out scope experiment."""
    out, study, data = Path(out), Path(study), Path(data)
    if type(workers) is not int or workers < 1:
        raise ValueError("workers must be a positive integer")
    if out.exists():
        raise ValueError(f"grant-round output already exists: {out}")
    seeds = (read_round.ARCHIVE_SEED, 20261123, 20261124, 20261125, *read_round.CONFIRMATION_SEEDS,
             *previous.CALIBRATION_SEEDS, *previous.CONFIRMATION_SEEDS, *CALIBRATION_SEEDS, *CONFIRMATION_SEEDS)
    if len(seeds) != len(set(seeds)):
        raise ValueError("the prior, calibration and confirmation grids need distinct seeds")
    out.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=out.parent) as temporary, _worker_threads():
        stage = Path(temporary) / "grant-round"
        stage.mkdir()
        models, fit, seen, provenance = _restore_fits(study, data, workers)
        prior = _reserve_previous(Path(previous_calibration), data, seen, provenance)
        _write_table(stage / "fitting.csv.gz", fit)
        controls = _sample(CALIBRATION_SEEDS, True, workers, seen)
        thresholds = {name: _calibrate(stage / name, controls[name], models) for name in POPULATIONS}
        # Both thresholds in both views are frozen before requesting confirmation data.
        confirmation = _sample(CONFIRMATION_SEEDS, False, workers, seen)
        varies = fit[GRANT_COLUMN].nunique() > 1
        decisions = {name: _confirm(stage / name, confirmation[name], models, thresholds[name], name, varies)
                     for name in POPULATIONS}
        n_cal = len(controls["native"])
        write_json(stage / "protocol.json", {
            "reference": REFERENCE, "candidate": CANDIDATE, "provenance": provenance,
            "prior_benchmarks": prior, "replaced_column": LEGACY_COLUMN, "replacement": GRANT_COLUMN,
            "input_columns": {name: list(model.columns) for name, model in models.items()},
            "fitting_runs": len(fit), "fitting_support": _support(fit),
            "calibration_seeds": list(CALIBRATION_SEEDS), "confirmation_seeds": list(CONFIRMATION_SEEDS),
            "calibration_controls_per_view": n_cal,
            "conformal_rank_one_based": math.ceil((n_cal + 1) * (1 - scope.MAX_FPR)),
            "thresholds": thresholds, "max_fpr": scope.MAX_FPR, "minimum_one_file_gain": 0.01,
            "minimum_one_file_runs": MIN_ONE_FILE, "cutoff_rule": "Strictly greater than the full-run control quantile.",
            "primary_population": "overlap", "native_population": "Paired native transfer check with shared run IDs.",
            "subgroups": "Control, sharing, case size and topology describe the original focal workflow.",
            "workflow": read_round.CONFIRMATION_CHANNEL, "scope_label": scope.STRICT,
            "fit": "Both 15-input logistic models use the archived fitting split and seed.",
            "competition": ("Successful simulated logins remain active throughout each run. At each "
                            "recorded read, count credential-compatible grants for the actor and host. "
                            "An exercised actor/host used at least two grant IDs while multiple grants were eligible."),
            "decisions": decisions,
        })
        stage.rename(out)
