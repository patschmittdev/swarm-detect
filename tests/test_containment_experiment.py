import gzip
import hashlib
import json
import socket
from dataclasses import replace
from pathlib import Path

import pandas as pd
import pytest

from swarmtrace.cli import main
from swarmtrace.contain import RandomController
from swarmtrace.eval.containment import (
    ARMS,
    BEFORE_FIRST,
    BETWEEN,
    DETECTORS,
    LENDER,
    LEVERS,
    NOT_COLLECTOR,
    OTHER_OWNER,
    TWIN,
    HostMap,
    RunFacts,
    bootstrap_seed,
    cost_cells,
    decomposition_rows,
    detector_arm,
    first_checkpoint_precedes,
    halt_arm,
    interval_text,
    lender_cells,
    measure_arm,
    oracle_arm,
    placement,
    prevention_cells,
    random_arm,
    timing_cells,
)
from swarmtrace.eval.harness import SplitResult, child_seed
from swarmtrace.eval.metrics import Estimate
from swarmtrace.eval.recorded import load_run_table
from swarmtrace.reproduce.config import ReproduceConfig, make_jobs
from swarmtrace.reproduce.containment import (
    RUN_FILES,
    ContainmentConfig,
    PairJob,
    PairResult,
    check_seeds,
    containment,
    controller_for,
    first_decision,
    first_flags,
    pair_jobs,
    render,
    twin_events,
    write_sample,
)
from swarmtrace.reproduce.frozen import (
    detector_controller,
    frozen_main_models,
    live_first_flag_tick,
)
from swarmtrace.sim.runner import Condition, run_one
from swarmtrace.trace.context import Context, ContextLevel
from swarmtrace.trace.interventions import InterventionRecord, read_interventions
from swarmtrace.trace.io import AgentLabel, Labels, RunPaths, read_labels, read_manifest
from swarmtrace.trace.schema import TraceEvent

DATA = Path(__file__).resolve().parents[1] / "data"
SEED = 20261120
COMMON = {"n_ticks": 48, "benign_credential_sharing": 10, "scope": "on",
          "scope_mistake_rate": 2}
# At pair seed child_seed(SEED, 98, 0) this positive is flagged by rule (39) and boosted (31)
# and not by logistic, so the tiny grid exercises both simulated and skipped detector arms.
POSITIVE = Condition("message", "peer", 5, 1, violation_size=5, **COMMON)
CONTROL = Condition("message", "peer", 0, 1, **COMMON)
TINY = ContainmentConfig(seed=SEED, workers=1, n_bootstrap=20, conditions=(POSITIVE, CONTROL))
BASE_FILES = RUN_FILES[:-1]

# Hand-built pair. O1 lends c-1 (host h-1) to collector O2, whose relayed login is at tick 4;
# O2 must read f-1 to f-5. The arm quarantines O2 and benign B2 from tick 13, so O2 reads two
# required files, not five, and B2's read at tick 20 is denied and its task is lost.
RUN = "0123456789abcdef"
O1, O2, B1, B2 = "a-o1", "a-o2", "a-b1", "a-b2"
OWNERS = {"c-1": O1, "c-2": O2, "c-3": B1, "c-4": B2}
REQUIRED = [f"f-{index}" for index in range(1, 6)]
HOSTS = HostMap({**dict.fromkeys(REQUIRED, "h-1"), "f-x": "h-1", "f-b": "h-2"},
                {"c-1": "h-1", "c-2": "h-3", "c-3": "h-2", "c-4": "h-2"})


def _event(seq: int, tick: int, agent: str, tool: str, target: str,
           credential: str | None = None, status: str = "ok") -> TraceEvent:
    args = {} if credential is None else {"credential": credential}
    return TraceEvent(1, RUN, seq, tick, agent, tool, target, args,
                      {"status": status, "size": 0}, None, None)


def _events(contained: bool) -> tuple[TraceEvent, ...]:
    late = "denied" if contained else "ok"
    rows = [(0, O1, "login", "h-1", "c-1"), (4, O2, "login", "h-1", "c-1"),
            (5, O2, "read", "f-1"), (6, O2, "read", "f-2"),
            (14, O2, "read", "f-3", None, late), (15, O2, "read", "f-4", None, late),
            (16, O2, "read", "f-5", None, late), (20, B2, "read", "f-b", None, late),
            (20, O1, "read", "f-x", None, late), (21, B1, "read", "f-b")]
    return tuple(_event(seq, *row) for seq, row in enumerate(rows))


def _facts(contained: bool, records: tuple[InterventionRecord, ...] = ()) -> RunFacts:
    agents = {O1: AgentLabel("offensive", "g-o"), O2: AgentLabel("offensive", "g-o"),
              B1: AgentLabel("benign_team", "g-b"), B2: AgentLabel("benign_team", "g-b")}
    outcomes = {
        "schema_version": 1, "run_id": RUN,
        "tasks": [{"group": "g-b", "owner": B1, "worker": B2, "host": "h-2",
                   "completed": not contained},
                  {"group": "g-o", "owner": O1, "worker": O2, "host": "h-1",
                   "completed": not contained}],
        "violation": {"worker": O2, "required": REQUIRED,
                      "read": REQUIRED[:2] if contained else REQUIRED},
        "out_of_scope_reads": [],
    }
    labels = Labels(RUN, agents, not contained, None if contained else 16)
    return RunFacts(labels, outcomes, Context(RUN, ContextLevel.C2, OWNERS, ()), records,
                    _events(contained))


QUARANTINE = (InterventionRecord(12, 13, "quarantine", O2, None),
              InterventionRecord(12, 13, "quarantine", B2, None),
              InterventionRecord(14, 15, "quarantine", O2, None))
"""The repeat row for O2 is how the engine records a decision applied twice."""


def test_hand_built_metrics_give_known_values() -> None:
    measure = measure_arm("rule-quarantine", _facts(False), _facts(True, QUARANTINE), HOSTS)
    assert (measure.required_twin, measure.required_arm, measure.prevented) == (5, 2, 3)
    assert measure.prevention == "partly prevented"
    assert measure.benign_tasks_lost == 1
    assert (measure.first_relayed_login, measure.first_effective) == (4, 13)
    assert measure.time_to_intervention == 9
    assert measure.first_collector_effective == 13 and measure.objective_tick_twin == 16
    assert (measure.first_required_read, measure.last_required_read) == (5, 16)
    assert measure.targets == 2 and measure.benign_quarantined == 1
    assert (measure.benign_ok_deficit, measure.benign_newly_denied,
            measure.benign_denied_change) == (1, 1, 1)
    assert measure.objective_twin and not measure.objective_arm and measure.positive
    prevention = prevention_cells([measure], SEED, (0,), 20)
    assert prevention["required reads prevented (pooled)"].startswith("3 of 5 files; 0.600")
    assert list(prevention)[1] == "required reads prevented (pooled)"
    assert (prevention["fully prevented"], prevention["partly prevented"],
            prevention["not prevented"]) == ("0", "1", "0")
    assert prevention["objective completed (also requires the group's later writes), arm"
                      ].startswith("0 of 1")
    assert prevention["objective completed, twin"].startswith("1 of 1")
    timing = timing_cells([measure])
    assert timing["ticks, relayed login to first intervention"].startswith("median 9;")
    assert timing["after first, at or before last required read (first / collector)"] == "1 / 1"
    assert timing["collector hit at or before twin's objective tick"] == "1"
    cost = cost_cells([measure], SEED, (1,), 20)
    assert cost["benign tasks lost"].startswith("1;")
    assert cost["benign ok-call deficit (pooled)"].startswith("1 of 2 ok calls")
    assert cost["benign agents newly denied (pooled)"].startswith("1 of 2 agents")
    assert cost["change in denied calls by benign agents"] == "1"


def _custom(events: list[tuple], records: tuple[InterventionRecord, ...] = (),
            contained: bool = True, read: list[str] | None = None) -> RunFacts:
    base = _facts(contained, records)
    outcomes = dict(base.outcomes)
    if read is not None:
        outcomes["violation"] = {**outcomes["violation"], "read": read}
    return replace(base, outcomes=outcomes,
                   events=tuple(_event(seq, *row) for seq, row in enumerate(events)))


def test_ok_deficit_newly_denied_and_denied_change_are_separate_measures() -> None:
    # B1 loses two ok calls; both become denials and it makes one extra denied call. B2's
    # denial at tick 22 already happens in the twin, so B2 is not newly denied.
    twin = _custom([(0, O1, "login", "h-1", "c-1"), (20, B1, "read", "f-b"),
                    (21, B1, "read", "f-b"), (22, B2, "read", "f-z", None, "denied")],
                   contained=False)
    arm = _custom([(0, O1, "login", "h-1", "c-1"), (20, B1, "read", "f-b", None, "denied"),
                   (21, B1, "read", "f-b", None, "denied"),
                   (22, B1, "read", "f-b", None, "denied"),
                   (22, B2, "read", "f-z", None, "denied")],
                  (InterventionRecord(19, 20, "quarantine", B1, None),))
    measure = measure_arm("rule-quarantine", twin, arm, HOSTS)
    assert (measure.benign_ok_deficit, measure.benign_newly_denied,
            measure.benign_denied_change) == (2, 1, 3)


def test_required_reads_come_from_the_collector_and_outcomes() -> None:
    # O1 also reads required f-3 first; only the collector's reads set the ticks. The trace
    # shows the collector reading three files although outcomes.json lists five: prevented
    # counts follow outcomes.json and read ticks follow the trace.
    rows = [(0, O1, "login", "h-1", "c-1"), (3, O1, "read", "f-3"),
            (4, O2, "login", "h-1", "c-1"), (5, O2, "read", "f-1"), (6, O2, "read", "f-2"),
            (9, O2, "read", "f-4")]
    twin = _custom(rows, contained=False)
    measure = measure_arm("rule-quarantine", twin, _custom(rows, read=REQUIRED[:1]), HOSTS)
    assert (measure.first_required_read, measure.last_required_read) == (5, 9)
    assert (measure.required_twin, measure.prevented) == (5, 4)


def test_collector_tick_differs_from_the_first_intervention() -> None:
    records = (InterventionRecord(10, 11, "quarantine", B2, None),
               InterventionRecord(14, 15, "quarantine", O2, None))
    measure = measure_arm("rule-quarantine", _facts(False), _facts(True, records), HOSTS)
    assert (measure.first_effective, measure.first_collector_effective) == (11, 15)
    assert (placement(measure.first_effective, measure),
            placement(measure.first_collector_effective, measure)) == (BETWEEN, BETWEEN)
    # Revoking a credential the collector never used on h-1 does not affect it; revoking the
    # borrowed c-1 ends its session there.
    unused = (InterventionRecord(10, 11, "revoke_credential", None, "c-4"),)
    measure = measure_arm("rule-revoke", _facts(False), _facts(True, unused), HOSTS)
    assert measure.first_effective == 11 and measure.first_collector_effective is None
    assert placement(None, measure) == NOT_COLLECTOR
    used = (*unused, InterventionRecord(12, 13, "revoke_credential", None, "c-1"))
    measure = measure_arm("rule-revoke", _facts(False), _facts(True, used), HOSTS)
    assert measure.first_collector_effective == 13
    # Revoked before the collector's borrowed login at tick 4: that login is denied, which
    # also affects the collector.
    early = (InterventionRecord(2, 3, "revoke_credential", None, "c-1"),)
    arm = _custom([(0, O1, "login", "h-1", "c-1"), (4, O2, "login", "h-1", "c-1", "denied")],
                  early)
    measure = measure_arm("rule-revoke", _facts(False), arm, HOSTS)
    assert measure.first_collector_effective == 3


def test_equal_tick_precedes_the_read_and_negative_timing_is_kept() -> None:
    records = (InterventionRecord(2, 3, "halt_all", None, None),)
    measure = measure_arm("halt-rule", _facts(False), _facts(True, records), HOSTS)
    assert measure.time_to_intervention == -1 and measure.time_to_collector == -1
    equal = (InterventionRecord(4, 5, "quarantine", O2, None),)
    measure = measure_arm("rule-quarantine", _facts(False), _facts(True, equal), HOSTS)
    assert measure.first_collector_effective == measure.first_required_read == 5
    assert placement(5, measure) == BEFORE_FIRST
    rows = decomposition_rows([(7, measure)])
    early = next(row for row in rows if row["category (first intervention affecting the "
                                                  "collector)"] == BEFORE_FIRST)
    # Outcomes say two required files were still read: listed as an exception.
    assert early["pairs"] == "1" and early["exceptions"] == "pair 7 (3 of 5)"


def test_first_checkpoint_counterfactual() -> None:
    measure = measure_arm("twin", _facts(False), _facts(False), HOSTS)
    # Relayed login at tick 4, first required read at tick 5: the first checkpoint is tick 7.
    assert first_checkpoint_precedes(measure, 8) is False
    assert first_checkpoint_precedes(replace(measure, first_required_read=8), 8) is True
    assert first_checkpoint_precedes(replace(measure, first_relayed_login=8,
                                             first_required_read=16), 8) is True


def test_pooled_and_mean_per_pair_differ() -> None:
    base = measure_arm("rule-quarantine", _facts(False), None, HOSTS)
    full = replace(base, required_twin=1, required_arm=0)
    none = replace(base, required_twin=4, required_arm=4)
    cells = prevention_cells([full, none], SEED, (0,), 50)
    assert cells["required reads prevented (pooled)"].startswith("1 of 5 files; 0.200")
    assert cells["prevented fraction, mean per pair"].startswith("0.500")
    assert (cells["fully prevented"], cells["not prevented"]) == ("1", "1")


def test_hand_built_revocation_locks_the_lender_out() -> None:
    revoke = (InterventionRecord(12, 13, "revoke_credential", None, "c-1"),)
    measure = measure_arm("rule-revoke", _facts(False), _facts(True, revoke), HOSTS)
    (lender,) = measure.lenders
    assert (lender.role, lender.cohort, lender.locked_out) == ("offensive", LENDER, True)
    cells = lender_cells([measure], LENDER, "offensive", SEED, (0,), 20)
    assert cells["locked out of own host (pooled)"].startswith("1 of 1 owners")
    two = lender_cells([measure, measure], LENDER, "offensive", SEED, (0,), 20)
    assert "degenerate bootstrap interval [1.000, 1.000]" in two["locked out of own host (pooled)"]
    assert cells["ok-call deficit (pooled)"].startswith("1 of 2 ok calls")
    assert lender_cells([measure], LENDER, "benign", SEED, (0,), 20)["owners"] == "0"
    assert measure.benign_revoked == 0 and measure.benign_quarantined == 0
    halt = measure_arm("halt-rule", _facts(False),
                       _facts(True, (InterventionRecord(12, 13, "halt_all", None, None),)), HOSTS)
    assert halt.benign_quarantined == 2 and halt.targets == 1


def test_two_lenders_one_lost_task_and_a_benign_owner_nobody_borrowed() -> None:
    # O1 borrows O2's c-2 and O2 borrows O1's c-1, so both are lenders; their one shared task
    # (owner O1, worker O2) is lost and counted once. B1's c-3 was never borrowed.
    rows = [(0, O1, "login", "h-1", "c-1"), (1, O1, "login", "h-3", "c-2"),
            (2, O2, "login", "h-3", "c-2"), (4, O2, "login", "h-1", "c-1"),
            (20, B1, "login", "h-2", "c-3"), (21, B1, "read", "f-b")]
    revoke = tuple(InterventionRecord(12, 13, "revoke_credential", None, credential)
                   for credential in ("c-1", "c-2", "c-3"))
    twin = _custom(rows, contained=False)
    arm = _custom(rows[:4] + [(20, B1, "login", "h-2", "c-3", "denied"),
                              (21, B1, "read", "f-b", None, "denied")], revoke)
    measure = measure_arm("rule-revoke", twin, arm, HOSTS)
    cohorts = {(lender.role, lender.cohort) for lender in measure.lenders}
    assert cohorts == {("offensive", LENDER), ("benign", OTHER_OWNER)}
    assert measure.benign_revoked == 1
    lenders = lender_cells([measure], LENDER, "offensive", SEED, (0,), 20)
    assert lenders["owners"] == "2" and lenders["distinct owned tasks lost"] == "1"
    other = lender_cells([measure], OTHER_OWNER, "benign", SEED, (0,), 20)
    assert other["owners"] == "1" and other["locked out of own host (pooled)"].startswith(
        "1 of 1 owners")


@pytest.mark.parametrize("value,expected", [
    (0.0, "degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; "
          "does not establish a zero population value"),
    (1.0, "degenerate bootstrap interval [1.000, 1.000]: all valid resamples were one; "
          "does not establish a population value of one"),
    (0.4, "degenerate bootstrap interval [0.400, 0.400]: all valid resamples were equal; "
          "does not establish a population value of exactly 0.400"),
])
def test_degenerate_intervals_carry_the_qualification(value: float, expected: str) -> None:
    text = interval_text(Estimate(value, value, value, 20, 20, ""))
    assert text == f"{value:.3f} ({expected})"
    assert interval_text(Estimate(0.4, 0.3, 0.5, 20, 20, "")) == "0.400 [0.300, 0.500]"


def test_unsimulated_arm_takes_the_twins_outcomes() -> None:
    measure = measure_arm("rule-quarantine", _facts(False), None, HOSTS)
    assert not measure.simulated and measure.targets == 0 and measure.prevented == 0
    assert measure.objective_arm == measure.objective_twin
    assert measure.benign_ok_deficit == 0 and measure.benign_newly_denied == 0


def test_arm_set_is_exact() -> None:
    assert ARMS == (
        "twin", "rule-quarantine", "rule-revoke", "logistic-quarantine", "logistic-revoke",
        "boosted-quarantine", "boosted-revoke", "random-rule-quarantine", "random-rule-revoke",
        "random-logistic-quarantine", "random-logistic-revoke", "random-boosted-quarantine",
        "random-boosted-revoke", "halt-rule", "halt-logistic", "halt-boosted",
        "oracle-quarantine", "oracle-revoke")


def test_full_grid_pairs_and_seeds() -> None:
    config = ContainmentConfig(seed=SEED)
    jobs = pair_jobs(config)
    positives = [job for job in jobs if job.condition.offensive_group_size]
    assert len(jobs) == 270 and len(positives) == 162
    assert all(sum(job.condition.violation_size == size for job in positives) == 54
               for size in (1, 2, 5))
    assert all(job.condition.violation_size == 0 for job in jobs[162:])
    assert {(job.condition.scope, job.condition.scope_mistake_rate,
             job.condition.benign_credential_sharing) for job in jobs} == {("on", 2, 10)}
    assert [job.seed for job in jobs] == [child_seed(SEED, 98, i) for i in range(270)]
    assert [job.random_seed for job in jobs] == [child_seed(SEED, 99, 1, i) for i in range(270)]
    check_seeds(config, jobs)
    main_seed = make_jobs(ReproduceConfig(seed=SEED))[0].seed
    with pytest.raises(ValueError, match="collide"):
        check_seeds(config, (replace(jobs[0], seed=main_seed), *jobs[1:]))
    with pytest.raises(ValueError, match="collide"):
        check_seeds(config, (replace(jobs[0], seed=child_seed(SEED, 95, 3)), *jobs[1:]))
    with pytest.raises(ValueError, match="random-arm seeds collide across pairs"):
        check_seeds(config, (replace(jobs[0], random_seed=jobs[1].random_seed), *jobs[1:]))
    with pytest.raises(ValueError, match="pair seeds collide with random-arm"):
        check_seeds(config, (replace(jobs[0], random_seed=jobs[5].seed), *jobs[1:]))
    with pytest.raises(ValueError, match="random-arm seeds collide with bootstrap"):
        check_seeds(config, (replace(jobs[0], random_seed=bootstrap_seed(SEED, 3, 1)),
                             *jobs[1:]))
    assert bootstrap_seed(SEED, 3, 1) == child_seed(SEED, 99, 0, 3, 1)
    with pytest.raises(ValueError, match="key spaces"):
        bootstrap_seed(SEED, 3)
    assert len(pair_jobs(ContainmentConfig(control_repeats=3))) == 162 + 54


def test_cli_has_the_containment_command(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as raised:
        main(["containment", "--help"])
    assert raised.value.code == 0
    assert "--data" in capsys.readouterr().out


@pytest.fixture(scope="module")
def models() -> SplitResult:
    return frozen_main_models(DATA, SEED)


@pytest.fixture(scope="module")
def experiment(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path, Path]:
    root = tmp_path_factory.mktemp("containment")

    def refuse(*args: object, **kwargs: object) -> None:
        raise OSError("network disabled in test")

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(socket, "socket", refuse)
        patch.setattr(socket, "create_connection", refuse)
        containment(root / "one", DATA, TINY, keep=root / "runs")
    containment(root / "two", DATA, replace(TINY, workers=2))
    return root / "one", root / "two", root / "runs"


def _files(root: Path) -> dict[str, bytes]:
    return {path.relative_to(root).as_posix(): path.read_bytes()
            for path in sorted(root.rglob("*")) if path.is_file()}


def test_output_is_identical_for_one_and_two_workers(experiment: tuple) -> None:
    one, two, _ = experiment
    assert _files(one) == _files(two)
    assert set(_files(one)) >= {"containment.md", "containment/runs.csv.gz"}


def test_report_states_counts_and_digests(experiment: tuple) -> None:
    one, _, _ = experiment
    text = (one / "containment.md").read_text(encoding="utf-8")
    assert f"Seed: {SEED}" in text and "Calibration controls: 61." in text
    assert "Pairs: 2: 1 positive" in text and "1 control" in text
    assert "each lost ok call appears as one denied call" in text
    assert "inflated by retries" not in text and "every tick" not in text
    block = text.split("## SHA-256")[1]
    for name, content in _files(one / "containment").items():
        assert f"{hashlib.sha256(content).hexdigest()}  containment/{name}" in block


def test_run_table_has_one_row_per_arm_and_run(experiment: tuple) -> None:
    one, _, runs = experiment
    table = load_run_table(one / "containment" / "runs.csv.gz")
    assert len(table.records) == 2 * len(ARMS)
    assert not [c for c in table.features if c.startswith(("label_", "condition_", "outcome_"))]
    pairs: dict[int, list] = {}
    for record in table.records:
        pairs.setdefault(int(record.condition["pair"]), []).append(record)
    for index, records in pairs.items():
        run_ids = {record.run_id.split(".")[0] for record in records}
        assert len(run_ids) == 1
        assert sorted(record.condition["arm"] for record in records) == sorted(ARMS)
        assert {record.condition["seed"] for record in records} == {child_seed(SEED, 98, index)}
        twin = next(r for r in records if r.condition["arm"] == TWIN).run_id
        for record in records:
            directory = runs / f"pair-{index:04d}" / str(record.condition["arm"]) / "run"
            assert bool(record.outcomes["simulated"]) == directory.is_dir()
            if directory.is_dir():
                assert read_labels(RunPaths(directory).labels).run_id == twin.split(".")[0]
                assert read_manifest(RunPaths(directory).manifest).seed == child_seed(SEED, 98,
                                                                                      index)
            else:
                pd.testing.assert_series_equal(table.features.loc[record.run_id],
                                               table.features.loc[twin], check_names=False)
    simulated = {r.condition["arm"] for r in pairs[0] if r.outcomes["simulated"]}
    assert simulated >= {detector_arm("rule", "quarantine"), halt_arm("boosted"),
                         oracle_arm("revoke")}
    assert not simulated & {detector_arm("logistic", lever) for lever in LEVERS}
    assert {r.condition["arm"] for r in pairs[1] if r.outcomes["simulated"]} == {TWIN}


def _job(index: int) -> PairJob:
    return pair_jobs(TINY)[index]


def test_first_flag_equals_first_intervention_tick_minus_the_offset(
    experiment: tuple, models: SplitResult,
) -> None:
    # run_one applies a decision taken at tick t from tick t + 1: every record has
    # effective_tick == tick + 1. A halt-all arm decides at the first flag, so
    # first_flag == min(effective_tick) - 1. A detector arm's first decision falls on a
    # checkpoint at or after its flag (equal when the flag checkpoint names a target), and is
    # what the twin replay predicts.
    _, _, runs = experiment
    root = runs / "pair-0000"
    events = twin_events(root / TWIN / "run")
    checked = 0
    for method in DETECTORS:
        flags = {lever: live_first_flag_tick(
            lambda lever=lever: detector_controller(models, method, lever), events,
            POSITIVE.n_ticks) for lever in LEVERS}
        assert flags["quarantine"] == flags["revoke"]
        flag = flags["quarantine"]
        halt = root / halt_arm(method) / "run"
        assert halt.is_dir() == (flag is not None)
        if flag is None:
            continue
        (record,) = read_interventions(RunPaths(halt).interventions)
        assert record.effective_tick - 1 == record.tick == flag
        for lever in LEVERS:
            applied = read_interventions(RunPaths(root / detector_arm(method, lever) / "run")
                                         .interventions)
            assert all(r.effective_tick == r.tick + 1 for r in applied)
            first = min(r.effective_tick for r in applied) - 1
            predicted, _ = first_decision(
                lambda lever=lever: detector_controller(models, method, lever), events,
                POSITIVE.n_ticks)
            assert first == predicted and first >= flag and first % 8 == 7
            checked += 1
    assert checked >= 4


def _plan(records: tuple[InterventionRecord, ...]) -> dict[int, int]:
    targets: dict[int, set] = {}
    for record in records:
        targets.setdefault(record.tick, set()).add((record.kind, record.agent, record.credential))
    return {tick: len(found) for tick, found in sorted(targets.items())}


def test_random_arms_match_their_shadows_ticks_and_counts(experiment: tuple) -> None:
    _, _, runs = experiment
    root = runs / "pair-0000"
    compared = 0
    for method in DETECTORS:
        for lever in LEVERS:
            shadow = root / detector_arm(method, lever) / "run"
            randomized = root / random_arm(method, lever) / "run"
            assert randomized.is_dir() == shadow.is_dir()
            if not shadow.is_dir():
                continue
            mine = read_interventions(RunPaths(randomized).interventions)
            theirs = read_interventions(RunPaths(shadow).interventions)
            assert _plan(mine) == _plan(theirs)
            assert {r.kind for r in mine} == {r.kind for r in theirs}
            compared += 1
    assert compared >= 4


def test_random_arm_draws_use_the_pair_seed(experiment: tuple, models: SplitResult) -> None:
    _, _, runs = experiment
    root = runs / "pair-0000"
    job = _job(0)
    arm = random_arm("rule", "quarantine")
    controller = controller_for(arm, models, job, root / TWIN / "run", {},
                                root / detector_arm("rule", "quarantine") / "run")
    assert isinstance(controller, RandomController)
    assert controller.seed == child_seed(SEED, 99, 1, 0)


def test_an_arm_with_no_decision_is_byte_identical_to_its_twin(
    experiment: tuple, models: SplitResult, tmp_path: Path,
) -> None:
    # The experiment skips such arms; this justifies taking the twin's outcomes for them.
    _, _, runs = experiment
    twin = runs / "pair-0001" / TWIN / "run"
    assert not (runs / "pair-0001" / oracle_arm("quarantine")).exists()
    job = _job(1)
    flags = first_flags(models, twin_events(twin), CONTROL.n_ticks)
    assert flags == dict.fromkeys(DETECTORS)
    for arm in (oracle_arm("quarantine"), oracle_arm("revoke")):
        controller = controller_for(arm, models, job, twin, flags)
        arm_dir = run_one(job.condition, job.seed, tmp_path / arm, controller=controller)
        for name in BASE_FILES:
            assert (arm_dir / name).read_bytes() == (twin / name).read_bytes(), name
        assert (arm_dir / "interventions.jsonl").read_bytes() == b""


def _sample_root() -> Path:
    return DATA / "containment" / "raw"


def test_committed_raw_sample_regenerates_byte_for_byte(models: SplitResult,
                                                        tmp_path: Path) -> None:
    (pair,) = sorted(path for path in _sample_root().iterdir() if path.is_dir())
    arms = sorted(path.name for path in pair.iterdir())
    assert len(arms) == 2 and TWIN in arms
    (arm,) = [name for name in arms if name != TWIN]
    job = pair_jobs(ContainmentConfig(seed=SEED))[int(pair.name.removeprefix("pair-"))]
    write_sample(tmp_path, job, arm, models)
    assert _files(tmp_path / pair.name) == _files(pair)
    contained = {path.name for path in (pair / arm).iterdir()}
    assert contained == {f"{name}.gz" for name in RUN_FILES}
    records = gzip.decompress((pair / arm / "interventions.jsonl.gz").read_bytes())
    assert records and json.loads(records.splitlines()[0])["kind"]


def test_random_shortfall_pairs_are_kept_and_filtered_into_the_second_line(
    models: SplitResult,
) -> None:
    measure = measure_arm("rule-quarantine", _facts(False), _facts(True, QUARANTINE), HOSTS)
    jobs = pair_jobs(TINY)
    arm = random_arm("rule", "quarantine")
    results = [PairResult(replace(jobs[0], condition=POSITIVE, index=index), RUN,
                          dict.fromkeys(DETECTORS, 7),
                          tuple(replace(measure, arm=name) for name in ARMS), pd.DataFrame(),
                          {arm: stats}, ARMS)
               for index, stats in enumerate(((5, 3, 1), (2, 2, 0)))]
    text = render(TINY, results, models, "command", {})
    rows = [line for line in text.splitlines() if line.startswith(f"| {arm} | ")]
    every = next(row for row in rows if "| all pairs | 2 |" in row)
    kept = next(row for row in rows if "| pairs without shortfall | 1 |" in row)
    assert every.endswith("| 7 | 5 | 1 |") and kept.endswith("| 2 | 2 | 0 |")
