import json
from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from swarmtrace.eval.recorded import TableRecord
from swarmtrace.eval.rounds import benchmark_round
from swarmtrace.reproduce import read_round as rr
from swarmtrace.reproduce.config import RunJob
from swarmtrace.sim.runner import Condition


def sample(prefix, i, *, confirmation=False, signal=0):
    positive = i % 3 == 0
    in_scope = not positive and i % 5 == 0
    channel = rr.CONFIRMATION_CHANNEL if confirmation else rr.DEVELOPMENT_CHANNELS[i % 2]
    condition = {
        "channel": channel, "topology": ("hub", "peer")[i % 2],
        "scope_mistake_rate": 0, "benign_sharing_teams": int(i % 2 == 0),
        "offence_style": "scope_violation" if positive else "credential_relay",
        "violation_size": 1 if positive else 0, "offensive_group_size": 2 if positive else 0,
    }
    ticks = (0, 8, 15) if confirmation else (15,)
    frames = pd.DataFrame(
        {column: [float(i % 7 + (t > 0)) for t in ticks] for column in rr.BASE_COLUMNS},
        index=pd.Index(ticks, name="tick"),
    )
    frames[rr.SECOND_READER] = [signal if t == 15 else 0 for t in ticks]
    return rr._ObservedRun(
        TableRecord(f"{prefix}-{i:03d}", positive or in_scope, condition),
        frames, 12 if positive else None, dict.fromkeys(rr.READ_COUNTS, 0), False,
    )


def test_native_confirmation_smoke_keeps_every_read_and_inclusive_checkpoints():
    condition = Condition(channel="preplanned", topology="peer", coordinated_groups=1,
                          offensive_group_size=2, scope="on", violation_size=1, n_ticks=17)
    observed = rr._observe((RunJob("scope", "smoke", 712, condition), False))
    assert observed is not None
    assert observed.features.index.tolist() == [0, 8, 16]
    assert observed.features.columns.tolist() == [*rr.BASE_COLUMNS, rr.SECOND_READER]
    assert observed.counts["successful_reads"] > 0
    assert observed.counts["successful_reads"] == sum(
        observed.counts[key] for key in ("grant_reads", "unknown_reads", "ordinary_reads"))
    assert observed.counts["missing_decisions"] == 0
    assert rr._observe((RunJob("scope", "smoke", 712, condition), True)) is None


def test_workflow_split_fits_only_declared_data_and_preserves_constant_feature_ties():
    development = [sample("dev", i) for i in range(300)]
    models, protocol = rr._fit(development)
    partitions = [set(row["run_ids"]) for row in protocol["partitions"].values()]
    assert set.union(*partitions) == {r.record.run_id for r in development}
    assert sum(map(len, partitions)) == len(development)
    assert protocol["constant_added_column"] and not protocol["feature_varies_in_fit"]
    assert len(rr.BASE_COLUMNS) == 15 and models[rr.CANDIDATE].columns == models[rr.REFERENCE].columns
    assert models[rr.CANDIDATE].threshold == models[rr.REFERENCE].threshold
    tests = [sample("held", i, confirmation=True, signal=i % 2) for i in range(24)]
    scores = rr._score(tests, models)
    pair = scores.pivot(index="run_id", columns="detector", values="score")
    np.testing.assert_array_equal(pair[rr.CANDIDATE], pair[rr.REFERENCE])
    timed = scores.pivot(index="run_id", columns="detector", values="first_alert_tick")
    pd.testing.assert_series_equal(timed[rr.CANDIDATE], timed[rr.REFERENCE], check_names=False)
    with pytest.raises(ValueError, match="held-out workflow"):
        rr._fit([*development, replace(development[0], preplanned_background=True)])


def test_varying_fitting_signal_adds_just_one_feature():
    models, fit = rr._fit([sample("dev", i, signal=i % 2) for i in range(300)])
    assert fit["feature_varies_in_fit"] and not fit["constant_added_column"]
    assert models[rr.CANDIDATE].columns == (*models[rr.REFERENCE].columns, rr.SECOND_READER)


def test_timing_distinguishes_same_tick_missing_objectives_and_anytime_control_alerts():
    rows = pd.DataFrame({
        "positive": [True, True, True, False, False, True], "score": [.9, .3, .3, .7, .4, .2],
        "threshold": .5, "first_alert_tick": pd.array([8, 8, 8, 0, 0, None], dtype="Int64"),
        "objective_tick": pd.array([9, 8, None, None, 3, 0], dtype="Int64"),
        "small_positive": [True, True, True, False, False, False],
        "two_agent_positive": [True, True, True, False, False, True],
        "hard_control": [False, False, False, True, False, False],
        "sharing_control": [False, False, False, False, True, False],
        "preplanned_background": False, rr.SECOND_READER: [1, 0, 0, 1, 0, 0],
        **dict.fromkeys(rr.READ_COUNTS, 0),
    })
    results = rr._diagnose(rows)
    assert results["positive_with_objective_after_zero"] == 2
    assert results["positive_strictly_before_objective"] == results["positive_first_alert_at_objective"] == 1
    assert results["positive_with_tick_zero_objective"] == results["positive_without_objective"] == 1
    assert results["positive_alert_without_objective"] == 1
    assert results["control_any_checkpoint_alert"] == 2 and results["false_positives"] == 1
    assert results["control_strictly_before_objective"] == 1
    assert results["positive_with_signal"] == results["controls_with_signal"] == 1


def test_round_exports_paired_scores_and_rejects_reused_runs_atomically(tmp_path, monkeypatch):
    development = [sample("dev", i) for i in range(300)]
    held = [sample("test", i, confirmation=True) for i in range(24)]
    monkeypatch.setattr(rr, "CONFIRMATION_SEEDS", (71, 72))
    monkeypatch.setattr(rr, "_observe", lambda task: task[0])
    monkeypatch.setattr(rr, "_jobs", lambda seed, _: development if seed == rr.ARCHIVE_SEED else held)
    out = tmp_path / "round"
    with pytest.raises(ValueError, match="disjoint"):
        rr.run_read_round(out, 1)
    assert not out.exists()
    monkeypatch.setattr(rr, "CONFIRMATION_SEEDS", (71,))
    rr.run_read_round(out, 1)
    protocol = json.loads((out / "protocol.json").read_text())
    assert protocol["confirmation_nonzero_runs"] == 0 and not protocol["feature_varies_in_fit"]
    assert protocol["development_eligible"] == len(development)
    assert protocol["checkpoints"] == list(range(0, 160, 8)) + [159]
    result = benchmark_round([out / "71.csv.gz"], "scope", rr.REFERENCE, rr.CANDIDATE).iloc[-1]
    assert result.primary_gained == result.primary_lost == 0
    diagnostics = pd.read_csv(out / "diagnostics.csv")
    pooled = diagnostics[(diagnostics.grid == "pooled") & (diagnostics.topology == "all")]
    assert set(pooled.detector) == {rr.CANDIDATE, rr.REFERENCE}
    assert (pooled.runs == len(held)).all()
