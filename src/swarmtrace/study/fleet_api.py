"""The detector interface the study scores, imported only when scoring starts."""

import math
from collections.abc import Callable
from dataclasses import dataclass, field

BASELINES = ("requests", "sessions", "concurrency", "template_multiplicity")


@dataclass(frozen=True)
class Fleet:
    load_events: Callable
    events_from_rows: Callable
    assess: Callable
    all_baselines: Callable


def default_fleet() -> Fleet:
    """The frozen detector and baselines from swarmtrace.fleet."""
    from swarmtrace.fleet import baselines, detector, events

    return Fleet(events.load_events, events.events_from_rows, detector.assess,
                 baselines.all_baselines)


@dataclass
class _StubResult:
    score: float = 0.0
    alert: bool = False
    groups: list = field(default_factory=list)
    evidence: list = field(default_factory=list)
    not_computable: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"score": self.score, "alert": self.alert, "groups": self.groups,
                "evidence": self.evidence, "not_computable": self.not_computable, "stub": True}


def _stub_load(path) -> list[dict]:
    import json

    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def stub_fleet() -> Fleet:
    """A detector that never alerts, for exercising the commands without the real detector."""
    return Fleet(_stub_load, list, lambda events: _StubResult(),
                 lambda events, identity_removed=False: dict.fromkeys(BASELINES, 0.0))


def _number(value) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def baseline_values(fleet: Fleet, events, identity: bool) -> dict:
    """The four baselines, called with the identity mode stated explicitly.

    Non-finite or missing values are reported as unavailable (None).
    """
    raw = fleet.all_baselines(events, identity_removed=not identity)
    return {name: _number(raw.get(name)) for name in BASELINES}


def score_events(fleet: Fleet, events, identity: bool = True) -> tuple[dict, dict, dict]:
    """(score, alert and groups as returned; the detector's to_dict(); baselines) for one window.

    The alert is taken as the detector returns it, never recomputed from the score.
    """
    result = fleet.assess(events)
    summary = {"score": float(result.score), "alert": bool(result.alert),
               "groups": [list(g) for g in result.groups]}
    return summary, result.to_dict(), baseline_values(fleet, events, identity)
