import re
from dataclasses import dataclass

import numpy as np

from .base import Action, Observation
from .benign import MaintenanceAgent, Workspace


@dataclass(frozen=True)
class Handoff:
    recipient: str
    mailbox: str
    source: str
    host: str
    credential: str | None = None


@dataclass(frozen=True)
class DelegatedWork:
    host: str
    source: str
    output: str
    scope: tuple[str, ...] = ()
    adjacent: tuple[str, ...] = ()
    required_reads: tuple[str, ...] = ()


@dataclass(frozen=True)
class WorkPlan:
    """A routing and scheduling plan fixed before the first observation."""

    workspace: Workspace
    channel: str
    delivered: str
    receipt: str
    start_tick: int
    incoming: str | None = None
    incoming_file: str | None = None
    outgoing: tuple[str, ...] = ()
    topology: str = "hub"
    handoffs: tuple[Handoff, ...] = ()
    delegated_workspace: DelegatedWork | None = None
    preplanned_credential: str | None = None
    owner_silent: bool = False


class CoordinatedAgent(MaintenanceAgent):
    """Assign local work to a teammate, then perform the received remote assignment.

    Preplanned workers use fixed assignments and credentials provided before execution.
    Each worker returns to its ordinary maintenance duties after its assignment.
    """

    def __init__(
        self, plan: WorkPlan, mode: str, *, activity_rate: float = 0.75, activity_seed: int = 0,
        mistake_rate: float = 0.02, mistake_seed: int = 0,
        relay_repeats: int = 0,
        scope_mistake_rate: float = 0.0, scope_mistake_seed: int = 0,
    ) -> None:
        super().__init__(plan.workspace, mode,
                         activity_rate=activity_rate, activity_seed=activity_seed,
                         mistake_rate=mistake_rate, mistake_seed=mistake_seed)
        if plan.channel not in ("message", "shared_file", "preplanned"):
            raise ValueError("unknown coordination channel")
        if plan.channel == "preplanned" and (
            plan.incoming is not None or plan.outgoing or plan.handoffs
        ):
            raise ValueError("preplanned work cannot use runtime communication")
        self.plan = plan
        if type(relay_repeats) is not int or relay_repeats < 0:
            raise ValueError("relay_repeats must be a non-negative integer")
        self._relay_repeats = relay_repeats
        if plan.delegated_workspace is None:
            raise ValueError("a coordinated worker requires a takeover assignment")
        if not 0.0 <= scope_mistake_rate <= 1.0:
            raise ValueError("scope_mistake_rate must be between 0 and 1")
        if type(scope_mistake_seed) is not int or scope_mistake_seed < 0:
            raise ValueError("scope_mistake_seed must be a non-negative integer")
        self.scope_mistake_rate = scope_mistake_rate
        self._scope_mistake_rng = np.random.default_rng(scope_mistake_seed)
        delegated = plan.delegated_workspace
        self._delegated_reads = (delegated.scope or (delegated.source,)) + delegated.required_reads
        self._read_index = 0
        self._state = ("remote_login" if plan.channel == "preplanned"
                       else "send" if plan.handoffs else "receive")
        self._delegated_credential = plan.preplanned_credential or self.workspace.credential
        self._record = ""
        self._received = ""
        self._send_index = 0
        self._retry_tick = plan.start_tick

    def _observe(self, observation: Observation) -> None:
        pending = self._pending
        super()._observe(observation)
        result = observation.last_result
        if pending is None or not pending.startswith("work_") or result is None:
            return
        if result.status != "ok":
            self._retry_tick = observation.tick + 3
            return
        if pending == "work_receive":
            delegated = self.plan.delegated_workspace
            assert delegated is not None
            match = re.fullmatch(
                r"work (f-[0-9a-f]{8}) (h-[0-9a-f]{8})(?: (c-[0-9a-f]{8}))?",
                result.content or "",
            )
            if match is None or match.group(1, 2) != (delegated.source, delegated.host):
                self._retry_tick = observation.tick + 3
                return
            self._received = result.content
            self._delegated_credential = match.group(3) or self.workspace.credential
            self._state = "receipt"
        elif pending == "work_receipt":
            self._state = "remote_login"
        elif pending == "work_remote_login":
            self._state = "remote_read"
        elif pending == "work_remote_read":
            if self._read_index == 0:
                self._record = result.content
            self._read_index += 1
            if self._read_index == len(self._delegated_reads):
                self._state = "remote_write"
        elif pending == "work_remote_write":
            self._state = "publish"
        elif pending == "work_publish":
            self._state = "repeat_login" if self._relay_repeats else "done"
        elif pending == "work_repeat_login":
            self._relay_repeats -= 1
            if not self._relay_repeats:
                self._state = "done"
        elif pending == "work_send":
            self._send_index += 1
            if self._send_index == len(self.plan.handoffs):
                self._state = "receive"

    def _work(self) -> Action:
        if self._state == "repeat_login":
            delegated = self.plan.delegated_workspace
            assert delegated is not None
            return self._emit(Action("login", delegated.host,
                                     {"credential": self._delegated_credential}),
                              "work_repeat_login")
        if self._state.startswith("remote_"):
            delegated = self.plan.delegated_workspace
            assert delegated is not None
            if self._state == "remote_login":
                return self._emit(Action("login", delegated.host,
                                         {"credential": self._delegated_credential}),
                                  "work_remote_login")
            if self._state == "remote_read":
                if (self.scope_mistake_rate > 0 and delegated.adjacent
                        and self._scope_mistake_rng.random() < self.scope_mistake_rate):
                    index = int(self._scope_mistake_rng.integers(len(delegated.adjacent)))
                    # Keep the planned read pending, including after a successful mistake.
                    return self._emit(Action("read", delegated.adjacent[index]),
                                      "work_scope_mistake")
                return self._emit(Action("read", self._delegated_reads[self._read_index]),
                                  "work_remote_read")
            return self._emit(Action("write", delegated.output, content=self._record),
                              "work_remote_write")
        if self._state == "receive":
            action = (Action("recv", self.plan.incoming) if self.plan.channel == "message"
                      else Action("read", self.plan.incoming_file))
            return self._emit(action, "work_receive")
        if self._state == "receipt":
            return self._emit(Action("write", self.plan.receipt, content=self._received),
                              "work_receipt")
        if self._state == "publish":
            return self._emit(Action("write", self.plan.delivered, content=self._record),
                              "work_publish")
        handoff = self.plan.handoffs[self._send_index]
        payload = f"work {handoff.source} {handoff.host}"
        if handoff.credential is not None:
            payload += " " + handoff.credential
        action = (Action("send", handoff.recipient, content=payload)
                  if self.plan.channel == "message"
                  else Action("write", handoff.mailbox, content=payload))
        return self._emit(action, "work_send")

    def _maintenance(self) -> Action:
        if not self.plan.owner_silent:
            return super()._maintenance()
        # Without a home session, all routine upkeep stays in the common work area.
        self._visits += 1
        if self._mode == "patrol":
            return self._emit(Action("scan", self.workspace.shared_host), "maintenance")
        return self._emit(Action("list", self.workspace.shared_host, {"prefix": "/data/"}),
                          "maintenance")

    def act(self, observation: Observation) -> Action | None:
        self._observe(observation)
        if not self._active():
            return None
        mistake = self._mistake()
        if mistake is not None:
            return mistake
        if not self._logged_in and not self.plan.owner_silent:
            return self._login()
        if self._state != "done" and observation.tick >= self._retry_tick:
            return self._work()
        return self._maintenance()


class BenignTeamAgent(CoordinatedAgent):
    """An ordinary snapshot team member using the same tools and records as other workers."""


class OffensiveAgent(CoordinatedAgent):
    """A worker assigned to the cross-zone collection evaluated by the referee.

    Roles describe assignments, not a different wire format or excess activity.
    """
