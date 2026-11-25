import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from swarmtrace.detect.assignment import AssignmentLogistic
from swarmtrace.features.assignment import ASSIGNMENT_COLUMNS, assignment_features
from swarmtrace.reproduce import assignment_transfer as transfer
from swarmtrace.reproduce.office_overlap import _office, office_job, with_office_overlap
from swarmtrace.trace.io import Trace
from swarmtrace.trace.tiers import Tier

BENCHMARKS = Path(__file__).resolve().parents[1] / "benchmarks"


@pytest.mark.parametrize("layout", ["two_issuers", "same_issuer"])
def test_office_grants_remain_identical_after_interleaving_and_identifier_collision(layout):
    native = _office("routine", 2, True, 0xfd000000)
    trace = Trace(native.audit.run_id, Tier.V1, native.events)
    view, context, audit, variant = with_office_overlap(trace, native.context, native.audit, layout=layout)
    chosen, documents, reverse, _ = office_job(trace.run_id, layout)
    assert chosen == variant
    isolated = transfer._office_grants(layout, chosen, documents, reverse)
    combined = assignment_features(view, context, audit).features
    extra = combined.drop(index=[g.grant_id for g in native.audit.grants])
    np.testing.assert_array_equal(extra.to_numpy(), isolated)


def test_frozen_detector_on_archived_benign_clerks_reproduces_every_control_alert():
    protocol = json.loads((BENCHMARKS / "assignment" / "protocol.json").read_bytes())
    model = AssignmentLogistic.from_parameters(protocol["model"], len(ASSIGNMENT_COLUMNS))
    cutoff = protocol["cutoffs"]["workflow"]["assignment-logistic"]
    rows, summary = transfer._archived_controls(BENCHMARKS, model, cutoff)
    archive = BENCHMARKS / "assignment-transfer"
    saved = pd.read_csv(archive / "office-control-runs.csv.gz", dtype={"run_id": str},
                        converters={"office_score": float, "threshold": float})
    pd.testing.assert_frame_equal(rows, saved, check_exact=True)
    counts = pd.read_csv(archive / "office-controls.csv", converters={"minimum_false_alert_rate": float})
    pd.testing.assert_frame_equal(summary, counts, check_exact=True)
    assert len(rows) == rows.run_id.nunique() == 4320
    assert (rows.office_alert == rows.variant.eq("mistake")).all()
    floor = summary.loc[summary.variant == "all"]
    assert floor.minimum_false_alert_rate.gt(.05).all()


def test_archived_mistake_inputs_coincide_with_top_scoring_grants_on_one_file_cases():
    # This is a retrospective feature collision diagnostic on the first confirmation.
    # Equal vectors constrain an individual grant scorer, even if the full logs differ.
    root = BENCHMARKS / "assignment"
    protocol = json.loads((root / "protocol.json").read_bytes())
    model = AssignmentLogistic.from_parameters(protocol["model"], len(ASSIGNMENT_COLUMNS))
    office = set()
    for layout in ("two_issuers", "same_issuer"):
        for docs in (1, 2, 3):
            bag = transfer._office_grants(layout, "mistake", docs, False)
            office.update(map(tuple, bag[bag[:, 0] > 0]))
    scores = pd.concat([pd.read_csv(root / "workflow" / f"{g}.csv.gz", dtype=str,
                                    usecols=["run_id", "small_positive", "detector", "score", "threshold"])
                        for g in protocol["confirmation_seeds"]])
    one_file = scores.loc[scores.small_positive.eq("True") & scores.detector.eq("assignment-logistic")]
    assert len(one_file) == one_file.run_id.nunique() == 540
    grants = pd.read_csv(root / "workflow/independent-assignments.csv.gz", dtype=str)
    cases = grants.loc[grants.run_id.isin(one_file.run_id)].set_index("run_id")
    inputs = cases[list(ASSIGNMENT_COLUMNS)].apply(lambda col: col.map(float))
    values = pd.Series(model.assignment_scores(inputs.to_numpy()), index=inputs.index)
    highest = inputs.loc[values.eq(values.groupby(level=0).transform("max"))]
    matched = set(highest.loc[highest.apply(tuple, axis=1).isin(office)].index)
    assert len(matched) == 496
    assert matched <= set(one_file.loc[one_file.score.map(float) > one_file.threshold.map(float), "run_id"])

    # A strict cutoff below the 109th highest office score must flag at least
    # 109 of the 2,160 controls. This necessary condition ignores native alerts.
    controls = pd.read_csv(BENCHMARKS / "assignment-transfer/office-control-runs.csv.gz",
                           usecols=["layout", "office_score"], converters={"office_score": float})
    floor = max(sorted(group.office_score, reverse=True)[len(group) * 5 // 100]
                for _, group in controls.groupby("layout"))
    assert one_file.score.map(float).gt(floor).sum() == 7
