"""Validate the grant observer and publish the full held-out comparison."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import pandas as pd

from swarmtrace.eval.grant_challenge import grant_challenge
from swarmtrace.trace.authorization import read_authorization
from swarmtrace.trace.context import read_context
from swarmtrace.trace.io import RunPaths, read_trace
from swarmtrace.trace.tiers import Tier

from .config import RunJob
from .office_overlap import with_office_overlap
from .scope import ScopeConfig, _identical_pair, _map, _worker_threads, make_identical_jobs


def _office_twin(job: RunJob) -> dict:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        pair = _identical_pair((job, root), capture_authorization=True)
        if pair.mismatches:
            raise ValueError(f"native role twin {pair.pair} differs in {pair.mismatches}")
        observations = []
        for arm in ("control", "relay"):
            paths = RunPaths(root / job.dataset / job.directory / arm)
            observations.append(with_office_overlap(read_trace(paths.trace, Tier.V1),
                                                    read_context(paths.context),
                                                    read_authorization(paths.authorization)))
        if observations[0] != observations[1]:
            raise ValueError(f"office observations differ after role flip on {pair.pair}")
        return dict(pair=pair.pair, seed=pair.seed, office_variant=observations[0][3],
                    native_identical=True, overlap_identical=True)


def _secondary(study: Path) -> None:
    from swarmtrace.eval.feature_limits import feature_ceiling

    protocol = json.loads((study / "protocol.json").read_bytes())
    limits, reviews, intervals = [], [], []
    for view in ("overlap", "native"):
        root = study / view
        grids = protocol["confirmation_seeds"]
        # Parse numeric inputs with Python float to preserve all exported binary64 values.
        raw = pd.concat([pd.read_csv(root / f"{grid}.csv.gz", dtype=str,
                                    keep_default_na=False) for grid in grids])
        card = pd.read_csv(root / "scorecard.csv")
        pooled = card[card.population == "pooled"].iloc[0]
        by_grid = card[card.population == "grid"]
        draws = np.random.default_rng(9071123).integers(len(grids), size=(20_000, len(grids)))
        net = (by_grid.primary_gained - by_grid.primary_lost).to_numpy()[draws].sum(axis=1)
        eligible = by_grid.primary_positives.to_numpy()[draws].sum(axis=1)
        low, high = np.quantile(net / eligible, [.025, .975])
        intervals.append(dict(view=view, grids=len(grids), primary_gain=pooled.primary_recall_delta,
                              grid_resample_low=low, grid_resample_high=high,
                              grids_gaining=int((by_grid.primary_recall_delta > 0).sum()),
                              grids_losing=int((by_grid.primary_recall_delta < 0).sum())))
        for detector, columns in protocol["input_columns"].items():
            rows = raw[raw.detector == detector].set_index("run_id")
            features = rows[columns].replace("", "nan").apply(lambda column: column.map(float))
            pos = rows.positive == "True"
            small = rows.small_positive == "True"
            metrics = feature_ceiling(features, pos, small, int(pooled.false_alert_budget))
            limits.append(dict(view=view, detector=detector, **metrics))
            flagged = rows.score.map(float) > rows.threshold.map(float)
            recall, fpr = flagged[pos].mean(), flagged[~pos].mean()
            for prevalence in (.001, .01, .05):
                tp = 1000 * prevalence * recall
                fp = 1000 * (1 - prevalence) * fpr
                reviews.append(dict(view=view, detector=detector, assumed_prevalence=prevalence,
                                    recall=recall, fpr=fpr, true_reviews_per_1000=tp,
                                    false_reviews_per_1000=fp,
                                    review_precision=tp / (tp + fp) if tp + fp else np.nan))
    for name, rows in (("feature-limits.csv", limits), ("review-load.csv", reviews),
                       ("seed-intervals.csv", intervals)):
        pd.DataFrame(rows).to_csv(study / name, index=False, lineterminator="\n")


def run_grant_study(out: Path, study: Path, data: Path, previous_calibration: Path, workers: int = 4,
                    *, checks_only: bool = False) -> None:
    config = ScopeConfig(seed=20261120, workers=workers)
    if out.exists():
        raise ValueError(f"grant study output already exists: {out}")
    out.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=out.parent) as directory:
        stage = Path(directory) / "study"
        checks = grant_challenge(check=True)
        with _worker_threads():
            twins = _map(_office_twin, make_identical_jobs(config), workers)
        if checks_only:
            stage.mkdir()
        else:
            from .grant_round import run_grant_round

            run_grant_round(stage, study, data, workers, previous_calibration=previous_calibration)
            _secondary(stage)
        checks.to_csv(stage / "attribution-checks.csv", index=False, lineterminator="\n")
        pd.DataFrame(twins).to_csv(stage / "role-twins.csv", index=False, lineterminator="\n")
        stage.rename(out)
