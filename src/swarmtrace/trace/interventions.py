import json
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

from .io import _serialize
from .schema import TraceEvent
from .tiers import Tier

KINDS = ("quarantine", "revoke_credential", "halt_all")
# Applied engine records also include channel cuts, unlike neutral Decisions.
_RECORD_KINDS = (*KINDS, "cut_channel")


@dataclass(frozen=True)
class Decision:
    kind: str
    agent: str | None = None
    credential: str | None = None


@dataclass(frozen=True)
class InterventionRecord:
    tick: int
    effective_tick: int
    kind: str
    agent: str | None
    credential: str | None


class Controller(Protocol):
    tier: Tier

    def observe(self, tick: int, events: tuple[TraceEvent, ...]) -> Sequence[Decision]: ...


def _from_record(record: object) -> InterventionRecord:
    if not isinstance(record, dict) or set(record) != {
        "tick", "effective_tick", "kind", "agent", "credential",
    }:
        raise ValueError("intervention must have exactly the schema fields")
    if any(type(record[key]) is not int or record[key] < 0
           for key in ("tick", "effective_tick")):
        raise ValueError("intervention ticks must be non-negative integers")
    if record["kind"] not in _RECORD_KINDS:
        raise ValueError("unknown intervention kind")
    if any(record[key] is not None and not isinstance(record[key], str)
           for key in ("agent", "credential")):
        raise ValueError("intervention identifiers must be strings or null")
    return InterventionRecord(**record)


def write_interventions(path: str | Path, records: Iterable[InterventionRecord]) -> None:
    """Write applied interventions in canonical JSONL, including an empty run."""
    lines = []
    for record in records:
        row = asdict(record)
        _from_record(row)
        lines.append(_serialize(row))
    Path(path).write_text("".join(lines), encoding="utf-8", newline="\n")


def read_interventions(path: str | Path) -> tuple[InterventionRecord, ...]:
    with Path(path).open(encoding="utf-8") as stream:
        return tuple(_from_record(json.loads(line)) for line in stream)
