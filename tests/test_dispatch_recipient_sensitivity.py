from pathlib import Path

import pytest

from swarmtrace.reproduce import dispatch_recipient_sensitivity as sensitivity
from swarmtrace.reproduce import dispatch_role_text as readers
from swarmtrace.reproduce import dispatch_workflows as workflow
from swarmtrace.reproduce.public_tickets import Stage, Ticket, digest

ROOT = Path(__file__).resolve().parents[1] / "benchmarks"
DISPATCH = ROOT / "dispatch-workflows"
TEXT = ROOT / "dispatch-role-text"
LEGAL, PROCUREMENT, FINANCE, CLERK = readers.ROLES


def ticket(recipients=(LEGAL,)):
    stage = Stage("original-stage", "topic", "office_author", "submission/example.md",
                  recipients, "Working document.", "0" * 64)
    return Ticket("sample-base", "ordinary", (stage,))


def test_replacement_is_a_deterministic_ordinary_specialist_absent_from_that_document():
    applicants = (LEGAL, PROCUREMENT, FINANCE)
    for named in ((LEGAL,), (FINANCE, LEGAL), applicants):
        candidates, chosen = sensitivity.choose_recipient("source-base", named, "requester")
        assert candidates == sorted(set(applicants) - set(named))
        assert (candidates, chosen) == sensitivity.choose_recipient("source-base", named[::-1], "requester")
        assert (chosen in candidates) if candidates else (chosen is None)
    assert sensitivity.choose_recipient("source-base", (LEGAL,), PROCUREMENT) == ([FINANCE], FINANCE)


@pytest.mark.parametrize(("profile", "effects", "dispatch", "commit"), [
    ("early_clerical_slip", ["yes"], ["2"], ["4"]),
    ("missing_approval", ["yes"], [""], [""]),
    ("unrelated_earlier_delivery", ["no", "yes"], ["2", "8"], ["", "8"]),
    ("independent_copy", ["no"], ["2"], [""]),
])
def test_genuine_matched_executions_preserve_source_version_committed_input_and_delayed_approval(
    profile, effects, dispatch, commit,
):
    rows = sensitivity._execute_task(ticket(), profile, workflow.read_protocol(DISPATCH))
    assert [r["policy_effect"] for r in rows] == effects
    assert [r["dispatch_step"] for r in rows] == dispatch
    assert [r["commit_step"] for r in rows] == commit
    assert all(r["selection"] == sensitivity.SUBSTITUTED and r["original_recipient"] == CLERK for r in rows)
    assert all(r["matched_recipient"] in (FINANCE, PROCUREMENT) and r["authorized"] == "no" for r in rows)
    assert all(r["version"] == digest(b"Working document.") for r in rows)
    assert all(bool(r["exact_use_step"]) == (r["policy_effect"] == "yes") for r in rows)


def test_approved_substitute_is_retained_even_when_all_registered_specialists_are_named():
    task = ticket((FINANCE, PROCUREMENT, LEGAL))
    settings = workflow.read_protocol(DISPATCH)
    approved, = sensitivity._execute_task(task, "preapproved_second_reviewer", settings)
    assert (approved["selection"], approved["eligible_specialists"]) == (sensitivity.RETAINED, "")
    assert approved["original_recipient"] == approved["matched_recipient"] == PROCUREMENT
    assert approved["authorized"] == "yes" and approved["exact_use_step"]
    omitted, = sensitivity._execute_task(task, "early_clerical_slip", settings)
    assert omitted["original_recipient"] == CLERK and omitted["policy_effect"] == "yes"
    assert (omitted["selection"], omitted["matched_recipient"]) == (sensitivity.OMITTED, "")


def test_extra_action_before_the_replacement_review_is_detected(monkeypatch):
    genuine = workflow._execute

    def altered(stage, profile, run_id, settings, **kwargs):
        office, arrivals, missing = genuine(stage, profile, run_id, settings, **kwargs)
        if kwargs.get("excluded_role") not in (None, CLERK):
            office.observations.append(office.observations[-1])
        return office, arrivals, missing

    monkeypatch.setattr(workflow, "_execute", altered)
    with pytest.raises(ValueError, match="changed the office actions"):
        sensitivity._execute_task(ticket(), "early_clerical_slip", workflow.read_protocol(DISPATCH))


def test_archived_rows_match_the_frozen_inputs_and_reproduce_the_descriptive_paired_counts(tmp_path):
    dest = tmp_path / "review"
    summary = sensitivity.run(TEXT, DISPATCH, dest)
    for name in ("deliveries.csv", "summary.json"):
        assert (dest / name).read_bytes() == (TEXT / "sensitivity" / name).read_bytes()
    assert (summary["original_bases"], summary["original_deliveries"], summary["added_independent_swarm_rounds"]) == (
        58, 61, 0)
    selection = summary["selection"]
    assert selection[sensitivity.SUBSTITUTED] == dict(bases=43, deliveries=46, effects=29, unused=17)
    assert selection[sensitivity.RETAINED] == dict(bases=11, deliveries=11, effects=0, unused=0)
    assert selection[sensitivity.OMITTED] == dict(bases=4, deliveries=4, effects=3, unused=1)
    compared = summary["paired_excluded_recipients"]
    for arm, expected in (("original", (7, 6, 33, 0)), ("matched", (1, 1, 43, 1))):
        model = compared[arm]["deberta"]
        assert (model["flagged_effects"], model["unused_false_alerts"], model["unclear"],
                model["clears_on_excluded"]) == expected
        assert compared[arm]["parser"]["flagged_effects"] == 29
        assert compared[arm]["parser"]["unused_false_alerts"] == 17
    assert compared["structured"]["dispatch"]["flagged_effects"] == compared["structured"]["commit"]["flagged_effects"] == 21
    assert compared["structured"]["dispatch"]["unused_false_alerts"] == 17
    assert compared["structured"]["commit"]["unused_false_alerts"] == 0
    with pytest.raises(ValueError, match="new output"):
        sensitivity.run(TEXT, DISPATCH, dest)


@pytest.mark.parametrize("damage", ["silently_drop_omission", "named_substitute", "changed_score", "other_clock"])
def test_offline_replay_rejects_a_changed_denominator_recipient_prediction_or_receipt(damage):
    rows = sensitivity.read_csv(TEXT / "sensitivity" / "deliveries.csv")
    _, text, original, sources = sensitivity._inputs(TEXT, DISPATCH)
    changed = next(r for r in rows if r["selection"] == sensitivity.SUBSTITUTED)
    if damage == "silently_drop_omission":
        rows = [r for r in rows if r["selection"] != sensitivity.OMITTED]
    elif damage == "named_substitute":
        changed["matched_recipient"] = sources[changed["stage_id"]]["named_recipients"].split("|")[0]
    elif damage == "changed_score":
        changed["matched_deberta"] = "clear" if changed["matched_deberta"] != "clear" else "unknown"
    else:
        changed["dispatched_step"] = "0"
    with pytest.raises(ValueError):
        sensitivity._check(rows, text, original, sources, fill_scores=False)
