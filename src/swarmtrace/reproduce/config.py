import os
from dataclasses import dataclass, replace

import numpy as np

from swarmtrace.sim.runner import Condition
from swarmtrace.sim.sweep import condition_grid


@dataclass(frozen=True)
class ReproduceConfig:
    seed: int = 20261120
    workers: int = min(4, os.cpu_count() or 1)
    runs_per_condition: int = 2
    control_repeats: int = 8
    n_ticks: int = 160
    checkpoint_every: int = 8
    n_bootstrap: int = 200
    shuffle_repeats: int = 20
    sample_runs: int = 6
    hold_out: tuple[str, ...] = ("channel", "topology")
    conditions: tuple[Condition, ...] | None = None

    def __post_init__(self) -> None:
        if type(self.seed) is not int or self.seed < 0:
            raise ValueError("seed must be a non-negative integer")
        for name in ("workers", "runs_per_condition", "control_repeats", "n_ticks",
                     "checkpoint_every", "n_bootstrap", "shuffle_repeats", "sample_runs"):
            value = getattr(self, name)
            if type(value) is not int or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        if self.conditions is not None and not self.conditions:
            raise ValueError("conditions must be nonempty")


@dataclass(frozen=True)
class RunJob:
    dataset: str
    directory: str
    seed: int
    condition: Condition


def make_jobs(config: ReproduceConfig) -> tuple[RunJob, ...]:
    """Spawn all RNG streams before dispatch, independent of process count and timing."""
    grid = config.conditions or condition_grid(n_ticks=config.n_ticks)
    cells = [("main", replace(condition, n_ticks=config.n_ticks))
             for condition in grid
             for _ in range(config.runs_per_condition *
                            (config.control_repeats if condition.offensive_group_size == 0 else 1))]
    benign = tuple(dict.fromkeys(replace(condition, offensive_group_size=0, loud_reuses=0,
                                         n_ticks=config.n_ticks) for condition in grid))
    cells.extend(("benign", condition) for condition in benign)
    channels = sorted({condition.channel for condition in grid if condition.channel is not None})
    cells.extend(("loud", Condition(channel, "peer", 5, 1, config.n_ticks,
                                    loud_reuses=32)) for channel in channels)
    if not channels:
        raise ValueError("reproduce conditions must name their channels")
    streams = np.random.SeedSequence(config.seed).spawn(len(cells))
    return tuple(RunJob(dataset, np.random.default_rng(stream).bytes(8).hex(),
                        int(stream.generate_state(1, dtype=np.uint64)[0]), condition)
                 for (dataset, condition), stream in zip(cells, streams, strict=True))
