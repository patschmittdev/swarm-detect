import hashlib
from collections.abc import Iterable, Mapping
from copy import deepcopy
from pathlib import Path

from swarmtrace.agents.base import Action
from swarmtrace.trace import io
from swarmtrace.trace.authorization import ReadAudit, write_authorization
from swarmtrace.trace.context import Context, write_context
from swarmtrace.trace.interventions import InterventionRecord, write_interventions
from swarmtrace.trace.schema import SCHEMA_VERSION, TraceEvent, validate_event
from swarmtrace.world import ToolResult


class Recorder:
    """The sole event constructor and trace writer in the simulation."""

    def __init__(self, run_id: str) -> None:
        self._run_id = run_id
        self._events: list[TraceEvent] = []
        self._latest_receipt: dict[str, int] = {}
        self._file_writers: dict[str, str] = {}

    @property
    def events(self) -> tuple[TraceEvent, ...]:
        return tuple(deepcopy(event) for event in self._events)

    @property
    def next_seq(self) -> int:
        return len(self._events)

    def record(self, tick: int, agent: str, action: Action, result: ToolResult) -> TraceEvent:
        args = dict(action.args)
        if action.tool in ("write", "send", "recv"):
            payload = (result.content or "") if action.tool == "recv" else action.content
            encoded = payload.encode("utf-8")
            args = {"size": len(encoded), "digest": hashlib.sha256(encoded).hexdigest()[:16]}
        content = None
        if result.status == "ok" and action.tool in ("read", "write", "send", "recv"):
            content = result.content
        event = TraceEvent(
            schema_version=SCHEMA_VERSION, run_id=self._run_id, seq=len(self._events),
            tick=tick, agent=agent, tool=action.tool, target=action.target, args=args,
            result={"status": result.status, "size": result.size}, content=content,
            provenance=self._latest_receipt.get(agent),
        )
        validate_event(event)
        if self._events and tick < self._events[-1].tick:
            raise ValueError("tick must be non-decreasing")
        self._events.append(event)
        if result.status == "ok":
            if action.tool == "write":
                self._file_writers[action.target] = agent
            received_message = action.tool == "recv" and action.target != agent
            received_file = (
                action.tool == "read" and self._file_writers.get(action.target) not in (None, agent)
            )
            if received_message or received_file:
                self._latest_receipt[agent] = event.seq
        return deepcopy(event)

    def write(self, path: str | Path) -> None:
        io.write_trace(path, self.events)


def write_metadata(paths: io.RunPaths, labels: io.Labels, manifest: io.Manifest) -> None:
    """Keep all run artifact writes at the recorder boundary."""
    if labels.run_id != manifest.run_id:
        raise ValueError("metadata must refer to the same run")
    io.write_labels(paths.labels, labels)
    io.write_manifest(paths.manifest, manifest)


def write_run_extras(paths: io.RunPaths, context: Context, outcomes: Mapping[str, object]) -> None:
    """Keep the scope-enabled context and outcome writes at the recorder boundary."""
    if context.run_id != outcomes.get("run_id"):
        raise ValueError("context and outcomes must refer to the same run")
    serialized = io._serialize(dict(outcomes))
    write_context(paths.context, context)
    paths.outcomes.write_text(serialized, encoding="utf-8", newline="\n")


def write_run_interventions(paths: io.RunPaths, records: Iterable[InterventionRecord]) -> None:
    """Keep the controller's applied intervention log at the recorder boundary."""
    write_interventions(paths.interventions, records)


def write_run_authorization(paths: io.RunPaths, audit: ReadAudit) -> None:
    write_authorization(paths.authorization, audit)
