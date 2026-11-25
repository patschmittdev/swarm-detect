import math
from collections.abc import Collection, Sequence
from typing import Protocol

import numpy as np
import pandas as pd

from swarmtrace.detect import CHECKPOINT_EVERY, RULE, propose_groups
from swarmtrace.features import pair_features, run_features
from swarmtrace.trace.interventions import Decision
from swarmtrace.trace.io import Trace
from swarmtrace.trace.schema import TraceEvent
from swarmtrace.trace.tiers import Tier

LEVERS = {"quarantine": "quarantine", "revoke": "revoke_credential"}
"""Lever name to the ``Decision`` kind it issues."""
SHARED_LOGINS = "shared_credential_logins"
"""V1 pair feature the rule attribution reads: logins with a credential another agent used first."""


class PrefixDetector(Protocol):
    """A calibrated online detector, such as a fitted ``OnlineDetector``."""

    threshold: float

    def score(self, prefixes: pd.DataFrame) -> np.ndarray: ...


class PairAttribution(Protocol):
    """A fitted pair scorer, such as ``PairScorer``."""

    threshold: float

    def score(self, pairs: pd.DataFrame) -> np.ndarray: ...


def check_lever(lever: str) -> str:
    """The ``Decision`` kind for ``lever``; raises on an unknown lever."""
    if lever not in LEVERS:
        raise ValueError(f"unknown lever {lever!r}; expected one of {tuple(LEVERS)}")
    return LEVERS[lever]


def borrowed_credentials(
    events: Sequence[TraceEvent], agents: Collection[str],
) -> set[str]:
    """Credentials that one of ``agents`` used in an ok login after another agent used it first.

    The first user of a credential is the first agent with an ok login using it, the rule of the
    ``shared_credential_logins`` pair feature.
    """
    first_user: dict[str, str] = {}
    borrowed = set()
    for event in events:
        if event.tool != "login" or event.result["status"] != "ok":
            continue
        credential = str(event.args["credential"])
        if first_user.setdefault(credential, event.agent) != event.agent and event.agent in agents:
            borrowed.add(credential)
    return borrowed


class DetectorController:
    """Containment driven by a frozen online detector and a frozen attribution.

    Events are buffered as they arrive. At each checkpoint (tick ``every - 1``, ``2 * every - 1``,
    ...) before the first flag, the prefix run features in ``columns`` are scored; a score
    strictly above ``detector.threshold`` is a flag. From the first flag on, every checkpoint
    adds the agents attributed in the prefix to a cumulative attributed set and names the
    targets not named before: the attributed agents (lever ``quarantine``) or every credential
    an attributed agent used in an ok login whose first user was another agent (lever
    ``revoke``). Decisions take effect at the next tick. No target is named twice.

    ``attribution`` is a fitted pair scorer, whose proposed groups (components of pairs scored
    strictly above its threshold, on the prefix pair features in ``pair_columns``) are the
    attributed agents, or ``RULE``, for which they are the agents of pairs with at least one
    shared-credential login in the prefix.
    """

    def __init__(
        self, detector: PrefixDetector, attribution: PairAttribution | str, lever: str,
        columns: Sequence[str], pair_columns: Sequence[str], every: int = CHECKPOINT_EVERY,
        tier: Tier = Tier.V1,
    ) -> None:
        self.kind = check_lever(lever)
        if isinstance(attribution, str) and attribution != RULE:
            raise ValueError(f"attribution must be a pair scorer or {RULE!r}, got {attribution!r}")
        if type(every) is not int or every < 1:
            raise ValueError(f"every must be a positive integer, got {every!r}")
        if math.isnan(detector.threshold):
            raise ValueError("calibrate the detector before containment")
        if tier is Tier.V0:
            raise ValueError("containment needs login credentials, which V0 removes")
        self.detector = detector
        self.attribution = attribution
        self.lever = lever
        self.columns = tuple(columns)
        self.pair_columns = tuple(pair_columns)
        self.every = every
        self.tier = tier
        self.first_flag_tick: int | None = None
        self._events: list[TraceEvent] = []
        self._attributed: set[str] = set()
        self._named: set[str] = set()

    def _attribute(self, trace: Trace, tick: int) -> set[str]:
        pairs = pair_features(trace, until_tick=tick)
        if isinstance(self.attribution, str):
            shared = pairs[SHARED_LOGINS]
            return {agent for pair, value in shared.items() if value > 0 for agent in pair}
        frame = pairs[list(self.pair_columns)]
        if frame.empty:
            return set()
        scores = pd.Series(self.attribution.score(frame), index=frame.index)
        return set().union(*propose_groups(scores, self.attribution.threshold))

    def observe(self, tick: int, events: tuple[TraceEvent, ...]) -> Sequence[Decision]:
        self._events.extend(events)
        if tick % self.every != self.every - 1 or not self._events:
            return ()
        trace = Trace(self._events[0].run_id, self.tier, tuple(self._events))
        if self.first_flag_tick is None:
            prefix = run_features(trace, until_tick=tick)[list(self.columns)]
            if not float(self.detector.score(prefix)[0]) > self.detector.threshold:
                return ()
            self.first_flag_tick = tick
        self._attributed |= self._attribute(trace, tick)
        if self.kind == "quarantine":
            targets = sorted(self._attributed - self._named)
            decisions = [Decision(self.kind, agent=agent) for agent in targets]
        else:
            targets = sorted(borrowed_credentials(trace.events, self._attributed) - self._named)
            decisions = [Decision(self.kind, credential=credential) for credential in targets]
        self._named.update(targets)
        return tuple(decisions)
