from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from swarmtrace.eval.rounds import benchmark_round


def grid(path, positive_count, reference, candidate, *, prefix="run"):
    size = len(reference)
    positions = np.arange(size)
    labels = pd.DataFrame({
        "task": "scope", "test_set": "independent", "split_seed": 24,
        "run_id": [f"{prefix}-{i}" for i in positions], "positive": positions < positive_count,
        "small_positive": positions < positive_count, "hard_control": positions >= positive_count,
    })
    frames = [labels.assign(detector=name, score=values, threshold=0.5)
              for name, values in [("incumbent", reference), ("new", candidate)]]
    table = pd.concat(frames, ignore_index=True)
    table.to_csv(path, index=False)
    return table


def evaluate(*paths):
    return benchmark_round(paths, "scope", "incumbent", "new")


def test_frozen_alerts_and_equal_budget_keep_whole_score_ties(tmp_path):
    path = tmp_path / "scores.csv"
    grid(path, 3, [.9, .8, .5, .85, .8, *([0] * 18)],
         [.95, .91, .5, .9, .9, *([0] * 18)])
    result = evaluate(path).iloc[-1]
    assert (result.controls, result.false_alert_budget) == (20, 1)
    assert result.reference_true_positives == result.candidate_true_positives == 2
    assert result.candidate_false_positives == 2 and result.evidence == "over_budget"
    assert result.reference_true_positives_at_budget == 1
    assert result.candidate_true_positives_at_budget == 2
    assert (result.primary_gained, result.primary_lost) == (0, 0)


def test_pooled_budget_uses_one_cutoff_across_grids(tmp_path):
    first, second = tmp_path / "a.csv", tmp_path / "b.csv"
    grid(first, 2, [.6, .6] + [0] * 20, [.6, .6] + [0] * 20, prefix="a")
    grid(second, 2, [.8, .8] + [.9] * 20, [.8, .8] + [.9] * 20, prefix="b")
    result = evaluate(first, second)
    assert result.reference_true_positives_at_budget.tolist() == [2, 0, 0]
    with pytest.raises(ValueError, match="overlap"):
        evaluate(first, first)


def test_round_trip_preserves_a_score_one_float_above_the_cutoff(tmp_path):
    path = tmp_path / "scores.csv"
    above = np.nextafter(.5, 1.0)
    grid(path, 2, [.5, above, 0], [above, above, 0])
    row = evaluate(path).iloc[-1]
    assert row.reference_true_positives == 1 and row.primary_gained == 1


@pytest.mark.parametrize(("controls", "threshold"), [(19, .5), (100, np.inf)])
def test_insufficient_controls_or_calibration_withholds_decision(tmp_path, controls, threshold):
    path = tmp_path / "scores.csv"
    table = grid(path, 100, [0] * (100 + controls), [1] * 100 + [0] * controls)
    table.loc[table.detector == "new", "threshold"] = threshold
    table.to_csv(path, index=False)
    assert evaluate(path).iloc[-1].evidence == "insufficient_data"


@pytest.mark.parametrize(("task", "expected"), [
    ("main", (324, 864, 115, 97, 148, 57, 76, 43)),
    ("scope", (1458, 1944, 1417, 1418, 1436, 109, 2, 1)),
])
def test_replay_frozen_zero_shot_scores_without_inference(task, expected):
    directory = Path(__file__).resolve().parents[1] / "benchmarks" / "zero-shot"
    paths = [directory / f"{seed}.csv.gz" for seed in (20261123, 20261124, 20261125)]
    result = benchmark_round(paths, task, "logistic", "logistic+zero-shot")
    columns = ["positives", "controls", "reference_true_positives_at_budget",
               "candidate_true_positives_at_budget", "candidate_true_positives",
               "candidate_false_positives", "primary_gained", "primary_lost"]
    assert tuple(result.iloc[-1][columns]) == expected


@pytest.mark.parametrize(("positives", "caught", "expected"), [
    (12, 0, "inconclusive"), (1000, 0, "below_minimum"), (100, 35, "promising"),
    (0, 0, "insufficient_data"),
])
def test_small_samples_and_small_effects_have_distinct_verdicts(tmp_path, positives, caught, expected):
    path = tmp_path / "scores.csv"
    grid(path, positives, [0] * (positives + 40), [1] * caught + [0] * (positives + 40 - caught))
    row = evaluate(path).iloc[-1]
    assert row.evidence == expected
    assert (row.primary_gained, row.primary_lost) == (caught, 0)
    if positives:
        assert row.delta_low < row.primary_recall_delta < row.delta_high


def test_primary_scope_counts_only_one_file_and_keeps_hard_controls(tmp_path):
    path = tmp_path / "scores.csv"
    table = grid(path, 3, [0, .8, .8] + [0] * 21, [.8, 0, 0] + [0] * 21)
    table.loc[table.run_id == "run-2", "small_positive"] = False
    table.to_csv(path, index=False)
    row = evaluate(path).iloc[-1]
    assert row.positives == 3 and row.primary_positives == 2 and row.hard_controls == 21
    assert row.primary_gained == row.primary_lost == 1
    assert row.primary_recall_delta == 0


@pytest.mark.parametrize(("issue", "message"), [
    ("missing detector row", "same run ids"), ("label disagreement", "same run ids"),
    ("missing label", "invalid"), ("duplicate", "one score"),
    ("different cutoff", "frozen"), ("training", "independent"),
    ("nonfinite score", "finite scores"),
])
def test_invalid_or_unpaired_inputs_cannot_produce_evidence(tmp_path, issue, message):
    path = tmp_path / "bad.csv"
    table = grid(path, 2, [1, 0, 0], [1, 0, 0])
    if issue == "missing detector row":
        table = table.iloc[1:]
    elif issue == "label disagreement":
        table.loc[0, "small_positive"] = False
    elif issue == "missing label":
        table["positive"] = table.positive.astype(object)
        table.loc[0, "positive"] = ""
    elif issue == "different cutoff":
        table.loc[0, "threshold"] = .25
    elif issue == "training":
        table.loc[0, "test_set"] = "archive"
    elif issue == "nonfinite score":
        table["score"] = table.score.astype(float)
        table.loc[0, "score"] = np.inf
    else:
        table = pd.concat([table, table.iloc[[0]]])
    table.to_csv(path, index=False)
    with pytest.raises(ValueError, match=message):
        evaluate(path)
