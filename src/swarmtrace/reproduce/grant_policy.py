"""Confirm two frozen logistic fits with stricter false-alert control and observed routing."""

import json
import math
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import pandas as pd

from swarmtrace.detect import RunDetector
from swarmtrace.eval import scope
from swarmtrace.eval.recorded import write_json
from swarmtrace.eval.rounds import benchmark_round

from . import grant_round as prior_round
from . import read_calibration as previous
from . import read_round
from .scope import _worker_threads

REFERENCE = prior_round.REFERENCE
CANDIDATE = "logistic+routed-verified-grant"
CALIBRATION_SEEDS = tuple(range(20261216, 20261222))
CONFIRMATION_SEEDS = tuple(range(20261222, 20261232))
LAYOUT = "same_issuer"
ARM_ERROR = .025
UPPER_ERROR = .05
BOOL_COLUMNS = prior_round.LABEL_COLUMNS[:5]


def _binomial_cdf(x: int, n: int, p: float) -> float:
    if x < 0:
        return 0.
    if x >= n or p == 0:
        return 1.
    if p == 1:
        return 0.
    if x > n * p:
        return 1. - _binomial_cdf(n - x - 1, n, 1. - p)
    # Work from the largest included mass downwards. This avoids underflow
    # at the origin when inverting the CDF for a large confirmation set.
    log_mass = (math.lgamma(n + 1) - math.lgamma(x + 1) - math.lgamma(n - x + 1)
                + x * math.log(p) + (n - x) * math.log1p(-p))
    mass = math.exp(log_mass)
    terms = [mass]
    for i in range(x, 0, -1):
        mass *= i / (n - i + 1) * ((1 - p) / p)
        terms.append(mass)
    return min(1., math.fsum(terms))


def _tolerance_rank(n: int) -> int:
    """Smallest ordinal whose null binomial upper tail is within the per-arm error."""
    low, high = 1, n + 1
    while low < high:
        mid = (low + high) // 2
        if _binomial_cdf(n - mid, n, scope.MAX_FPR) <= ARM_ERROR:
            high = mid
        else:
            low = mid + 1
    if low > n:
        raise ValueError("too few controls for a finite upper tolerance limit")
    return low


def _upper_fpr(alerts: int, controls: int) -> float:
    """One-sided 95% Clopper-Pearson upper confidence limit."""
    if controls < 1 or not 0 <= alerts <= controls:
        raise ValueError("upper FPR needs valid false-alert and control counts")
    if alerts == controls:
        return 1.
    if alerts == 0:
        return -math.expm1(math.log(UPPER_ERROR) / controls)
    low, high = alerts / controls, 1.
    for _ in range(55):
        mid = (low + high) / 2
        if _binomial_cdf(alerts, controls, mid) <= UPPER_ERROR:
            high = mid
        else:
            low = mid
    return high


def _strict_bools(frame: pd.DataFrame) -> None:
    for column in BOOL_COLUMNS:
        parsed = frame[column].map({"True": True, "False": False})
        if parsed.isna().any():
            raise ValueError(f"invalid prior boolean in {column}")
        frame[column] = parsed.astype(bool)
    if ((frame.small_positive | frame.two_agent_positive) & ~frame.positive).any() or (
            (frame.hard_control | frame.sharing_control) & frame.positive).any():
        raise ValueError("inconsistent prior positive and control subgroup labels")


def _features(frame: pd.DataFrame, columns) -> pd.DataFrame:
    return frame[list(columns)].replace("", "nan").apply(lambda col: col.map(float))


def _earlier_ids(prior: Path, protocol: dict) -> set[str]:
    provenance = protocol["provenance"]
    # Accept a regenerated study in another directory. Its upstream native archive
    # and older score files are identified by the hashes in the prior protocol.
    roots = (prior.parent.parent, Path.cwd(), Path(__file__).resolve().parents[3])
    root = next((p for p in roots if (p / "data/scope/runs.csv.gz").is_file()
                 and previous._sha256(p / "data/scope/runs.csv.gz") == provenance["archive_table_sha256"]
                 and (p / "benchmarks/read-calibration/protocol.json").is_file()), None)
    if root is None:
        raise ValueError("the upstream matching scope archive and read-calibration study are required")
    archive = pd.read_csv(root / "data/scope/runs.csv.gz", usecols=["run_id"], dtype=str)
    seen = set()
    previous._reserve(pd.Index(archive.run_id), seen)
    partitions = [run for partition in provenance["partitions"].values() for run in partition["run_ids"]]
    if len(partitions) != len(set(partitions)) or not seen.issuperset(partitions):
        raise ValueError("prior development partitions do not match the upstream archive")
    for grid in provenance["original_confirmation"].values():
        previous._reserve(pd.Index(grid["run_ids"]), seen)
    recorded = prior_round._reserve_previous(root / "benchmarks/read-calibration", root / "data",
                                            seen, provenance)
    if recorded != protocol["prior_benchmarks"]:
        raise ValueError("upstream benchmark ids or hashes differ from the prior grant study")
    return seen


def _restore(prior: Path):
    protocol = json.loads((prior / "protocol.json").read_bytes())
    original, updated = REFERENCE, prior_round.CANDIDATE
    columns = {original: prior_round.BASE_COLUMNS, updated: prior_round.CANDIDATE_COLUMNS}
    if (protocol["input_columns"] != {a: list(c) for a, c in columns.items()}
            or protocol["reference"] != original or protocol["candidate"] != updated
            or protocol["max_fpr"] != scope.MAX_FPR or protocol["scope_label"] != scope.STRICT
            or protocol["calibration_seeds"] != list(prior_round.CALIBRATION_SEEDS)
            or protocol["confirmation_seeds"] != list(prior_round.CONFIRMATION_SEEDS)):
        raise ValueError("prior study differs from the frozen two-fit grant protocol")
    provenance = protocol["provenance"]
    fitting = pd.read_csv(prior / "fitting.csv.gz", dtype=str, keep_default_na=False)
    _strict_bools(fitting)
    stored_fit = provenance["partitions"]["fitting"]
    if (fitting.run_id.tolist() != stored_fit["run_ids"] or not fitting.run_id.is_unique
            or len(fitting) != protocol["fitting_runs"] or not fitting.population.eq("native").all()
            or int(fitting.positive.sum()) != stored_fit["positives"]
            or int((~fitting.positive).sum()) != stored_fit["controls"]):
        raise ValueError("prior fitting ids, order or strict labels do not match the recorded partition")
    models = {}
    for arm, inputs in columns.items():
        model = RunDetector(REFERENCE, provenance["fit_seed"], scope.MAX_FPR)
        models[arm] = model.fit(_features(fitting, inputs), fitting.positive.to_numpy())
    seen = _earlier_ids(prior, protocol)
    earlier_count = len(seen)
    verify_grid = prior_round.CONFIRMATION_SEEDS[0]
    checks = {}
    for name in ("calibration-controls", *prior_round.CONFIRMATION_SEEDS):
        full = name == verify_grid
        usecols = None if full else ["run_id", "grid", "detector", *BOOL_COLUMNS]
        native = None
        for view in ("native", "overlap"):
            path = prior / view / f"{name}.csv.gz"
            raw = pd.read_csv(path, usecols=usecols, dtype=str, keep_default_na=False)
            _strict_bools(raw)
            if set(raw.detector) != set(models) or raw.duplicated(["run_id", "detector"]).any():
                raise ValueError("prior study requires one record per run and arm")
            ids = None
            for arm, model in models.items():
                part = raw[raw.detector == arm].set_index("run_id").sort_index()
                membership = part[["grid", *BOOL_COLUMNS]]
                if ids is not None and not ids.equals(membership):
                    raise ValueError("prior study must pair arms on identical ids and labels")
                ids = membership
                if full:
                    cutoff = float(protocol["thresholds"][view][arm])
                    saved = part.score.map(float).to_numpy()
                    replay = model.score(_features(part, model.columns))
                    error = np.max(np.abs(saved - replay))
                    if (not part.threshold.map(float).eq(cutoff).all() or not np.isfinite(error)
                            or error > 1e-12 or not np.array_equal(saved > cutoff, replay > cutoff)):
                        raise ValueError("frozen scores or threshold decisions failed prior-grid parity")
                    checks[f"{view}/{arm}"] = {"rows": len(part), "alert_count": int((replay > cutoff).sum()),
                                                "max_abs_score_error": float(error), "sha256": previous._sha256(path)}
            if view == "native":
                native = ids
            elif not native.equals(ids):
                raise ValueError("prior views have different run ids or strict labels")
        if name == "calibration-controls":
            counts = native.groupby("grid").size().to_dict()
            if counts != {str(s): previous.CONTROLS_PER_GRID for s in prior_round.CALIBRATION_SEEDS} or native.positive.any():
                raise ValueError("incomplete prior calibration controls")
        elif (not native.grid.eq(str(name)).all() or int(native.positive.sum()) != previous.POSITIVES_PER_GRID
              or int((~native.positive).sum()) != previous.CONTROLS_PER_GRID):
            raise ValueError("incomplete prior confirmation grid")
        previous._reserve(native.index, seen)
    fallback = float(protocol["thresholds"]["native"][REFERENCE])
    return models, fallback, seen, {
        "protocol_sha256": previous._sha256(prior / "protocol.json"), "fit_sha256": previous._sha256(prior / "fitting.csv.gz"),
        "fit_seed": provenance["fit_seed"], "archive_seed": provenance["archive_seed"], "fitting_runs": len(fitting),
        "prior_parity_grid": verify_grid, "prior_parity": checks, "prior_score_error_tolerance": 1e-12,
        "upstream_ids_reserved": earlier_count, "total_prior_ids_reserved": len(seen),
    }


def _sample(seeds, controls_only, workers, seen):
    populations = prior_round._sample(seeds, controls_only, workers, seen, layout=LAYOUT)
    office, native = populations["overlap"], populations["native"]
    if not office.exercised_overlap_pairs.gt(0).all() or native.exercised_overlap_pairs.gt(0).any():
        raise ValueError("layout support differs from the preregistered grant routing populations")
    return {LAYOUT: office.assign(population=LAYOUT), "native": native}


def _routed(rows: pd.DataFrame, models: dict, fallback: float, thresholds: dict) -> pd.DataFrame:
    overlap = rows.exercised_overlap_pairs.gt(0).to_numpy()
    common = models[REFERENCE].score(rows[list(models[REFERENCE].columns)])
    selected = common.copy()
    if overlap.any():
        grant = models[prior_round.CANDIDATE]
        selected[overlap] = grant.score(rows.loc[overlap, list(grant.columns)])
    results = []
    for arm, scores in ((REFERENCE, common), (CANDIDATE, selected)):
        if not np.isfinite(scores).all():
            raise ValueError("routed model returned a nonfinite score")
        results.append(rows.assign(
            detector=arm, score=scores, threshold=np.where(overlap, thresholds[arm], fallback),
            routed_to_overlap=overlap, task="scope", split_seed=read_round.ARCHIVE_SEED,
        ))
    return pd.concat(results, ignore_index=True)


def _save_view(path: Path, calibration: pd.DataFrame, confirmation: pd.DataFrame, view: str) -> dict:
    prior_round._write_table(path / "calibration-controls.csv.gz", calibration.assign(test_set="calibration"))
    files = []
    for grid, rows in confirmation.groupby("grid", sort=True):
        dest = path / f"{grid}.csv.gz"
        prior_round._write_table(dest, rows.assign(test_set="independent"))
        files.append(dest)
    counts = []
    for arm, rows in confirmation.groupby("detector", sort=False):
        if rows.threshold.nunique() != 1:
            raise ValueError("each planned population must have one frozen cutoff per arm")
        threshold = rows.threshold.iloc[0]
        for grid, subset in [*rows.groupby("grid", sort=True), ("pooled", rows)]:
            summary = previous._diagnose(subset, threshold)
            upper = _upper_fpr(summary["false_positives"], summary["controls"])
            counts.append(dict(grid=grid, detector=arm, **summary, fpr_exact_upper_95=upper,
                               routed_runs=int(subset.routed_to_overlap.sum())))
    diagnostics = pd.DataFrame(counts)
    diagnostics.to_csv(path / "diagnostics.csv", index=False, lineterminator="\n")
    scorecard = benchmark_round(files, "scope", REFERENCE, CANDIDATE)
    scorecard["source"] = scorecard.source.replace({str(p): p.name for p in files})
    pooled = scorecard.population == "pooled"
    result = scorecard[pooled].iloc[0]
    upper = diagnostics[(diagnostics.grid == "pooled") & (diagnostics.detector == CANDIDATE)].fpr_exact_upper_95.item()
    native = view == "native"
    same = False
    if native:
        arms = [confirmation[confirmation.detector == a].set_index("run_id").sort_index()
                for a in (REFERENCE, CANDIDATE)]
        same = arms[0][["score", "threshold"]].equals(arms[1][["score", "threshold"]])
        if not same or confirmation.routed_to_overlap.any():
            raise ValueError("native fallback failed score and decision parity")
    eligible = int(result.primary_positives) >= prior_round.MIN_ONE_FILE
    accepted = bool(not native and eligible and result.evidence == "promising" and upper <= scope.MAX_FPR)
    qualification = result.evidence
    if native:
        qualification = "fallback_parity"
    elif not eligible:
        qualification = "insufficient_data"
    elif accepted:
        qualification = "qualified_local_profile"
    elif result.evidence == "promising":
        qualification = "insufficient_fpr_confidence"
    scorecard["round_evidence"] = ""
    scorecard.loc[pooled, "round_evidence"] = qualification
    scorecard.to_csv(path / "scorecard.csv", index=False, lineterminator="\n")
    grids = scorecard[~pooled]
    return {
        "paired_evidence": result.evidence, "round_evidence": qualification,
        "qualified_local_profile": accepted, "candidate_fpr_exact_upper_95": upper,
        "counts_toward_diminishing_returns": qualification == "below_minimum",
        "native_fallback_parity_verified": same, "one_file_runs": int(result.primary_positives),
        "grids_gaining": int((grids.primary_recall_delta > 0).sum()),
        "grids_equal": int((grids.primary_recall_delta == 0).sum()),
        "grids_losing": int((grids.primary_recall_delta < 0).sum()),
    }


def run_grant_policy(out: Path, prior: Path, workers: int = 4) -> None:
    """Test one fixed grant routing policy on a new office layout and native control."""
    out, prior = Path(out), Path(prior)
    if type(workers) is not int or workers < 1:
        raise ValueError("workers must be a positive integer")
    if out.exists():
        raise ValueError(f"grant-policy output already exists: {out}")
    seeds = (read_round.ARCHIVE_SEED, 20261123, 20261124, 20261125, *read_round.CONFIRMATION_SEEDS,
             *previous.CALIBRATION_SEEDS, *previous.CONFIRMATION_SEEDS, *prior_round.CALIBRATION_SEEDS,
             *prior_round.CONFIRMATION_SEEDS, *CALIBRATION_SEEDS, *CONFIRMATION_SEEDS)
    if len(seeds) != len(set(seeds)):
        raise ValueError("prior, calibration and confirmation seeds must be disjoint")
    out.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=out.parent) as temporary, _worker_threads():
        stage = Path(temporary) / "policy"
        stage.mkdir()
        models, fallback, seen, provenance = _restore(prior)
        controls = _sample(CALIBRATION_SEEDS, True, workers, seen)
        office = controls[LAYOUT]
        if office.positive.any() or not office.exercised_overlap_pairs.gt(0).all():
            raise ValueError("tolerance calibration requires only strict controls with exercised overlap")
        rank = _tolerance_rank(len(office))
        scores = prior_round._scores(office, models)
        thresholds = {arm: float(np.sort(scores[key])[rank - 1])
                      for arm, key in ((REFERENCE, REFERENCE), (CANDIDATE, prior_round.CANDIDATE))}
        calibration = {name: _routed(rows, models, fallback, thresholds) for name, rows in controls.items()}
        fresh = _sample(CONFIRMATION_SEEDS, False, workers, seen)
        decisions = {}
        for view, rows in fresh.items():
            paired = _routed(rows, models, fallback, thresholds)
            decisions[view] = _save_view(stage / view, calibration[view], paired, view)
        n = len(office)
        write_json(stage / "protocol.json", {
            "reference": REFERENCE, "candidate": CANDIDATE, "provenance": provenance,
            "input_columns": {name: list(fit.columns) for name, fit in models.items()},
            "primary_population": LAYOUT, "native_cutoff": fallback, "overlap_thresholds": thresholds,
            "routing": "Use the overlap cutoffs only after two distinct concurrently eligible grants were exercised.",
            "calibration_seeds": list(CALIBRATION_SEEDS), "confirmation_seeds": list(CONFIRMATION_SEEDS),
            "calibration_controls_per_view": n, "max_fpr": scope.MAX_FPR, "family_error": 2 * ARM_ERROR,
            "per_arm_error": ARM_ERROR, "calibration_rank_one_based": rank,
            "order_statistic_tail": _binomial_cdf(n - rank, n, scope.MAX_FPR),
            "smaller_rank_tail": _binomial_cdf(n - rank + 1, n, scope.MAX_FPR),
            "max_calibration_scores_strictly_above_cutoff": n - rank,
            "overlap_calibration_alerts": {arm: int((scores[key] > thresholds[arm]).sum())
                                          for arm, key in ((REFERENCE, REFERENCE), (CANDIDATE, prior_round.CANDIDATE))},
            "calibration_assumption": "The nominal order-statistic family bound assumes iid control scores. "
                                      "The simulation fixes workflow strata and measures the actual held-out rate.",
            "confirmation_interval": "One-sided 95% Clopper-Pearson upper limit, using inversion of the binomial CDF.",
            "minimum_one_file_gain": .01, "minimum_one_file_runs": prior_round.MIN_ONE_FILE,
            "adoption_rule": "Local profile requires the promising paired result and an exact upper FPR limit at most 5%.",
            "decisions": decisions,
        })
        stage.rename(out)
