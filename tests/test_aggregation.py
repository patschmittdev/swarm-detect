import ast
from dataclasses import replace
from pathlib import Path

import pandas as pd
import pytest

import swarmtrace.features as features
from swarmtrace.features import (
    AGENT_FEATURES,
    EXPANSION_WINDOW,
    FAMILIES,
    PAIR_FEATURES,
    RUN_FEATURES,
    THRESHOLDS,
    agent_features,
    feature_columns,
    pair_features,
    run_features,
)
from swarmtrace.trace.io import Trace, read_trace
from swarmtrace.trace.schema import TraceEvent, validate_trace
from swarmtrace.trace.tiers import Tier

EXPANSION = "access_expansion_after_receipt"
SHARED = "shared_credential_logins"
AGGREGATION = (EXPANSION, SHARED)
EXISTING_FIXTURES = ("all_benign", "messaging_pair", "shared_file_trio", "benign_team", "denials")

A, B, C = "a-00000001", "a-00000002", "a-00000003"
H1, H2 = "h-00000001", "h-00000002"
F1 = "f-00000001"
C1, C2, C3 = "c-00000001", "c-00000002", "c-00000003"

X, D1, D2 = "a-40b6f2d8", "a-1c7e5a90", "a-5b38d0f4"
S1, S2, O1, O2 = "a-73a9e216", "a-9f04c6b1", "a-c2d81b57", "a-e85f3a0c"
DELEGATION, SLOPPY, RELAY = (tuple(sorted(p)) for p in ((D1, D2), (S1, S2), (O1, O2)))


def load(fixtures_dir: Path, name: str, tier: Tier = Tier.V2) -> Trace:
    return read_trace(fixtures_dir / name / "trace.jsonl", tier=tier)


def make_trace(rows: list[tuple], tier: Tier = Tier.V1) -> Trace:
    """Rows are ``(tick, agent, tool, target)`` plus an optional status and, for logins, a
    credential, written ``(tick, agent, "login", host, status, credential)``."""
    events = []
    for seq, row in enumerate(rows):
        tick, agent, tool, target, *rest = row
        status = rest[0] if rest else "ok"
        args: dict[str, int | str] = {}
        if tier is not Tier.V0:
            if tool == "login":
                args = {"credential": rest[1]}
            elif tool in ("write", "send", "recv"):
                args = {"size": 0, "digest": "0000000000000000"}
        events.append(TraceEvent(
            schema_version=1, run_id="0123456789abcdef", seq=seq, tick=tick, agent=agent,
            tool=tool, target=target, args=args, result={"status": status, "size": 0},
            content=None, provenance=None,
        ))
    validate_trace(events, tier=tier)
    return Trace("0123456789abcdef", tier, tuple(events))


def counts(trace: Trace, column: str) -> dict[tuple[str, str], int]:
    frame = pair_features(trace)
    return {pair: int(value) for pair, value in frame[column].items() if value}


def test_family_registry() -> None:
    assert FAMILIES == ("generic", "aggregation")
    assert EXPANSION_WINDOW == 20
    assert {spec.family for spec in AGENT_FEATURES} == {"generic"}
    assert [spec.name for spec in PAIR_FEATURES if spec.family == "aggregation"] == list(
        AGGREGATION
    )
    specs = {spec.name: spec for spec in PAIR_FEATURES}
    assert specs[EXPANSION].tier is Tier.V0
    assert specs[SHARED].tier is Tier.V1
    assert specs[EXPANSION].direction == specs[SHARED].direction == "higher"
    for spec in RUN_FEATURES:
        source = next(pair for pair in PAIR_FEATURES if spec.name.startswith(pair.name + "_"))
        assert spec.family == source.family
    assert THRESHOLDS[EXPANSION] == THRESHOLDS[SHARED] == 0.0


@pytest.mark.parametrize("tier", list(Tier))
@pytest.mark.parametrize("level", ["agent", "pair", "run"])
def test_feature_columns_filter_by_family(level: str, tier: Tier) -> None:
    every = feature_columns(level, tier)
    generic = feature_columns(level, tier, families=("generic",))
    aggregation = feature_columns(level, tier, families=("aggregation",))
    assert feature_columns(level, tier, families=FAMILIES) == every
    assert feature_columns(level, tier, families=("aggregation", "generic")) == every
    assert set(generic) | set(aggregation) == set(every)
    assert not set(generic) & set(aggregation)
    assert generic == tuple(name for name in every if name in generic)
    assert feature_columns(level, tier, families=()) == ()
    assert not any(name.startswith(AGGREGATION) for name in generic)


def test_feature_columns_aggregation_by_tier() -> None:
    assert feature_columns("pair", Tier.V0, families=("aggregation",)) == (EXPANSION,)
    assert feature_columns("pair", Tier.V1, families=("aggregation",)) == AGGREGATION
    assert feature_columns("run", Tier.V0, families=("aggregation",)) == tuple(
        f"{EXPANSION}_{suffix}" for suffix in ("max", "top_k_mean", "n_above")
    )
    assert feature_columns("run", Tier.V2, families=("aggregation",)) == tuple(
        f"{name}_{suffix}" for name in AGGREGATION for suffix in ("max", "top_k_mean", "n_above")
    )
    assert feature_columns("agent", Tier.V2, families=("aggregation",)) == ()
    assert feature_columns("pair", Tier.V2)[-2:] == AGGREGATION


def test_feature_columns_rejects_unknown_family() -> None:
    with pytest.raises(ValueError, match="family"):
        feature_columns("pair", Tier.V0, families=("generic", "privilege"))
    with pytest.raises(ValueError, match="family"):
        feature_columns("pair", Tier.V0, families="generic")


@pytest.mark.parametrize("tier", [Tier.V1, Tier.V2])
def test_credential_relay_pair_values(fixtures_dir: Path, tier: Tier) -> None:
    trace = load(fixtures_dir, "credential_relay", tier)
    frame = pair_features(trace)
    assert len(frame) == 21
    assert counts(trace, EXPANSION) == {DELEGATION: 1, SLOPPY: 1, RELAY: 1}
    assert counts(trace, SHARED) == {SLOPPY: 1, RELAY: 1}
    assert frame[EXPANSION].dtype == frame[SHARED].dtype == "int64"


def test_credential_relay_at_v0(fixtures_dir: Path) -> None:
    trace = load(fixtures_dir, "credential_relay", Tier.V0)
    frame = pair_features(trace)
    assert SHARED not in frame.columns
    assert counts(trace, EXPANSION) == {DELEGATION: 1, SLOPPY: 1, RELAY: 1}
    run = run_features(trace)
    assert not any(column.startswith(SHARED) for column in run.columns)
    assert run.iloc[0][f"{EXPANSION}_max"] == 1.0


def test_credential_relay_run_values(fixtures_dir: Path) -> None:
    row = run_features(load(fixtures_dir, "credential_relay")).iloc[0]
    assert row[f"{EXPANSION}_max"] == 1.0
    assert row[f"{EXPANSION}_top_k_mean"] == 1.0
    assert row[f"{EXPANSION}_n_above"] == 3
    assert row[f"{SHARED}_max"] == 1.0
    assert row[f"{SHARED}_top_k_mean"] == pytest.approx(2 / 3)
    assert row[f"{SHARED}_n_above"] == 2


@pytest.mark.parametrize("tier", list(Tier))
@pytest.mark.parametrize("name", EXISTING_FIXTURES)
def test_existing_fixtures_have_no_aggregation(fixtures_dir: Path, name: str, tier: Tier) -> None:
    frame = pair_features(load(fixtures_dir, name, tier))
    for column in feature_columns("pair", tier, families=("aggregation",)):
        assert (frame[column] == 0).all()


def test_expansion_after_message() -> None:
    trace = make_trace([
        (0, A, "login", H1, "ok", C1), (1, A, "send", B), (2, B, "recv", A),
        (3, B, "login", H1, "ok", C2),
    ])
    assert counts(trace, EXPANSION) == {(A, B): 1}
    assert counts(trace, SHARED) == {}


def test_expansion_after_reading_latest_write() -> None:
    trace = make_trace([
        (0, A, "login", H1, "ok", C1), (1, A, "write", F1), (2, B, "read", F1),
        (3, B, "login", H1, "ok", C2),
    ])
    assert counts(trace, EXPANSION) == {(A, B): 1}
    overwritten = make_trace([
        (0, A, "login", H1, "ok", C1), (1, A, "write", F1), (1, C, "write", F1),
        (2, B, "read", F1), (3, B, "login", H1, "ok", C2),
    ])
    assert counts(overwritten, EXPANSION) == {}
    failed_overwrite = make_trace([
        (0, A, "login", H1, "ok", C1), (1, A, "write", F1), (1, C, "write", F1, "denied"),
        (2, B, "read", F1), (3, B, "login", H1, "ok", C2),
    ])
    assert counts(failed_overwrite, EXPANSION) == {(A, B): 1}


def test_expansion_requires_first_login() -> None:
    trace = make_trace([
        (0, B, "login", H1, "ok", C2), (0, A, "login", H1, "ok", C1), (1, A, "send", B),
        (2, B, "recv", A), (3, B, "login", H1, "ok", C2),
    ])
    assert counts(trace, EXPANSION) == {}


def test_expansion_counts_first_ok_login_only_once() -> None:
    trace = make_trace([
        (0, A, "login", H1, "ok", C1), (1, A, "send", B), (2, B, "recv", A),
        (3, B, "login", H1, "ok", C2), (4, B, "login", H1, "ok", C2),
    ])
    assert counts(trace, EXPANSION) == {(A, B): 1}


def test_expansion_requires_sender_login_to_the_host() -> None:
    trace = make_trace([
        (0, A, "login", H2, "ok", C1), (1, A, "send", B), (2, B, "recv", A),
        (3, B, "login", H1, "ok", C2),
    ])
    assert counts(trace, EXPANSION) == {}


def test_expansion_requires_sender_login_before_the_receivers_login() -> None:
    between = make_trace([
        (1, A, "send", B), (2, B, "recv", A), (3, A, "login", H1, "ok", C1),
        (4, B, "login", H1, "ok", C2),
    ])
    assert counts(between, EXPANSION) == {(A, B): 1}
    after = make_trace([
        (1, A, "send", B), (2, B, "recv", A), (3, B, "login", H1, "ok", C2),
        (4, A, "login", H1, "ok", C1),
    ])
    assert counts(after, EXPANSION) == {}


def test_expansion_ignores_denied_logins() -> None:
    denied_receiver = make_trace([
        (0, A, "login", H1, "ok", C1), (1, A, "send", B), (2, B, "recv", A),
        (3, B, "login", H1, "denied", C2),
    ])
    assert counts(denied_receiver, EXPANSION) == {}
    retried = make_trace([
        (0, A, "login", H1, "ok", C1), (1, A, "send", B), (2, B, "recv", A),
        (3, B, "login", H1, "denied", C2), (4, B, "login", H1, "ok", C1),
    ])
    assert counts(retried, EXPANSION) == {(A, B): 1}
    denied_sender = make_trace([
        (0, A, "login", H1, "denied", C1), (1, A, "send", B), (2, B, "recv", A),
        (3, B, "login", H1, "ok", C2),
    ])
    assert counts(denied_sender, EXPANSION) == {}


def test_expansion_ignores_failed_receipts() -> None:
    trace = make_trace([
        (0, A, "login", H1, "ok", C1), (1, A, "write", F1), (2, B, "read", F1, "denied"),
        (2, B, "recv", A, "not_found"), (3, B, "login", H1, "ok", C2),
    ])
    assert counts(trace, EXPANSION) == {}


@pytest.mark.parametrize(("delay", "expected"), [(EXPANSION_WINDOW, 1), (EXPANSION_WINDOW + 1, 0)])
def test_expansion_window_is_inclusive(delay: int, expected: int) -> None:
    trace = make_trace([
        (0, A, "login", H1, "ok", C1), (1, A, "send", B), (2, B, "recv", A),
        (2 + delay, B, "login", H1, "ok", C2),
    ])
    assert pair_features(trace).loc[(A, B), EXPANSION] == expected


def test_expansion_uses_the_latest_receipt() -> None:
    trace = make_trace([
        (0, A, "login", H1, "ok", C1), (1, A, "send", B), (1, A, "send", B), (2, B, "recv", A),
        (30, B, "recv", A), (45, B, "login", H1, "ok", C2),
    ])
    assert counts(trace, EXPANSION) == {(A, B): 1}


def test_expansion_receipt_must_precede_login() -> None:
    same_tick = make_trace([
        (0, A, "login", H1, "ok", C1), (1, A, "send", B), (2, B, "recv", A),
        (2, B, "login", H1, "ok", C2),
    ])
    assert counts(same_tick, EXPANSION) == {(A, B): 1}
    login_first = make_trace([
        (0, A, "login", H1, "ok", C1), (1, A, "send", B), (2, B, "login", H1, "ok", C2),
        (2, B, "recv", A),
    ])
    assert counts(login_first, EXPANSION) == {}


def test_expansion_counts_one_per_login_and_sender() -> None:
    trace = make_trace([
        (0, A, "login", H1, "ok", C1), (0, C, "login", H1, "ok", C3), (1, A, "send", B),
        (1, A, "write", F1), (1, C, "send", B), (2, B, "recv", A), (2, B, "read", F1),
        (2, B, "recv", C), (3, B, "login", H1, "ok", C2),
    ])
    assert counts(trace, EXPANSION) == {(A, B): 1, (B, C): 1}


def test_expansion_sums_both_orderings() -> None:
    trace = make_trace([
        (0, A, "login", H1, "ok", C1), (0, B, "login", H2, "ok", C2), (1, A, "send", B),
        (1, B, "send", A), (2, B, "recv", A), (2, A, "recv", B), (3, B, "login", H1, "ok", C2),
        (3, A, "login", H2, "ok", C1),
    ])
    assert counts(trace, EXPANSION) == {(A, B): 2}


def test_self_receipts_do_not_count() -> None:
    trace = make_trace([
        (0, A, "login", H1, "ok", C1), (1, A, "send", A), (2, A, "recv", A),
        (2, A, "write", F1), (3, A, "read", F1), (4, A, "login", H2, "ok", C1),
        (5, B, "scan", H1),
    ])
    assert counts(trace, EXPANSION) == {}
    assert counts(trace, SHARED) == {}


def test_shared_credential_between_two_agents() -> None:
    trace = make_trace([
        (0, A, "login", H1, "ok", C1), (1, B, "login", H2, "ok", C1),
        (2, B, "login", H1, "ok", C1),
    ])
    assert counts(trace, SHARED) == {(A, B): 2}


def test_shared_credential_by_three_agents() -> None:
    trace = make_trace([
        (0, A, "login", H1, "ok", C1), (1, B, "login", H1, "ok", C1),
        (2, C, "login", H1, "ok", C1),
    ])
    assert counts(trace, SHARED) == {(A, B): 1, (A, C): 1}


def test_shared_credential_own_reuse() -> None:
    alone = make_trace([
        (0, A, "login", H1, "ok", C1), (1, A, "login", H2, "ok", C1),
        (2, B, "login", H1, "ok", C2), (3, B, "login", H1, "ok", C2),
    ])
    assert counts(alone, SHARED) == {}
    after_other = make_trace([
        (0, A, "login", H1, "ok", C1), (1, B, "login", H1, "ok", C1),
        (2, A, "login", H1, "ok", C1),
    ])
    assert counts(after_other, SHARED) == {(A, B): 1}


def test_shared_credential_first_user_never_counts() -> None:
    handover = make_trace([
        (0, B, "login", H1, "ok", C1), (1, A, "login", H1, "ok", C1),
        (2, B, "login", H2, "ok", C1), (3, A, "login", H2, "ok", C1),
    ])
    assert counts(handover, SHARED) == {(A, B): 2}
    later_users = make_trace([
        (0, A, "login", H1, "ok", C1), (1, B, "login", H1, "ok", C1),
        (2, C, "login", H1, "ok", C1), (3, B, "login", H2, "ok", C1),
        (4, C, "login", H2, "ok", C1),
    ])
    assert counts(later_users, SHARED) == {(A, B): 2, (A, C): 2}


def test_shared_credential_ignores_denied_logins() -> None:
    trace = make_trace([
        (0, A, "login", H1, "denied", C1), (1, B, "login", H1, "ok", C1),
        (2, A, "login", H1, "ok", C2), (3, B, "login", H1, "denied", C2),
    ])
    assert counts(trace, SHARED) == {}
    first_user_after_denial = make_trace([
        (0, A, "login", H1, "denied", C1), (1, B, "login", H1, "ok", C1),
        (2, A, "login", H1, "ok", C1),
    ])
    assert counts(first_user_after_denial, SHARED) == {(A, B): 1}


def test_shared_credential_is_absent_at_v0() -> None:
    trace = make_trace([
        (0, A, "login", H1, "ok", C1), (1, A, "send", B), (2, B, "recv", A),
        (3, B, "login", H1, "ok", C1),
    ], tier=Tier.V0)
    frame = pair_features(trace)
    assert list(frame.columns) == list(feature_columns("pair", Tier.V0))
    assert SHARED not in frame.columns
    assert frame.loc[(A, B), EXPANSION] == 1


def test_aggregation_respects_until_tick(fixtures_dir: Path) -> None:
    trace = load(fixtures_dir, "credential_relay")
    assert counts_at(trace, 11, EXPANSION) == {DELEGATION: 1, SLOPPY: 1}
    assert counts_at(trace, 12, EXPANSION) == {DELEGATION: 1, SLOPPY: 1, RELAY: 1}
    assert counts_at(trace, 12, SHARED) == {SLOPPY: 1, RELAY: 1}
    assert counts_at(trace, 13, SHARED) == {SLOPPY: 1, RELAY: 1}


def counts_at(trace: Trace, tick: int, column: str) -> dict[tuple[str, str], int]:
    frame = pair_features(trace, until_tick=tick)
    return {pair: int(value) for pair, value in frame[column].items() if value}


def test_package_never_imports_detect_or_eval() -> None:
    package = Path(features.__file__).parent
    for path in package.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [("." * node.level) + (node.module or "")]
            for name in names:
                assert not name.startswith(("swarmtrace.detect", "swarmtrace.eval")), name
                assert not name.lstrip(".").startswith(("detect", "eval")), name


FUNCTIONS = (agent_features, pair_features, run_features)
LEVELS = ("agent", "pair", "run")


def renamed_id(agent: str) -> str:
    return f"a-{0xFFFFFFFF - int(agent[2:], 16):08x}"


def rename(trace: Trace) -> Trace:
    events = tuple(
        replace(
            event,
            agent=renamed_id(event.agent),
            target=renamed_id(event.target) if event.tool in ("send", "recv") else event.target,
        )
        for event in trace.events
    )
    return Trace(trace.run_id, trace.tier, events)


@pytest.mark.parametrize("tier", list(Tier))
def test_credential_relay_columns_follow_tier(fixtures_dir: Path, tier: Tier) -> None:
    trace = load(fixtures_dir, "credential_relay", tier)
    full = load(fixtures_dir, "credential_relay")
    for function, level in zip(FUNCTIONS, LEVELS):
        frame = function(trace)
        assert tuple(frame.columns) == feature_columns(level, tier)
        pd.testing.assert_frame_equal(frame, function(full)[list(frame.columns)])


@pytest.mark.parametrize("tier", list(Tier))
def test_credential_relay_prefix(fixtures_dir: Path, tier: Tier) -> None:
    trace = load(fixtures_dir, "credential_relay", tier)
    last = trace.events[-1].tick
    for function in FUNCTIONS:
        pd.testing.assert_frame_equal(function(trace, until_tick=last), function(trace))
    for tick in range(-1, last + 2):
        cut = Trace(trace.run_id, trace.tier, tuple(e for e in trace.events if e.tick <= tick))
        for function, level in zip(FUNCTIONS, LEVELS):
            frame = function(trace, until_tick=tick)
            assert tuple(frame.columns) == feature_columns(level, tier)
            pd.testing.assert_frame_equal(frame, function(cut, until_tick=tick))


@pytest.mark.parametrize("tier", list(Tier))
def test_credential_relay_invariant_to_agent_renaming(fixtures_dir: Path, tier: Tier) -> None:
    trace = load(fixtures_dir, "credential_relay", tier)
    renamed = rename(trace)
    assert list(map(renamed_id, trace.agents)) == list(reversed(renamed.agents))
    agents = agent_features(trace)
    agents.index = agents.index.map(renamed_id)
    pd.testing.assert_frame_equal(agents.sort_index(), agent_features(renamed))
    pairs = pair_features(trace)
    pairs.index = pd.MultiIndex.from_tuples(
        [tuple(sorted(map(renamed_id, pair))) for pair in pairs.index],
        names=["agent_a", "agent_b"],
    )
    pd.testing.assert_frame_equal(pairs.sort_index(), pair_features(renamed))
    pd.testing.assert_frame_equal(run_features(trace), run_features(renamed))
