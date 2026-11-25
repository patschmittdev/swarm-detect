from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from swarmtrace.agents.base import Action, Agent, Observation
from swarmtrace.trace.authorization import ReadAudit, ReadGrant
from swarmtrace.trace.interventions import InterventionRecord
from swarmtrace.trace.schema import TraceEvent
from swarmtrace.world import ToolResult, World, tools
from swarmtrace.world.authorization import ReadGateway

from .recorder import Recorder


@dataclass(frozen=True)
class Intervention:
    kind: str
    agent: str | None = None
    credential: str | None = None


def quarantine(agent: str) -> Intervention:
    return Intervention("quarantine", agent)


def cut_channel() -> Intervention:
    """Disable explicit send/recv communication from the next tick."""
    return Intervention("cut_channel")


def revoke_credential(credential: str) -> Intervention:
    return Intervention("revoke_credential", credential=credential)


def halt_all() -> Intervention:
    return Intervention("halt_all")


Monitor = Callable[[TraceEvent], Intervention | None]
TickController = Callable[[int, tuple[TraceEvent, ...]], Sequence[Intervention]]


class Engine:
    """Run one action per scheduled agent per tick, with a fresh seeded order each tick.

    Without a schedule every agent is due every tick. Explicit schedules contain
    absolute integer ticks; omitted agents are idle. None actions emit no event.
    At least one tool call is required to write a trace under the trace contract.
    """

    def __init__(
        self, world: World, agents: Mapping[str, Agent], seed: int,
        schedule: Mapping[str, tuple[int, ...]] | None = None, monitor: Monitor | None = None,
        after_tick: Callable[[int], None] | None = None,
        controller: TickController | None = None,
        *, read_grants: Sequence[ReadGrant] | None = None,
    ) -> None:
        if type(seed) is not int or seed < 0:
            raise ValueError("seed must be a non-negative integer")
        if not agents.keys() <= world.permissions.keys():
            raise ValueError("all agents must be registered in the world")
        if schedule is not None and (
            not schedule.keys() <= agents.keys()
            or any(type(tick) is not int or tick < 0 for ticks in schedule.values() for tick in ticks)
        ):
            raise ValueError("schedule must contain known agents and non-negative integer ticks")
        id_seed, order_seed = np.random.SeedSequence(seed).spawn(2)
        self._rng = np.random.default_rng(order_seed)
        run_id = np.random.default_rng(id_seed).bytes(8).hex()
        self._recorder = Recorder(run_id)
        self._read_gateway = (ReadGateway(world, run_id, tuple(read_grants))
                              if read_grants is not None else None)
        self._world = world
        self._agents = dict(agents)
        self._schedule = None if schedule is None else {
            agent: frozenset(ticks) for agent, ticks in schedule.items()
        }
        self._monitor = monitor
        self._after_tick = after_tick
        self._controller = controller
        self._has_run = False
        self._pending: list[Intervention] = []
        self.interventions: list[InterventionRecord] = []
        self._last_result: dict[str, ToolResult] = {}
        self._tick = 0

    @property
    def read_audit(self) -> ReadAudit | None:
        return self._read_gateway.audit if self._read_gateway is not None else None

    def _execute(self, agent: str, action: Action) -> ToolResult:
        if agent in self._world.quarantined:
            return ToolResult("denied", 0)
        if action.tool == "read" and self._read_gateway is not None:
            return self._read_gateway.read(self._recorder.next_seq, agent, action.target, action.grant_id)
        function = getattr(tools, action.tool)
        if action.tool in ("write", "send"):
            return function(self._world, agent, action.target, action.content)
        return function(self._world, agent, action.target, **action.args)

    def _validate_intervention(self, intervention: Intervention) -> None:
        if intervention.kind not in ("quarantine", "cut_channel", "revoke_credential", "halt_all"):
            raise ValueError("unknown intervention")
        if (intervention.agent is not None or intervention.kind == "quarantine") and (
            intervention.agent not in self._agents
        ):
            raise ValueError("intervention requires a known agent")
        if (intervention.credential is not None or intervention.kind == "revoke_credential") and (
            intervention.credential not in self._world.credentials
        ):
            raise ValueError("intervention requires a known credential")

    def _apply_pending(self) -> None:
        for intervention in self._pending:
            self._validate_intervention(intervention)
            if intervention.kind == "quarantine":
                self._world.quarantined.add(intervention.agent)
            elif intervention.kind == "cut_channel":
                self._world.channel_cut = True
            elif intervention.kind == "revoke_credential":
                self._world.revoke(intervention.credential)
            elif intervention.kind == "halt_all":
                self._world.quarantined.update(self._world.permissions)
            self.interventions.append(InterventionRecord(
                self._tick - 1, self._tick, intervention.kind,
                intervention.agent, intervention.credential,
            ))
        self._pending.clear()

    def run(self, n_ticks: int, path: str | Path) -> tuple[TraceEvent, ...]:
        if type(n_ticks) is not int or n_ticks < 1:
            raise ValueError("n_ticks must be a positive integer")
        if self._has_run:
            raise RuntimeError("an Engine can run only once; create a fresh Engine")
        self._has_run = True
        agent_ids = tuple(sorted(self._agents))
        hosts = tuple(sorted(self._world.hosts))
        for _ in range(n_ticks):
            self._apply_pending()
            self._world.apply_grants(self._tick)
            tick_events: list[TraceEvent] = []
            due = [
                agent for agent in agent_ids
                if self._schedule is None or self._tick in self._schedule.get(agent, ())
            ]
            for index in self._rng.permutation(len(due)):
                agent = due[int(index)]
                observation = Observation(
                    self._tick, agent, hosts, agent_ids, self._last_result.get(agent),
                )
                action = self._agents[agent].act(observation)
                if action is None:
                    continue
                try:
                    result = self._execute(agent, action)
                except tools.SimulatedToolError:
                    result = ToolResult("error", 0)
                event = self._recorder.record(self._tick, agent, action, result)
                self._last_result[agent] = result
                if self._controller is not None:
                    tick_events.append(deepcopy(event))
                if self._monitor is not None:
                    intervention = self._monitor(event)
                    if intervention is not None:
                        self._pending.append(intervention)
            if self._after_tick is not None:
                self._after_tick(self._tick)
            if self._controller is not None:
                interventions = tuple(self._controller(self._tick, tuple(tick_events)))
                for intervention in interventions:
                    self._validate_intervention(intervention)
                self._pending.extend(interventions)
            self._tick += 1
        self._recorder.write(path)
        return self._recorder.events
