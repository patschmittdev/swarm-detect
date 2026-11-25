from collections.abc import Mapping, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from swarmtrace.detect import CHECKPOINT_EVERY, checkpoints, volume_features
from swarmtrace.features import agent_features, pair_features, run_features
from swarmtrace.trace.io import Labels, RunPaths, Trace, read_labels, read_manifest, read_trace
from swarmtrace.trace.tiers import Tier

OFFENSIVE = "offensive"
BENIGN_TEAM = "benign_team"
SHARED_LOGINS = "shared_credential_logins"
"""V1 pair feature: logins by one agent with a credential another agent used first."""
PREFIX_INDEX = ["run_id", "tick"]
_LEVELS = {"agent": agent_features, "pair": pair_features, "run": run_features}


@dataclass(frozen=True)
class RunRecord:
    run_id: str
    trace_path: Path
    labels: Labels
    condition: Mapping[str, int | str]

    @property
    def offensive(self) -> frozenset[str]:
        return frozenset(
            agent for agent, label in self.labels.agents.items() if label.role == OFFENSIVE
        )

    @property
    def positive(self) -> bool:
        return bool(self.offensive)


def find_runs(root: str | Path) -> list[Path]:
    """Run directories directly under ``root`` that contain a trace, sorted by name."""
    found = sorted(path for path in Path(root).iterdir() if RunPaths(path).trace.is_file())
    if not found:
        raise ValueError(f"no run directories with a trace under {root}")
    return found


def load_runs(root: str | Path) -> list[RunRecord]:
    """Label-side records for every run under ``root``, sorted by run id."""
    records = []
    for directory in find_runs(root):
        paths = RunPaths(directory)
        labels = read_labels(paths.labels)
        manifest = read_manifest(paths.manifest)
        if labels.run_id != manifest.run_id:
            raise ValueError(
                f"{directory}: labels run_id {labels.run_id} != manifest run_id {manifest.run_id}"
            )
        records.append(RunRecord(labels.run_id, paths.trace, labels, manifest.condition))
    ids = [record.run_id for record in records]
    if len(set(ids)) != len(ids):
        raise ValueError(f"duplicate run ids under {root}")
    return sorted(records, key=lambda record: record.run_id)


def pair_labels(index: pd.MultiIndex, labels: Labels) -> np.ndarray:
    """True for pairs whose agents are both offensive and share a group id."""
    agents = labels.agents

    def coordinated(first: str, second: str) -> bool:
        a, b = agents.get(first), agents.get(second)
        return (
            a is not None and b is not None and a.role == OFFENSIVE and b.role == OFFENSIVE
            and a.group is not None and a.group == b.group
        )

    return np.array([coordinated(first, second) for first, second in index], dtype=bool)


def shared_login_pairs(pairs: pd.DataFrame) -> dict[str, frozenset[tuple[str, str]]]:
    """Per run, the agent pairs with at least one shared-credential login.

    ``pairs`` is indexed by ``(run_id, agent_a, agent_b)`` and has the V1 ``SHARED_LOGINS``
    column. Every run in the index gets an entry, possibly empty.
    """
    found: dict[str, set[tuple[str, str]]] = {
        str(run): set() for run in pairs.index.get_level_values("run_id")
    }
    for (run, first, second), value in pairs[SHARED_LOGINS].items():
        if value > 0:
            found[str(run)].add((str(first), str(second)))
    return {run: frozenset(found[run]) for run in sorted(found)}


def _with_run(frame: pd.DataFrame, run_id: str) -> pd.DataFrame:
    return pd.concat({run_id: frame}, names=["run_id"])


def feature_table(root: str | Path, level: str, tier: Tier) -> pd.DataFrame:
    """Feature matrix at ``level`` over every run under ``root``, read from traces alone.

    Agent and pair rows carry ``run_id`` as their first index level.
    """
    if level not in _LEVELS:
        raise ValueError(f"Unknown feature level: {level!r}; expected one of {tuple(_LEVELS)}")
    frames = []
    for directory in find_runs(root):
        trace = read_trace(RunPaths(directory).trace, tier)
        frame = _LEVELS[level](trace)
        frames.append(frame if level == "run" else _with_run(frame, trace.run_id))
    return pd.concat(frames)


@dataclass(frozen=True)
class TierData:
    """Feature matrices for one tier, row-aligned to sorted run ids, with labels kept apart."""

    tier: Tier
    records: Mapping[str, RunRecord]
    traces: Mapping[str, Trace]
    runs: pd.DataFrame
    volume: pd.DataFrame
    pairs: pd.DataFrame
    pair_labels: np.ndarray
    prefix_runs: pd.DataFrame
    """Run features at each online checkpoint, indexed by ``(run_id, tick)``."""
    prefix_volume: pd.DataFrame
    """Volume features at each online checkpoint, indexed by ``(run_id, tick)``."""
    checkpoint_every: int = CHECKPOINT_EVERY
    shared_logins: Mapping[str, frozenset[tuple[str, str]]] = field(default_factory=dict)
    """Label-side evidence for the role table: per run with a benign team, the agent pairs with
    a shared-credential login, always computed at V1 whatever ``tier`` is. A run missing here
    has no evidence."""


def _at_tick(frame: pd.DataFrame, run_id: str, tick: int) -> pd.DataFrame:
    return frame.set_axis(pd.MultiIndex.from_tuples([(run_id, tick)], names=PREFIX_INDEX))


def _build_serial(
    records: Sequence[RunRecord], tier: Tier, checkpoint_every: int, retain_traces: bool,
) -> TierData:
    if not records:
        raise ValueError("build_tier_data needs at least one run")
    ordered = sorted(records, key=lambda record: record.run_id)
    traces, runs, volume, pairs, labels = {}, [], [], [], []
    prefix_runs, prefix_volume, shared = [], [], {}
    for record in ordered:
        trace = read_trace(record.trace_path, tier)
        if trace.run_id != record.run_id:
            raise ValueError(f"{record.trace_path}: trace run_id {trace.run_id} != {record.run_id}")
        if retain_traces:
            traces[record.run_id] = trace
        full_runs = run_features(trace)
        full_volume = volume_features(agent_features(trace), trace.run_id)
        runs.append(full_runs)
        volume.append(full_volume)
        last = max(event.tick for event in trace.events)
        for tick in checkpoints(last, checkpoint_every):
            at_runs = full_runs if tick == last else run_features(trace, until_tick=tick)
            at_volume = full_volume if tick == last else volume_features(
                agent_features(trace, until_tick=tick), trace.run_id
            )
            prefix_runs.append(_at_tick(at_runs, trace.run_id, tick))
            prefix_volume.append(_at_tick(at_volume, trace.run_id, tick))
        frame = pair_features(trace)
        labels.append(pair_labels(frame.index, record.labels))
        pairs.append(_with_run(frame, trace.run_id))
        if any(label.role == BENIGN_TEAM for label in record.labels.agents.values()):
            evidence = frame if SHARED_LOGINS in frame else pair_features(
                read_trace(record.trace_path, Tier.V1))
            shared.update(shared_login_pairs(_with_run(evidence, trace.run_id)))
    return TierData(
        tier=tier,
        records={record.run_id: record for record in ordered},
        traces=traces,
        runs=pd.concat(runs),
        volume=pd.concat(volume),
        pairs=pd.concat(pairs),
        pair_labels=np.concatenate(labels),
        prefix_runs=pd.concat(prefix_runs),
        prefix_volume=pd.concat(prefix_volume),
        checkpoint_every=checkpoint_every,
        shared_logins=shared,
    )


def _build_one(job: tuple[RunRecord, Tier, int, bool]) -> TierData:
    record, tier, every, retain = job
    return _build_serial([record], tier, every, retain)


def build_tier_data(
    records: Sequence[RunRecord], tier: Tier, *, workers: int = 1,
    checkpoint_every: int = CHECKPOINT_EVERY, retain_traces: bool = True,
) -> TierData:
    """Extract independently per run; assembly order never depends on worker completion."""
    if not records:
        raise ValueError("build_tier_data needs at least one run")
    if workers < 1 or checkpoint_every < 1:
        raise ValueError("workers and checkpoint_every must be positive")
    if workers == 1 or len(records) < 2:
        return _build_serial(records, tier, checkpoint_every, retain_traces)
    jobs = [(record, tier, checkpoint_every, retain_traces)
            for record in sorted(records, key=lambda record: record.run_id)]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        parts = list(pool.map(_build_one, jobs))
    return TierData(
        tier, {run: record for part in parts for run, record in part.records.items()},
        {run: trace for part in parts for run, trace in part.traces.items()},
        pd.concat([part.runs for part in parts]), pd.concat([part.volume for part in parts]),
        pd.concat([part.pairs for part in parts]),
        np.concatenate([part.pair_labels for part in parts]),
        pd.concat([part.prefix_runs for part in parts]),
        pd.concat([part.prefix_volume for part in parts]), checkpoint_every,
        {run: found for part in parts for run, found in part.shared_logins.items()},
    )
