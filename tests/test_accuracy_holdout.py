import pytest

from swarmtrace.detect import COMPONENT_COLUMN
from swarmtrace.eval.recorded import load_run_table
from swarmtrace.eval.scope import STRICT, labels_for
from swarmtrace.features import feature_columns
from swarmtrace.features.spec import AGGREGATION, SCOPE
from swarmtrace.reproduce import accuracy_holdout
from swarmtrace.reproduce.config import RunJob
from swarmtrace.sim.runner import Condition
from swarmtrace.trace.context import ContextLevel
from swarmtrace.trace.tiers import Tier


def test_holdout_writes_native_tables_and_preserves_existing_output(tmp_path, monkeypatch):
    main_job = RunJob("main", "main-0", 1, Condition("message", "peer", 0, 1, 24))
    scope_job = RunJob("scope", "scope-0", 2, Condition("message", "peer", 2, 1, 24,
                                                       scope="on", violation_size=1))
    monkeypatch.setattr(accuracy_holdout, "make_jobs", lambda config: (main_job,))
    monkeypatch.setattr(accuracy_holdout, "make_scope_jobs", lambda config: (scope_job,))
    root = tmp_path / "holdout"
    accuracy_holdout.write_holdout_tables(root, 20261123, workers=1)
    main = load_run_table(root / "main/runs.csv.gz")
    scope = load_run_table(root / "scope/runs.csv.gz")
    aggregation = feature_columns("run", Tier.V1, (AGGREGATION,))
    c2 = feature_columns("run", Tier.V1, (SCOPE,), context=ContextLevel.C2)
    assert tuple(main.features.columns) == (*aggregation, COMPONENT_COLUMN)
    assert tuple(scope.features.columns) == (*aggregation, *(f"{key}__C2" for key in c2))
    assert not main.records[0].positive
    assert labels_for(scope.records, STRICT) == {scope.records[0].run_id: True}
    original = (root / "scope/runs.csv.gz").read_bytes()
    with pytest.raises(ValueError, match="already exists"):
        accuracy_holdout.write_holdout_tables(root, 20261124, workers=1)
    assert (root / "scope/runs.csv.gz").read_bytes() == original
