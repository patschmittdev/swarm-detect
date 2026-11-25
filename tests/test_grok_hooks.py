import pytest

from swarmtrace.eval.grok_hooks import review_grok_hooks


def start(parent, child):
    return dict(hookEventName="subagent_start", sessionId=parent, subagentId=child, subagentType="review")


def stop(child, session=None):
    return dict(hookEventName="subagent_stop", sessionId=child if session is None else session, subagentId=child)


def test_two_overlapping_same_type_workers_close_by_child_and_skip_unrelated_content():
    hooks = [start("desk", "first"), {"hookEventName": "unrelated", "sessionId": []},
             start("desk", "second"), stop("second"), stop("first")]
    counts = review_grok_hooks(iter(hooks))
    assert (counts["events"], counts["other_events"], counts["start_events"], counts["stop_events"]) == (5, 1, 2, 2)
    assert (counts["matched_episodes"], counts["naive_same_session_matches"], counts["incomplete_starts"]) == (2, 0, 0)
    assert counts["overlapping_starts"] == counts["invalid_events"] == 0
    assert all(type(v) is int and v >= 0 for v in counts.values())


def test_bad_stop_leaves_child_active_until_valid_close_and_duplicate_stop_is_orphaned():
    result = review_grok_hooks([stop("early"), start("desk", "a"), stop("a", "desk"), stop("a"), stop("a")])
    assert (result["mismatched_stop_sessions"], result["invalid_events"]) == (1, 1)
    assert (result["matched_episodes"], result["orphan_stops"], result["incomplete_starts"]) == (1, 2, 0)


@pytest.mark.parametrize(("hooks", "overlap"), [
    ([start("one", "x"), start("two", "x"), stop("x"), stop("x")], 1),
    ([start("one", "x"), stop("x"), start("two", "x"), stop("x")], 0),
])
def test_child_claimed_by_distinct_parents_is_ambiguous_across_one_capture(hooks, overlap):
    counts = review_grok_hooks(hooks)
    assert counts["cross_parent_child_ids"] == 1
    assert counts["overlapping_starts"] == overlap
    assert (counts["matched_episodes"], counts["ambiguous_stops"], counts["incomplete_starts"]) == (0, 2, 0)


def test_repeated_starts_are_ambiguous_until_drained_and_capture_boundaries_are_independent():
    a = start("desk", "a")
    result = review_grok_hooks([a, a, stop("a"), stop("a"), a, stop("a"), a])
    assert (result["overlapping_starts"], result["ambiguous_stops"], result["matched_episodes"]) == (1, 2, 1)
    assert result["incomplete_starts"] == 1
    fresh = review_grok_hooks([stop("a"), start("other", "a"), stop("a")])
    assert (fresh["orphan_stops"], fresh["matched_episodes"], fresh["cross_parent_child_ids"]) == (1, 1, 0)


def test_same_session_comparator_can_close_a_different_child_in_nested_work():
    result = review_grok_hooks([start("desk", "a"), start("a", "b"), stop("a"), stop("b")])
    assert result["matched_episodes"] == 2
    assert result["naive_same_session_matches"] == result["naive_wrong_child_matches"] == 1


def test_links_append_only_exact_original_ordinals_in_completion_order():
    other = {"hookEventName": "unrelated", "content": "private"}
    events = [other, start("desk", "first"), start("desk", "second"), other,
              start("desk", "reused"), start("other", "reused"), stop("reused"),
              stop("second"), other, stop("first"), stop("reused"), start("desk", "unfinished")]
    links = [{"start_event": 98, "stop_event": 99}]
    counts = review_grok_hooks(iter(events), links=links)
    assert counts == review_grok_hooks(events)
    assert counts["ambiguous_stops"] == 2 and counts["incomplete_starts"] == 1
    assert links == [{"start_event": 98, "stop_event": 99},
                     {"start_event": 3, "stop_event": 8}, {"start_event": 2, "stop_event": 10}]


def test_invalid_fields_count_events_once_and_do_not_create_episodes():
    events = [None, {"hookEventName": "  "}, {"hookEventName": "subagent_start"},
              start("desk", []), stop("a", " "), start("a", "a"), start("desk", "missing-stop")]
    counts = review_grok_hooks(events)
    assert counts["invalid_events"] == 6
    assert (counts["invalid_event_names"], counts["invalid_session_ids"], counts["invalid_child_ids"]) == (2, 2, 2)
    assert counts["self_parent_starts"] == 1
    assert (counts["matched_episodes"], counts["incomplete_starts"]) == (0, 1)
    assert all(v == 0 for v in review_grok_hooks([]).values())
