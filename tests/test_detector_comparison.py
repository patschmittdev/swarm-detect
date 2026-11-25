from pathlib import Path

import pandas as pd
import pytest

from swarmtrace.cli import main
from swarmtrace.detect import COMPONENT_COLUMN
from swarmtrace.eval.comparison import _cohort, _compare
from swarmtrace.eval.recorded import RunTable, TableRecord, write_run_table
from swarmtrace.features import feature_columns
from swarmtrace.features.spec import AGGREGATION, SCOPE
from swarmtrace.trace.context import ContextLevel
from swarmtrace.trace.tiers import Tier

DATA = Path(__file__).resolve().parents[1] / "data"


def twins(task: str) -> RunTable:
    # Give equal feature vectors opposite evaluation labels and different label-side metadata.
    columns = list(feature_columns("run", Tier.V1, (AGGREGATION,)))
    ids = pd.Index(["twin-a", "twin-b"], name="run_id")
    if task == "scope":
        columns.extend(f"{c}__C2" for c in feature_columns(
            "run", Tier.V1, (SCOPE,), context=ContextLevel.C2))
    else:
        columns.append(COMPONENT_COLUMN)
    runs = pd.DataFrame(0.0, columns=columns, index=ids)
    records = tuple(TableRecord(
        run, task == "scope" or i == 1,
        {"benign_sharing_teams": 1 - i, "offensive_group_size": 2, "violation_size": i,
         "offence_style": "scope_violation" if i else "credential_relay",
         "scope_mistake_rate": 0},
        {"objective_completed": i},
    ) for i, run in enumerate(ids))
    return RunTable(runs, records)


def test_cli_freezes_published_baselines_and_scores_opposite_label_twins(tmp_path):
    for task in ("main", "scope"):
        table = twins(task)
        write_run_table(tmp_path / task / "runs.csv.gz", table.features, table.records)
    out = tmp_path / "report.csv"
    scores = tmp_path / "scores.csv"
    main(["compare-detectors", "--data", str(DATA), "--seed", "20261120",
          "--test-tables", str(tmp_path), "--out", str(out), "--scores-out", str(scores)])
    results = pd.read_csv(out)
    archive = results[results.test_set == "archive"].set_index(["task", "detector"])
    fresh = results[results.test_set == "independent"].set_index(["task", "detector"])
    for key, expected in {
        ("main", "rule"): (7, 4), ("main", "logistic"): (14, 5), ("main", "boosted"): (13, 5),
        ("scope", "scope_rule"): (102, 1), ("scope", "logistic"): (140, 11),
        ("scope", "boosted"): (139, 10),
    }.items():
        assert tuple(archive.loc[key, ["true_positives", "false_positives"]]) == expected
    assert {"component_rule", "scope_breadth_rule", "sharing_logistic",
            "scope_logistic"} <= set(results.detector)
    pd.testing.assert_series_equal(archive.threshold, fresh.threshold)
    assert (fresh.positives == 1).all() and (fresh.controls == 1).all()
    assert (fresh.hard_controls == 1).all() and (fresh.small_positives == 1).all()
    assert (fresh.auroc == 0.5).all() and (fresh.average_precision == 0.5).all()
    assert (fresh.hard_control_auroc == 0.5).all()
    assert (fresh.accuracy_delta_vs_logistic == 0).all()
    assert fresh.delta_low.isna().all()  # One run per class cannot support a bootstrap interval.
    assert archive.loc[("scope", "scope_breadth_rule"), "accuracy_delta_vs_logistic"] == (
        pytest.approx((132 - 8 - (140 - 11)) / 339)
    )
    exports = pd.read_csv(scores)
    assert set(exports.test_set) == {"independent"} and set(exports.run_id) == {"twin-a", "twin-b"}
    assert not exports.duplicated(["task", "run_id", "detector"]).any()
    for key, group in exports.groupby(["task", "detector"]):
        assert group.score.nunique() == 1
        assert group.threshold.unique().tolist() == [fresh.loc[key, "threshold"]]
    round_csv = tmp_path / "round.csv"
    main(["benchmark-round", "--scores", str(scores), "--task", "scope", "--candidate", "boosted",
          "--out", str(round_csv)])
    assert pd.read_csv(round_csv).population.tolist() == ["grid", "pooled"]


def test_reused_run_id_is_rejected_for_independent_scoring():
    table = twins("main")
    with pytest.raises(ValueError, match="overlaps the archive"):
        _compare("main", table, 20261120, table)


def test_missing_scope_labelling_cannot_silently_turn_a_violation_into_a_control():
    table = twins("scope")
    record = table.records[1]
    incomplete = TableRecord(record.run_id, True, {"violation_size": 1})
    with pytest.raises(ValueError, match="offence_style"):
        _cohort(RunTable(table.features, (table.records[0], incomplete)), "scope")
