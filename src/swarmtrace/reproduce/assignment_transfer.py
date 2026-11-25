"""Retrospective tests of frozen assignment scores against previously published workflows."""

from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import pandas as pd

from swarmtrace.features.assignment import assignment_features
from swarmtrace.trace.io import Trace
from swarmtrace.trace.tiers import Tier

from . import assignment_margin as margin
from . import assignment_round as study_round
from . import grant_policy, grant_round, read_calibration
from .office_overlap import VARIANTS, _office, office_job


def _first_confirmation(study, models, cutoffs):
    """Recover log odds from the original inputs and verify the stored probability decisions."""
    results = []
    for view in study_round.VIEWS:
        replay_cutoffs = cutoffs[view].copy()
        tables = [pd.read_csv(study / view / f"{seed}.csv.gz", dtype=str, keep_default_na=False)
                  for seed in study_round.CONFIRMATION_SEEDS]
        frame = pd.concat(tables, ignore_index=True)
        reference = frame.loc[frame.detector == study_round.REFERENCE].set_index("run_id").sort_index()
        scores = margin._whole_scores(reference, models)
        for arm in (*margin.WHOLE_RUN, margin.CANDIDATE):
            old = frame.loc[frame.detector == arm].set_index("run_id").sort_index()
            archived = old.threshold.map(float)
            if (not old.index.equals(reference.index) or archived.nunique() != 1
                    or abs(archived.iloc[0] - cutoffs[view][arm]) > 1e-12):
                raise ValueError("earlier scores differ in run order or frozen cutoff")
            saved = old.score.map(float).to_numpy()
            if arm in margin.WHOLE_RUN and (
                    not np.allclose(scores[arm], saved, rtol=0, atol=1e-12)
                    or not np.array_equal(scores[arm] > cutoffs[view][arm], saved > archived.iloc[0])):
                raise ValueError("old confirmation probabilities or their strict decisions failed replay")
            scores[arm] = saved
            replay_cutoffs[arm] = archived.iloc[0]
        grant_policy._strict_bools(reference)
        results.append(margin._operating_points(reference, scores, replay_cutoffs).assign(view=view))
    return pd.concat(results, ignore_index=True)


def _office_grants(layout, variant, documents, reverse):
    # The previous workflows remap colliding identities and shift all office ticks
    # together. Neither operation changes a feature within these disjoint grants.
    job = _office(variant, documents, reverse, 0xfd000000, layout)
    trace = Trace(job.audit.run_id, Tier.V1, job.events)
    return assignment_features(trace, job.context, job.audit).features.to_numpy()


def _archived_controls(benchmarks, model, cutoff):
    layouts = (
        ("two_issuers", benchmarks / "grant-scope" / "overlap", grant_round.CONFIRMATION_SEEDS),
        ("same_issuer", benchmarks / "grant-policy" / grant_policy.LAYOUT, grant_policy.CONFIRMATION_SEEDS),
    )
    rows, seen, scores = [], set(), {}
    cols = ["grid", "run_id", "detector", "office_variant", "positive", "test_set"]
    for layout, directory, seeds in layouts:
        for seed in seeds:
            raw = pd.read_csv(directory / f"{seed}.csv.gz", usecols=cols, dtype=str, keep_default_na=False)
            base = raw.loc[raw.detector == study_round.REFERENCE]
            if (not base.grid.eq(str(seed)).all() or not base.test_set.eq("independent").all()
                    or not base.positive.isin(["True", "False"]).all() or not base.run_id.is_unique
                    or len(base) != read_calibration.POSITIVES_PER_GRID + read_calibration.CONTROLS_PER_GRID):
                raise ValueError("unexpected population in the archived office workflow")
            controls = base.loc[base.positive == "False"]
            if len(controls) != read_calibration.CONTROLS_PER_GRID:
                raise ValueError("archived office controls differ from the published count")
            read_calibration._reserve(base.run_id, seen)
            for row in controls.itertuples():
                variant, documents, reverse, _ = office_job(row.run_id, layout)
                if variant != row.office_variant:
                    raise ValueError("archived office variant failed replay")
                key = layout, variant, documents, reverse
                if key not in scores:
                    scores[key] = model.score(_office_grants(*key))
                rows.append(dict(layout=layout, grid=seed, run_id=row.run_id, variant=variant,
                                 documents=documents, reverse=reverse, office_score=scores[key],
                                 threshold=cutoff, office_alert=scores[key] > cutoff))
    frame = pd.DataFrame(rows)
    counts = []
    for layout, group in frame.groupby("layout", sort=False):
        for variant in ("all", *VARIANTS):
            subset = group if variant == "all" else group.loc[group.variant == variant]
            alerts = int(subset.office_alert.sum())
            counts.append(dict(layout=layout, variant=variant, controls=len(subset),
                               minimum_false_alerts=alerts, minimum_false_alert_rate=alerts / len(subset)))
    return frame, pd.DataFrame(counts)


def audit_assignment_transfer(study: Path, benchmarks: Path, out: Path) -> None:
    if out.exists():
        raise ValueError("assignment transfer audit requires a new output directory")
    out.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=out.parent) as tmp:
        work = Path(tmp)
        stage = work / "results"
        stage.mkdir()
        models, local, _, calibration = margin._prepare(study, benchmarks, work)
        cutoffs = calibration["cutoffs"]
        replay = _first_confirmation(study, models, cutoffs)
        controls, counts = _archived_controls(benchmarks, local, cutoffs["workflow"][margin.CANDIDATE])
        replay.to_csv(stage / "first-confirmation.csv", index=False, lineterminator="\n")
        grant_round._write_table(stage / "office-control-runs.csv.gz", controls)
        counts.to_csv(stage / "office-controls.csv", index=False, lineterminator="\n")
        stage.rename(out)
