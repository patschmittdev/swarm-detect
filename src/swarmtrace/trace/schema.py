import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from .tiers import Tier

SCHEMA_VERSION = 1
TOOLS = ("scan", "login", "list", "read", "write", "send", "recv")
STATUSES = ("ok", "denied", "not_found", "error")
ROLES = ("benign_solo", "benign_team", "offensive")


class TraceSchemaError(ValueError):
    """A field violates the trace contract."""


@dataclass(frozen=True)
class TraceEvent:
    schema_version: int
    run_id: str
    seq: int
    tick: int
    agent: str
    tool: str
    target: str
    args: Mapping[str, int | str]
    result: Mapping[str, int | str]
    content: str | None
    provenance: int | None


def _require(condition: bool, field: str, description: str) -> None:
    if not condition:
        raise TraceSchemaError(f"{field}: {description}")


def _integer(value: object, field: str) -> None:
    _require(type(value) is int and value >= 0, field, "expected a non-negative integer")


def _identifier(value: object, prefix: str, field: str) -> None:
    pattern = re.escape(prefix) + ("[0-9a-f]{8}" if prefix else "[0-9a-f]{16}")
    _require(isinstance(value, str) and re.fullmatch(pattern, value) is not None,
             field, f"expected {pattern}")


def _keys(value: object, expected: set[str], field: str) -> None:
    _require(isinstance(value, Mapping), field, "expected a mapping")
    _require(set(value) == expected, field, f"expected exactly {sorted(expected)}")


def validate_event(event: TraceEvent, tier: Tier = Tier.V2) -> None:
    _require(isinstance(event, TraceEvent), "event", "expected TraceEvent")
    _require(isinstance(tier, Tier), "tier", "expected Tier")
    _require(type(event.schema_version) is int and event.schema_version == SCHEMA_VERSION,
             "schema_version", "expected 1")
    _identifier(event.run_id, "", "run_id")
    _integer(event.seq, "seq")
    _integer(event.tick, "tick")
    _identifier(event.agent, "a-", "agent")
    _require(event.tool in TOOLS, "tool", "unknown tool")
    target_prefix = {
        "scan": "h-", "login": "h-", "list": "h-", "read": "f-",
        "write": "f-", "send": "a-", "recv": "a-",
    }[event.tool]
    _identifier(event.target, target_prefix, "target")
    argument_keys = {
        "scan": set(), "login": {"credential"}, "list": {"prefix"}, "read": set(),
        "write": {"size", "digest"}, "send": {"size", "digest"}, "recv": {"size", "digest"},
    }[event.tool]
    if tier is Tier.V0:
        _keys(event.args, set(), "args")
    else:
        _keys(event.args, argument_keys, "args")
        if event.tool == "login":
            _identifier(event.args["credential"], "c-", "args.credential")
        elif event.tool == "list":
            _require(isinstance(event.args["prefix"], str), "args.prefix", "expected a string")
        elif event.tool in ("write", "send", "recv"):
            _integer(event.args["size"], "args.size")
            _identifier(event.args["digest"], "", "args.digest")
    _keys(event.result, {"status", "size"}, "result")
    _require(event.result["status"] in STATUSES, "result.status", "unknown status")
    _integer(event.result["size"], "result.size")
    if tier is Tier.V0:
        _require(event.result["size"] == 0, "result.size", "must be 0 at V0")
    needs_content = (
        tier is Tier.V2
        and event.result["status"] == "ok"
        and event.tool in ("read", "write", "send", "recv")
    )
    if needs_content:
        _require(isinstance(event.content, str), "content", "expected a string on an ok V2 content tool")
    else:
        _require(event.content is None, "content", "must be null for this tier, tool and status")
    if tier is Tier.V2:
        if event.provenance is not None:
            _integer(event.provenance, "provenance")
            _require(event.provenance < event.seq, "provenance", "must refer to an earlier seq")
    else:
        _require(event.provenance is None, "provenance", "must be null at V0 and V1")


def validate_trace(events: Iterable[TraceEvent], tier: Tier = Tier.V2) -> None:
    run_id: str | None = None
    previous_tick = 0
    latest_receipt: dict[str, int] = {}
    file_writers: dict[str, str] = {}
    for seq, event in enumerate(events):
        validate_event(event, tier=tier)
        if run_id is None:
            run_id = event.run_id
        _require(event.run_id == run_id, "run_id", "must be the same throughout the trace")
        _require(event.seq == seq, "seq", "must be contiguous from 0")
        _require(event.tick >= previous_tick, "tick", "must be non-decreasing")
        if tier is Tier.V2:
            _require(event.provenance == latest_receipt.get(event.agent), "provenance",
                     "must be the most recent earlier receipt of another agent's content")
        previous_tick = event.tick
        if tier is Tier.V2 and event.result["status"] == "ok":
            if event.tool == "write":
                file_writers[event.target] = event.agent
            received_message = event.tool == "recv" and event.target != event.agent
            read_writer = file_writers.get(event.target)
            received_file = event.tool == "read" and read_writer not in (None, event.agent)
            if received_message or received_file:
                latest_receipt[event.agent] = seq
    _require(run_id is not None, "events", "expected at least one event")
