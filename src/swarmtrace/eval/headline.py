"""Compact views of existing measurements; this module never fits or scores a model."""

import math
from collections.abc import Mapping, Sequence
from pathlib import Path

from .harness import NOT_AVAILABLE, REPORTED_DETECTORS, MetricRow
from .report import split_context


def _value(row: MetricRow | None, *, rate: bool = False) -> str:
    if row is None:
        return "not computed"
    if row.note in NOT_AVAILABLE:
        return row.note
    count = f"{row.n} of {row.total}; " if rate else ""
    if math.isnan(row.value):
        return f"{count}undefined ({row.note})"
    interval = (f"[{row.low:.3f}, {row.high:.3f}]" if not math.isnan(row.low)
                else f"[no interval: {row.note}]")
    return f"{count}{row.value:.3f} {interval}"


def _detector(method: str) -> str:
    return "volume (family-independent)" if method == "volume" else method


def _detection_table(rows: Sequence[MetricRow]) -> list[str]:
    selected = {}
    for row in rows:
        if row.method in REPORTED_DETECTORS:
            selected.setdefault((row.split, row.tier, row.family, row.method), {})[row.metric] = row
    lines = [*split_context(rows),
             "| Split | Tier | Family | Detector | AUROC | "
             "Detection rate at calibrated threshold | FPR | "
             "Online coverage | Online FPR |",
             "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    metrics = ("auroc", "detection_rate", "false_positive_rate", "detection_coverage",
               "online_false_positive_rate")
    for (split, tier, family, method), measurements in selected.items():
        values = " | ".join(_value(measurements.get(metric), rate=metric != "auroc")
                            for metric in metrics)
        lines.append(f"| {split} | {tier} | {family} | {_detector(method)} | {values} |")
    return lines


def format_headline(
    rows: Sequence[MetricRow], controls: Sequence[Mapping[str, object]],
    negative: Sequence[Mapping[str, object]],
) -> str:
    """Render supplied metric/control objects, preserving their estimates and intervals."""
    by_run = [row for row in rows if row.split == "by run"]
    lines = ["# Headline measurements", "",
             "Rates show k of n and 95% Wilson intervals. AUROC intervals bootstrap runs. "
             "Full-trace detection rate counts flagged positive test runs; FPR counts "
             "flagged control test runs at the calibrated threshold. Online coverage and "
             "online FPR count runs crossing their separately calibrated online threshold. "
             "Volume is family-independent. Rule has no fitted parameters: its score is the "
             "number of agent pairs with at least one shared-credential login, thresholded by "
             "the same calibration; it is not available at V0 or without aggregation "
             "features.", "",
             "## By-run split", "", *_detection_table(by_run), ""]
    factors: dict[str, list[MetricRow]] = {}
    for row in rows:
        if row.split.startswith("held-out "):
            factor = row.split.removeprefix("held-out ").partition("=")[0]
            factors.setdefault(factor, []).append(row)
    for factor, selected in factors.items():
        lines += [f"## Held-out {factor}", "", *_detection_table(selected), ""]
    selected = [row for row in by_run if row.tier == "V1" and row.family == "aggregation"]
    lines += ["## V1 aggregation: offensive group size", "", *split_context(selected),
              "Size-specific detection rates use the same full-trace calibrated threshold "
              "and count positive test runs of that group size.", "",
              "| Detector | Size 2 | Size 3 | Size 5 |", "| --- | --- | --- | --- |"]
    for method in REPORTED_DETECTORS:
        metrics = {row.metric: row for row in selected if row.method == method}
        cells = " | ".join(_value(metrics.get(f"detection_rate_size_{size}"), rate=True)
                           for size in (2, 3, 5))
        lines.append(f"| {_detector(method)} | {cells} |")
    lines += ["", "## V1 aggregation: positives versus sharing controls", "",
              *split_context(selected),
              "Sharing controls contain at least one benign team assigned credential sharing, "
              "recorded by the simulator as benign_sharing_teams. This flag is label-side.", "",
              "| Detector | Positive test runs | Sharing controls | All test controls | "
              "Restricted AUROC |", "| --- | --- | --- | --- | --- |"]
    for method in REPORTED_DETECTORS:
        row = next((r for r in selected if r.method == method
                    and r.metric == "sharing_control_auroc"), None)
        if row is None or row.note.startswith("missing benign_sharing"):
            lines.append(f"| {_detector(method)} | unavailable | unavailable | unavailable | "
                         f"{_value(row)} |")
        else:
            total = row.split_counts[4] if row.split_counts else "not recorded"
            lines.append(f"| {_detector(method)} | {row.positive_runs} | {row.control_runs} | "
                         f"{total} | {_value(row)} |")
    lines += ["", "## Independent controls", "", *split_context(by_run),
              "Benign/loud runs are separate test sweeps; the fitting and calibration counts "
              "above refer to their main by-run models. BOTH V1 aggregation detectors must "
              "flag every loud run at the calibrated threshold and score it strictly above "
              "every calibration control with benign_sharing_teams == 0. Logistic must also "
              "beat every calibration control. Loud counts below require all applicable bars. "
              "Boosted's all-controls strict bar is non-gating; its measured outcome has "
              "a separate row in controls.md. The rule baseline has no gating bars; its "
              "rows are diagnostics. "
              "Other loud rows are diagnostics. Shuffled AUROC mean and SE are descriptive: "
              "no pass/fail criterion is applied to permutations of the same dataset.", ""]
    if controls:
        binding = [row for row in controls if row["tier"] == "V1"
                   and row["family"] == "aggregation" and row["mode"] == "full-trace"
                   and row["detector"] in ("logistic", "boosted")]
        status = ("passed" if len(binding) == 2 and all(
            row["loud_required_met"] == row["loud_runs"]
            and row["loud_runs"] > 0 for row in binding
        ) else "FAILED")
        lines += [
            f"Independent benign test: {controls[0]['benign_runs']} control / 0 positive; "
            f"independent loud test: 0 control / {controls[0]['loud_runs']} positive.", "",
            f"Binding loud gate: {status}.", "",
        ]
    lines += ["| Tier | Family | Detector | All-benign FPR | Loud meeting required bars | "
              "Shuffled AUROC mean (SE) | Permutations |",
              "| --- | --- | --- | --- | --- | --- | --- |"]
    shuffled = {(r["tier"], r["family"], r["method"]): r for r in negative}
    for row in controls:
        if row["mode"] != "full-trace":
            continue
        key = row["tier"], row["family"], row["detector"]
        perm = shuffled.get(key)
        if perm is None:
            summary = "not computed"
        elif isinstance(perm["auroc_mean"], str):
            summary = perm["auroc_mean"]
        else:
            summary = f"{perm['auroc_mean']:.3f} ({perm['auroc_se']:.3f})"
        repeats = perm["repeats"] if perm is not None else "not computed"
        lines.append(f"| {key[0]} | {key[1]} | {key[2]} | {row['benign_rate']} | "
                     f"{row['loud_required_rate']} | {summary} | {repeats} |")
    if negative:
        first = negative[0]
        lines += ["", f"Shuffled by-run splits: seed {first['seed']}; "
                  f"fitting {first['fitting_controls']} control / "
                  f"{first['fitting_positive']} positive; calibration "
                  f"{first['calibration_controls']} control / {first['calibration_positive']} "
                  f"positive; test {first['test_controls']} control / "
                  f"{first['test_positive']} positive (same counts each permutation)."]
    return "\n".join([*lines, ""])


def format_readme_headline(headline: str) -> str:
    """Select a block of at most 45 lines without recomputing any reported cell."""
    sections: dict[str, list[str]] = {}
    section = ""
    for line in headline.splitlines():
        if line.startswith("## "):
            section = line
            sections[section] = []
        elif section:
            sections[section].append(line)

    lines = []
    selected = ("| by run | V0 | generic |", "| by run | V1 | aggregation |",
                "| by run | V2 | all |")
    for title in ("## By-run split", "## V1 aggregation: offensive group size",
                  "## V1 aggregation: positives versus sharing controls"):
        body = sections[title]
        context = [line for line in body if line.startswith("Seed:")]
        table = [line for line in body if line.startswith("|")]
        if title == "## By-run split":
            table = [line for line in table
                     if line.startswith(("| Split |", "| --- |", *selected))]
        lines += [title, "", *context, "", *table, ""]

    controls = sections["## Independent controls"]
    lines += [line for line in controls
              if line.startswith(("Binding loud gate:", "Independent benign test:"))]
    lines.append("Full headline and held-out tables: [headline](data/headline.md). "
                 "Full reports: [V0](data/results-V0.md), [V1](data/results-V1.md), "
                 "[V2](data/results-V2.md), [controls](data/controls.md), "
                 "[shuffled labels](data/negative-control.md).")
    if len(lines) > 45:
        raise ValueError("README headline exceeds 45 lines")
    return "\n".join([*lines, ""])


def write_headline(
    rows: Sequence[MetricRow], controls: Sequence[Mapping[str, object]],
    negative: Sequence[Mapping[str, object]], out: Path,
) -> Path:
    path = out / "headline.md"
    path.write_text(format_headline(rows, controls, negative), encoding="utf-8", newline="\n")
    return path
