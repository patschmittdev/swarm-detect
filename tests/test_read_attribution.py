import pandas as pd
import pytest

from swarmtrace.eval.read_attribution import attribution_challenge, summarize_attribution


def test_independent_attribution_challenge_scores_both_methods_on_the_same_reads():
    cases = attribution_challenge()
    gateway, legacy = (cases[cases.method == method].set_index("case")
                       for method in ("gateway", "legacy_borrowed_login"))
    truth = ["seq", "tick", "agent", "file", "expected_basis", "expected_grant",
             "expected_out_of_scope"]
    pd.testing.assert_frame_equal(gateway[truth], legacy[truth])
    summary = summarize_attribution(cases).set_index("method")
    for method, expected in (
        ("gateway", (14, 13, 12, 0, 1, 1, 1, 6, 0, 1, 6, 0)),
        ("legacy_borrowed_login", (14, 13, 5, 1, 7, 1, 1, 5, 2, 2, 4, 1)),
    ):
        row = summary.loc[method]
        counts = ["reads", "resolvable", "correct_attributions", "wrong_attributions",
                  "unknown_attributions", "indeterminate_truth", "abstained_on_indeterminate",
                  "scope_tp", "scope_fp", "scope_fn", "scope_tn", "alerts_on_unassessed"]
        assert tuple(row[counts]) == expected
    assert summary.loc["gateway", "scope_precision"] == 1
    assert summary.loc["gateway", "scope_recall"] == pytest.approx(6 / 7)
    assert summary.loc["legacy_borrowed_login", "scope_recall"] == pytest.approx(5 / 7)
    assert summary.loc["legacy_borrowed_login", "scope_precision"] == pytest.approx(5 / 7)


def test_challenge_exercises_real_overlap_partial_capture_and_positive_corroboration():
    cases = attribution_challenge()
    gateway = cases[cases.method == "gateway"].set_index("case")
    assert gateway.loc["explicit_second_assignment", "predicted_grant"] == gateway.loc[
        "explicit_second_assignment", "expected_grant"]
    assert gateway.loc["ambiguous_unbound_read", "predicted_basis"] == "unknown"
    assert gateway.loc["missing_decision", "expected_basis"] == "grant"
    assert gateway.loc["missing_decision", "predicted_basis"] == "unknown"
    assert gateway.loc["ordinary_after_borrowed_login", "predicted_basis"] == "ordinary"
    assert (gateway[gateway.tick < 14].corroborated_files == 0).all()
    assert (gateway[gateway.tick >= 14].corroborated_files == 1).all()
