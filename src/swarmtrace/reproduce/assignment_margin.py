"""Confirm assignment-local scores against the pre-sigmoid margins of the frozen whole-run fits."""

import hashlib
import json
from pathlib import Path
from shutil import copyfile
from tempfile import TemporaryDirectory

import numpy as np
import pandas as pd

from swarmtrace.detect.assignment import TEMPERATURE, AssignmentLogistic
from swarmtrace.eval.assignment_round import FAMILIES, report_assignment_round
from swarmtrace.eval.recorded import write_json
from swarmtrace.eval.scope import MAX_FPR
from swarmtrace.features.assignment import ASSIGNMENT_COLUMNS

from . import assignment_round as previous
from . import grant_policy, grant_round, read_calibration
from .scope import _worker_threads

REFERENCE = "logistic-margin"
VERIFIED_MARGIN = "logistic+verified-grant-margin"
CANDIDATE = previous.CANDIDATE
CONFIRMATION_SEEDS = tuple(range(20270121, 20270131))
CONTROL_COUNT = 1728
RANK = 1660
HISTORICAL_COUNT = 16200
ORIGINAL_TEST_COUNT = 3780
WHOLE_RUN = {previous.REFERENCE: REFERENCE, previous.VERIFIED: VERIFIED_MARGIN}
OLD_ARMS = (previous.REFERENCE, previous.VERIFIED, previous.POOLED, previous.SHARED_WEIGHTS, CANDIDATE)
MEMBERSHIP = ["grid", "family", *grant_round.LABEL_COLUMNS]
SCORE_TOLERANCE = 1e-12
# Published calibration only. Each digest covers the sorted IDs strictly above rank 1660,
# one ID per line including the trailing newline. No confirmation outcomes enter these checks.
_NATIVE_MARGIN_ALERTS = "0951fb7e1cd08fe5efc2bc49b1bac05652417f53674ce65ae4cc378963c5b7da"
MARGIN_CONTROL_ANCHORS = {
    "native": {REFERENCE: (1.5414546633478383, _NATIVE_MARGIN_ALERTS),
               VERIFIED_MARGIN: (1.477519040365805, _NATIVE_MARGIN_ALERTS)},
    "workflow": {
        REFERENCE: (57.58078938969106, "60016c2e4f4e7d7505728fd7dd7992a1f57265bfcd2e06e38d3a8fa5457e1ae4"),
        VERIFIED_MARGIN: (31.023514919995613, "48f348c1be6d651ec2fa201ebc97de750975ba8ff18665bf01e403e6379649d4"),
    },
}


def _restore_local(protocol):
    if (protocol["reference"] != previous.REFERENCE or protocol["candidate"] != CANDIDATE
            or protocol["primary_view"] != "workflow"
            or protocol["assignment_columns"] != list(ASSIGNMENT_COLUMNS)
            or protocol["model"]["temperature"] != TEMPERATURE
            or protocol["calibration_seeds"] != list(previous.CALIBRATION_SEEDS)
            or protocol["confirmation_seeds"] != list(previous.CONFIRMATION_SEEDS)
            or protocol["calibration_controls_per_view"] != CONTROL_COUNT
            or protocol["rank_one_based"] != RANK or grant_policy._tolerance_rank(CONTROL_COUNT) != RANK):
        raise ValueError("assignment study differs from the frozen model, calibration or confirmation plan")
    return AssignmentLogistic.from_parameters(protocol["model"], len(ASSIGNMENT_COLUMNS))


def _membership(rows, view, split):
    if (set(rows.detector) != set(OLD_ARMS) or rows.duplicated(["run_id", "detector"]).any()
            or not rows.run_id.str.fullmatch("[0-9a-f]{16}").all()
            or not rows.view.eq(view).all() or not rows.task.eq("scope").all()
            or not rows.test_set.eq(split).all()):
        raise ValueError("archived assignment runs need one record per expected detector, view and split")
    reference = rows.loc[rows.detector == previous.REFERENCE].set_index("run_id")[MEMBERSHIP].sort_index()
    for arm in OLD_ARMS:
        part = rows.loc[rows.detector == arm].set_index("run_id")[MEMBERSHIP].sort_index()
        if not reference.equals(part):
            raise ValueError("archived detector memberships, families or labels differ")
    return reference


def _check_population(membership, seeds, *, calibration):
    data = membership.copy()
    grant_policy._strict_bools(data)
    if set(data.grid) != {str(seed) for seed in seeds}:
        raise ValueError("archive contains a missing or unexpected grid")
    for index, grid in enumerate(seeds):
        group = data.loc[data.grid == str(grid)]
        family = FAMILIES[index % len(FAMILIES)]
        if (not group.family.eq(family).all()
                or int((~group.positive).sum()) != read_calibration.CONTROLS_PER_GRID
                or int(group.hard_control.sum()) != read_calibration.IN_SCOPE_PER_GRID
                or int(group.positive.sum()) != (0 if calibration else read_calibration.POSITIVES_PER_GRID)
                or int(group.small_positive.sum()) != (0 if calibration else read_calibration.IN_SCOPE_PER_GRID)):
            raise ValueError("archived grid differs from its planned family or run counts")


def _reserve_confirmation(study, seen, sources):
    parts = []
    columns = ["run_id", "detector", "view", "task", "test_set", *MEMBERSHIP]
    for seed in previous.CONFIRMATION_SEEDS:
        paired = []
        for view in previous.VIEWS:
            relative = f"{view}/{seed}.csv.gz"
            path = study / relative
            # Open only membership for this old confirmation, never its scores for calibration.
            rows = pd.read_csv(path, dtype=str, usecols=columns, keep_default_na=False)
            paired.append(_membership(rows, view, "independent"))
            if not paired[-1].grid.eq(str(seed)).all():
                raise ValueError("historical assignment file contains runs from another grid")
            sources[relative] = read_calibration._sha256(path)
        if not paired[0].equals(paired[1]):
            raise ValueError("previous assignment confirmation views use different underlying runs")
        parts.append(paired[0])
    all_runs = pd.concat(parts)
    _check_population(all_runs, previous.CONFIRMATION_SEEDS, calibration=False)
    read_calibration._reserve(all_runs.index, seen)


def _whole_scores(frame, models):
    scores = {}
    for arm, margin in WHOLE_RUN.items():
        model = models[arm]
        # pandas' default CSV float conversion can change a value by one ULP.
        inputs = grant_policy._features(frame, model.columns)
        scores[arm] = model.score(inputs)
        scores[margin] = model.score_margin(inputs)
    if not all(np.isfinite(values).all() for values in scores.values()):
        raise ValueError("whole-run fits returned nonfinite probabilities or margins")
    return scores


def _check_provenance(recorded, replay):
    # Every upstream hash, seed, population, alert count and diagnostic key must match.
    # The largest measured error against a prior grid depends on the numerical libraries.
    if replay["prior_score_error_tolerance"] != SCORE_TOLERANCE:
        raise ValueError("unexpected upstream score replay tolerance")

    def comparable(provenance):
        checks = {}
        for name, result in provenance["prior_parity"].items():
            difference = result["max_abs_score_error"]
            if not 0. <= difference <= SCORE_TOLERANCE:
                raise ValueError(f"upstream score error outside the historical tolerance for {name}")
            checks[name] = {key: value for key, value in result.items() if key != "max_abs_score_error"}
        return {**provenance, "prior_parity": checks}

    if comparable(recorded) != comparable(replay):
        raise ValueError("historical model, archive identity or operating decisions differ")


def _control_parity(scores, cutoffs, arms, old_cutoffs, ids, view):
    checks, numerical = {}, {}
    for arm, values in scores.items():
        effective = cutoffs[arm]
        flagged = values > effective
        if arm in arms:
            part = arms[arm]
            saved = part.score.map(float).to_numpy()
            canonical = old_cutoffs[arm]
            equal = int((saved == values).sum())
            maximum_error = float(np.abs(saved - values).max())
            if (not np.isfinite(maximum_error) or maximum_error > SCORE_TOLERANCE
                    or float(np.sort(saved)[RANK - 1]) != canonical
                    or not part.threshold.map(float).eq(canonical).all()
                    or not np.array_equal(flagged, saved > canonical)):
                raise ValueError(f"the archived {view} {arm} scores or strict control flags differ")
            checks[arm] = {"bitwise_equal_archived_scores": equal,
                           "scores_equal_one": int((values == 1.).sum())}
        else:
            canonical, digest = MARGIN_CONTROL_ANCHORS[view][arm]
            flagged_ids = ("\n".join(sorted(ids[flagged])) + "\n").encode("ascii")
            if hashlib.sha256(flagged_ids).hexdigest() != digest:
                raise ValueError(f"the {view} {arm} strict control IDs differ from the released margin")
            maximum_error = None
        if abs(effective - canonical) > SCORE_TOLERANCE:
            raise ValueError(f"the {view} {arm} rank cutoff exceeds the historical numerical tolerance")
        if effective != canonical or (arm in arms and maximum_error != 0.):
            numerical[arm] = {
                "published_cutoff": canonical, "platform_cutoff": effective,
                "strict_flags_matching": len(ids), "strict_alerts": int(flagged.sum()),
            }
            if maximum_error is not None:
                numerical[arm]["max_abs_score_error"] = maximum_error
    # A bit-identical replay preserves the original release packet. Record actual diagnostic
    # differences on other platforms without widening the strict alert comparison.
    if numerical:
        checks["numerical_replay"] = {"absolute_tolerance": SCORE_TOLERANCE, "arms": numerical}
    return checks


def _calibrate_view(study, stage, view, local, models, old_cutoffs, sources):
    scores_path = study / view / "calibration-controls.csv.gz"
    bags_path = study / view / "calibration-assignments.csv.gz"
    raw = pd.read_csv(scores_path, dtype=str, keep_default_na=False)
    members = _membership(raw, view, "calibration")
    _check_population(members, previous.CALIBRATION_SEEDS, calibration=True)
    if len(members) != CONTROL_COUNT:
        raise ValueError("expected exactly the original calibration controls")
    arms = {arm: raw.loc[raw.detector == arm].set_index("run_id").loc[members.index]
            for arm in (previous.REFERENCE, previous.VERIFIED, CANDIDATE)}
    base = arms[previous.REFERENCE]
    columns = list(dict.fromkeys(c for model in models.values() for c in model.columns))
    if not all(base[columns].equals(part[columns]) for part in arms.values()):
        raise ValueError("archived calibration arms have different whole-run inputs")
    scores = _whole_scores(base, models)
    bags = pd.read_csv(bags_path, dtype=str, keep_default_na=False)
    if (not set(bags.run_id) <= set(members.index) or bags.duplicated(["run_id", "grant_id"]).any()
            or bags.grant_id.eq("").any()):
        raise ValueError("unexpected or duplicate archived calibration assignments")
    grouped = grant_policy._features(bags, ASSIGNMENT_COLUMNS).groupby(bags.run_id, sort=False)
    counts = grouped.size().reindex(members.index, fill_value=0)
    if not np.array_equal(counts, base.assignment_count.map(int)):
        raise ValueError("published calibration assignment counts differ from the archived bags")
    scores[CANDIDATE] = grouped.apply(lambda x: local.score(x.to_numpy())).reindex(
        members.index, fill_value=0.).to_numpy(dtype=float)
    cutoffs = {arm: float(np.sort(values)[RANK - 1]) for arm, values in scores.items()}
    checks = _control_parity(scores, cutoffs, arms, old_cutoffs, members.index, view)
    folder = stage / view
    scored = pd.concat([base.reset_index().assign(detector=arm, score=values, threshold=cutoffs[arm])
                        for arm, values in scores.items()], ignore_index=True)
    grant_round._write_table(folder / "calibration-controls.csv.gz", scored)
    copyfile(bags_path, folder / bags_path.name)
    for path in (scores_path, bags_path):
        sources[path.relative_to(study).as_posix()] = read_calibration._sha256(path)
    return members, cutoffs, checks


def _prepare(study, benchmarks, stage):
    protocol = json.loads((study / "protocol.json").read_bytes())
    local = _restore_local(protocol)
    models, seen, provenance = previous._previous(benchmarks)
    _check_provenance(protocol["provenance"], provenance)
    if len(seen) != HISTORICAL_COUNT or protocol["cutoffs"]["workflow"][previous.REFERENCE] != 1.:
        raise ValueError("the restored historical models, IDs or incumbent threshold differ")
    sources = {"protocol.json": read_calibration._sha256(study / "protocol.json")}
    cutoffs, checks, members = {}, {}, {}
    for view in previous.VIEWS:
        members[view], cutoffs[view], checks[view] = _calibrate_view(
            study, stage, view, local, models, protocol["cutoffs"][view], sources)
    if not members["native"].equals(members["workflow"]):
        raise ValueError("calibration views have different underlying IDs or labels")
    read_calibration._reserve(members["workflow"].index, seen)
    _reserve_confirmation(study, seen, sources)
    if len(seen) != HISTORICAL_COUNT + CONTROL_COUNT + ORIGINAL_TEST_COUNT:
        raise ValueError("unexpected number of historical, calibration and previous confirmation IDs")
    calibration = {
        "reference": REFERENCE, "candidate": CANDIDATE, "primary_view": "workflow",
        "descriptive_comparators": [previous.REFERENCE, VERIFIED_MARGIN, previous.VERIFIED],
        "control_count_per_view": CONTROL_COUNT, "rank_one_based": RANK, "cutoffs": cutoffs,
        "assignment_model": protocol["model"], "assignment_columns": list(ASSIGNMENT_COLUMNS),
        "whole_run_inputs": {arm: list(models[arm].columns) for arm in WHOLE_RUN},
        "whole_run_probability_to_margin_arm": WHOLE_RUN, "original_score_replay": checks,
        "assignment_study_input_sha256": sources, "upstream": provenance,
        "history_counts": {"earlier": HISTORICAL_COUNT, "calibration": CONTROL_COUNT,
                           "first_confirmation": ORIGINAL_TEST_COUNT, "reserved_before_fresh": len(seen)},
        "calibration_seeds": list(previous.CALIBRATION_SEEDS),
        "first_confirmation_seeds": list(previous.CONFIRMATION_SEEDS),
        "confirmation_seeds": list(CONFIRMATION_SEEDS),
        "family_by_grid": {str(seed): FAMILIES[index % 2] for index, seed in enumerate(CONFIRMATION_SEEDS)},
        "comparison": "Each score strictly exceeds its own frozen cutoff to flag. Full-run thresholds.",
    }
    write_json(stage / "calibration.json", calibration)
    return models, local, seen, calibration


def _operating_points(frame, scores, cutoffs):
    results = []
    for family in (*FAMILIES, "pooled"):
        mask = np.ones(len(frame), dtype=bool) if family == "pooled" else frame.family.eq(family).to_numpy()
        subset = frame.loc[mask]
        positive, small, hard = (subset[col].to_numpy(dtype=bool)
                                 for col in ("positive", "small_positive", "hard_control"))
        controls = int((~positive).sum())
        for arm, values in scores.items():
            flags = values[mask] > cutoffs[arm]
            fp = int((flags & ~positive).sum())
            upper = grant_policy._upper_fpr(fp, controls) if controls else None
            results.append(dict(family=family, detector=arm, controls=controls, positives=int(positive.sum()),
                                true_positives=int((flags & positive).sum()), false_positives=fp,
                                one_file_runs=int(small.sum()), one_file_detections=int((flags & small).sum()),
                                hard_controls=int(hard.sum()), hard_false_positives=int((flags & hard).sum()),
                                threshold=cutoffs[arm], exact_fpr_upper=upper,
                                exact_fpr_bound_met=upper is not None and upper <= MAX_FPR))
    return pd.DataFrame(results)


def run_assignment_margin(study: Path, benchmarks: Path, out: Path, workers: int = 4) -> None:
    """Freeze the original control order statistic before opening ten unseen full-run grids."""
    if type(workers) is not int or workers < 1 or out.exists():
        raise ValueError("assignment margin confirmation needs a positive worker count and a new output directory")
    out.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=out.parent) as temporary, _worker_threads():
        stage = Path(temporary) / "study"
        stage.mkdir()
        models, local, seen, calibration = _prepare(study, benchmarks, stage)
        confirmation = previous._sample(CONFIRMATION_SEEDS, False, workers, seen)
        decisions = {}
        for view in previous.VIEWS:
            samples = confirmation[view]
            frame = previous._frame(samples)
            if (len(frame) != ORIGINAL_TEST_COUNT or not frame.run_id.is_unique
                    or frame.family.tolist() != [calibration["family_by_grid"][str(k)] for k in frame.grid]):
                raise ValueError("fresh confirmation requires complete grids with the planned alternating families")
            scores = _whole_scores(frame, models)
            scores[CANDIDATE] = np.array([local.score(sample.bag) for sample in samples])
            cutoffs = calibration["cutoffs"][view]
            folder = stage / view
            files = previous._export(folder, samples, scores, cutoffs, calibration=False)
            decisions[view] = report_assignment_round(
                folder, files, candidate=CANDIDATE, reference=REFERENCE,
                alternatives=(previous.REFERENCE, VERIFIED_MARGIN, previous.VERIFIED), primary=view == "workflow")
            _operating_points(frame, scores, cutoffs).to_csv(folder / "operating-points.csv", index=False,
                                                             lineterminator="\n")
        if len(seen) != calibration["history_counts"]["reserved_before_fresh"] + ORIGINAL_TEST_COUNT:
            raise ValueError("fresh underlying IDs did not extend the disjoint history")
        write_json(stage / "protocol.json", {**calibration, "decisions": decisions,
                                             "unique_ids_including_confirmation": len(seen)})
        stage.rename(out)
