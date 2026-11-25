from pathlib import Path

import pytest

from swarmtrace.reproduce import dispatch_role_text as study
from swarmtrace.reproduce.public_tickets import ONLY_DESIGNATED


def test_document_projection_uses_complete_file_tokens_and_exclusive_routing():
    legal, procurement, _, clerk = study.ROLES
    header = f"One prior decision mentioned {clerk}."
    first = f"First, ask {legal} to perform a review of submission/a.md."
    second = f"Next, ask {procurement} to perform a review of submission/aa.md."
    prompt = "\n".join((header, first, second, ONLY_DESIGNATED))
    complete = study.routing(prompt)
    document = study.routing(prompt, "submission/a.md")
    assert complete.text == "\n".join((first, second, ONLY_DESIGNATED))
    assert document.text == "\n".join((first, ONLY_DESIGNATED))
    assert study.parse_role(complete, procurement) == (study.YES, "2")
    assert study.parse_role(document, procurement) == (study.NO, "all")
    assert study.parse_role(complete, clerk) == (study.NO, "all")
    assert study.parse_role(study.routing(prompt, "submission/absent.md"), legal) == (study.UNKNOWN, "")
    assert study.parse_role(study.routing(first), legal) == (study.UNKNOWN, "")
    malformed = study.routing("Forward to liaison for submission/a.md.\n" + ONLY_DESIGNATED)
    assert study.parse_role(malformed, clerk) == (study.UNKNOWN, "")


def test_zero_shot_preserves_absolute_floor_tie_and_missing_context_abstentions():
    r = study.Routing(("a", "b"), (0,), True)
    assert study.nli_decision(r, .9, .1) == study.YES
    assert study.nli_decision(r, .71, .72) == study.NO
    assert study.nli_decision(r, .5, .001) == study.UNKNOWN
    assert study.nli_decision(r, .9, .9) == study.UNKNOWN
    assert study.nli_decision(study.Routing(("a",), (), True), .9, .1) == study.UNKNOWN
    assert study.nli_decision(study.Routing(("a",), (0,), False), .9, .1) == study.UNKNOWN
    with pytest.raises(ValueError, match="probability"):
        study.nli_decision(r, float("nan"), .1)


def test_abstained_designations_stay_in_recall_and_complete_stages():
    rows = [dict(stage_id="one", truth=t, parser=y) for t, y in ((study.YES, study.YES),
            (study.YES, study.UNKNOWN), (study.NO, study.YES), (study.NO, study.NO))]
    counts = study._role_counts(rows, "parser")
    assert counts["precision"] == counts["recall"] == .5
    assert counts["coverage"] == .75
    assert study._stage_counts(rows, "parser")["exact_role_sets"] == 0
    assert study._stage_counts(rows, "parser")["stages_with_abstention"] == 1


def test_one_warning_before_an_unused_copy_remains_a_false_effect_alert():
    cases = [dict(base_id="one", authorized="no", policy_effect="no", exact_use_step="", reader="alert"),
             dict(base_id="one", authorized="no", policy_effect="yes", exact_use_step="4", reader="unknown"),
             dict(base_id="two", authorized="yes", policy_effect="no", exact_use_step="5", reader="clear")]
    counts = study._delivery_counts(cases, "reader")
    assert (counts["deliveries"], counts["bases"], counts["unused_false_alerts"]) == (3, 2, 1)
    assert (counts["flagged_effects"], counts["abstained_effects"], counts["warns_on_authorized"]) == (0, 1, 0)


def test_external_role_benchmark_replays_all_fixed_roles_and_real_dispatch_witnesses(tmp_path):
    benchmarks = Path(__file__).resolve().parents[1] / "benchmarks"
    root = benchmarks / "dispatch-role-text"
    out = tmp_path / "scorecard"
    summary = study.replay(root, benchmarks / "dispatch-workflows", out)
    for name in ("role-metrics.csv", "stage-metrics.csv", "primary-dispatches.csv", "summary.json"):
        assert (out / name).read_bytes() == (root / "results" / name).read_bytes()
    assert summary["partitions"]["confirmation"] == {"bases": 58, "stages": 58, "groups": 43}
    assert summary["partitions"]["integration"]["stages"] == 77
    assert summary["stages_with_different_document_view"] == 0
    assert summary["primary_dispatch"]["parser"]["deliveries"] == 61
    assert summary["primary_dispatch"]["dispatch"]["effects"] == 32
    assert summary["primary_by_authority_and_recipient"]["no"] == {"unlisted_records_clerk": 50}
    assert sum(summary["primary_by_authority_and_recipient"]["yes"].values()) == 11
    specialists = next(r for r in summary["confirmation_roles"] if r["method"] == "deberta" and r["role"] == "real_specialists")
    assert (specialists["true_designated"], specialists["true_excluded"], specialists["false_designated"],
            specialists["abstained_excluded"]) == (82, 8, 1, 83)
    assert summary["independent_swarm_rounds"] == 0
    with pytest.raises(ValueError, match="new output"):
        study.replay(root, benchmarks / "dispatch-workflows", out)
