from __future__ import annotations

from dataclasses import replace
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .schema import TraceEvent


class Tier(Enum):
    V0 = "V0"
    V1 = "V1"
    V2 = "V2"


def project(event: TraceEvent, tier: Tier) -> TraceEvent:
    if tier is Tier.V2:
        return event
    if tier is Tier.V1:
        return replace(event, content=None, provenance=None)
    if tier is Tier.V0:
        return replace(event, content=None, provenance=None, args={},
                       result={"status": event.result["status"], "size": 0})
    raise ValueError(f"Unknown tier: {tier!r}")
