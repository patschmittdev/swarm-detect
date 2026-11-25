"""Review native Claude Code hook records using counts and optional links by event ordinal."""

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field


def _id(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _counts(*names: str) -> dict[str, int]:
    return dict.fromkeys(names, 0)


@dataclass
class _Call:
    # Only identifiers, hook kinds and ordinals are retained. Tool arguments and results can be private.
    identities: set[tuple[str | None, str | None]] = field(default_factory=set)
    pre: set[tuple[str | None, str | None]] = field(default_factory=set)
    terminals: set[tuple[str | None, str | None, str, str | None]] = field(default_factory=set)
    first_pre: int | None = None
    first_terminal: int | None = None
    active_count: int = 0
    latest_actor: str | None = None
    child_start_event: int | None = None
    latest_start_event: int | None = None
    invalid_actor: bool = False


def _record_call(call, event, kind, actor, ordinal, active, tools):
    name = _id(event.get("tool_name"))
    identity = (actor, name)
    call.identities.add(identity)
    if "agent_id" in event and actor is None:
        call.invalid_actor = True
    if kind == "PreToolUse":
        if identity in call.pre:
            tools["duplicate_pre"] += 1
        call.pre.add(identity)
        if call.first_pre is None:
            call.first_pre = ordinal
            call.active_count = len(active)
            call.latest_actor = next(reversed(active), None)
            call.child_start_event = active.get(actor)
            call.latest_start_event = active.get(call.latest_actor)
        return
    response = event.get("tool_response")
    child = _id(response.get("agentId")) if (
        kind == "PostToolUse" and name == "Agent" and isinstance(response, Mapping)
    ) else None
    terminal = (actor, name, kind, child)
    if terminal in call.terminals:
        tools["duplicate_terminal"] += 1
    call.terminals.add(terminal)
    if call.first_terminal is None:
        call.first_terminal = ordinal


def _compare_timing(call, actor, counts):
    counts["eligible"] += 1
    if call.active_count != 1:
        counts["conservative_unassigned"] += 1
    if not call.active_count:
        counts["unassigned"] += 1
        return
    result = "correct" if call.latest_actor == actor else "wrong"
    counts[result] += 1
    if call.active_count > 1:
        counts["overlap"] += 1
        counts["overlap_" + result] += 1


def _finish_call(call, session, first_start, tools, latest, lineage, links):
    if len(call.identities) != 1:
        tools["identity_conflicts"] += 1
        return
    actor, name = next(iter(call.identities))
    if name is None or call.invalid_actor:
        tools["incomplete_identity_calls"] += 1
        return
    if actor and call.first_pre is not None:
        _compare_timing(call, actor, latest)
    if call.first_pre is None:
        tools["missing_pre"] += 1
        return
    if call.first_terminal is None:
        tools["missing_result"] += 1
        return
    outcomes = {kind for _, _, kind, _ in call.terminals}
    if len(outcomes) != 1:
        tools["outcome_conflicts"] += 1
        return
    if call.first_terminal < call.first_pre:
        tools["out_of_order"] += 1
        return
    success = outcomes == {"PostToolUse"}
    targets = {target for _, _, _, target in call.terminals}
    if len(targets) > 1:
        tools["result_target_conflicts"] += 1
        return
    prefix = "child_paired_" if actor else "untagged_correlated_"
    tools[prefix + ("success" if success else "failure")] += 1
    if links is not None and actor is not None:
        links.append(dict(pre_event=call.first_pre, result_event=call.first_terminal,
                          child_start_event=call.child_start_event, latest_start_event=call.latest_start_event))
    target, = targets
    if target is not None:
        lineage["launch_acks"] += 1
        start = first_start.get((session, target))
        observed = start is not None and start <= call.first_terminal
        lineage["observed_target" if observed else "unobserved_target"] += 1
        lineage["explicit_child_caller" if actor else "untagged_caller"] += 1


def review_claude_hooks(events: Iterable[Mapping], *, links: list[dict] | None = None) -> dict:
    """Review one ordered capture. Call separately for each independent capture boundary.

    A native child start/stop applies only to its exact session and child. A parent Stop
    does not close children. Tool-use IDs are scoped by session. A conflicting actor or name
    prevents a match. Repeated observations of the same ID and disposition count once.
    A success counts a native PostToolUse record, without interpreting its payload as an effect.
    Calls missing the actor on both halves can be correlated, but have no child attribution.
    The timing diagnostic compares the open child with the latest start against each explicit
    worker pre-hook. A conservative single-open guess abstains at zero or multiple open workers.
    When supplied, links receives one-based event ordinals for verified explicit child pairs.
    Each optional start ordinal refers to the child active when that call's pre-hook arrived.
    """
    lifecycle = _counts("starts", "distinct_children", "matched_stops", "orphan_stops", "open_at_end",
                        "resumed_starts", "duplicate_open_starts", "duplicate_closed_stops", "missing_identity")
    tools = _counts("pre", "post", "failure", "explicit_child_pre", "untagged_pre", "untagged_terminal",
                    "missing_call_id", "missing_tool_name", "missing_session", "invalid_actor",
                    "duplicate_pre", "duplicate_terminal",
                    "child_paired_success", "child_paired_failure", "untagged_correlated_success",
                    "untagged_correlated_failure", "missing_pre", "missing_result", "incomplete_identity_calls",
                    "identity_conflicts", "outcome_conflicts", "result_target_conflicts", "out_of_order")
    latest = _counts("eligible", "correct", "wrong", "unassigned", "overlap", "overlap_correct",
                     "overlap_wrong", "conservative_unassigned")
    lineage = _counts("launch_acks", "observed_target", "unobserved_target", "explicit_child_caller",
                      "untagged_caller")
    active: dict[str, dict[str, int]] = defaultdict(dict)
    first_start = {}
    stopped = set()
    sessions = set()
    calls: dict[tuple[str, str], _Call] = defaultdict(_Call)
    event_count = 0
    for event_count, event in enumerate(events, 1):
        if not isinstance(event, Mapping):
            raise ValueError("each Claude hook record must be a JSON object")
        kind = _id(event.get("hook_event_name"))
        actor = _id(event.get("agent_id"))
        session = _id(event.get("session_id"))
        if session:
            sessions.add(session)
        if kind in ("SubagentStart", "SubagentStop"):
            if session is None or actor is None:
                lifecycle["missing_identity"] += 1
                continue
            child = (session, actor)
            if kind == "SubagentStart":
                if actor in active[session]:
                    lifecycle["duplicate_open_starts"] += 1
                else:
                    lifecycle["resumed_starts"] += int(child in first_start)
                    lifecycle["starts"] += 1
                    first_start.setdefault(child, event_count)
                    active[session][actor] = event_count
            elif actor in active[session]:
                del active[session][actor]
                lifecycle["matched_stops"] += 1
                stopped.add(child)
            elif child in stopped:
                lifecycle["duplicate_closed_stops"] += 1
            else:
                lifecycle["orphan_stops"] += 1
                stopped.add(child)
        elif kind in ("PreToolUse", "PostToolUse", "PostToolUseFailure"):
            call_id = _id(event.get("tool_use_id"))
            counter = {"PreToolUse": "pre", "PostToolUse": "post", "PostToolUseFailure": "failure"}[kind]
            tools[counter] += 1
            if kind == "PreToolUse":
                tools["explicit_child_pre" if actor else "untagged_pre"] += 1
            elif actor is None:
                tools["untagged_terminal"] += 1
            tools["missing_call_id"] += int(call_id is None)
            tools["missing_tool_name"] += int(_id(event.get("tool_name")) is None)
            tools["missing_session"] += int(session is None)
            tools["invalid_actor"] += int("agent_id" in event and actor is None)
            if session and call_id:
                _record_call(calls[session, call_id], event, kind, actor, event_count, active[session], tools)
    for (session, _), call in calls.items():
        _finish_call(call, session, first_start, tools, latest, lineage, links)
    lifecycle["distinct_children"] = len(first_start)
    lifecycle["open_at_end"] = sum(len(group) for group in active.values())
    return dict(events=event_count, sessions=len(sessions), lifecycle=lifecycle, tools=tools,
                latest_open=latest, lineage=lineage)
