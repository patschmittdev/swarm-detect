import json
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from .schema import TraceEvent, TraceSchemaError, validate_trace
from .tiers import Tier, project


@dataclass(frozen=True)
class Trace:
    run_id: str
    tier: Tier
    events: tuple[TraceEvent, ...]

    @property
    def agents(self) -> tuple[str, ...]:
        return tuple(sorted({event.agent for event in self.events}))


@dataclass(frozen=True)
class AgentLabel:
    role: str
    group: str | None


@dataclass(frozen=True)
class Labels:
    run_id: str
    agents: Mapping[str, AgentLabel]
    objective_completed: bool
    objective_tick: int | None


@dataclass(frozen=True)
class Manifest:
    run_id: str
    seed: int
    condition: Mapping[str, int | str]
    code_version: str


@dataclass(frozen=True)
class RunPaths:
    run_dir: Path

    @property
    def trace(self) -> Path:
        return self.run_dir / "trace.jsonl"

    @property
    def labels(self) -> Path:
        return self.run_dir / "labels.json"

    @property
    def manifest(self) -> Path:
        return self.run_dir / "manifest.json"

    @property
    def context(self) -> Path:
        return self.run_dir / "context.json"

    @property
    def outcomes(self) -> Path:
        return self.run_dir / "outcomes.json"

    @property
    def authorization(self) -> Path:
        return self.run_dir / "authorization.json"

    @property
    def interventions(self) -> Path:
        return self.run_dir / "interventions.jsonl"


def _serialize(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"


def write_trace(path: str | Path, events: Iterable[TraceEvent]) -> None:
    records = tuple(events)
    validate_trace(records, tier=Tier.V2)
    with Path(path).open("w", encoding="utf-8", newline="\n") as stream:
        for event in records:
            stream.write(_serialize(asdict(event)))


def read_trace(path: str | Path, tier: Tier = Tier.V2) -> Trace:
    events = []
    expected = {field.name for field in fields(TraceEvent)}
    with Path(path).open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            try:
                record = json.loads(line)
            except json.JSONDecodeError as error:
                raise TraceSchemaError(f"event at line {line_number}: invalid JSON") from error
            if not isinstance(record, dict):
                raise TraceSchemaError(f"event at line {line_number}: expected an object")
            if set(record) != expected:
                raise TraceSchemaError(
                    f"event fields at line {line_number}: missing {sorted(expected - set(record))}, "
                    f"unexpected {sorted(set(record) - expected)}"
                )
            events.append(TraceEvent(**record))
    validate_trace(events, tier=Tier.V2)
    projected = tuple(project(event, tier) for event in events)
    validate_trace(projected, tier=tier)
    return Trace(events[0].run_id, tier, projected)


def write_labels(path: str | Path, labels: Labels) -> None:
    Path(path).write_text(_serialize(asdict(labels)), encoding="utf-8", newline="\n")


def read_labels(path: str | Path) -> Labels:
    record = json.loads(Path(path).read_text(encoding="utf-8"))
    return Labels(
        run_id=record["run_id"],
        agents={agent: AgentLabel(**label) for agent, label in record["agents"].items()},
        objective_completed=record["objective_completed"],
        objective_tick=record["objective_tick"],
    )


def write_manifest(path: str | Path, manifest: Manifest) -> None:
    Path(path).write_text(_serialize(asdict(manifest)), encoding="utf-8", newline="\n")


def read_manifest(path: str | Path) -> Manifest:
    return Manifest(**json.loads(Path(path).read_text(encoding="utf-8")))
