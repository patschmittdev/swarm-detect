"""Replacement sweep: three positive replicates, 90 controls per condition.

One real four-rate tiny sweep is shared across the module. A small sample checks
worker-independent raw and recorded bytes; report rendering repeats from measured
results. No simulator, extractor, fit, calibration or bootstrap in the sweep is
faked. Control repeats are absolute counts per condition, independent of positive
replicates. All new seed streams descend from (91, rate_index, 2, ...).
"""

import hashlib
import importlib
import importlib.util
import json
import multiprocessing
import os
import re
import socket
import sys
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from functools import cache
from itertools import product
from pathlib import Path
from textwrap import dedent

import numpy as np
import pandas as pd
import pytest
from sklearn.utils.parallel import _get_threadpool_controller

from swarmtrace import cli
from swarmtrace.detect import RULE_COLUMN, OnlineDetector, PairScorer, RunDetector
from swarmtrace.eval import data as eval_data
from swarmtrace.eval import harness, metrics, splits
from swarmtrace.eval.recorded import write_recorded
from swarmtrace.features import feature_columns
from swarmtrace.reproduce import config as reproduce_config
from swarmtrace.reproduce import pipeline
from swarmtrace.reproduce.verify import verify
from swarmtrace.sim import runner
from swarmtrace.sim.sweep import condition_grid
from swarmtrace.trace.io import read_trace
from swarmtrace.trace.tiers import Tier

SEED = 20261120
RATES = (0, 5, 10, 30)
METHODS = ("rule", "logistic", "boosted")
TINY_REPLICATES = 2
TINY_POSITIVE_RUNS = 3 * TINY_REPLICATES
TINY_TICKS = 1
CONTROL_REPEAT_MARGIN = 2
HEADERS = (
    "rate", "runs", "fitting (positive, control)", "calibration (positive, control)",
    "test (positive, control)", "sharing test controls (q)", "A_s",
    "AUROC vs non-sharing controls", "overall AUROC", "expected 1 - q/2",
    "interval contains 1 - q/2", "interval contains 1 - q", "detection rate", "FPR",
    "calibration controls", "threshold",
)
HISTORY = (
    "A first sweep of 792 runs (one positive replicate, 8 control repeats) was too small "
    "to distinguish 1 - q/2 from 1 - q at rates 5 and 10 and was replaced by this one "
    "before any conclusion was written."
)
HASH_START = "```swarmtrace-sharing-sha256"
NUMBER = r"(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"


@pytest.fixture(scope="module")
def sweep():
    # A missing implementation is a real RED failure, never an importorskip.
    return importlib.import_module("swarmtrace.reproduce.sharing_sweep")


def _tiny_calibration_controls(control_repeats, rate_index):
    """Ask the production split functions; class counts do not depend on run identities."""
    labels = {f"control-{index:04d}": False
              for index in range(control_repeats)}
    labels.update({f"positive-{index:04d}": True for index in range(TINY_POSITIVE_RUNS)})
    ids = sorted(labels)
    split = splits.split_by_run(
        ids, [labels[run] for run in ids], harness.EvalConfig.test_fraction,
        harness.child_seed(SEED, 91, rate_index, 2, 1),
    )
    evaluation_seed = harness.child_seed(SEED, 91, rate_index, 2, 2)
    _, calibration = splits.calibration_split(
        split.train, [labels[run] for run in split.train], splits.CALIBRATION_FRACTION,
        harness.child_seed(evaluation_seed, harness.SEED_KEY + 1, 0),
    )
    return sum(not labels[run] for run in calibration)


@cache
def _minimum_control_repeats():
    # With the current 30%/30% splits this is 88 controls; 87 gives only 18.
    repeats = 1
    while min(_tiny_calibration_controls(repeats, index) for index in range(len(RATES))) < 19:
        repeats += 1
    return repeats


def _tiny_config(sweep, *, workers=1, control_repeats=None):
    if control_repeats is None:
        control_repeats = _minimum_control_repeats() + CONTROL_REPEAT_MARGIN
    return sweep.SharingSweepConfig(
        seed=SEED, workers=workers, runs_per_condition=TINY_REPLICATES,
        control_repeats=control_repeats,
        n_ticks=TINY_TICKS, checkpoint_every=TINY_TICKS, n_bootstrap=2,
        conditions=condition_grid(coordinated_groups=(1,), channels=("message",),
                                  topologies=("peer",), n_ticks=TINY_TICKS),
    )


def _patch_aliases(patch, original, replacement):
    """Observe the real function even when production imported it by name."""
    for name, module in tuple(sys.modules.items()):
        if name.startswith("swarmtrace.") and module is not None:
            for attribute, value in tuple(vars(module).items()):
                if value is original:
                    patch.setattr(module, attribute, replacement)


def _snapshot(root):
    return {path.relative_to(root).as_posix(): path.read_bytes()
            for path in root.rglob("*") if path.is_file()}


def _rows(report):
    rows = []
    for method in METHODS:
        section = report.split(f"## {method}\n", 1)[1].split("\n## ", 1)[0]
        lines = [line for line in section.splitlines() if line.startswith("|")]
        header = tuple(cell.strip() for cell in lines[0].strip("|").split("|"))
        assert header == HEADERS
        for line in lines[2:]:
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            rows.append({"detector": method, **dict(zip(header, cells, strict=True))})
    return rows


def _estimate(cell):
    found = re.search(rf"({NUMBER})\s*\[({NUMBER}),\s*({NUMBER})\]", cell)
    assert found is not None, f"missing value and interval: {cell!r}"
    return tuple(float(value) for value in found.groups())


def _assert_rate(cell, k, n):
    assert re.search(rf"\b{k} of {n}\b", cell), cell
    estimate = metrics.wilson(k, n)
    assert _estimate(cell) == pytest.approx(
        (estimate.value, estimate.low, estimate.high), abs=0.00051,
    )


def _seed_audit(patch):
    parents = {}
    calls = []
    original_seed, original_jobs = harness.child_seed, reproduce_config.make_jobs

    def seed(base, *key):
        value = original_seed(base, *key)
        calls.append((base, key, value))
        parents[value] = (base, key)
        return value

    def jobs(config):
        result = original_jobs(config)
        # make_jobs uses SeedSequence.spawn, not child_seed. Preserve that lineage
        # in the audit instead of requiring a second job generator for this sweep.
        for index, job in enumerate(result):
            parents[job.seed] = (config.seed, ("make_jobs", index))
        return result

    _patch_aliases(patch, original_seed, seed)
    _patch_aliases(patch, original_jobs, jobs)
    return parents, calls


def _rate_ancestor(seed, parents):
    seen = set()
    while seed != SEED:
        assert seed not in seen, "cycle in seed lineage"
        seen.add(seed)
        assert seed in parents, f"seed {seed} has no recorded namespace-91 ancestor"
        base, key = parents[seed]
        if base == SEED:
            assert len(key) >= 4 and key[0] == 91 and key[2] == 2, key
            assert key[1] in range(4), key
            return key[1]
        seed = base
    pytest.fail("the main seed was reused directly")


def _calibration_count(jobs, plan):
    labels = {job.directory: job.condition.offensive_group_size > 0 for job in jobs}
    ids = sorted(labels)
    split = splits.split_by_run(ids, [labels[run] for run in ids], 0.3, plan.split_seed)
    _, calibration = splits.calibration_split(
        split.train, [labels[run] for run in split.train], splits.CALIBRATION_FRACTION,
        harness.child_seed(plan.evaluation_seed, harness.SEED_KEY + 1, 0),
    )
    return sum(not labels[run] for run in calibration)


def test_enlarged_grid_and_fresh_seeds_are_disjoint_from_first_sweep_and_main(sweep, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("preflight planning attempted simulation or feature extraction")

    _patch_aliases(monkeypatch, pipeline._simulate, forbidden)
    _patch_aliases(monkeypatch, eval_data.build_tier_data, forbidden)
    main = reproduce_config.ReproduceConfig()
    old_seeds = {job.seed for job in reproduce_config.make_jobs(main)}
    for rate_index in range(4):
        first = replace(main, seed=harness.child_seed(SEED, 91, rate_index, 0),
                        runs_per_condition=1, control_repeats=8, hold_out=())
        old_seeds.update(job.seed for job in reproduce_config.make_jobs(first))
    parents, seed_calls = _seed_audit(monkeypatch)
    plans = sweep.plan_sharing_sweep(sweep.SharingSweepConfig(seed=SEED, workers=1))
    assert [(plan.rate_index, plan.rate) for plan in plans] == list(enumerate(RATES))
    all_seeds = []
    for plan in plans:
        assert isinstance(plan.config, reproduce_config.ReproduceConfig)
        assert plan.config.runs_per_condition == 3
        assert plan.config.n_ticks == main.n_ticks == 160
        cells = Counter((job.condition.coordinated_groups, job.condition.channel,
                         job.condition.topology, job.condition.offensive_group_size)
                        for job in plan.jobs)
        assert set(cells) == set(product((1, 2, 3), ("message", "shared_file", "preplanned"),
                                         ("hub", "peer"), (0, 2, 3, 5)))
        assert {count for cell, count in cells.items() if cell[-1]} == {3}
        controls = [job for job in plan.jobs if job.condition.offensive_group_size == 0]
        positives = [job for job in plan.jobs if job.condition.offensive_group_size > 0]
        assert {count for cell, count in cells.items() if cell[-1] == 0} == {90}
        assert len(controls) == 1620 and len(positives) == 162
        assert len(plan.jobs) == 1782
        assert plan.calibration_controls == _calibration_count(plan.jobs, plan) == 340
        for job in plan.jobs:
            assert isinstance(job, reproduce_config.RunJob) and job.dataset == "main"
            assert job.condition.benign_credential_sharing == plan.rate
            assert _rate_ancestor(job.seed, parents) == plan.rate_index
            all_seeds.append(job.seed)
        assert _rate_ancestor(plan.split_seed, parents) == plan.rate_index
        assert _rate_ancestor(plan.evaluation_seed, parents) == plan.rate_index
        assert plan.split_seed != plan.evaluation_seed
    assert len(all_seeds) == len(set(all_seeds))
    assert set(all_seeds).isdisjoint(old_seeds)
    assert seed_calls and all(len(key) >= 2 for _, key, _ in seed_calls)


def test_control_count_is_independent_of_positive_replicates(sweep):
    config = replace(_tiny_config(sweep), runs_per_condition=3, control_repeats=89)
    plans = sweep.plan_sharing_sweep(config)
    for plan in plans:
        assert sum(job.condition.offensive_group_size == 0 for job in plan.jobs) == 89
        assert sum(job.condition.offensive_group_size > 0 for job in plan.jobs) == 9
        assert plan.calibration_controls == _calibration_count(plan.jobs, plan) == 19


@pytest.mark.parametrize("workers", (1, 2))
def test_preflight_refuses_18_controls_before_simulation(sweep, tmp_path, monkeypatch, workers):
    def forbidden(*args, **kwargs):
        pytest.fail("invalid calibration inventory reached execution")

    for function in (pipeline._simulate, runner.run_one, eval_data.build_tier_data,
                     harness.evaluate_split):
        _patch_aliases(monkeypatch, function, forbidden)
    minimum = _minimum_control_repeats()
    assert [_tiny_calibration_controls(minimum - 1, index) for index in range(4)] == [18] * 4
    assert [_tiny_calibration_controls(minimum, index) for index in range(4)] == [19] * 4
    config = _tiny_config(sweep, workers=workers, control_repeats=minimum - 1)
    out = tmp_path / "refused"
    message = r"(?i)(19.*calibration controls|calibration controls.*19)"
    with pytest.raises(ValueError, match=message):
        sweep.run_sharing_sweep(out, config)
    assert not out.exists() or not _snapshot(out)
    accepted = sweep.plan_sharing_sweep(replace(config, control_repeats=minimum))
    assert [plan.calibration_controls for plan in accepted] == [19] * 4


def _install_socket_guard(root, patch):
    guard, markers = root / "socket-guard", root / "worker-markers"
    guard.mkdir()
    markers.mkdir()
    existing = importlib.util.find_spec("sitecustomize")
    startup = ""
    if existing is not None and existing.origin is not None:
        startup = f"import runpy\nrunpy.run_path({existing.origin!r}, run_name='sitecustomize')\n"
    (guard / "sitecustomize.py").write_text(startup + dedent("""\
        import atexit
        import multiprocessing
        import os
        import socket
        from pathlib import Path

        class ForbiddenSocket(socket.socket):
            def __new__(cls, *args, **kwargs):
                raise AssertionError("sharing sweep must not open sockets")

        socket.socket = ForbiddenSocket

        def mark_worker():
            name = multiprocessing.current_process().name
            if name == "MainProcess":
                return
            try:
                socket.socket()
            except AssertionError:
                marker = Path(os.environ["SWARMTRACE_SHARING_SOCKET_MARKERS"])
                (marker / f"{os.getpid()}.txt").write_text(name, encoding="utf-8")
            else:
                raise AssertionError("worker socket guard was lost")

        atexit.register(mark_worker)
        """), encoding="utf-8")
    patch.setenv("SWARMTRACE_SHARING_SOCKET_MARKERS", str(markers))
    previous = os.environ.get("PYTHONPATH")
    patch.setenv("PYTHONPATH", str(guard) + (os.pathsep + previous if previous else ""))
    for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        patch.setenv(name, "1")

    class ForbiddenSocket(socket.socket):
        def __new__(cls, *args, **kwargs):
            raise AssertionError("sharing sweep must not open sockets")

    patch.setattr(socket, "socket", ForbiddenSocket)
    return markers


def _execution_audit(patch):
    audit = {"runs": [], "evaluations": {}, "detectors": [], "seeds": defaultdict(list),
             "extractions": [], "dispatches": [], "samples": {}}
    audit["parents"], audit["seed_calls"] = _seed_audit(patch)
    original_run, original_evaluate = runner.run_one, harness.evaluate_split
    original_build, original_simulate = eval_data.build_tier_data, pipeline._simulate

    def run(condition, seed, out, *args, **kwargs):
        result = original_run(condition, seed, out, *args, **kwargs)
        trace = read_trace(Path(result) / "trace.jsonl", Tier.V1)
        credentials = defaultdict(set)
        for event in trace.events:
            if event.tool == "login" and event.result["status"] == "ok":
                credentials[event.args["credential"]].add(event.agent)
        audit["runs"].append((condition, seed, trace.run_id, credentials))
        key = (condition.benign_credential_sharing, condition.offensive_group_size > 0)
        if key not in audit["samples"]:
            job = next(job for job in audit["dispatches"] if job.seed == seed)
            audit["samples"][key] = (job, _snapshot(Path(result)))
        return result

    def evaluate(data, split, config, seed, *, family="all"):
        rates = {record.condition["benign_credential_sharing"] for record in data.records.values()}
        assert len(rates) == 1
        rate = rates.pop()
        assert rate not in audit["evaluations"], "duplicate evaluator for a rate"
        result = original_evaluate(data, split, config, seed, family=family)
        audit["evaluations"][rate] = (data, split, config, seed, family, result)
        return result

    def build(records, tier, **kwargs):
        audit["extractions"].append(tier)
        return original_build(records, tier, **kwargs)

    def simulate(task):
        audit["dispatches"].append(task[0])
        return original_simulate(task)

    for original, wrapper in ((original_run, run), (original_evaluate, evaluate),
                              (original_build, build), (original_simulate, simulate)):
        _patch_aliases(patch, original, wrapper)

    def watch_seed(function, kind, position):
        def watched(*args, **kwargs):
            seed = kwargs.get("seed", args[position] if len(args) > position else None)
            audit["seeds"][kind].append(seed)
            return function(*args, **kwargs)
        _patch_aliases(patch, function, watched)

    watch_seed(splits.split_by_run, "split", 3)
    watch_seed(splits.calibration_split, "calibration", 3)
    watch_seed(metrics.bootstrap, "bootstrap", 3)

    def watch_detector(cls, method):
        original = getattr(cls, method)

        def guarded(self, frame, *args, **kwargs):
            assert isinstance(frame, pd.DataFrame)
            assert not any(str(column).startswith(("label_", "condition_"))
                           for column in frame.columns)
            audit["detectors"].append((cls.__name__, method, getattr(self, "model", "pairs")))
            if method == "fit":
                audit["seeds"]["fit"].append(self.seed)
            return original(self, frame, *args, **kwargs)

        patch.setattr(cls, method, guarded)

    for cls in (RunDetector, OnlineDetector):
        for method in ("fit", "calibrate", "score"):
            watch_detector(cls, method)
    for method in ("fit", "score"):
        watch_detector(PairScorer, method)
    return audit


@pytest.fixture(scope="module")
def completed(sweep, tmp_path_factory):
    root = tmp_path_factory.mktemp("sharing-sweep")
    out = root / "sweep"
    config = _tiny_config(sweep)
    control_runs = config.control_repeats
    with pytest.MonkeyPatch.context() as guard:
        markers = _install_socket_guard(root, guard)
        with pytest.raises(AssertionError, match="sharing sweep must not open sockets"):
            socket.socket()
        with pytest.MonkeyPatch.context() as spies:
            audit = _execution_audit(spies)
            report = sweep.run_sharing_sweep(out, config)
        assert report == out / "sharing-sweep.md"
        # Two workers regenerate only eight sampled runs, not another four fits.
        worker_root = root / "workers"
        jobs = [job for job, _ in audit["samples"].values()]
        with ProcessPoolExecutor(max_workers=2,
                                 mp_context=multiprocessing.get_context("spawn")) as pool:
            list(pool.map(pipeline._simulate, [(job, worker_root) for job in jobs]))
        for job, expected in audit["samples"].values():
            assert _snapshot(worker_root / job.dataset / job.directory) == expected
        records = eval_data.load_runs(worker_root / "main")
        for workers in (1, 2):
            data = eval_data.build_tier_data(records, Tier.V1, workers=workers,
                                              checkpoint_every=TINY_TICKS, retain_traces=False)
            write_recorded(root / f"recorded-{workers}", data)
        assert _snapshot(root / "recorded-1") == _snapshot(root / "recorded-2")
    # Keep later score/interval assertions under the same native-thread limit as
    # the sweep, avoiding OpenMP startup overhead for these tiny prediction batches.
    with _get_threadpool_controller().limit(limits=1):
        yield {"out": out, "root": root, "config": config, "audit": audit, "markers": markers,
               "report": report.read_text(encoding="utf-8"), "snapshot": _snapshot(out),
               "control_runs": control_runs, "total_runs": control_runs + TINY_POSITIVE_RUNS}


def test_rates_reach_real_simulator_and_zero_rate_has_no_shared_control_login(completed):
    audit = completed["audit"]
    assert Counter(condition.benign_credential_sharing for condition, *_ in audit["runs"]) == {
        rate: completed["total_runs"] for rate in RATES
    }
    assert all(condition.n_ticks == TINY_TICKS for condition, *_ in audit["runs"])
    assert len(audit["dispatches"]) == len(audit["runs"])
    assert audit["extractions"] == [Tier.V1] * 4
    controls = [credentials for condition, _, _, credentials in audit["runs"]
                if condition.benign_credential_sharing == 0
                and condition.offensive_group_size == 0]
    assert len(controls) == completed["control_runs"] and all(controls)
    assert all(len(agents) == 1 for credentials in controls for agents in credentials.values())
    assert {rate for rate in audit["evaluations"]} == set(RATES)
    for data, split, _, _, family, result in audit["evaluations"].values():
        assert data.tier == Tier.V1 and family == "aggregation" and split.name == "by run"
        assert set(result.fitting).isdisjoint(result.calibration)
        assert set(result.fitting + result.calibration) == set(split.train)
        assert set(split.train).isdisjoint(split.test)


def test_distinct_namespace_91_seeds_cover_runs_split_fit_calibration_and_bootstrap(completed):
    audit = completed["audit"]
    calls, parents = audit["seed_calls"], audit["parents"]
    assert calls and all(len(key) >= 2 for _, key, _ in calls)
    for _, _, seed in calls:
        _rate_ancestor(seed, parents)
    run_seeds = {rate: set() for rate in RATES}
    for condition, seed, _, _ in audit["runs"]:
        assert _rate_ancestor(seed, parents) == RATES.index(condition.benign_credential_sharing)
        run_seeds[condition.benign_credential_sharing].add(seed)
    assert all(len(seeds) == completed["total_runs"] for seeds in run_seeds.values())
    assert len(set.union(*run_seeds.values())) == len(RATES) * completed["total_runs"]
    for rate_index, rate in enumerate(RATES):
        streams = {"runs": run_seeds[rate]}
        for kind in ("split", "calibration", "fit", "bootstrap"):
            streams[kind] = {seed for seed in audit["seeds"][kind]
                             if _rate_ancestor(seed, parents) == rate_index}
            assert streams[kind], f"no observed {kind} seeds for rate {rate}"
        for first, left in streams.items():
            for second, right in streams.items():
                if first != second:
                    assert left.isdisjoint(right), (rate, first, second)


def test_detector_boundaries_are_observed_without_label_or_condition_columns(completed):
    observed = set(completed["audit"]["detectors"])
    for detector in METHODS:
        for method in ("fit", "calibrate", "score"):
            assert ("RunDetector", method, detector) in observed


def test_report_cells_match_existing_evaluator_and_test_control_populations(completed):
    assert HISTORY in completed["report"]
    assert "child_seed(seed, 91, rate_index, 2," in completed["report"]
    assert "conformal quantile of the calibration-control scores" in completed["report"]
    assert "more than about 5 percent" in completed["report"]
    assert "threshold falls inside the sharing-score range" in completed["report"]
    rows = _rows(completed["report"])
    assert Counter((int(row["rate"]), row["detector"]) for row in rows) == Counter(
        product(RATES, METHODS)
    )
    for row in rows:
        rate, method = int(row["rate"]), row["detector"]
        data, split, config, _, _, result = completed["audit"]["evaluations"][rate]
        assert f"Seed: {SEED}" in completed["report"]
        assert "V1, aggregation features, by-run split" in completed["report"]
        assert row["runs"] == (f'{completed["total_runs"]} ({TINY_POSITIVE_RUNS} positive, '
                               f'{completed["control_runs"]} control)')
        measured = {metric.metric: metric for metric in result.rows if metric.method == method}
        counts = measured["auroc"].split_counts
        for index, name in enumerate(("fitting", "calibration", "test")):
            assert row[f"{name} (positive, control)"] == (
                f"{counts[2 * index + 1]} positive, {counts[2 * index]} control"
            )
        assert int(row["calibration controls"]) == counts[2] == 19
        controls = [run for run in split.test if not data.records[run].positive]
        sharing = [run for run in controls
                   if data.records[run].condition["benign_sharing_teams"] > 0]
        _assert_rate(row["sharing test controls (q)"], len(sharing), len(controls))
        expected = 1 - len(sharing) / len(controls) / 2
        assert float(row["expected 1 - q/2"]) == pytest.approx(expected, abs=0.00051)
        auroc = measured["auroc"]
        assert _estimate(row["overall AUROC"]) == pytest.approx(
            (auroc.value, auroc.low, auroc.high), abs=0.00051,
        )
        for column, metric in (("detection rate", "detection_rate"),
                               ("FPR", "false_positive_rate")):
            _assert_rate(row[column], measured[metric].n, measured[metric].total)
        assert re.fullmatch(r"\d+\.\d{6}|inf", row["threshold"])
        assert float(row["threshold"]) == pytest.approx(result.thresholds[method], abs=0.00000051)
        if rate == 0:
            assert not sharing
        if len(sharing) < 2:
            note = ("undefined: no sharing controls" if rate == 0 else
                    f"undefined: {len(sharing)} sharing control{'s' if len(sharing) != 1 else ''}")
            for column in ("A_s", "interval contains 1 - q/2", "interval contains 1 - q"):
                assert row[column] == note
        else:
            restricted = measured["sharing_control_auroc"]
            assert _estimate(row["A_s"]) == pytest.approx(
                (restricted.value, restricted.low, restricted.high), abs=0.00051,
            )
            for column, target in (("interval contains 1 - q/2", expected),
                                   ("interval contains 1 - q", 1 - len(sharing) / len(controls))):
                assert row[column] == ("yes" if auroc.low <= target <= auroc.high else "no")
        # Independently select the complement, using the already-fitted detector.
        selected = [run for run in split.test if run not in sharing]
        features = harness.family_data(data, "aggregation").runs.loc[selected]
        scores = result.fitted[method].score(features)
        labels = np.array([data.records[run].positive for run in selected], dtype=bool)
        complement = metrics.bootstrap(
            lambda idx: metrics.auroc(labels[idx], scores[idx]),
            [np.flatnonzero(labels), np.flatnonzero(~labels)], 2,
            harness.child_seed(SEED, 91, RATES.index(rate), 2, 3, harness.SEED_INDEX[method], 0),
        )
        assert _estimate(row["AUROC vs non-sharing controls"]) == pytest.approx(
            (complement.value, complement.low, complement.high), abs=0.00051,
        )
        assert config.n_bootstrap == 2 and config.max_fpr == 0.05
    # The short horizon deliberately leaves non-supporting measurements in place.
    assert any(row["interval contains 1 - q/2"] == "no" for row in rows)


def test_report_team_subgroups_use_same_fitted_scores_and_run_bootstrap(completed):
    section = completed["report"].split("## A_s by sharing-team count\n", 1)[1].split("\n## ", 1)[0]
    lines = [line for line in section.splitlines() if line.startswith("|")]
    header = tuple(cell.strip() for cell in lines[0].strip("|").split("|"))
    assert header == ("rate", "detector", "sharing teams", "sharing controls k of n", "A_s")
    rows = [dict(zip(header, (cell.strip() for cell in line.strip("|").split("|")), strict=True))
            for line in lines[2:]]
    assert Counter((int(row["rate"]), row["detector"], row["sharing teams"]) for row in rows) == (
        Counter(product(RATES, METHODS, ("one team", "two or more")))
    )
    for row in rows:
        rate, method = int(row["rate"]), row["detector"]
        data, split, _, _, _, result = completed["audit"]["evaluations"][rate]
        labels = np.array([data.records[run].positive for run in split.test], dtype=bool)
        teams = np.array([data.records[run].condition["benign_sharing_teams"] for run in split.test])
        one = row["sharing teams"] == "one team"
        subset = (~labels) & ((teams == 1) if one else (teams >= 2))
        k, n = int(subset.sum()), int(((~labels) & (teams > 0)).sum())
        assert row["sharing controls k of n"] == f"{k} of {n}"
        if k < 2:
            assert row["A_s"] == ("undefined: no sharing controls" if rate == 0 else
                                  f"undefined: {k} sharing control{'s' if k != 1 else ''}")
            continue
        scores = result.fitted[method].score(
            harness.family_data(data, "aggregation").runs.loc[list(split.test)],
        )
        estimate = metrics.bootstrap(
            lambda idx: metrics.auroc(labels[idx], scores[idx]),
            [np.flatnonzero(labels), np.flatnonzero(subset)], 2,
            harness.child_seed(SEED, 91, RATES.index(rate), 2, 3,
                               harness.SEED_INDEX[method], 1 if one else 2),
        )
        assert _estimate(row["A_s"]) == pytest.approx(
            (estimate.value, estimate.low, estimate.high), abs=0.00051,
        )


def test_only_v1_run_tables_are_published_with_metadata_and_sha256(completed):
    expected = {"sharing-sweep.md", *(f"sharing-sweep/rate-{rate}/runs.csv.gz" for rate in RATES)}
    assert set(completed["snapshot"]) == expected
    root = completed["out"]
    for rate in RATES:
        relative = f"sharing-sweep/rate-{rate}/runs.csv.gz"
        content = completed["snapshot"][relative]
        digest = hashlib.sha256(content).hexdigest()
        assert any(relative in line and digest in line for line in completed["report"].splitlines())
        frame = pd.read_csv(root / relative, dtype={"run_id": str})
        assert frame["run_id"].is_unique and len(frame) == completed["total_runs"]
        assert frame["label_positive"].sum() == TINY_POSITIVE_RUNS
        assert set(frame["condition_benign_credential_sharing"]) == {rate}
        assert "condition_benign_sharing_teams" in frame
        features = [column for column in frame if column != "run_id"
                    and not column.startswith(("label_", "condition_"))]
        assert tuple(features) == feature_columns("run", Tier.V1)
        data = completed["audit"]["evaluations"][rate][0]
        pd.testing.assert_frame_equal(frame.set_index("run_id")[features], data.runs,
                                      check_dtype=False, check_exact=False, rtol=1e-12, atol=1e-12)
        assert frame["label_positive"].tolist() == [
            data.records[run].positive for run in frame["run_id"]
        ]
        assert frame["condition_benign_sharing_teams"].tolist() == [
            data.records[run].condition["benign_sharing_teams"] for run in frame["run_id"]
        ]
        if rate == 0:
            controls = frame.loc[~frame["label_positive"].astype(bool)]
            assert controls[RULE_COLUMN].eq(0).all()
            assert controls["condition_benign_sharing_teams"].eq(0).all()
    assert b"\r\n" not in completed["snapshot"]["sharing-sweep.md"]
    lines = completed["report"].splitlines()
    assert lines[-7] == HASH_START and lines[-6] == "path | sha256" and lines[-1] == "```"
    assert [line.split(" | ")[0] for line in lines[-5:-1]] == [
        f"sharing-sweep/rate-{rate}/runs.csv.gz" for rate in RATES
    ]


def test_report_bytes_match_across_workers_on_rerender_without_refitting(
    sweep, completed, monkeypatch,
):
    def forbidden(*args, **kwargs):
        pytest.fail("report rendering attempted simulation, extraction, or refitting")

    for function in (pipeline._simulate, eval_data.build_tier_data, harness.evaluate_split):
        _patch_aliases(monkeypatch, function, forbidden)
    monkeypatch.setattr(RunDetector, "fit", forbidden)
    rows, subgroups, hashes = [], [], []
    config = replace(completed["config"], workers=2)
    plans = sweep.plan_sharing_sweep(config)
    serial = sweep.plan_sharing_sweep(completed["config"])
    assert [(plan.jobs, plan.split_seed, plan.evaluation_seed, plan.calibration_controls)
            for plan in plans] == [
        (plan.jobs, plan.split_seed, plan.evaluation_seed, plan.calibration_controls)
        for plan in serial
    ]
    for plan in plans:
        data, split, _, _, _, result = completed["audit"]["evaluations"][plan.rate]
        measured, grouped = sweep._result_rows(data, split, result, config, plan)
        rows.extend(measured)
        subgroups.extend(grouped)
        relative = f"sharing-sweep/rate-{plan.rate}/runs.csv.gz"
        hashes.append({"path": relative,
                       "sha256": hashlib.sha256(completed["snapshot"][relative]).hexdigest()})
    report = completed["root"] / "rerendered.md"
    sweep._write_report(report, config, plans, rows, subgroups, hashes)
    assert report.read_bytes() == completed["snapshot"]["sharing-sweep.md"]


def test_real_tiny_sweep_completes_with_socket_creation_forbidden_in_workers(completed):
    markers = {int(path.stem): path.read_text(encoding="utf-8")
               for path in completed["markers"].glob("*.txt")}
    assert any(pid != os.getpid() and "Process" in name for pid, name in markers.items()), (
        f"no guarded worker actually executed: {markers}"
    )


def test_cli_registers_sharing_sweep(capsys):
    with pytest.raises(SystemExit) as error:
        cli.main(["sharing-sweep", "--help"])
    assert error.value.code == 0
    help_text = capsys.readouterr().out
    assert "--seed" in help_text and "--out" in help_text


def test_cli_dispatches_seed_and_output(sweep, tmp_path, monkeypatch):
    seen = []

    def run(out, config):
        seen.append((out, config))
        return out / "sharing-sweep.md"

    _patch_aliases(monkeypatch, sweep.run_sharing_sweep, run)
    cli.main(["sharing-sweep", "--seed", "20261120", "--out", str(tmp_path)])
    assert len(seen) == 1 and seen[0][0] == tmp_path
    assert isinstance(seen[0][1], sweep.SharingSweepConfig) and seen[0][1].seed == SEED


def _main_manifest(root):
    (root / "main.bin").write_bytes(b"existing main artifact\n")
    manifest = {"artifacts_sha256": {"main.bin": hashlib.sha256(
        (root / "main.bin").read_bytes()).hexdigest()}}
    (root / "experiment.json").write_text(json.dumps(manifest), encoding="utf-8")


@pytest.fixture
def verified_sweep(tmp_path):
    _main_manifest(tmp_path)
    lines = ["# Sharing sweep", "", HASH_START, "path | sha256"]
    for rate in RATES:
        relative = f"sharing-sweep/rate-{rate}/runs.csv.gz"
        path = tmp_path / relative
        path.parent.mkdir(parents=True)
        path.write_bytes(f"archive {rate}\n".encode())
        lines.append(f"{relative} | {hashlib.sha256(path.read_bytes()).hexdigest()}")
    (tmp_path / "sharing-sweep.md").write_text("\n".join([*lines, "```", ""]), encoding="utf-8")
    return tmp_path


def test_verify_checks_generated_sweep_hashes(completed, tmp_path, capsys):
    _main_manifest(tmp_path)
    for relative, content in completed["snapshot"].items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    before = _snapshot(tmp_path)
    verify(tmp_path)
    captured = capsys.readouterr()
    assert "5 of 5 match" in captured.out
    assert "unlisted artifact: sharing-sweep" not in captured.err
    assert _snapshot(tmp_path) == before


def test_verify_checks_sweep_files_and_keeps_unrelated_warnings(verified_sweep, capsys):
    tmp_path = verified_sweep
    (tmp_path / "unrelated.bin").write_bytes(b"still warn")
    (tmp_path / "sharing-sweep" / "extra.bin").write_bytes(b"also warn")
    before = _snapshot(tmp_path)
    verify(tmp_path)
    captured = capsys.readouterr()
    assert "unlisted artifact: unrelated.bin" in captured.err
    assert "unlisted artifact: sharing-sweep/extra.bin" in captured.err
    assert "unlisted artifact: sharing-sweep.md" not in captured.err
    assert "unlisted artifact: sharing-sweep/rate-" not in captured.err
    assert _snapshot(tmp_path) == before
    readme = (Path(__file__).resolve().parents[1] / "README.md").read_text(encoding="utf-8")
    reproduction = readme.split("## Reproduce", 1)[1]
    assert "--out sharing-sweep-out" in reproduction and "Copy-Item" in reproduction
    assert "verify checks the sweep hashes" in reproduction


@pytest.mark.parametrize("mutation", ("tamper", "missing"))
def test_verify_rejects_corrupt_sweep_with_cli_exit_1(verified_sweep, mutation, capsys):
    relative = "sharing-sweep/rate-10/runs.csv.gz"
    path = verified_sweep / relative
    if mutation == "tamper":
        path.write_bytes(path.read_bytes() + b"changed")
    else:
        path.unlink()
    before = _snapshot(verified_sweep)
    with pytest.raises(SystemExit) as error:
        cli.main(["verify", "--data", str(verified_sweep)])
    assert error.value.code == 1
    message = capsys.readouterr().err
    assert relative in message
    assert ("hash mismatch" if mutation == "tamper" else "missing artifact") in message
    assert _snapshot(verified_sweep) == before


@pytest.mark.parametrize("empty_directory", (False, True))
def test_verify_accepts_absent_sweep(tmp_path, capsys, empty_directory):
    _main_manifest(tmp_path)
    if empty_directory:
        (tmp_path / "sharing-sweep" / "rate-0").mkdir(parents=True)
    verify(tmp_path)
    assert "1 of 1 match" in capsys.readouterr().out


@pytest.mark.parametrize("mutation", (
    "no-block", "duplicate-block", "duplicate-path", "traversal", "bad-digest",
    "missing-row", "extra-row", "no-end", "trailing-text", "missing-report",
))
def test_verify_rejects_malformed_or_missing_hash_block(verified_sweep, mutation):
    report = verified_sweep / "sharing-sweep.md"
    text = report.read_text(encoding="utf-8")
    if mutation == "missing-report":
        report.unlink()
    else:
        lines = text.splitlines()
        start = lines.index(HASH_START)
        if mutation == "no-block":
            text = "no machine-readable hashes\n"
        elif mutation == "duplicate-block":
            text += "\n".join(lines[start:]) + "\n"
        elif mutation == "duplicate-path":
            text = text.replace("rate-5/", "rate-0/")
        elif mutation == "traversal":
            text = text.replace("sharing-sweep/rate-0/", "../rate-0/")
        elif mutation == "bad-digest":
            text = text.replace(lines[start + 2].split(" | ")[1], "x" * 64)
        elif mutation == "missing-row":
            text = text.replace(lines[start + 2] + "\n", "")
        elif mutation == "extra-row":
            text = text.replace("\n```\n", f"\n{lines[start + 2]}\n```\n")
        elif mutation == "no-end":
            text = text.removesuffix("```\n")
        else:
            text += "not the final block\n"
        report.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match="sharing-sweep.md"):
        verify(verified_sweep)


def test_existing_output_is_refused_before_execution(sweep, tmp_path, monkeypatch):
    _main_manifest(tmp_path)
    before = _snapshot(tmp_path)

    def forbidden(*args, **kwargs):
        pytest.fail("nonempty output reached simulation")

    _patch_aliases(monkeypatch, pipeline._simulate, forbidden)
    with pytest.raises(ValueError, match="fresh"):
        sweep.run_sharing_sweep(tmp_path, _tiny_config(sweep))
    assert _snapshot(tmp_path) == before


@pytest.mark.parametrize(("rate", "count", "note"), (
    (0, 0, "undefined: no sharing controls"),
    (5, 0, "undefined: 0 sharing controls"),
    (5, 1, "undefined: 1 sharing control"),
))
def test_sparse_sharing_controls_withhold_as_and_both_contains(
    sweep, completed, rate, count, note,
):
    data, split, _, _, _, result = completed["audit"]["evaluations"][rate]
    controls = [run for run in split.test if not data.records[run].positive]
    records = {run: replace(record, condition={**record.condition,
                                               "benign_sharing_teams": int(run in controls[:count])})
               for run, record in data.records.items()}
    plan = sweep.plan_sharing_sweep(completed["config"])[RATES.index(rate)]
    rows, _ = sweep._result_rows(replace(data, records=records), split, result,
                                  completed["config"], plan)
    for row in rows:
        for column in ("A_s", "interval contains 1 - q/2", "interval contains 1 - q"):
            assert row[column] == note


def test_subset_auroc_identity_and_sharing_team_strata(sweep):
    labels = np.array([True, True, False, False, False, False, False, False])
    scores = np.array([2, 2, 2, 1, 3, 2, 0, 0], dtype=float)
    teams = np.array([0, 0, 1, 1, 2, 3, 0, 0])
    overall = metrics.auroc(labels, scores)
    template = harness.MetricRow("V1", "by run", "in-distribution", "rule", "auroc",
                                 overall, 0.5, 1.0, 8, 8, 2, 2, "")
    measured = {}
    for key, mask in {"sharing": (~labels) & (teams > 0),
                      "one": (~labels) & (teams == 1),
                      "many": (~labels) & (teams >= 2),
                      "nonsharing": (~labels) & (teams == 0)}.items():
        measured[key] = sweep._restricted_auroc(template, labels, scores, mask, 2,
                                                harness.child_seed(SEED, 91, 0, 2, 3, len(key)))
        assert measured[key].control_runs == int(mask.sum())
        assert measured[key].positive_runs == 2 and measured[key].valid == 2
    assert measured["one"].value == 0.75
    assert measured["many"].value == 0.25
    assert measured["sharing"].value == 0.5 and measured["nonsharing"].value == 1
    q = 4 / 6
    assert overall == pytest.approx(1 - q * (1 - measured["sharing"].value))


@pytest.mark.parametrize(("value", "expected"), (
    (0.0, "0.000000"), (1 / 3, "0.333333"), (2.0, "2.000000"), (float("inf"), "inf"),
))
def test_threshold_has_one_fixed_format(sweep, value, expected):
    assert sweep._threshold(value) == expected


MATCHED_HEADING = "## Matched on the number of sharing-like teams"
MATCHED_NOTE = (
    "The one-team and two-or-more rows above compare runs with different numbers of "
    "sharing-like teams; this table matches them."
)
MATCHED_COLUMNS = (
    "rate", "detector", "sharing-like teams K", "relay test runs (positives) k",
    "sharing test controls k", "AUROC (matched)", "population",
)


def _remove_matched_section(content):
    start = content.index(MATCHED_HEADING.encode())
    end = content.index(b"## Recorded V1 run tables", start)
    return content[:start] + content[end:]


@pytest.fixture(scope="module")
def rendered_tables(sweep, tmp_path_factory):
    from time import perf_counter

    source = Path(__file__).resolve().parents[1] / "data"
    target = tmp_path_factory.mktemp("sharing-render")
    original_report = (source / "sharing-sweep.md").read_bytes()
    (target / "sharing-sweep.md").write_bytes(original_report)
    tables = {}
    for rate in RATES:
        name = f"sharing-sweep/rate-{rate}/runs.csv.gz"
        content = (source / name).read_bytes()
        path = target / name
        path.parent.mkdir(parents=True)
        path.write_bytes(content)
        tables[name] = content
    _main_manifest(target)

    def forbidden(*args, **kwargs):
        pytest.fail("render-only path attempted simulation, trace loading, or feature extraction")

    with pytest.MonkeyPatch.context() as patch:
        for function in (runner.run_one, pipeline._simulate, eval_data.build_tier_data,
                         eval_data.load_runs, read_trace):
            _patch_aliases(patch, function, forbidden)
        parents, seed_calls = _seed_audit(patch)
        # Missing pair/prefix data must not be replaced with invented measurements.
        patch.setattr(PairScorer, "fit", forbidden)
        patch.setattr(OnlineDetector, "fit", forbidden)
        start = perf_counter()
        report = sweep.render_sharing_sweep_from_tables(
            target, sweep.SharingSweepConfig(seed=SEED, workers=1),
        )
        elapsed = perf_counter() - start
    assert report == target / "sharing-sweep.md"
    assert {name: (target / name).read_bytes() for name in tables} == tables
    return {"source": source, "out": target, "report": report.read_bytes(), "tables": tables,
            "parents": parents, "seed_calls": seed_calls, "elapsed": elapsed}


def test_table_only_render_preserves_every_preexisting_report_byte(rendered_tables):
    original = _remove_matched_section(rendered_tables["report"])
    assert hashlib.sha256(original).hexdigest() == (
        "8ad47d31272a409b71c1b478e2c4faff04c6eec2d019f90c182a021d04a8ba2c"
    )
    committed = (rendered_tables["source"] / "sharing-sweep.md").read_bytes()
    assert committed == rendered_tables["report"]


def test_table_only_render_has_matched_rows_and_verifiable_unchanged_hashes(
    rendered_tables, capsys,
):
    report = rendered_tables["report"].decode("utf-8")
    section = report.split(MATCHED_HEADING + "\n", 1)[1].split("## Recorded V1 run tables", 1)[0]
    lines = [line for line in section.splitlines() if line.startswith("|")]
    assert tuple(cell.strip() for cell in lines[0].strip("|").split("|")) == MATCHED_COLUMNS
    rows = [dict(zip(MATCHED_COLUMNS, (cell.strip() for cell in line.strip("|").split("|")),
                     strict=True)) for line in lines[2:]]
    assert len(rows) == 36 and {int(row["rate"]) for row in rows} == {5, 10, 30}
    pooled = [row for row in rows if row["population"].startswith("pooled")]
    assert len(pooled) == 9 and {row["detector"] for row in pooled} == {"rule"}
    assert MATCHED_NOTE in section.splitlines()
    for operation in (4, 5):
        assert (f"child_seed(config.seed, NAMESPACE, rate_index, REVISION, {operation}, "
                "detector_index, k_index)") in section
    before = _snapshot(rendered_tables["out"])
    verify(rendered_tables["out"])
    assert "5 of 5 match" in capsys.readouterr().out
    assert _snapshot(rendered_tables["out"]) == before


def test_committed_table_render_runtime_budget(rendered_tables):
    assert rendered_tables["elapsed"] < 60, (
        f"Rendering all four committed tables required {rendered_tables['elapsed']:.2f} seconds"
    )


def test_matched_buckets_counts_and_rule_only_pooling(sweep, tmp_path):
    from types import SimpleNamespace

    from swarmtrace.eval.recorded import TableRecord, write_run_table

    # Positive K adds one for the relay; high-scoring non-sharing controls are excluded.
    values = [
        (True, 0, 2), (True, 0, 4), (False, 1, 1), (False, 1, 3),
        (True, 1, 5), (False, 2, 2), (False, 2, 4),
        (True, 2, 4), (True, 3, 8), (False, 3, 1), (False, 4, 7),
        (False, 0, 999),
        (True, 1, 6), (False, 2, 3),  # Fitting-only rows, available only to the pooled rule.
    ]
    ids = [f"run-{index:02d}" for index in range(len(values))]
    records = [TableRecord(run, positive, {"benign_sharing_teams": teams})
               for run, (positive, teams, _) in zip(ids, values, strict=True)]
    frame = pd.DataFrame(0.0, index=pd.Index(ids, name="run_id"),
                         columns=feature_columns("run", Tier.V1))
    frame[RULE_COLUMN] = np.array([score for _, _, score in values], dtype="int64")
    path = tmp_path / "runs.csv.gz"
    write_run_table(path, frame, records)
    data = sweep._table_data(path, 160)
    split = splits.Split("by run", "in-distribution", tuple(ids[-2:]), tuple(ids[:-2]))
    seen = defaultdict(list)

    class Scorer:
        def __init__(self, method):
            self.method = method

        def score(self, matrix):
            seen[self.method].append(tuple(matrix.index))
            assert not any(column.startswith(("label_", "condition_")) for column in matrix)
            return matrix[RULE_COLUMN].to_numpy(dtype=float)

    metrics_rows = tuple(harness.MetricRow("V1", "by run", "in-distribution", method, "auroc",
                                          0.5, 0.0, 1.0, 12, 12, 2, 2, "") for method in METHODS)
    result = harness.SplitResult(metrics_rows, {}, {method: Scorer(method) for method in METHODS},
                                  tuple(ids[-2:]), ())
    config = sweep.SharingSweepConfig(workers=1, n_bootstrap=2)
    assert sweep._matched_rows(data, split, result, config,
                               SimpleNamespace(rate=0, rate_index=0)) == []
    assert not seen
    rows = sweep._matched_rows(data, split, result, config, SimpleNamespace(rate=5, rate_index=1))
    assert len(rows) == 12
    for method in METHODS:
        test = {row["sharing-like teams K"]: row for row in rows
                if row["detector"] == method and row["population"] == "test split"}
        for key in (1, "3-or-more"):
            assert test[key]["relay test runs (positives) k"] == 2
            assert test[key]["sharing test controls k"] == 2
            assert _estimate(test[key]["AUROC (matched)"])[0] == 0.75
        assert test[2]["relay test runs (positives) k"] == 1
        assert test[2]["sharing test controls k"] == 2
        assert test[2]["AUROC (matched)"] == "undefined: 1 relay run"
        assert seen[method] == ([split.test, tuple(ids)] if method == "rule" else [split.test])
    pooled = [row for row in rows if row["population"].startswith("pooled")]
    assert {row["detector"] for row in pooled} == {"rule"}
    assert {row["population"] for row in pooled} == {
        "pooled over all runs of the rate (fitting, calibration and test); rule only, "
        "legitimate only because the rule has no fitted parameters"
    }
    pooled_two = next(row for row in pooled if row["sharing-like teams K"] == 2)
    assert pooled_two["relay test runs (positives) k"] == 2
    assert pooled_two["sharing test controls k"] == 3
    assert _estimate(pooled_two["AUROC (matched)"])[0] == 1.0
    no_sharing = {run: replace(record, condition={"benign_sharing_teams": 0})
                  for run, record in data.records.items()}
    sparse = sweep._matched_rows(replace(data, records=no_sharing), split, result, config,
                                 SimpleNamespace(rate=10, rate_index=2))
    assert sparse[0]["AUROC (matched)"] == "undefined: 0 sharing controls"
    assert "0 relay runs" in sparse[1]["AUROC (matched)"]


def test_matched_seed_namespaces_do_not_collide_with_existing_sweep_seeds(rendered_tables):
    calls = rendered_tables["seed_calls"]
    matched = [(base, key, value) for base, key, value in calls
               if base == SEED and len(key) == 6 and key[:1] == (91,) and key[3] in (4, 5)]
    expected = {(91, rate_index, 2, operation, harness.SEED_INDEX[method], bucket)
                for rate_index in (1, 2, 3) for operation in (4, 5)
                for method in (METHODS if operation == 4 else ("rule",)) for bucket in range(3)}
    assert {key for _, key, _ in matched} == expected
    assert len(matched) == len(expected)
    reserved = {value for base, key, value in calls if (base, key) not in
                {(base, key) for base, key, _ in matched}}
    reserved.update(value for value, (_, key) in rendered_tables["parents"].items()
                    if key[:1] == ("make_jobs",))
    # Reserve both new operations for all rates/detectors/buckets, including unused rate 0.
    new = [harness.child_seed(SEED, 91, rate_index, 2, operation,
                               harness.SEED_INDEX[method], bucket)
           for rate_index in range(4) for operation in (4, 5)
           for method in METHODS for bucket in range(3)]
    assert len(new) == len(set(new)) and set(new).isdisjoint(reserved)
    for rate_index in range(4):
        evaluation = harness.child_seed(SEED, 91, rate_index, 2, 2)
        # Include the unchanged harness's fitting, online, attribution and bootstrap subkeys.
        legacy = {harness.child_seed(evaluation, index, key)
                  for index in range(6) for key in range(18)}
        legacy.update(harness.child_seed(evaluation, index, 11, size)
                      for index in range(6) for size in (2, 3, 5))
        assert set(new).isdisjoint(legacy)


def test_cli_dispatches_render_from_without_out(sweep, tmp_path, monkeypatch):
    seen = []

    def forbidden(*args, **kwargs):
        pytest.fail("render CLI dispatched simulation")

    _patch_aliases(monkeypatch, sweep.run_sharing_sweep, forbidden)
    _patch_aliases(monkeypatch, sweep.render_sharing_sweep_from_tables,
                   lambda data, config: seen.append((data, config)))
    cli.main(["sharing-sweep", "--render-from", str(tmp_path), "--seed", str(SEED)])
    assert len(seen) == 1 and seen[0][0] == tmp_path and seen[0][1].seed == SEED


def test_cli_rejects_ambiguous_sharing_output_modes(tmp_path):
    with pytest.raises(SystemExit) as error:
        cli.main(["sharing-sweep", "--out", str(tmp_path), "--render-from", str(tmp_path),
                  "--seed", str(SEED)])
    assert error.value.code == 2
