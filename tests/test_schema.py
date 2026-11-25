from dataclasses import FrozenInstanceError, replace

import pytest

from swarmtrace.trace.schema import (
    ROLES,
    SCHEMA_VERSION,
    STATUSES,
    TOOLS,
    TraceEvent,
    TraceSchemaError,
    validate_event,
    validate_trace,
)
from swarmtrace.trace.tiers import Tier, project


def test_pinned_vocabulary() -> None:
    assert SCHEMA_VERSION == 1
    assert TOOLS == ("scan", "login", "list", "read", "write", "send", "recv")
    assert STATUSES == ("ok", "denied", "not_found", "error")
    assert ROLES == ("benign_solo", "benign_team", "offensive")


def test_event_is_frozen(event: TraceEvent) -> None:
    with pytest.raises(FrozenInstanceError):
        event.tick = 3


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema_version", 2), ("schema_version", True), ("schema_version", 1.0),
        ("run_id", "ABCDEF0123456789"), ("run_id", "0123456789abcde"),
        ("run_id", "0123456789abcdef\n"), ("run_id", 123),
        ("seq", -1), ("seq", 0.5), ("seq", True),
        ("tick", -1), ("tick", 1.5), ("tick", False),
        ("agent", "a-1234567g"), ("agent", "h-12345678"),
        ("agent", "a-ABCDEF12"), ("tool", "shell"), ("tool", None),
        ("target", "f-12345678"), ("target", "h-1234567g"),
        ("args", {"unexpected": 1}), ("args", []),
        ("result", {}), ("result", {"status": "ok"}),
        ("result", {"size": 0}), ("result", {"status": "unknown", "size": 0}),
        ("result", {"status": "ok", "size": -1}),
        ("result", {"status": "ok", "size": 0.5}),
        ("result", {"status": "ok", "size": True}),
        ("result", {"status": "ok", "size": 0, "text": "free text"}),
        ("result", []), ("content", "forbidden on scan"),
        ("content", 5), ("provenance", -1), ("provenance", 0),
        ("provenance", True), ("provenance", 0.5),
    ],
)
def test_invalid_fields_name_the_field(event: TraceEvent, field: str, value: object) -> None:
    with pytest.raises(TraceSchemaError, match=field):
        validate_event(replace(event, **{field: value}))


@pytest.mark.parametrize("tier", list(Tier))
@pytest.mark.parametrize(
    ("tool", "target", "args"),
    [
        ("scan", "h-12345678", {}),
        ("login", "h-12345678", {"credential": "c-12345678"}),
        ("list", "h-12345678", {"prefix": "folder/"}),
        ("read", "f-12345678", {}),
        ("write", "f-12345678", {"size": 4, "digest": "0123456789abcdef"}),
        ("send", "a-87654321", {"size": 4, "digest": "0123456789abcdef"}),
        ("recv", "a-87654321", {"size": 4, "digest": "0123456789abcdef"}),
    ],
)
def test_tool_shapes(
    event: TraceEvent, tool: str, target: str, args: dict[str, int | str], tier: Tier
) -> None:
    content = "x" if tool in ("read", "write", "send", "recv") else None
    valid = project(replace(event, tool=tool, target=target, args=args, content=content), tier)
    validate_event(valid, tier=tier)
    validate_trace([valid], tier=tier)
    with pytest.raises(TraceSchemaError, match="target"):
        validate_event(replace(valid, target="c-12345678"), tier=tier)
    with pytest.raises(TraceSchemaError, match="args"):
        validate_event(replace(valid, args={**valid.args, "extra": 1}), tier=tier)
    for key in valid.args:
        with pytest.raises(TraceSchemaError, match="args"):
            validate_event(
                replace(valid, args={k: v for k, v in valid.args.items() if k != key}), tier=tier
            )


@pytest.mark.parametrize("tier", [Tier.V1, Tier.V2])
@pytest.mark.parametrize(
    ("tool", "target", "args"),
    [
        ("login", "h-12345678", {"credential": "a-12345678"}),
        ("login", "h-12345678", {"credential": "c-ABCDEF12"}),
        ("list", "h-12345678", {"prefix": 1}),
        ("write", "f-12345678", {"size": -1, "digest": "0123456789abcdef"}),
        ("send", "a-87654321", {"size": 1.0, "digest": "0123456789abcdef"}),
        ("recv", "a-87654321", {"size": True, "digest": "0123456789abcdef"}),
        ("write", "f-12345678", {"size": 1, "digest": "ABCDEF0123456789"}),
        ("send", "a-87654321", {"size": 1, "digest": "0123456789abcde"}),
        ("recv", "a-87654321", {"size": 1, "digest": 123}),
    ],
)
def test_bad_tool_arguments(
    event: TraceEvent, tool: str, target: str, args: dict[str, object], tier: Tier
) -> None:
    content = "x" if tool in ("read", "write", "send", "recv") else None
    candidate = project(replace(event, tool=tool, target=target, args=args, content=content), tier)
    with pytest.raises(TraceSchemaError, match="args"):
        validate_event(candidate, tier=tier)


@pytest.mark.parametrize("tool", TOOLS)
@pytest.mark.parametrize("status", STATUSES)
@pytest.mark.parametrize("content", [None, "", "text", 1])
def test_content_visibility(
    event: TraceEvent, tool: str, status: str, content: object
) -> None:
    target = "h-12345678"
    args = {}
    if tool == "login":
        args = {"credential": "c-12345678"}
    elif tool == "list":
        args = {"prefix": ""}
    elif tool in ("read", "write"):
        target = "f-12345678"
    elif tool in ("send", "recv"):
        target = "a-87654321"
    if tool in ("write", "send", "recv"):
        args = {"size": 1, "digest": "0123456789abcdef"}
    candidate = replace(
        event, tool=tool, target=target, args=args, content=content,
        result={"status": status, "size": 0},
    )
    needs_content = status == "ok" and tool in ("read", "write", "send", "recv")
    valid = isinstance(content, str) if needs_content else content is None
    if valid:
        validate_event(candidate)
        validate_trace([candidate])
    else:
        with pytest.raises(TraceSchemaError, match="content"):
            validate_event(candidate)
        with pytest.raises(TraceSchemaError, match="content"):
            validate_trace([candidate])


@pytest.mark.parametrize("status", STATUSES)
def test_statuses(event: TraceEvent, status: str) -> None:
    validate_event(replace(event, result={"status": status, "size": 0}))


@pytest.mark.parametrize("tier", list(Tier))
@pytest.mark.parametrize(
    ("changes", "field"),
    [
        ({"run_id": "fedcba9876543210"}, "run_id"),
        ({"seq": 2}, "seq"),
        ({"seq": 0}, "seq"),
        ({"tick": 1}, "tick"),
        ({"tool": "unknown"}, "tool"),
    ],
)
def test_invalid_trace_order(
    event: TraceEvent, changes: dict[str, object], field: str, tier: Tier
) -> None:
    first = replace(event, tick=2)
    second = replace(first, seq=1, tick=2)
    with pytest.raises(TraceSchemaError, match=field):
        validate_trace([first, replace(second, **changes)], tier=tier)


def test_trace_starts_at_zero_and_is_not_empty(event: TraceEvent) -> None:
    with pytest.raises(TraceSchemaError, match="seq"):
        validate_trace([replace(event, seq=1)])
    with pytest.raises(TraceSchemaError, match="events"):
        validate_trace([])
    validate_trace([event, replace(event, seq=1)])


def receipt(event: TraceEvent, seq: int = 0) -> TraceEvent:
    return replace(
        event, seq=seq, tool="recv", target="a-87654321",
        args={"size": 1, "digest": "0123456789abcdef"}, content="x",
        result={"status": "ok", "size": 1},
    )


def test_provenance_requires_same_agent_and_receipt(event: TraceEvent) -> None:
    received = receipt(event)
    followup = replace(event, seq=1, provenance=0)
    validate_trace([received, followup])
    for source in [event, replace(received, agent="a-87654321")]:
        with pytest.raises(TraceSchemaError, match="provenance"):
            validate_trace([source, followup])
    for pointer in [1, 2, None]:
        with pytest.raises(TraceSchemaError, match="provenance"):
            validate_trace([received, replace(followup, provenance=pointer)])


def test_provenance_uses_most_recent_receipt(event: TraceEvent) -> None:
    first = receipt(event)
    second = replace(receipt(event, 1), provenance=0)
    third = replace(event, seq=2, provenance=1)
    validate_trace([first, second, third])
    with pytest.raises(TraceSchemaError, match="provenance"):
        validate_trace([first, second, replace(third, provenance=0)])


@pytest.mark.parametrize(
    "changes",
    [{"target": "a-12345678"},
     {"result": {"status": "denied", "size": 0}, "content": None}],
)
def test_provenance_does_not_use_non_receipts(
    event: TraceEvent, changes: dict[str, object]
) -> None:
    first = replace(receipt(event), **changes)
    validate_trace([first, replace(event, seq=1)])
    with pytest.raises(TraceSchemaError, match="provenance"):
        validate_trace([first, replace(event, seq=1, provenance=0)])


def test_file_provenance_requires_another_agents_write(event: TraceEvent) -> None:
    written = replace(
        event, agent="a-87654321", tool="write", target="f-12345678",
        args={"size": 1, "digest": "0123456789abcdef"}, content="x",
        result={"status": "ok", "size": 1},
    )
    read = replace(event, seq=1, tool="read", target=written.target, content="x")
    followup = replace(event, seq=2, provenance=1)
    validate_trace([written, read, followup])
    for source in [
        replace(written, agent=event.agent),
        replace(written, result={"status": "denied", "size": 0}, content=None),
        replace(written, target="f-87654321"),
    ]:
        validate_trace([source, read, replace(followup, provenance=None)])
        with pytest.raises(TraceSchemaError, match="provenance"):
            validate_trace([source, read, followup])


def test_empty_recv_content_still_counts_as_receipt(event: TraceEvent) -> None:
    received = replace(
        receipt(event), content="", result={"status": "ok", "size": 0},
        args={"size": 0, "digest": "e3b0c44298fc1c14"},
    )
    followup = replace(event, seq=1, provenance=0)
    validate_trace([received, followup])
    with pytest.raises(TraceSchemaError, match="provenance"):
        validate_trace([received, replace(followup, provenance=None)])
    with pytest.raises(TraceSchemaError, match="content"):
        validate_trace([replace(received, content=None), followup])
    with pytest.raises(TraceSchemaError, match="content"):
        validate_trace([replace(received, content=None), replace(followup, provenance=None)])


@pytest.mark.parametrize("status", ["denied", "not_found", "error"])
@pytest.mark.parametrize("tool", ["read", "recv"])
def test_failed_receipts_do_not_advance_provenance(
    event: TraceEvent, status: str, tool: str
) -> None:
    written = replace(
        event, agent="a-87654321", tool="write", target="f-12345678",
        args={"size": 1, "digest": "0123456789abcdef"}, content="x",
    )
    received = receipt(event, seq=1)
    failed = replace(
        received, seq=2, tool=tool, provenance=1, content=None,
        target="f-12345678" if tool == "read" else received.target,
        args={} if tool == "read" else received.args, result={"status": status, "size": 0},
    )
    followup = replace(event, seq=3, provenance=1)
    validate_trace([written, received, failed, followup])
    with pytest.raises(TraceSchemaError, match="provenance"):
        validate_trace([written, received, failed, replace(followup, provenance=2)])


@pytest.mark.parametrize("status", ["denied", "not_found", "error"])
def test_failed_write_does_not_replace_last_ok_writer(event: TraceEvent, status: str) -> None:
    written = replace(
        event, agent="a-87654321", tool="write", target="f-12345678",
        args={"size": 0, "digest": "e3b0c44298fc1c14"}, content="",
    )
    failed_write = replace(
        written, seq=1, agent=event.agent, content=None, result={"status": status, "size": 0}
    )
    read = replace(event, seq=2, tool="read", target=written.target, content="")
    followup = replace(event, seq=3, provenance=2)
    validate_trace([written, failed_write, read, followup])
    with pytest.raises(TraceSchemaError, match="provenance"):
        validate_trace([written, failed_write, read, replace(followup, provenance=None)])


def test_file_overwrite_changes_provenance_source(event: TraceEvent) -> None:
    written = replace(
        event, agent="a-87654321", tool="write", target="f-12345678",
        args={"size": 1, "digest": "0123456789abcdef"}, content="x",
    )
    own_write = replace(written, seq=1, agent=event.agent)
    read = replace(event, seq=2, tool="read", target=written.target, content="x")
    validate_trace([written, own_write, read, replace(event, seq=3)])
    with pytest.raises(TraceSchemaError, match="provenance"):
        validate_trace([written, own_write, read, replace(event, seq=3, provenance=2)])
