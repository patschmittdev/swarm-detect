"""The oracle containment controller: an upper bound that acts on ground truth.

It lives in ``eval`` because it reads labels, which ``swarmtrace.contain`` never may.
"""

from collections.abc import Mapping, Sequence

from swarmtrace.contain import check_lever
from swarmtrace.trace.context import Context, ContextLevel
from swarmtrace.trace.interventions import Decision
from swarmtrace.trace.schema import TraceEvent
from swarmtrace.trace.tiers import Tier

from .data import RunRecord


class OracleController:
    """Acts once, at the first ok login by an offensive agent with a credential it does not own.

    ``owners`` maps each credential to its owning agent. Lever ``quarantine`` quarantines every
    offensive agent; lever ``revoke`` revokes every credential an offensive agent owns. Both take
    effect at the next tick. With no offensive agent (a control run) it never decides.
    """

    tier = Tier.V1

    def __init__(self, offensive: frozenset[str], owners: Mapping[str, str], lever: str) -> None:
        self.kind = check_lever(lever)
        self.offensive = frozenset(offensive)
        self.owners = dict(owners)
        self.lever = lever
        self.fired_tick: int | None = None

    def _relayed(self, event: TraceEvent) -> bool:
        return (event.tool == "login" and event.result["status"] == "ok"
                and event.agent in self.offensive
                and self.owners.get(str(event.args["credential"])) != event.agent)

    def observe(self, tick: int, events: tuple[TraceEvent, ...]) -> Sequence[Decision]:
        if self.fired_tick is not None or not any(self._relayed(event) for event in events):
            return ()
        self.fired_tick = tick
        if self.kind == "quarantine":
            return tuple(Decision(self.kind, agent=agent) for agent in sorted(self.offensive))
        return tuple(Decision(self.kind, credential=credential)
                     for credential, owner in sorted(self.owners.items())
                     if owner in self.offensive)


def oracle_for(record: RunRecord, context: Context, lever: str) -> OracleController:
    """The oracle for a run, from the uncontained twin's labels and credential directory.

    The directory must be the twin's context at C1 or above; a positive run with an empty or C0
    directory is refused, because every login would then look borrowed.
    """
    if context.run_id != record.run_id:
        raise ValueError(f"context run {context.run_id!r} is not record run {record.run_id!r}")
    if record.offensive and (context.level is ContextLevel.C0 or not context.credentials):
        raise ValueError("the oracle needs the credential directory (context C1 or above)")
    return OracleController(record.offensive, context.credentials, lever)
