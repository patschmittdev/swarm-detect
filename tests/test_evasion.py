import hashlib
import json
import socket
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from swarmtrace import cli
from swarmtrace.detect import RULE, RunDetector
from swarmtrace.eval.harness import EvalConfig, child_seed, family_data
from swarmtrace.eval.recorded import load_recorded, load_run_table
from swarmtrace.eval.splits import split_by_run
from swarmtrace.reproduce import evasion, frozen
from swarmtrace.reproduce.config import ReproduceConfig, make_jobs
from swarmtrace.reproduce.evasion import PREDICTION, render_report_header
from swarmtrace.reproduce.pipeline import _rate
from swarmtrace.reproduce.sharing_sweep import SharingSweepConfig, plan_sharing_sweep
from swarmtrace.reproduce.verify import verify
from swarmtrace.sim.runner import Condition, build_run
from swarmtrace.sim.sweep import condition_grid
from swarmtrace.trace.io import read_manifest
from swarmtrace.trace.tiers import Tier

EXPECTED_PREDICTION = (
    "Prediction (written before the run): with the owner silent, the shared-credential feature "
    "is zero for the relay group, and the frozen detectors flag owner-silent relay runs at "
    "about the rate they flag control runs, because the only remaining shared logins come "
    "from benign sharing teams in the same run."
)
EXPECTED_POST_HOC_NOTE = (
    "The breakdown by topology and size was added after an 18-run exploratory probe on other "
    "seeds, run after the prediction was committed and before this sweep; it is post hoc. "
    "The prediction text was not changed."
)


def test_prediction_is_pinned_verbatim() -> None:
    assert PREDICTION == EXPECTED_PREDICTION


def test_post_hoc_note_is_pinned_verbatim() -> None:
    assert evasion.POST_HOC_NOTE == EXPECTED_POST_HOC_NOTE


def test_report_header_starts_with_heading_and_pinned_prediction() -> None:
    expected_start = (
        "# Named evasion: owner-silent credential relay against frozen detectors\n\n"
        f"{EXPECTED_PREDICTION}\n\n"
    )
    assert render_report_header().startswith(expected_start)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
METHODS = (RULE, "logistic", "boosted")


@pytest.fixture(scope="module")
def frozen_main():
    # Reconstruct real main models once; the tiny sweeps reuse these frozen instances.
    root = PROJECT_ROOT / "data/dataset/main"
    data = load_recorded(root, Tier.V1)
    with evasion._get_threadpool_controller().limit(limits=1):
        result = frozen.frozen_main_models(root, evasion.MAIN_SEED, n_bootstrap=2)
    return result, data


@pytest.mark.parametrize("n_bootstrap", (None, 2))
def test_shared_main_fit_preserves_defaults_and_recorded_checkpoint_cadence(
    tmp_path, monkeypatch, n_bootstrap,
) -> None:
    from types import SimpleNamespace

    data = SimpleNamespace(checkpoint_every=13, records={
        "c": SimpleNamespace(positive=True), "a": SimpleNamespace(positive=False),
        "b": SimpleNamespace(positive=True), "d": SimpleNamespace(positive=False),
    })
    seen = []
    expected = object()

    def load(root, tier):
        assert root == tmp_path and tier is Tier.V1
        return data

    def evaluate(actual_data, split, config, seed, *, family):
        assert actual_data is data
        seen.append((split, config, seed, family))
        return expected

    monkeypatch.setattr(frozen, "load_recorded", load)
    monkeypatch.setattr(frozen, "evaluate_split", evaluate)
    kwargs = {} if n_bootstrap is None else {"n_bootstrap": n_bootstrap}
    assert frozen.frozen_main_models(tmp_path, 17, **kwargs) is expected
    ids = list(data.records)
    assert seen == [(
        split_by_run(ids, [data.records[run].positive for run in ids], 0.3, child_seed(17, 0)),
        EvalConfig(tiers=(Tier.V1,), seed=17, test_fraction=0.3, families=("aggregation",),
                   n_bootstrap=ReproduceConfig.n_bootstrap if n_bootstrap is None else n_bootstrap,
                   checkpoint_every=13),
        child_seed(17, 1, 0), "aggregation",
    )]


@pytest.mark.parametrize("missing_from", ("fitted", "thresholds"))
@pytest.mark.parametrize("method", METHODS)
def test_evasion_preserves_main_fit_inputs_and_rejects_missing_detectors(
    tmp_path, monkeypatch, missing_from, method,
) -> None:
    from contextlib import contextmanager
    from types import SimpleNamespace

    config = evasion.EvasionConfig(seed=17, n_bootstrap=3, data_root=tmp_path / "main-data",
                                   conditions=(Condition(offensive_group_size=2),))
    archive = config.data_root / "dataset/main"
    data = SimpleNamespace(checkpoint_every=13)
    result = SimpleNamespace(fitted=dict.fromkeys(METHODS), thresholds=dict.fromkeys(METHODS))
    del getattr(result, missing_from)[method]
    seen, active = [], []

    @contextmanager
    def limit(*, limits):
        assert limits == 1
        active.append(limits)
        try:
            yield
        finally:
            active.pop()

    def load(root, tier):
        assert active == [1]
        assert root == archive and tier is Tier.V1
        seen.append("load")
        return data

    def fit(root, seed, *, n_bootstrap):
        assert active == [1]
        assert root == archive and seed == 20261120 and n_bootstrap == 3
        seen.append("fit")
        return result

    monkeypatch.setattr(evasion, "_get_threadpool_controller", lambda: SimpleNamespace(limit=limit))
    monkeypatch.setattr(evasion, "load_recorded", load)
    monkeypatch.setattr(evasion, "frozen_main_models", fit)
    out = tmp_path / "output"
    message = "^recorded main data could not supply all frozen detectors$"
    with pytest.raises(ValueError, match=message):
        evasion.run_evasion(out, config)
    assert seen == ["load", "fit"] and active == []
    assert not out.exists()


def test_frozen_main_reproduces_recorded_detection_rows(frozen_main) -> None:
    result, data = frozen_main
    ids = list(data.records)
    split = split_by_run(ids, [data.records[run].positive for run in ids],
                         0.3, child_seed(20261120, 0))
    matrix = family_data(data, "aggregation").runs.loc[list(split.test)]
    positive = np.array([data.records[run].positive for run in split.test], dtype=bool)
    nonsharing = np.array([not data.records[run].positive
                           and data.records[run].condition["benign_sharing_teams"] == 0
                           for run in split.test], dtype=bool)
    recorded = (PROJECT_ROOT / "data/results-V1.md").read_text(encoding="utf-8")
    section = recorded.split("### Features: aggregation", 1)[1]
    full_trace = section.split("### Full-trace detection", 1)[1].split("###", 1)[0]
    for method, positive_k, control_k in ((RULE, 7, 4), ("logistic", 14, 5), ("boosted", 13, 5)):
        flags = result.fitted[method].score(matrix) > result.thresholds[method]
        assert (int(flags[positive].sum()), int(positive.sum())) == (positive_k, 32)
        assert (int(flags[~positive].sum()), int((~positive).sum())) == (control_k, 86)
        assert (int(flags[nonsharing].sum()), int(nonsharing.sum())) == (0, 72)
        rows = {row.metric: row for row in result.rows if row.method == method}
        assert (rows["detection_rate"].n, rows["detection_rate"].total) == (positive_k, 32)
        assert (rows["false_positive_rate"].n, rows["false_positive_rate"].total) == (control_k, 86)
        line = next(line for line in full_trace.splitlines()
                    if line.startswith(f"| by run | {method}"))
        assert f"{positive_k} of 32 runs" in line and f"{control_k} of 86 runs" in line
    assert set(result.fitting).isdisjoint(result.calibration)
    assert set(result.fitting + result.calibration).isdisjoint(split.test)


def test_paired_grid_seeds_are_disjoint_from_real_default_experiments(monkeypatch) -> None:
    calls = []

    def seed(base, *key):
        calls.append((base, key))
        return child_seed(base, *key)

    monkeypatch.setattr(evasion, "child_seed", seed)
    jobs = evasion.plan_evasion(evasion.EvasionConfig())
    standard = [job for job in jobs if job.dataset == "standard"]
    silent = [job for job in jobs if job.dataset == "owner_silent"]
    grid = tuple(cell for cell in condition_grid(n_ticks=160) if cell.offensive_group_size > 0)
    assert len(standard) == len(silent) == len(grid) == 54
    assert [job.condition for job in standard] == list(grid)
    for index, (first, second) in enumerate(zip(standard, silent, strict=True)):
        assert first.seed == second.seed == child_seed(20261120, 92, 0, index)
        assert first.directory == second.directory
        assert replace(first.condition, relay_style="owner_silent") == second.condition
    seeds = {job.seed for job in standard}
    assert len(seeds) == 54
    assert seeds.isdisjoint(job.seed for job in make_jobs(ReproduceConfig())
                            if job.dataset == "main")
    assert seeds.isdisjoint(job.seed for plan in plan_sharing_sweep(SharingSweepConfig())
                            for job in plan.jobs)
    assert calls and all(len(key) >= 2 for _, key in calls)
    assert calls == [(20261120, (92, 0, index)) for index in range(54)]


@pytest.fixture(scope="module")
def report_pair_counts():
    return []


@pytest.fixture(scope="module")
def completed(tmp_path_factory, frozen_main, report_pair_counts):
    root = tmp_path_factory.mktemp("evasion")
    config = evasion.EvasionConfig(workers=1, n_bootstrap=2, conditions=(
        Condition("message", "hub", 2, 1, n_ticks=48),
        Condition("preplanned", "peer", 3, 2, n_ticks=48, benign_credential_sharing=100),
    ))
    scored, archives = [], []
    original_score = RunDetector.score
    original_write, original_load = evasion.write_recorded, evasion.load_recorded
    original_report = evasion._write_report

    def score(detector, matrix):
        assert not any(str(column).startswith(("label_", "condition_", "outcome_"))
                       for column in matrix.columns)
        scored.append(id(detector))
        return original_score(detector, matrix)

    def forbidden(*args, **kwargs):
        raise AssertionError("evasion must not refit, recalibrate, or open sockets")

    def write(path, data):
        archives.append(("write", Path(path)))
        return original_write(path, data)

    def load(path, tier):
        if Path(path) == config.data_root / "dataset/main":
            assert tier is Tier.V1
            return frozen_main[1]
        data = original_load(path, tier)
        archives.append(("load", Path(path), data))
        return data

    def write_report(path, config, datasets, scores, result, main, pair_counts, hashes):
        report_pair_counts.append(dict(pair_counts))
        return original_report(path, config, datasets, scores, result, main, pair_counts, hashes)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(evasion, "frozen_main_models", lambda *args, **kwargs: frozen_main[0])
        patch.setattr(RunDetector, "score", score)
        patch.setattr(RunDetector, "fit", forbidden)
        patch.setattr(RunDetector, "calibrate", forbidden)
        patch.setattr(evasion, "write_recorded", write)
        patch.setattr(evasion, "load_recorded", load)
        patch.setattr(evasion, "_write_report", write_report)
        with pytest.MonkeyPatch.context() as offline:
            offline.setattr(socket, "socket", forbidden)
            offline.setattr(socket, "create_connection", forbidden)
            serial = evasion.run_evasion(root / "serial", config)
        parallel = evasion.run_evasion(root / "parallel", replace(config, workers=2))
    return root, config, serial, parallel, scored, archives


def test_tiny_offline_sweep_is_byte_identical_across_workers(completed) -> None:
    _, _, serial, parallel, _, _ = completed
    for relative in ("evasion.md", "evasion/runs.csv.gz"):
        assert (serial.parent / relative).read_bytes() == (parallel.parent / relative).read_bytes()
    assert not list(serial.parent.glob("swarmtrace-evasion-*"))


def test_detectors_receive_only_round_tripped_features(completed, frozen_main) -> None:
    _, _, _, _, scored, archives = completed
    assert {id(frozen_main[0].fitted[method]) for method in METHODS} <= set(scored)
    assert len(archives) == 8
    for index in range(0, len(archives), 2):
        assert archives[index][0] == "write" and archives[index + 1][0] == "load"
        assert archives[index][1] == archives[index + 1][1]


def test_combined_table_and_raw_sample_preserve_pair_identity(completed) -> None:
    _, config, report, _, _, _ = completed
    table = load_run_table(report.parent / "evasion/runs.csv.gz")
    assert table.features.index.is_unique and len(table.features) == 4
    frame = pd.read_csv(report.parent / "evasion/runs.csv.gz", dtype={"run_id": str})
    committed = pd.read_csv(PROJECT_ROOT / "data/evasion/runs.csv.gz", nrows=0)
    assert len(frame.set_index("run_id").columns) == 46
    assert tuple(frame.columns) == tuple(committed.columns)
    assert not any(column.startswith("outcome_") for column in frame)
    assert all(record.outcomes == {} for record in table.records)
    assert frame["label_positive"].all()
    assert set(frame["condition_relay_style"]) == {"standard", "owner_silent"}
    for _, rows in frame.groupby("condition_source_run_id"):
        assert len(rows) == 2 and rows["condition_paired_seed"].nunique() == 1
        source_id = rows["condition_source_run_id"].iloc[0].removeprefix("run:")
        assert set(rows["run_id"]) == {
            f"{style}:{source_id}" for style in ("standard", "owner_silent")
        }
    manifests = sorted((report.parent / "evasion/raw").glob("*/*/manifest.json"))
    assert len(manifests) == 2
    samples = [read_manifest(path) for path in manifests]
    assert samples[0].seed == samples[1].seed
    assert samples[0].run_id == samples[1].run_id
    sample_job = next(job for job in evasion.plan_evasion(config)
                      if job.condition.topology == "peer"
                      and job.condition.offensive_group_size == 3)
    assert samples[0].seed == sample_job.seed
    assert all(sample.condition["topology"] == "peer"
               and sample.condition["offensive_group_size"] == 3 for sample in samples)
    expected = {"evasion.md", "evasion/runs.csv.gz"}
    expected.update((path.parent / name).relative_to(report.parent).as_posix()
                    for path in manifests
                    for name in ("trace.jsonl", "labels.json", "manifest.json"))
    assert {path.relative_to(report.parent).as_posix() for path in report.parent.rglob("*")
            if path.is_file()} == expected


def test_generated_report_pins_prediction_and_verifier_accepts_hash_block(
    completed, tmp_path,
) -> None:
    _, _, report, _, _, _ = completed
    text = report.read_text(encoding="utf-8")
    assert text.startswith(
        "# Named evasion: owner-silent credential relay against frozen detectors\n\n"
        + EXPECTED_PREDICTION + "\n\n"
    )
    assert text.count(EXPECTED_PREDICTION) == 1
    paths = ["evasion/runs.csv.gz", *sorted(
        path.relative_to(report.parent).as_posix()
        for path in (report.parent / "evasion/raw").rglob("*") if path.is_file()
    )]
    hashes = "".join(f"{name} | {hashlib.sha256((report.parent / name).read_bytes()).hexdigest()}\n"
                     for name in paths)
    assert len(paths) == 7
    assert text.endswith("```swarmtrace-evasion-sha256\npath | sha256\n" + hashes + "```\n")
    for section in ("Detection by detector", "Shared credential features", "Objective completion",
                    "Calibration control median", "Benign sharing teams",
                    "Topology and group size", "Owner-silent detection by shape",
                    "Shared credential features by topology and size"):
        assert f"## {section}\n" in text
    shape_section = text.split("## Owner-silent detection by shape\n", 1)[1]
    assert EXPECTED_POST_HOC_NOTE + "\n\n| benign sharing teams" in shape_section
    assert text.count(EXPECTED_POST_HOC_NOTE) == 1
    assert ("The aggregation family's other feature, access expansion after receipt, also "
            "falls under owner_silent, because it too reads logins.") in text
    for path in report.parent.rglob("*"):
        if path.is_file():
            destination = tmp_path / path.relative_to(report.parent)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(path.read_bytes())
    (tmp_path / "main.bin").write_bytes(b"main")
    (tmp_path / "experiment.json").write_text(json.dumps({
        "artifacts_sha256": {"main.bin": hashlib.sha256(b"main").hexdigest()},
    }), encoding="utf-8")
    verify(tmp_path)


def test_cli_dispatches_evasion(tmp_path, monkeypatch) -> None:
    seen = []
    monkeypatch.setattr(cli, "run_evasion", lambda out, config: seen.append((out, config)))
    cli.main(["evasion", "--out", str(tmp_path), "--seed", "17", "--workers", "2"])
    assert len(seen) == 1 and seen[0][0] == tmp_path
    assert seen[0][1].seed == 17 and seen[0][1].workers == 2


def test_evasion_refuses_nonempty_output_before_fitting(tmp_path, monkeypatch) -> None:
    (tmp_path / "keep.txt").write_text("keep", encoding="utf-8")

    def forbidden(*args, **kwargs):
        pytest.fail("nonempty output reached fitting")

    monkeypatch.setattr(evasion, "frozen_main_models", forbidden)
    with pytest.raises(ValueError, match="fresh"):
        evasion.run_evasion(tmp_path, evasion.EvasionConfig())
    assert (tmp_path / "keep.txt").read_text(encoding="utf-8") == "keep"


def _table_rows(report: str, title: str) -> list[dict[str, str]]:
    section = report.split(f"## {title}\n", 1)[1].split("\n## ", 1)[0]
    lines = [line for line in section.splitlines() if line.startswith("|")]
    columns = [cell.strip() for cell in lines[0].strip("|").split("|")]
    return [dict(zip(columns, (cell.strip() for cell in line.strip("|").split("|")), strict=True))
            for line in lines[2:]]


def test_report_rates_use_frozen_scores_and_label_side_subsets(completed, frozen_main) -> None:
    _, _, report, _, _, archives = completed
    text = report.read_text(encoding="utf-8")
    result, main = frozen_main
    datasets = {entry[1].name: entry[2] for entry in archives if entry[0] == "load"}
    scores = {style: {method: pd.Series(result.fitted[method].score(
        family_data(data, "aggregation").runs), index=data.runs.index) for method in METHODS}
              for style, data in datasets.items()}
    flags = {style: {method: values > result.thresholds[method]
                     for method, values in measured.items()} for style, measured in scores.items()}
    detection = _table_rows(text, "Detection by detector")
    assert [row["detector"] for row in detection] == list(METHODS)
    for row in detection:
        method = row["detector"]
        standard, silent = (flags[style][method] for style in ("standard", "owner_silent"))
        assert row["standard"] == _rate(standard.tolist())
        assert row["owner_silent"] == _rate(silent.tolist())
        assert row["standard only (paired)"] == _rate((standard & ~silent).tolist())
        assert row["owner_silent only (paired)"] == _rate((~standard & silent).tolist())
        assert float(row["threshold"]) == result.thresholds[method]
    for row in _table_rows(text, "Shared credential features"):
        values = datasets[row["style"]].runs[row["feature"]]
        assert float(row["mean"]) == pytest.approx(values.mean(), abs=0.000051)
        assert row["zero runs"] == _rate(values.eq(0).tolist())
    for row in _table_rows(text, "Objective completion"):
        records = datasets[row["style"]].records.values()
        selected = [record for record in records if row["offensive size"] == "all"
                    or record.condition["offensive_group_size"] == int(row["offensive size"])]
        assert row["completed"] == _rate([record.labels.objective_completed for record in selected])
    calibration = [run for run in result.calibration if not main.records[run].positive]
    for row in _table_rows(text, "Calibration control median"):
        method = row["detector"]
        matrix = family_data(main, "aggregation").runs.loc[calibration]
        median = float(np.median(result.fitted[method].score(matrix)))
        assert int(row["calibration controls"]) == len(calibration)
        assert float(row["median calibration control score"]) == pytest.approx(median, abs=0.000051)
        assert row["owner_silent at or below median"] == _rate(
            scores["owner_silent"][method].le(median).tolist(),
        )
    for row in _table_rows(text, "Benign sharing teams"):
        data = datasets[row["style"]]
        selected = [run for run, record in data.records.items()
                    if (record.condition["benign_sharing_teams"] > 0)
                    == (row["benign sharing teams"] == ">=1")]
        assert row["flagged"] == _rate(flags[row["style"]][row["detector"]].loc[selected].tolist())
    shapes = _table_rows(text, "Topology and group size")
    assert len(shapes) == 12
    for row in shapes:
        data = datasets[row["style"]]
        selected = [run for run, record in data.records.items()
                    if record.condition["topology"] == row["topology"]
                    and record.condition["offensive_group_size"] == int(row["offensive size"])]
        assert int(row["positive runs"]) == len(selected) and row["control runs"] == "0"
        for method in METHODS:
            assert row[method] == _rate(flags[row["style"]][method].loc[selected].tolist())


def test_default_data_root_is_independent_of_working_directory(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert evasion.EvasionConfig().data_root == PROJECT_ROOT / "data"


def test_seed_collision_is_rejected_before_execution(monkeypatch) -> None:
    reserved = next(job.seed for job in make_jobs(ReproduceConfig()) if job.dataset == "main")
    monkeypatch.setattr(evasion, "child_seed", lambda *args: reserved)
    with pytest.raises(ValueError, match="collide"):
        evasion.plan_evasion(evasion.EvasionConfig(conditions=(Condition(offensive_group_size=2),)))


def test_combined_table_preserves_all_digit_source_ids(frozen_main, tmp_path) -> None:
    _, main = frozen_main
    source_id = "0000000000000001"
    record = next(iter(main.records.values()))
    runs = main.runs.iloc[:1].set_axis(pd.Index([source_id], name="run_id"))
    datasets = {style: replace(main, runs=runs, records={source_id: replace(
        record, run_id=source_id, condition={"relay_style": style, "paired_seed": 1},
    )}) for style in ("standard", "owner_silent")}
    path = tmp_path / "runs.csv.gz"
    evasion._combined_table(path, datasets)
    table = load_run_table(path)
    assert set(table.features.index) == {f"{style}:{source_id}" for style in datasets}
    assert all(record.condition["source_run_id"] == f"run:{source_id}" for record in table.records)


def test_combined_table_preserves_committed_schema_and_gzip_bytes(tmp_path) -> None:
    from types import SimpleNamespace

    path = PROJECT_ROOT / "data/evasion/runs.csv.gz"
    committed = path.read_bytes()
    assert hashlib.sha256(committed).hexdigest() == (
        "f13532791e0c72d50e2cc79740e174e16d9eccdff332453081f19c540019fdf4"
    )
    columns = pd.read_csv(path, index_col="run_id", nrows=0).columns
    assert len(columns) == 46
    assert not any(column.startswith("outcome_") for column in columns)
    table = load_run_table(path)
    datasets = {}
    for style in ("standard", "owner_silent"):
        selected = [record for record in table.records if record.condition["relay_style"] == style]
        source_ids = {record.run_id: record.condition["source_run_id"].removeprefix("run:")
                      for record in selected}
        runs = table.features.loc[list(source_ids)].rename(index=source_ids)
        records = {source_ids[record.run_id]: replace(
            record, run_id=source_ids[record.run_id],
            condition={key: value for key, value in record.condition.items()
                       if key != "source_run_id"},
        ) for record in selected}
        datasets[style] = SimpleNamespace(runs=runs, records=records)
    output = tmp_path / "runs.csv.gz"
    evasion._combined_table(output, datasets)
    assert output.read_bytes() == committed


def test_report_pair_verdict_uses_in_memory_counts_from_recorded_pair_values(
    completed, report_pair_counts,
) -> None:
    _, config, report, _, _, archives = completed
    silent = next(entry[2] for entry in archives
                  if entry[0] == "load" and entry[1].name == "owner_silent")
    expected_counts = {}
    zero, total = 0, 0
    for job in evasion.plan_evasion(config):
        if job.dataset != "owner_silent":
            continue
        setup = build_run(job.condition, job.seed)
        run = next(run for run, record in silent.records.items()
                   if record.condition["paired_seed"] == job.seed)
        directed = {(relay.owner, relay.recipient) for relay in setup.objective.relays}
        values = [silent.pairs.loc[(run, *sorted(pair)), "shared_credential_logins"]
                  for pair in sorted(directed)]
        expected = (sum(value == 0 for value in values), len(directed))
        expected_counts[run] = expected
        zero += expected[0]
        total += expected[1]
    assert report_pair_counts == [expected_counts, expected_counts]
    assert zero == total == 5  # One two-member hub and one three-member peer ring.
    text = report.read_text(encoding="utf-8")
    after_prediction = text.split(EXPECTED_PREDICTION + "\n\n", 1)[1]
    verdict, rest = after_prediction.split("\n\n", 1)
    assert verdict.startswith("Outcome: the shared-credential feature is zero for every "
                              f"lender-borrower pair under owner_silent ({zero} of {total} pairs).")
    assert "hubs of five flagged 0 of 0, 0 of 0, 0 of 0." in verdict
    assert "Main test controls with no sharing team: 0 of 72, 0 of 72, 0 of 72." in verdict
    assert rest.startswith("Seed:")
    for row in _table_rows(text, "Owner-silent detection by shape"):
        if row["shape"] in {"hubs of 3", "hubs of 5"}:
            assert row["owner_silent flagged"] == _rate([])
    for row in _table_rows(text, "Shared credential features by topology and size"):
        if row["runs"] == "0":
            assert all(np.isnan(float(row[f"mean {column}"])) for column in evasion.SHARED_COLUMNS)


def test_lender_pair_count_changes_when_the_measured_pair_feature_changes(completed) -> None:
    _, config, _, _, _, archives = completed
    data = next(entry[2] for entry in archives
                if entry[0] == "load" and entry[1].name == "owner_silent")
    jobs = evasion.plan_evasion(config)
    job = next(job for job in jobs if job.dataset == "owner_silent")
    run = next(run for run, record in data.records.items()
               if record.condition["paired_seed"] == job.seed)
    relay = build_run(job.condition, job.seed).objective.relays[0]
    key = (run, *sorted((relay.owner, relay.recipient)))
    pairs = data.pairs.copy()
    pairs.loc[key, "shared_credential_logins"] = 1
    measured = evasion._lender_pair_counts(replace(data, pairs=pairs), jobs)
    assert measured[run][0] < measured[run][1]


@pytest.fixture
def shape_data(frozen_main):
    result, main = frozen_main
    original = next(record for record in main.records.values() if record.positive)
    # Explicit topology/size cases and two sharing-team cases that must stay out of zero rows.
    cases = [("hub", 2, 0), ("peer", 2, 0), ("peer", 3, 0), ("peer", 5, 0),
             ("hub", 3, 0), ("hub", 5, 0), ("peer", 3, 1), ("hub", 5, 1)]
    ids = [f"r{index}" for index in range(len(cases))]
    records = {run: replace(original, run_id=run, condition={
        "topology": topology, "offensive_group_size": size, "benign_sharing_teams": teams,
    }) for run, (topology, size, teams) in zip(ids, cases, strict=True)}
    frame = pd.DataFrame(0.0, index=pd.Index(ids, name="run_id"), columns=main.runs.columns)
    for offset, column in enumerate(evasion.SHARED_COLUMNS, start=1):
        frame[column] = np.arange(1, len(ids) + 1, dtype=float) * offset
    datasets = {style: replace(main, records=records, runs=frame + index)
                for index, style in enumerate(("standard", "owner_silent"))}
    scores = {style: pd.DataFrame({method: [result.thresholds[method] + delta
                                           for delta in (-1, 1, -1, 1, 1, 1, -1, 1)]
                                   for method in METHODS}, index=frame.index)
              for style in datasets}
    return datasets, scores


def test_shape_tables_match_declared_populations_and_all_three_feature_means(
    shape_data, frozen_main,
) -> None:
    datasets, scores = shape_data
    result, main = frozen_main
    tables = dict(evasion._report_tables(datasets, scores, result, main))
    detection = tables["Detection by detector"]
    for row in detection:
        assert row["main test controls without a sharing team, k of 72"] == _rate([False] * 72)
    rows = tables["Owner-silent detection by shape"]
    assert len(rows) == 12
    expected = {("0", "pairs and peer rings"): [False, True, False, True],
                ("0", "hubs of 3"): [True], ("0", "hubs of 5"): [True],
                (">=1", "any shape"): [False, True]}
    for row in rows:
        assert row["owner_silent flagged"] == _rate(expected[
            row["benign sharing teams"], row["shape"]])
        assert row["main test controls with no sharing team, k of 72"] == _rate([False] * 72)
        control_k = 4 if row["detector"] == "rule" else 5
        assert row["all main test controls, k of 86"] == _rate(
            [True] * control_k + [False] * (86 - control_k),
        )
    features = tables["Shared credential features by topology and size"]
    assert len(features) == 24
    for row in features:
        data = datasets[row["style"]]
        selected = [run for run, record in data.records.items()
                    if record.condition["topology"] == row["topology"]
                    and record.condition["offensive_group_size"] == row["offensive size"]
                    and (row["population"] == "all runs"
                         or record.condition["benign_sharing_teams"] == 0)]
        assert row["runs"] == len(selected)
        for column in evasion.SHARED_COLUMNS:
            assert row[f"mean {column}"] == data.runs.loc[selected, column].mean()


@pytest.mark.parametrize("held_pairs,held_fives,ending", (
    (True, False, "held for pairs and peer rings and did not hold for hubs of five."),
    (False, True, "held for hubs of five and did not hold for pairs and peer rings."),
    (True, True, "held for both pairs and peer rings and hubs of five."),
    (False, False, "did not hold for either pairs and peer rings or hubs of five."),
))
def test_verdict_conclusion_is_computed_for_both_shapes(
    shape_data, frozen_main, held_pairs: bool, held_fives: bool, ending: str,
) -> None:
    datasets, scores = shape_data
    result, main = frozen_main
    silent = scores["owner_silent"].copy()
    for method in METHODS:
        silent[method] = result.thresholds[method] - 1
    # A flag by just one of the three detectors is enough to reject the prediction.
    if not held_pairs:
        silent.loc["r0", "logistic"] = result.thresholds["logistic"] + 1
    if not held_fives:
        silent.loc["r5", "boosted"] = result.thresholds["boosted"] + 1
    counts = {run: (2, 2) for run in datasets["owner_silent"].records}
    verdict = evasion._verdict(datasets, {**scores, "owner_silent": silent}, result, main, counts)
    assert "owner_silent (16 of 16 pairs)." in verdict
    assert "hub credential (3 runs)." in verdict
    assert verdict.endswith("The prediction " + ending)


def test_verdict_rejects_nonzero_lender_pair_features(shape_data, frozen_main) -> None:
    datasets, scores = shape_data
    counts = {run: (2, 2) for run in datasets["owner_silent"].records}
    counts["r0"] = (1, 2)
    with pytest.raises(ValueError, match="lender-borrower"):
        evasion._verdict(datasets, scores, *frozen_main, counts)
