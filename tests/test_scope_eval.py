import gzip
import math
from collections import Counter
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import swarmtrace.eval.scope as scope_eval
from swarmtrace.detect import (
    FILES_RULE,
    FILES_RULE_COLUMN,
    RULE,
    RULE_COLUMN,
    SCOPE_RULE,
    RunDetector,
)
from swarmtrace.eval.data import RunRecord, load_runs
from swarmtrace.eval.harness import TOO_SMALL, child_seed
from swarmtrace.eval.recorded import TableRecord, load_run_table, write_run_table
from swarmtrace.eval.scope import (
    CONTEXTS,
    NOT_GATED,
    REFERENCE,
    SCOPE_DETECTORS,
    ScopeRow,
    evaluate_scope,
    labels_for,
    run_kind,
    scope_split,
    scope_table,
)
from swarmtrace.eval.splits import split_by_stratum
from swarmtrace.features import feature_columns
from swarmtrace.features.spec import SCOPE
from swarmtrace.sim.runner import Condition, run_one
from swarmtrace.trace.context import ContextLevel
from swarmtrace.trace.io import AgentLabel, Labels, RunPaths
from swarmtrace.trace.tiers import Tier

N_BOOTSTRAP = 20
SEED = 20261120


def make_record(index: int, kind: str, mistake: int, sharing: int = 0,
                size: int = 0) -> RunRecord:
    run_id = f"{index:016x}"
    positive = kind != "control"
    agents = {"a-00000001": AgentLabel("offensive" if positive else "benign_solo",
                                       "g-1" if positive else None),
              "a-00000002": AgentLabel("benign_team", "g-2")}
    condition: dict[str, int | str] = {
        "channel": "shared_file", "topology": "hub", "offensive_group_size": 2 if positive else 0,
        "offence_style": "scope_violation" if kind == "violation" else "credential_relay",
        "benign_sharing_teams": sharing, "scope": "on",
        "violation_size": size, "scope_mistake_rate": mistake,
    }
    return RunRecord(run_id, Path(run_id) / "trace.jsonl",
                     Labels(run_id, agents, positive, 10 if positive else None), condition)


def fixture_records() -> list[RunRecord]:
    """200 controls, 25 in-scope relays and 60 violations over mistake rates 0 and 5."""
    records: list[RunRecord] = []

    def add(kind: str, mistake: int, count: int, size: int = 0) -> None:
        for i in range(count):
            records.append(make_record(len(records), kind, mistake,
                                       sharing=int(i % 4 == 0), size=size))

    for mistake in (0, 5):
        add("control", mistake, 100)
    add("in_scope", 0, 20)
    add("in_scope", 5, 5)
    for mistake in (0, 5):
        for size in (1, 2, 5):
            add("violation", mistake, 10, size)
    return records


def fixture_table(records: list[RunRecord]) -> pd.DataFrame:
    """V1 columns of noise; the rule, breadth and out-of-scope columns are planted.

    Breadth (C0, C1, C2) is high for violations and for in-scope relays at mistake rate 5.
    Out-of-scope reads (C2) is 1 exactly for violations.
    """
    rng = np.random.default_rng(7)
    index = pd.Index([record.run_id for record in records], name="run_id")
    frame = pd.DataFrame(index=index)
    for column in feature_columns("run", Tier.V1):
        if column.endswith(("_n_above", "_n_at_or_below")):
            frame[column] = rng.integers(0, 3, len(records)).astype("int64")
        else:
            frame[column] = rng.normal(size=len(records))
    frame[RULE_COLUMN] = np.array([
        int(record.positive or record.condition["benign_sharing_teams"] > 0)
        for record in records], dtype="int64")
    kinds = [run_kind(record) for record in records]
    high = np.array([
        kind.startswith("violation") or (kind == "in_scope"
                                         and record.condition["scope_mistake_rate"] == 5)
        for kind, record in zip(kinds, records)])
    violation = np.array([kind.startswith("violation") for kind in kinds])
    for level in ContextLevel:
        for column in feature_columns("run", Tier.V1, (SCOPE,), context=level):
            if column == "borrowed_session_breadth_max":
                values = np.where(high, 9.0, 0.0)
            elif column == "out_of_scope_reads_borrowed_max":
                values = violation.astype(float)
            elif column.endswith("_n_above"):
                values = rng.integers(0, 3, len(records)).astype("int64")
            else:
                values = rng.normal(size=len(records))
            frame[f"{column}__{level.value}"] = values
    return frame


@pytest.fixture(scope="module")
def records() -> list[RunRecord]:
    return fixture_records()


@pytest.fixture(scope="module")
def table(records: list[RunRecord]) -> pd.DataFrame:
    return fixture_table(records)


@pytest.fixture(scope="module")
def rows(table: pd.DataFrame, records: list[RunRecord]) -> list[ScopeRow]:
    return evaluate_scope(table, records, SEED, N_BOOTSTRAP)


def pick(rows: list[ScopeRow], labelling: str, context: str, detector: str,
         metric: str) -> ScopeRow:
    found = [row for row in rows if (row.labelling, row.context, row.detector, row.metric)
             == (labelling, context, detector, metric)]
    assert len(found) == 1, (labelling, context, detector, metric, len(found))
    return found[0]


def test_labels_for_gives_exact_vectors_for_the_three_kinds() -> None:
    records = [make_record(0, "control", 0), make_record(1, "in_scope", 2),
               make_record(2, "violation", 5, size=1), make_record(3, "control", 2, sharing=1),
               make_record(4, "violation", 0, size=5)]
    ids = [record.run_id for record in records]
    assert labels_for(records, "legacy") == dict(zip(ids, [False, True, True, False, True]))
    assert labels_for(records, "strict") == dict(zip(ids, [False, False, True, False, True]))
    assert [run_kind(record) for record in records] == [
        "control", "in_scope", "violation_1", "control", "violation_5"]
    with pytest.raises(ValueError, match="labelling"):
        labels_for(records, "loose")


def test_split_by_stratum_sends_rounded_fraction_of_each_stratum_to_test() -> None:
    sizes = {"a": 10, "b": 7, "c": 3, "d": 1, "e": 15}
    ids, strata = [], []
    for name, count in sizes.items():
        for i in range(count):
            ids.append(f"{name}{i:03d}")
            strata.append(name)
    # Unsorted input order must not matter.
    ids, strata = ids[::-1], strata[::-1]
    train, test = split_by_stratum(ids, strata, 0.3, 11)
    assert not set(train) & set(test)
    assert sorted(train + test) == sorted(ids)
    assert list(train) == sorted(train) and list(test) == sorted(test)
    held = Counter(run[0] for run in test)
    assert {name: held.get(name, 0) for name in sizes} == {
        name: round(0.3 * count) for name, count in sizes.items()}
    assert split_by_stratum(ids, strata, 0.3, 11) == (train, test)
    assert split_by_stratum(list(reversed(ids)), list(reversed(strata)), 0.3, 11) == (train, test)
    assert split_by_stratum(ids, strata, 0.3, 12) != (train, test)
    with pytest.raises(ValueError):
        split_by_stratum(ids, strata, 1.0, 11)
    with pytest.raises(ValueError):
        split_by_stratum(ids, strata[:-1], 0.3, 11)
    with pytest.raises(ValueError):
        split_by_stratum(ids + ids[:1], strata + strata[:1], 0.3, 11)


def test_scope_split_matches_the_task_5_grid_counts() -> None:
    records: list[RunRecord] = []
    for mistake in (0, 2, 5):
        for _ in range(162):
            records.append(make_record(len(records), "control", mistake))
        for _ in range(54):
            records.append(make_record(len(records), "in_scope", mistake))
        for size in (1, 2, 5):
            for _ in range(54):
                records.append(make_record(len(records), "violation", mistake, size=size))
    assert len(records) == 1134
    split = scope_split(records, SEED)
    kinds = {record.run_id: run_kind(record) for record in records}
    test = Counter(kinds[run] for run in split.test)
    assert test["control"] == 147 and test["in_scope"] == 48
    assert sum(test[f"violation_{size}"] for size in (1, 2, 5)) == 144
    calibration = Counter(kinds[run] for run in split.calibration)
    assert calibration["control"] == 102
    assert calibration["control"] + calibration["in_scope"] == 135
    assert split.train == tuple(sorted(split.fitting + split.calibration))
    expected = split_by_stratum([r.run_id for r in records],
                                [scope_eval.stratum(r) for r in records], 0.3,
                                child_seed(SEED, 97, 0))
    assert (split.train, split.test) == expected


def test_rows_cover_labellings_contexts_and_detectors(rows: list[ScopeRow]) -> None:
    assert SCOPE_DETECTORS == (RULE, SCOPE_RULE, "logistic", "boosted", FILES_RULE)
    assert CONTEXTS == (REFERENCE, "C0", "C1", "C2")
    combos = {(row.labelling, row.context, row.detector) for row in rows if row.detector != "split"}
    assert combos == {(labelling, context, detector) for labelling in ("strict", "legacy")
                      for context in CONTEXTS for detector in SCOPE_DETECTORS}
    for row in rows:
        assert len(row.split_counts) == 6
        assert row.seed == SEED
    # Every row of a labelling carries that labelling's class counts.
    for labelling in ("strict", "legacy"):
        counts = {row.split_counts for row in rows if row.labelling == labelling}
        assert len(counts) == 1
    strict = next(row.split_counts for row in rows if row.labelling == "strict")
    legacy = next(row.split_counts for row in rows if row.labelling == "legacy")
    # Same runs in each set; in-scope relays move from positives to controls.
    assert [strict[i] + strict[i + 1] for i in (0, 2, 4)] == [
        legacy[i] + legacy[i + 1] for i in (0, 2, 4)]
    assert strict[4] - legacy[4] == 8 and legacy[5] - strict[5] == 8
    # In-scope relays are controls under strict in fitting and calibration too.
    assert strict[0] - legacy[0] == 12 and strict[2] - legacy[2] == 5


PLANTED = "out_of_scope_reads_borrowed_max__C2"


def _unaffected(row: ScopeRow) -> bool:
    """Rows whose feature set never contains the planted C2 column."""
    return row.context != "C2" or row.detector == RULE


def test_rows_without_the_planted_column_are_unchanged_when_it_is_removed(
    rows: list[ScopeRow], table: pd.DataFrame, records: list[RunRecord],
) -> None:
    """Both labellings: the aggregation-only reference, C0, C1, and ``rule`` everywhere."""
    removed = evaluate_scope(table.drop(columns=PLANTED), records, SEED, N_BOOTSTRAP)
    before = [row for row in rows if _unaffected(row)]
    after = [row for row in removed if _unaffected(row)]
    assert {row.labelling for row in before} == {"strict", "legacy"}
    assert {row.context for row in before} == {*CONTEXTS, "all"}
    assert _same(before, after)
    gone = [row for row in removed if row.context == "C2" and row.detector == SCOPE_RULE]
    assert gone and all(math.isnan(row.value) and row.note == scope_eval.NOT_AVAILABLE_SCOPE
                        for row in gone)


class Calls:
    """Records every fit and calibrate call of the detectors evaluate_scope builds."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.calls: list[tuple] = []
        calls = self.calls

        class Recording(RunDetector):
            def fit(self, features: pd.DataFrame, labels: np.ndarray) -> "Recording":
                calls.append(("fit", self.model, self.seed, tuple(features.columns),
                              tuple(features.index), tuple(bool(v) for v in labels)))
                return super().fit(features, labels)

            def calibrate(self, features: pd.DataFrame, labels: np.ndarray) -> "Recording":
                calls.append(("calibrate", self.model, self.seed, tuple(features.columns),
                              tuple(features.index), tuple(bool(v) for v in labels)))
                return super().calibrate(features, labels)

        monkeypatch.setattr(scope_eval, "RunDetector", Recording)

    def of(self, kind: str) -> list[tuple]:
        return [call for call in self.calls if call[0] == kind]


def _fit_seed(context: str, detector: str) -> int:
    return child_seed(SEED, 97, 2, CONTEXTS.index(context), SCOPE_DETECTORS.index(detector))


def test_c2_detectors_see_exactly_the_planted_column_and_separate_with_it(
    rows: list[ScopeRow], table: pd.DataFrame, records: list[RunRecord],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    aggregation = feature_columns("run", Tier.V1, ("aggregation",))
    scope = feature_columns("run", Tier.V1, (SCOPE,), context=ContextLevel.C2)
    assert PLANTED.removesuffix("__C2") in scope
    for frame, expected in (
        (table, aggregation + scope),
        (table.drop(columns=PLANTED),
         aggregation + tuple(c for c in scope if c != PLANTED.removesuffix("__C2"))),
    ):
        calls = Calls(monkeypatch)
        evaluate_scope(frame, records, SEED, 2)
        fitted = {call[1] for call in calls.of("fit")
                  if call[2] == _fit_seed("C2", call[1])}
        assert fitted == ({RULE, SCOPE_RULE, "logistic", "boosted"} if frame is table
                          else {RULE, "logistic", "boosted"})
        for call in calls.calls:
            if call[2] == _fit_seed("C2", call[1]):
                assert call[3] == expected
    for detector in (SCOPE_RULE, "logistic", "boosted"):
        assert pick(rows, "strict", "C2", detector, "auroc").value == 1.0
    assert pick(rows, "legacy", "C2", SCOPE_RULE, "auroc").value < 1.0


def _same(first: list[ScopeRow], second: list[ScopeRow]) -> bool:
    def key(row: ScopeRow) -> tuple:
        return tuple("nan" if isinstance(v, float) and math.isnan(v) else v
                     for v in (row.labelling, row.context, row.detector, row.metric, row.value,
                               row.low, row.high, row.n, row.total, row.note))
    return [key(row) for row in first] == [key(row) for row in second]


def test_strict_fpr_on_in_scope_relays_is_the_known_k_of_n(rows: list[ScopeRow]) -> None:
    # Breadth is 9 for violations and for the in-scope relays at mistake rate 5, 0 otherwise.
    # Stratified counts: 2 of the 8 test in-scope relays are at mistake rate 5, and 1 of 47
    # strict calibration controls scores 9, so the strict threshold is 0.
    threshold = pick(rows, "strict", "C0", SCOPE_RULE, "full_trace_threshold")
    assert threshold.value == 0.0
    fpr = pick(rows, "strict", "C0", SCOPE_RULE, "fpr_in_scope_relays")
    assert (fpr.n, fpr.total) == (2, 8)
    assert pick(rows, "strict", "C0", SCOPE_RULE, "false_positive_rate").n == 2
    assert pick(rows, "strict", "C0", SCOPE_RULE, "detection_rate").n == 18
    assert not [row for row in rows if row.labelling == "legacy"
                and row.metric == "fpr_in_scope_relays"]
    legacy = pick(rows, "legacy", "C0", SCOPE_RULE, "detection_rate_violation_size_0")
    assert (legacy.n, legacy.total) == (2, 8)
    assert pick(rows, "legacy", "C0", SCOPE_RULE, "false_positive_rate").n == 0
    for size in (1, 2, 5):
        row = pick(rows, "strict", "C0", SCOPE_RULE, f"detection_rate_violation_size_{size}")
        assert (row.n, row.total) == (6, 6)
    assert pick(rows, "strict", "C0", SCOPE_RULE, "fpr_mistake_rate_5").n == 2
    assert pick(rows, "strict", "C0", SCOPE_RULE, "fpr_mistake_rate_0").n == 0


def test_sharing_controls_are_exactly_the_benign_sharing_runs(
    rows: list[ScopeRow], records: list[RunRecord],
) -> None:
    split = scope_split(records, SEED)
    by_id = {record.run_id: record for record in records}
    sharing = [run for run in split.test if not by_id[run].positive
               and by_id[run].condition["benign_sharing_teams"] > 0]
    # The fixture has in-scope relays with a sharing team; they are not sharing controls.
    assert any(by_id[run].positive and by_id[run].condition["benign_sharing_teams"] > 0
               for run in split.test)
    in_scope = [run for run in split.test if run_kind(by_id[run]) == "in_scope"]
    for labelling, positives in (("strict", 18), ("legacy", 26)):
        row = pick(rows, labelling, "C0", RULE, "sharing_control_auroc")
        assert (row.control_runs, row.positive_runs) == (len(sharing), positives)
        assert row.value == 0.5
        sharing_fpr = pick(rows, labelling, "C0", RULE, "fpr_sharing_controls")
        assert sharing_fpr.total == len(sharing)
        unmatched = pick(rows, labelling, "C0", RULE, "in_scope_vs_sharing_auroc")
        assert unmatched.status == NOT_GATED == "reported, not gated"
        assert (unmatched.positive_runs, unmatched.control_runs) == (len(in_scope), len(sharing))
        assert unmatched.value == 0.5
    assert all(row.status == "" for row in rows if row.metric != "in_scope_vs_sharing_auroc")


def test_scope_rule_is_absent_without_its_column(rows: list[ScopeRow]) -> None:
    reference = [row for row in rows if row.context == REFERENCE and row.detector == SCOPE_RULE]
    assert reference and all(math.isnan(row.value) and row.note == scope_eval.NOT_AVAILABLE_SCOPE
                             for row in reference)
    # At C0 its score is the breadth column, at C2 the out-of-scope column.
    assert pick(rows, "strict", "C2", SCOPE_RULE, "full_trace_threshold").value == 0.0
    assert pick(rows, "strict", "C2", SCOPE_RULE, "fpr_in_scope_relays").n == 0
    assert pick(rows, "strict", "C1", SCOPE_RULE, "fpr_in_scope_relays").n == 2


def test_too_few_calibration_controls_never_fires(records: list[RunRecord]) -> None:
    small = [r for r in records if run_kind(r) != "control" or int(r.run_id, 16) % 10 == 0]
    table = fixture_table(records).loc[[r.run_id for r in small]]
    found = evaluate_scope(table, small, SEED, N_BOOTSTRAP)
    calibration = pick(found, "legacy", "all", "split", "calibration_controls")
    assert calibration.value < 19
    threshold = pick(found, "legacy", "C0", RULE, "full_trace_threshold")
    assert math.isinf(threshold.value) and threshold.note == TOO_SMALL
    assert pick(found, "legacy", "C0", RULE, "detection_rate").n == 0


def test_no_label_condition_or_outcome_column_reaches_a_detector(
    table: pd.DataFrame, records: list[RunRecord], tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[tuple[str, tuple[str, ...]]] = []

    class Recording(RunDetector):
        def fit(self, features: pd.DataFrame, labels: np.ndarray) -> "Recording":
            seen.append((self.model, tuple(features.columns)))
            return super().fit(features, labels)

    path = tmp_path / "runs.csv.gz"
    write_run_table(path, table.assign(**{FILES_RULE_COLUMN: 4}), records,
                    extra={record.run_id: {"tasks_completed": 3} for record in records})
    loaded = load_run_table(path)
    pd.testing.assert_frame_equal(loaded.features, table, check_exact=True)
    assert list(loaded.diagnostics) == [FILES_RULE_COLUMN]
    rewritten = tmp_path / "roundtrip.csv.gz"
    write_run_table(rewritten, pd.concat([loaded.features, loaded.diagnostics], axis=1),
                    loaded.records, extra={r.run_id: r.outcomes for r in loaded.records})
    assert rewritten.read_bytes() == path.read_bytes()
    assert all(FILES_RULE_COLUMN not in feature_columns("run", Tier.V1, families,
                                                       context=ContextLevel.C2)
               for families in (None, ("generic",), ("aggregation",), ("scope",)))
    monkeypatch.setattr(scope_eval, "RunDetector", Recording)
    diagnostics = []
    found = evaluate_scope(loaded.features, loaded.records, SEED, 2,
                           diagnostics=loaded.diagnostics, calibration_rows=diagnostics)
    assert seen
    assert not any(column.startswith(("label_", "condition_", "outcome_", "run_id"))
                   for _, columns in seen for column in columns)
    assert not any("__C" in column for _, columns in seen for column in columns)
    assert {columns for model, columns in seen if model == FILES_RULE} == {(FILES_RULE_COLUMN,)}
    assert all(FILES_RULE_COLUMN not in columns for model, columns in seen if model != FILES_RULE)
    for labelling in ("strict", "legacy"):
        for context in CONTEXTS:
            assert pick(found, labelling, context, FILES_RULE, "auroc").value == 0.5
            assert pick(found, labelling, context, FILES_RULE, scope_eval.THRESHOLD).value == 4
    for row in diagnostics:
        assert row.rank == math.ceil((row.calibration_controls + 1) * 0.95)
        if row.detector == FILES_RULE:
            # Equal-to-threshold counts must include ties; flags still use strictly greater.
            assert row.above_zero == row.at_or_above_threshold == row.total
            assert row.threshold == 4
        if row.labelling == "legacy":
            assert row.control_kind != "in_scope"
    for prefix in ("label_positive", "condition_scope", "outcome_x"):
        with pytest.raises(ValueError, match="label-side"):
            evaluate_scope(table.assign(**{prefix: 1}), records, SEED, 2)


def test_files_rule_and_calibration_diagnostics_preserve_existing_rows_and_seeds(
    table: pd.DataFrame, records: list[RunRecord], monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Parameter-free stand-in keeps this preservation check cheap; record exact inputs/seeds.
    calls = []

    class RecordingRule(RunDetector):
        def fit(self, features: pd.DataFrame, labels: np.ndarray) -> "RecordingRule":
            calls.append((self.model, self.seed, features.copy(), labels.copy()))
            self.columns = tuple(features.columns)
            return self

        def score(self, features: pd.DataFrame) -> np.ndarray:
            assert tuple(features.columns) == self.columns
            column = FILES_RULE_COLUMN if self.model == FILES_RULE else RULE_COLUMN
            return features[column].to_numpy(dtype=float)

    monkeypatch.setattr(scope_eval, "RunDetector", RecordingRule)
    baseline = evaluate_scope(table, records, SEED, 2)
    before = calls[:]
    calls.clear()
    diagnostics = pd.DataFrame({FILES_RULE_COLUMN: np.arange(len(table))}, index=table.index)
    calibration = []
    extended = evaluate_scope(table, records, SEED, 2, diagnostics=diagnostics,
                              calibration_rows=calibration)
    assert repr([row for row in baseline if row.detector != FILES_RULE]) == repr(
        [row for row in extended if row.detector != FILES_RULE])
    after = [call for call in calls if call[0] != FILES_RULE]
    assert len(before) == len(after)
    for old, new in zip(before, after, strict=True):
        assert old[:2] == new[:2]
        pd.testing.assert_frame_equal(old[2], new[2], check_exact=True)
        np.testing.assert_array_equal(old[3], new[3])
    split = scope_split(records, SEED)
    by_id = {record.run_id: record for record in records}
    for row in calibration:
        labels = labels_for(records, row.labelling)
        ids = [run for run in split.calibration if not labels[run]]
        kinds = {run: ("in_scope" if run_kind(by_id[run]) == "in_scope" else
                       "sharing" if by_id[run].condition["benign_sharing_teams"] > 0 else
                       "nonsharing") for run in ids}
        selected = [run for run in ids if kinds[run] == row.control_kind]
        assert row.total == len(selected)
        if row.note:
            assert row.above_zero is row.at_or_above_threshold is None
        else:
            source = (diagnostics[FILES_RULE_COLUMN] if row.detector == FILES_RULE
                      else table[RULE_COLUMN])
            assert row.above_zero == int((source.loc[selected] > 0).sum())
            assert row.at_or_above_threshold == int((source.loc[selected] >= row.threshold).sum())


def test_rows_are_identical_from_records_and_from_a_loaded_table(
    rows: list[ScopeRow], table: pd.DataFrame, records: list[RunRecord], tmp_path: Path,
) -> None:
    path = tmp_path / "runs.csv.gz"
    write_run_table(path, table, records)
    loaded = load_run_table(path)
    assert _same(rows, evaluate_scope(loaded.features, loaded.records, SEED, N_BOOTSTRAP))


def test_run_table_round_trips_exactly(tmp_path: Path) -> None:
    records = [make_record(0, "control", 0), make_record(1, "violation", 5, sharing=1, size=2),
               make_record(2, "in_scope", 2)]
    records[0] = replace(records[0], condition={
        key: value for key, value in records[0].condition.items() if key != "scope"})
    records[1] = replace(records[1], condition={**records[1].condition, "loud_reuses": 2})
    features = pd.DataFrame({
        "count_n_above": np.array([0, 3, -1], dtype="int64"),
        "integral_max": [1.0, 2.0, -0.0],
        "ratio_top_k_mean": [0.1, math.nan, 1 / 3],
        "tiny": [1e-300, 2.5e17, math.inf],
    }, index=pd.Index([record.run_id for record in records], name="run_id"))
    extra = {records[0].run_id: {"tasks_completed": 4, "violation": "read"},
             records[2].run_id: {"tasks_completed": 0}}
    path = tmp_path / "table" / "runs.csv.gz"
    write_run_table(path, features, records, extra=extra)
    with gzip.open(path, "rb") as source:
        text = source.read().decode("utf-8")
    assert "\r" not in text
    header = text.split("\n", 1)[0].split(",")
    assert header[:5] == ["run_id", "count_n_above", "integral_max", "ratio_top_k_mean", "tiny"]
    assert header[5] == "label_positive"
    assert header[6:] == sorted(header[6:])
    assert path.read_bytes()[4:8] == b"\x00\x00\x00\x00"
    loaded = load_run_table(path)
    pd.testing.assert_frame_equal(loaded.features, features, check_exact=True)
    assert list(loaded.features.dtypes) == ["int64", "float64", "float64", "float64"]
    assert math.copysign(1.0, loaded.features["integral_max"].iloc[2]) == -1.0
    assert loaded.records == tuple(
        TableRecord(record.run_id, record.positive, dict(record.condition),
                    dict(extra.get(record.run_id, {})))
        for record in records)
    assert labels_for(loaded.records, "strict") == labels_for(records, "strict")
    again = tmp_path / "again.csv.gz"
    write_run_table(again, loaded.features, loaded.records,
                    extra={record.run_id: record.outcomes for record in loaded.records})
    assert again.read_bytes() == path.read_bytes()


def test_run_table_refuses_ambiguous_or_misaligned_input(tmp_path: Path) -> None:
    records = [make_record(0, "control", 0), make_record(1, "in_scope", 0)]
    index = pd.Index([record.run_id for record in records], name="run_id")
    features = pd.DataFrame({"x": [1.0, 2.0]}, index=index)
    path = tmp_path / "runs.csv.gz"
    with pytest.raises(ValueError, match="run ids"):
        write_run_table(path, features.iloc[::-1], records)
    with pytest.raises(ValueError, match="dtype"):
        write_run_table(path, features.astype(str), records)
    with pytest.raises(ValueError, match="label_"):
        write_run_table(path, features.assign(label_x=1.0), records)
    numeric = replace(records[0], condition={**records[0].condition, "channel": "12"})
    with pytest.raises(ValueError, match="channel"):
        write_run_table(path, features, [numeric, records[1]])
    with pytest.raises(ValueError, match="outcome"):
        write_run_table(path, features, records, extra={records[0].run_id: {"flag": True}})
    assert not path.exists()


def _seed(index: int) -> int:
    return child_seed(SEED, 197, index)


@pytest.fixture(scope="module")
def simulated(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("scope-runs")
    conditions = [
        Condition("shared_file", "hub", 0, 2, scope="on", scope_mistake_rate=5),
        Condition("message", "peer", 0, 2, scope="on", benign_credential_sharing=100),
        Condition("shared_file", "hub", 2, 2, scope="on"),
        Condition("message", "hub", 3, 2, scope="on", violation_size=2, scope_mistake_rate=2),
    ]
    for index, condition in enumerate(conditions):
        run_one(condition, _seed(index), root / f"run{index}")
    return root


def test_scope_table_from_simulated_runs(simulated: Path, tmp_path: Path) -> None:
    records = load_runs(simulated)
    frame = scope_table(records, workers=1)
    base = list(feature_columns("run", Tier.V1))
    suffixed = [f"{column}__{level.value}" for level in ContextLevel
                for column in feature_columns("run", Tier.V1, (SCOPE,), context=level)]
    assert list(frame.columns) == base + suffixed
    assert list(frame.index) == sorted(record.run_id for record in records)
    assert frame.index.name == "run_id"
    assert not any(column.startswith(("label_", "condition_", "outcome_"))
                   for column in frame.columns)
    c0 = [column for column in frame.columns if column.endswith("__C0")]
    assert c0 and all(column.removesuffix("__C0") + "__C1" in frame for column in c0)
    for column in c0:
        pd.testing.assert_series_equal(
            frame[column], frame[column.removesuffix("__C0") + "__C1"], check_names=False)
    assert frame["borrowed_session_breadth_max__C0"].max() > 0
    pd.testing.assert_frame_equal(scope_table(records, workers=2), frame)
    path = tmp_path / "runs.csv.gz"
    write_run_table(path, frame, records)
    pd.testing.assert_frame_equal(load_run_table(path).features, frame, check_exact=True)


def test_scope_table_refuses_runs_without_context(tmp_path: Path) -> None:
    run_one(Condition("shared_file", "hub", 0, 2), _seed(9), tmp_path / "off")
    with pytest.raises(ValueError, match="context.json"):
        scope_table(load_runs(tmp_path), workers=1)
    assert not RunPaths(tmp_path / "off").context.exists()


def _kinds(records: list[RunRecord]) -> np.ndarray:
    return np.array([run_kind(record) for record in records])


def _hardest(rows: list[ScopeRow], suffix: str = "") -> ScopeRow:
    return pick(rows, "strict", "C2", SCOPE_RULE, scope_eval.HARDEST + suffix)


def test_violation_against_in_scope_auroc_separates_perfectly_when_overall_does_not(
    table: pd.DataFrame, records: list[RunRecord],
) -> None:
    kinds = _kinds(records)
    sharing = np.array([not r.positive and r.condition["benign_sharing_teams"] > 0
                        for r in records])
    planted = table.copy()
    # Violations score 1 and in-scope relays 0; so do benign sharing controls, which keeps the
    # overall strict AUROC below 1.
    planted[PLANTED] = (np.char.startswith(kinds.astype(str), "violation_") | sharing).astype(float)
    found = evaluate_scope(planted, records, SEED, N_BOOTSTRAP)
    assert pick(found, "strict", "C2", SCOPE_RULE, "auroc").value < 1.0
    hardest = _hardest(found)
    assert (hardest.value, hardest.positive_runs, hardest.control_runs) == (1.0, 18, 8)
    assert hardest.note == "" and hardest.interval == "bootstrap"
    assert hardest.requested == N_BOOTSTRAP and hardest.valid == N_BOOTSTRAP
    for size in (1, 2, 5):
        cell = _hardest(found, f"_size_{size}")
        assert (cell.value, cell.positive_runs, cell.control_runs) == (1.0, 6, 8)
    for rate, counts in ((0, (9, 6)), (5, (9, 2))):
        cell = _hardest(found, f"_mistake_rate_{rate}")
        assert (cell.value, cell.positive_runs, cell.control_runs) == (1.0, *counts)
    # Strict only, for every context and detector.
    assert not [row for row in found if row.labelling == "legacy"
                and row.metric.startswith(scope_eval.HARDEST)]
    assert {(row.context, row.detector) for row in found
            if row.metric == scope_eval.HARDEST} == {
        (context, detector) for context in CONTEXTS for detector in SCOPE_DETECTORS}


def test_violation_against_in_scope_auroc_is_at_chance_when_they_score_alike(
    table: pd.DataFrame, records: list[RunRecord],
) -> None:
    planted = table.copy()
    planted[PLANTED] = np.array([float(r.positive) for r in records])
    found = evaluate_scope(planted, records, SEED, N_BOOTSTRAP)
    assert pick(found, "strict", "C2", SCOPE_RULE, "auroc").value > 0.5
    assert _hardest(found).value == 0.5
    for suffix in ("_size_1", "_size_2", "_size_5", "_mistake_rate_0", "_mistake_rate_5"):
        assert _hardest(found, suffix).value == 0.5


def test_violation_against_in_scope_cells_are_undefined_when_a_class_is_empty(
    records: list[RunRecord],
) -> None:
    kept = [r for r in records
            if not (run_kind(r) == "in_scope" and r.condition["scope_mistake_rate"] == 5)]
    found = evaluate_scope(fixture_table(records).loc[[r.run_id for r in kept]], kept, SEED, 5)
    cell = _hardest(found, "_mistake_rate_5")
    assert math.isnan(cell.value) and cell.note == scope_eval.NO_IN_SCOPE
    assert (cell.positive_runs, cell.control_runs) == (9, 0)
    assert _hardest(found, "_mistake_rate_0").note == ""


def test_hardest_negative_bootstrap_seeds_collide_with_no_other(
    rows: list[ScopeRow], records: list[RunRecord],
) -> None:
    keys = []
    for li in range(2):
        for ci in range(len(CONTEXTS)):
            for di in range(len(SCOPE_DETECTORS)):
                keys += [(li, ci, di, k) for k in scope_eval.AUROC_KEYS.values()]
                keys += [(li, ci, di, 3, scope_eval.SIZE_CELL, s) for s in (1, 2, 5)]
                keys += [(li, ci, di, 3, scope_eval.MISTAKE_CELL, m) for m in (0, 2, 5)]
    seeds = [child_seed(SEED, 97, 3, *key) for key in keys]
    assert len(set(seeds)) == len(seeds)
    assert sorted(scope_eval.AUROC_KEYS.values()) == [0, 1, 2, 3]


def _calibration_table(records: list[RunRecord]) -> pd.DataFrame:
    """Breadth: benign 0, in-scope relays 5 (7 at mistake rate 5), violations 9."""
    planted = fixture_table(records)
    values = np.array([
        9.0 if kind.startswith("violation") else 0.0 if kind == "control"
        else 7.0 if record.condition["scope_mistake_rate"] == 5 else 5.0
        for kind, record in zip(_kinds(records), records)])
    for level in ("C0", "C1", "C2"):
        planted[f"borrowed_session_breadth_max__{level}"] = values
    return planted


def test_strict_calibration_counts_in_scope_relays_as_controls(
    records: list[RunRecord], monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = Calls(monkeypatch)
    found = evaluate_scope(_calibration_table(records), records, SEED, 2)
    # Strict calibration controls: 42 benign at 0, 4 in-scope at 5 and 1 at 7. The conformal
    # rank is ceil(48 * 0.95) = 46, so the threshold is 5; with legacy labels it would be 0.
    assert pick(found, "strict", "C0", SCOPE_RULE, "full_trace_threshold").value == 5.0
    assert pick(found, "legacy", "C0", SCOPE_RULE, "full_trace_threshold").value == 0.0
    fpr = pick(found, "strict", "C0", SCOPE_RULE, "fpr_in_scope_relays")
    assert (fpr.n, fpr.total) == (2, 8)
    overall = pick(found, "strict", "C0", SCOPE_RULE, "false_positive_rate")
    assert (overall.n, overall.total) == (2, 68)
    assert pick(found, "strict", "C0", SCOPE_RULE, "detection_rate").n == 18

    split = scope_split(records, SEED)
    fitted = 4 * len(CONTEXTS) - 1  # scope_rule is not available at the reference
    for kind, runs in (("fit", split.fitting), ("calibrate", split.calibration)):
        made = calls.of(kind)
        assert len(made) == 2 * fitted
        for labelling, part in (("strict", made[:fitted]), ("legacy", made[fitted:])):
            labels = labels_for(records, labelling)
            expected = tuple(labels[run] for run in runs)
            for call in part:
                assert call[4] == runs
                assert call[5] == expected, (kind, labelling, call[1])
    strict_cal = tuple(labels_for(records, "strict")[run] for run in split.calibration)
    legacy_cal = tuple(labels_for(records, "legacy")[run] for run in split.calibration)
    assert sum(strict_cal) + 5 == sum(legacy_cal)


def test_run_table_refuses_an_empty_table(tmp_path: Path) -> None:
    empty = pd.DataFrame({"x": np.array([], dtype="int64")},
                         index=pd.Index([], name="run_id"))
    path = tmp_path / "runs.csv.gz"
    with pytest.raises(ValueError, match="empty run table"):
        write_run_table(path, empty, [])
    assert not path.exists()
