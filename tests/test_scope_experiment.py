import gzip
import hashlib
import importlib.util
import multiprocessing
import os
import socket
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from dataclasses import fields, replace
from pathlib import Path
from shutil import copyfile, copytree
from textwrap import dedent

import pandas as pd
import pytest

from swarmtrace.cli import main
from swarmtrace.detect import FILES_RULE_COLUMN
from swarmtrace.eval.data import load_runs
from swarmtrace.eval.harness import child_seed
from swarmtrace.eval.recorded import load_run_table, write_run_table
from swarmtrace.eval.scope import labels_for, run_kind, scope_split
from swarmtrace.features import feature_columns
from swarmtrace.features.spec import SCOPE
from swarmtrace.reproduce import ReproduceConfig, make_jobs
from swarmtrace.reproduce import scope as experiment
from swarmtrace.sim.runner import Condition, build_run, run_one
from swarmtrace.trace.context import ContextLevel
from swarmtrace.trace.io import Trace, read_manifest
from swarmtrace.trace.schema import TraceEvent
from swarmtrace.trace.tiers import Tier

DATA = Path(__file__).resolve().parents[1] / "data"
SEED = 20261120


def tiny_config(**changes: object) -> experiment.ScopeConfig:
    # 88 controls give round(.3 * (88 - round(.3 * 88))) = 19 calibration controls.
    # Keep the real split, features and all four detectors, but shorten the traces.
    config = experiment.ScopeConfig(
        coordinated_groups=(1,), channels=("message",), topologies=("peer",),
        group_sizes=(2,), mistake_rates=(0,), control_repeats=88,
        offensive_repeats=6, identical_repeats=1, n_ticks=8, n_bootstrap=1, workers=1,
    )
    return replace(config, **changes)


def file_bytes(root: Path) -> dict[str, bytes]:
    return {path.relative_to(root).as_posix(): path.read_bytes()
            for path in sorted(root.rglob("*")) if path.is_file()}


@pytest.fixture(scope="module")
def tiny_outputs(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    root = tmp_path_factory.mktemp("scope-experiment")
    guard, markers = root / "socket-guard", root / "worker-markers"
    guard.mkdir()
    markers.mkdir()
    existing = importlib.util.find_spec("sitecustomize")
    startup = ""
    if existing is not None and existing.origin is not None:
        startup = ("import runpy\n"
                   f"runpy.run_path({existing.origin!r}, run_name='sitecustomize')\n\n")
    (guard / "sitecustomize.py").write_text(startup + dedent("""\
        import atexit
        import multiprocessing
        import os
        import socket
        from pathlib import Path

        class ForbiddenSocket(socket.socket):
            def __new__(cls, *args, **kwargs):
                raise AssertionError("scope must not open sockets")

        socket.socket = ForbiddenSocket

        def mark_guard():
            try:
                socket.socket()
            except AssertionError as error:
                assert str(error) == "scope must not open sockets"
            else:
                raise AssertionError("worker socket guard is not installed")
            marker = Path(os.environ["SWARMTRACE_SCOPE_MARKERS"]) / f"{os.getpid()}.txt"
            marker.write_text(multiprocessing.current_process().name, encoding="utf-8")

        def mark_worker():
            if multiprocessing.current_process().name != "MainProcess":
                mark_guard()

        mark_guard()
        atexit.register(mark_worker)
        """), encoding="utf-8")

    class ForbiddenSocket(socket.socket):
        def __new__(cls, *args: object, **kwargs: object) -> None:
            raise AssertionError("scope must not open sockets")

    with pytest.MonkeyPatch.context() as patch:
        pythonpath = os.environ.get("PYTHONPATH")
        patch.setenv("PYTHONPATH", str(guard) + (os.pathsep + pythonpath if pythonpath else ""))
        patch.setenv("SWARMTRACE_SCOPE_MARKERS", str(markers))
        patch.setattr(socket, "socket", ForbiddenSocket)
        with pytest.raises(AssertionError, match="scope must not open sockets"):
            socket.socket()
        for workers, name in ((1, "one"), (2, "two")):
            experiment.run_scope(root / name, tiny_config(workers=workers))
    worker_names = [path.read_text(encoding="utf-8") for path in markers.glob("*.txt")]
    assert any(name.startswith("SpawnProcess-") for name in worker_names), worker_names
    return root / "one", root / "two"


def test_default_grid_counts_and_disjoint_seed_namespaces() -> None:
    config = experiment.ScopeConfig()
    jobs = experiment.make_scope_jobs(config)
    twins = experiment.make_identical_jobs(config)
    assert len(jobs) == 1134 and len(twins) == 108
    assert Counter(job.condition.offensive_group_size > 0 for job in jobs) == {
        False: 486, True: 648,
    }
    assert Counter(job.condition.violation_size for job in jobs
                   if job.condition.offensive_group_size) == {0: 162, 1: 162, 2: 162, 5: 162}
    assert Counter(job.condition.scope_mistake_rate for job in jobs) == {0: 378, 2: 378, 5: 378}
    assert [job.seed for job in jobs] == [child_seed(SEED, 95, i) for i in range(1134)]
    assert [job.seed for job in twins] == [child_seed(SEED, 96, i) for i in range(108)]
    assert all(job.dataset == "scope" and job.condition.scope == "on"
               and job.condition.benign_credential_sharing == 10 for job in jobs)
    assert all(job.dataset == "identical" and job.condition.scope == "on"
               and job.condition.benign_credential_sharing == 100 for job in twins)
    main_seeds = {job.seed for job in make_jobs(ReproduceConfig()) if job.dataset == "main"}
    scope_seeds, identical_seeds = ({job.seed for job in group} for group in (jobs, twins))
    assert len(scope_seeds) == 1134 and len(identical_seeds) == 108
    assert main_seeds.isdisjoint(scope_seeds | identical_seeds)
    assert scope_seeds.isdisjoint(identical_seeds)
    counts = experiment.preflight(config)
    assert counts["legacy"] == (237, 324, 102, 132, 147, 192)
    assert counts["strict"] == (318, 243, 135, 99, 195, 144)


def test_table_columns_seeds_counts_and_outputs(tiny_outputs: tuple[Path, Path]) -> None:
    out = tiny_outputs[0]
    table = load_run_table(out / "scope" / "runs.csv.gz")
    records = table.records
    assert len(records) == 112
    assert Counter(run_kind(record) for record in records) == {
        "control": 88, "in_scope": 6, "violation_1": 6, "violation_2": 6, "violation_5": 6,
    }
    expected = list(feature_columns("run", Tier.V1))
    for level in ContextLevel:
        expected.extend(f"{column}__{level.value}"
                        for column in feature_columns("run", Tier.V1, (SCOPE,), context=level))
    assert list(table.features.columns) == expected
    assert list(table.diagnostics.columns) == [FILES_RULE_COLUMN]
    assert str(table.diagnostics[FILES_RULE_COLUMN].dtype) == "int64"
    assert set(record.condition["seed"] for record in records) == {
        job.seed for job in experiment.make_scope_jobs(tiny_config())}
    assert all(record.condition["dataset"] == "scope" for record in records)
    for record in records:
        assert type(record.outcomes["objective_completed"]) is int
        assert record.outcomes["objective_completed"] in (0, 1)
        assert all(type(value) in (int, str) for value in record.condition.values())
        assert all(type(value) in (int, str) for value in record.outcomes.values())
    csv = gzip.decompress((out / "scope" / "runs.csv.gz").read_bytes()).decode("utf-8")
    assert all(prefix in csv.splitlines()[0]
               for prefix in ("label_", "condition_", "outcome_", "__C0", "__C1", "__C2"))
    assert b"\r" not in csv.encode("utf-8")
    assert {path.name for path in out.iterdir()} == {"scope", "scope.md", "scope-identical.md"}
    assert {path.name for path in (out / "scope").iterdir()} == {"runs.csv.gz", "raw"}
    report = (out / "scope.md").read_text(encoding="utf-8")
    assert "Strict" in report and "Legacy" in report
    assert "aggregation-only reference" in report
    for metric in ("violation_vs_in_scope_auroc", "violation_vs_in_scope_auroc_size_5",
                   "violation_vs_in_scope_auroc_mistake_rate_0", "fpr_sharing_controls",
                   "fpr_nonsharing_controls", "fpr_in_scope_relays", "reported, not gated",
                   "detection_rate_violation_size_5", "detection_rate_mistake_rate_0"):
        assert metric in report
    split = scope_split(records, SEED)
    test = [record for record in records if record.run_id in split.test]
    sharing = sum(not record.positive and record.condition["benign_sharing_teams"] > 0
                  for record in test)
    assert f"sharing controls: {sharing}" in report
    assert "in-scope relays: 2" in report
    for labelling, count in (("strict", 20), ("legacy", 19)):
        labels = labels_for(records, labelling)
        assert sum(not labels[run] for run in split.calibration) == count
    assert report.endswith("```\n")
    assert [line for line in report.splitlines()
            if line.lstrip().startswith(("```", "~~~"))] == ["```text", "```"]
    checksum_block = report.split("```text\n")[1].removesuffix("```\n")
    checksums = dict(line.split("  ", 1)[::-1] for line in checksum_block.splitlines())
    artifacts = {name: content for name, content in file_bytes(out).items()
                 if name.startswith("scope/")}
    assert checksums == {name: hashlib.sha256(content).hexdigest()
                         for name, content in artifacts.items()}
    assert "1 of 1 identical" in (out / "scope-identical.md").read_text(encoding="utf-8")
    assert "AUROC is exactly 0.5 at every context level" in (
        out / "scope-identical.md").read_text(encoding="utf-8")


def test_workers_and_socket_guard_preserve_every_output(tiny_outputs: tuple[Path, Path]) -> None:
    assert file_bytes(tiny_outputs[0]) == file_bytes(tiny_outputs[1])


def test_gate_fails_before_sweep_and_cli_names_pair(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    config = tiny_config(n_ticks=160)
    calls = []

    def altered(condition: Condition, seed: int, out: Path) -> Path:
        assert condition.benign_credential_sharing == 100, "main sweep ran after gate failure"
        calls.append(condition)
        if condition.offensive_group_size:
            control = replace(condition, offensive_group_size=0)
            setup = build_run(control, seed)
            assert condition.offensive_group_size == len(setup.groups[setup.focal_group].members)
            condition = replace(condition, violation_size=1)
        return run_one(condition, seed, out)

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("main sweep ran after gate failure")

    monkeypatch.setattr(experiment, "run_one", altered)
    monkeypatch.setattr(experiment, "_simulate", forbidden)
    monkeypatch.setattr(experiment, "ScopeConfig", lambda **kwargs: config)
    out = tmp_path / "failed"
    with pytest.raises(SystemExit) as error:
        main(["scope", "--seed", str(SEED), "--out", str(out), "--workers", "1"])
    assert error.value.code != 0 and len(calls) == 2
    assert set(file_bytes(out)) == {"scope-identical.md"}
    report = (out / "scope-identical.md").read_text(encoding="utf-8")
    pair = experiment.make_identical_jobs(config)[0]
    assert pair.directory in report and str(pair.seed) in report and "trace.jsonl" in report
    assert pair.directory in capsys.readouterr().err
    assert "AUROC is exactly 0.5" not in report


def test_preflight_and_nonempty_output_refuse_before_simulation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("must refuse before any simulation or assembly")

    monkeypatch.setattr(experiment, "run_one", forbidden)
    monkeypatch.setattr(experiment, "build_run", forbidden)
    out = tmp_path / "small"
    with pytest.raises(ValueError, match="legacy.*19 calibration controls"):
        experiment.run_scope(out, tiny_config(control_repeats=1))
    assert not out.exists()
    occupied = tmp_path / "occupied"
    occupied.mkdir()
    (occupied / "keep.txt").write_bytes(b"keep")
    with pytest.raises(ValueError, match="fresh directory"):
        experiment.run_scope(occupied, tiny_config())
    assert file_bytes(occupied) == {"keep.txt": b"keep"}


def test_timing_cli_dispatches_without_running_experiment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    def timed(out: Path, config: experiment.ScopeConfig, count: int) -> None:
        assert out == tmp_path and config.seed == SEED and config.workers == 4 and count == 50

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("timing mode must not publish experiment results")

    monkeypatch.setattr(experiment, "time_scope_runs", timed)
    monkeypatch.setattr(experiment, "run_scope", forbidden)
    main(["scope", "--seed", str(SEED), "--out", str(tmp_path), "--workers", "4",
          "--time-runs", "50"])


def test_timing_measures_requested_runs_and_leaves_no_results(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    seen = []

    def simulate(task: tuple) -> None:
        job, root = task
        seen.append(job.seed)
        (root / job.directory).write_bytes(b"timing-only")

    times = iter((10.0, 12.0))
    monkeypatch.setattr(experiment, "_simulate", simulate)
    monkeypatch.setattr(experiment, "perf_counter", lambda: next(times))
    result = experiment.time_scope_runs(tmp_path, tiny_config(), 50)
    assert len(seen) == len(set(seen)) == 50
    assert result["runs"] == 50 and result["seconds"] == 2.0
    assert result["simulations"] == 114
    assert result["projected_seconds"] == pytest.approx(4.56)
    assert "excludes feature extraction, fitting and reporting" in capsys.readouterr().out
    assert not list(tmp_path.iterdir())


def assert_samples_regenerate(out: Path, regenerated: Path) -> None:
    table = load_run_table(out / "scope" / "runs.csv.gz")
    by_id = {record.run_id: record for record in table.records}
    samples = sorted(path for path in (out / "scope" / "raw").iterdir() if path.is_dir())
    assert len(samples) == 2
    manifests = [read_manifest(sample / "manifest.json") for sample in samples]
    assert {value.condition["violation_size"] for value in manifests} == {0, 5}
    assert len({value.seed for value in manifests}) == 2
    assert len({tuple(value.condition[key] for key in
                      ("channel", "topology", "coordinated_groups", "offensive_group_size",
                       "scope_mistake_rate")) for value in manifests}) == 1
    for sample, manifest in zip(samples, manifests, strict=True):
        assert manifest.condition["offensive_group_size"] > 0
        record = by_id[manifest.run_id]
        requested = {field.name: manifest.condition[field.name] for field in fields(Condition)
                     if field.name in manifest.condition}
        condition = Condition(**requested)
        directory = run_one(condition, manifest.seed, regenerated / sample.name)
        assert file_bytes(directory) == file_bytes(sample)
        actual_records = load_runs(regenerated)
        actual_record = next(value for value in actual_records if value.run_id == manifest.run_id)
        actual = experiment.build_scope_table([actual_record])
        pd.testing.assert_frame_equal(actual[table.features.columns],
                                      table.features.loc[[manifest.run_id]],
                                      check_exact=True)
        if FILES_RULE_COLUMN in table.diagnostics:
            pd.testing.assert_frame_equal(actual[[FILES_RULE_COLUMN]],
                                          table.diagnostics.loc[[manifest.run_id]],
                                          check_exact=True)
        assert record.positive == actual_record.positive
        assert record.condition["seed"] == manifest.seed
        assert all(record.condition[key] == value for key, value in manifest.condition.items())
        assert record.outcomes["objective_completed"] == int(
            actual_record.labels.objective_completed)
        matching = [value for value in table.records
                    if all(value.condition[key] == manifest.condition[key] for key in
                           ("channel", "topology", "coordinated_groups", "offensive_group_size",
                            "scope_mistake_rate", "violation_size"))]
        assert manifest.run_id == min(value.run_id for value in matching)


def test_tiny_raw_samples_regenerate(tiny_outputs: tuple[Path, Path], tmp_path: Path) -> None:
    assert_samples_regenerate(tiny_outputs[0], tmp_path)


@pytest.mark.skipif(not (DATA / "scope").is_dir(), reason="scope data has not been committed")
def test_committed_scope_samples_regenerate(tmp_path: Path) -> None:
    assert_samples_regenerate(DATA, tmp_path)
    assert sum(path.stat().st_size for path in DATA.rglob("*") if path.is_file()) < 20_000_000


def test_distinct_files_counts_ok_reads_per_agent_not_reads_or_union() -> None:
    rows = [
        ("a-00000001", "read", "f-00000001", "ok"),
        ("a-00000001", "read", "f-00000001", "ok"),
        ("a-00000001", "read", "f-00000002", "ok"),
        ("a-00000001", "read", "f-00000003", "denied"),
        ("a-00000002", "read", "f-00000004", "ok"),
        ("a-00000002", "write", "f-00000005", "ok"),
    ]
    events = tuple(TraceEvent(1, "0123456789abcdef", i, i, agent, tool, target,
                              None, {"status": status}, None, None)
                   for i, (agent, tool, target, status) in enumerate(rows))
    trace = Trace("0123456789abcdef", Tier.V0, events)
    assert experiment.distinct_files_read_max(trace) == 2
    assert experiment.distinct_files_read_max(replace(trace, events=())) == 0


def assert_c0_c1_identical(table: pd.DataFrame) -> None:
    c0 = table.filter(regex="__C0$").rename(columns=lambda name: name.removesuffix("__C0"))
    c1 = table.filter(regex="__C1$").rename(columns=lambda name: name.removesuffix("__C1"))
    assert len(c0.columns) > 0
    pd.testing.assert_frame_equal(c0, c1, check_exact=True)


def test_tiny_context_identity_and_added_report_sections(tiny_outputs: tuple[Path, Path]) -> None:
    out = tiny_outputs[0]
    table = load_run_table(out / "scope" / "runs.csv.gz")
    assert_c0_c1_identical(table.features)
    report = (out / "scope.md").read_text(encoding="utf-8")
    assert ("C0 and C1 scope columns are identical in every run; their rows differ only "
            "in bootstrap seed.") in report
    assert ("At C2 under the strict labelling the threshold is set by in-scope relays "
            "that made an out-of-scope mistake read.") in report
    for context in ("aggregation-only reference", "C0", "C1", "C2"):
        block = report.split(f"## {context}: files_rule\n", 1)[1].split("\n## ", 1)[0]
        assert "| full_trace_threshold | nan" not in block
        assert "| violation_vs_in_scope_auroc_size_1 |" in block
    comparison = report.split("## Strict detection by violation size\n", 1)[1].split("\n## ", 1)[0]
    assert "| Size 1 | Size 2 | Size 5 |" in comparison
    for context in ("C0", "C2"):
        for detector in ("scope_rule", "files_rule", "logistic", "boosted"):
            assert f"| {context} | {detector} |" in comparison
    breadth = report.split("## Observed borrowed-session breadth\n", 1)[1].split("\n## ", 1)[0]
    for name, positive in (("in-scope relays", True), ("benign controls", False)):
        ids = [record.run_id for record in table.records
               if (run_kind(record) == "in_scope" if positive else not record.positive)]
        values = table.features.loc[ids, "borrowed_session_breadth_max__C0"]
        assert (f"| {name} | {len(ids)} | {values.min():.4f} | {values.median():.4f} | "
                f"{values.max():.4f} |") in breadth


@pytest.mark.skipif(not (DATA / "scope").is_dir(), reason="scope data has not been committed")
def test_recorded_context_identity_and_original_column_bytes(tmp_path: Path) -> None:
    path = DATA / "scope" / "runs.csv.gz"
    recorded = load_run_table(path)
    assert_c0_c1_identical(recorded.features)
    # Adding the diagnostic must not change any existing cell, serialization or column order.
    extended = recorded.features.assign(**{FILES_RULE_COLUMN: 0})
    target = tmp_path / "extended.csv.gz"
    write_run_table(target, extended, recorded.records,
                    extra={record.run_id: record.outcomes for record in recorded.records})
    original_csv = gzip.decompress(path.read_bytes()).decode("utf-8").splitlines()
    extended_csv = gzip.decompress(target.read_bytes()).decode("utf-8").splitlines()
    original_columns = original_csv[0].split(",")
    extended_columns = extended_csv[0].split(",")
    keep = [name for name in original_columns if name != FILES_RULE_COLUMN]
    assert extended_columns == [*keep, FILES_RULE_COLUMN]
    before = [original_columns.index(name) for name in keep]
    after = [extended_columns.index(name) for name in keep]
    assert [[row.split(",")[i] for i in before] for row in original_csv] == [
        [row.split(",")[i] for i in after] for row in extended_csv]
    original = tmp_path / "original.csv.gz"
    write_run_table(original, recorded.features, recorded.records,
                    extra={record.run_id: record.outcomes for record in recorded.records})
    if recorded.diagnostics.empty:
        assert original.read_bytes() == path.read_bytes()


@pytest.mark.skipif(not (DATA / "scope.md").is_file(), reason="scope report has not been committed")
def test_recorded_report_lines_survive_additive_diagnostics(tmp_path: Path) -> None:
    # Replay recorded features only. No simulations or writes to data; one native model thread.
    root = tmp_path / "scope"
    copytree(DATA / "scope" / "raw", root / "raw")
    path = root / "runs.csv.gz"
    copyfile(DATA / "scope" / "runs.csv.gz", path)
    config = experiment.ScopeConfig()
    with experiment._worker_threads(), ProcessPoolExecutor(
        max_workers=1, mp_context=multiprocessing.get_context("spawn"),
    ) as pool:
        rows, calibration = pool.submit(experiment._evaluate_table, path, SEED,
                                        config.n_bootstrap).result()
    recorded = load_run_table(path)
    report = experiment._report(rows, recorded.records, config, tmp_path,
                                calibration=calibration, table=recorded.features)
    # Artifact hashes change with the new column; the report body remains additive.
    baseline = (DATA / "scope.md").read_text(encoding="utf-8")
    baseline_body = baseline.split("## SHA-256", 1)[0].split("```", 1)[0]
    remaining = iter(report.split("```", 1)[0].splitlines(keepends=True))
    for line in baseline_body.splitlines(keepends=True):
        assert any(candidate == line for candidate in remaining), f"Changed original line: {line}"
