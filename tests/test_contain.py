import ast
import math
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import swarmtrace.contain as contain
from swarmtrace.contain import (
    LEVERS,
    DetectorController,
    HaltAllController,
    RandomController,
)
from swarmtrace.detect import RULE
from swarmtrace.features import feature_columns
from swarmtrace.trace.interventions import Decision, InterventionRecord
from swarmtrace.trace.schema import TraceEvent
from swarmtrace.trace.tiers import Tier

ALLOWED = ("swarmtrace.trace", "swarmtrace.features", "swarmtrace.detect", "swarmtrace.contain")
BLOCKED = ("swarmtrace.eval", "swarmtrace.sim", "swarmtrace.world", "swarmtrace.agents",
           "swarmtrace.objectives", "swarmtrace.reproduce")
FORBIDDEN = ("Labels", "Manifest", "RunPaths", "outcomes", "labels.json", "manifest.json",
             "read_labels", "read_manifest", "read_trace", "open(")
RUN_COLUMNS = feature_columns("run", Tier.V1, ("aggregation",))
PAIR_COLUMNS = feature_columns("pair", Tier.V1, ("aggregation",))
RUN = "0123456789abcdef"
A, B, C, D, E = (f"a-0000000{index}" for index in range(1, 6))


def _event(seq: int, tick: int, agent: str, tool: str, target: str,
           credential: str | None = None, status: str = "ok") -> TraceEvent:
    args = {} if credential is None else {"credential": credential}
    return TraceEvent(1, RUN, seq, tick, agent, tool, target, args,
                      {"status": status, "size": 0}, None, None)


# C borrows A's credential at tick 3, E borrows D's at tick 10, C's login at tick 12 is denied.
STREAM = tuple(_event(seq, *row) for seq, row in enumerate((
    (0, A, "login", "h-a", "c-a"), (0, B, "login", "h-b", "c-b"), (0, D, "login", "h-d", "c-d"),
    (1, A, "read", "f-1"), (1, B, "read", "f-2"),
    (3, C, "login", "h-a", "c-a"),
    (5, C, "read", "f-3"),
    (10, E, "login", "h-d", "c-d"),
    (12, C, "login", "h-b", "c-x", "denied"),
    (14, B, "read", "f-4"),
    (20, A, "read", "f-5"),
)))
LAST_TICK = 31


def _drive(controller: object, stream: Sequence[TraceEvent] = STREAM,
           last: int = LAST_TICK) -> dict[int, tuple[Decision, ...]]:
    out = {}
    for tick in range(last + 1):
        decisions = tuple(controller.observe(tick, tuple(e for e in stream if e.tick == tick)))
        if decisions:
            out[tick] = decisions
    return out


class StubDetector:
    """Scores the n-th checkpoint with ``scores[n]``; checks what the controller hands it."""

    def __init__(self, scores: Sequence[float], threshold: float = 0.5) -> None:
        self.scores, self.threshold, self.columns = list(scores), threshold, RUN_COLUMNS
        self.frames: list[pd.DataFrame] = []

    def score(self, frame: pd.DataFrame) -> np.ndarray:
        assert tuple(frame.columns) == self.columns and list(frame.index) == [RUN]
        self.frames.append(frame)
        return np.array([self.scores[len(self.frames) - 1]])


class StubScorer:
    """Attributes pairs with a shared-credential login, through the pair-scorer interface."""

    threshold = 0.5
    columns = PAIR_COLUMNS

    def score(self, pairs: pd.DataFrame) -> np.ndarray:
        assert tuple(pairs.columns) == self.columns
        return (pairs["shared_credential_logins"] > 0).to_numpy(dtype=float)


def _controller(scores: Sequence[float], lever: str = "quarantine",
                attribution: object = RULE, threshold: float = 0.5) -> DetectorController:
    return DetectorController(StubDetector(scores, threshold), attribution, lever,
                              RUN_COLUMNS, PAIR_COLUMNS)


def test_contain_imports_only_trace_features_detect_and_never_touches_label_side() -> None:
    package = Path(contain.__file__).parent
    paths = list(package.rglob("*.py"))
    assert {path.name for path in paths} >= {"__init__.py", "controller.py", "reference.py"}
    for path in paths:
        source = path.read_text(encoding="utf-8")
        for forbidden in FORBIDDEN:
            assert forbidden not in source, (path.name, forbidden)
        for node in ast.walk(ast.parse(source)):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = ["swarmtrace.contain" if node.level else node.module or ""]
            for name in names:
                if name.startswith("swarmtrace"):
                    assert name.startswith(ALLOWED), (path.name, name)
                assert not name.startswith(BLOCKED), (path.name, name)


def test_contain_imports_without_eval_simulation_or_reproduce() -> None:
    script = f"""
import sys
for name in {BLOCKED!r}:
    sys.modules[name] = None
import swarmtrace.contain
assert not any(name.startswith({BLOCKED!r}) for name in sys.modules if sys.modules[name])
"""
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_no_decision_before_first_checkpoint_and_flag_at_tick_7_decides_at_tick_7() -> None:
    controller = _controller([0.9])
    out = _drive(controller)
    assert min(out) == 7
    assert out[7] == (Decision("quarantine", agent=A), Decision("quarantine", agent=C))
    assert controller.first_flag_tick == 7
    assert controller.tier is Tier.V1


def test_score_equal_to_threshold_is_not_a_flag() -> None:
    controller = _controller([0.5, 0.5, 0.5, 0.5])
    assert _drive(controller) == {}
    assert controller.first_flag_tick is None
    assert len(controller.detector.frames) == 4


def test_checkpoints_score_the_prefix_only() -> None:
    controller = _controller([0.1, 0.1, 0.1, 0.1])
    _drive(controller)
    frames = controller.detector.frames
    assert [frame["shared_credential_logins_n_above"].iloc[0] for frame in frames] == [1, 2, 2, 2]


def test_newly_attributed_agents_are_added_at_later_checkpoints_once() -> None:
    out = _drive(_controller([0.9]))
    assert out == {
        7: (Decision("quarantine", agent=A), Decision("quarantine", agent=C)),
        15: (Decision("quarantine", agent=D), Decision("quarantine", agent=E)),
    }


def test_first_flag_at_a_later_checkpoint_names_everyone_attributed_by_then() -> None:
    out = _drive(_controller([0.2, 0.9]))
    assert out == {15: tuple(Decision("quarantine", agent=agent) for agent in (A, C, D, E))}


def test_revoke_lever_names_exactly_the_borrowed_credentials() -> None:
    out = _drive(_controller([0.9], lever="revoke"))
    assert out == {
        7: (Decision("revoke_credential", credential="c-a"),),
        15: (Decision("revoke_credential", credential="c-d"),),
    }


def test_revoke_lever_revokes_a_later_borrowing_by_an_agent_already_attributed() -> None:
    stream = (*STREAM, _event(len(STREAM), 18, C, "login", "h-b", "c-b"))
    out = _drive(_controller([0.9], lever="revoke"), stream)
    assert out[23] == (Decision("revoke_credential", credential="c-b"),)


def test_pair_scorer_attribution_uses_proposed_groups() -> None:
    out = _drive(_controller([0.9], attribution=StubScorer()))
    assert out == _drive(_controller([0.9]))


def test_controller_rejects_bad_configuration() -> None:
    with pytest.raises(ValueError, match="lever"):
        _controller([0.9], lever="cut")
    with pytest.raises(ValueError, match="attribution"):
        _controller([0.9], attribution="pairs")
    with pytest.raises(ValueError, match="calibrate"):
        _controller([0.9], threshold=math.nan)
    with pytest.raises(ValueError, match="every"):
        DetectorController(StubDetector([0.9]), RULE, "quarantine", RUN_COLUMNS, PAIR_COLUMNS,
                           every=0)
    assert LEVERS == {"quarantine": "quarantine", "revoke": "revoke_credential"}


def _shadow(*rows: tuple[int, str, str]) -> tuple[InterventionRecord, ...]:
    return tuple(
        InterventionRecord(tick, tick + 1, kind,
                           target if kind == "quarantine" else None,
                           target if kind == "revoke_credential" else None)
        for tick, kind, target in rows
    )


QUARANTINE_SHADOW = _shadow((7, "quarantine", A), (7, "quarantine", C),
                            (15, "quarantine", D), (15, "quarantine", E))


def _summary(out: dict[int, tuple[Decision, ...]]) -> dict[int, tuple[str, int]]:
    return {tick: (decisions[0].kind, len(decisions)) for tick, decisions in out.items()}


def test_random_controller_replays_shadow_ticks_and_counts() -> None:
    out = _drive(RandomController(QUARANTINE_SHADOW, seed=1))
    assert _summary(out) == {7: ("quarantine", 2), 15: ("quarantine", 2)}
    named = [decision.agent for decisions in out.values() for decision in decisions]
    assert len(set(named)) == 4
    revoke = _shadow((7, "revoke_credential", "c-a"), (15, "revoke_credential", "c-d"))
    out = _drive(RandomController(revoke, seed=1))
    assert _summary(out) == {7: ("revoke_credential", 1), 15: ("revoke_credential", 1)}
    assert RandomController(revoke, seed=1).tier is Tier.V1


def test_random_controller_is_deterministic_and_seed_dependent() -> None:
    first = _drive(RandomController(QUARANTINE_SHADOW, seed=5))
    assert first == _drive(RandomController(QUARANTINE_SHADOW, seed=5))
    outcomes = {tuple(sorted(_drive(RandomController(QUARANTINE_SHADOW, seed=seed)).items()))
                for seed in range(20)}
    assert len(outcomes) > 1


def test_random_controller_never_names_a_target_absent_from_the_prefix() -> None:
    seen_at_7 = {A, B, C, D}
    credentials_at_7 = {"c-a", "c-b", "c-d"}
    revoke = _shadow((7, "revoke_credential", "c-a"), (7, "revoke_credential", "c-b"))
    for seed in range(50):
        out = _drive(RandomController(QUARANTINE_SHADOW, seed=seed))
        assert {decision.agent for decision in out[7]} <= seen_at_7
        named = [decision.agent for decisions in out.values() for decision in decisions]
        assert len(named) == len(set(named))
        out = _drive(RandomController(revoke, seed=seed))
        assert {decision.credential for decision in out[7]} <= credentials_at_7
    # A shadow larger than the pool names the whole pool; c-x, denied at tick 12, is not in it.
    many = _shadow(*((15, "revoke_credential", f"c-{index}") for index in range(5)))
    out = _drive(RandomController(many, seed=0))
    assert {decision.credential for decision in out[15]} == credentials_at_7


def test_random_controller_counts_distinct_shadow_targets_and_rejects_other_kinds() -> None:
    repeated = (*_shadow((7, "quarantine", A)), *_shadow((7, "quarantine", A)))
    assert _summary(_drive(RandomController(repeated, seed=0))) == {7: ("quarantine", 1)}
    with pytest.raises(ValueError, match="kind"):
        RandomController(_shadow((7, "halt_all", A)), seed=0)


def test_halt_all_controller_issues_one_halt_all() -> None:
    controller = HaltAllController(15)
    assert _drive(controller) == {15: (Decision("halt_all"),)}
    assert controller.tier is Tier.V1
    with pytest.raises(ValueError):
        HaltAllController(-1)


def test_random_controller_records_a_partial_shortfall() -> None:
    # Four agents by tick 7 against a shadow of five; only E is left at tick 15 against two.
    shadow = _shadow(*((7, "quarantine", f"a-1000000{index}") for index in range(5)),
                     (15, "quarantine", "a-20000001"), (15, "quarantine", "a-20000002"))
    controller = RandomController(shadow, seed=3)
    out = _drive(controller)
    assert _summary(out) == {7: ("quarantine", 4), 15: ("quarantine", 1)}
    assert controller.shortfalls == ((7, 5, 4), (15, 2, 1))
    assert (controller.total_requested, controller.total_named) == (7, 5)


def test_random_controller_records_a_tick_with_no_candidates() -> None:
    shadow = (*QUARANTINE_SHADOW[:2], *_shadow((7, "quarantine", B), (7, "quarantine", D),
                                              (8, "quarantine", E)))
    controller = RandomController(shadow, seed=0)
    out = _drive(controller)
    assert 8 not in out and _summary(out) == {7: ("quarantine", 4)}
    assert controller.shortfalls == ((8, 1, 0),)
    assert (controller.total_requested, controller.total_named) == (5, 4)


def test_random_controller_has_no_shortfall_when_candidates_suffice() -> None:
    for seed in range(10):
        controller = RandomController(QUARANTINE_SHADOW, seed=seed)
        _drive(controller)
        assert controller.shortfalls == ()
        assert (controller.total_requested, controller.total_named) == (4, 4)
    first, second = (RandomController(QUARANTINE_SHADOW, seed=7) for _ in range(2))
    assert _drive(first) == _drive(second) and first.shortfalls == second.shortfalls


class DroppingScorer(StubScorer):
    """Attributes shared-credential pairs at the first scoring only, and nothing afterwards."""

    def __init__(self) -> None:
        self.calls = 0

    def score(self, pairs: pd.DataFrame) -> np.ndarray:
        self.calls += 1
        values = super().score(pairs)
        return values if self.calls == 1 else np.zeros_like(values)


def test_attribution_is_cumulative_when_the_scorer_drops_an_agent() -> None:
    # C is attributed at tick 7 only, then borrows B's credential at tick 18.
    stream = (*STREAM, _event(len(STREAM), 18, C, "login", "h-b", "c-b"))
    revoke = _drive(_controller([0.9], lever="revoke", attribution=DroppingScorer()), stream)
    assert revoke == {7: (Decision("revoke_credential", credential="c-a"),),
                      23: (Decision("revoke_credential", credential="c-b"),)}
    quarantine = _drive(_controller([0.9], attribution=DroppingScorer()), stream)
    assert quarantine == {7: (Decision("quarantine", agent=A), Decision("quarantine", agent=C))}
