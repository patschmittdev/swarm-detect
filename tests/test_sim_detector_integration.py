from pathlib import Path

import numpy as np
import pandas as pd

from swarmtrace.detect import PairScorer, RunDetector
from swarmtrace.eval.data import build_tier_data, load_runs
from swarmtrace.features import feature_columns
from swarmtrace.sim.runner import Condition, run_one
from swarmtrace.trace.tiers import Tier


def test_simulator_relay_delegation_and_sloppy_sharing_reach_detectors(tmp_path: Path) -> None:
    for index, (size, sharing, channel) in enumerate((
        (5, 0, "message"), (5, 0, "shared_file"),
        (0, 0, "message"), (0, 0, "shared_file"),
        (5, 0, "message"), (5, 0, "shared_file"),
        (0, 100, "message"), (0, 0, "shared_file"),
    )):
        run_one(Condition(channel, "peer", size, 1, 96, sharing),
                index + 90, tmp_path / str(index))
    records = load_runs(tmp_path)
    data = build_tier_data(records, Tier.V1, checkpoint_every=96)
    run_cols = list(feature_columns("run", Tier.V1, ("aggregation",)))
    pair_cols = list(feature_columns("pair", Tier.V1, ("aggregation",)))
    training = [r.run_id for r in records if r.trace_path.parent.name in {"0", "1", "2", "3"}]
    test = [r for r in records if r.run_id not in training]
    y = np.array([data.records[r].positive for r in training])
    detector = RunDetector("logistic", 3).fit(data.runs.loc[training, run_cols], y)
    pair_train = data.pairs.index.get_level_values("run_id").isin(training)
    scorer = PairScorer(3, n_folds=2).fit(data.pairs.loc[pair_train, pair_cols],
                                        data.pair_labels[pair_train])
    proposals = scorer.propose(data.pairs.loc[~pair_train, pair_cols])
    scores = dict(zip([r.run_id for r in test],
                      detector.score(data.runs.loc[[r.run_id for r in test], run_cols])))
    delegated = next(r for r in test if not r.positive
                     and r.condition["benign_credential_sharing"] == 0)
    assert data.pairs.loc[delegated.run_id, "shared_credential_logins"].max() == 0
    for record in test:
        pairs = data.pairs.loc[record.run_id]
        if record.positive:
            relay = pd.Series([set(pair) <= record.offensive for pair in pairs.index],
                              index=pairs.index)
            assert pairs.loc[relay, "shared_credential_logins"].max() > 0
            assert any(len(group & record.offensive) >= 2 for group in proposals[record.run_id])
            assert scores[record.run_id] > scores[delegated.run_id]
        elif record.condition["benign_credential_sharing"] == 100:
            assert pairs["shared_credential_logins"].max() > 0
            assert scores[record.run_id] > scores[delegated.run_id]
