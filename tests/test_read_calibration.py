import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from swarmtrace.eval.metrics import wilson
from swarmtrace.reproduce import read_calibration as rc

ROOT = Path(__file__).resolve().parents[1]
STUDY = ROOT / "benchmarks" / "read-authorization"
DATA = ROOT / "data"


def test_published_calibration_replays_from_control_and_confirmation_scores():
    root = ROOT / "benchmarks" / "read-calibration"
    protocol = json.loads((root / "protocol.json").read_bytes())
    controls = pd.read_csv(root / "calibration-controls.csv.gz", dtype={"score": str})
    rank = math.ceil((len(controls) + 1) * (1 - protocol["max_fpr"]))
    cutoff = sorted(map(float, controls.score))[rank - 1]
    assert rank == 617 and not controls.positive.any() and controls.run_id.is_unique
    assert cutoff == protocol["thresholds"][rc.CANDIDATE]
    raw = pd.concat([pd.read_csv(root / f"{seed}.csv.gz", dtype={"score": str, "threshold": str})
                     for seed in rc.CONFIRMATION_SEEDS]).set_index(["detector", "run_id"])
    reference, candidate = raw.loc[rc.REFERENCE], raw.loc[rc.CANDIDATE]
    pd.testing.assert_frame_equal(reference.drop(columns="threshold"), candidate.drop(columns="threshold"))
    assert candidate.index.is_unique and not set(candidate.index).intersection(controls.run_id)
    details = pd.read_csv(root / "diagnostics.csv").set_index(["grid", "detector"])
    for detector, rows in ((rc.REFERENCE, reference), (rc.CANDIDATE, candidate)):
        flagged = rows.score.map(float) > rows.threshold.map(float)
        pooled = details.loc["pooled", detector]
        for condition, column in ((rows.positive, "true_positives"),
                                  (~rows.positive, "false_positives"),
                                  (rows.small_positive, "one_file_flagged"),
                                  (rows.hard_control, "in_scope_relay_flagged")):
            assert pooled[column] == (flagged & condition).sum()
    decision = protocol["decision"]
    new = details.loc["pooled", rc.CANDIDATE]
    assert decision["recalibrated_observed_within_budget"] == (
        new.false_positives <= protocol["max_fpr"] * new.controls)
    assert decision["counts_toward_diminishing_returns"] is False


def test_restores_restricted_archived_split_and_cutoff():
    model, published, seen, provenance = rc._restore(STUDY, DATA)
    assert model.columns == rc.read_round.BASE_COLUMNS
    assert model.threshold == pytest.approx(0.6128164021162121, rel=0, abs=1e-12)
    assert published == 0.6128164021162121
    assert len(seen) == 1134 + 2 * 378
    assert len(provenance["partitions"]["fitting"]["run_ids"]) == 256
    assert provenance["partitions"]["calibration"]["controls"] == 62
    assert len(provenance["archive_table_sha256"]) == 64


@pytest.mark.parametrize("damage", ["inputs", "partition", "labels", "threshold"])
def test_refuses_changed_source_before_touching_new_grids(tmp_path, monkeypatch, damage):
    protocol = json.loads((STUDY / "workflow" / "protocol.json").read_text())
    if damage == "inputs":
        protocol["input_columns"][rc.REFERENCE].reverse()
    elif damage == "partition":
        fit, cal = (protocol["partitions"][name]["run_ids"] for name in ("fitting", "calibration"))
        fit[0], cal[0] = cal[0], fit[0]
    elif damage == "labels":
        protocol["partitions"]["calibration"]["positives"] += 1
    else:
        protocol["thresholds"][rc.REFERENCE] += 2e-12
    (tmp_path / "workflow").mkdir()
    (tmp_path / "workflow" / "protocol.json").write_text(json.dumps(protocol))
    monkeypatch.setattr(rc, "_sample", lambda *args: pytest.fail("opened a fresh grid"))
    with pytest.raises(ValueError, match="ordered C2 inputs|ids or strict labels|cutoff differs"):
        rc.run_read_calibration(tmp_path / "out", tmp_path, DATA, 1)
    assert not (tmp_path / "out").exists()


class FakeModel:
    columns = ("value",)

    def __init__(self):
        self.scored = []

    def score(self, features):
        self.scored.extend(features.index)
        return features.value.to_numpy()


def sample(seed, controls_only, workers):
    controls, positives = rc.CONTROLS_PER_GRID, 0 if controls_only else rc.POSITIVES_PER_GRID
    n = controls + positives
    index = pd.Index([f"{seed}-{i}" for i in range(n)], name="run_id")
    i = np.arange(n)
    if controls_only:
        # 204 low scores per seed. The pooled 617th smallest value is 0.7 (including ties).
        values = np.where(i < 204, .3, np.where(i < 212, .7, .9))
    else:
        values = np.resize([.4, .6, .7, .8], n)
    truth = pd.DataFrame({
        "positive": i >= controls, "hard_control": i < rc.IN_SCOPE_PER_GRID,
        "sharing_control": (i >= rc.IN_SCOPE_PER_GRID) & (i < controls) & (i % 3 == 0),
        "small_positive": (i >= controls) & (i % 3 == 0),
        "two_agent_positive": (i >= controls) & (i % 3 == 1),
        "topology": np.where(i % 2 == 0, "hub", "peer"), "scope_mistake_rate": 0,
    }, index=index)
    return pd.DataFrame({"value": values}, index=index), truth


@pytest.fixture
def simulated(monkeypatch):
    model = FakeModel()
    monkeypatch.setattr(rc, "CALIBRATION_SEEDS", (21, 22, 23))
    monkeypatch.setattr(rc, "CONFIRMATION_SEEDS", (31, 32))
    monkeypatch.setattr(rc, "_restore", lambda study, data: (model, .5, {"prior-id"}, {}))
    monkeypatch.setattr(rc, "_sample", sample)
    return model


def test_one_control_quantile_fixed_before_confirmation_and_paired_scores(tmp_path, simulated):
    out = tmp_path / "study"
    rc.run_read_calibration(out, tmp_path, tmp_path, 1)
    protocol = json.loads((out / "protocol.json").read_text())
    assert protocol["thresholds"] == {rc.REFERENCE: .5, rc.CANDIDATE: .7}
    assert protocol["conformal_rank_one_based"] == 617 and protocol["calibration_controls"] == 648
    controls = pd.read_csv(out / protocol["outputs"]["calibration_scores"])
    assert controls.score.sort_values().iloc[616] == .7 and not controls.positive.any()
    assert len(set(simulated.scored)) == len(simulated.scored) == 648 + 756
    assert simulated.scored[:648] == controls.run_id.tolist()
    truth, values = [], []
    for seed, name in protocol["outputs"]["scores"].items():
        pairs = pd.read_csv(out / name).set_index(["detector", "run_id"])
        old, new = pairs.loc[rc.REFERENCE], pairs.loc[rc.CANDIDATE]
        assert new.index.tolist() == protocol["samples"]["confirmation"][seed]["run_ids"]
        pd.testing.assert_frame_equal(old.drop(columns="threshold"), new.drop(columns="threshold"))
        truth.extend(old.positive)
        values.extend(old.score)
    truth, values = np.array(truth), np.array(values)
    old, new = values > .5, values > .7
    details = pd.read_csv(out / "diagnostics.csv")
    assert len(details) == 6
    pooled = details[(details.grid == "pooled") & (details.detector == rc.CANDIDATE)].iloc[0]
    assert pooled.false_positives == (new & ~truth).sum()
    interval = wilson(int(pooled.false_positives), 432)
    assert pooled.fpr_wilson_low == pytest.approx(interval.low)
    assert pooled.fpr_wilson_high == pytest.approx(interval.high)
    assert pooled.one_file_runs == pooled.two_agent_runs == pooled.in_scope_relay_runs == 108
    decision = protocol["decision"]
    assert decision["false_alerts_avoided"] == (old & ~new & ~truth).sum()
    assert decision["newly_missed_violations"] == (old & ~new & truth).sum()
    assert decision["reviews_saved"] == old.sum() - new.sum()
    assert not decision["recalibrated_observed_within_budget"]
    assert not decision["counts_toward_diminishing_returns"]
    repeat = tmp_path / "repeat"
    rc.run_read_calibration(repeat, tmp_path, tmp_path, 1)
    assert all(path.read_bytes() == (repeat / path.name).read_bytes() for path in out.iterdir())


@pytest.mark.parametrize("damage", ["prior_collision", "calibration_reuse", "positive_control"])
def test_bad_samples_cannot_publish_output(tmp_path, simulated, monkeypatch, damage):
    def wrong_sample(seed, controls_only, workers):
        original = 21 if seed == 31 and damage == "calibration_reuse" else seed
        features, truth = sample(original, controls_only, workers)
        if seed == 21 and damage == "prior_collision":
            features.index = truth.index = features.index.map(lambda x: "prior-id" if x == "21-0" else x)
        if seed == 21 and damage == "positive_control":
            truth.iloc[0, truth.columns.get_loc("positive")] = True
        return features, truth

    monkeypatch.setattr(rc, "_sample", wrong_sample)
    out = tmp_path / "study"
    with pytest.raises(ValueError, match="disjoint ids|wrong positive or control composition"):
        rc.run_read_calibration(out, tmp_path, tmp_path, 1)
    assert not out.exists()


def test_native_grid_selection_filters_control_jobs_before_running(monkeypatch):
    class Checked(Exception):
        pass

    def check_dispatch(function, jobs, workers):
        assert function is rc._holdout_row
        assert len(jobs) == 216
        assert all(job.condition.channel == "preplanned" and job.condition.violation_size == 0
                   for job in jobs)
        assert sum(job.condition.offensive_group_size > 0 for job in jobs) == 54
        raise Checked

    monkeypatch.setattr(rc, "_map", check_dispatch)
    with pytest.raises(Checked):
        rc._sample(412, True, 1)


def test_native_features_and_strict_truth_align_for_all_control_types(monkeypatch):
    jobs = rc.read_round._jobs(412, ("preplanned",))
    selected = [next(j for j in jobs if j.condition.offensive_group_size == 0),
                next(j for j in jobs if j.condition.offensive_group_size == 2
                     and j.condition.violation_size == 0),
                next(j for j in jobs if j.condition.offensive_group_size == 2
                     and j.condition.violation_size == 1)]
    monkeypatch.setattr(rc.read_round, "_jobs", lambda seed, channels: selected)
    features, truth = rc._sample(412, False, 1)
    assert list(features) == list(rc.read_round.BASE_COLUMNS) and features.index.equals(truth.index)
    assert tuple(truth[["positive", "hard_control", "small_positive", "two_agent_positive"]].sum()) == (1, 1, 1, 1)
    assert int((~truth.positive & ~truth.hard_control).sum()) == 1
