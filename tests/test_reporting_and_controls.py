import csv
import gzip
import json
import math
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from swarmtrace.cli import main
from swarmtrace.detect import RULE, RULE_COLUMN
from swarmtrace.eval.data import TierData, build_tier_data, load_runs
from swarmtrace.eval.diagnostics import split_stability
from swarmtrace.eval.harness import (
    DETECTORS,
    NOT_AVAILABLE_FAMILY,
    NOT_AVAILABLE_TIER,
    EvalConfig,
    MetricRow,
    SplitResult,
    child_seed,
    evaluate_split,
)
from swarmtrace.eval.headline import format_headline, format_readme_headline
from swarmtrace.eval.metrics import auroc, wilson
from swarmtrace.eval.recorded import load_recorded, write_gzip, write_recorded
from swarmtrace.eval.report import format_tier
from swarmtrace.eval.splits import Split, split_by_run
from swarmtrace.features import feature_columns, run_features
from swarmtrace.reproduce.config import ReproduceConfig
from swarmtrace.reproduce.controls import (
    LOUD_GATING_BARS,
    NOT_GATED,
    above_calibration_controls,
    loud_bar_rows,
    negative_control,
    require_loud_detection,
)
from swarmtrace.reproduce.pipeline import _control_rows, render_readme
from swarmtrace.sim.runner import Condition, run_one
from swarmtrace.trace.io import read_trace
from swarmtrace.trace.tiers import Tier

DATA = Path(__file__).resolve().parents[1] / "data"


def test_wilson_retains_uncertainty_at_zero_and_one() -> None:
    zero, all_runs = wilson(0, 18), wilson(18, 18)
    assert zero.value == zero.low == 0
    assert zero.high == pytest.approx(0.1758792236)
    assert all_runs.high == all_runs.value == 1
    assert all_runs.low == pytest.approx(1 - zero.high)
    assert zero.requested == zero.valid == 0
    assert math.isnan(wilson(0, 0).value)
    with pytest.raises(ValueError):
        wilson(19, 18)


@pytest.fixture(scope="module")
def v1_data(tmp_path_factory: pytest.TempPathFactory) -> TierData:
    root = tmp_path_factory.mktemp("reporting_runs")
    for index in range(12):
        run_one(Condition("message", "peer", 2 if index % 2 else 0, 1, 40,
                          benign_credential_sharing=100 if index % 4 == 0 else 0),
                800 + index, root / str(index))
    return build_tier_data(load_runs(root), Tier.V1, checkpoint_every=40)


def test_new_metrics_reuse_flags_and_wilson_intervals(v1_data: TierData) -> None:
    data = v1_data
    ids = sorted(data.records)
    config = EvalConfig(seed=5, n_bootstrap=4, n_folds=2, families=("aggregation",))
    split = split_by_run(ids, [data.records[r].positive for r in ids], 0.3, child_seed(5, 0))
    result = evaluate_split(data, split, config, child_seed(5, 1, 0), family="aggregation")
    positives = [r for r in split.test if data.records[r].positive]
    rows = {(row.method, row.metric): row for row in result.rows}
    for method in ("volume", "logistic", "boosted"):
        matrix = data.volume if method == "volume" else data.runs[
            list(feature_columns("run", Tier.V1, ("aggregation",)))
        ]
        flags = result.fitted[method].flag(matrix.loc[positives])
        row = rows[method, "detection_rate"]
        assert (row.n, row.total) == (int(flags.sum()), len(positives))
        assert (row.low, row.high) == (wilson(row.n, row.total).low,
                                      wilson(row.n, row.total).high)
        for metric in ("false_positive_rate", "online_false_positive_rate", "detection_coverage"):
            rate = rows[method, metric]
            assert rate.interval == "Wilson" and rate.high > rate.low
        assert rows[method, "attribution_recall"].unit == "agents"
    for method in ("logistic", "boosted"):
        subgroup = rows[method, "detection_rate_size_2"]
        assert (subgroup.n, subgroup.total) == (rows[method, "detection_rate"].n, len(positives))
        comparison = rows[method, "sharing_control_auroc"]
        assert comparison.positive_runs == len(positives)
        assert comparison.control_runs == sum(
            not data.records[r].positive and data.records[r].condition["benign_sharing_teams"] > 0
            for r in split.test
        )
    assert "Detection rate" in format_tier(result.rows, "V1")
    for stability in split_stability(data, config, n_seeds=2):
        method = str(stability["detector"]).split()[0]
        assert stability["single_auroc"] == rows[method, "auroc"].value


def test_headline_reuses_metric_values_and_only_short_block_is_embedded(tmp_path: Path) -> None:
    base = MetricRow("V1", "by run", "in-distribution", "logistic", "auroc",
                     0.625, 0.375, 0.875, 20, 20, 10, 10, "", family="aggregation",
                     seed=17, split_counts=(50, 20, 22, 8, 14, 6))
    rate = replace(base, metric="detection_rate", value=0.5, low=0.188, high=0.812,
                   n=3, total=6, interval="Wilson", requested=0, valid=0)
    rows = [base, rate, replace(base, split="held-out channel=message", kind="held-out"),
            replace(rate, metric="detection_rate_size_2"),
            replace(base, metric="sharing_control_auroc", positive_runs=6, control_runs=2)]
    rows += [replace(row, method=RULE) for row in rows]
    text = format_headline(rows, [], [])
    assert "0.625 [0.375, 0.875]" in text
    assert "3 of 6" in text and "0.188, 0.812" in text
    assert "Held-out channel" in text and "message" in text
    assert "Seed: 17" in text and "50 control / 20 positive" in text
    assert "Sharing controls" in text and "2" in text
    headline = tmp_path / "headline.md"
    headline.write_text(text, encoding="utf-8")
    (tmp_path / "results-V1.md").write_text("FULL TABLE MUST STAY OUT", encoding="utf-8")
    readme = tmp_path / "README.md"
    readme.write_text("## What the results show\n\n<!-- BEGIN GENERATED RESULTS -->\nold\n"
                      "<!-- END GENERATED RESULTS -->\n", encoding="utf-8")
    render_readme(readme, headline)
    rendered = readme.read_text(encoding="utf-8")
    assert format_readme_headline(text) in rendered
    assert text not in rendered and "FULL TABLE MUST STAY OUT" not in rendered
    assert "## Held-out channel" not in rendered and "| held-out " not in rendered
    assert "| by run | V1 | aggregation | rule | 0.625 [0.375, 0.875]" in rendered
    assert "| rule | 3 of 6; 0.500 [0.188, 0.812]" in rendered
    assert "| rule | 6 | 2 | 14 | 0.625 [0.375, 0.875] |" in rendered
    assert headline.read_text(encoding="utf-8") == text
    assert rendered.startswith("## What the results show\n\n<!-- BEGIN")


@pytest.mark.parametrize("gate", ["passed", "FAILED"])
def test_readme_headline_is_short_and_preserves_recorded_tables(gate: str) -> None:
    headline = (DATA / "headline.md").read_text(encoding="utf-8")
    headline = headline.replace("Binding loud gate: passed.", f"Binding loud gate: {gate}.")
    block = format_readme_headline(headline)
    assert len(block.splitlines()) <= 45
    prefixes = ("| by run | V0 | generic |", "| by run | V1 | aggregation |",
                "| by run | V2 | all |")
    expected = [line for line in headline.splitlines() if line.startswith(prefixes)]
    actual = [line for line in block.splitlines() if line.startswith("| by run |")]
    assert actual == expected and len(actual) >= 9
    assert "| held-out " not in block and "## Held-out " not in block
    for title in ("By-run split", "V1 aggregation: offensive group size",
                  "V1 aggregation: positives versus sharing controls"):
        source = headline.split(f"## {title}\n", 1)[1].split("\n## ", 1)[0]
        compact = block.split(f"## {title}\n", 1)[1].split("\n## ", 1)[0]
        context = next(line for line in source.splitlines() if line.startswith("Seed:"))
        assert context in compact
        tables = [line for line in source.splitlines() if line.startswith("|")]
        if title == "By-run split":
            assert tables[:2] == [line for line in compact.splitlines()
                                  if line.startswith("|")][:2]
        else:
            assert tables == [line for line in compact.splitlines() if line.startswith("|")]
    counts = next(line for line in headline.splitlines()
                  if line.startswith("Independent benign test:"))
    assert counts in block and f"Binding loud gate: {gate}." in block
    for report in ("headline", "results-V0", "results-V1", "results-V2", "controls",
                   "negative-control"):
        assert f"](data/{report}.md)" in block


def test_headline_covers_each_detector_family_tier_and_held_out_value() -> None:
    splits = ("by run", "held-out channel=message", "held-out channel=shared_file",
              "held-out channel=preplanned", "held-out topology=hub", "held-out topology=peer")
    metrics = ("auroc", "detection_rate", "false_positive_rate", "detection_coverage",
               "online_false_positive_rate")
    rows = [
        MetricRow(tier.value, split, "in-distribution" if split == "by run" else "held-out",
                  method, metric, 0.5, 0.25, 0.75, 3, 6, 0, 0, "", family=family,
                  seed=17, split_counts=(50, 20, 22, 8, 14, 6))
        for split in splits for tier in Tier for family in ("generic", "aggregation", "all")
        for method in ("volume", "logistic", "boosted") for metric in metrics
    ]
    text = format_headline(rows, [], [])
    for split in splits:
        lines = [line for line in text.splitlines() if line.startswith(f"| {split} |")]
        assert len(lines) == 27
        assert sum("volume (family-independent)" in line for line in lines) == 9
        assert all(line.count("3 of 6") == 4 for line in lines)
        assert f"Seed: 17; split: {split}; fitting 50 control / 20 positive; " in text
    assert "## Held-out channel" in text and "## Held-out topology" in text
    assert "Detection rate at calibrated threshold" in text
    assert "Size-specific detection rates use the same full-trace calibrated threshold" in text


def test_committed_raw_samples_regenerate_exactly(tmp_path: Path) -> None:
    samples = {}
    for dataset, count in (("main", 2), ("benign", 1), ("loud", 1)):
        root = DATA / "raw" / dataset
        assert root.is_dir(), f"missing committed {dataset} samples: {root}"
        samples[dataset] = sorted(path for path in root.iterdir() if path.is_dir())[:count]
        assert len(samples[dataset]) == count, (
            f"{count} committed {dataset} samples are required under {root}"
        )
    experiment = json.loads((DATA / "experiment.json").read_text(encoding="utf-8"))
    metadata = {(r["dataset"], r["run_id"]): r for r in experiment["run_metadata"]}
    for dataset, group in samples.items():
        recorded_root = DATA / "dataset" / dataset
        recorded = {}
        for sample in group:
            label = f"{dataset}/{sample.name}"
            assert sample.is_dir(), f"missing committed raw sample: {label}"
            assert (dataset, sample.name) in metadata, f"missing run_metadata for sample {label}"
            for name in ("trace.jsonl", "labels.json", "manifest.json"):
                assert (sample / f"{name}.gz").is_file(), f"missing sample {label}/{name}.gz"
            entry = metadata[dataset, sample.name]
            directory = run_one(Condition(**entry["requested_condition"]), entry["seed"],
                                tmp_path / dataset / sample.name)
            for name in ("trace.jsonl", "labels.json", "manifest.json"):
                target = directory / f"{name}.gz"
                write_gzip(target, (directory / name).read_bytes())
                assert target.read_bytes() == (sample / f"{name}.gz").read_bytes(), (
                    f"{label}/{name} did not regenerate exactly"
                )
            for tier in (Tier.V0, Tier.V1, Tier.V2):
                actual = run_features(read_trace(directory / "trace.jsonl", tier))
                assert (recorded_root / tier.value).is_dir(), (
                    f"missing recorded {tier.value} directory for sample {label}"
                )
                table = recorded_root / tier.value / "runs.csv.gz"
                assert table.is_file(), (
                    f"missing recorded {tier.value} table for sample {label}"
                )
                assert (recorded_root / "manifest.json").is_file(), (
                    f"missing recorded manifest for sample {label}"
                )
                if tier not in recorded:
                    recorded[tier] = load_recorded(recorded_root, tier)
                assert sample.name in recorded[tier].runs.index, (
                    f"missing recorded {tier.value} row for sample {label}"
                )
                expected = recorded[tier].runs.loc[[sample.name]]
                pd.testing.assert_frame_equal(actual, expected, check_exact=True,
                                              obj=f"{label}/{tier.value} run features")


def test_benign_sharing_is_label_side(v1_data: TierData, tmp_path: Path) -> None:
    for record in v1_data.records.values():
        expected = (not record.positive) and record.condition["benign_credential_sharing"] == 100
        assert record.condition["benign_sharing_teams"] == int(expected)
        assert "benign_sharing_teams" not in record.trace_path.read_text(encoding="utf-8")
    assert not any("benign_sharing" in column for column in v1_data.runs)
    write_recorded(tmp_path, v1_data)
    with gzip.open(tmp_path / "V1" / "runs.csv.gz", "rt", encoding="utf-8", newline="") as source:
        rows = list(csv.DictReader(source))
    assert len(rows) == len(v1_data.records)
    for row in rows:
        record = v1_data.records[row["run_id"]]
        sharing = record.condition["benign_sharing_teams"]
        assert int(row["condition_benign_sharing_teams"]) == sharing
        assert row["label_positive"] == str(record.positive)
    restored = load_recorded(tmp_path, Tier.V1)
    assert all(not column.startswith(("label_", "condition_")) for column in restored.runs)
    pd.testing.assert_frame_equal(restored.runs, v1_data.runs, check_exact=True)


def test_loud_binding_rule_rejects_ties_and_insufficient_calibration() -> None:
    assert above_calibration_controls([0.9, 0.8], [0.1, 0.8]) == [True, False]
    assert above_calibration_controls([1.0], []) == [False]
    assert above_calibration_controls([math.nan], [0.1]) == [False]


def test_control_gates_use_recorded_sharing_metadata_only_after_scoring(
    v1_data: TierData, tmp_path: Path,
) -> None:
    write_recorded(tmp_path, v1_data)
    main_data = load_recorded(tmp_path, Tier.V1)
    calibration = tuple(main_data.records)
    controls = [run for run in calibration if not main_data.records[run].positive]
    sharing = next(run for run in controls
                   if main_data.records[run].condition["benign_sharing_teams"] > 0)

    class FixedDetector:
        threshold = 0.5

        def __init__(self, method: str) -> None:
            self.calibration_scores = np.full(len(controls), 0.0021)
            peak = 0.8842 if method == "boosted" else 0.4
            self.calibration_scores[controls.index(sharing)] = peak
            self.value = 0.88 if method == "boosted" else 0.99
            self.inputs: list[pd.DataFrame] = []

        def score(self, frame: pd.DataFrame) -> np.ndarray:
            assert not any(column.startswith(("label_", "condition_")) for column in frame)
            assert not any("benign_sharing" in column for column in frame)
            self.inputs.append(frame.copy())
            return np.full(len(frame), self.value)

        def flag(self, frame: pd.DataFrame) -> np.ndarray:
            return np.zeros(len(frame), dtype=bool)

        def first_crossings(self, frame: pd.DataFrame) -> dict[str, None]:
            return dict.fromkeys(frame.index.get_level_values("run_id"))

    fact = MetricRow("V1", "by run", "in-distribution", "split", "test_runs",
                     12, math.nan, math.nan, 12, 12, 0, 0, "",
                     split_counts=(30, 12, 20, 5, 6, 6))
    fitted = {key: FixedDetector(method) for method in ("volume", "logistic", "boosted", RULE)
              for key in (method, f"{method}-online")}
    result = SplitResult((fact,), {}, fitted, (), calibration)
    rows, flags = _control_rows(result, v1_data, v1_data, "aggregation", ReproduceConfig(),
                                main=main_data)
    require_loud_detection(flags)
    assert all(flags["logistic"]["all_controls"])
    assert not any(flags["boosted"]["all_controls"])
    assert all(flags["boosted"]["nonsharing_controls"])
    assert all(row["high"] > 0 for row in rows)
    assert all("12 of 12" in row["loud_at_calibrated_threshold"] for row in rows)
    bars = loud_bar_rows(rows)
    assert len(bars) == 9
    assert {row["gating"] for row in bars if row["detector"] == RULE} == {"no (non-gating)"}
    assert RULE not in flags
    strict = next(row for row in bars if row["detector"] == "boosted"
                  and row["bar"] == "all_controls")
    assert strict["gating"] == "no (non-gating)"
    assert strict["outcome"] == "not met: lowest loud 0.8800, highest calibration control 0.8842"
    assert "not monotone in shared-login counts" in strict["note"]
    headline = format_headline(result.rows, rows, [])
    assert "Binding loud gate: passed" in headline
    assert "volume (family-independent)" in headline
    assert "12 control / 0 positive" in headline
    negative = [{"tier": "V1", "family": "aggregation", "method": method,
                 "auroc_mean": 0.475, "auroc_se": 0.025, "repeats": 20, "seed": 17,
                 "fitting_controls": 30, "fitting_positive": 12,
                 "calibration_controls": 20, "calibration_positive": 5,
                 "test_controls": 6, "test_positive": 6}
                for method in ("volume (family-independent)", "logistic", "boosted")]
    headline = format_headline(result.rows, rows, negative)
    assert headline.count("0.475 (0.025) | 20") == 3
    assert "no pass/fail criterion" in headline

    altered = replace(main_data, records={
        run: replace(record, condition={**record.condition, "benign_sharing_teams": 0})
        if run == sharing else record for run, record in main_data.records.items()
    })
    _, changed = _control_rows(result, v1_data, v1_data, "aggregation", ReproduceConfig(),
                               main=altered)
    assert not any(changed["boosted"]["nonsharing_controls"])
    assert changed["boosted"]["all_controls"] == flags["boosted"]["all_controls"]
    assert changed["boosted"]["calibrated_threshold"] == flags["boosted"]["calibrated_threshold"]
    pd.testing.assert_frame_equal(fitted["boosted"].inputs[0], fitted["boosted"].inputs[1])
    with pytest.raises(ValueError, match="boosted.*nonsharing_controls"):
        require_loud_detection(changed)
    fitted["boosted"].threshold = 0.88
    _, at_threshold = _control_rows(result, v1_data, v1_data, "aggregation",
                                    ReproduceConfig(), main=main_data)
    assert all(at_threshold["boosted"]["nonsharing_controls"])
    assert not any(at_threshold["boosted"]["calibrated_threshold"])
    with pytest.raises(ValueError, match="boosted.*calibrated_threshold"):
        require_loud_detection(at_threshold)
    missing = replace(main_data, records={
        run: replace(record, condition={k: v for k, v in record.condition.items()
                                        if k != "benign_sharing_teams"})
        for run, record in main_data.records.items()
    })
    with pytest.raises(ValueError, match="benign_sharing_teams.*calibration"):
        _control_rows(result, v1_data, v1_data, "aggregation", ReproduceConfig(),
                      main=missing)


def test_zero_reuse_counterfactual_does_not_pass_logistic_strict_bar(tmp_path: Path) -> None:
    experiment = json.loads((DATA / "experiment.json").read_text(encoding="utf-8"))
    loud_metadata = [entry for entry in experiment["run_metadata"] if entry["dataset"] == "loud"]
    assert len(loud_metadata) == 3, "three committed loud runs are required"
    for entry in loud_metadata:
        assert entry["requested_condition"]["loud_reuses"] == 32
        condition = replace(Condition(**entry["requested_condition"]), loud_reuses=0)
        run_one(condition, entry["seed"], tmp_path / entry["run_id"])
    quiet = build_tier_data(load_runs(tmp_path), Tier.V1, checkpoint_every=160)
    data = load_recorded(DATA / "dataset" / "main", Tier.V1)
    benign = load_recorded(DATA / "dataset" / "benign", Tier.V1)
    loud = load_recorded(DATA / "dataset" / "loud", Tier.V1)
    assert set(loud.records) == {entry["run_id"] for entry in loud_metadata}
    assert all(record.condition["loud_reuses"] == 32 for record in loud.records.values())
    assert all(record.condition.get("loud_reuses", 0) == 0 for record in quiet.records.values())
    config = ReproduceConfig(seed=experiment["config"]["seed"],
                             n_bootstrap=experiment["config"]["n_bootstrap"])
    ids = sorted(data.records)
    split = split_by_run(ids, [data.records[r].positive for r in ids], 0.3,
                         child_seed(config.seed, 0))
    recorded_split = next(value for value in experiment["splits"] if value["name"] == "by run")
    assert split.train == tuple(recorded_split["train"])
    assert split.test == tuple(recorded_split["test"])
    # Match _evaluate_job, including the full recorded data, folds, cadence and fit seed.
    result = evaluate_split(
        data, split, EvalConfig(seed=config.seed, n_bootstrap=config.n_bootstrap),
        child_seed(config.seed, 1, 0), family="aggregation",
    )
    for reuses, controls in ((32, loud), (0, quiet)):
        for method in ("logistic", "boosted"):
            scores = result.fitted[method].calibration_scores
            assert scores.size > 0, f"{method}: empty calibration with loud_reuses={reuses}"
            assert np.isfinite(scores).all(), (
                f"{method}: non-finite calibration with loud_reuses={reuses}"
            )
        _, flags = _control_rows(result, benign, controls, "aggregation", config, main=data)
        assert len(flags["logistic"]["all_controls"]) == 3
        if reuses == 32:
            assert all(flags["logistic"]["all_controls"])
            for method in ("logistic", "boosted"):
                for bar in ("calibrated_threshold", "nonsharing_controls"):
                    assert len(flags[method][bar]) == 3 and all(flags[method][bar]), (method, bar)
            require_loud_detection(flags)
        else:
            assert not all(flags["logistic"]["all_controls"]), (
                "zero-reuse counterfactual unexpectedly passes the logistic strict bar"
            )


def test_negative_control_reports_standard_error_without_pass_band(v1_data: TierData) -> None:
    rows = negative_control(v1_data, "aggregation", 7, 2)
    assert [row["method"] for row in rows] == [
        "volume (family-independent)", "logistic", "boosted", RULE]
    assert all(row["repeats"] == 2 and row["auroc_se"] >= 0 for row in rows)
    assert all("near_chance" not in row for row in rows)
    for row in rows:
        assert row["auroc_se"] == pytest.approx((row["auroc_max"] - row["auroc_min"]) / 2)


def test_split_stability_uses_twenty_seeds_and_no_online_fit(
    v1_data: TierData, monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen_seeds = []

    def record_split(
        ids: Sequence[str], labels: Sequence[bool], fraction: float, seed: int,
    ) -> Split:
        seen_seeds.append(seed)
        return split_by_run(ids, labels, fraction, seed)

    class ConstantDetector:
        def __init__(self, *args: object) -> None:
            self.fitting: set[str] = set()

        def fit(self, frame: pd.DataFrame, labels: np.ndarray) -> "ConstantDetector":
            self.fitting = set(frame.index)
            return self

        def score(self, frame: pd.DataFrame) -> np.ndarray:
            assert self.fitting.isdisjoint(frame.index)
            return np.full(len(frame), 0.5)

    monkeypatch.setattr("swarmtrace.eval.diagnostics.split_by_run", record_split)
    monkeypatch.setattr("swarmtrace.eval.diagnostics.RunDetector", ConstantDetector)

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("split stability must not fit an online model")

    monkeypatch.setattr("swarmtrace.detect.OnlineDetector.fit", forbidden)
    rows = split_stability(v1_data, EvalConfig(seed=8, families=("aggregation",)))
    assert [row["detector"] for row in rows] == [
        "volume (family-independent)", "logistic", "boosted", RULE]
    assert all(row["split_seeds"] == 20 and row["auroc_mean"] == 0.5 for row in rows)
    assert all(row["auroc_std"] == 0 and row["single_auroc"] == 0.5 for row in rows)
    assert len(seen_seeds) == len(set(seen_seeds)) == 20
    assert seen_seeds[0] == child_seed(8, 0)


def test_recorded_stability_cli_skips_full_evaluation(
    v1_data: TierData, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_recorded(tmp_path / "recorded", v1_data)

    def diagnostic(data: TierData, config: EvalConfig) -> list[dict[str, str | int | float]]:
        assert data.tier == Tier.V1 and config.seed == 17
        return [{"seed": 17, "split": "by run", "split_seeds": 20,
                 "single_auroc": 0.5, "auroc_mean": 0.5, "auroc_std": 0.0}]

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("diagnostic must not call ordinary evaluation")

    monkeypatch.setattr("swarmtrace.eval.diagnostics.split_stability", diagnostic)
    monkeypatch.setattr("swarmtrace.eval.commands.evaluate", forbidden)
    main(["eval", "--runs", str(tmp_path / "recorded"), "--out", str(tmp_path / "report"),
          "--seed", "17", "--tiers", "V1", "--workers", "2", "--split-stability"])
    text = (tmp_path / "report" / "split-stability.md").read_text(encoding="utf-8")
    assert "20 different by-run split seeds" in text
    assert "single_auroc" in text and "auroc_std" in text
    assert not (tmp_path / "report" / "results-V1.md").exists()


def test_recorded_stability_table_is_shipped() -> None:
    path = DATA / "split-stability.md"
    assert path.is_file(), (
        "generate data/split-stability.md with the README eval command and commit it"
    )
    lines = [line for line in path.read_text(encoding="utf-8").splitlines()
             if line.startswith("| ")]
    columns = [cell.strip() for cell in lines[0].strip("|").split("|")]
    rows = [dict(zip(columns, [cell.strip() for cell in line.strip("|").split("|")], strict=True))
            for line in lines[2:]]
    assert len(rows) == 36
    assert sum(row["detector"] == "rule" for row in rows) == 9
    experiment = json.loads((DATA / "experiment.json").read_text(encoding="utf-8"))
    assert {row["seed"] for row in rows} == {str(experiment["config"]["seed"])}
    assert {row["split_seeds"] for row in rows} == {"20"}
    assert {(row["tier"], row["family"], row["detector"]) for row in rows} == {
        (tier.value, family, detector) for tier in Tier
        for family in ("generic", "aggregation", "all")
        for detector in ("volume (family-independent)", "logistic", "boosted", "rule")
    }


# The rule baseline in split-stability, negative-control and controls tables.
FAMILIES = ("generic", "aggregation", "all")


@pytest.fixture(scope="module")
def v0_data(v1_data: TierData) -> TierData:
    root = next(iter(v1_data.records.values())).trace_path.parents[1]
    return build_tier_data(load_runs(root), Tier.V0, checkpoint_every=40)


def without_rule(monkeypatch: pytest.MonkeyPatch, module: str) -> None:
    monkeypatch.setattr(f"{module}.REPORTED_DETECTORS", DETECTORS)


def by_detector(rows: Sequence[dict], key: str = "detector") -> dict[tuple, dict]:
    return {(row["tier"], row["family"], row[key], row.get("mode")): row for row in rows}


def test_split_stability_reports_the_rule_without_changing_existing_rows(
    v1_data: TierData, v0_data: TierData, monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = EvalConfig(seed=5, families=FAMILIES)
    rows = [*split_stability(v1_data, config, n_seeds=2),
            *split_stability(v0_data, config, n_seeds=2)]
    rule = {(row["tier"], row["family"]): row for row in rows if row["detector"] == RULE}
    assert set(rule) == {(tier, family) for tier in ("V0", "V1") for family in FAMILIES}
    for family in ("aggregation", "all"):
        assert isinstance(rule["V1", family]["single_auroc"], float)
        assert rule["V1", family]["auroc_std"] >= 0
    assert rule["V1", "generic"]["single_auroc"] == NOT_AVAILABLE_FAMILY
    assert {rule["V0", family]["auroc_mean"] for family in FAMILIES} == {NOT_AVAILABLE_TIER}
    # The rule's single AUROC is the count's AUROC on the reported split's test runs.
    ids = sorted(v1_data.records)
    split = split_by_run(ids, [v1_data.records[r].positive for r in ids], 0.3,
                         child_seed(5, 0))
    labels = np.array([v1_data.records[r].positive for r in split.test])
    counts = v1_data.runs.loc[list(split.test), RULE_COLUMN].to_numpy(dtype=float)
    assert rule["V1", "aggregation"]["single_auroc"] == auroc(labels, counts)
    without_rule(monkeypatch, "swarmtrace.eval.diagnostics")
    before = [*split_stability(v1_data, config, n_seeds=2),
              *split_stability(v0_data, config, n_seeds=2)]
    assert repr(before) == repr([row for row in rows if row["detector"] != RULE])


def test_negative_control_reports_the_rule_without_changing_existing_rows(
    v1_data: TierData, v0_data: TierData, monkeypatch: pytest.MonkeyPatch,
) -> None:
    def run() -> list[dict]:
        return [row for data in (v1_data, v0_data) for family in FAMILIES
                for row in negative_control(data, family, 7, 2)]

    rows = run()
    rule = {(row["tier"], row["family"]): row for row in rows if row["method"] == RULE}
    assert set(rule) == {(tier, family) for tier in ("V0", "V1") for family in FAMILIES}
    for family in ("aggregation", "all"):
        assert 0.0 <= rule["V1", family]["auroc_mean"] <= 1.0
    assert rule["V1", "generic"]["auroc_mean"] == NOT_AVAILABLE_FAMILY
    assert {rule["V0", family]["auroc_se"] for family in FAMILIES} == {NOT_AVAILABLE_TIER}
    without_rule(monkeypatch, "swarmtrace.reproduce.controls")
    assert repr(run()) == repr([row for row in rows if row["method"] != RULE])


@pytest.fixture(scope="module")
def family_results(v1_data: TierData) -> dict[str, tuple]:
    ids = sorted(v1_data.records)
    config = EvalConfig(seed=5, n_bootstrap=4, n_folds=2)
    split = split_by_run(ids, [v1_data.records[r].positive for r in ids], 0.3,
                         child_seed(5, 0))
    return {family: evaluate_split(v1_data, split, config, child_seed(5, 1, 0),
                                   family=family) for family in ("aggregation", "generic")}


def test_controls_report_the_rule_as_a_non_gating_diagnostic(
    v1_data: TierData, family_results: dict, monkeypatch: pytest.MonkeyPatch,
) -> None:
    def run() -> tuple[list[dict], dict, list[dict]]:
        rows, flags = [], {}
        for family, result in family_results.items():
            control, family_flags = _control_rows(result, v1_data, v1_data, family,
                                                  ReproduceConfig(), main=v1_data)
            rows.extend(control)
            if family == "aggregation":
                flags = family_flags
        return rows, flags, loud_bar_rows(rows)

    rows, flags, bars = run()
    controls = by_detector(rows)
    for mode in ("full-trace", "online"):
        rule = controls["V1", "aggregation", RULE, mode]
        assert rule["loud_required_met"] == rule["loud_required_rate"] == NOT_GATED
        assert isinstance(rule["FPR"], float) and rule["benign_runs"] == 12
        assert rule["threshold"] == family_results["aggregation"].fitted[RULE].threshold
        generic = controls["V1", "generic", RULE, mode]
        assert generic["FPR"] == generic["benign_rate"] == NOT_AVAILABLE_FAMILY
        assert generic["benign_runs"] == 12
        assert list(generic) == list(rule)
    # Full-trace benign flags and loud flags use the main model's own rule and threshold.
    fitted = family_results["aggregation"].fitted[RULE]
    full = controls["V1", "aggregation", RULE, "full-trace"]
    counts = v1_data.runs[RULE_COLUMN].to_numpy(dtype=float)
    assert full["benign_flagged"] == int((counts > fitted.threshold).sum())
    assert full["loud_at_calibrated_threshold_count"] == int((counts > fitted.threshold).sum())
    rule_bars = [row for row in bars if row["detector"] == RULE]
    assert [row["bar"] for row in rule_bars] == [
        "calibrated_threshold", "nonsharing_controls", "all_controls"]
    assert {row["gating"] for row in rule_bars} == {"no (non-gating)"}
    assert all("diagnostic only" in row["note"] for row in rule_bars)
    assert RULE not in flags and RULE not in LOUD_GATING_BARS
    without_rule(monkeypatch, "swarmtrace.reproduce.pipeline")
    before_rows, before_flags, before_bars = run()
    assert repr(before_rows) == repr([row for row in rows if row["detector"] != RULE])
    assert repr(before_flags) == repr(flags)
    assert repr(before_bars) == repr([row for row in bars if row["detector"] != RULE])


def test_reproduce_gate_and_headline_ignore_a_failing_rule(
    v1_data: TierData, family_results: dict,
) -> None:
    passing = {method: dict.fromkeys(bars, [True, True])
               for method, bars in LOUD_GATING_BARS.items()}
    require_loud_detection(passing)
    require_loud_detection({**passing, RULE: dict.fromkeys(
        ("calibrated_threshold", "nonsharing_controls", "all_controls"), [False, False])})
    result = family_results["aggregation"]
    rows, _ = _control_rows(result, v1_data, v1_data, "aggregation",
                            ReproduceConfig(), main=v1_data)
    binding = [row for row in rows if row["detector"] in LOUD_GATING_BARS
               and row["mode"] == "full-trace"]
    rows = [{**row, "loud_required_met": row["loud_runs"]} if row in binding else row
            for row in rows]
    rule_bars = [row for row in loud_bar_rows(rows) if row["detector"] == RULE]
    failing = [{**row, "loud_required_met": 0, "loud_at_calibrated_threshold_count": 0}
               if row["detector"] == RULE else row for row in rows]
    assert any(row["outcome"].startswith(("met", "not met")) for row in rule_bars)
    assert any(row["outcome"].startswith("not met")
               for row in loud_bar_rows(failing) if row["detector"] == RULE)
    for controls in (rows, failing):
        headline = format_headline(result.rows, controls, [])
        assert "Binding loud gate: passed" in headline
        assert "| V1 | aggregation | rule | " in headline
        assert NOT_GATED in headline
    negative = negative_control(v1_data, "generic", 7, 2)
    generic = family_results["generic"]
    generic_rows, _ = _control_rows(generic, v1_data, v1_data, "generic",
                                    ReproduceConfig(), main=v1_data)
    headline = format_headline(generic.rows, generic_rows, negative)
    assert f"| V1 | generic | rule | {NOT_AVAILABLE_FAMILY} | {NOT_AVAILABLE_FAMILY} | " \
        f"{NOT_AVAILABLE_FAMILY} | 2 |" in headline
