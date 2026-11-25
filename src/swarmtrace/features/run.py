import math
from collections.abc import Mapping

import pandas as pd

from swarmtrace.trace.context import Context
from swarmtrace.trace.io import Trace

from .pair import pair_features
from .spec import (
    AGGREGATES,
    LOWER,
    PAIR_FEATURES,
    SCOPE_PAIR_FEATURES,
    SCOPE_THRESHOLDS,
    THRESHOLDS,
    TOP_K,
    available,
    context_available,
    feature_columns,
)


def run_features(
    trace: Trace,
    until_tick: int | None = None,
    top_k: int = TOP_K,
    thresholds: Mapping[str, float] | None = None,
    *,
    context: Context | None = None,
) -> pd.DataFrame:
    """Run-level aggregates of every available pair feature, one row indexed by ``run_id``.

    Each pair feature is aggregated toward its declared coordination direction: extreme value,
    mean of the ``top_k`` most extreme values, and count of pairs past the threshold (strictly
    above for HIGHER, at or below for LOWER). NaN pair values are skipped, never counted.
    ``thresholds`` overrides entries of ``THRESHOLDS`` and, with a ``context``,
    ``SCOPE_THRESHOLDS``, whose SCOPE aggregates then follow the others.
    """
    if top_k < 1:
        raise ValueError(f"top_k must be at least 1, got {top_k}")
    limits = {**THRESHOLDS, **SCOPE_THRESHOLDS, **(thresholds or {})}
    pairs = pair_features(trace, until_tick=until_tick, context=context)
    specs = PAIR_FEATURES if context is None else PAIR_FEATURES + tuple(
        spec for spec in SCOPE_PAIR_FEATURES if context_available(spec, context.level)
    )
    row: dict[str, float] = {}
    counts = set()
    for spec in specs:
        if not available(spec, trace.tier):
            continue
        lower = spec.direction == LOWER
        extreme, k_mean, count = (f"{spec.name}_{suffix}" for suffix in AGGREGATES[spec.direction])
        values = sorted(
            (float(value) for value in pairs[spec.name] if not math.isnan(value)),
            reverse=not lower,
        )
        top = values[:top_k]
        limit = limits[spec.name]
        row[extreme] = values[0] if values else math.nan
        row[k_mean] = sum(top) / len(top) if top else math.nan
        row[count] = sum((value <= limit) if lower else (value > limit) for value in values)
        counts.add(count)
    columns = list(feature_columns(
        "run", trace.tier, context=None if context is None else context.level
    ))
    frame = pd.DataFrame([row], columns=columns, index=pd.Index([trace.run_id], name="run_id"))
    return frame.astype(
        {column: "int64" if column in counts else "float64" for column in columns}
    )
