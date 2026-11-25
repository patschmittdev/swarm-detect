"""Load and validate one window of service requests."""

import json
import math
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from os import PathLike
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Event:
    seq: int
    t_start: int | float
    t_end: int | float
    token_id: str | None
    user_agent: str
    method: str
    path: str
    query: str
    status: int
    bytes_in: int
    bytes_out: int
    write_sha256: str | None


def _time(value: object, field: str) -> int | float:
    if type(value) is int and value >= 0:
        return value
    if type(value) is float and math.isfinite(value) and value >= 0:
        return value
    raise ValueError(f"{field} must be a finite nonnegative number")


def _event(row: dict) -> Event:
    if not isinstance(row, dict):
        raise ValueError("expected a JSON object")
    for field in ("seq", "bytes_in", "bytes_out"):
        if type(row[field]) is not int or row[field] < 0:
            raise ValueError(f"{field} must be a nonnegative integer")
    if type(row["status"]) is not int or not 100 <= row["status"] <= 599:
        raise ValueError("status must be an HTTP status integer between 100 and 599")
    for field in ("user_agent", "method", "path", "query"):
        if not isinstance(row[field], str):
            raise ValueError(f"{field} must be a string")
    if not row["method"] or not row["path"].startswith("/"):
        raise ValueError("method must be nonempty and path must start with /")
    for field in ("token_id", "write_sha256"):
        if row[field] is not None and (
            not isinstance(row[field], str) or not row[field]
        ):
            raise ValueError(f"{field} must be a nonempty string or null")
    start = _time(row["t_start"], "t_start")
    end = _time(row["t_end"], "t_end")
    if end < start:
        raise ValueError("t_end must be at least t_start")
    return Event(
        row["seq"], start, end, row["token_id"], row["user_agent"], row["method"], row["path"],
        row["query"], row["status"], row["bytes_in"], row["bytes_out"], row["write_sha256"],
    )


def events_from_rows(rows: Iterable[dict]) -> tuple[Event, ...]:
    """Validate rows and return immutable events sorted by completion sequence."""
    events = []
    seen = set()
    for number, row in enumerate(rows, start=1):
        try:
            event = _event(row)
            if event.seq in seen:
                raise ValueError(f"duplicate seq {event.seq}")
        except KeyError as exc:
            raise ValueError(f"row {number}: missing field {exc.args[0]}") from exc
        except ValueError as exc:
            raise ValueError(f"row {number}: {exc}") from exc
        seen.add(event.seq)
        events.append(event)
    return tuple(sorted(events, key=lambda event: event.seq))


def _json_rows(lines: Iterable[str]) -> Iterator[dict]:
    for number, line in enumerate(lines, start=1):
        try:
            yield json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"row {number}: invalid JSON at column {exc.colno}") from exc


def load_events(path: str | PathLike[str]) -> tuple[Event, ...]:
    """Read a UTF-8 JSONL window, with the filename and row in validation errors."""
    try:
        with Path(path).open(encoding="utf-8-sig") as source:
            return events_from_rows(_json_rows(source))
    except ValueError as exc:
        raise ValueError(f"{path}: {exc}") from exc
