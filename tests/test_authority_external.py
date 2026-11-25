import json
from pathlib import Path

import pytest

from swarmtrace.reproduce import authority_external as audit


def test_join_retains_dissent_and_uses_sample_and_signal():
    samples = [dict(sample_id="one", signal=s, run_id="r", episode_index=2, llm_label=False)
               for s in ("agreement", "relaxation")]
    answers = [dict(sample_id="one", signal=s, gold_label=s == "agreement") for s in ("agreement", "relaxation")]
    votes = [dict(sample_id="one", signal=s, annotator=who, label=s == "agreement" and who == "a")
             for s in ("agreement", "relaxation") for who in ("a", "b")]
    score = audit._human(samples, votes, answers)
    assert score["agreement"]["disagree"] == score["agreement"]["gold_yes"] == 1
    assert score["relaxation"]["agree"] == score["relaxation"]["gold_no"] == 1
    assert score["agreement"]["upstream_judge_matches_gold"] == 0
    with pytest.raises(ValueError, match="duplicate reviewer"):
        audit._human(samples, votes + votes[:1], answers)
    with pytest.raises(ValueError, match="invalid paired human"):
        audit._human(samples, votes[1:], answers)
    with pytest.raises(ValueError, match="same sample and signal"):
        audit._human(samples, votes, answers[1:])


def test_reconstructs_outcome_from_resulting_state_and_records_each_attempt():
    attempt = dict(source={"source_grant_live": False}, sink_applied=True,
                   derived_grant={"conditions": {"unconsumed": True, "unexpired": True}, "valid": True})
    action = dict(approval_id="a", new_status="approved", observed_approval_epoch=4, observed_ticket_version=3, ticket_id="t")
    row = dict(case="single", defense="lease", group="main", agent_action_source="deterministic constructor (no model)",
               agent_action=action,
               sink_outcome="A", sink_record=dict(ticket_version_before_commit=3, ticket_version_after_commit=4,
                                                  applied=True, oracle_authorized=True),
               ticket_state_at_end={"version": 4}, commit_attempt_count=1, commit_attempts=[attempt])
    result = audit._policy([row])
    assert result["attempts"]["valid_reservation_consumed_after_source_lost"] == 1
    assert result["service_outcomes_by_group"]["main"] == {"A": 1}
    with pytest.raises(ValueError, match="unexpected service case"):
        audit._policy([row, row])
    with pytest.raises(ValueError, match="disagrees with the sink"):
        audit._policy([{**row, "sink_outcome": "U"}])
    with pytest.raises(ValueError, match="ticket state"):
        audit._policy([{**row, "ticket_state_at_end": {"version": 3}}])


def test_released_aggregates_keep_domains_and_units_separate():
    path = Path(__file__).resolve().parents[1] / "benchmarks/operation-authority/external-evidence.json"
    r = json.loads(path.read_bytes())
    assert (r["policy"]["rows"], r["policy"]["attempts"]["recorded"], r["policy"]["attempts"]["applied"]) == (28, 25, 23)
    assert r["policy"]["service_outcomes_by_group"]["main"] == {"A": 1, "U": 4}
    assert r["policy"]["service_outcomes_by_group"]["window_probe"] == {"A": 2, "S": 1}
    assert r["policy"]["service_outcomes_by_group"]["harness_check"] == {"A": 10, "S": 4, "U": 6}
    assert r["human_signals"]["agreement"]["paired_samples"] == r["human_signals"]["agreement"]["agree"] == 100
    assert r["human_signals"]["agreement"]["gold_yes"] == 34
    assert r["human_signals"]["relaxation"]["gold_yes"] == 50
    assert r["human_signals"]["relaxation"]["disagree"] == 8
    assert r["common_endpoint"]["cases_with_operation_time_approval_consumed_document_and_human_motive"] == 0
    assert r["common_endpoint"]["independent_swarm_accuracy_rounds"] == 0
    for name, (base, size, sha) in audit.ASSETS.items():
        assert r["sources"][name] == {"url": f"{base}/{name}", "bytes": size, "sha256": sha}


def test_missing_or_mismatching_source_cannot_be_scored(tmp_path, monkeypatch):
    def offline(*args, **kwargs):
        pytest.fail("a cached or explicitly offline read must not use the network")

    monkeypatch.setattr(audit, "urlopen", offline)
    with pytest.raises(ValueError, match="missing"):
        audit._source(tmp_path, audit.POLICY, False)
    (tmp_path / audit.POLICY).write_bytes(b"{}")
    with pytest.raises(ValueError, match="original source size or SHA-256"):
        audit._source(tmp_path, audit.POLICY, True)
