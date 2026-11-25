"""Evaluation: the only package that reads ``labels.json`` and ``manifest.json``.

Loads run directories, splits by run and by held-out condition, fits detectors on training runs
only, and reports detection AUROC, false-positive rate on control runs, per-agent attribution
precision and recall, and time to detection, each with a bootstrap interval over runs.
"""

from .data import RunRecord, TierData, build_tier_data, feature_table, load_runs, pair_labels
from .harness import (
    ATTRIBUTION,
    DETECTORS,
    REPORTED_DETECTORS,
    EvalConfig,
    MetricRow,
    SplitResult,
    evaluate,
    evaluate_split,
)
from .metrics import (
    Estimate,
    attribution_counts,
    auroc,
    bootstrap,
    conditional_time_to_detection,
    detected_at_completion,
    detected_before_completion,
    detected_strictly_before_completion,
    detection_coverage,
    detection_fraction,
    false_positive_rate,
)
from .splits import HELD_OUT, IN_DISTRIBUTION, Split, held_out_splits, split_by_run

__all__ = [
    "ATTRIBUTION",
    "DETECTORS",
    "HELD_OUT",
    "IN_DISTRIBUTION",
    "REPORTED_DETECTORS",
    "Estimate",
    "EvalConfig",
    "MetricRow",
    "RunRecord",
    "Split",
    "SplitResult",
    "TierData",
    "attribution_counts",
    "auroc",
    "bootstrap",
    "build_tier_data",
    "conditional_time_to_detection",
    "detected_at_completion",
    "detected_before_completion",
    "detected_strictly_before_completion",
    "detection_coverage",
    "detection_fraction",
    "evaluate",
    "evaluate_split",
    "false_positive_rate",
    "feature_table",
    "held_out_splits",
    "load_runs",
    "pair_labels",
    "split_by_run",
]
