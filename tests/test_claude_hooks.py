import json

import pytest

from swarmtrace.eval.claude_hooks import review_claude_hooks


def hook(kind, *, session="ticket", child=None, call=None, name=None, **other):
    event = {"hook_event_name": kind, **other}
    if session is not None:
        event["session_id"] = session
    if child is not None:
        event["agent_id"] = child
    if call is not None:
        event["tool_use_id"] = call
    if name is not None:
        event["tool_name"] = name
    return event


def tool(kind, call, *, child="reviewer", name="Read", **rest):
    return hook(kind, child=child, call=call, name=name, **rest)


def test_starts_stops_resumes_and_orphans_are_scoped_to_the_native_session():
    report = review_claude_hooks([
        hook("SubagentStop", child="unexpected"), hook("SubagentStop", child="unexpected"),
        hook("SubagentStart", child="reviewer"), hook("SubagentStart", child="reviewer"),
        hook("SubagentStart", session="other", child="reviewer"), hook("SubagentStop", child="reviewer"),
        hook("SubagentStop", child="reviewer"), hook("SubagentStart", child="reviewer"),
        hook("SubagentStop", session="other", child="reviewer"), hook("Stop"), hook("SessionEnd"),
        hook("SubagentStart", child="unseen", session=None), hook("SubagentStop", child=""),
    ])
    assert report["events"] == 13 and report["sessions"] == 2
    assert report["lifecycle"] == dict(starts=3, distinct_children=2, matched_stops=2, orphan_stops=1,
                                        open_at_end=1, resumed_starts=1, duplicate_open_starts=1,
                                        duplicate_closed_stops=2, missing_identity=2)
    separate = review_claude_hooks([hook("SubagentStop", child="reviewer")])
    assert separate["lifecycle"]["orphan_stops"] == 1
    assert separate["lifecycle"]["matched_stops"] == 0


def test_latest_open_timing_is_scored_against_explicit_actor_and_can_disagree():
    report = review_claude_hooks([
        tool("PreToolUse", "no-open", child="reviewer"),
        hook("SubagentStart", child="reviewer"), tool("PreToolUse", "one-open"),
        hook("SubagentStart", child="assistant"), hook("SubagentStart", child="reviewer"),
        tool("PreToolUse", "both", child="reviewer"), tool("PreToolUse", "both", child="reviewer"),
        tool("PreToolUse", "last", child="assistant"), tool("PreToolUse", "without-actor", child=None),
        tool("PostToolUse", "without-actor", child=None), hook("SubagentStop", child="assistant"),
        tool("PreToolUse", "single-wrong", child="assistant"), tool("PreToolUse", None),
    ])
    assert report["latest_open"] == dict(eligible=5, correct=2, wrong=2, unassigned=1,
                                         overlap=2, overlap_correct=1, overlap_wrong=1,
                                         conservative_unassigned=3)
    assert report["tools"]["explicit_child_pre"] == 7 and report["tools"]["untagged_pre"] == 1
    assert report["tools"]["duplicate_pre"] == report["tools"]["missing_call_id"] == 1
    assert report["tools"]["untagged_correlated_success"] == 1
    assert report["tools"]["child_paired_success"] == 0


def test_only_ordered_nonconflicting_tool_pairs_verify_native_success_or_failure():
    report = review_claude_hooks([
        tool("PreToolUse", "ok"), tool("PostToolUse", "ok"), tool("PostToolUse", "ok"),
        tool("PreToolUse", "failed"), tool("PostToolUseFailure", "failed"), tool("PostToolUseFailure", "failed"),
        tool("PreToolUse", "other-actor"), tool("PostToolUse", "other-actor", child="assistant"),
        tool("PreToolUse", "other-name"), tool("PostToolUse", "other-name", name="Write"),
        tool("PreToolUse", "lost-actor"), tool("PostToolUse", "lost-actor", child=None),
        tool("PreToolUse", "both"), tool("PostToolUse", "both"), tool("PostToolUseFailure", "both"),
        tool("PostToolUse", "reordered"), tool("PreToolUse", "reordered"),
        tool("PreToolUse", "orphaned-pre"), tool("PostToolUseFailure", "orphaned-failure"),
        tool("PreToolUse", "ok", session="other"), tool("PostToolUse", "ok", session="other"),
    ])
    counts = report["tools"]
    assert (counts["child_paired_success"], counts["child_paired_failure"], counts["duplicate_terminal"]) == (2, 1, 2)
    assert (counts["identity_conflicts"], counts["outcome_conflicts"], counts["out_of_order"]) == (3, 1, 1)
    assert counts["missing_pre"] == counts["missing_result"] == 1
    assert counts["untagged_correlated_success"] == 0
    assert report["latest_open"]["eligible"] == 6


def test_missing_native_fields_never_join_unrelated_calls():
    report = review_claude_hooks([
        tool("PreToolUse", None), tool("PostToolUse", "", session=None),
        tool("PreToolUse", "same", name=None), tool("PostToolUse", "same", name=None),
        tool("PreToolUse", "unknown", child=None), tool("PostToolUse", "unknown", child=None),
        tool("PreToolUse", "another", session="other"), tool("PostToolUse", "another", session="ticket")
    ])
    c = report["tools"]
    assert c["missing_call_id"] == c["missing_tool_name"] == 2
    assert c["missing_session"] == c["incomplete_identity_calls"] == 1
    assert c["missing_pre"] == c["missing_result"] == 1
    assert c["untagged_correlated_success"] == 1 and c["child_paired_success"] == 0


def test_launch_links_require_matching_calls_and_exact_returned_agent_id():
    events = [hook("SubagentStart", child="clerk"), hook("SubagentStart", session="other", child="absent")]
    for source, target, call in (("reviewer", "clerk", "nested"), (None, "clerk", "unspecified-caller"),
                                 (None, "absent", "no-start-in-this-session"), ("clerk", None, "no-ack")):
        events.append(tool("PreToolUse", call, child=source, name="Agent"))
        events.append(tool("PostToolUse", call, child=source, name="Agent", tool_response={"agentId": target}))
    events.extend([
        tool("PostToolUse", "nested", name="Agent", child="reviewer", tool_response={"agentId": "clerk"}),
        tool("PreToolUse", "conflicting", name="Agent"),
        tool("PostToolUse", "conflicting", name="Agent", tool_response={"agentId": "clerk"}),
        tool("PostToolUse", "conflicting", name="Agent", tool_response={"agentId": "other"}),
        # A caller can mention a worker in its own input or in the body of an unrelated tool.
        tool("PreToolUse", "independent", name="Read", tool_input={"agentId": "clerk"}),
        tool("PostToolUse", "independent", name="Read", tool_response={"agentId": "clerk"}),
    ])
    report = review_claude_hooks(events)
    assert report["lineage"] == dict(launch_acks=3, observed_target=2, unobserved_target=1,
                                     explicit_child_caller=1, untagged_caller=2)
    assert report["tools"]["result_target_conflicts"] == 1


def test_a_later_start_cannot_confirm_an_earlier_launch_ack():
    report = review_claude_hooks([
        tool("PreToolUse", "claim", name="Agent"),
        tool("PostToolUse", "claim", name="Agent", tool_response={"agentId": "assistant"}),
        hook("SubagentStart", child="assistant"),
        tool("PostToolUse", "claim", name="Agent", tool_response={"agentId": "assistant"}),
        tool("PreToolUse", "second", name="Agent"),
        tool("PostToolUse", "second", name="Agent", tool_response={"agentId": "assistant"}),
        tool("PreToolUse", "contradictory", name="Agent"),
        tool("PostToolUse", "contradictory", name="Agent", tool_response={}),
        tool("PostToolUse", "contradictory", name="Agent", tool_response={"agentId": "assistant"}),
    ])
    assert report["lineage"]["launch_acks"] == 2
    assert report["lineage"]["observed_target"] == report["lineage"]["unobserved_target"] == 1
    assert report["tools"]["result_target_conflicts"] == report["tools"]["duplicate_terminal"] == 1


def test_malformed_actor_on_both_halves_does_not_become_an_untagged_caller():
    report = review_claude_hooks([
        tool("PreToolUse", "bad", child={"name": "example"}, name="Agent"),
        tool("PostToolUse", "bad", child=42, name="Agent", tool_response={"agentId": "assistant"}),
    ])
    assert report["tools"]["invalid_actor"] == 2
    assert report["tools"]["incomplete_identity_calls"] == 1
    assert report["tools"]["untagged_correlated_success"] == report["lineage"]["launch_acks"] == 0


def test_review_links_locate_only_verified_explicit_pairs_using_the_original_event_ordinals():
    private = "private-label-in-user-record"
    events = [
        hook("SubagentStart", child=private), hook("SubagentStart", child="assistant"),
        tool("PreToolUse", private, child=private, name=private, tool_input={"text": private}),
        hook("SubagentStop", child=private),
        tool("PostToolUse", private, child=private, name=private, tool_response={"text": private}),
        tool("PreToolUse", "failed", child="no-start"), tool("PostToolUseFailure", "failed", child="no-start"),
        tool("PreToolUse", "missing"), tool("PreToolUse", "wrong"),
        tool("PostToolUse", "wrong", child="another"), tool("PreToolUse", "untagged", child=None),
        tool("PostToolUse", "untagged", child=None), hook("SubagentStart", child=private),
        tool("PreToolUse", "resumed", child=private), tool("PostToolUse", "resumed", child=private),
    ]
    links = []
    report = review_claude_hooks(events, links=links)
    assert report == review_claude_hooks(events)
    assert links == [
        dict(pre_event=3, result_event=5, child_start_event=1, latest_start_event=2),
        dict(pre_event=6, result_event=7, child_start_event=None, latest_start_event=2),
        dict(pre_event=14, result_event=15, child_start_event=13, latest_start_event=13),
    ]
    assert private not in json.dumps(links)


def test_result_is_count_only_and_empty_stream_or_invalid_record_are_distinguishable():
    private = "do-not-export"
    raw = [hook("SubagentStart", session=private, child=private, transcript_path=private),
           tool("PreToolUse", private, child=private, session=private, name=private,
                tool_input={private: private}, cwd=private),
           tool("PostToolUse", private, child=private, session=private, name=private,
                tool_response={private: private}, prompt=private)]
    report = review_claude_hooks(iter(raw))
    assert report["tools"]["child_paired_success"] == 1
    assert private not in json.dumps(report)
    for key in ("lifecycle", "tools", "latest_open", "lineage"):
        assert all(type(value) is int and value >= 0 for value in report[key].values())
    assert review_claude_hooks([])["events"] == 0
    with pytest.raises(ValueError, match="JSON object"):
        review_claude_hooks([{}, None])
