from collections import deque
from pathlib import Path

import numpy as np

from .io import AgentLabel, Labels, Manifest, RunPaths, write_labels, write_manifest, write_trace
from .schema import SCHEMA_VERSION, TraceEvent


def _token(rng: np.random.Generator, byte_count: int) -> str:
    return rng.bytes(byte_count).hex()


def _ids(rng: np.random.Generator, prefix: str, count: int) -> list[str]:
    identifiers: list[str] = []
    seen: set[str] = set()
    while len(identifiers) < count:
        candidate = prefix + _token(rng, 4)
        if candidate not in seen:
            identifiers.append(candidate)
            seen.add(candidate)
    return identifiers


def _bounded_integer(name: str, value: int, lower: int, upper: int | None = None) -> None:
    if type(value) is not int or value < lower or (upper is not None and value > upper):
        raise ValueError(f"{name} must be an integer from {lower} to {upper or 'unbounded'}")


def generate_synthetic_runs(
    out_dir: str | Path, n_runs: int, seed: int, signal: int, positive_percent: int = 50
) -> list[Path]:
    _bounded_integer("n_runs", n_runs, 0)
    _bounded_integer("seed", seed, 0)
    _bounded_integer("signal", signal, 0, 100)
    _bounded_integer("positive_percent", positive_percent, 0, 100)
    content = "synthetic"
    directories = []
    for run_seed in np.random.SeedSequence(seed).spawn(n_runs):
        count_seed, label_seed, id_seed, action_seed, order_seed, signal_seed = run_seed.spawn(6)
        count_rng = np.random.default_rng(count_seed)
        agent_count = int(count_rng.integers(12, 29))
        label_rng = np.random.default_rng(label_seed)
        positive = int(label_rng.integers(100)) < positive_percent
        group_size = int(label_rng.integers(2, 9)) if positive else 0
        group_indices = set(int(i) for i in label_rng.permutation(agent_count)[:group_size])
        id_rng = np.random.default_rng(id_seed)
        run_id = _token(id_rng, 8)
        agents = _ids(id_rng, "a-", agent_count)
        files = _ids(id_rng, "f-", 256)
        action_rngs = [np.random.default_rng(child) for child in action_seed.spawn(agent_count)]
        order_rng = np.random.default_rng(order_seed)
        signal_rng = np.random.default_rng(signal_seed)
        recent_group: deque[TraceEvent] = deque()
        events = []
        for tick in range(16):
            for index_value in order_rng.permutation(agent_count):
                index = int(index_value)
                agent = agents[index]
                target = files[int(action_rngs[index].integers(len(files)))]
                while recent_group and recent_group[0].tick < tick - 3:
                    recent_group.popleft()
                if index in group_indices and signal > 0:
                    candidates = [event.target for event in recent_group if event.agent != agent]
                    if candidates and signal_rng.random() < 0.95 * signal / 100:
                        target = candidates[int(signal_rng.integers(len(candidates)))]
                event = TraceEvent(
                    schema_version=SCHEMA_VERSION, run_id=run_id, seq=len(events), tick=tick,
                    agent=agent, tool="read", target=target, args={},
                    result={"status": "ok", "size": len(content)}, content=content, provenance=None,
                )
                events.append(event)
                if index in group_indices:
                    recent_group.append(event)
        directory = Path(out_dir) / run_id
        directory.mkdir(parents=True, exist_ok=True)
        paths = RunPaths(directory)
        labels = Labels(
            run_id=run_id,
            agents={
                agent: AgentLabel(
                    role="offensive" if index in group_indices else "benign_solo",
                    group="group-1" if index in group_indices else None,
                )
                for index, agent in enumerate(agents)
            },
            objective_completed=False, objective_tick=None,
        )
        manifest = Manifest(
            run_id=run_id, seed=seed,
            condition={
                "generator": "synthetic", "signal": signal,
                "positive_percent": positive_percent, "agent_count": agent_count,
                "group_size": group_size, "run_index": int(run_seed.spawn_key[0]),
            },
            code_version="0.1.0",
        )
        write_trace(paths.trace, events)
        write_labels(paths.labels, labels)
        write_manifest(paths.manifest, manifest)
        directories.append(directory)
    return directories
