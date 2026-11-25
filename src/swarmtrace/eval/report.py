import math
from collections.abc import Sequence
from pathlib import Path

from swarmtrace.detect import CHECKPOINT_EVERY

from .harness import (
    ATTRIBUTION_METRICS,
    FULL_TRACE_METRICS,
    GROUP_METRICS,
    NOT_AVAILABLE,
    ONLINE_METRICS,
    ROLE_CATEGORIES,
    ROLE_METRICS,
    SPLIT_METRICS,
    SPLIT_ROW,
    THRESHOLD_METRICS,
    MetricRow,
)
from .splits import CALIBRATION_FRACTION, HELD_OUT, IN_DISTRIBUTION

TITLES = {
    "auroc": "AUROC",
    "detection_rate": "Detection rate at calibrated threshold",
    "false_positive_rate": "FPR on controls",
    "online_false_positive_rate": "Online FPR on controls",
    "detection_coverage": "Detection coverage",
    "detected_strictly_before_completion": "Detected strictly before completion",
    "detected_at_completion": "Detected at completion",
    "time_to_detection": "Time to detection (conditional on detection)",
    "attribution_precision": "Precision",
    "attribution_recall": "Recall",
    "group_jaccard": "Mean Jaccard overlap of proposed group",
    "group_exact": "Reconstructed exactly",
    **ROLE_CATEGORIES,
}
DEGENERATE_NOUNS = {
    "attribution_precision": "precision",
    "attribution_recall": "recall",
    "group_jaccard": "mean Jaccard overlap",
    "group_exact": "exact-reconstruction rate",
}
"""Run-bootstrap metrics whose collapsed intervals are printed with a qualification."""
SECTIONS = ((IN_DISTRIBUTION, "In-distribution"), (HELD_OUT, "Held-out"))
NOTES = (
    "Detection rates use 95% Wilson intervals, with k of n runs. AUROC, means and attribution "
    "use percentile bootstrap intervals over runs and show valid/requested resamples. "
    "Attribution precision and recall count agents (k of n agents), but agents in one run are "
    "not independent, so their intervals resample whole runs, not agents.",
    "",
    "Resampling: test runs are resampled with replacement within strata, each stratum to its "
    "own size. AUROC is stratified by positive and control runs; time to detection resamples "
    "detected runs with an objective tick above 0. Bootstrap treats runs as independent even "
    "though default control conditions each have 16 replicates (2 rpc x 8 repeats). Its "
    "interval is withheld when a stratum has fewer than 2 runs or fewer than 90% of requested "
    "resamples give a defined value.",
    "",
    "Calibration: each split's training runs are divided by run, stratified by class, into a "
    f"fitting set and a calibration set ({CALIBRATION_FRACTION:.0%} of each class). Every "
    "model is fitted on the fitting set, and its threshold is the split-conformal quantile of "
    "its own scores on the calibration control runs (the ceil((n + 1)(1 - alpha))-th smallest "
    "of n, alpha = 0.05; +inf, never firing, when n is too small). Run counts per split are in "
    "the Calibration table.",
    "",
    "Full-trace detection uses a model fitted on complete fitting-set traces. Detection rate "
    "is the fraction of positive test runs scoring above its calibrated threshold; FPR is "
    "the corresponding fraction of control test runs.",
    "",
    "Online detection uses a separate model fitted on prefix features at checkpoints (every "
    f"{CHECKPOINT_EVERY} ticks plus the final tick), with a run-level threshold calibrated on "
    "each calibration control run's maximum checkpoint score. Online FPR is the fraction "
    "of control test runs crossing it at any checkpoint. Coverage is the fraction of positive "
    "test runs crossing it at any checkpoint. Among positive runs with an objective tick above "
    "0, Detected strictly before completion is the fraction whose first crossing checkpoint is "
    "before that tick, and Detected at completion the fraction whose first crossing checkpoint "
    "is that tick; an undetected run counts in neither. Time to detection is the mean "
    "first-crossing checkpoint tick divided by the objective tick, conditional on detection; "
    "it is quantized to the checkpoint cadence.",
    "",
    "Attribution rows: for each detector, groups proposed by the pair scorer count only in runs "
    "that detector flags; offensive agents in unflagged runs are false negatives. The pairs "
    "row is the pair scorer on every test run, a diagnostic not gated by any detector. "
    "Attribution precision and recall resample test runs within positive and control strata; "
    "group reconstruction resamples positive test runs.",
    "",
    "Group reconstruction, per positive test run: the proposed group is the connected component "
    "of flagged pairs with the most offensive members (ties to the larger Jaccard overlap, then "
    "to the first sorted agent ids). It is empty, with Jaccard overlap 0, when the detector does "
    "not flag the run or no pair is flagged. Reconstructed exactly means the proposed group "
    "equals the offensive group.",
    "",
    "Wrongly named agents: non-offensive agents in any proposed group, counted by role, out of "
    "all wrongly named agents (precision's denominator minus its numerator). Roles come from "
    "the labels. The labels do not say which benign team shares credentials, only how many "
    "teams in a run do (benign_sharing_teams). A team is observed sharing when two of its "
    "members have a shared-credential login (shared_credential_logins in the V1 pair table); "
    "a non-sharing team cannot produce one. This evidence is always taken at V1, whatever the "
    "tier or feature family of the table, because the role table describes ground truth, not "
    "what the defender sees; it stays on the evaluation side. A team is also sharing when "
    "every benign team in its run is declared sharing. When the sharing teams found number "
    "exactly the declared count, the run's other benign teams are non-sharing; otherwise they "
    "are counted as sharing unresolved, never guessed. No sharing metadata means the run's "
    "condition lacks benign_sharing_teams.",
    "",
    "A degenerate bootstrap interval is one where every valid resample gave the same value, "
    "so both ends are equal; it is printed with that qualification, because it reflects the "
    "few runs that carry the count, not certainty about the population rate.",
    "",
    "Rule: a baseline with no fitted parameters. Its score for a run is the number of agent "
    "pairs with at least one shared-credential login (shared_credential_logins_n_above, a V1 "
    "aggregation feature). Its full-trace and online thresholds are calibrated like the fitted "
    "detectors', and a run is flagged when its count is strictly above the threshold, so a "
    "control tied at the threshold is not flagged. Online, it is the same count on each prefix. "
    "Its attribution rows gate the pair scorer by its own flags. It is not available at V0 or "
    "without aggregation features.",
)


def _degenerate(row: MetricRow) -> str:
    """Qualified text for a bootstrap interval whose ends are equal."""
    noun, end = DEGENERATE_NOUNS[row.metric], row.low
    if end == 0:
        why = f"all valid resamples were zero; does not establish zero population {noun}"
    elif end == 1:
        why = f"all valid resamples were one; does not establish a population {noun} of one"
    else:
        why = (f"all valid resamples were equal; does not establish a population {noun} of "
               f"exactly {end:.3f}")
    return f"degenerate bootstrap interval [{row.low:.3f}, {row.high:.3f}]: {why}"


def _cell(row: MetricRow | None) -> str:
    if row is None:
        return "not computed"
    if row.note in NOT_AVAILABLE:
        return row.note
    if row.interval == "count":
        return f"undefined ({row.note})" if math.isnan(row.value) else str(row.n)
    counts = f"{row.n} of {row.total} {row.unit}"
    counts += ("; Wilson" if row.interval == "Wilson"
               else f"; {row.valid}/{row.requested} resamples")
    if math.isnan(row.value):
        note = f"; {row.note}" if row.note else ""
        return f"undefined ({counts}{note})"
    if (row.interval == "bootstrap" and row.metric in DEGENERATE_NOUNS
            and not math.isnan(row.low) and row.low == row.high):
        return f"{row.value:.3f} ({counts}; {_degenerate(row)})"
    if math.isnan(row.low):
        interval = f" [no interval: {row.note}]"
    else:
        interval = f" [{row.low:.3f}, {row.high:.3f}]"
    return f"{row.value:.3f}{interval} ({counts})"


def split_context(rows: Sequence[MetricRow]) -> list[str]:
    """Captions shared by full and compact tables, with class counts from the actual fit."""
    contexts = {}
    for row in rows:
        contexts.setdefault((row.seed, row.split), row.split_counts)
    lines = []
    for (seed, split), counts in contexts.items():
        if len(counts) != 6:
            lines.append(f"Seed: {seed}; split: {split}; class counts not recorded.")
            continue
        fit_c, fit_p, cal_c, cal_p, test_c, test_p = counts
        lines.append(f"Seed: {seed}; split: {split}; fitting {fit_c} control / {fit_p} positive; "
                     f"calibration {cal_c} control / {cal_p} positive; "
                     f"test {test_c} control / {test_p} positive.")
    return [*lines, ""] if lines else []


def _table(rows: Sequence[MetricRow], metrics: tuple[str, ...], label: str) -> list[str]:
    cells: dict[tuple[str, str], dict[str, MetricRow]] = {}
    for row in rows:
        if row.metric in metrics:
            cells.setdefault((row.split, row.method), {})[row.metric] = row
    lines = [
        *split_context(rows),
        f"| Split | {label} | " + " | ".join(TITLES[metric] for metric in metrics) + " |",
        "| --- | --- | " + " | ".join("---" for _ in metrics) + " |",
    ]
    for (split, method), by_metric in cells.items():
        values = " | ".join(_cell(by_metric.get(metric)) for metric in metrics)
        label = "volume (family-independent)" if method == "volume" else method
        lines.append(f"| {split} | {label} | {values} |")
    return lines


def _roles(rows: Sequence[MetricRow]) -> list[str]:
    cells: dict[tuple[str, str], dict[str, MetricRow]] = {}
    for row in rows:
        if row.metric in ROLE_METRICS:
            cells.setdefault((row.split, row.method), {})[row.metric] = row
    lines = [
        *split_context(rows),
        "| Split | Method | Wrongly named | "
        + " | ".join(TITLES[metric] for metric in ROLE_METRICS) + " |",
        "| --- | --- | --- | " + " | ".join("---" for _ in ROLE_METRICS) + " |",
    ]
    for (split, method), by_metric in cells.items():
        first = next(iter(by_metric.values()))
        total = (first.note if first.note in NOT_AVAILABLE
                 else f"undefined ({first.note})" if math.isnan(first.value)
                 else f"{first.total} agents")
        values = " | ".join(_cell(by_metric.get(metric)) for metric in ROLE_METRICS)
        label = "volume (family-independent)" if method == "volume" else method
        lines.append(f"| {split} | {label} | {total} | {values} |")
    return lines


def _calibration(rows: Sequence[MetricRow]) -> list[str]:
    splits: dict[str, dict[str, MetricRow]] = {}
    never: dict[str, list[str]] = {}
    for row in rows:
        if row.method == SPLIT_ROW and row.metric in SPLIT_METRICS:
            splits.setdefault(row.split, {})[row.metric] = row
        elif row.metric in THRESHOLD_METRICS and math.isinf(row.value):
            suffix = " (online)" if row.metric == "online_threshold" else ""
            never.setdefault(row.split, []).append(f"{row.method}{suffix}")
    lines = [
        *split_context(rows),
        "| Split | Fitting runs | Calibration runs | Calibration controls | Test runs "
        "| Never fires (calibration set too small) |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for split, counts in splits.items():
        values = " | ".join(
            str(counts[metric].n) if metric in counts else "not computed"
            for metric in SPLIT_METRICS
        )
        lines.append(f"| {split} | {values} | {', '.join(never.get(split, [])) or 'none'} |")
    return lines


def format_tier(rows: Sequence[MetricRow], tier: str) -> str:
    """Markdown results for one tier: in-distribution and held-out rows in separate sections."""
    selected = [row for row in rows if row.tier == tier]
    cadence = selected[0].checkpoint_every if selected else CHECKPOINT_EVERY
    notes = [note.replace(f"{CHECKPOINT_EVERY} ticks plus", f"{cadence} ticks plus")
             for note in NOTES]
    lines = [
        f"# Results, tier {tier}",
        "",
        *notes,
        "",
    ]
    for kind, heading in SECTIONS:
        section = [row for row in selected if row.kind == kind]
        lines += [f"## {heading}", ""]
        if not section:
            lines += ["No splits of this kind were run.", ""]
            continue
        first_family = section[0].family
        lines += ["### Calibration", "",
                  *_calibration([row for row in section if row.family == first_family]), ""]
        for family in dict.fromkeys(row.family for row in section):
            subset = [row for row in section if row.family == family]
            lines += [f"### Features: {family}", "",
                      "Volume is a family-independent reference; its columns do not change.", ""]
            lines += ["### Full-trace detection", "",
                      *_table(subset, FULL_TRACE_METRICS, "Detector"), ""]
            lines += ["### Online detection", "", *_table(subset, ONLINE_METRICS, "Detector"), ""]
            lines += ["### Attribution", "", *_table(subset, ATTRIBUTION_METRICS, "Method"), ""]
            lines += ["### Group reconstruction", "",
                      *_table(subset, GROUP_METRICS, "Method"), ""]
            lines += ["### Wrongly named agents", "", *_roles(subset), ""]
    return "\n".join(lines)


def write_report(rows: Sequence[MetricRow], out_dir: str | Path) -> list[Path]:
    """Write ``results-<tier>.md`` for each tier present in ``rows``, in order of appearance."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    for tier in dict.fromkeys(row.tier for row in rows):
        path = out / f"results-{tier}.md"
        path.write_text(format_tier(rows, tier), encoding="utf-8", newline="\n")
        paths.append(path)
    return paths
