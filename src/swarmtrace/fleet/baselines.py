"""Four reference scores for one request window."""

import re
from collections import defaultdict
from collections.abc import Sequence

from swarmtrace.fleet.detector import STATE_WRITE, request_target
from swarmtrace.fleet.events import Event


def _concurrency(events: Sequence[Event]) -> int:
    """Count positive-duration intervals as half-open.

    Equal start and end times show activity but provide no evidence of overlap with
    other requests at that same instant or with intervals ending or starting there.
    """
    endpoints = []
    instants = set()
    for event in events:
        if event.t_start == event.t_end:
            instants.add(event.t_start)
        else:
            endpoints.extend(((event.t_start, 1), (event.t_end, -1)))
    endpoints.extend((instant, 0) for instant in instants)
    active = peak = 0
    for _, change in sorted(endpoints):
        active += change
        peak = max(peak, active + (change == 0))
    return peak


def _template_multiplicity(events: Sequence[Event]) -> int:
    authors = defaultdict(set)
    for event in events:
        target = request_target(event)
        if event.token_id is not None and target is not None and target[0] == STATE_WRITE:
            name = target[1][1].lower()
            key = re.sub(r"[\W_]+", " ", re.sub(r"\d+", "0", name)).strip()
            authors[key].add(event.token_id)
    return max(map(len, authors.values()), default=0)


def all_baselines(
    events: Sequence[Event], identity_removed: bool = False,
) -> dict[str, float | None]:
    """Return reference scores using the caller's identity export mode."""
    tokens = set() if identity_removed else {
        event.token_id for event in events if event.token_id is not None
    }
    template_multiplicity = None if identity_removed else float(_template_multiplicity(events))
    return {
        "requests": float(len(events)),
        "sessions": float(len(tokens)),
        "concurrency": float(_concurrency(events)),
        "template_multiplicity": template_multiplicity,
    }
