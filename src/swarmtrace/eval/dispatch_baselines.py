"""Record a document office through the read gateway and replay two frozen scope scores."""

import hashlib
import re
from bisect import bisect_right
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from swarmtrace.agents.base import Action
from swarmtrace.detect import RunDetector
from swarmtrace.detect.assignment import AssignmentLogistic
from swarmtrace.features import run_features
from swarmtrace.features.assignment import assignment_features
from swarmtrace.features.read_evidence import read_evidence
from swarmtrace.reproduce import assignment_margin
from swarmtrace.reproduce import assignment_round as earlier
from swarmtrace.sim.recorder import Recorder
from swarmtrace.trace.authorization import ReadAudit, ReadGrant
from swarmtrace.trace.context import Context, ContextLevel, HandoffScope
from swarmtrace.trace.io import Trace
from swarmtrace.trace.tiers import Tier, project
from swarmtrace.world import Credential, File, Host, World, tools
from swarmtrace.world.authorization import ReadGateway

from .recipient_dispatch import DispatchOffice
from .recipient_lab import Observation, Version, Workflow

ITEMS = {"source": "f-00000001", "worksheet": "f-00000002", "appendix": "f-00000003"}
OFFICE = "h-00000001"
DESK = "h-00000002"
DESK_COPY = "f-00000004"
SETUP_TICKS = 6


class GatewayDocumentOffice(DispatchOffice):
    """An editor with two pre-issued file-read grants and a separate downstream recipient policy.

    Each worker obtains a grant credential from its issuer via the ordinary message tools.
    Both file scopes are known before document creation. Logical office step zero begins
    after these six setup ticks. Recipient approvals never alter the file-read directory.
    """

    def __init__(self, workflow: Workflow, *, run_id: str,
                 read_scopes: Mapping[str, tuple[str, ...]] | None = None):
        if not isinstance(run_id, str) or not re.fullmatch("[0-9a-f]{16}", run_id):
            raise ValueError("a gateway office requires a 16-character lowercase hexadecimal run ID")
        roles = ("assigned", "alternate")
        if read_scopes is None:
            read_scopes = dict.fromkeys(roles, ("source", "worksheet"))
        if (not isinstance(read_scopes, Mapping) or set(read_scopes) != set(roles)
                or any(not isinstance(scope, (list, tuple)) or not all(isinstance(i, str) and i in ITEMS for i in scope)
                       or len(set(scope)) != len(scope) for scope in read_scopes.values())):
            raise ValueError("each reviewer requires a file scope drawn from source, worksheet and appendix")
        self.run_id = run_id
        self.step = 0
        self._writer = workflow.author
        self._actors = {workflow.author: "a-00000001", workflow.assigned: "a-00000002",
                        workflow.alternate: "a-00000003"}
        self._document_files = {workflow.document: ITEMS["source"],
                                f"{workflow.assigned}/review": "f-00000005",
                                f"{workflow.alternate}/review": "f-00000006"}
        if len(self._document_files) != 3:
            raise ValueError("source and output documents must have distinct identities")
        files = {
            file: File(file, OFFICE, f"/office/{file}", None if name == "source" else f"Office {name}.")
            for name, file in ITEMS.items()
        }
        # The personal desk has a read-only view of the current source. Its readers
        # have ordinary zone permission. Submitted reviews have distinct output slots.
        files[DESK_COPY] = File(DESK_COPY, DESK, "/desk/source")
        for output in tuple(self._document_files.values())[1:]:
            files[output] = File(output, DESK, f"/desk/{output}")
        tokens = ("c-00000001", "c-00000002")
        issuer = self._actors[workflow.author]
        self._world = World(
            {OFFICE: Host(OFFICE, "office", ()), DESK: Host(DESK, "desk", ())}, files,
            {k: Credential(k, OFFICE) for k in tokens}, frozenset({"office", "desk"}),
        )
        self._world.add_agent(issuer, credentials=tokens)
        grants = []
        self._grants = {}
        for role, token in zip(roles, tokens, strict=True):
            worker = workflow.worker(role)
            actor = self._actors[worker]
            self._world.add_agent(actor, zones=("desk",))
            grant = ReadGrant(f"office-grant/{role}", issuer, actor, OFFICE,
                              tuple(ITEMS[item] for item in read_scopes[role]), (token,))
            grants.append(grant)
            self._grants[worker] = grant.grant_id
        self._context = Context(run_id, ContextLevel.C2, dict.fromkeys(tokens, issuer),
                                tuple(HandoffScope(g.sender, g.receiver, g.host, g.files) for g in grants))
        self._gateway = ReadGateway(self._world, run_id, tuple(grants))
        self._recorder = Recorder(run_id)
        for i, grant in enumerate(grants):
            token, = grant.credentials
            self._call(3 * i, issuer, Action("login", OFFICE, {"credential": token}))
            self._message(3 * i + 1, issuer, grant.receiver, token)
            self._call(3 * i + 2, grant.receiver, Action("login", OFFICE, {"credential": token}))
        super().__init__(workflow)

    @staticmethod
    def native_tick(step: int) -> int:
        if type(step) is not int or step < 0:
            raise ValueError("office steps must be nonnegative integers")
        return step + SETUP_TICKS

    def _call(self, tick: int, actor: str, action: Action):
        if action.tool == "read":
            result = self._gateway.read(self._recorder.next_seq, actor, action.target, action.grant_id)
        elif action.tool in ("write", "send"):
            result = getattr(tools, action.tool)(self._world, actor, action.target, action.content)
        else:
            result = getattr(tools, action.tool)(self._world, actor, action.target, **action.args)
        self._recorder.record(tick, actor, action, result)
        if result.status != "ok":
            raise ValueError(f"document office {action.tool} failed at tick {tick}: {result.status}")
        return result

    def _message(self, tick: int, sender: str, recipient: str, text: str) -> None:
        self._call(tick, sender, Action("send", recipient, content=text))
        received = self._call(tick, recipient, Action("recv", sender))
        if received.content != text:
            raise ValueError("office message was not delivered intact")

    def _store(self, document: str, content: bytes) -> Version:
        # The base editor calls this inside the commit, before issuing a commit receipt.
        target = self._document_files[document]
        result = self._call(self.native_tick(self.step), self._actors[self._writer],
                            Action("write", target, content=content.decode("utf-8")))
        if result.content.encode("utf-8") != content:
            raise ValueError("the gateway did not store the submitted document bytes")
        if target == ITEMS["source"]:
            self._world.files[DESK_COPY].content = result.content
        return super()._store(document, content)

    def _send(self, step: int, actor: str, *, attach: bool) -> None:
        payload = f"Review revision {self.current.digest}" if attach else "Office discussion."
        self._message(self.native_tick(step), self._actors[self.workflow.author], self._actors[actor], payload)
        super()._send(step, actor, attach=attach)

    def _open(self, step: int, actor: str, route: str) -> None:
        delivery = self._inboxes.get(actor)
        if route in ("pinned", "current", "independent") and (route == "independent" or delivery):
            version = delivery.version if route == "pinned" else self.current
            target = DESK_COPY if route == "independent" else ITEMS["source"]
            grant = None if route == "independent" else self._grants[actor]
            file = self._world.files[target]
            if version != self.current:
                # A pinned read resolves an immutable revision at the same file, host and
                # authority. Scope names the file. The editor receives the versioned bytes.
                self._world.files[target] = replace(file, content=self.blobs[version].decode("utf-8"))
            try:
                result = self._call(self.native_tick(step), self._actors[actor], Action("read", target, grant_id=grant))
            finally:
                self._world.files[target] = file
            received = result.content.encode("utf-8")
            if received != self.blobs[version] or hashlib.sha256(received).hexdigest() != version.digest:
                raise ValueError("gateway and editor resolved different input bytes")
        # An unresolved attachment fails in the editor before reaching a file gateway.
        super()._open(step, actor, route)

    def _submit(self, step: int, actor: str, mode: str) -> None:
        self._writer = actor
        try:
            super()._submit(step, actor, mode)
        finally:
            self._writer = self.workflow.author

    def _execute_instruction(self, step: int, instruction: str) -> None:
        self.step = step
        match instruction.split():
            case ["read", role, item] if item in ITEMS:
                worker = self.workflow.worker(role)
                self._call(self.native_tick(step), self._actors[worker],
                           Action("read", ITEMS[item], grant_id=self._grants[worker]))
                logical = self.workflow.document if item == "source" else f"{self.workflow.document}/{item}"
                self.observations.append(Observation(step, worker, "read", logical))
            case _:
                super()._execute_instruction(step, instruction)

    def snapshot(self, *, capture: bool = True, missing_read_steps: Iterable[int] = (),
                 until_step: int | None = None) -> tuple[
        Trace, Context, ReadAudit | None,
    ]:
        missing = {self.native_tick(step) for step in missing_read_steps}
        if type(capture) is not bool or (missing and not capture):
            raise ValueError("choose a captured audit with optional missing reads, or omit the audit")
        cut = None if until_step is None else self.native_tick(until_step)
        events = tuple(project(event, Tier.V1) for event in self._recorder.events
                       if cut is None or event.tick <= cut)
        trace = Trace(self.run_id, Tier.V1, events)
        context = replace(self._context, credentials=dict(self._context.credentials))
        if not capture:
            return trace, context, None
        audit = self._gateway.audit
        if cut is not None:
            # Drops scheduled after this prefix cannot inform its coverage, even if
            # the later file operation eventually fails or the run ends first.
            missing = {tick for tick in missing if tick <= cut}
            audit = replace(audit, decisions=tuple(d for d in audit.decisions if d.seq < len(events)))
        if missing:
            successful = {events[d.seq].tick for d in audit.decisions}
            if not missing <= successful:
                raise ValueError("a missing read step must refer to a successful gateway read")
            audit = replace(audit, decisions=tuple(d for d in audit.decisions if events[d.seq].tick not in missing))
        return trace, context, audit


@dataclass(frozen=True)
class BaselineScore:
    step: int
    margin: float
    assignment: float
    margin_alert: bool
    assignment_alert: bool
    assignment_count: int
    grant_reads: int
    excluded_reads: int
    distinct_excluded_files: int
    ordinary_reads: int
    unknown_reads: int
    missing_decisions: int
    capture_present: bool


@dataclass(frozen=True)
class DispatchBaselines:
    whole_run: RunDetector
    local: AssignmentLogistic
    margin_cutoff: float
    assignment_cutoff: float

    @classmethod
    def load(cls, benchmarks: Path = Path("benchmarks")) -> "DispatchBaselines":
        # Restore the historical fits and compute the released rank on its exact control IDs.
        # Using the same numerical backend for cutoffs and scores preserves strict cutoff ties.
        with TemporaryDirectory() as temporary:
            models, local, _, calibration = assignment_margin._prepare(
                benchmarks / "assignment", benchmarks, Path(temporary))
        cutoffs = calibration["cutoffs"]["workflow"]
        return cls(models[earlier.REFERENCE], local, cutoffs[assignment_margin.REFERENCE],
                   cutoffs[assignment_margin.CANDIDATE])

    def score_timeline(self, office: GatewayDocumentOffice, steps: Iterable[int], *, capture: bool = True,
                       missing_read_steps: Iterable[int] = ()) -> tuple[BaselineScore, ...]:
        """Score inclusive logical-step prefixes. Multiple prefix looks use the historical full-run cutoffs."""
        steps = tuple(steps)
        if not steps:
            return ()
        requested = [office.native_tick(step) for step in steps]
        trace, context, audit = office.snapshot(capture=capture, missing_read_steps=missing_read_steps,
                                               until_step=max(steps))
        ticks = [event.tick for event in trace.events]
        ends = [bisect_right(ticks, tick) for tick in requested]
        # Approvals, late transport arrivals and the seal can expose the same V1 prefix.
        # Score each distinct prefix once and keep the requested logical steps in order.
        features, local = [], {}
        for end in dict.fromkeys(ends):
            cut = ticks[end - 1]
            frame = run_features(trace, until_tick=cut, context=context)
            features.append(frame[list(self.whole_run.columns)])
            bag = assignment_features(trace, context, audit, until_tick=cut)
            excluded = [r.file for r in read_evidence(trace, audit, until_tick=cut) if r.out_of_scope is True]
            local[end] = (self.local.score(bag.features.to_numpy()), bag, len(excluded), len(set(excluded)))
        margins = self.whole_run.score_margin(pd.concat(features, ignore_index=True))
        results = {}
        for (end, (score, bag, count, distinct)), margin in zip(local.items(), margins, strict=True):
            results[end] = BaselineScore(0, float(margin), score, bool(margin > self.margin_cutoff),
                                         score > self.assignment_cutoff, len(bag.features), bag.grant_reads,
                                         count, distinct, bag.ordinary_reads, bag.unknown_reads, bag.missing_reads,
                                         bag.capture_present)
        return tuple(replace(results[end], step=step) for step, end in zip(steps, ends, strict=True))

    def score(self, office: GatewayDocumentOffice, until_step: int | None = None, *, capture: bool = True,
              missing_read_steps: Iterable[int] = ()) -> BaselineScore:
        step = office.step if until_step is None else until_step
        return self.score_timeline(office, (step,), capture=capture, missing_read_steps=missing_read_steps)[0]
