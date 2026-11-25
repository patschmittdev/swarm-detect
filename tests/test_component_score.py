from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from swarmtrace.detect import COMPONENT_COLUMN, COMPONENT_RULE, RunDetector
from swarmtrace.detect.components import component_score
from swarmtrace.features import pair_features
from swarmtrace.trace.io import read_trace
from swarmtrace.trace.tiers import Tier


def pairs(*rows: tuple[str, str, int, int, int]) -> pd.DataFrame:
    return pd.DataFrame.from_records(rows, columns=[
        "agent_a", "agent_b", "direct_messages", "read_after_write", "shared_credential_logins",
    ]).set_index(["agent_a", "agent_b"])


def test_only_groups_with_observed_interactions_count() -> None:
    frame = pairs(("a", "b", 0, 0, 1), ("c", "d", 1, 0, 0), ("e", "f", 0, 1, 0),
                  ("b", "f", 0, 0, 0), ("g", "h", 0, 0, 0))
    frame["target_overlap"] = 1
    frame["label_pair"] = True
    assert component_score(frame) == 1 / 4
    renamed = frame.rename(index=dict(zip("abcdefgh", "zyxwvuts", strict=True)))
    assert component_score(renamed.iloc[::-1]) == 1 / 4


def test_bridge_unites_sharing_groups_and_repeated_evidence_counts_once() -> None:
    groups = pairs(("a", "b", 0, 0, 1), ("c", "d", 0, 0, 2))
    assert component_score(groups) == 2 / 3
    bridged = pd.concat([groups, pairs(("b", "c", 0, 1, 0))])
    assert component_score(bridged) == 1 / 2
    extra = pairs(("a", "d", 10, 20, 30), ("d", "e", 0, 0, 6))
    assert component_score(pd.concat([bridged, extra])) == 1 / 2


def test_no_sharing_has_zero_score() -> None:
    assert component_score(pairs()) == 0.0
    assert component_score(pairs(("a", "b", 2, 0, 0), ("a", "c", 0, 2, 0))) == 0.0


def test_score_requires_a_single_run() -> None:
    multiple = pd.concat([pairs(("a", "b", 0, 0, 1))] * 2, keys=["one", "two"], names=["run_id"])
    with pytest.raises(ValueError, match="single run"):
        component_score(multiple)


def test_raw_audit_pair_features_and_unavailable_access_log(fixtures_dir: Path) -> None:
    path = fixtures_dir / "credential_relay" / "trace.jsonl"
    assert component_score(pair_features(read_trace(path, Tier.V1))) == 2 / 4
    with pytest.raises(ValueError, match="shared_credential_logins"):
        component_score(pair_features(read_trace(path, Tier.V0)))


def test_run_detector_scores_the_component_feature() -> None:
    rows = pd.DataFrame({"direct_messages_max": [10, 0], COMPONENT_COLUMN: [0, 0.5]})
    labels = np.array([False, True])
    detector = RunDetector(COMPONENT_RULE, seed=1).fit(rows, labels)
    np.testing.assert_array_equal(detector.score(rows), [0, 0.5])
    with pytest.raises(ValueError, match=COMPONENT_COLUMN):
        detector.fit(rows.drop(columns=COMPONENT_COLUMN), labels)
