import json

import numpy as np
import pandas as pd
import pytest

from swarmtrace.eval.assignment_round import FAMILIES, report_assignment_round


def _grid(family, *, small=270, large=1, controls=200):
    index = np.arange(small + large + controls)
    positive = index < small + large
    rows = pd.DataFrame({
        "task": "scope", "test_set": "independent", "split_seed": 24,
        "run_id": [f"{family}-{i}" for i in index], "family": family,
        "positive": positive, "small_positive": index < small,
        "hard_control": ~positive & (index < small + large + controls // 2),
        "shared_verified_documents": 1, "shared_reads_before_component_end": 2,
        "office_reads_before_native_end": 4, "office_tickets": 1 + index % 3,
        "exercised_office_tickets": 1, "assignment_count": 2, "unknown_reads": 1,
        "missing_decisions": 0, "no_safe_interleave": False, "fallback": False,
    })
    return pd.concat([
        rows.assign(detector=arm, score=scores, threshold=.5)
        for arm, scores in (("ref", np.zeros(len(index))), ("new", (index < 35) * .9),
                            ("alternative", positive * .9))
    ], ignore_index=True)


def _report(tmp_path, tables, *, primary=True):
    paths = []
    for i, table in enumerate(tables):
        path = tmp_path / f"grid-{i}.csv"
        table.to_csv(path, index=False)
        paths.append(path)
    return report_assignment_round(tmp_path / "report", paths, candidate="new", reference="ref",
                                   alternatives=("alternative",), primary=primary)


def test_qualifies_only_the_predeclared_comparison_and_counts_support_once(tmp_path):
    tables = [_grid(f) for f in FAMILIES]
    tables[0].loc[tables[0].run_id.eq("record_check-270"),
                  ["fallback", "no_safe_interleave"]] = True
    tables[0].loc[tables[0].fallback, ["shared_verified_documents", "shared_reads_before_component_end"]] = 0
    decision = _report(tmp_path, tables)
    json.dumps(decision, allow_nan=False)
    assert decision["paired_evidence"] == "promising"
    assert decision["round_evidence"] == "qualified_local_profile"
    assert decision["qualified_local_profile"] and not decision["counts_toward_diminishing_returns"]
    assert (decision["one_file_runs"], decision["controls"]) == (540, 400)
    assert (decision["grids_gaining"], decision["grids_losing"]) == (2, 0)
    assert decision["candidate_fpr_upper"] == pytest.approx(1 - .05 ** (1 / 400))
    out = tmp_path / "report"
    scorecard = pd.read_csv(out / "scorecard.csv")
    assert len(scorecard) == 6
    pooled = scorecard[scorecard.population == "pooled"].set_index("reference")
    assert pooled.loc["ref", "round_evidence"] == "qualified_local_profile"
    assert pooled.loc["alternative", "round_evidence"] == "descriptive_comparator"
    assert pooled.loc["alternative", "primary_lost"] == 470
    families = pd.read_csv(out / "families.csv").set_index("family")
    assert families.loc["record_check", "primary_gained"] == 35
    assert families.loc["clerical_handoff", "candidate_fpr_upper"] == pytest.approx(1 - .05 ** (1 / 200))
    support = pd.read_csv(out / "support.csv").set_index(["family", "run_class"])
    all_runs = support.loc[("pooled", "all")]
    assert (all_runs.runs, all_runs.unknown_reads, all_runs.missing_decisions) == (942, 942, 0)
    assert (all_runs.office_tickets_min, all_runs.office_tickets_max) == (1, 3)
    assert (all_runs.exercised_office_tickets, all_runs.assignment_count) == (942, 1884)
    assert all_runs.runs_with_shared_documents == all_runs.runs_with_shared_read_before_component_end == 941
    assert all_runs.shared_reads_before_component_end == 1882
    assert all_runs.office_reads_before_native_end == 3768
    checked = support.loc[("record_check", "positive")]
    assert (checked.fallback_runs, checked.no_safe_interleave_runs) == (1, 1)
    assert checked.runs == 271 and checked.runs_with_shared_documents == 270


def test_rankings_observe_whole_ties_exact_cutoffs_and_pooled_false_alert_budgets(tmp_path):
    first, second = [_grid(f, small=2, large=1, controls=100) for f in FAMILIES]
    high = np.nextafter(.9, 1)
    first.loc[first.detector == "new", "score"] = [high, .9, .8, *([.9] * 4), .8, .8, *([0] * 94)]
    first.loc[first.detector == "ref", "score"] = [0, 0, 0, *([0] * 6), .7, *([0] * 93)]
    second.loc[second.detector == "new", "score"] = [.1, .1, .1, *([0] * 100)]
    _report(tmp_path, [first, second])
    rankings = pd.read_csv(tmp_path / "report/review-budgets.csv")
    assert len(rankings) == 3 * 3 * 3
    flags = rankings[rankings.detector == "new"].set_index(["family", "budget_fraction"])
    for q in (.01, .02):
        row = flags.loc[("record_check", q)]
        assert (row.false_positives, row.true_positives, row.small_true_positives) == (0, 1, 1)
    row = flags.loc[("record_check", .05)]
    assert (row.false_alert_budget, row.false_positives, row.true_positives, row.small_true_positives) == (5, 4, 2, 2)
    pooled = flags.loc[("pooled", .05)]
    assert (pooled.false_alert_budget, pooled.false_positives, pooled.true_positives) == (10, 6, 6)
    family = pd.read_csv(tmp_path / "report/families.csv").set_index("family").loc["record_check"]
    assert (family.hard_false_positives_added, family.hard_false_positives_removed) == (6, 1)


@pytest.mark.parametrize(("case", "expected"), [
    ("equal", "below_minimum"), ("native", "descriptive_transfer"),
    ("too_few", "insufficient_data"), ("absent_family", "insufficient_data"),
    ("missing_shared", "insufficient_feature_support"), ("family_loss", "failed_family_guardrails"),
    ("family_fpr", "failed_family_guardrails"), ("confidence", "insufficient_fpr_confidence"),
    ("over_budget", "over_budget"),
])
def test_transfer_coverage_and_operating_point_gates_precede_a_stopping_decision(tmp_path, case, expected):
    tables = [_grid(f, small=269 if case == "too_few" and i else 270) for i, f in enumerate(FAMILIES)]
    if case == "absent_family":
        tables = [_grid(FAMILIES[0], small=540)]
    if case in ("equal", "native", "missing_shared"):
        for t in tables:
            t.loc[t.detector == "new", "score"] = 0
    if case == "missing_shared":
        t = tables[1]
        t.loc[~t.positive, "shared_verified_documents"] = 0
    if case == "family_loss":
        t = tables[1]
        t.loc[t.detector == "new", "score"] = 0
        t.loc[(t.detector == "ref") & t.run_id.eq("clerical_handoff-0"), "score"] = .8
    if case in ("family_fpr", "confidence", "over_budget"):
        for i, t in enumerate(tables):
            k = 11 if case == "over_budget" or (case == "family_fpr" and i) else (9 if case == "confidence" else 0)
            ids = t[t.detector.eq("new") & ~t.positive & ~t.hard_control].index[:k]
            t.loc[ids, "score"] = .7
    result = _report(tmp_path, tables, primary=case != "native")
    assert result["round_evidence"] == expected
    assert result["counts_toward_diminishing_returns"] is (case == "equal")
    assert not result["qualified_local_profile"]
    if case in ("equal", "missing_shared", "native"):
        assert result["paired_evidence"] == "below_minimum"
    if case in ("family_loss", "family_fpr", "confidence"):
        assert result["paired_evidence"] == "promising"


def test_no_controls_yields_no_operating_point_and_a_json_safe_decision(tmp_path):
    decision = _report(tmp_path, [_grid(f, controls=0) for f in FAMILIES])
    json.dumps(decision, allow_nan=False)
    assert decision["round_evidence"] == "insufficient_data" and decision["candidate_fpr_upper"] is None
    ranks = pd.read_csv(tmp_path / "report/review-budgets.csv")
    assert ranks.false_positives.isna().all() and ranks.true_positives.isna().all()


@pytest.mark.parametrize(("column", "value", "match"), [
    ("family", "elsewhere", "family"), ("fallback", "unclear", "flags"),
    ("office_tickets", "-1", "nonnegative"), ("office_tickets", "0", "exercised"),
    ("missing_decisions", "3", "unknown"), ("unknown_reads", "2", "inconsistent"),
])
def test_invalid_or_arm_specific_support_cannot_produce_a_report_packet(tmp_path, column, value, match):
    table = _grid(FAMILIES[0], small=2, controls=20)
    table[column] = table[column].astype(object)
    table.loc[0, column] = value
    with pytest.raises(ValueError, match=match):
        _report(tmp_path, [table])
    assert not (tmp_path / "report").exists()
