"""Features computed from a defender-visible ``Trace`` alone.

Every column is declared in ``AGENT_FEATURES``, ``PAIR_FEATURES`` or ``RUN_FEATURES`` with its
minimum visibility tier, a definition and, for pair and run features, the direction
(``HIGHER`` or ``LOWER``) in which values indicate coordination, and a family: ``GENERIC``
coordination features or ``AGGREGATION`` features aimed at privilege aggregation. A feature
whose tier is above ``trace.tier`` is omitted from the output. Every function takes ``until_tick`` and then sees only events with
``tick <= until_tick``.

``SCOPE_PAIR_FEATURES`` and ``SCOPE_RUN_FEATURES`` (family ``SCOPE``) also need a defender
``Context`` of a minimum level. ``pair_features`` and ``run_features`` return them only when a
``context`` for the same run is passed; with the default ``context=None`` every function, column
set and threshold set is exactly as without scope features.
"""

from .agent import agent_features
from .pair import pair_features
from .run import run_features
from .spec import (
    AGENT_FEATURES,
    AGGREGATION,
    EXPANSION_WINDOW,
    FAMILIES,
    GENERIC,
    HIGHER,
    LAGS,
    LOWER,
    PAIR_FEATURES,
    RUN_FEATURES,
    SCOPE,
    SCOPE_PAIR_FEATURES,
    SCOPE_RUN_FEATURES,
    SCOPE_THRESHOLDS,
    THRESHOLDS,
    TOP_K,
    FeatureSpec,
    feature_columns,
)

__all__ = [
    "AGENT_FEATURES",
    "AGGREGATION",
    "EXPANSION_WINDOW",
    "FAMILIES",
    "GENERIC",
    "HIGHER",
    "LAGS",
    "LOWER",
    "PAIR_FEATURES",
    "RUN_FEATURES",
    "SCOPE",
    "SCOPE_PAIR_FEATURES",
    "SCOPE_RUN_FEATURES",
    "SCOPE_THRESHOLDS",
    "THRESHOLDS",
    "TOP_K",
    "FeatureSpec",
    "agent_features",
    "feature_columns",
    "pair_features",
    "run_features",
]
