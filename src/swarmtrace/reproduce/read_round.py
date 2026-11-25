"""Held-out scope comparison using trusted read decisions and one second-reader feature."""

import math
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from swarmtrace.detect import RunDetector
from swarmtrace.eval import scope
from swarmtrace.eval.data import RunRecord
from swarmtrace.eval.harness import child_seed
from swarmtrace.eval.metrics import ratio
from swarmtrace.eval.recorded import TableRecord, write_gzip, write_json
from swarmtrace.features import feature_columns, run_features
from swarmtrace.features.read_evidence import corroborated_file_count, read_evidence
from swarmtrace.features.spec import AGGREGATION, SCOPE
from swarmtrace.sim.runner import build_run, run_one
from swarmtrace.trace.authorization import read_authorization
from swarmtrace.trace.context import ContextLevel, read_context
from swarmtrace.trace.io import RunPaths, read_labels, read_manifest, read_trace
from swarmtrace.trace.tiers import Tier

from .config import RunJob
from .scope import ScopeConfig, _map, _worker_threads, make_scope_jobs

ARCHIVE_SEED = 20261120
CONFIRMATION_SEEDS = (20261126, 20261127)
DEVELOPMENT_CHANNELS = ("message", "shared_file")
CONFIRMATION_CHANNEL = "preplanned"
REFERENCE = "logistic"
CANDIDATE = "logistic+second-reader"
SECOND_READER = "corroborated_out_of_scope_files"
BASE_COLUMNS = feature_columns("run", Tier.V1, (AGGREGATION, SCOPE), context=ContextLevel.C2)
CHECKPOINT_INTERVAL = 8
READ_COUNTS = ("successful_reads", "grant_reads", "ordinary_reads", "unknown_reads",
               "missing_decisions", "confirmed_out_of_scope_reads")


@dataclass(frozen=True)
class _ObservedRun:
    record: TableRecord
    features: pd.DataFrame
    objective_tick: int | None
    counts: dict[str, int]
    preplanned_background: bool


def _ticks(last: int) -> tuple[int, ...]:
    """Inclusive end-of-tick prefixes from zero, always including the terminal tick once."""
    return (*range(0, last, CHECKPOINT_INTERVAL), last)


def _jobs(seed: int, channels: Collection[str]) -> list[RunJob]:
    # Preserve the published (95, i) simulation streams by filtering after enumeration.
    return [job for job in make_scope_jobs(ScopeConfig(seed=seed))
            if job.condition.channel in channels]


def _observe(task: tuple[RunJob, bool]) -> _ObservedRun | None:
    job, development = task
    setup = build_run(job.condition, job.seed)
    background = any(group.channel == CONFIRMATION_CHANNEL
                     for index, group in enumerate(setup.groups) if index != setup.focal_group)
    if development and (background or job.condition.channel not in DEVELOPMENT_CHANNELS):
        return None
    if not development and job.condition.channel != CONFIRMATION_CHANNEL:
        raise ValueError("confirmation requires the held-out focal channel")
    with TemporaryDirectory() as temporary:
        paths = RunPaths(run_one(job.condition, job.seed, temporary, capture_authorization=True))
        trace = read_trace(paths.trace, Tier.V1)
        context = read_context(paths.context)
        audit = read_authorization(paths.authorization)
        reads = read_evidence(trace, audit)
        last = job.condition.n_ticks - 1
        ticks = (last,) if development else _ticks(last)
        values = []
        for tick in ticks:
            # The terminal row uses the native full-trace calculation.
            horizon = None if tick == last else tick
            frame = run_features(trace, until_tick=horizon, context=context)
            row = frame.loc[trace.run_id, list(BASE_COLUMNS)].to_dict()
            row[SECOND_READER] = corroborated_file_count(reads, until_tick=horizon)
            values.append(row)
        features = pd.DataFrame(values, index=pd.Index(ticks, name="tick"))
        counts = {
            "successful_reads": len(reads), "grant_reads": sum(r.basis == "grant" for r in reads),
            "ordinary_reads": sum(r.basis == "ordinary" for r in reads),
            "unknown_reads": sum(r.basis == "unknown" for r in reads),
            "missing_decisions": len(reads) - len(audit.decisions),
            "confirmed_out_of_scope_reads": sum(r.out_of_scope is True for r in reads),
        }
        # Outcomes and experiment factors only enter the evaluation metadata.
        labels, manifest = read_labels(paths.labels), read_manifest(paths.manifest)
        if not trace.run_id == labels.run_id == manifest.run_id:
            raise ValueError("scope-round input run ids do not match")
        record = RunRecord(trace.run_id, paths.trace, labels, manifest.condition)
        return _ObservedRun(TableRecord(record.run_id, record.positive, record.condition),
                            features, labels.objective_tick, counts, background)


def _fit(runs: Sequence[_ObservedRun]) -> tuple[dict[str, RunDetector], dict]:
    records = [r.record for r in runs]
    if any(r.preplanned_background or r.record.condition["channel"] not in DEVELOPMENT_CHANNELS
           for r in runs):
        raise ValueError("a held-out workflow cannot enter fitting or calibration")
    split = scope.scope_split(records, ARCHIVE_SEED)
    full = pd.DataFrame([r.features.iloc[-1] for r in runs],
                        index=pd.Index([r.run_id for r in records], name="run_id"))
    labels = pd.Series(scope.labels_for(records, scope.STRICT), dtype=bool)
    fit, calibration = full.loc[list(split.fitting)], full.loc[list(split.calibration)]
    seed = child_seed(ARCHIVE_SEED, scope.SEED_KEY, 2, scope.CONTEXTS.index("C2"),
                      scope.SCOPE_DETECTORS.index("logistic"))
    # Scaling a constant fitting column produces zeros and logistic learns a zero coefficient.
    # Omitting it here preserves exact ties, including when a later workflow has nonzero evidence.
    constant = fit[SECOND_READER].nunique() == 1
    candidate_columns = list(BASE_COLUMNS) if constant else [*BASE_COLUMNS, SECOND_READER]
    models = {}
    for name, columns in ((REFERENCE, list(BASE_COLUMNS)), (CANDIDATE, candidate_columns)):
        model = RunDetector("logistic", seed, scope.MAX_FPR)
        model.fit(fit[columns], labels.loc[fit.index].to_numpy())
        model.calibrate(calibration[columns], labels.loc[calibration.index].to_numpy())
        if not math.isfinite(model.threshold):
            raise ValueError("the development calibration set did not yield a finite cutoff")
        models[name] = model
    partitions = {}
    for name, ids in (("fitting", split.fitting), ("calibration", split.calibration),
                      ("unused", split.test)):
        subset = full.loc[list(ids)]
        positive = labels.loc[subset.index]
        nonzero = subset[SECOND_READER] > 0
        partitions[name] = {
            "run_ids": list(ids), "positives": int(positive.sum()),
            "controls": int((~positive).sum()),
            "positive_with_signal": int((positive & nonzero).sum()),
            "controls_with_signal": int((~positive & nonzero).sum()),
        }
    fit_details = {
        "partitions": partitions, "fit_seed": seed, "constant_added_column": bool(constant),
        "feature_varies_in_fit": not constant,
        "input_columns": {name: list(model.columns) for name, model in models.items()},
        "thresholds": {name: model.threshold for name, model in models.items()},
    }
    return models, fit_details


def _score(runs: Sequence[_ObservedRun], models: dict[str, RunDetector]) -> pd.DataFrame:
    records = [r.record for r in runs]
    positives = scope.labels_for(records, scope.STRICT)
    entries = []
    for run in runs:
        record, condition = run.record, run.record.condition
        positive = positives[record.run_id]
        entries.append({
            "run_id": record.run_id, "positive": positive,
            "hard_control": scope.run_kind(record) == scope.IN_SCOPE,
            "small_positive": positive and condition["violation_size"] == 1,
            "two_agent_positive": positive and condition["offensive_group_size"] == 2,
            "sharing_control": not record.positive and condition["benign_sharing_teams"] > 0,
            "channel": condition["channel"], "topology": condition["topology"],
            "scope_mistake_rate": condition["scope_mistake_rate"],
            "preplanned_background": run.preplanned_background, "objective_tick": run.objective_tick,
            SECOND_READER: int(run.features[SECOND_READER].iloc[-1]), **run.counts,
        })
    metadata = pd.DataFrame(entries).set_index("run_id").sort_index()
    metadata["objective_tick"] = metadata.objective_tick.astype("Int64")
    frames = pd.concat({r.record.run_id: r.features for r in runs}, names=["run_id"])
    results = []
    for name, model in models.items():
        scores = pd.Series(model.score(frames[list(model.columns)]), index=frames.index)
        crossings = scores[scores > model.threshold].index.to_frame(index=False)
        first = crossings.groupby("run_id").tick.min().reindex(metadata.index).astype("Int64")
        results.append(metadata.assign(
            task="scope", test_set="independent", split_seed=ARCHIVE_SEED, detector=name,
            score=scores.groupby(level="run_id").last(), threshold=model.threshold,
            first_alert_tick=first,
        ).reset_index())
    return pd.concat(results, ignore_index=True)


def _diagnose(scores: pd.DataFrame) -> dict:
    positive = scores.positive
    controls = ~positive
    full_alert = scores.score > scores.threshold
    any_alert = scores.first_alert_tick.notna()
    timed = scores.objective_tick.gt(0).fillna(False)
    before = scores.first_alert_tick.lt(scores.objective_tick).fillna(False)
    at = scores.first_alert_tick.eq(scores.objective_tick).fillna(False)
    outside = scores.confirmed_out_of_scope_reads.gt(0)
    signal = scores[SECOND_READER].gt(0)
    result = {
        "runs": len(scores), "positives": int(positive.sum()), "controls": int(controls.sum()),
        "true_positives": int((positive & full_alert).sum()),
        "false_positives": int((controls & full_alert).sum()),
        "positive_with_signal": int((positive & signal).sum()),
        "controls_with_signal": int((controls & signal).sum()),
        "positive_with_confirmed_outside": int((positive & outside).sum()),
        "controls_with_confirmed_outside": int((controls & outside).sum()),
        "preplanned_background_runs": int(scores.preplanned_background.sum()),
        **{name: int(scores[name].sum()) for name in READ_COUNTS},
    }
    for name, mask in (
        ("one_file", scores.small_positive), ("two_agent", scores.two_agent_positive),
        ("in_scope_relay", scores.hard_control), ("benign_sharing", scores.sharing_control),
    ):
        hits, count = int((mask & full_alert).sum()), int(mask.sum())
        result.update({f"{name}_runs": count, f"{name}_flagged": hits,
                       f"{name}_flag_rate": ratio(hits, count)})
    for name, mask in (("positive", positive), ("control", controls)):
        eligible = mask & timed
        missing = mask & scores.objective_tick.isna()
        early, completed = int((eligible & before).sum()), int(eligible.sum())
        result.update({
            f"{name}_with_objective_after_zero": completed,
            f"{name}_without_objective": int(missing.sum()),
            f"{name}_with_tick_zero_objective": int((mask & scores.objective_tick.eq(0)).sum()),
            f"{name}_alert_without_objective": int((missing & any_alert).sum()),
            f"{name}_any_checkpoint_alert": int((mask & any_alert).sum()),
            f"{name}_any_checkpoint_alert_rate": ratio(
                int((mask & any_alert).sum()), int(mask.sum())),
            f"{name}_strictly_before_objective": early,
            f"{name}_strictly_before_rate": ratio(early, completed),
            f"{name}_first_alert_at_objective": int((eligible & at).sum()),
        })
    return result


def run_read_round(out: Path, workers: int = 4) -> None:
    """Fit on recorded simulator families and score two disjoint focal preplanned grids."""
    out = Path(out)
    if type(workers) is not int or workers < 1:
        raise ValueError("workers must be a positive integer")
    if out.exists():
        raise ValueError(f"read round output already exists: {out}")
    out.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=out.parent) as temporary, _worker_threads():
        stage = Path(temporary) / "round"
        stage.mkdir()
        jobs = _jobs(ARCHIVE_SEED, DEVELOPMENT_CHANNELS)
        observed = _map(_observe, [(job, True) for job in jobs], workers)
        development = [run for run in observed if run is not None]
        models, details = _fit(development)
        seen = {r.record.run_id for r in development}
        grids = {}
        for seed in CONFIRMATION_SEEDS:
            jobs_test = _jobs(seed, (CONFIRMATION_CHANNEL,))
            runs = _map(_observe, [(job, False) for job in jobs_test], workers)
            ids = {r.record.run_id for r in runs}
            if len(ids) != len(runs) or ids & seen:
                raise ValueError("development and confirmation need disjoint, unique run ids")
            seen.update(ids)
            scores = _score(runs, models)
            grids[str(seed)] = scores
            content = scores.to_csv(index=False, lineterminator="\n").encode("utf-8")
            write_gzip(stage / f"{seed}.csv.gz", content)
        pooled = pd.concat(grids.values(), ignore_index=True)
        rows = []
        for grid, scores in [*grids.items(), ("pooled", pooled)]:
            for detector, frame in scores.groupby("detector", sort=False):
                for topology, subset in [("all", frame), *frame.groupby("topology", sort=True)]:
                    rows.append(dict(grid=grid, topology=topology, detector=detector,
                                     **_diagnose(subset)))
        pd.DataFrame(rows).to_csv(stage / "diagnostics.csv", index=False, lineterminator="\n")
        write_json(stage / "protocol.json", {
            "archive_seed": ARCHIVE_SEED, "confirmation_seeds": list(CONFIRMATION_SEEDS),
            "development_channels_all_groups": list(DEVELOPMENT_CHANNELS),
            "confirmation_focal_channel": CONFIRMATION_CHANNEL,
            "confirmation_nonzero_runs": int(
                pooled.loc[pooled.detector == REFERENCE, SECOND_READER].gt(0).sum()),
            "development_focal_eligible": len(jobs),
            "excluded_development_preplanned_background": len(jobs) - len(development),
            "development_eligible": len(development), **details,
            "reference": REFERENCE, "candidate": CANDIDATE, "added_feature": SECOND_READER,
            "scope_label": "strict", "max_fpr": scope.MAX_FPR, "minimum_one_file_recall_gain": 0.01,
            "checkpoints": list(_ticks(ScopeConfig().n_ticks - 1)),
            "timing_threshold": "frozen full-trace calibration applied to inclusive prefixes",
            "objective": ("Referee end-of-tick completion of the full snapshot, relay and "
                          "applicable scope requirements"),
            "outputs": {"scores": {str(seed): f"{seed}.csv.gz" for seed in CONFIRMATION_SEEDS},
                        "diagnostics": "diagnostics.csv"},
        })
        stage.rename(out)
