"""Recorded-data split sensitivity, separate from the timed reproduction pipeline."""

from collections.abc import Mapping
from pathlib import Path

import numpy as np

from swarmtrace.detect import RULE, RunDetector

from .data import TierData
from .harness import (
    DETECTORS,
    REPORTED_DETECTORS,
    SEED_INDEX,
    SEED_KEY,
    EvalConfig,
    child_seed,
    family_data,
    rule_unavailable,
)
from .metrics import auroc
from .recorded import is_recorded, load_recorded, recorded_root
from .splits import CALIBRATION_FRACTION, calibration_split, split_by_run


def by_run_partitions(
    labels: Mapping[str, bool], test_fraction: float, seed: int, repeat: int = 0,
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    """Fitting, calibration and test runs for the published by-run split or a repeat."""
    ids = sorted(labels)
    split_seed = child_seed(seed, 0) if repeat == 0 else child_seed(seed, 80, repeat)
    split = split_by_run(ids, [labels[run] for run in ids], test_fraction, split_seed)
    fitting, calibration = calibration_split(
        split.train, [labels[run] for run in split.train], CALIBRATION_FRACTION,
        child_seed(child_seed(seed, 1, 0), SEED_KEY + 1, 0),
    )
    return fitting, calibration, split.test


def split_stability(
    data: TierData, config: EvalConfig, n_seeds: int = 20,
) -> list[dict[str, str | int | float]]:
    """Vary only by-run split assignment; retain the reported fit/calibration RNG seeds."""
    if n_seeds < 2:
        raise ValueError("split stability needs at least two split seeds")
    labels = {run: record.positive for run, record in data.records.items()}
    scores: dict[tuple[str, str], list[float]] = {
        (family, method): [] for family in config.families for method in REPORTED_DETECTORS
    }
    matrices = {family: family_data(data, family).runs for family in config.families}
    unavailable = {family: rule_unavailable(matrices[family].columns, data.tier)
                   for family in config.families}
    fit_seed = child_seed(config.seed, 1, 0)
    counts = {}
    for repeat in range(n_seeds):
        fitting, calibration, test_ids = by_run_partitions(
            labels, config.test_fraction, config.seed, repeat)
        for name, runs in (("fitting", fitting), ("calibration", calibration),
                           ("test", test_ids)):
            counts[f"{name}_controls"] = sum(not data.records[run].positive for run in runs)
            counts[f"{name}_positive"] = sum(data.records[run].positive for run in runs)
        y_fit = np.array([data.records[run].positive for run in fitting], dtype=bool)
        y_test = np.array([labels[run] for run in test_ids], dtype=bool)
        volume = None
        for family in config.families:
            for method in REPORTED_DETECTORS:
                if method == RULE:
                    if unavailable[family] is None:
                        rule = RunDetector(RULE, child_seed(fit_seed, SEED_INDEX[RULE], 0))
                        rule.fit(matrices[family].loc[list(fitting)], y_fit)
                        test = matrices[family].loc[list(test_ids)]
                        scores[family, method].append(auroc(y_test, rule.score(test)))
                    continue
                index = DETECTORS.index(method)
                if method == "volume" and volume is not None:
                    scores[family, method].append(volume)
                    continue
                matrix = data.volume if method == "volume" else matrices[family]
                detector = RunDetector("boosted" if method == "boosted" else "logistic",
                                       child_seed(fit_seed, index, 0), config.max_fpr)
                detector.fit(matrix.loc[list(fitting)], y_fit)
                value = auroc(y_test, detector.score(matrix.loc[list(test_ids)]))
                scores[family, method].append(value)
                if method == "volume":
                    volume = value
    def summary(family: str, method: str, values: list[float]) -> dict[str, str | float]:
        if method == RULE and unavailable[family] is not None:
            return dict.fromkeys(("single_auroc", "auroc_mean", "auroc_std"), unavailable[family])
        return {"single_auroc": values[0], "auroc_mean": float(np.mean(values)),
                "auroc_std": float(np.std(values, ddof=1))}

    return [{"seed": config.seed, "split": "by run", "tier": data.tier.value,
             "family": family,
             "detector": "volume (family-independent)" if method == "volume" else method,
             "split_seeds": n_seeds, **summary(family, method, values),
             **counts} for (family, method), values in scores.items()]


def write_split_stability(root: Path, out: Path, config: EvalConfig) -> Path:
    """Only full-trace fits, with neither online extraction/fitting nor bootstrap."""
    root = recorded_root(root)
    if not is_recorded(root):
        raise ValueError("--split-stability requires recorded feature tables")
    rows = []
    for tier in config.tiers:
        rows.extend(split_stability(load_recorded(root, tier), config))
    columns = tuple(rows[0])
    lines = ["# Split stability", "",
             "20 different by-run split seeds on the same recorded runs. The first uses "
             "child_seed(seed, 0), the reported split; the other 19 use "
             "child_seed(seed, 80, i), i=1..19. Fit and calibration seeds and fractions are "
             "unchanged. The single value uses the exact reported full-trace fitting recipe. "
             "SD is the sample standard deviation across splits, not an uncertainty interval. "
             "No online model or bootstrap is run. Class counts are identical across splits. "
             "--workers is ignored for recorded datasets.", "",
             "| " + " | ".join(columns) + " |", "| " + " | ".join("---" for _ in columns) + " |"]
    for row in rows:
        values = [f"{row[key]:.6f}" if isinstance(row[key], float) else str(row[key])
                  for key in columns]
        lines.append("| " + " | ".join(values) + " |")
    out.mkdir(parents=True, exist_ok=True)
    path = out / "split-stability.md"
    path.write_text("\n".join([*lines, ""]), encoding="utf-8", newline="\n")
    return path
