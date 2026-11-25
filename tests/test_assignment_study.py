import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from swarmtrace.cli import main
from swarmtrace.detect.assignment import AssignmentLogistic
from swarmtrace.features.assignment import ASSIGNMENT_COLUMNS
from swarmtrace.reproduce import assignment_round as study


def test_check_cli_compares_both_role_twin_workflows_without_opening_grids(tmp_path, monkeypatch):
    make = study.make_identical_jobs
    monkeypatch.setattr(study, "make_identical_jobs", lambda cfg: make(cfg)[:1])
    out = tmp_path / "checks"
    main(["assignment-round", "--out", str(out), "--workers", "1", "--checks-only"])
    rows = pd.read_csv(out / "role-twins.csv")
    assert rows.family.tolist() == ["record_check", "clerical_handoff"]
    assert rows.identical.all() and not (out / "protocol.json").exists()
    with pytest.raises(SystemExit):
        main(["assignment-round", "--out", str(out), "--checks-only"])


def test_published_local_scores_cutoffs_and_ids_replay_from_raw_assignments():
    root = Path(__file__).resolve().parents[1] / "benchmarks" / "assignment"
    protocol = json.loads((root / "protocol.json").read_bytes())
    assert protocol["assignment_columns"] == list(ASSIGNMENT_COLUMNS)
    params = protocol["model"]
    model = AssignmentLogistic(*(np.array(params[k]) for k in ("center", "scale", "weights")), params["intercept"])
    by_view = []
    for view in study.VIEWS:
        path = root / view
        calibration = pd.read_csv(path / "calibration-controls.csv.gz", usecols=["run_id", "score", "detector"], dtype=str)
        for name, rows in calibration.groupby("detector"):
            assert rows.run_id.nunique() == len(rows) == 1728
            cutoff = sorted(rows.score.map(float))[protocol["rank_one_based"] - 1]
            assert cutoff == protocol["cutoffs"][view][name]
        bags = pd.read_csv(path / "calibration-assignments.csv.gz", dtype=str)
        controls = calibration.loc[calibration.detector == study.CANDIDATE].set_index("run_id")
        inputs = bags[list(ASSIGNMENT_COLUMNS)].apply(lambda col: col.map(float))
        local_controls = inputs.groupby(bags.run_id).apply(lambda grant: model.score(grant.to_numpy())).reindex(
            controls.index, fill_value=0.)
        local_cutoff = sorted(local_controls)[protocol["rank_one_based"] - 1]
        archived_cutoff = protocol["cutoffs"][view][study.CANDIDATE]
        np.testing.assert_allclose(local_controls, controls.score.map(float), rtol=0, atol=1e-14)
        np.testing.assert_array_equal(local_controls > local_cutoff, controls.score.map(float) > archived_cutoff)
        scores = pd.concat([pd.read_csv(path / f"{k}.csv.gz", dtype={"score": str, "threshold": str, "run_id": str},
                                        usecols=["score", "threshold", "run_id", "detector", "positive", "small_positive"])
                            for k in protocol["confirmation_seeds"]], ignore_index=True)
        selected = scores[scores.detector == study.CANDIDATE].set_index("run_id")
        assert len(selected) == selected.index.nunique() == 3780 and selected.small_positive.sum() == 540
        assert set(selected.index).isdisjoint(calibration.run_id)
        grants = pd.read_csv(path / "independent-assignments.csv.gz", keep_default_na=False, dtype=str)
        grants[list(ASSIGNMENT_COLUMNS)] = grants[list(ASSIGNMENT_COLUMNS)].apply(lambda x: x.map(float))
        replay = grants.groupby("run_id")[list(ASSIGNMENT_COLUMNS)].apply(lambda g: model.score(g.to_numpy(dtype=float)))
        actual = selected.score.map(float)
        replay = replay.reindex(selected.index, fill_value=0.)
        np.testing.assert_allclose(actual, replay, rtol=0, atol=1e-14)
        flagged = actual > selected.threshold.map(float)
        np.testing.assert_array_equal(flagged, replay > local_cutoff)
        card = pd.read_csv(path / "scorecard.csv")
        primary = card[(card.population == "pooled") & (card.reference == study.REFERENCE)].iloc[0]
        assert primary.candidate_false_positives == (flagged & ~selected.positive).sum()
        assert primary.candidate_small_true_positives == (flagged & selected.small_positive).sum()
        assert primary.round_evidence == protocol["decisions"][view]["round_evidence"]
        by_view.append(set(selected.index))
    assert by_view[0] == by_view[1]
