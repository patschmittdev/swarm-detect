from collections.abc import Sequence
from itertools import product
from pathlib import Path

import numpy as np

from .runner import (
    CHANNELS,
    COORDINATED_GROUP_COUNTS,
    GROUP_SIZES,
    TOPOLOGIES,
    Condition,
    run_one,
)


def condition_grid(
    *, group_sizes: Sequence[int] = GROUP_SIZES,
    coordinated_groups: Sequence[int] = COORDINATED_GROUP_COUNTS,
    channels: Sequence[str] = CHANNELS, topologies: Sequence[str] = TOPOLOGIES,
    n_ticks: int = 160,
    benign_credential_sharing: int = 10, scope: str = "off",
) -> tuple[Condition, ...]:
    """The 72 scripted, no-evasion conditions, or an explicitly selected subgrid."""
    axes = (group_sizes, coordinated_groups, channels, topologies)
    if any(not axis or len(set(axis)) != len(axis) for axis in axes):
        raise ValueError("grid axes must be nonempty and contain no duplicates")
    return tuple(Condition(channel, topology, size, groups, n_ticks, benign_credential_sharing,
                           scope=scope)
                 for size, groups, channel, topology in product(*axes))


def run_sweep(
    out_dir: str | Path, seed: int, *, runs_per_condition: int = 1,
    conditions: Sequence[Condition] | None = None, capture_authorization: bool = False,
) -> list[Path]:
    """Run independent seeded replicates into opaque, deterministic subdirectories."""
    if type(seed) is not int or seed < 0:
        raise ValueError("seed must be a non-negative integer")
    if type(runs_per_condition) is not int or runs_per_condition < 1:
        raise ValueError("runs_per_condition must be a positive integer")
    grid = condition_grid() if conditions is None else tuple(conditions)
    if not grid or any(not isinstance(condition, Condition) for condition in grid):
        raise ValueError("conditions must contain at least one Condition")
    children = np.random.SeedSequence(seed).spawn(len(grid) * runs_per_condition)
    paths: list[Path] = []
    options = {"capture_authorization": True} if capture_authorization else {}
    for condition in grid:
        for _ in range(runs_per_condition):
            child = children[len(paths)]
            run_seed = int(child.generate_state(1, dtype=np.uint64)[0])
            directory = Path(out_dir) / np.random.default_rng(child).bytes(8).hex()
            paths.append(run_one(condition, run_seed, directory, **options))
    return paths
