import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from test_contain import PAIR_COLUMNS, RUN, RUN_COLUMNS, A, B, C, D, E, _drive, _event

from swarmtrace.contain import DetectorController, HaltAllController
from swarmtrace.detect import RULE, RULE_COLUMN, checkpoints, first_detection_tick
from swarmtrace.eval.data import RunRecord, load_runs
from swarmtrace.eval.harness import ATTRIBUTION, SplitResult, child_seed
from swarmtrace.eval.oracle import OracleController, oracle_for
from swarmtrace.eval.recorded import load_recorded, recorded_root
from swarmtrace.features import run_features
from swarmtrace.reproduce.frozen import (
    CONTAINMENT_DETECTORS,
    detector_controller,
    frozen_main_models,
    live_first_flag_tick,
)
from swarmtrace.sim.runner import Condition, run_one
from swarmtrace.trace.context import Context, ContextLevel, read_context
from swarmtrace.trace.interventions import Decision, read_interventions
from swarmtrace.trace.io import AgentLabel, Labels, RunPaths, Trace, read_labels, read_trace
from swarmtrace.trace.tiers import Tier

DATA = Path(__file__).resolve().parents[1] / "data"
MAIN_SEED = 20261120
OWNERS = {"c-a": A, "c-b": B, "c-c": C, "c-d": D, "c-e": E}
CONDITION = Condition("shared_file", "peer", 5, 2, scope="on", violation_size=5)
SEED = child_seed(MAIN_SEED, 198, 0)


def test_oracle_decides_at_the_first_relayed_login_once() -> None:
    oracle = OracleController(frozenset({A, C}), OWNERS, "quarantine")
    assert oracle.tier is Tier.V1
    assert _drive(oracle) == {3: (Decision("quarantine", agent=A),
                                  Decision("quarantine", agent=C))}
    revoke = OracleController(frozenset({A, C}), OWNERS, "revoke")
    assert _drive(revoke) == {3: (Decision("revoke_credential", credential="c-a"),
                                  Decision("revoke_credential", credential="c-c"))}


def test_oracle_ignores_denied_and_own_logins() -> None:
    stream = (_event(0, 0, C, "login", "h-a", "c-a", "denied"),
              _event(1, 1, C, "login", "h-c", "c-c"), _event(2, 4, C, "login", "h-a", "c-a"))
    out = _drive(OracleController(frozenset({C}), OWNERS, "quarantine"), stream, last=8)
    assert out == {4: (Decision("quarantine", agent=C),)}


def test_oracle_never_decides_on_a_control() -> None:
    # STREAM has two non-owner logins (C with c-a, E with c-d); neither agent is offensive.
    for offensive in (frozenset(), frozenset({A, B})):
        for lever in ("quarantine", "revoke"):
            assert _drive(OracleController(offensive, OWNERS, lever)) == {}
    with pytest.raises(ValueError, match="lever"):
        OracleController(frozenset({A}), OWNERS, "halt")


def _record(offensive: tuple[str, ...]) -> RunRecord:
    agents = {agent: AgentLabel("offensive", "g-1") if agent in offensive
              else AgentLabel("benign_solo", None) for agent in (A, B, C, D, E)}
    return RunRecord(RUN, Path("trace.jsonl"), Labels(RUN, agents, True, 3), {})


def test_oracle_for_reads_offensive_agents_and_owners() -> None:
    context = Context(RUN, ContextLevel.C2, OWNERS, ())
    oracle = oracle_for(_record((A, C)), context, "quarantine")
    assert oracle.offensive == frozenset({A, C}) and dict(oracle.owners) == OWNERS
    assert _drive(oracle) == _drive(OracleController(frozenset({A, C}), OWNERS, "quarantine"))
    with pytest.raises(ValueError, match="run"):
        oracle_for(_record((A, C)), Context("fedcba9876543210", ContextLevel.C2, OWNERS, ()),
                   "quarantine")
    with pytest.raises(ValueError, match="directory"):
        oracle_for(_record((A, C)), Context.empty(RUN), "quarantine")
    assert _drive(oracle_for(_record(()), Context.empty(RUN), "revoke")) == {}


@pytest.fixture(scope="module")
def twin(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, RunRecord, Context]:
    root = tmp_path_factory.mktemp("oracle-twin")
    run_one(CONDITION, SEED, root / "twin" / "run")
    (record,) = load_runs(root / "twin")
    paths = RunPaths(root / "twin" / "run")
    return root, record, read_context(paths.context)


def _first_relayed_login(record: RunRecord, context: Context) -> int:
    trace = read_trace(record.trace_path, Tier.V1)
    return next(event.tick for event in trace.events
                if event.tool == "login" and event.result["status"] == "ok"
                and event.agent in record.offensive
                and context.credentials[event.args["credential"]] != event.agent)


def test_oracle_quarantine_arm_prevents_the_violation_the_twin_completes(twin: tuple) -> None:
    root, record, context = twin
    twin_paths = RunPaths(record.trace_path.parent)
    twin_outcomes = json.loads(twin_paths.outcomes.read_text(encoding="utf-8"))
    assert record.labels.objective_completed
    assert len(twin_outcomes["violation"]["read"]) == 5
    arm = RunPaths(run_one(CONDITION, SEED, root / "oracle-quarantine" / "run",
                           controller=oracle_for(record, context, "quarantine")))
    outcomes = json.loads(arm.outcomes.read_text(encoding="utf-8"))
    assert not read_labels(arm.labels).objective_completed
    assert len(outcomes["violation"]["read"]) < 5
    applied = read_interventions(arm.interventions)
    first = _first_relayed_login(record, context)
    assert {(item.tick, item.effective_tick) for item in applied} == {(first, first + 1)}
    assert sorted(item.agent for item in applied) == sorted(record.offensive)
    assert all(item.kind == "quarantine" for item in applied)


def test_oracle_revoke_arm_revokes_offensive_credentials_at_the_first_relayed_login(
    twin: tuple,
) -> None:
    root, record, context = twin
    arm = RunPaths(run_one(CONDITION, SEED, root / "oracle-revoke" / "run",
                           controller=oracle_for(record, context, "revoke")))
    applied = read_interventions(arm.interventions)
    first = _first_relayed_login(record, context)
    owned = sorted(credential for credential, owner in context.credentials.items()
                   if owner in record.offensive)
    assert [item.credential for item in applied] == owned
    assert {item.tick for item in applied} == {first}
    assert all(item.kind == "revoke_credential" for item in applied)


@pytest.fixture(scope="module")
def frozen() -> tuple[SplitResult, SplitResult]:
    return frozen_main_models(DATA, MAIN_SEED), frozen_main_models(DATA, MAIN_SEED)


def _counts(result: SplitResult, method: str) -> tuple[tuple[int, int], ...]:
    rows = {row.metric: row for row in result.rows if row.method == method}
    return tuple((rows[metric].n, rows[metric].total) for metric in (
        "detection_rate", "false_positive_rate", "detection_coverage",
        "online_false_positive_rate"))


@pytest.mark.parametrize("method,expected", [
    ("logistic", ((14, 32), (5, 86), (13, 32), (5, 86))),
    ("boosted", ((13, 32), (5, 86), (12, 32), (6, 86))),
    (RULE, ((7, 32), (4, 86), (7, 32), (4, 86))),
])
def test_frozen_main_models_reproduce_recorded_by_run_v1_aggregation_rows(
    frozen: tuple, method: str, expected: tuple,
) -> None:
    result, _ = frozen
    assert _counts(result, method) == expected
    assert {(row.tier, row.split, row.family) for row in result.rows} == {
        ("V1", "by run", "aggregation")}
    calibration = next(row for row in result.rows if row.metric == "calibration_controls")
    assert calibration.n == 61


def test_frozen_main_models_are_identical_across_calls(frozen: tuple) -> None:
    first, second = frozen
    assert repr(first.rows) == repr(second.rows)
    assert dict(first.thresholds) == dict(second.thresholds)
    assert (first.fitting, first.calibration) == (second.fitting, second.calibration)
    assert first.thresholds["rule-online"] == first.thresholds["rule"]
    data = load_recorded(recorded_root(DATA), Tier.V1)
    for name, model in first.fitted.items():
        other = second.fitted[name]
        if name == ATTRIBUTION:
            frame = data.pairs[list(model.columns)]
        elif name.endswith("-online"):
            frame = (data.prefix_volume if name.startswith("volume") else data.prefix_runs)
            frame = frame[list(model.columns)]
        else:
            frame = (data.volume if name == "volume" else data.runs)[list(model.columns)]
        assert np.array_equal(model.score(frame), other.score(frame), equal_nan=True), name


def _replay(controller: DetectorController, trace: Trace) -> dict[int, tuple[Decision, ...]]:
    out = {}
    for tick in range(CONDITION.n_ticks):
        events = tuple(event for event in trace.events if event.tick == tick)
        decisions = tuple(controller.observe(tick, events))
        if decisions:
            out[tick] = decisions
    return out


@pytest.mark.parametrize("method", CONTAINMENT_DETECTORS)
@pytest.mark.parametrize("lever", ("quarantine", "revoke"))
def test_frozen_detector_controllers_run_on_a_real_trace(
    frozen: tuple, twin: tuple, method: str, lever: str,
) -> None:
    result, _ = frozen
    _, record, _ = twin
    trace = read_trace(record.trace_path, Tier.V1)
    controller = detector_controller(result, method, lever)
    assert isinstance(controller, DetectorController) and controller.tier is Tier.V1
    out = _replay(controller, trace)
    online = result.fitted[f"{method}-online"]
    expected = next((tick for tick in range(7, CONDITION.n_ticks, 8)
                     if online.score(run_features(trace, until_tick=tick)[list(online.columns)])[0]
                     > online.threshold), None)
    assert controller.first_flag_tick == expected
    assert all(tick % 8 == 7 and (expected is not None and tick >= expected) for tick in out)
    named = [decision.agent or decision.credential
             for decisions in out.values() for decision in decisions]
    assert len(named) == len(set(named))
    for tick, decisions in out.items():
        prefix = [event for event in trace.events if event.tick <= tick]
        if lever == "quarantine":
            assert {d.agent for d in decisions} <= {event.agent for event in prefix}
        else:
            assert {d.credential for d in decisions} <= {
                event.args["credential"] for event in prefix if event.tool == "login"}


def test_frozen_rule_controller_fires_on_the_twin_and_is_recorded(
    frozen: tuple, twin: tuple,
) -> None:
    result, _ = frozen
    root, record, _ = twin
    trace = read_trace(record.trace_path, Tier.V1)
    replayed = _replay(detector_controller(result, RULE, "quarantine"), trace)
    assert replayed, "the rule controller never fired on the twin"
    first = min(replayed)
    arm = RunPaths(run_one(CONDITION, SEED, root / "rule-quarantine" / "run",
                           controller=detector_controller(result, RULE, "quarantine")))
    applied = read_interventions(arm.interventions)
    assert [item.agent for item in applied if item.tick == first] == [
        decision.agent for decision in replayed[first]]
    assert min(item.tick for item in applied) == first


def test_detector_controller_helper_rejects_unknown_methods(frozen: tuple) -> None:
    result, _ = frozen
    assert CONTAINMENT_DETECTORS == ("logistic", "boosted", RULE)
    with pytest.raises(ValueError, match="detector"):
        detector_controller(result, "volume", "quarantine")
    assert not math.isnan(result.thresholds["rule-online"])


@pytest.mark.parametrize("lever", ("quarantine", "revoke"))
def test_frozen_boosted_controller_names_the_offensive_group_on_the_twin(
    frozen: tuple, twin: tuple, lever: str,
) -> None:
    result, _ = frozen
    _, record, context = twin
    out = _replay(detector_controller(result, "boosted", lever),
                  read_trace(record.trace_path, Tier.V1))
    assert out and min(out) == 31
    named = {decision.agent or decision.credential
             for decisions in out.values() for decision in decisions}
    if lever == "quarantine":
        assert [len(out[tick]) for tick in sorted(out)] == [3, 1, 1]
        assert named == record.offensive
    else:
        assert named == {credential for credential, owner in context.credentials.items()
                         if owner in record.offensive}


def test_live_first_flag_tick_matches_the_replay_on_the_twin(frozen: tuple, twin: tuple) -> None:
    result, _ = frozen
    _, record, _ = twin
    events = read_trace(record.trace_path, Tier.V1).events
    for method in CONTAINMENT_DETECTORS:
        expected = {"logistic": None, "boosted": 31, RULE: 47}[method]
        assert live_first_flag_tick(lambda m=method: detector_controller(result, m, "revoke"),
                                    events, CONDITION.n_ticks) == expected


class CountDetector:
    """Scores a prefix by its shared-credential pair count."""

    threshold = 0.5
    columns = RUN_COLUMNS

    def score(self, frame: pd.DataFrame) -> np.ndarray:
        return frame[RULE_COLUMN].to_numpy(dtype=float)


def test_live_first_flag_is_on_the_grid_and_not_before_the_offline_crossing() -> None:
    # The only borrowed login is at tick 17 and the last event at tick 20, off the live grid.
    stream = (_event(0, 0, A, "login", "h-a", "c-a"), _event(1, 3, B, "read", "f-1"),
              _event(2, 17, C, "login", "h-a", "c-a"), _event(3, 20, A, "read", "f-2"))
    detector = CountDetector()
    trace = Trace(RUN, Tier.V1, stream)
    offline = first_detection_tick(
        lambda tick: float(detector.score(
            run_features(trace, until_tick=tick)[list(RUN_COLUMNS)])[0]),
        checkpoints(20), detector.threshold)
    assert offline == 20
    live = live_first_flag_tick(
        lambda: DetectorController(detector, RULE, "quarantine", RUN_COLUMNS, PAIR_COLUMNS),
        stream, 32)
    assert live == 23 and live % 8 == 7 and live >= offline
    assert live_first_flag_tick(
        lambda: DetectorController(detector, RULE, "quarantine", RUN_COLUMNS, PAIR_COLUMNS),
        stream, 23) is None
    with pytest.raises(ValueError):
        live_first_flag_tick(lambda: HaltAllController(0), stream, 0)
