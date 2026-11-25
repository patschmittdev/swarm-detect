"""Detectors over feature matrices with labels supplied explicitly by the caller.

``RunDetector`` scores full runs and ``OnlineDetector`` scores prefixes at fixed checkpoints.
Both support fitted models and rules over credential sharing, file reads and task scope.
Their thresholds are split-conformal quantiles over held-out calibration controls.
``PairScorer`` attributes coordination to pairs and proposes connected components as groups.
"""

from .attribution import PairScorer, propose_groups
from .models import (
    COMPONENT_COLUMN,
    COMPONENT_RULE,
    DETECTOR_MODELS,
    FILES_RULE,
    FILES_RULE_COLUMN,
    RULE,
    RULE_COLUMN,
    RUN_MODELS,
    SCOPE_BREADTH_RULE,
    SCOPE_LOGISTIC,
    SCOPE_RULE,
    SCOPE_RULE_COLUMNS,
    SHARING_LOGISTIC,
    VOLUME_COLUMNS,
    RunDetector,
    volume_features,
)
from .online import CHECKPOINT_EVERY, OnlineDetector, checkpoints, first_detection_tick
from .threshold import conformal_threshold

__all__ = [
    "CHECKPOINT_EVERY",
    "COMPONENT_COLUMN",
    "COMPONENT_RULE",
    "DETECTOR_MODELS",
    "FILES_RULE",
    "FILES_RULE_COLUMN",
    "RULE",
    "RULE_COLUMN",
    "RUN_MODELS",
    "SCOPE_BREADTH_RULE",
    "SCOPE_LOGISTIC",
    "SCOPE_RULE",
    "SCOPE_RULE_COLUMNS",
    "SHARING_LOGISTIC",
    "VOLUME_COLUMNS",
    "OnlineDetector",
    "PairScorer",
    "RunDetector",
    "checkpoints",
    "conformal_threshold",
    "first_detection_tick",
    "propose_groups",
    "volume_features",
]
