import csv
import io
import json
import shutil
from pathlib import Path

import pytest

from swarmtrace.eval import dispatch_reviews as reviews

STUDY = Path(__file__).resolve().parents[1] / "benchmarks" / "dispatch-workflows"


def _votes(tmp_path, change):
    with (STUDY / "reviewers/reviewer-one.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    change(rows)
    path = tmp_path / "other.csv"
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return path


def test_submitted_blind_panel_reproduces_scorecard(tmp_path):
    reports = tmp_path / "reports"
    result = reviews.run_dispatch_reviews(STUDY, reports)
    assert result == json.loads((STUDY / "review-summary.json").read_bytes())
    for name in ("review-agreement.csv", "review-summary.json"):
        assert (reports / name).read_bytes() == (STUDY / name).read_bytes()
    assert reviews.run_dispatch_reviews(STUDY, reports) == result
    assert (result["primary_cases"], result["paired_probe_cases"]) == (58, 2)
    for f, expected in (("read_exception", {"no": 19, "unknown": 0, "yes": 39}),
                        ("completed_effect", {"no": 26, "unknown": 0, "yes": 32}),
                        ("cooperation", {"no": 8, "unknown": 0, "yes": 50})):
        agreement = result["primary_agreement"][f]
        assert (agreement["agree"], agreement["disagree"], agreement["consensus"]) == (58, 0, expected)
        assert agreement["cohen_kappa"] == 1
    for f in ("read_exception", "completed_effect"):
        assert result["primary_references"][f]["agree_with_reference"] == 58
    intent = result["primary_agreement"]["intent"]
    assert (intent["agree"], intent["disagree"]) == (50, 8)
    assert intent["cohen_kappa"] == pytest.approx(0.649016641452345)
    assert intent["consensus"] == {"coordinated": 0, "mistake": 0, "routine": 11, "unresolved": 39}
    assert intent["reviewer_one_by_reviewer_two"]["routine"]["unresolved"] == 8
    assert all(r["resolved_positive"] == 0 and r["resolved_negative"] == 11 and r["excluded_uncertain"] == 47
               for r in result["detectors_on_primary_consensus_intent"].values())
    probes = result["matched_probes"]
    assert probes["identical_observations_except_case_id"]
    assert {p["script_intent"] for p in probes["cases"]} == {"coordinated", "mistake"}
    assert {p["intent"] for p in probes["cases"]} == {"unresolved"}


def test_disagreement_does_not_convert_ambiguous_outcomes_to_negatives(tmp_path):
    def change(rows):
        # Compare reviewer one with a copy of itself that gives one routine case an ambiguous label.
        # Reviewer one judged 19 primary cases routine and 39 unresolved.
        row = next(r for r in rows if r["intent"] == "routine")
        row.update(intent="unresolved", read_exception="unknown")

    custom = _votes(tmp_path, change)
    result = reviews.run_dispatch_reviews(STUDY, tmp_path / "out", review_two=custom)
    intent = result["primary_agreement"]["intent"]
    assert (intent["disagree"], intent["consensus"]["routine"], intent["consensus"]["unresolved"]) == (1, 18, 39)
    assert intent["cohen_kappa"] < 1
    assert result["primary_agreement"]["read_exception"]["reviewer_one_by_reviewer_two"]["no"]["unknown"] == 1
    for counts in result["detectors_on_primary_consensus_intent"].values():
        assert (counts["resolved_negative"], counts["excluded_uncertain"]) == (18, 40)
    assert result["reviewer_source"]["reviewer-two.csv"] == "supplied_for_replay"


@pytest.mark.parametrize(("change", "match"), [
    (lambda rows: rows[0].update(evidence="read:300"), "citations"),
    (lambda rows: rows[0].update(evidence=""), "citations"),
    (lambda rows: rows[0].update(intent="suspicious"), "invalid reviewer label"),
    (lambda rows: rows.append(rows[1].copy()), "duplicate case ID"),
    (lambda rows: rows.pop(), "coverage differs"),
])
def test_rejects_unverifiable_votes(tmp_path, change, match):
    custom = _votes(tmp_path, change)
    with pytest.raises(ValueError, match=match):
        reviews.run_dispatch_reviews(STUDY, tmp_path / "out", review_one=custom)
    assert not (tmp_path / "out").exists()


def test_kappa_counts_unknown_and_is_undefined_for_a_constant_label():
    rows = [{"one_a": a, "two_a": b} for a, b in
            [("yes", "yes"), ("no", "unknown"), ("unknown", "no"), ("no", "no")]]
    result = reviews._ratings(rows, "a", reviews.VOTES)
    assert result["agree"] == 2
    assert result["cohen_kappa"] == pytest.approx(0.2)
    assert reviews._ratings(rows[:1], "a", reviews.VOTES)["cohen_kappa"] is None


@pytest.mark.parametrize(("name", "expected"), [
    ("review-packets.jsonl", "blinded reviewer input"),
    ("reviewers/reviewer-two.csv", "submitted reviewer file has changed"),
])
def test_rejects_edits_to_frozen_panel_inputs(tmp_path, name, expected):
    study = tmp_path / "study"
    for source in ["protocol.json", "review-packets.jsonl", "reviewers/panel.json",
                   "reviewers/reviewer-one.csv", "reviewers/reviewer-two.csv"]:
        (study / source).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(STUDY / source, study / source)
    path = study / name
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(ValueError, match=expected):
        reviews.run_dispatch_reviews(study, tmp_path / "out")


def test_checks_probe_membership_and_observable_equivalence(tmp_path):
    shutil.copyfile(STUDY / "runs.csv.gz", tmp_path / "runs.csv.gz")
    membership = (STUDY / "review-membership.csv").read_bytes()
    (tmp_path / "review-membership.csv").write_bytes(membership)
    lines = (STUDY / "review-packets.jsonl").read_bytes().splitlines()
    packets = {p["case_id"]: p for p in map(json.loads, lines)}
    protocol = reviews.read_protocol(STUDY)
    case, = [r["case_id"] for r in csv.DictReader(io.StringIO(membership.decode()))
             if r["primary"] == "False" and r["profile"] == "late_clerical_slip"]
    packets[case]["grants"] = {}
    with pytest.raises(ValueError, match="probe packets differ"):
        reviews._join_membership(tmp_path, packets, protocol)
    del packets[case]
    with pytest.raises(ValueError, match="membership IDs differ"):
        reviews._join_membership(tmp_path, packets, protocol)


def test_preserves_existing_conflicting_output(tmp_path):
    (tmp_path / "review-summary.json").write_bytes(b"previous report")
    with pytest.raises(ValueError, match="conflicting"):
        reviews.run_dispatch_reviews(STUDY, tmp_path)
    assert (tmp_path / "review-summary.json").read_bytes() == b"previous report"
    assert not (tmp_path / "review-agreement.csv").exists()


def _panel():
    return json.loads((STUDY / "reviewers/panel.json").read_bytes())


def test_original_identical_ballot_is_retained_and_replaced():
    original = (STUDY / "reviewers/original-ballot.csv").read_bytes()
    assert reviews.digest(original) == _panel()["original_submission"]["sha256"]
    for name in ("reviewer-one.csv", "reviewer-two.csv"):
        assert (STUDY / "reviewers" / name).read_bytes() != original


def test_rerun_prompt_is_instructions_followed_by_the_frozen_packets():
    panel = _panel()
    prompt = panel["prompt_instructions"].encode("utf-8") + (STUDY / "review-packets.jsonl").read_bytes()
    assert panel["prompt_parts"][1] == "review-packets.jsonl"
    assert reviews.digest(prompt) == panel["prompt_sha256"]
