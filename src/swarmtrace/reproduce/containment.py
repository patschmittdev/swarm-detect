"""The containment experiment: paired runs with and without a controller.

Every pair is one condition and seed. Its uncontained twin is simulated first; each of the
other 17 arms is the same condition and seed with one controller attached, stored under its
own root. First-flag ticks come only from ``live_first_flag_tick``, replaying the twin's
V1 events through a fresh controller on its own live grid. An arm whose controller never
decides is not simulated: up to its first decision an arm's events equal the twin's, so a
replay of the twin through a fresh controller finds that first decision exactly, and with
none the arm's run files are the twin's. Detectors and thresholds are the frozen main models;
nothing is refitted for containment.

Seeds: pair i runs at ``child_seed(seed, 98, i)``; bootstraps use ``child_seed(seed, 99, 0,
...)``; the random arms of pair i draw from ``child_seed(seed, 99, 1, i)``.
"""

import argparse
import hashlib
import multiprocessing
import os
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from swarmtrace.contain import HaltAllController, RandomController
from swarmtrace.detect import CHECKPOINT_EVERY
from swarmtrace.eval.containment import (
    ARMS,
    COHORTS,
    COMPARISON_KEY,
    DETECTORS,
    LEVERS,
    RANDOM_KEY,
    ROLES,
    TWIN,
    ArmMeasure,
    HostMap,
    bootstrap_seed,
    bootstrap_seeds,
    cost_cells,
    decomposition_rows,
    detector_arm,
    first_checkpoint_precedes,
    flagged_control_cells,
    halt_arm,
    lender_cells,
    load_run_facts,
    measure_arm,
    oracle_arm,
    outcome_values,
    paired_cells,
    prevention_cells,
    random_arm,
    rate_text,
    tick_cells,
    timing_cells,
)
from swarmtrace.eval.containment import SEED_KEY as ANALYSIS_KEY
from swarmtrace.eval.data import load_runs
from swarmtrace.eval.harness import SplitResult, child_seed
from swarmtrace.eval.oracle import oracle_for
from swarmtrace.eval.recorded import TableRecord, write_gzip, write_run_table
from swarmtrace.features import feature_columns, run_features
from swarmtrace.features.spec import AGGREGATION
from swarmtrace.sim.runner import CHANNELS, TOPOLOGIES, Condition, build_run, run_one
from swarmtrace.trace.context import read_context
from swarmtrace.trace.interventions import Controller, read_interventions
from swarmtrace.trace.io import RunPaths, read_trace
from swarmtrace.trace.schema import TraceEvent
from swarmtrace.trace.tiers import Tier

from .config import ReproduceConfig, make_jobs
from .frozen import detector_controller, frozen_main_models, live_first_flag_tick

PAIR_KEY = 98
SHARING_RATE = 10
MISTAKE_RATE = 2
VIOLATION_SIZES = (1, 2, 5)
OFFENSIVE_SIZES = (2, 3, 5)
GROUP_COUNTS = (1, 2, 3)
CONTROL_REPEATS = 6
OTHER_SEED_KEYS = {95: 1134, 96: 216}
"""Scope and identical-twin dataset seed keys with upper bounds on their indices:
1,134 scope runs and 108 twin pairs, enumerated to 216."""
MIN_CALIBRATION_CONTROLS = 19
RUN_FILES = ("trace.jsonl", "labels.json", "manifest.json", "context.json", "outcomes.json",
             "interventions.jsonl")
MARKDOWN = "containment.md"
DIRECTORY = "containment"


@dataclass(frozen=True)
class ContainmentConfig:
    seed: int = 20261120
    workers: int = min(4, os.cpu_count() or 1)
    control_repeats: int = CONTROL_REPEATS
    n_bootstrap: int = ReproduceConfig.n_bootstrap
    n_ticks: int = 160
    conditions: tuple[Condition, ...] | None = None
    """An explicit pair list (tests); the full grid when None."""

    def __post_init__(self) -> None:
        for name in ("seed", "workers", "control_repeats", "n_bootstrap", "n_ticks"):
            value = getattr(self, name)
            if type(value) is not int or value < (0 if name == "seed" else 1):
                raise ValueError(f"{name} must be a positive integer")
        if self.conditions is not None and (
            not self.conditions or any(condition.scope != "on" for condition in self.conditions)
        ):
            raise ValueError("conditions must be a nonempty tuple of scope-on conditions")


@dataclass(frozen=True)
class PairJob:
    index: int
    seed: int
    """Run seed of every arm: ``child_seed(seed, 98, index)``."""
    condition: Condition
    random_seed: int
    """Draws of the pair's random arms: ``child_seed(seed, 99, 1, index)``."""


def pair_conditions(config: ContainmentConfig) -> tuple[Condition, ...]:
    """54 positive cells by violation size, then 18 control cells by the control repeats."""
    if config.conditions is not None:
        return config.conditions
    common = {"n_ticks": config.n_ticks, "benign_credential_sharing": SHARING_RATE,
              "scope": "on", "scope_mistake_rate": MISTAKE_RATE}
    positives = [Condition(channel, topology, size, groups, violation_size=violation, **common)
                 for groups in GROUP_COUNTS for channel in CHANNELS for topology in TOPOLOGIES
                 for size in OFFENSIVE_SIZES for violation in VIOLATION_SIZES]
    controls = [Condition(channel, topology, 0, groups, **common)
                for groups in GROUP_COUNTS for channel in CHANNELS for topology in TOPOLOGIES
                for _ in range(config.control_repeats)]
    return (*positives, *controls)


def pair_jobs(config: ContainmentConfig) -> tuple[PairJob, ...]:
    return tuple(PairJob(index, child_seed(config.seed, PAIR_KEY, index), condition,
                         child_seed(config.seed, ANALYSIS_KEY, RANDOM_KEY, index))
                 for index, condition in enumerate(pair_conditions(config)))


def check_seeds(config: ContainmentConfig, jobs: Sequence[PairJob]) -> None:
    """Every seed family is internally distinct and disjoint from the others.

    Families: pair run seeds, random-arm seeds (one per pair, shared by that pair's six random
    arms, so distinct across pairs), every bootstrap seed the report can use, the main run
    seeds and the seeds of keys 95 and 96."""
    seeds = [job.seed for job in jobs]
    randoms = [job.random_seed for job in jobs]
    if len(set(seeds)) != len(seeds):
        raise ValueError("pair seeds collide")
    if len(set(randoms)) != len(randoms):
        raise ValueError("random-arm seeds collide across pairs")
    main = {job.seed for job in make_jobs(ReproduceConfig(seed=config.seed))}
    other = {child_seed(config.seed, key, index)
             for key, count in OTHER_SEED_KEYS.items() for index in range(count)}
    boot = bootstrap_seeds(config.seed)
    families = {"pair": set(seeds), "random-arm": set(randoms), "bootstrap": boot,
                "main and keys 95, 96": main | other}
    names = list(families)
    for i, first in enumerate(names):
        for second in names[i + 1:]:
            if families[first] & families[second]:
                raise ValueError(f"{first} seeds collide with {second} seeds")


ARM_SPECS: dict[str, tuple[str, str | None, str | None]] = {
    TWIN: ("twin", None, None),
    **{detector_arm(m, lever): ("detector", m, lever) for m in DETECTORS for lever in LEVERS},
    **{random_arm(m, lever): ("random", m, lever) for m in DETECTORS for lever in LEVERS},
    **{halt_arm(m): ("halt", m, None) for m in DETECTORS},
    **{oracle_arm(lever): ("oracle", None, lever) for lever in LEVERS},
}


def twin_events(twin_dir: Path) -> tuple[TraceEvent, ...]:
    """The twin's events projected to V1 in trace order, as ``run_one`` presents them."""
    return read_trace(RunPaths(twin_dir).trace, Tier.V1).events


def first_flags(models: SplitResult, events: Sequence[TraceEvent],
                n_ticks: int) -> dict[str, int | None]:
    """Each detector's first-flag tick on the twin. The flag does not depend on the lever:
    before it, a controller only scores."""
    return {method: live_first_flag_tick(
        lambda method=method: detector_controller(models, method, "quarantine"), events, n_ticks)
        for method in DETECTORS}


def first_decision(
    make: Callable[[], Controller], events: Sequence[TraceEvent], n_ticks: int,
) -> tuple[int | None, Controller]:
    """Replay the twin through a fresh controller until its first decision.

    Returns the decision tick, or None, and the replayed controller (after a full replay when
    it never decides)."""
    controller = make()
    by_tick: dict[int, list[TraceEvent]] = {}
    for event in events:
        by_tick.setdefault(event.tick, []).append(event)
    for tick in range(n_ticks):
        if controller.observe(tick, tuple(by_tick.get(tick, ()))):
            return tick, controller
    return None, controller


def controller_for(
    arm: str, models: SplitResult, job: PairJob, twin_dir: Path,
    flags: Mapping[str, int | None], shadow_dir: Path | None = None,
) -> Controller:
    """A fresh controller for ``arm`` of ``job``; ``shadow_dir`` is the shadow arm's run for a
    random arm."""
    kind, method, lever = ARM_SPECS[arm]
    if kind == "detector":
        return detector_controller(models, str(method), str(lever))
    if kind == "random":
        if shadow_dir is None:
            raise ValueError("a random arm needs its shadow's run")
        return RandomController(read_interventions(RunPaths(shadow_dir).interventions),
                                job.random_seed)
    if kind == "halt":
        tick = flags[str(method)]
        if tick is None:
            raise ValueError("halt-all needs a first flag")
        return HaltAllController(tick)
    if kind == "oracle":
        (record,) = load_runs(twin_dir.parent)
        return oracle_for(record, read_context(RunPaths(twin_dir).context), str(lever))
    raise ValueError(f"arm {arm!r} has no controller")


@dataclass(frozen=True)
class PairResult:
    job: PairJob
    run_id: str
    flags: Mapping[str, int | None]
    measures: tuple[ArmMeasure, ...]
    """One per arm, in ``ARMS`` order."""
    features: pd.DataFrame
    """V1 aggregation run features, one row per arm in ``ARMS`` order."""
    random_stats: Mapping[str, tuple[int, int, int]]
    """Random arm: total requested, total named, shortfall ticks."""
    simulated: tuple[str, ...]


def host_map(job: PairJob) -> HostMap:
    world = build_run(job.condition, job.seed).world
    return HostMap({file.id: file.host for file in world.files.values()},
                   {credential.id: credential.host for credential in world.credentials.values()})


def simulate_pair(job: PairJob, models: SplitResult,
                  root: Path) -> tuple[PairResult, dict[str, Path | None]]:
    """Simulate one pair's twin and every arm whose controller decides, under ``root``."""
    n_ticks = job.condition.n_ticks
    twin_dir = run_one(job.condition, job.seed, root / TWIN / "run")
    events = twin_events(twin_dir)
    flags = first_flags(models, events, n_ticks)
    dirs: dict[str, Path | None] = {TWIN: twin_dir}
    random_stats: dict[str, tuple[int, int, int]] = {}
    for arm in ARMS[1:]:
        kind, method, lever = ARM_SPECS[arm]
        dirs[arm] = None
        shadow = None
        if kind in ("detector", "halt") and flags[str(method)] is None:
            continue
        if kind == "random":
            shadow = dirs[detector_arm(str(method), str(lever))]
            if shadow is None:
                random_stats[arm] = (0, 0, 0)
                continue

        def make(arm: str = arm, shadow: Path | None = shadow) -> Controller:
            return controller_for(arm, models, job, twin_dir, flags, shadow)

        tick, replayed = first_decision(make, events, n_ticks)
        if tick is None:
            if isinstance(replayed, RandomController):
                random_stats[arm] = (replayed.total_requested, replayed.total_named,
                                     len(replayed.shortfalls))
            continue
        controller = make()
        dirs[arm] = run_one(job.condition, job.seed, root / arm / "run", controller=controller)
        applied = read_interventions(RunPaths(dirs[arm]).interventions)
        if not applied or min(record.tick for record in applied) != tick:
            raise RuntimeError(f"pair {job.index} {arm}: the twin replay's first decision "
                               "does not match the arm")
        if isinstance(controller, RandomController):
            random_stats[arm] = (controller.total_requested, controller.total_named,
                                 len(controller.shortfalls))
    hosts = host_map(job)
    twin = load_run_facts(twin_dir)
    columns = list(feature_columns("run", Tier.V1, (AGGREGATION,)))
    twin_features = run_features(read_trace(RunPaths(twin_dir).trace, Tier.V1))[columns]
    measures, frames = [], []
    for arm in ARMS:
        directory = dirs[arm]
        if arm == TWIN:
            measures.append(measure_arm(arm, twin, twin, hosts))
            frames.append(twin_features)
        elif directory is None:
            measures.append(measure_arm(arm, twin, None, hosts))
            frames.append(twin_features)
        else:
            measures.append(measure_arm(arm, twin, load_run_facts(directory), hosts))
            frames.append(run_features(read_trace(RunPaths(directory).trace, Tier.V1))[columns])
    result = PairResult(job, twin.labels.run_id, flags, tuple(measures), pd.concat(frames),
                        random_stats, tuple(arm for arm in ARMS if dirs[arm] is not None))
    return result, dirs


_MODELS: list[SplitResult] = []


def _initialize(models: SplitResult) -> None:
    _MODELS[:] = [models]


def _pair_worker(task: tuple[PairJob, Path | None]) -> PairResult:
    job, keep = task
    if keep is not None:
        return simulate_pair(job, _MODELS[0], keep / f"pair-{job.index:04d}")[0]
    with TemporaryDirectory(prefix="swarmtrace-contain-") as temporary:
        result, _ = simulate_pair(job, _MODELS[0], Path(temporary))
    return result


def run_pairs(jobs: Sequence[PairJob], models: SplitResult, workers: int,
              keep: Path | None = None) -> list[PairResult]:
    """Every pair, in job order whatever ``workers`` is. Run directories are deleted unless
    ``keep`` names a directory to hold them, one ``pair-<index>`` per pair."""
    tasks = [(job, keep) for job in jobs]
    if workers == 1 or len(jobs) < 2:
        _initialize(models)
        return [_pair_worker(task) for task in tasks]
    names = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")
    previous = {name: os.environ.get(name) for name in names}
    try:
        os.environ.update(dict.fromkeys(names, "1"))
        with ProcessPoolExecutor(max_workers=workers,
                                 mp_context=multiprocessing.get_context("spawn"),
                                 initializer=_initialize, initargs=(models,)) as pool:
            return list(pool.map(_pair_worker, tasks))
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def _table(rows: Sequence[Mapping[str, str]]) -> str:
    if not rows:
        return "No rows.\n"
    columns = list(rows[0])
    lines = ["| " + " | ".join(columns) + " |", "| " + " | ".join("---" for _ in columns) + " |"]
    lines.extend("| " + " | ".join(str(row[column]) for column in columns) + " |"
                 for row in rows)
    return "\n".join(lines) + "\n"


def _by_arm(results: Sequence[PairResult], arm: str,
            keep: Callable[[PairResult], bool] = lambda result: True) -> list[ArmMeasure]:
    index = ARMS.index(arm)
    return [result.measures[index] for result in results if keep(result)]


def _random_cells(results: Sequence[PairResult], arm: str) -> dict[str, str]:
    stats = [result.random_stats.get(arm, (0, 0, 0)) for result in results]
    return {"random: requested": str(sum(s[0] for s in stats)),
            "random: named": str(sum(s[1] for s in stats)),
            "random: pairs with a shortfall": str(sum(s[2] > 0 for s in stats))}


def _shortfall(result: PairResult, arm: str) -> bool:
    return result.random_stats.get(arm, (0, 0, 0))[2] > 0


def calibration_rows(results: Sequence[PairResult], models: SplitResult) -> list[dict[str, str]]:
    rows = []
    for method in DETECTORS:
        recorded = {row.metric: row for row in models.rows if row.method == method}
        controls = [result for result in results if not result.measures[0].positive]
        positives = [result for result in results if result.measures[0].positive]
        rows.append({
            "detector": method,
            "scope-on control twins flagged (live grid)": rate_text(
                sum(r.flags[method] is not None for r in controls), len(controls)),
            "scope-on positive twins flagged (live grid)": rate_text(
                sum(r.flags[method] is not None for r in positives), len(positives)),
            "recorded main FPR, full trace": rate_text(recorded["false_positive_rate"].n,
                                                       recorded["false_positive_rate"].total),
            "recorded main FPR, online": rate_text(recorded["online_false_positive_rate"].n,
                                                   recorded["online_false_positive_rate"].total),
        })
    return rows


def render(config: ContainmentConfig, results: Sequence[PairResult], models: SplitResult,
           command: str, digests: Mapping[str, str]) -> str:
    seed, boot = config.seed, config.n_bootstrap
    positives = [r for r in results if r.measures[0].positive]
    controls = [r for r in results if not r.measures[0].positive]
    calibration = next(row for row in models.rows if row.metric == "calibration_controls")
    counts = calibration.split_counts if hasattr(calibration, "split_counts") else ()
    by_size: dict[int, int] = {}
    for result in positives:
        size = result.job.condition.violation_size
        by_size[size] = by_size.get(size, 0) + 1
    simulated = sum(len(r.simulated) for r in results)
    lines = [
        "# Containment experiment", "",
        f"Seed: {seed}. Command: `{command}`. Output does not depend on `--workers`.", "",
        f"Pairs: {len(results)}: {len(positives)} positive (scope violation; "
        + ", ".join(f"size {size}: {count}" for size, count in sorted(by_size.items()))
        + f") and {len(controls)} control. Scope on, sharing rate {SHARING_RATE}, mistake "
        f"rate {MISTAKE_RATE}, {config.n_ticks} ticks. Control repeats per control cell: "
        f"{config.control_repeats}"
        + ("" if config.control_repeats == CONTROL_REPEATS else
           f" (reduced from {CONTROL_REPEATS} for runtime)")
        + f". Pair i runs at `child_seed({seed}, 98, i)`.",
        "",
        f"Arms per pair: {len(ARMS)}. Simulated runs: {simulated} of {len(ARMS) * len(results)}; "
        "an arm whose controller never decides is not simulated and its outcomes are the "
        "twin's.", "",
        "Detectors and thresholds: the frozen main models (by-run split, V1, aggregation), "
        "refitted deterministically from `data/dataset/main`; nothing is refitted on this "
        f"dataset. Main split counts (fitting C/P, calibration C/P, test C/P): "
        f"{'/'.join(str(c) for c in counts)}. Calibration controls: {calibration.n}. "
        "Controllers check every 8 ticks (7, 15, ...) and act from the next tick.", "",
        "Rates over pairs (and the calibration rates over runs) are k of n with a 95% Wilson "
        "interval. Quantities pooled over pairs (files, calls, agents, lenders; marked "
        "pooled) and means over pairs carry 95% percentile bootstrap intervals over pairs, "
        f"because agents and calls are clustered by pair ({boot} resamples, seeds "
        f"`child_seed({seed}, 99, 0, arm, metric)`). Random arms draw from "
        f"`child_seed({seed}, 99, 1, i)` for pair i, shared by the six random arms of a pair.",
        "",
        "## Detector calibration under shift", "",
        "Flag: the controller's first flag on the uncontained twin, replayed on the live "
        "grid. The recorded main rates are the frozen models' by-run test rows; the online "
        "row uses the offline checkpoint grid, which adds the run's last event.", "",
        _table(calibration_rows(results, models)), "",
    ]
    arms = ARMS[1:]
    detector_arms = [detector_arm(m, lever) for m in DETECTORS for lever in LEVERS]
    lines += ["## Required out-of-scope reads prevented, then objective (positive pairs)", "",
              "Prevented: required files the collector read in the twin and not in the arm "
              "(outcomes.json), pooled over pairs and as a mean of per-pair fractions over "
              "pairs whose twin read any. Fully, partly and not prevented count pairs. The "
              "objective also requires the group's later writes, so it can fail with no "
              "required read prevented.", ""]
    rows = [{"arm": arm, **prevention_cells(_by_arm(positives, arm), seed,
                                            (ARMS.index(arm),), boot)} for arm in ARMS]
    lines += [_table(rows), ""]
    lines += ["## Why required reads were not prevented (detector arms, positive pairs)", "",
              "Positive pairs by where the arm's first intervention affecting the collector "
              "falls against the twin's required reads: a quarantine naming the collector, a "
              "halt_all, or the revocation of every credential the collector logged in with "
              "on the required files' host in the twin (it denies that login or ends that "
              "session). Exceptions list pairs hit at or before the first required read that "
              "were not fully prevented.", ""]
    rows = []
    for arm in detector_arms:
        rows.extend({"arm": arm, **row} for row in decomposition_rows(
            [(r.job.index, r.measures[ARMS.index(arm)]) for r in positives]))
    lines += [_table(rows), ""]
    counterfactual = [first_checkpoint_precedes(r.measures[0], CHECKPOINT_EVERY)
                      for r in positives]
    defined = [value for value in counterfactual if value is not None]
    lines += [
        "Counterfactual from the twins, separating detection coverage from the checkpoint "
        "cadence: an intervention decided at the first live checkpoint at or after the first "
        "relayed login, effective the next tick, would precede the first required read in "
        f"{rate_text(sum(defined), len(defined))} positive pairs.", ""]
    lines += ["## Timing against the damage (positive pairs)", "",
              "Each placement cell gives the first intervention / the first intervention "
              "affecting the collector. Ticks are signed, from the twin's first relayed login. "
              "An intervention effective at the tick of a read precedes it.", "",
              _table([{"arm": arm, **timing_cells(_by_arm(positives, arm))} for arm in arms]),
              "", _table([{"arm": arm, **tick_cells(_by_arm(positives, arm))} for arm in arms]),
              ""]
    for title, population, offset in (("positive pairs", positives, 0),
                                      ("control pairs", controls, len(ARMS))):
        lines += [f"## Benign cost against the twin ({title})", "",
                  _table([{"arm": arm, **cost_cells(_by_arm(population, arm), seed,
                                                    (offset + ARMS.index(arm),), boot)}
                          for arm in arms]), ""]
    rows = []
    for method in DETECTORS:
        for arm in (*(detector_arm(method, lever) for lever in LEVERS), halt_arm(method)):
            flagged = [r.measures[ARMS.index(arm)] for r in controls
                       if r.flags[method] is not None]
            rows.append({"arm": arm, **flagged_control_cells(flagged, len(controls))})
    lines += ["## Benign cost on flagged control runs", "",
              "Control runs whose detector flagged on the twin (false alarms), and the benign "
              "cost of acting on them, per run.", "", _table(rows), ""]
    revoke = [arm for arm in arms if arm.endswith("revoke")]
    lines += ["## Owners of revoked credentials (revoke arms, all pairs)", "",
              "Lenders: owners of a revoked credential that another agent used for an ok login "
              "in the twin before the revocation took effect. Other revoked owners: owners of "
              "revoked credentials nobody borrowed. Locked out: ok calls on its own host at or "
              "after the revocation's effective tick in the twin, none in the arm. Tasks lost "
              "count distinct tasks owned. Each host accepts one credential, revocation ends "
              "sessions opened with it, and credentials are not reissued, so the owner of a "
              "revoked credential is locked out of its own host by construction.", "",
              _table([{"arm": arm, "cohort": cohort, "role": role,
                       **lender_cells(_by_arm(results, arm), cohort, role, seed,
                                      (2 * len(ARMS) + ARMS.index(arm),), boot)}
                      for arm in revoke for cohort in COHORTS for role in ROLES]), ""]
    lines += ["## Matched random comparisons", "",
              "Each random arm replays its detector arm's decision ticks and counts with "
              "random targets. The first two lines use all pairs; the second two use only "
              "pairs where the random arm had no shortfall. Prevention and objective on "
              "positive pairs; benign cost on all pairs.", ""]
    rows = []
    for method in DETECTORS:
        for lever in LEVERS:
            shadow, randomized = detector_arm(method, lever), random_arm(method, lever)
            for subset, keep in (
                ("all pairs", lambda r: True),
                ("pairs without shortfall", lambda r, a=randomized: not _shortfall(r, a)),
            ):
                chosen = [r for r in results if keep(r)]
                chosen_positive = [r for r in chosen if r.measures[0].positive]
                for arm in (shadow, randomized):
                    # One seed per arm and metric: a subset equal to all pairs prints the same
                    # intervals as the full tables.
                    prevention = prevention_cells(_by_arm(chosen_positive, arm), seed,
                                                  (ARMS.index(arm),), boot)
                    cost = cost_cells(_by_arm(chosen, arm), seed,
                                      (3 * len(ARMS) + ARMS.index(arm),), boot)
                    rows.append({
                        "arm": arm, "pairs": subset,
                        "positive pairs": prevention["pairs"],
                        "required reads prevented (pooled)":
                            prevention["required reads prevented (pooled)"],
                        "objective completed, arm": prevention[
                            "objective completed (also requires the group's later writes), arm"],
                        "objective completed, twin": prevention["objective completed, twin"],
                        "all pairs": cost["pairs"],
                        "benign ok-call deficit (pooled)": cost["benign ok-call deficit (pooled)"],
                        "benign agents newly denied (pooled)":
                            cost["benign agents newly denied (pooled)"],
                        **_random_cells(chosen, randomized),
                    })
    lines += [_table(rows), ""]
    lines += ["## Paired comparisons", "",
              "Sums over pairs of the first arm minus the second, with a percentile bootstrap "
              f"of the sum over pairs (seeds `child_seed({seed}, 99, 0, {COMPARISON_KEY}, "
              "comparison, metric)`), and the pairs where each arm is larger. Required files "
              "on positive pairs; benign measures on all pairs.", ""]
    rows = []

    def compare(index: int, metric: int, first: str, second: str, measure: str,
                population: Sequence[PairResult],
                value: Callable[[ArmMeasure], int]) -> None:
        a, b = _by_arm(population, first), _by_arm(population, second)
        rows.append({"comparison": f"{first} minus {second}", "measure": measure,
                     **paired_cells([value(m) for m in a], [value(m) for m in b],
                                    bootstrap_seed(seed, COMPARISON_KEY, index, metric), boot,
                                    ("first", "second"))})

    for index, (method, lever) in enumerate((m, lever) for m in DETECTORS for lever in LEVERS):
        compare(index, 0, detector_arm(method, lever), random_arm(method, lever),
                "required files prevented", positives, lambda m: m.prevented)
    for offset, method in enumerate(DETECTORS):
        first, second = detector_arm(method, "quarantine"), detector_arm(method, "revoke")
        for metric, (measure, value) in enumerate((
            ("benign ok-call deficit", lambda m: m.benign_ok_deficit),
            ("benign tasks lost", lambda m: m.benign_tasks_lost),
            ("benign agents newly denied", lambda m: m.benign_newly_denied),
        )):
            compare(6 + offset, metric, first, second, measure, results, value)
    for offset, method in enumerate(DETECTORS):
        first, second = halt_arm(method), detector_arm(method, "quarantine")
        compare(9 + offset, 0, first, second, "required files prevented", positives,
                lambda m: m.prevented)
        compare(9 + offset, 1, first, second, "benign ok-call deficit", results,
                lambda m: m.benign_ok_deficit)
    lines += [_table(rows), ""]
    lines += [
        "## Definitions", "",
        "- Benign agents: every agent whose label role is not offensive. Benign task: an "
        "outcomes.json task whose owner is benign; lost when complete in the twin and "
        "incomplete in the arm.",
        "- Benign ok-call deficit: ok calls by benign agents in the twin minus in the arm, "
        "summed over pairs, over the twin's benign ok calls.",
        "- Benign agents newly denied: benign agents with a denied call in the arm whose "
        "(tick, tool, target) is not a denied call by that agent in the twin, over all benign "
        "agents of the pairs.",
        "- Change in denied calls by benign agents: arm minus twin, summed. Scripted agents "
        "keep their call schedule when blocked, so in this experiment each lost ok call "
        "appears as one denied call.",
        "- Benign agents quarantined counts distinct agents named by quarantine records; a "
        "halt-all arm quarantines every agent. Benign-owned credentials revoked counts "
        "distinct revoked credentials whose directory owner is benign.",
        "- Any intervention: the arm has at least one intervention record; targets are "
        "counted distinct, not by record.",
        "- A degenerate bootstrap interval is one where every valid resample gave the same "
        "value, so both ends are equal; it is printed with that qualification, because it "
        "reflects the pairs that carry the count, not certainty about the population value.",
        "",
        "## SHA-256", "",
        "```",
        *(f"{digest}  {name}" for name, digest in sorted(digests.items())),
        "```", "",
    ]
    return "\n".join(lines)


def _sample(results: Sequence[PairResult]) -> tuple[PairResult, str]:
    """The first positive pair, in job order, with a detector arm that intervened."""
    detector_arms = [detector_arm(m, lever) for m in DETECTORS for lever in LEVERS]
    for result in results:
        if not result.measures[0].positive:
            continue
        for arm in detector_arms:
            if result.measures[ARMS.index(arm)].targets:
                return result, arm
    raise ValueError("no detector arm intervened on any positive pair")


def write_sample(out: Path, job: PairJob, arm: str, models: SplitResult) -> None:
    """Regenerate one pair's twin and one contained arm (not a random arm) and store every
    run file, gzipped."""
    with TemporaryDirectory(prefix="swarmtrace-sample-") as temporary:
        root = Path(temporary)
        twin = run_one(job.condition, job.seed, root / TWIN / "run")
        flags = first_flags(models, twin_events(twin), job.condition.n_ticks)
        contained = run_one(job.condition, job.seed, root / arm / "run",
                            controller=controller_for(arm, models, job, twin, flags))
        for name, directory in ((TWIN, twin), (arm, contained)):
            for filename in RUN_FILES:
                path = directory / filename
                if path.is_file():
                    write_gzip(out / f"pair-{job.index:04d}" / name / f"{filename}.gz",
                               path.read_bytes())


def write_table(path: Path, results: Sequence[PairResult]) -> None:
    keyed, records, extra = [], [], {}
    for result in results:
        condition = {key: value for key, value in asdict(result.job.condition).items()
                     if value is not None}
        for index, arm in enumerate(ARMS):
            key = f"{result.run_id}.{arm}"
            frame = result.features.iloc[[index]].copy()
            frame.index = pd.Index([key], name="run_id")
            keyed.append(frame)
            measure = result.measures[index]
            records.append(TableRecord(key, measure.positive, {
                **condition, "arm": arm, "pair": result.job.index, "seed": result.job.seed}))
            values = outcome_values(measure)
            kind, method, _ = ARM_SPECS[arm]
            if kind in ("detector", "halt") and result.flags[str(method)] is not None:
                values["first_flag_tick"] = int(result.flags[str(method)])  # type: ignore[arg-type]
            if kind == "random":
                requested, named, shortfalls = result.random_stats.get(arm, (0, 0, 0))
                values |= {"random_requested": requested, "random_named": named,
                           "random_shortfall_ticks": shortfalls}
            extra[key] = values
    frame = pd.concat(keyed).sort_index()
    write_run_table(path, frame, records, extra)


def containment(out: str | Path, data: str | Path, config: ContainmentConfig,
                *, keep: Path | None = None) -> Path:
    """Run the experiment and write ``containment.md`` and ``containment/`` under ``out``.

    ``keep`` retains every simulated run directory there (for inspection and tests)."""
    out, data = Path(out), Path(data)
    if (out / MARKDOWN).exists() or (out / DIRECTORY).exists():
        raise ValueError(f"{out} already holds containment output; choose a fresh directory")
    jobs = pair_jobs(config)
    check_seeds(config, jobs)
    models = frozen_main_models(data, config.seed)
    calibration = next(row for row in models.rows if row.metric == "calibration_controls")
    if calibration.n < MIN_CALIBRATION_CONTROLS:
        raise ValueError(f"the frozen split has {calibration.n} calibration controls; "
                         f"at least {MIN_CALIBRATION_CONTROLS} are needed")
    command = (f"swarmtrace containment --seed {config.seed} --data {data.as_posix()} "
               f"--out DIR --control-repeats {config.control_repeats} "
               f"--bootstrap {config.n_bootstrap}")
    print(f"seed={config.seed}; {len(jobs)} pairs; command={command} "
          f"--workers {config.workers}", flush=True)
    results = run_pairs(jobs, models, config.workers, keep)
    target = out / DIRECTORY
    target.mkdir(parents=True)
    write_table(target / "runs.csv.gz", results)
    sample, arm = _sample(results)
    write_sample(target / "raw", sample.job, arm, models)
    digests = {path.relative_to(out).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
               for path in sorted(target.rglob("*")) if path.is_file()}
    text = render(config, results, models, command, digests)
    (out / MARKDOWN).write_text(text, encoding="utf-8", newline="\n")
    return out / MARKDOWN


def add_parser(commands: argparse._SubParsersAction) -> None:
    parser = commands.add_parser("containment", help="Run and record the containment experiment")
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--data", type=Path, required=True,
                        help="Directory holding the recorded main dataset (such as data)")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=ContainmentConfig.workers)
    parser.add_argument("--control-repeats", type=int, default=CONTROL_REPEATS)
    parser.add_argument("--bootstrap", type=int, default=ContainmentConfig.n_bootstrap)


def run(arguments: argparse.Namespace) -> None:
    config = ContainmentConfig(seed=arguments.seed, workers=arguments.workers,
                               control_repeats=arguments.control_repeats,
                               n_bootstrap=arguments.bootstrap)
    containment(arguments.out, arguments.data, config)


