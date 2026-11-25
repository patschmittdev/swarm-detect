"""Confirm two full-trace operating points for one frozen scope classifier."""

import hashlib
import json
import math
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import pandas as pd

from swarmtrace.detect import RunDetector, conformal_threshold
from swarmtrace.eval import scope
from swarmtrace.eval.comparison import _cohort
from swarmtrace.eval.harness import child_seed
from swarmtrace.eval.metrics import ratio, wilson
from swarmtrace.eval.recorded import RunTable, load_run_table, write_gzip, write_json

from . import read_round
from .accuracy_holdout import _holdout_row
from .scope import _map, _worker_threads

CALIBRATION_SEEDS = (20261128, 20261129, 20261130)
CONFIRMATION_SEEDS = (20261201, 20261202)
REFERENCE = read_round.REFERENCE
CANDIDATE = "logistic+recalibrated"
CONTROLS_PER_GRID = 216
POSITIVES_PER_GRID = 162
IN_SCOPE_PER_GRID = 54


def _reserve(ids: pd.Index, seen: set[str]) -> None:
    if not ids.is_unique or seen.intersection(ids):
        raise ValueError("archive, prior confirmation, calibration and test runs need disjoint ids")
    seen.update(ids)


def _sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _restore(study: Path, data: Path) -> tuple[RunDetector, float, set[str], dict]:
    """Restore the restricted fit and reproduce its original calibration before seeing new data."""
    workflow = study / "workflow"
    source = workflow / "protocol.json"
    protocol = json.loads(source.read_text(encoding="utf-8"))
    archive = data / "scope" / "runs.csv.gz"
    fit_seed = child_seed(read_round.ARCHIVE_SEED, scope.SEED_KEY, 2, scope.CONTEXTS.index("C2"),
                          scope.SCOPE_DETECTORS.index(REFERENCE))
    settings = {
        "archive_seed": read_round.ARCHIVE_SEED, "fit_seed": fit_seed, "reference": REFERENCE,
        "scope_label": scope.STRICT, "max_fpr": scope.MAX_FPR,
        "development_channels_all_groups": list(read_round.DEVELOPMENT_CHANNELS),
        "confirmation_focal_channel": read_round.CONFIRMATION_CHANNEL,
        "confirmation_seeds": list(read_round.CONFIRMATION_SEEDS),
    }
    if any(protocol.get(key) != value for key, value in settings.items()):
        raise ValueError("prior protocol differs from the frozen strict-scope logistic design")
    columns = protocol["input_columns"][REFERENCE]
    table = load_run_table(archive)
    cohort = _cohort(table, "scope")
    if columns != list(read_round.BASE_COLUMNS) or columns != list(cohort.features):
        raise ValueError("archive and prior protocol must have the same ordered C2 inputs")
    partitions = protocol["partitions"]
    recorded = [run for name in ("fitting", "calibration", "unused")
                for run in partitions[name]["run_ids"]]
    ids = set(recorded)
    if (len(ids) != len(recorded) or len(ids) != protocol["development_eligible"]
            or not ids.issubset(cohort.features.index)):
        raise ValueError("prior development ids are missing, duplicated, or outside the archive")
    eligible = [record for record in table.records if record.run_id in ids]
    if any(r.condition["channel"] not in read_round.DEVELOPMENT_CHANNELS for r in eligible):
        raise ValueError("prior development contains a held-out focal channel")
    split = scope.scope_split(eligible, read_round.ARCHIVE_SEED)
    for name, subset in (("fitting", split.fitting), ("calibration", split.calibration),
                         ("unused", split.test)):
        entry = partitions[name]
        positive = int(cohort.truth.loc[list(subset), "positive"].sum())
        if (list(subset) != entry["run_ids"] or positive != entry["positives"]
                or len(subset) - positive != entry["controls"]):
            raise ValueError(f"archived {name} ids or strict labels differ from the prior study")
    fit, old_cal = cohort.select(split.fitting), cohort.select(split.calibration)
    model = RunDetector(REFERENCE, fit_seed, scope.MAX_FPR)
    model.fit(fit.features, fit.truth.positive.to_numpy())
    model.calibrate(old_cal.features, old_cal.truth.positive.to_numpy())
    published = float(protocol["thresholds"][REFERENCE])
    if not math.isfinite(published) or not math.isclose(
        model.threshold, published, rel_tol=0.0, abs_tol=1e-12
    ):
        raise ValueError("restored logistic cutoff differs from the prior full-trace cutoff")

    seen = set(cohort.features.index)
    prior_tests = {}
    for seed in read_round.CONFIRMATION_SEEDS:
        scores_path = workflow / protocol["outputs"]["scores"][str(seed)]
        rows = pd.read_csv(scores_path, usecols=["run_id", "detector", "threshold", "split_seed"],
                           dtype={"run_id": str, "threshold": str})
        counts = rows.groupby("run_id").detector.agg(list)
        expected = {REFERENCE, protocol["candidate"]}
        if (len(counts) != CONTROLS_PER_GRID + POSITIVES_PER_GRID
                or not all(len(names) == 2 and set(names) == expected for names in counts)
                or not rows.split_seed.eq(read_round.ARCHIVE_SEED).all()
                or not rows.loc[rows.detector == REFERENCE, "threshold"].map(float).eq(published).all()):
            raise ValueError("previous confirmation scores do not match the frozen protocol")
        _reserve(counts.index, seen)
        prior_tests[str(seed)] = {"run_ids": counts.index.tolist(), "sha256": _sha256(scores_path)}
    provenance = {
        **settings, "protocol_sha256": _sha256(source), "archive_table_sha256": _sha256(archive),
        "input_columns": columns,
        "partitions": {name: {key: entry[key] for key in ("run_ids", "positives", "controls")}
                       for name, entry in partitions.items()},
        "original_confirmation": prior_tests, "published_threshold": published,
        "reproduced_threshold": model.threshold, "absolute_tolerance": 1e-12,
    }
    return model, published, seen, provenance


def _sample(seed: int, controls_only: bool, workers: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    jobs = read_round._jobs(seed, (read_round.CONFIRMATION_CHANNEL,))
    if controls_only:
        jobs = [job for job in jobs if job.condition.violation_size == 0]
    rows = _map(_holdout_row, jobs, workers)
    frames, records = zip(*rows, strict=True)
    if any(record.condition["channel"] != read_round.CONFIRMATION_CHANNEL for record in records):
        raise ValueError("calibration follow-up requires focal preplanned workflows")
    cohort = _cohort(RunTable(pd.concat(frames), records), "scope")
    truth = cohort.truth.assign(
        two_agent_positive=cohort.truth.positive & np.array([
            r.condition["offensive_group_size"] == 2 for r in records], dtype=bool),
        sharing_control=[not r.positive and r.condition["benign_sharing_teams"] > 0
                         for r in records],
        topology=[r.condition["topology"] for r in records],
        scope_mistake_rate=[r.condition["scope_mistake_rate"] for r in records],
    )
    return cohort.features.sort_index(), truth.sort_index()


def _score_sample(model: RunDetector, seed: int, controls_only: bool, workers: int,
                  seen: set[str]) -> pd.DataFrame:
    features, truth = _sample(seed, controls_only, workers)
    if not features.index.equals(truth.index) or tuple(features.columns) != model.columns:
        raise ValueError("run ids and ordered classifier inputs must match")
    _reserve(features.index, seen)
    if (int((~truth.positive).sum()) != CONTROLS_PER_GRID
            or int(truth.positive.sum()) != (0 if controls_only else POSITIVES_PER_GRID)
            or int(truth.hard_control.sum()) != IN_SCOPE_PER_GRID
            or (truth.positive & (truth.hard_control | truth.sharing_control)).any()):
        raise ValueError("wrong positive or control composition for the frozen preplanned grid")
    scores = model.score(features)
    if not np.isfinite(scores).all():
        raise ValueError("the frozen model returned a nonfinite score")
    return truth.assign(grid=seed, score=scores).reset_index()


def _sample_details(frame: pd.DataFrame) -> dict:
    return {"run_ids": frame.run_id.tolist(), "positives": int(frame.positive.sum()),
            "controls": int((~frame.positive).sum()), "in_scope_relays": int(frame.hard_control.sum()),
            "benign_controls": int((~frame.positive & ~frame.hard_control).sum()),
            "benign_sharing": int(frame.sharing_control.sum())}


def _diagnose(frame: pd.DataFrame, threshold: float) -> dict:
    flagged, positive = frame.score > threshold, frame.positive
    tp, fp = int((flagged & positive).sum()), int((flagged & ~positive).sum())
    positives, controls = int(positive.sum()), int((~positive).sum())
    fpr = wilson(fp, controls)
    result = {
        "threshold": threshold, "runs": len(frame), "reviews": int(flagged.sum()),
        "positives": positives, "controls": controls, "true_positives": tp, "false_positives": fp,
        "false_negatives": positives - tp, "true_negatives": controls - fp,
        "recall": ratio(tp, positives), "fpr": fpr.value,
        "fpr_wilson_low": fpr.low, "fpr_wilson_high": fpr.high,
    }
    for name, mask in (("one_file", frame.small_positive), ("two_agent", frame.two_agent_positive),
                       ("in_scope_relay", frame.hard_control), ("benign_sharing", frame.sharing_control)):
        flagged_count, count = int((flagged & mask).sum()), int(mask.sum())
        result.update({f"{name}_flagged": flagged_count, f"{name}_runs": count,
                       f"{name}_flag_rate": ratio(flagged_count, count)})
    return result


def _decision(frame: pd.DataFrame, old: float, new: float) -> dict:
    old_flags, new_flags = frame.score > old, frame.score > new
    lost, gained = old_flags & ~new_flags, new_flags & ~old_flags
    pos = frame.positive
    controls = int((~pos).sum())
    return {
        "old_observed_within_budget": int((old_flags & ~pos).sum()) <= controls * scope.MAX_FPR,
        "recalibrated_observed_within_budget": int((new_flags & ~pos).sum()) <= controls * scope.MAX_FPR,
        "false_alerts_avoided": int((lost & ~pos).sum()),
        "false_alerts_added": int((gained & ~pos).sum()),
        "newly_missed_violations": int((lost & pos).sum()),
        "recovered_violations": int((gained & pos).sum()),
        "reviews_saved": int(old_flags.sum() - new_flags.sum()),
        "same_scores_and_ranking": True, "counts_toward_diminishing_returns": False,
    }


def run_read_calibration(out: Path, study: Path, data: Path, workers: int = 4) -> None:
    """Freeze one new cutoff on strict controls and compare it on fresh full preplanned grids."""
    out = Path(out)
    if type(workers) is not int or workers < 1:
        raise ValueError("workers must be a positive integer")
    if out.exists():
        raise ValueError(f"calibration study output already exists: {out}")
    seeds = (read_round.ARCHIVE_SEED, *read_round.CONFIRMATION_SEEDS,
             *CALIBRATION_SEEDS, *CONFIRMATION_SEEDS)
    if len(set(seeds)) != len(seeds):
        raise ValueError("calibration, confirmation and prior seeds must be disjoint")
    out.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=out.parent) as temporary, _worker_threads():
        stage = Path(temporary) / "calibration"
        stage.mkdir()
        model, old, seen, provenance = _restore(Path(study), Path(data))
        samples: dict[str, dict] = {"calibration": {}, "confirmation": {}}
        calibration = []
        for seed in CALIBRATION_SEEDS:
            frame = _score_sample(model, seed, True, workers, seen)
            samples["calibration"][str(seed)] = _sample_details(frame)
            calibration.append(frame)
        controls = pd.concat(calibration, ignore_index=True)
        n = len(controls)
        rank = math.ceil((n + 1) * (1.0 - scope.MAX_FPR))
        new = conformal_threshold(controls.score.to_numpy(), scope.MAX_FPR)
        thresholds = {REFERENCE: old, CANDIDATE: new}
        write_gzip(stage / "calibration-controls.csv.gz", controls.to_csv(
            index=False, lineterminator="\n").encode("utf-8"))

        tests = {}
        for seed in CONFIRMATION_SEEDS:
            frame = _score_sample(model, seed, False, workers, seen)
            samples["confirmation"][str(seed)] = _sample_details(frame)
            tests[str(seed)] = frame
            paired = pd.concat([
                frame.assign(detector=detector, threshold=cutoff, task="scope",
                             test_set="independent", split_seed=read_round.ARCHIVE_SEED)
                for detector, cutoff in thresholds.items()
            ], ignore_index=True)
            write_gzip(stage / f"{seed}.csv.gz", paired.to_csv(
                index=False, lineterminator="\n").encode("utf-8"))
        pooled = pd.concat(tests.values(), ignore_index=True)
        diagnostics = [
            dict(grid=grid, detector=detector, **_diagnose(frame, threshold))
            for grid, frame in [*tests.items(), ("pooled", pooled)]
            for detector, threshold in thresholds.items()
        ]
        pd.DataFrame(diagnostics).to_csv(stage / "diagnostics.csv", index=False, lineterminator="\n")
        write_json(stage / "protocol.json", {
            "reference": REFERENCE, "candidate": CANDIDATE, "provenance": provenance,
            "calibration_seeds": list(CALIBRATION_SEEDS), "confirmation_seeds": list(CONFIRMATION_SEEDS),
            "focal_channel": read_round.CONFIRMATION_CHANNEL, "scope_label": scope.STRICT,
            "max_fpr": scope.MAX_FPR, "thresholds": thresholds, "samples": samples,
            "calibration_controls": n, "conformal_rank_one_based": rank,
            "cutoff_rule": ("Use the ceil((n+1)*(1-alpha))-th smallest full-trace control score. "
                            "Alert when score > threshold."),
            "operating_point_decision": "Observed pooled confirmation false-positive rate <= 5%",
            "fpr_interval": "Two-sided 95% Wilson score interval over confirmation controls",
            "decision": _decision(pooled, old, new),
            "outputs": {"scores": {seed: f"{seed}.csv.gz" for seed in tests},
                        "calibration_scores": "calibration-controls.csv.gz", "diagnostics": "diagnostics.csv"},
        })
        stage.rename(out)
