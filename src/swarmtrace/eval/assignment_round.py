"""Paired decisions and observed workflow support for the assignment-local study."""

from pathlib import Path

import pandas as pd

from swarmtrace.reproduce.grant_policy import _upper_fpr

from .rounds import MINIMUM_GAIN, _budget_flags, _paired_grid, _summary, benchmark_round
from .scope import MAX_FPR

FAMILIES = ("record_check", "clerical_handoff")
MIN_ONE_FILE = 540
COUNT_COLUMNS = (
    "shared_verified_documents", "shared_reads_before_component_end",
    "office_reads_before_native_end", "office_tickets", "exercised_office_tickets",
    "assignment_count", "unknown_reads", "missing_decisions",
)
FLAG_COLUMNS = ("fallback", "no_safe_interleave")


def _observations(path: Path, arms: tuple[str, ...], reference: str, candidate: str):
    """Align run-level evidence and all rankings to the same validated pair and labels."""
    paired = _paired_grid(path, "scope", reference, candidate)
    columns = ["family", *COUNT_COLUMNS, *FLAG_COLUMNS]
    raw = pd.read_csv(path, usecols=["task", "detector", "score", "run_id", *columns],
                      dtype=str, keep_default_na=False)
    rows = raw.loc[raw.task.eq("scope") & raw.detector.isin(arms)].copy()
    if rows.family.nunique() != 1 or rows.family.iloc[0] not in FAMILIES:
        raise ValueError(f"{path} must name one planned workflow family per grid")
    for column in COUNT_COLUMNS:
        if not rows[column].str.fullmatch(r"[0-9]+").all():
            raise ValueError(f"{path} needs nonnegative integer counts for {column}")
        rows[column] = pd.to_numeric(rows[column], errors="raise")
    for column in FLAG_COLUMNS:
        flags = rows[column].str.lower().map({"true": True, "false": False, "1": True, "0": False})
        if flags.isna().any():
            raise ValueError(f"{path} has invalid {column} flags")
        rows[column] = flags
    if (rows.exercised_office_tickets > rows.office_tickets).any():
        raise ValueError(f"{path} has more exercised office tickets than issued tickets")
    if (rows.missing_decisions > rows.unknown_reads).any():
        raise ValueError(f"{path} has more missing decisions than unknown reads")
    if rows.groupby("run_id", sort=False)[columns].nunique().gt(1).any().any():
        raise ValueError(f"{path} has inconsistent workflow support across detectors for one run")
    metadata = rows.drop_duplicates("run_id").set_index("run_id")[columns]
    # Python's float parser preserves the one-ULP comparisons used by benchmark_round.
    rows["score"] = rows.score.map(float)
    scores = rows.pivot(index="run_id", columns="detector", values="score")
    return paired.join(metadata), scores.loc[paired.index, list(arms)]


def _support(family: str, run_class: str, rows: pd.DataFrame) -> dict:
    result = dict(
        family=family, run_class=run_class, runs=len(rows),
        fallback_runs=int(rows.fallback.sum()),
        no_safe_interleave_runs=int(rows.no_safe_interleave.sum()),
        empty_assignment_runs=int(rows.assignment_count.eq(0).sum()),
        runs_with_shared_documents=int(rows.shared_verified_documents.gt(0).sum()),
        runs_with_shared_read_before_component_end=int(rows.shared_reads_before_component_end.gt(0).sum()),
        runs_with_office_read_before_native_end=int(rows.office_reads_before_native_end.gt(0).sum()),
        runs_with_unknown_reads=int(rows.unknown_reads.gt(0).sum()),
        runs_with_missing_decisions=int(rows.missing_decisions.gt(0).sum()),
    )
    for column in COUNT_COLUMNS:
        result[column] = int(rows[column].sum())
    for column in ("office_tickets", "exercised_office_tickets", "assignment_count"):
        result[f"{column}_min"] = int(rows[column].min()) if len(rows) else None
        result[f"{column}_max"] = int(rows[column].max()) if len(rows) else None
    return result


def _family_summary(family: str, rows: pd.DataFrame, candidate: str, reference: str) -> dict:
    summary = _summary(rows, "scope", MINIMUM_GAIN["scope"])
    hard = rows.hard_control
    new = rows.candidate_score > rows.candidate_threshold
    old = rows.reference_score > rows.reference_threshold
    for arm in ("reference", "candidate"):
        summary[f"{arm}_fpr_upper"] = (
            _upper_fpr(summary[f"{arm}_false_positives"], summary["controls"])
            if summary["controls"] else None)
    return dict(
        family=family, reference=reference, candidate=candidate, **summary,
        hard_false_positives_added=int((hard & new & ~old).sum()),
        hard_false_positives_removed=int((hard & old & ~new).sum()),
    )


def _budgets(family: str, rows: pd.DataFrame, scores: pd.DataFrame) -> list[dict]:
    positive = rows.positive.to_numpy()
    small = rows.small_positive.to_numpy()
    hard = rows.hard_control.to_numpy()
    controls = int((~positive).sum())
    counts = dict(controls=controls, positives=int(positive.sum()),
                  small_positives=int(small.sum()), hard_controls=int(hard.sum()))
    result = []
    for arm, values in scores.loc[rows.index].items():
        for percent in (1, 2, 5):
            budget = controls * percent // 100
            ranked = _budget_flags(values.to_numpy(), positive, budget) if controls else None
            result.append(dict(
                family=family, detector=arm, budget_fraction=percent / 100, **counts,
                false_alert_budget=budget,
                false_positives=int(ranked[~positive].sum()) if controls else None,
                true_positives=int(ranked[positive].sum()) if controls else None,
                small_true_positives=int(ranked[small].sum()) if controls else None,
                hard_false_positives=int(ranked[hard].sum()) if controls else None,
            ))
    return result


def report_assignment_round(
    folder: Path, grid_files: list[Path], *, candidate: str, reference: str,
    alternatives: tuple[str, ...], primary: bool,
) -> dict:
    """Write frozen-cutoff, retrospective ranking, and workflow-coverage summaries.

    Each arm's retrospective cutoff is computed within the named family or across the
    full pooled population. Only the comparison with the incumbent on the primary view
    determines qualification or contributes a round to the stopping rule.
    """
    arms = (candidate, reference, *alternatives)
    if len(arms) != len(set(arms)) or not all(isinstance(a, str) and a for a in arms):
        raise ValueError("assignment reporting requires distinct, named detector arms")
    cards = [benchmark_round(grid_files, "scope", arm, candidate) for arm in arms[1:]]
    card = pd.concat(cards, ignore_index=True)
    card["source"] = card.source.replace({str(p): p.name for p in grid_files})
    observations = [_observations(path, arms, reference, candidate) for path in grid_files]
    rows = pd.concat([pair for pair, _ in observations])
    scores = pd.concat([rankings for _, rankings in observations])
    family_rows, support_rows, budget_rows = [], [], []
    for family in (*FAMILIES, "pooled"):
        sample = rows if family == "pooled" else rows.loc[rows.family == family]
        if family != "pooled" and not sample.empty:
            family_rows.append(_family_summary(family, sample, candidate, reference))
        for run_class, subset in (("positive", sample[sample.positive]),
                                  ("control", sample[~sample.positive]), ("all", sample)):
            support_rows.append(_support(family, run_class, subset))
        budget_rows.extend(_budgets(family, sample, scores))
    family_results = pd.DataFrame(family_rows)
    support = pd.DataFrame(support_rows)
    pooled = card.population.eq("pooled")
    incumbent = card.reference.eq(reference)
    result = card.loc[pooled & incumbent].iloc[0]
    grids = card.loc[~pooled & incumbent]
    upper = _upper_fpr(int(result.candidate_false_positives), int(result.controls)) if result.controls else None
    shared = support.loc[support.family.isin(FAMILIES) & support.run_class.ne("all")]
    shared_in_each_class = bool(shared.runs_with_shared_documents.gt(0).all())
    families_present = len(family_results) == len(FAMILIES)
    family_data = bool(families_present and family_results.primary_positives.gt(0).all()
                       and family_results.controls.gt(0).all())
    no_family_loss = bool(family_data and family_results.primary_gained.ge(family_results.primary_lost).all())
    within_family_budgets = bool(family_data and family_results.candidate_false_positives.le(
        family_results.false_alert_budget).all())
    enough_data = bool(family_data and result.primary_positives >= MIN_ONE_FILE
                       and result.evidence != "insufficient_data")
    bound_met = upper is not None and upper <= MAX_FPR
    evidence = result.evidence
    if not primary:
        evidence = "descriptive_transfer"
    elif not enough_data:
        evidence = "insufficient_data"
    elif not shared_in_each_class:
        evidence = "insufficient_feature_support"
    elif result.evidence == "over_budget":
        evidence = "over_budget"
    elif not (no_family_loss and within_family_budgets):
        evidence = "failed_family_guardrails"
    elif not bound_met:
        evidence = "insufficient_fpr_confidence"
    elif result.evidence == "promising":
        evidence = "qualified_local_profile"
    card["round_evidence"] = ""
    card.loc[pooled & ~incumbent, "round_evidence"] = "descriptive_comparator"
    card.loc[pooled & incumbent, "round_evidence"] = evidence
    folder.mkdir(parents=True, exist_ok=True)
    for name, frame in (("scorecard", card), ("families", family_results), ("support", support),
                        ("review-budgets", pd.DataFrame(budget_rows))):
        frame.to_csv(folder / f"{name}.csv", index=False, lineterminator="\n")
    return {
        "candidate": candidate, "reference": reference, "primary": primary,
        "paired_evidence": result.evidence, "round_evidence": evidence,
        "qualified_local_profile": evidence == "qualified_local_profile",
        "counts_toward_diminishing_returns": evidence == "below_minimum",
        "candidate_fpr_upper": upper, "pooled_fpr_bound_met": bound_met,
        "shared_documents_in_both_classes_of_each_family": shared_in_each_class,
        "no_family_net_one_file_loss": no_family_loss,
        "all_families_within_false_alert_budget": within_family_budgets,
        "required_data_present": enough_data, "run_count": len(rows),
        "one_file_runs": int(result.primary_positives), "controls": int(result.controls),
        "primary_gained": int(result.primary_gained), "primary_lost": int(result.primary_lost),
        "grids_gaining": int(grids.primary_recall_delta.gt(0).sum()),
        "grids_losing": int(grids.primary_recall_delta.lt(0).sum()),
        "grids_equal": int(grids.primary_recall_delta.eq(0).sum()),
    }
