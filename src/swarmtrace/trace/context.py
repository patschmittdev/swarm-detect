from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path

from .io import _serialize
from .schema import SCHEMA_VERSION


class ContextLevel(Enum):
    C0 = "C0"
    C1 = "C1"
    C2 = "C2"


@dataclass(frozen=True)
class HandoffScope:
    sender: str
    receiver: str
    host: str
    files: tuple[str, ...]


@dataclass(frozen=True)
class Context:
    run_id: str
    level: ContextLevel
    credentials: Mapping[str, str]
    handoffs: tuple[HandoffScope, ...]

    @classmethod
    def empty(cls, run_id: str) -> Context:
        return cls(run_id, ContextLevel.C0, {}, ())


def project_context(context: Context, level: ContextLevel) -> Context:
    if level is ContextLevel.C0:
        return Context.empty(context.run_id)
    if level is ContextLevel.C1:
        return replace(context, level=level, credentials=dict(context.credentials), handoffs=())
    if level is ContextLevel.C2:
        return replace(context, level=level, credentials=dict(context.credentials))
    raise ValueError(f"Unknown context level: {level!r}")


def _from_record(record: object) -> Context:
    if not isinstance(record, dict) or set(record) != {
        "schema_version", "run_id", "credentials", "handoffs",
    }:
        raise ValueError("context must have exactly the schema fields")
    if type(record["schema_version"]) is not int or record["schema_version"] != SCHEMA_VERSION:
        raise ValueError("unsupported context schema_version")
    if not isinstance(record["run_id"], str):
        raise ValueError("context run_id must be a string")
    credentials = record["credentials"]
    if not isinstance(credentials, dict) or any(
        not isinstance(key, str) or not isinstance(value, str)
        for key, value in credentials.items()
    ):
        raise ValueError("context credentials must map strings to strings")
    if not isinstance(record["handoffs"], list):
        raise ValueError("context handoffs must be a list")
    handoffs = []
    for row in record["handoffs"]:
        if not isinstance(row, dict) or set(row) != {"sender", "receiver", "host", "files"}:
            raise ValueError("handoff must have exactly sender, receiver, host and files")
        if (any(not isinstance(row[key], str) for key in ("sender", "receiver", "host"))
                or not isinstance(row["files"], list)
                or any(not isinstance(file, str) for file in row["files"])):
            raise ValueError("handoff identifiers must be strings")
        handoffs.append(HandoffScope(row["sender"], row["receiver"], row["host"],
                                     tuple(sorted(row["files"]))))
    return Context(record["run_id"], ContextLevel.C2, dict(credentials),
                   tuple(sorted(handoffs, key=lambda handoff: (handoff.receiver, handoff.sender))))


def write_context(path: str | Path, context: Context) -> None:
    """Write a full C2 record in the canonical run format, never a projection."""
    if context.level is not ContextLevel.C2:
        raise ValueError("context on disk must be C2")
    record = {
        "schema_version": SCHEMA_VERSION, "run_id": context.run_id,
        "credentials": dict(context.credentials),
        "handoffs": [
            {"sender": handoff.sender, "receiver": handoff.receiver, "host": handoff.host,
             "files": list(handoff.files)}
            for handoff in context.handoffs
        ],
    }
    full = _from_record(record)
    record["handoffs"] = [
        {"sender": handoff.sender, "receiver": handoff.receiver, "host": handoff.host,
         "files": list(handoff.files)}
        for handoff in full.handoffs
    ]
    Path(path).write_text(_serialize(record), encoding="utf-8", newline="\n")


def read_context(path: str | Path, level: ContextLevel = ContextLevel.C2) -> Context:
    """Load full context before projecting; an absent C0 file has an unknown run id."""
    if not isinstance(level, ContextLevel):
        raise ValueError(f"Unknown context level: {level!r}")
    try:
        text = Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        if level is ContextLevel.C0:
            return Context.empty("")
        raise
    return project_context(_from_record(json.loads(text)), level)
