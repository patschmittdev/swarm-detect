"""Containment controllers: defender-side, reading only projected trace events.

``DetectorController`` scores the trace prefix with a frozen online detector at fixed
checkpoints and, from its first flag on, quarantines the attributed agents or revokes the
credentials they borrowed. ``RandomController`` and ``HaltAllController`` are reference
controllers. This package imports only ``trace``, ``features`` and ``detect``; the oracle
controller, which needs ground truth, lives in ``swarmtrace.eval``.
"""

from .controller import LEVERS, DetectorController, borrowed_credentials, check_lever
from .reference import HaltAllController, RandomController

__all__ = [
    "LEVERS",
    "DetectorController",
    "HaltAllController",
    "RandomController",
    "borrowed_credentials",
    "check_lever",
]
