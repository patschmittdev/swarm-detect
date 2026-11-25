import numpy as np

from .base import Action, Observation


class RandomWalkAgent:
    """Trivial seeded scan/list policy for engine tests."""

    def __init__(self, seed: int) -> None:
        self._rng = np.random.default_rng(np.random.SeedSequence(seed).spawn(1)[0])

    def act(self, observation: Observation) -> Action | None:
        if not observation.hosts:
            return None
        host = observation.hosts[int(self._rng.integers(len(observation.hosts)))]
        if int(self._rng.integers(2)) == 0:
            return Action("scan", host)
        return Action("list", host, {"prefix": ""})
