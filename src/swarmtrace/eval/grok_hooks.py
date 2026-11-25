"""Audit parent and child identity in one ordered capture of native Grok hooks."""

from collections import defaultdict, deque
from collections.abc import Iterable, Mapping


def _identifier(value: object) -> bool:
    return isinstance(value, str) and bool(value) and value == value.strip()


def review_grok_hooks(events: Iterable[Mapping], *, links: list[dict[str, int]] | None = None) -> dict[str, int]:
    """Count lifecycle matches within this capture. Return counts without event content or IDs.

    Starts carry the parent's session ID. A stop must carry the child's own ID in both
    identity fields. Multiple parent claims anywhere in this capture make that child
    ambiguous. Overlapping starts for one child stay ambiguous until their stops drain.
    An incomplete start has no accompanying valid stop by the end of the capture.
    When supplied, links receives the one-based source positions of exact matches.
    """
    counts = dict.fromkeys((
        "events", "other_events", "start_events", "stop_events", "matched_episodes",
        "naive_same_session_matches", "naive_wrong_child_matches", "orphan_stops",
        "ambiguous_stops", "incomplete_starts", "cross_parent_child_ids", "overlapping_starts",
        "invalid_events", "invalid_event_names", "invalid_session_ids", "invalid_child_ids",
        "self_parent_starts", "mismatched_stop_sessions",
    ), 0)
    lifecycle = []
    parents = defaultdict(set)
    for ordinal, event in enumerate(events, 1):
        counts["events"] = ordinal
        name = event.get("hookEventName") if isinstance(event, Mapping) else None
        if not _identifier(name):
            counts["invalid_event_names"] += 1
            counts["invalid_events"] += 1
            continue
        if name not in ("subagent_start", "subagent_stop"):
            counts["other_events"] += 1
            continue
        start = name == "subagent_start"
        counts["start_events" if start else "stop_events"] += 1
        session, child = event.get("sessionId"), event.get("subagentId")
        valid_session, valid_child = _identifier(session), _identifier(child)
        if not (valid_session and valid_child):
            counts["invalid_session_ids"] += int(not valid_session)
            counts["invalid_child_ids"] += int(not valid_child)
            counts["invalid_events"] += 1
            continue
        if (start and session == child) or (not start and session != child):
            counts["self_parent_starts" if start else "mismatched_stop_sessions"] += 1
            counts["invalid_events"] += 1
            continue
        if start:
            parents[child].add(session)
        lifecycle.append((ordinal, start, session, child))

    counts["cross_parent_child_ids"] = sum(len(ids) > 1 for ids in parents.values())
    active = defaultdict(deque)
    overlaps = set()
    by_session = defaultdict(deque)
    for ordinal, start, session, child in lifecycle:
        if start:
            if active[child]:
                counts["overlapping_starts"] += 1
                overlaps.add(child)
            active[child].append(ordinal)
            by_session[session].append(child)
            continue

        # The comparison pairs the earliest active start with the same sessionId.
        if by_session.get(session):
            naive_child = by_session[session].popleft()
            counts["naive_same_session_matches"] += 1
            counts["naive_wrong_child_matches"] += int(naive_child != child)

        if not active[child]:
            counts["orphan_stops"] += 1
            continue
        start_ordinal = active[child].popleft()
        if len(parents[child]) > 1 or child in overlaps:
            counts["ambiguous_stops"] += 1
        else:
            counts["matched_episodes"] += 1
            if links is not None:
                links.append({"start_event": start_ordinal, "stop_event": ordinal})
        if not active[child]:
            overlaps.discard(child)

    counts["incomplete_starts"] = sum(len(starts) for starts in active.values())
    return counts
