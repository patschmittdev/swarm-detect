from collections.abc import Sequence

import numpy as np

from swarmtrace.trace.interventions import Decision, InterventionRecord
from swarmtrace.trace.schema import TraceEvent
from swarmtrace.trace.tiers import Tier

_TARGETS = {"quarantine": "agent", "revoke_credential": "credential"}


class RandomController:
    """Replays a shadow arm's decision ticks and counts with targets drawn at random.

    For each tick and kind in ``shadow`` (applied records, whose ``tick`` is the decision tick),
    it names as many distinct targets as the shadow did, drawn uniformly without replacement
    from the sorted candidates not named before: agents with any event in the prefix
    (``quarantine``) or credentials used in an ok login in the prefix (``revoke_credential``).
    When fewer candidates remain, it names all of them, possibly none, and records the shortfall:
    after the run, ``shortfalls`` holds ``(tick, requested, named)`` for every shadow tick and
    kind where ``named < requested``, and ``total_requested`` and ``total_named`` the totals. A
    caller that compares this arm with its shadow must report the shortfalls beside the
    comparison, because a matched comparison is only matched where they are empty.
    Deterministic for a seed.
    """

    tier = Tier.V1

    def __init__(self, shadow: Sequence[InterventionRecord], seed: int) -> None:
        plan: dict[int, dict[str, set[str]]] = {}
        for record in shadow:
            if record.kind not in _TARGETS:
                raise ValueError(f"cannot shadow decision kind {record.kind!r}")
            target = getattr(record, _TARGETS[record.kind])
            if target is None:
                raise ValueError(f"a {record.kind!r} record must name its target")
            plan.setdefault(record.tick, {}).setdefault(record.kind, set()).add(target)
        self.plan = {tick: {kind: len(targets) for kind, targets in kinds.items()}
                     for tick, kinds in sorted(plan.items())}
        self.seed = seed
        self._rng = np.random.default_rng(seed)
        self._pool: dict[str, set[str]] = {kind: set() for kind in _TARGETS}
        self._named: dict[str, set[str]] = {kind: set() for kind in _TARGETS}
        self.shortfalls: tuple[tuple[int, int, int], ...] = ()
        self.total_requested = 0
        self.total_named = 0

    def observe(self, tick: int, events: tuple[TraceEvent, ...]) -> Sequence[Decision]:
        for event in events:
            self._pool["quarantine"].add(event.agent)
            if event.tool == "login" and event.result["status"] == "ok":
                self._pool["revoke_credential"].add(str(event.args["credential"]))
        decisions = []
        for kind, count in sorted(self.plan.get(tick, {}).items()):
            candidates = sorted(self._pool[kind] - self._named[kind])
            picks = self._rng.choice(len(candidates), size=min(count, len(candidates)),
                                     replace=False)
            chosen = sorted(str(candidates[int(index)]) for index in picks)
            self._named[kind].update(chosen)
            self.total_requested += count
            self.total_named += len(chosen)
            if len(chosen) < count:
                self.shortfalls = (*self.shortfalls, (tick, count, len(chosen)))
            decisions.extend(Decision(kind, **{_TARGETS[kind]: target}) for target in chosen)
        return tuple(decisions)


class HaltAllController:
    """Issues one ``halt_all`` at ``first_flag_tick``, effective the next tick."""

    tier = Tier.V1

    def __init__(self, first_flag_tick: int) -> None:
        if type(first_flag_tick) is not int or first_flag_tick < 0:
            raise ValueError("first_flag_tick must be a non-negative integer")
        self.first_flag_tick = first_flag_tick

    def observe(self, tick: int, events: tuple[TraceEvent, ...]) -> Sequence[Decision]:
        return (Decision("halt_all"),) if tick == self.first_flag_tick else ()
