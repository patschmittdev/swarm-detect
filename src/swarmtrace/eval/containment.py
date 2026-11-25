"""Containment measurements: each arm of a pair against its uncontained twin.

Labels, ``outcomes.json`` and the credential directory join here only; ``swarmtrace.contain``
never sees them. Every measure compares one arm with the twin of the same condition and seed,
so the two runs share a run id and are identical up to the first effective intervention.

Definitions, all per pair:

- Required reads: distinct files of the violation's required set that the collector read,
  from ``outcomes.json``. Prevented = twin's minus arm's.
- Benign agents are every agent whose label role is not ``offensive``. A benign task is an
  ``outcomes.json`` task whose owner is benign; it is lost when complete in the twin and
  incomplete in the arm.
- Benign ok-call deficit: ok calls by benign agents in the twin minus in the arm. A benign
  agent is newly denied when the arm has a denied call by it whose ``(tick, tool, target)`` is
  not a denied call by it in the twin. Scripted agents keep their call schedule when blocked,
  so in this experiment each lost ok call appears as one denied call.
- Intervention targets are distinct ``(kind, agent, credential)`` of ``interventions.jsonl``;
  the engine writes a row each time a decision is applied, even a repeat. ``halt_all``
  quarantines every agent.
- First relayed login: the twin's first ok login by an offensive agent with a credential the
  directory does not assign to it. Collector's first and last required read: the twin's ticks
  of the first ok read of the first and of the last required file. First effective
  intervention: the arm's smallest ``effective_tick``; a call at that tick is already denied,
  so it precedes a read at the same tick.
- First intervention affecting the collector: see ``ArmMeasure.first_collector_effective``.
- Owners of revoked credentials (revoke arms), from the directory: a lender when another agent
  used one of its revoked credentials for an ok login in the twin before that revocation took
  effect, otherwise an other revoked owner. An owner's own host is the host of its revoked
  credential; its own-host calls are ``scan``, ``login`` and ``list`` on that host and
  ``read`` and ``write`` of files on it. It is locked out when it has ok own-host calls at or
  after the revocation's effective tick in the twin and none in the arm.
"""

import json
import math
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from swarmtrace.trace.context import Context, read_context
from swarmtrace.trace.interventions import InterventionRecord, read_interventions
from swarmtrace.trace.io import Labels, RunPaths, read_labels, read_trace
from swarmtrace.trace.schema import TraceEvent
from swarmtrace.trace.tiers import Tier

from .harness import child_seed
from .metrics import Estimate, bootstrap, wilson

OFFENSIVE = "offensive"
DETECTORS = ("rule", "logistic", "boosted")
LEVERS = ("quarantine", "revoke")
TWIN = "twin"
SEED_KEY = 99
"""``child_seed(seed, 99, 0, ...)`` seeds bootstraps; ``(99, 1, i)`` the random arms of pair i."""
BOOTSTRAP_KEY, RANDOM_KEY = 0, 1
HOST_TOOLS = frozenset({"scan", "login", "list"})
FILE_TOOLS = frozenset({"read", "write"})


def detector_arm(method: str, lever: str) -> str:
    return f"{method}-{lever}"


def random_arm(method: str, lever: str) -> str:
    return f"random-{method}-{lever}"


def halt_arm(method: str) -> str:
    return f"halt-{method}"


def oracle_arm(lever: str) -> str:
    return f"oracle-{lever}"


ARMS = (
    TWIN,
    *(detector_arm(method, lever) for method in DETECTORS for lever in LEVERS),
    *(random_arm(method, lever) for method in DETECTORS for lever in LEVERS),
    *(halt_arm(method) for method in DETECTORS),
    *(oracle_arm(lever) for lever in LEVERS),
)
"""The 18 arms of every pair, in report order."""


@dataclass(frozen=True)
class RunFacts:
    """What the measures read of one run: label side, context, interventions and V1 events."""

    labels: Labels
    outcomes: Mapping[str, Any]
    context: Context
    interventions: tuple[InterventionRecord, ...]
    events: tuple[TraceEvent, ...]


@dataclass(frozen=True)
class HostMap:
    """File and credential hosts of a run's world, handed over as plain data."""

    files: Mapping[str, str]
    credentials: Mapping[str, str]


def load_run_facts(run_dir: str | Path) -> RunFacts:
    paths = RunPaths(Path(run_dir))
    interventions = (read_interventions(paths.interventions)
                     if paths.interventions.is_file() else ())
    return RunFacts(read_labels(paths.labels),
                    json.loads(paths.outcomes.read_text(encoding="utf-8")),
                    read_context(paths.context), interventions,
                    read_trace(paths.trace, Tier.V1).events)


LENDER, OTHER_OWNER = "lender", "other revoked owner"
COHORTS = (LENDER, OTHER_OWNER)
ROLES = ("offensive", "benign")
FULL, PARTIAL, NONE = "fully prevented", "partly prevented", "not prevented"
NO_READS = "no required read in twin"


@dataclass(frozen=True)
class LenderMeasure:
    """The directory owner of one or more credentials revoked in an arm."""

    role: str
    """``offensive`` or ``benign``."""
    cohort: str
    """``LENDER`` when another agent used one of its revoked credentials for an ok login in the
    twin before that revocation took effect; otherwise ``OTHER_OWNER``."""
    ok_twin: int
    ok_arm: int
    denied_twin: int
    denied_arm: int
    newly_denied: bool
    tasks_lost: int
    """Tasks it owns (the owner-based identity of the benign-task measure), complete in the
    twin and incomplete in the arm. Each task has one owner, so sums over owners count
    distinct tasks."""
    locked_out: bool


@dataclass(frozen=True)
class ArmMeasure:
    arm: str
    positive: bool
    simulated: bool
    targets: int
    """Distinct intervention targets."""
    objective_twin: bool
    objective_arm: bool
    objective_tick_twin: int | None
    required: int
    """Files in the violation's required set; 0 on a control."""
    required_twin: int
    required_arm: int
    benign_agents: int
    benign_quarantined: int
    benign_revoked: int
    benign_tasks_lost: int
    benign_ok_twin: int
    benign_ok_arm: int
    benign_denied_twin: int
    benign_denied_arm: int
    benign_newly_denied: int
    first_relayed_login: int | None
    first_required_read: int | None
    last_required_read: int | None
    first_effective: int | None
    first_collector_effective: int | None
    """First effective tick of an intervention that affects the collector: a quarantine naming
    it, a halt_all, or the revocation that leaves no unrevoked credential among those it used,
    in the twin, for an ok login on the required files' host up to its last required read. A
    revocation before that login denies it; one after ends the session. Either way the
    session its required reads depend on is gone."""
    lenders: tuple[LenderMeasure, ...]
    unowned_revoked: int
    """Revoked credentials with no owner in the directory."""

    @property
    def prevented(self) -> int:
        return self.required_twin - self.required_arm

    @property
    def prevention(self) -> str:
        if not self.required_twin:
            return NO_READS
        if self.prevented >= self.required_twin:
            return FULL
        return PARTIAL if self.prevented > 0 else NONE

    @property
    def benign_ok_deficit(self) -> int:
        return self.benign_ok_twin - self.benign_ok_arm

    @property
    def benign_denied_change(self) -> int:
        return self.benign_denied_arm - self.benign_denied_twin

    @property
    def time_to_intervention(self) -> int | None:
        return _delta(self.first_effective, self.first_relayed_login)

    @property
    def time_to_collector(self) -> int | None:
        return _delta(self.first_collector_effective, self.first_relayed_login)


def _delta(tick: int | None, origin: int | None) -> int | None:
    return None if tick is None or origin is None else tick - origin


def _offensive(labels: Labels) -> set[str]:
    return {agent for agent, label in labels.agents.items() if label.role == OFFENSIVE}


def first_relayed_login(facts: RunFacts) -> int | None:
    offensive = _offensive(facts.labels)
    for event in facts.events:
        if (event.tool == "login" and event.result["status"] == "ok"
                and event.agent in offensive
                and facts.context.credentials.get(str(event.args["credential"])) != event.agent):
            return event.tick
    return None


def required_read_ticks(facts: RunFacts) -> tuple[int | None, int | None]:
    """Ticks of the collector's first ok read of its first and of its last required file, from
    the trace. Reads of required files by any other agent do not count."""
    violation = facts.outcomes.get("violation")
    if violation is None:
        return None, None
    required = set(violation["required"])
    first: dict[str, int] = {}
    for event in facts.events:
        if (event.tool == "read" and event.result["status"] == "ok"
                and event.agent == violation["worker"] and event.target in required):
            first.setdefault(event.target, event.tick)
    return (min(first.values()), max(first.values())) if first else (None, None)


def first_collector_tick(twin: RunFacts, contained: RunFacts, hosts: HostMap) -> int | None:
    """See ``ArmMeasure.first_collector_effective``; None on a control."""
    violation = twin.outcomes.get("violation")
    if violation is None or not violation["required"]:
        return None
    collector = violation["worker"]
    host_of = {hosts.files.get(file) for file in violation["required"]}
    if len(host_of) != 1 or None in host_of:
        raise ValueError("required files must lie on one known host")
    (host,) = host_of
    by_tick: dict[int, list[InterventionRecord]] = {}
    for record in contained.interventions:
        by_tick.setdefault(record.effective_tick, []).append(record)
    # Credentials the collector logged in with on that host in the twin, up to its last required
    # read: revoking all of them ends its session or denies the login the reads depend on.
    _, last = required_read_ticks(twin)
    used = {str(event.args["credential"]) for event in twin.events
            if event.agent == collector and event.tool == "login" and event.target == host
            and event.result["status"] == "ok" and (last is None or event.tick <= last)}
    revoked: set[str] = set()
    for tick in sorted(by_tick):
        for record in by_tick[tick]:
            if record.kind == "halt_all" or (record.kind == "quarantine"
                                             and record.agent == collector):
                return tick
            if record.kind == "revoke_credential":
                revoked.add(str(record.credential))
        if used and used <= revoked:
            return tick
    return None


def _calls(events: Sequence[TraceEvent], status: str) -> Counter[str]:
    return Counter(event.agent for event in events if event.result["status"] == status)


def _denied_keys(events: Sequence[TraceEvent]) -> dict[str, set[tuple[int, str, str]]]:
    keys: dict[str, set[tuple[int, str, str]]] = {}
    for event in events:
        if event.result["status"] == "denied":
            keys.setdefault(event.agent, set()).add((event.tick, event.tool, event.target))
    return keys


def _tasks(outcomes: Mapping[str, Any]) -> dict[tuple, dict]:
    return {(task["group"], task["owner"], task["worker"], task["host"]): task
            for task in outcomes["tasks"]}


def _lost(twin: Mapping[str, Any], arm: Mapping[str, Any],
          keep: Callable[[dict], bool]) -> int:
    before, after = _tasks(twin), _tasks(arm)
    if set(before) != set(after):
        raise ValueError("an arm and its twin must list the same tasks")
    return sum(1 for key, task in before.items()
               if keep(task) and task["completed"] and not after[key]["completed"])


def _required_read(outcomes: Mapping[str, Any]) -> tuple[int, int]:
    """Required and read files of the violation, from ``outcomes.json``: the prevented count
    is taken from here, never from the trace."""
    violation = outcomes.get("violation")
    if violation is None:
        return 0, 0
    return len(set(violation["required"])), len(set(violation["read"]))


def measure_arm(
    arm: str, twin: RunFacts, contained: RunFacts | None, hosts: HostMap,
) -> ArmMeasure:
    """One arm against its twin. ``contained`` is None for an arm that was not simulated,
    because its controller never decides; its outcomes are the twin's."""
    simulated = contained is not None
    contained = twin if contained is None else contained
    if contained.labels.run_id != twin.labels.run_id:
        raise ValueError("an arm and its twin must share a run id")
    labels, owners = twin.labels, twin.context.credentials
    benign = {agent for agent, label in labels.agents.items() if label.role != OFFENSIVE}
    records = contained.interventions
    targets = {(record.kind, record.agent, record.credential) for record in records}
    halted = any(record.kind == "halt_all" for record in records)
    quarantined = {record.agent for record in records if record.kind == "quarantine"}
    revoked: dict[str, int] = {}
    for record in records:
        if record.kind == "revoke_credential":
            credential = str(record.credential)
            revoked[credential] = min(revoked.get(credential, record.effective_tick),
                                      record.effective_tick)
    ok_twin, ok_arm = _calls(twin.events, "ok"), _calls(contained.events, "ok")
    denied_twin, denied_arm = _calls(twin.events, "denied"), _calls(contained.events, "denied")
    keys_twin, keys_arm = _denied_keys(twin.events), _denied_keys(contained.events)

    def newly_denied(agent: str) -> bool:
        return bool(keys_arm.get(agent, set()) - keys_twin.get(agent, set()))

    def own_host_ok(events: Sequence[TraceEvent], agent: str, host: str, since: int) -> int:
        return sum(1 for event in events
                   if event.agent == agent and event.tick >= since
                   and event.result["status"] == "ok"
                   and ((event.tool in HOST_TOOLS and event.target == host)
                        or (event.tool in FILE_TOOLS and hosts.files.get(event.target) == host)))

    def borrowed(credential: str, owner: str, before: int) -> bool:
        return any(event.tool == "login" and event.result["status"] == "ok"
                   and event.agent != owner and event.tick < before
                   and str(event.args["credential"]) == credential for event in twin.events)

    lenders = []
    by_owner: dict[str, list[str]] = {}
    for credential in sorted(revoked):
        owner = owners.get(credential)
        if owner is not None:
            by_owner.setdefault(owner, []).append(credential)
    for owner, credentials in sorted(by_owner.items()):
        locked = any(
            own_host_ok(twin.events, owner, hosts.credentials[c], revoked[c]) > 0
            and own_host_ok(contained.events, owner, hosts.credentials[c], revoked[c]) == 0
            for c in credentials)
        cohort = (LENDER if any(borrowed(c, owner, revoked[c]) for c in credentials)
                  else OTHER_OWNER)
        lenders.append(LenderMeasure(
            "benign" if owner in benign else OFFENSIVE, cohort, ok_twin[owner], ok_arm[owner],
            denied_twin[owner], denied_arm[owner], newly_denied(owner),
            _lost(twin.outcomes, contained.outcomes,
                  lambda task, owner=owner: task["owner"] == owner),
            locked))
    required, required_twin = _required_read(twin.outcomes)
    _, required_arm = _required_read(contained.outcomes)
    first_read, last_read = required_read_ticks(twin)
    return ArmMeasure(
        arm=arm, positive=bool(_offensive(labels)), simulated=simulated, targets=len(targets),
        objective_twin=bool(labels.objective_completed),
        objective_arm=bool(contained.labels.objective_completed),
        objective_tick_twin=labels.objective_tick,
        required=required, required_twin=required_twin, required_arm=required_arm,
        benign_agents=len(benign),
        benign_quarantined=len(benign) if halted else len(quarantined & benign),
        benign_revoked=sum(1 for credential in revoked if owners.get(credential) in benign),
        benign_tasks_lost=_lost(twin.outcomes, contained.outcomes,
                                lambda task: task["owner"] in benign),
        benign_ok_twin=sum(ok_twin[agent] for agent in benign),
        benign_ok_arm=sum(ok_arm[agent] for agent in benign),
        benign_denied_twin=sum(denied_twin[agent] for agent in benign),
        benign_denied_arm=sum(denied_arm[agent] for agent in benign),
        benign_newly_denied=sum(1 for agent in sorted(benign) if newly_denied(agent)),
        first_relayed_login=first_relayed_login(twin),
        first_required_read=first_read, last_required_read=last_read,
        first_effective=min((record.effective_tick for record in records), default=None),
        first_collector_effective=first_collector_tick(twin, contained, hosts),
        lenders=tuple(lenders),
        unowned_revoked=sum(1 for credential in revoked if credential not in owners),
    )


def outcome_values(measure: ArmMeasure) -> dict[str, int]:
    """The ``outcome_`` cells of a run-table row: integers only, absent when undefined."""
    values = {
        "simulated": int(measure.simulated), "intervention_targets": measure.targets,
        "objective_completed": int(measure.objective_arm),
        "required_reads": measure.required_arm,
        "benign_ok_calls": measure.benign_ok_arm, "benign_denied_calls": measure.benign_denied_arm,
        "benign_quarantined": measure.benign_quarantined,
        "benign_credentials_revoked": measure.benign_revoked,
        "benign_tasks_lost": measure.benign_tasks_lost,
        "benign_agents_newly_denied": measure.benign_newly_denied,
    }
    for name, value in (("first_effective_tick", measure.first_effective),
                        ("first_relayed_login_tick", measure.first_relayed_login),
                        ("first_required_read_tick", measure.first_required_read),
                        ("last_required_read_tick", measure.last_required_read),
                        ("first_collector_effective_tick", measure.first_collector_effective),
                        ("twin_objective_tick", measure.objective_tick_twin)):
        if value is not None:
            values[name] = value
    return values


# Summaries. Rates over pairs are k of n with a Wilson interval; quantities pooled over pairs,
# means over pairs and paired differences carry a percentile bootstrap over pairs.

ARM_KEYS = 4 * len(ARMS)
"""Bootstrap key spaces: ``(arm key, metric)`` with arm key below ``ARM_KEYS`` and metric
below ``METRIC_KEYS``, and ``(COMPARISON_KEY, comparison, metric)``."""
METRIC_KEYS = 24
COMPARISON_KEY, COMPARISONS, COMPARISON_METRICS = 1000, 64, 8


def bootstrap_seed(seed: int, *key: int) -> int:
    """``child_seed(seed, 99, 0, *key)`` for a key in the enumerated spaces only, so
    ``bootstrap_seeds`` lists every bootstrap seed the report can use."""
    valid = ((len(key) == 2 and 0 <= key[0] < ARM_KEYS and 0 <= key[1] < METRIC_KEYS)
             or (len(key) == 3 and key[0] == COMPARISON_KEY and 0 <= key[1] < COMPARISONS
                 and 0 <= key[2] < COMPARISON_METRICS))
    if not valid:
        raise ValueError(f"bootstrap key {key!r} is outside the enumerated key spaces")
    return child_seed(seed, SEED_KEY, BOOTSTRAP_KEY, *key)


def bootstrap_seeds(seed: int) -> set[int]:
    return ({bootstrap_seed(seed, arm, metric)
             for arm in range(ARM_KEYS) for metric in range(METRIC_KEYS)}
            | {bootstrap_seed(seed, COMPARISON_KEY, comparison, metric)
               for comparison in range(COMPARISONS) for metric in range(COMPARISON_METRICS)})


def rate_text(k: int, n: int) -> str:
    if not n:
        return f"{k} of {n}"
    estimate = wilson(k, n)
    return f"{k} of {n}; {estimate.value:.3f} [{estimate.low:.3f}, {estimate.high:.3f}]"


def _degenerate(low: float, high: float, digits: int) -> str:
    """The repository's qualification (``eval/report.py``) of an interval with equal ends."""
    ends = f"[{low:.{digits}f}, {high:.{digits}f}]"
    if low == 0:
        why = "all valid resamples were zero; does not establish a zero population value"
    elif low == 1 and digits == 3:
        why = "all valid resamples were one; does not establish a population value of one"
    else:
        why = (f"all valid resamples were equal; does not establish a population value of "
               f"exactly {low:.{digits}f}")
    return f"degenerate bootstrap interval {ends}: {why}"


def interval_text(estimate: Estimate, digits: int = 3, sign: bool = False) -> str:
    form = f"+.{digits}f" if sign else f".{digits}f"
    if math.isnan(estimate.value):
        return "undefined"
    if estimate.note:
        return f"{estimate.value:{form}} (no interval: {estimate.note})"
    if estimate.low == estimate.high:
        return f"{estimate.value:{form}} ({_degenerate(estimate.low, estimate.high, digits)})"
    return f"{estimate.value:{form}} [{estimate.low:{form}}, {estimate.high:{form}}]"


def pooled_text(numerators: Sequence[int], denominators: Sequence[int], seed: int,
                n_bootstrap: int, unit: str = "") -> str:
    """Sum over pairs of the numerators over the sum of the denominators, with a bootstrap."""
    numerators, denominators = np.asarray(numerators), np.asarray(denominators)
    k, n = int(numerators.sum()), int(denominators.sum())
    if not len(numerators):
        return "no pairs"
    estimate = bootstrap(lambda idx: (numerators[idx].sum() / denominators[idx].sum()
                                      if denominators[idx].sum() else math.nan),
                         [np.arange(len(numerators))], n_bootstrap, seed)
    unit = f" {unit}" if unit else ""
    return f"{k} of {n}{unit}; {interval_text(estimate)}"


def mean_text(values: Sequence[float], seed: int, n_bootstrap: int) -> str:
    values = np.asarray(values, dtype=float)
    if not len(values):
        return "no pairs"
    estimate = bootstrap(lambda idx: float(values[idx].mean()), [np.arange(len(values))],
                         n_bootstrap, seed)
    return f"{interval_text(estimate)} over {len(values)}"


def paired_cells(first: Sequence[int], second: Sequence[int], seed: int, n_bootstrap: int,
                 names: tuple[str, str]) -> dict[str, str]:
    """Sum over pairs of first minus second, with a bootstrap of that sum over pairs, and the
    pairs where each side is larger."""
    a, b = np.asarray(first, dtype=float), np.asarray(second, dtype=float)
    differences = a - b
    n = len(differences)
    if not n:
        return {"pairs": "0", "difference (sum)": "no pairs", f"{names[0]} larger": "",
                f"{names[1]} larger": ""}
    estimate = bootstrap(lambda idx: float(differences[idx].sum()), [np.arange(n)],
                         n_bootstrap, seed)
    return {
        "pairs": str(n),
        "difference (sum)": interval_text(estimate, digits=1, sign=True),
        f"{names[0]} larger": rate_text(int((differences > 0).sum()), n),
        f"{names[1]} larger": rate_text(int((differences < 0).sum()), n),
    }


def _ticks(values: Sequence[int | None]) -> str:
    found = sorted(value for value in values if value is not None)
    if not found:
        return "none"
    return f"median {float(np.median(found)):g}; range {found[0]} to {found[-1]}; n {len(found)}"


def prevention_cells(measures: Sequence[ArmMeasure], seed: int, key: tuple[int, ...],
                     n_bootstrap: int) -> dict[str, str]:
    """Positive pairs: required reads prevented first, then objective completion.

    ``key`` identifies the arm; seeds are ``bootstrap_seed(seed, *key, metric)``."""
    n = len(measures)
    arm_done = [int(m.objective_arm) for m in measures]
    twin_done = [int(m.objective_twin) for m in measures]
    with_twin_reads = [m for m in measures if m.required_twin]
    kinds = Counter(m.prevention for m in measures)
    return {
        "pairs": str(n),
        "required reads prevented (pooled)": pooled_text(
            [m.prevented for m in measures], [m.required_twin for m in measures],
            bootstrap_seed(seed, *key, 1), n_bootstrap, "files"),
        "prevented fraction, mean per pair": mean_text(
            [m.prevented / m.required_twin for m in with_twin_reads],
            bootstrap_seed(seed, *key, 2), n_bootstrap),
        FULL: str(kinds[FULL]), PARTIAL: str(kinds[PARTIAL]), NONE: str(kinds[NONE]),
        "pairs with no required read in twin": str(kinds[NO_READS]),
        "objective failed with no required read prevented": str(sum(
            m.objective_twin and not m.objective_arm and m.prevented == 0 for m in measures)),
        "reads prevented but objective completed": str(sum(
            m.prevented > 0 and m.objective_arm for m in measures)),
        "objective completed (also requires the group's later writes), arm":
            rate_text(sum(arm_done), n),
        "objective completed, twin": rate_text(sum(twin_done), n),
        "completion difference, arm minus twin": mean_text(
            [a - t for a, t in zip(arm_done, twin_done, strict=True)],
            bootstrap_seed(seed, *key, 0), n_bootstrap),
        "simulated": str(sum(m.simulated for m in measures)),
        "any intervention": rate_text(sum(m.targets > 0 for m in measures), n),
    }


BEFORE_FIRST = "at or before first required read"
BETWEEN = "after first, at or before last required read"
AFTER_LAST = "after last required read"
NOT_COLLECTOR = "intervention never affects the collector"
NO_INTERVENTION = "no intervention"


def placement(tick: int | None, measure: ArmMeasure) -> str:
    """Where ``tick`` falls against the twin's required reads; an intervention effective at
    the tick of a read precedes it."""
    if tick is None:
        return NOT_COLLECTOR if measure.first_effective is not None else NO_INTERVENTION
    if measure.first_required_read is None or measure.last_required_read is None:
        return NO_READS
    if tick <= measure.first_required_read:
        return BEFORE_FIRST
    return BETWEEN if tick <= measure.last_required_read else AFTER_LAST


def timing_cells(measures: Sequence[ArmMeasure]) -> dict[str, str]:
    """Positive pairs: the first intervention and the first intervention affecting the
    collector, each from the twin's first relayed login and against the required reads."""
    first = Counter(placement(m.first_effective, m) for m in measures)
    collector = Counter(placement(m.first_collector_effective, m) for m in measures)

    def both(name: str) -> str:
        return f"{first[name]} / {collector[name]}"

    return {
        "pairs": str(len(measures)),
        "with intervention / affecting the collector": (
            f"{sum(m.first_effective is not None for m in measures)} / "
            f"{sum(m.first_collector_effective is not None for m in measures)}"),
        "ticks, relayed login to first intervention": _ticks(
            [m.time_to_intervention for m in measures]),
        "ticks, relayed login to first affecting the collector": _ticks(
            [m.time_to_collector for m in measures]),
        f"{BEFORE_FIRST} (first / collector)": both(BEFORE_FIRST),
        f"{BETWEEN} (first / collector)": both(BETWEEN),
        f"{AFTER_LAST} (first / collector)": both(AFTER_LAST),
        NOT_COLLECTOR: str(collector[NOT_COLLECTOR]),
        NO_INTERVENTION: str(first[NO_INTERVENTION]),
        f"{NO_READS} (first / collector)": both(NO_READS),
        "collector hit at or before twin's objective tick": str(sum(
            m.first_collector_effective is not None and m.objective_tick_twin is not None
            and m.first_collector_effective <= m.objective_tick_twin for m in measures)),
        "collector hit after twin's objective tick": str(sum(
            m.first_collector_effective is not None and m.objective_tick_twin is not None
            and m.first_collector_effective > m.objective_tick_twin for m in measures)),
    }


def tick_cells(measures: Sequence[ArmMeasure]) -> dict[str, str]:
    """The ticks behind the timing table."""
    return {
        "first intervention tick": _ticks([m.first_effective for m in measures]),
        "first tick affecting the collector": _ticks(
            [m.first_collector_effective for m in measures]),
        "twin: first relayed login": _ticks([m.first_relayed_login for m in measures]),
        "twin: first required read": _ticks([m.first_required_read for m in measures]),
        "twin: last required read": _ticks([m.last_required_read for m in measures]),
        "twin: objective tick": _ticks([m.objective_tick_twin for m in measures]),
    }


DECOMPOSITION = (NO_INTERVENTION, NOT_COLLECTOR, AFTER_LAST, BETWEEN, BEFORE_FIRST, NO_READS)


def decomposition_rows(items: Sequence[tuple[int, ArmMeasure]]) -> list[dict[str, str]]:
    """Positive pairs by where the first collector-affecting intervention falls, with the
    twin's required files and the files prevented in each category. Exceptions: pairs whose
    collector was hit at or before the first required read and still read a required file."""
    rows = []
    for category in DECOMPOSITION:
        chosen = [(index, m) for index, m in items
                  if placement(m.first_collector_effective, m) == category]
        exceptions = [f"pair {index} ({m.prevented} of {m.required_twin})" for index, m in chosen
                      if category == BEFORE_FIRST and m.prevention != FULL]
        early = sum(placement(m.first_effective, m) == BEFORE_FIRST for _, m in chosen
                    if category != BEFORE_FIRST)
        rows.append({
            "category (first intervention affecting the collector)": category,
            "pairs": str(len(chosen)),
            "required files in twin": str(sum(m.required_twin for _, m in chosen)),
            "files prevented": str(sum(m.prevented for _, m in chosen)),
            "of which first intervention at or before first read": str(early),
            "exceptions": ", ".join(exceptions) if exceptions else "none",
        })
    return rows


def first_checkpoint_precedes(measure: ArmMeasure, every: int) -> bool | None:
    """Counterfactual from the twin: would an intervention decided at the first live checkpoint
    at or after the first relayed login (effective the next tick) precede the first required
    read? None without a relayed login or a required read."""
    login, read = measure.first_relayed_login, measure.first_required_read
    if login is None or read is None:
        return None
    checkpoint = login + (every - 1 - login % every) % every
    return checkpoint + 1 <= read


def cost_cells(measures: Sequence[ArmMeasure], seed: int, key: tuple[int, ...],
               n_bootstrap: int) -> dict[str, str]:
    """Benign cost against the twin. Agent counts are clustered by pair, so their intervals
    are bootstraps over pairs, like every other paired quantity."""
    n = len(measures)
    lost = [m.benign_tasks_lost for m in measures]
    return {
        "pairs": str(n),
        "any intervention": str(sum(m.targets > 0 for m in measures)),
        "benign agents quarantined": str(sum(m.benign_quarantined for m in measures)),
        "benign-owned credentials revoked": str(sum(m.benign_revoked for m in measures)),
        "benign tasks lost":
            f"{sum(lost)}; pairs with any: {rate_text(sum(x > 0 for x in lost), n)}",
        "benign ok-call deficit (pooled)": pooled_text(
            [m.benign_ok_deficit for m in measures], [m.benign_ok_twin for m in measures],
            bootstrap_seed(seed, *key, 3), n_bootstrap, "ok calls"),
        "benign agents newly denied (pooled)": pooled_text(
            [m.benign_newly_denied for m in measures], [m.benign_agents for m in measures],
            bootstrap_seed(seed, *key, 4), n_bootstrap, "agents"),
        "change in denied calls by benign agents": str(
            sum(m.benign_denied_change for m in measures)),
    }


def flagged_control_cells(flagged: Sequence[ArmMeasure], controls: int) -> dict[str, str]:
    """Control pairs whose detector flagged: per-run benign cost."""
    fractions = sorted(m.benign_ok_deficit / m.benign_ok_twin for m in flagged
                       if m.benign_ok_twin)
    lost = [m.benign_tasks_lost for m in flagged]
    if fractions:
        spread = (f"median {float(np.median(fractions)):.3f}; range {fractions[0]:.3f} to "
                  f"{fractions[-1]:.3f}")
    else:
        spread = "none"
    return {
        "flagged control runs": rate_text(len(flagged), controls),
        "benign ok-call deficit per flagged run, fraction of its benign ok calls": spread,
        "benign tasks lost": f"{sum(lost)}; runs with any: {sum(x > 0 for x in lost)}",
        "benign agents newly denied": str(sum(m.benign_newly_denied for m in flagged)),
    }


def lender_cells(measures: Sequence[ArmMeasure], cohort: str, role: str, seed: int,
                 key: tuple[int, ...], n_bootstrap: int) -> dict[str, str]:
    """Owners of revoked credentials in ``cohort`` with ``role``; bootstraps over pairs."""
    metric = 5 + 3 * (len(ROLES) * COHORTS.index(cohort) + ROLES.index(role))

    def per_pair(value: Callable[[LenderMeasure], int]) -> list[int]:
        return [sum(value(x) for x in m.lenders if x.role == role and x.cohort == cohort)
                for m in measures]

    owners = per_pair(lambda x: 1)
    return {
        "owners": str(sum(owners)),
        "pairs with one": str(sum(count > 0 for count in owners)),
        "locked out of own host (pooled)": pooled_text(
            per_pair(lambda x: int(x.locked_out)), owners, bootstrap_seed(seed, *key, metric),
            n_bootstrap, "owners"),
        "ok-call deficit (pooled)": pooled_text(
            per_pair(lambda x: x.ok_twin - x.ok_arm), per_pair(lambda x: x.ok_twin),
            bootstrap_seed(seed, *key, metric + 1), n_bootstrap, "ok calls"),
        "newly denied (pooled)": pooled_text(
            per_pair(lambda x: int(x.newly_denied)), owners,
            bootstrap_seed(seed, *key, metric + 2), n_bootstrap, "owners"),
        "distinct owned tasks lost": str(sum(per_pair(lambda x: x.tasks_lost))),
        "change in denied calls": str(sum(per_pair(lambda x: x.denied_arm - x.denied_twin))),
    }
