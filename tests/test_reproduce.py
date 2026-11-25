import gzip
import importlib.util
import json
import os
import socket
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from pathlib import Path
from textwrap import dedent

import numpy as np
import pandas as pd
import pytest

from swarmtrace.cli import main
from swarmtrace.eval.data import build_tier_data, load_runs
from swarmtrace.eval.harness import EvalConfig, evaluate_split, family_data
from swarmtrace.eval.headline import format_readme_headline
from swarmtrace.eval.recorded import load_recorded, write_gzip, write_recorded
from swarmtrace.eval.splits import Split
from swarmtrace.features import feature_columns
from swarmtrace.reproduce import ReproduceConfig, make_jobs, reproduce
from swarmtrace.reproduce.controls import require_loud_detection, shuffled_labels
from swarmtrace.reproduce.pipeline import _simulate, render_readme, split_inventory
from swarmtrace.sim.runner import Condition, run_one
from swarmtrace.trace.tiers import Tier


@pytest.fixture(scope="module")
def small_runs(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("reproduce-runs")
    for index in range(8):
        run_one(Condition("message", "peer", 2 if index % 2 else 0, 1, 32),
                index + 500, root / str(index))
    return root


def test_process_features_and_recorded_bytes_are_worker_independent(
    small_runs: Path, tmp_path: Path,
) -> None:
    records = load_runs(small_runs)[:2]
    one = build_tier_data(records, Tier.V1, workers=1, checkpoint_every=16,
                          retain_traces=False)
    two = build_tier_data(records, Tier.V1, workers=2, checkpoint_every=16,
                          retain_traces=False)
    for field in ("runs", "volume", "pairs", "prefix_runs", "prefix_volume"):
        pd.testing.assert_frame_equal(getattr(one, field), getattr(two, field))
    for name, data in (("one", one), ("two", two)):
        write_recorded(tmp_path / name, data)
        for record in records:
            write_gzip(tmp_path / name / "raw" / record.run_id / "trace.jsonl.gz",
                       record.trace_path.read_bytes())
    first = {p.relative_to(tmp_path / "one"): p.read_bytes()
             for p in (tmp_path / "one").rglob("*") if p.is_file()}
    second = {p.relative_to(tmp_path / "two"): p.read_bytes()
              for p in (tmp_path / "two").rglob("*") if p.is_file()}
    assert first == second
    for path, contents in first.items():
        if path.suffix == ".gz":
            assert contents[3] == 0  # No filename or other optional header fields.
            assert contents[4:8] == b"\0" * 4
            assert b"\r" not in gzip.decompress(contents)
    restored = load_recorded(tmp_path / "one", Tier.V1)
    assert restored.checkpoint_every == 16
    assert not restored.traces
    for field in ("runs", "volume", "pairs", "prefix_runs", "prefix_volume"):
        pd.testing.assert_frame_equal(getattr(one, field), getattr(restored, field),
                                      check_exact=True)
    np.testing.assert_array_equal(one.pair_labels, restored.pair_labels)
    assert [(r.positive, r.condition) for r in one.records.values()] == [
        (r.positive, r.condition) for r in restored.records.values()
    ]
    write_recorded(tmp_path / "reloaded", restored)
    for path in (tmp_path / "reloaded").rglob("*"):
        if path.is_file():
            assert path.read_bytes() == first[path.relative_to(tmp_path / "reloaded")]


def test_recorded_float_parsing_is_exact_without_deprecated_options(
    small_runs: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = build_tier_data(load_runs(small_runs)[:1], Tier.V1, checkpoint_every=32)
    data.volume.iloc[0] = [
        float.fromhex("0x1.999999999999bp-4"), -0.0,
        float.fromhex("0x0.0000000000001p-1022"),
        float.fromhex("0x1.fffffffffffffp+1023"), float("nan"),
    ]
    write_recorded(tmp_path / "original", data)
    original_read_csv = pd.read_csv

    def read_without_deprecated_option(*args: object, **kwargs: object) -> pd.DataFrame:
        assert "float_precision" not in kwargs
        return original_read_csv(*args, **kwargs)

    monkeypatch.setattr(pd, "read_csv", read_without_deprecated_option)
    restored = load_recorded(tmp_path / "original", Tier.V1)
    pd.testing.assert_frame_equal(data.volume, restored.volume, check_exact=True)
    assert np.signbit(restored.volume.iloc[0, 1])
    write_recorded(tmp_path / "restored", restored)
    for path in (tmp_path / "original").rglob("*"):
        if path.is_file():
            rewritten = tmp_path / "restored" / path.relative_to(tmp_path / "original")
            assert path.read_bytes() == rewritten.read_bytes()


def test_recorded_eval_never_reads_traces(
    small_runs: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = build_tier_data(load_runs(small_runs), Tier.V0, checkpoint_every=32)
    write_recorded(tmp_path / "recorded", data)

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("recorded evaluation tried to read a trace")

    monkeypatch.setattr("swarmtrace.eval.data.read_trace", forbidden)
    main(["eval", "--runs", str(tmp_path / "recorded"), "--out", str(tmp_path / "report"),
          "--seed", "17", "--tiers", "V0", "--bootstrap", "2",
          "--families", "generic", "aggregation", "all"])
    report = (tmp_path / "report" / "results-V0.md").read_text(encoding="utf-8")
    assert all(f"Features: {family}" in report for family in ("generic", "aggregation", "all"))
    assert "volume (family-independent)" in report
    assert "every 32 ticks" in report


def test_families_select_exact_columns_and_leave_volume_unchanged(small_runs: Path) -> None:
    data = build_tier_data(load_runs(small_runs)[:1], Tier.V1, checkpoint_every=32)
    for family in ("generic", "aggregation", "all"):
        selected = family_data(data, family)
        families = None if family == "all" else (family,)
        assert tuple(selected.runs.columns) == feature_columns("run", Tier.V1, families)
        assert tuple(selected.pairs.columns) == feature_columns("pair", Tier.V1, families)
        assert tuple(selected.prefix_runs.columns) == tuple(selected.runs.columns)
        pd.testing.assert_frame_equal(selected.volume, data.volume)
        pd.testing.assert_frame_equal(selected.prefix_volume, data.prefix_volume)


def test_family_selection_and_pair_fitting_exclude_calibration(
    small_runs: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = build_tier_data(load_runs(small_runs), Tier.V1, checkpoint_every=32)
    seen: list[set[str]] = []
    from swarmtrace.detect import PairScorer

    original = PairScorer.fit

    def spy(self: PairScorer, frame: pd.DataFrame, labels: np.ndarray) -> PairScorer:
        seen.append(set(frame.index.get_level_values("run_id")))
        return original(self, frame, labels)

    monkeypatch.setattr(PairScorer, "fit", spy)
    ids = tuple(data.records)
    split = Split("all fitting", "in-distribution", ids, ())
    # Use all runs except one from each class, retaining at least two fitting positives.
    test = tuple(next(r for r in ids if data.records[r].positive == value)
                 for value in (False, True))
    split = replace(split, train=tuple(r for r in ids if r not in test), test=test)
    config = EvalConfig(n_bootstrap=2, n_folds=2)
    result = evaluate_split(data, split, config, 1, family="aggregation")
    assert seen and all(runs <= set(result.fitting) for runs in seen)
    assert all(not runs & set(result.calibration + split.test) for runs in seen)
    assert result.fitted["logistic"].columns == feature_columns("run", Tier.V1, ("aggregation",))
    assert result.fitted["pairs"].columns == feature_columns("pair", Tier.V1, ("aggregation",))
    assert all(row.family == "aggregation" for row in result.rows)


def test_default_splits_have_enough_calibration_controls() -> None:
    config = ReproduceConfig(seed=20261120)
    assert config.runs_per_condition == 2
    assert config.checkpoint_every == 8
    assert config.shuffle_repeats == 20
    jobs = make_jobs(config)
    primary = [job for job in jobs if job.dataset == "main"]
    assert sum(job.condition.offensive_group_size == 0 for job in primary) == 288
    assert sum(job.condition.offensive_group_size > 0 for job in primary) == 108
    # This helper uses the same split/calibration seed rules as evaluation.
    counts = split_inventory(jobs, config)
    assert len(counts) == 6
    assert min(row["calibration_controls"] for row in counts) >= 19


def test_shuffle_is_seeded_across_whole_runs() -> None:
    ids = [f"{i:016x}" for i in range(100)]
    labels = dict(zip(ids, [True] * 25 + [False] * 75))
    first = shuffled_labels(labels, 7)
    assert first == shuffled_labels(dict(reversed(list(labels.items()))), 7)
    assert first != labels and first != shuffled_labels(labels, 8)
    assert sum(first.values()) == sum(labels.values())


def test_loud_control_failure_is_actionable() -> None:
    flags = {method: {bar: [True, True] for bar in
                     ("calibrated_threshold", "nonsharing_controls", "all_controls")}
             for method in ("logistic", "boosted")}
    flags["boosted"]["all_controls"] = [False, False]
    require_loud_detection(flags)
    for method, bar in (("logistic", "calibrated_threshold"), ("boosted", "calibrated_threshold"),
                        ("logistic", "nonsharing_controls"), ("boosted", "nonsharing_controls"),
                        ("logistic", "all_controls")):
        changed = {name: dict(bars) for name, bars in flags.items()}
        changed[method][bar] = [True, False]
        with pytest.raises(ValueError, match=f"loud.*V1.*aggregation.*{method}.*{bar}"):
            require_loud_detection(changed)
        changed[method].pop(bar)
        with pytest.raises(ValueError, match=f"{method}.*{bar}"):
            require_loud_detection(changed)
    with pytest.raises(ValueError, match="loud"):
        require_loud_detection({})


def test_reproduce_allows_separately_generated_stability(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    diagnostic = tmp_path / "split-stability.md"
    diagnostic.write_text("separate recorded-data diagnostic\n", encoding="utf-8")

    def stop_before_simulation(*args: object) -> None:
        raise RuntimeError("simulation sentinel")

    monkeypatch.setattr("swarmtrace.reproduce.pipeline._simulate", stop_before_simulation)
    with pytest.raises(RuntimeError, match="simulation sentinel"):
        reproduce(tmp_path, ReproduceConfig(workers=1))
    assert diagnostic.read_text(encoding="utf-8") == "separate recorded-data diagnostic\n"


def test_reproduce_rejects_insufficient_calibration_and_cli_propagates_control_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A test-sized sweep cannot calibrate at alpha=.05 and must fail preflight.
    config = ReproduceConfig(seed=17, workers=1, runs_per_condition=1,
                             n_ticks=24, checkpoint_every=24,
                             control_repeats=1, n_bootstrap=2, shuffle_repeats=1,
                             sample_runs=1, hold_out=(),
                             conditions=(Condition("message", "peer", 0, 1, 24),
                                         Condition("message", "peer", 2, 1, 24)))
    for name, workers in (("one", 1), ("two", 2)):
        with pytest.raises(ValueError, match="calibration controls"):
            reproduce(tmp_path / name, replace(config, workers=workers))
    assert not (tmp_path / "one" / "dataset").exists()

    def broken(out: Path, config: ReproduceConfig, *, readme: Path | None = None) -> None:
        assert config.runs_per_condition == 2
        assert config.checkpoint_every == 8
        raise ValueError("loud control failed at V1 with aggregation features")

    monkeypatch.setattr("swarmtrace.reproduce.commands.reproduce", broken)
    with pytest.raises(SystemExit) as error:
        main(["reproduce", "--seed", "17", "--out", str(tmp_path / "broken")])
    assert error.value.code == 2


def test_reproduce_with_workers_completes_without_opening_sockets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing = importlib.util.find_spec("sitecustomize")
    startup = ""
    if existing is not None and existing.origin is not None:
        # Preserve environment startup (for example Debian/conda path setup), then
        # install our guard last so startup cannot replace the worker socket patch.
        startup = ("import runpy\n"
                   f"runpy.run_path({existing.origin!r}, run_name='sitecustomize')\n\n")
    guard = tmp_path / "socket-guard"
    markers = tmp_path / "worker-markers"
    guard.mkdir()
    markers.mkdir()
    (guard / "sitecustomize.py").write_text(startup + dedent("""\
        import atexit
        import multiprocessing
        import os
        import socket
        from pathlib import Path

        # Keep a class so modules such as ssl can still define socket subclasses.
        class ForbiddenSocket(socket.socket):
            def __new__(cls, *args, **kwargs):
                raise AssertionError("reproduction must not open sockets")

        socket.socket = ForbiddenSocket

        def mark_guard():
            try:
                socket.socket()
            except AssertionError as error:
                assert str(error) == "reproduction must not open sockets"
            else:
                raise AssertionError("worker socket guard is not installed")
            marker = Path(os.environ["SWARMTRACE_SOCKET_MARKERS"]) / f"{os.getpid()}.txt"
            marker.write_text(multiprocessing.current_process().name, encoding="utf-8")

        def mark_worker():
            # Spawn assigns the pool process name after startup. A resource tracker
            # remains MainProcess and may outlive the test's temporary directory.
            if multiprocessing.current_process().name != "MainProcess":
                mark_guard()

        mark_guard()
        atexit.register(mark_worker)
        """), encoding="utf-8")
    monkeypatch.setenv("SWARMTRACE_SOCKET_MARKERS", str(markers))
    pythonpath = os.environ.get("PYTHONPATH")
    monkeypatch.setenv("PYTHONPATH", str(guard) + (os.pathsep + pythonpath if pythonpath else ""))
    for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        monkeypatch.setenv(name, "1")

    def no_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("reproduction must not open sockets")

    monkeypatch.setattr(socket, "socket", no_network)
    with pytest.raises(AssertionError, match="reproduction must not open sockets"):
        socket.socket()
    # Leave create_connection and socketpair alone; multiprocessing uses local pipes.
    # This two-cell grid has 88 controls (19 calibration) and 44 positives (22 fitting).
    # Fewer repetitions lose the 19-control preflight or boosted's 20-row positive leaf.
    config = ReproduceConfig(
        workers=2, runs_per_condition=44, control_repeats=2, n_ticks=64,
        checkpoint_every=64, n_bootstrap=1, shuffle_repeats=1, sample_runs=1, hold_out=(),
        conditions=(Condition("message", "peer", 0, 1, 64, benign_credential_sharing=0),
                    Condition("message", "peer", 5, 1, 64, benign_credential_sharing=0,
                              loud_reuses=32)),
    )
    counts = split_inventory(make_jobs(config), config)
    assert len(counts) == 1
    assert counts[0]["calibration_controls"] == 19
    assert counts[0]["fitting_positive"] == 22
    out = tmp_path / "reproduced"
    reports = reproduce(out, config)
    assert {path.name for path in reports} == {
        "inventory.md", "results-V0.md", "results-V1.md", "results-V2.md",
        "controls.md", "negative-control.md", "headline.md",
    }
    assert all(path.is_file() for path in reports)
    experiment = json.loads((out / "experiment.json").read_text(encoding="utf-8"))
    require_loud_detection(experiment["loud_flags_V1_aggregation"])
    worker_markers = {int(path.stem): path.read_text(encoding="utf-8")
                      for path in markers.glob("*.txt")}
    assert any(pid != os.getpid() and name.startswith("SpawnProcess-")
               for pid, name in worker_markers.items()), (
        f"socket guard did not run in a spawned pool worker: {worker_markers}"
    )


def test_tiny_simulation_grid_is_worker_independent(tmp_path: Path) -> None:
    config = ReproduceConfig(seed=9, runs_per_condition=1, n_ticks=8, control_repeats=1,
                             conditions=(Condition("message", "peer", 0, 1),
                                         Condition("message", "peer", 2, 1)))
    jobs = make_jobs(config)
    for job in jobs:
        _simulate((job, tmp_path / "one"))
    with ProcessPoolExecutor(max_workers=2) as pool:
        list(pool.map(_simulate, [(job, tmp_path / "two") for job in jobs]))
    one = {p.relative_to(tmp_path / "one"): p.read_bytes()
           for p in (tmp_path / "one").rglob("*") if p.is_file()}
    two = {p.relative_to(tmp_path / "two"): p.read_bytes()
           for p in (tmp_path / "two").rglob("*") if p.is_file()}
    assert one == two and len(one) == 3 * len(jobs)


def test_readme_renderer_preserves_generated_tables_verbatim(tmp_path: Path) -> None:
    readme = tmp_path / "README.md"
    readme.write_text("Before\n<!-- BEGIN GENERATED RESULTS -->\nPending\n"
                      "<!-- END GENERATED RESULTS -->\nAfter\n", encoding="utf-8")
    report = tmp_path / "headline.md"
    headline = (Path(__file__).resolve().parents[1] / "data" / "headline.md").read_text(
        encoding="utf-8")
    report.write_text(headline, encoding="utf-8")
    render_readme(readme, report)
    result = readme.read_text(encoding="utf-8")
    assert format_readme_headline(headline) in result
    assert headline not in result and "| held-out " not in result
    assert report.read_text(encoding="utf-8") == headline
    assert result.startswith("Before\n") and result.endswith("\nAfter\n")
    assert "Pending" not in result


def test_loud_reuse_is_recorded_in_condition(tmp_path: Path) -> None:
    run_one(Condition("message", "peer", 2, 1, 96, loud_reuses=16), 4, tmp_path / "loud")
    data = build_tier_data(load_runs(tmp_path), Tier.V1, checkpoint_every=96)
    assert data.pairs["shared_credential_logins"].max() >= 16
    manifest = json.loads((tmp_path / "loud" / "manifest.json").read_text())
    assert manifest["condition"]["loud_reuses"] == 16
