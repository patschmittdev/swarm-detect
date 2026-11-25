import gzip
import json
import math
from dataclasses import replace
from pathlib import Path

import pandas as pd
import pytest

from swarmtrace.eval.recorded import load_recorded
from swarmtrace.features import (
    FAMILIES,
    PAIR_FEATURES,
    RUN_FEATURES,
    SCOPE,
    SCOPE_PAIR_FEATURES,
    SCOPE_RUN_FEATURES,
    SCOPE_THRESHOLDS,
    THRESHOLDS,
    FeatureSpec,
    agent_features,
    feature_columns,
    pair_features,
    run_features,
)
from swarmtrace.sim.runner import Condition, build_run, run_one
from swarmtrace.trace.context import (
    Context,
    ContextLevel,
    HandoffScope,
    project_context,
    read_context,
)
from swarmtrace.trace.io import Trace, read_trace
from swarmtrace.trace.schema import TraceEvent, validate_trace
from swarmtrace.trace.tiers import Tier, project

DATA = Path(__file__).resolve().parents[1] / "data"
RUN_ID = "0123456789abcdef"
FIXTURE_NAMES = ("all_benign", "messaging_pair", "shared_file_trio", "benign_team", "denials",
                 "credential_relay")
SCOPE_NAMES = ("borrowed_session_breadth", "out_of_scope_reads_borrowed",
               "out_of_scope_reads_own")
LEVELS = tuple(ContextLevel)

A, B, C = "a-00000001", "a-00000002", "a-00000003"
HA, HB = "h-0000000a", "h-0000000b"
CA, CB = "c-0000000a", "c-0000000b"
F1, F2, F3, F4, F9 = "f-00000001", "f-00000002", "f-00000003", "f-00000004", "f-00000009"
DIRECTORY = {CA: A, CB: B}

Row = tuple[int, str, str, str, str] | tuple[int, str, str, str, str, str]


def make_trace(rows: list[Row], tier: Tier = Tier.V1) -> Trace:
    """Rows are (tick, agent, tool, target, status[, credential]); logins carry a credential."""
    events = []
    for seq, row in enumerate(rows):
        tick, agent, tool, target, status = row[:5]
        args = {"credential": row[5]} if tool == "login" else {}
        if tool == "list":
            args = {"prefix": ""}
        event = TraceEvent(
            schema_version=1, run_id=RUN_ID, seq=seq, tick=tick, agent=agent, tool=tool,
            target=target, args=args, result={"status": status, "size": 0},
            content=None, provenance=None,
        )
        events.append(project(event, tier))
    validate_trace(tuple(events), tier=tier)
    return Trace(RUN_ID, tier, tuple(events))


def context(level: ContextLevel, handoffs: tuple[HandoffScope, ...] = (),
            credentials: dict[str, str] | None = None, run_id: str = RUN_ID) -> Context:
    full = Context(run_id, ContextLevel.C2, dict(DIRECTORY if credentials is None
                                                  else credentials), handoffs)
    return project_context(full, level)


def scope_row(trace: Trace, level: ContextLevel, handoffs: tuple[HandoffScope, ...] = (),
              pair: tuple[str, str] = (A, B), **kwargs: object) -> pd.Series:
    frame = pair_features(trace, context=context(level, handoffs), **kwargs)
    return frame.loc[pair]


# Fixture A: the lender logs in first; the borrower logs in with the lender's credential, reads
# three new files of which two are in the hand-off scope, and re-reads one.
FIXTURE_A = [
    (0, A, "login", HA, "ok", CA),
    (0, B, "login", HB, "ok", CB),
    (0, C, "scan", HA, "ok"),
    (1, B, "login", HA, "ok", CA),
    (2, B, "read", F1, "ok"),
    (3, B, "read", F2, "ok"),
    (4, B, "read", F3, "ok"),
    (5, B, "read", F3, "ok"),
]
HANDOFF_A = (HandoffScope(A, B, HA, (F1, F2)),)

# Fixture B: delegation under the receiver's own credential with one read outside scope.
FIXTURE_B = [
    (0, A, "login", HA, "ok", CA),
    (0, B, "login", HB, "ok", CB),
    (1, B, "login", HA, "ok", CB),
    (2, B, "read", F1, "ok"),
    (3, B, "read", F9, "ok"),
]
HANDOFF_B = (HandoffScope(A, B, HA, (F1,)),)

# Fixture C: the borrower uses the lender's credential first and the owner never does.
FIXTURE_C = [
    (0, A, "scan", HA, "ok"),
    (0, B, "login", HB, "ok", CB),
    (1, B, "login", HA, "ok", CA),
    (2, B, "read", F1, "ok"),
    (3, B, "read", F2, "ok"),
    (4, B, "read", F3, "ok"),
]

# Reads before the borrowed login, denied reads, and a denied borrowed login are excluded.
FIXTURE_EXCLUSIONS = [
    (0, A, "login", HA, "ok", CA),
    (0, B, "login", HA, "denied", CA),
    (1, B, "read", F1, "ok"),
    (1, B, "read", F9, "ok"),
    (2, B, "login", HA, "ok", CA),
    (3, B, "read", F1, "ok"),
    (3, B, "read", F2, "denied"),
    (4, B, "read", F3, "ok"),
    (6, B, "read", F4, "ok"),
    (7, B, "read", F2, "ok"),
]
HANDOFF_EXCLUSIONS = (HandoffScope(A, B, HA, (F3,)),)


def test_registry() -> None:
    assert SCOPE == "scope" and SCOPE not in FAMILIES
    assert [spec.name for spec in SCOPE_PAIR_FEATURES] == list(SCOPE_NAMES)
    assert {(spec.name, spec.tier, spec.context, spec.direction, spec.family, spec.level)
            for spec in SCOPE_PAIR_FEATURES} == {
        ("borrowed_session_breadth", Tier.V1, ContextLevel.C0, "higher", SCOPE, "pair"),
        ("out_of_scope_reads_borrowed", Tier.V1, ContextLevel.C2, "higher", SCOPE, "pair"),
        ("out_of_scope_reads_own", Tier.V1, ContextLevel.C2, "higher", SCOPE, "pair"),
    }
    assert [(spec.name, spec.tier, spec.context, spec.family) for spec in SCOPE_RUN_FEATURES] == [
        (f"{spec.name}_{suffix}", spec.tier, spec.context, SCOPE)
        for spec in SCOPE_PAIR_FEATURES for suffix in ("max", "top_k_mean", "n_above")
    ]
    assert all(spec.description for spec in SCOPE_PAIR_FEATURES + SCOPE_RUN_FEATURES)
    assert SCOPE_THRESHOLDS == {"borrowed_session_breadth": 4.0,
                                "out_of_scope_reads_borrowed": 0.0,
                                "out_of_scope_reads_own": 0.0}
    assert not set(SCOPE_THRESHOLDS) & set(THRESHOLDS)
    assert all(spec.context is ContextLevel.C0 for spec in PAIR_FEATURES + RUN_FEATURES)
    assert all(spec.family != SCOPE for spec in PAIR_FEATURES + RUN_FEATURES)
    assert FeatureSpec("x", "pair", Tier.V0, "d").context is ContextLevel.C0


@pytest.mark.parametrize("level", ["agent", "pair", "run"])
@pytest.mark.parametrize("tier", list(Tier))
def test_feature_columns_without_context_are_unchanged(level: str, tier: Tier) -> None:
    for families in (None, FAMILIES, ("generic",), ("aggregation",)):
        assert feature_columns(level, tier, families, context=None) == \
            feature_columns(level, tier, families)
    with pytest.raises(ValueError):
        feature_columns(level, tier, (SCOPE,))
    with pytest.raises(ValueError):
        feature_columns(level, tier, ("aggregation", SCOPE), context=None)


def test_feature_columns_with_context() -> None:
    base = feature_columns("pair", Tier.V1)
    assert feature_columns("pair", Tier.V1, context=ContextLevel.C0) == (
        *base, "borrowed_session_breadth")
    assert feature_columns("pair", Tier.V1, context=ContextLevel.C1) == (
        *base, "borrowed_session_breadth")
    assert feature_columns("pair", Tier.V2, context=ContextLevel.C2) == (
        *feature_columns("pair", Tier.V2), *SCOPE_NAMES)
    assert feature_columns("pair", Tier.V1, (SCOPE,), context=ContextLevel.C2) == SCOPE_NAMES
    assert feature_columns("pair", Tier.V1, ("aggregation",), context=ContextLevel.C2) == \
        feature_columns("pair", Tier.V1, ("aggregation",))
    assert feature_columns("run", Tier.V1, (SCOPE,), context=ContextLevel.C1) == (
        "borrowed_session_breadth_max", "borrowed_session_breadth_top_k_mean",
        "borrowed_session_breadth_n_above")
    assert len(feature_columns("run", Tier.V1, (SCOPE,), context=ContextLevel.C2)) == 9
    for level in LEVELS:
        assert feature_columns("agent", Tier.V2, context=level) == feature_columns("agent", Tier.V2)
        with pytest.raises(ValueError):
            feature_columns("pair", Tier.V1, ("unknown",), context=level)
    with pytest.raises(ValueError):
        feature_columns("pair", Tier.V1, context="C2")  # type: ignore[arg-type]


@pytest.mark.parametrize("level", LEVELS)
def test_no_scope_column_at_v0(level: ContextLevel) -> None:
    for name in ("pair", "run"):
        columns = feature_columns(name, Tier.V0, context=level)
        assert columns == feature_columns(name, Tier.V0)
        assert feature_columns(name, Tier.V0, (SCOPE,), context=level) == ()
    trace = make_trace(FIXTURE_A, Tier.V0)
    ctx = context(level, HANDOFF_A)
    pd.testing.assert_frame_equal(pair_features(trace, context=ctx), pair_features(trace))
    pd.testing.assert_frame_equal(run_features(trace, context=ctx), run_features(trace))


def test_fixture_a_borrowed_session() -> None:
    trace = make_trace(FIXTURE_A)
    for level in (ContextLevel.C0, ContextLevel.C1):
        row = scope_row(trace, level, HANDOFF_A)
        assert row["borrowed_session_breadth"] == 3
        assert "out_of_scope_reads_borrowed" not in row.index
    row = scope_row(trace, ContextLevel.C2, HANDOFF_A)
    assert row["borrowed_session_breadth"] == 3
    assert row["out_of_scope_reads_borrowed"] == 1
    assert row["out_of_scope_reads_own"] == 0
    frame = pair_features(trace, context=context(ContextLevel.C2, HANDOFF_A))
    for pair in ((A, C), (B, C)):
        assert list(frame.loc[pair, list(SCOPE_NAMES)]) == [0, 0, 0]
    assert all(frame[name].dtype == "int64" for name in SCOPE_NAMES)


def test_fixture_b_delegation_under_own_credential() -> None:
    trace = make_trace(FIXTURE_B)
    for level in LEVELS:
        assert scope_row(trace, level, HANDOFF_B)["borrowed_session_breadth"] == 0
    row = scope_row(trace, ContextLevel.C2, HANDOFF_B)
    assert row["out_of_scope_reads_own"] == 1
    assert row["out_of_scope_reads_borrowed"] == 0


def test_fixture_c_owner_never_logs_in() -> None:
    # C1 adds nothing over C0 only while the owner is the first to use its credential.
    trace = make_trace(FIXTURE_C)
    assert scope_row(trace, ContextLevel.C0)["borrowed_session_breadth"] == 0
    assert scope_row(trace, ContextLevel.C1)["borrowed_session_breadth"] == 3
    assert scope_row(trace, ContextLevel.C2)["borrowed_session_breadth"] == 3


def test_context_level_gates_what_is_used() -> None:
    trace = make_trace(FIXTURE_C)
    populated_c0 = Context(RUN_ID, ContextLevel.C0, dict(DIRECTORY), HANDOFF_A)
    pd.testing.assert_frame_equal(pair_features(trace, context=populated_c0),
                                  pair_features(trace, context=Context.empty(RUN_ID)))
    trace = make_trace(FIXTURE_A)
    populated_c1 = Context(RUN_ID, ContextLevel.C1, dict(DIRECTORY), HANDOFF_A)
    frame = pair_features(trace, context=populated_c1)
    assert tuple(frame.columns) == feature_columns("pair", Tier.V1, context=ContextLevel.C1)
    pd.testing.assert_frame_equal(frame, pair_features(trace, context=context(ContextLevel.C1)))


def test_credential_missing_from_directory_is_not_borrowed() -> None:
    trace = make_trace(FIXTURE_A)
    ctx = context(ContextLevel.C2, HANDOFF_A, credentials={CB: B})
    row = pair_features(trace, context=ctx).loc[(A, B)]
    assert row["borrowed_session_breadth"] == 0
    assert row["out_of_scope_reads_borrowed"] == 0
    assert row["out_of_scope_reads_own"] == 0


def test_handoff_features_require_matching_host_and_sender() -> None:
    trace = make_trace(FIXTURE_A)
    for handoff in (HandoffScope(A, B, "h-0000000c", (F1,)), HandoffScope(C, B, HA, (F1,)),
                    HandoffScope(B, A, HA, (F1,))):
        row = pair_features(trace, context=context(ContextLevel.C2, (handoff,))).loc[
            tuple(sorted((handoff.sender, handoff.receiver)))]
        assert row["out_of_scope_reads_borrowed"] == 0
        assert row["out_of_scope_reads_own"] == 0
    # Hand-offs of the pair are summed; the second one has an empty scope.
    twice = (*HANDOFF_A, HandoffScope(A, B, HA, ()))
    assert scope_row(trace, ContextLevel.C2, twice)["out_of_scope_reads_borrowed"] == 4
    # Own and borrowed both apply when the first login is own and a later one borrowed.
    rows = [(0, A, "login", HA, "ok", CA), (1, B, "login", HA, "ok", CB),
            (2, B, "read", F1, "ok"), (3, B, "login", HA, "ok", CA), (4, B, "read", F2, "ok")]
    row = scope_row(make_trace(rows), ContextLevel.C2, (HandoffScope(A, B, HA, ()),))
    assert (row["out_of_scope_reads_own"], row["out_of_scope_reads_borrowed"]) == (2, 1)
    assert row["borrowed_session_breadth"] == 1


def test_exclusions_and_prefixes() -> None:
    trace = make_trace(FIXTURE_EXCLUSIONS)
    expected = {1: (0, 0), 2: (0, 0), 3: (0, 0), 4: (1, 0), 5: (1, 0), 6: (2, 1), 7: (3, 2)}
    for tick, (breadth, outside) in expected.items():
        row = scope_row(trace, ContextLevel.C2, HANDOFF_EXCLUSIONS, until_tick=tick)
        assert (row["borrowed_session_breadth"], row["out_of_scope_reads_borrowed"]) == (
            breadth, outside), tick
    ctx = context(ContextLevel.C2, HANDOFF_EXCLUSIONS)
    full_pairs, full_runs = pair_features(trace, context=ctx), run_features(trace, context=ctx)
    assert full_pairs.loc[(A, B), "borrowed_session_breadth"] == 3
    pd.testing.assert_frame_equal(pair_features(trace, until_tick=7, context=ctx), full_pairs)
    pd.testing.assert_frame_equal(run_features(trace, until_tick=7, context=ctx), full_runs)
    for tick in range(-1, 9):
        cut = Trace(RUN_ID, trace.tier, tuple(e for e in trace.events if e.tick <= tick))
        for function in (pair_features, run_features):
            pd.testing.assert_frame_equal(function(trace, until_tick=tick, context=ctx),
                                          function(cut, until_tick=tick, context=ctx))


def test_run_features_aggregate_scope_columns() -> None:
    trace = make_trace(FIXTURE_A)
    ctx = context(ContextLevel.C2, HANDOFF_A)
    frame = run_features(trace, context=ctx)
    assert tuple(frame.columns) == feature_columns("run", Tier.V1, context=ContextLevel.C2)
    row = frame.iloc[0]
    assert row["borrowed_session_breadth_max"] == 3.0
    assert row["borrowed_session_breadth_top_k_mean"] == 1.0
    assert row["borrowed_session_breadth_n_above"] == 0
    assert row["out_of_scope_reads_borrowed_max"] == 1.0
    assert row["out_of_scope_reads_borrowed_n_above"] == 1
    assert row["out_of_scope_reads_own_n_above"] == 0
    assert frame["borrowed_session_breadth_n_above"].dtype == "int64"
    assert frame["borrowed_session_breadth_max"].dtype == "float64"
    lowered = run_features(trace, context=ctx, thresholds={"borrowed_session_breadth": 2.0})
    assert lowered.iloc[0]["borrowed_session_breadth_n_above"] == 1
    assert run_features(trace, context=ctx, top_k=1).iloc[0][
        "borrowed_session_breadth_top_k_mean"] == 3.0
    pd.testing.assert_frame_equal(frame[list(run_features(trace).columns)], run_features(trace))
    empty = run_features(make_trace([(0, A, "scan", HA, "ok")]), context=ctx).iloc[0]
    assert math.isnan(empty["borrowed_session_breadth_max"])
    assert empty["out_of_scope_reads_own_n_above"] == 0


def test_run_id_mismatch_raises() -> None:
    for tier in (Tier.V0, Tier.V1):
        trace = make_trace(FIXTURE_A, tier)
        for bad in (Context.empty(""), context(ContextLevel.C2, run_id="fedcba9876543210")):
            for function in (pair_features, run_features):
                with pytest.raises(ValueError, match="run_id"):
                    function(trace, context=bad)


@pytest.mark.parametrize("tier", list(Tier))
@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_context_none_matches_default_and_scope_columns_are_appended(
    fixtures_dir: Path, name: str, tier: Tier,
) -> None:
    trace = read_trace(fixtures_dir / name / "trace.jsonl", tier)
    pairs, runs = pair_features(trace), run_features(trace)
    rank = {Tier.V0: 0, Tier.V1: 1, Tier.V2: 2}
    assert tuple(pairs.columns) == tuple(
        spec.name for spec in PAIR_FEATURES if rank[spec.tier] <= rank[tier])
    assert tuple(runs.columns) == tuple(
        spec.name for spec in RUN_FEATURES if rank[spec.tier] <= rank[tier])
    pd.testing.assert_frame_equal(pair_features(trace, context=None), pairs, check_exact=True)
    pd.testing.assert_frame_equal(run_features(trace, context=None), runs, check_exact=True)
    for level in LEVELS:
        ctx = Context.empty(trace.run_id) if level is ContextLevel.C0 else Context(
            trace.run_id, level, {}, ())
        scoped = pair_features(trace, context=ctx)
        assert tuple(scoped.columns) == feature_columns("pair", tier, context=level)
        pd.testing.assert_frame_equal(scoped[list(pairs.columns)], pairs, check_exact=True)
        scoped_runs = run_features(trace, context=ctx)
        pd.testing.assert_frame_equal(scoped_runs[list(runs.columns)], runs, check_exact=True)


def test_credential_relay_fixture_borrows_but_reads_nothing_after(fixtures_dir: Path) -> None:
    # Borrowed logins without later reads give breadth 0, not the login count.
    trace = read_trace(fixtures_dir / "credential_relay" / "trace.jsonl", Tier.V1)
    frame = pair_features(trace, context=Context.empty(trace.run_id))
    assert frame["shared_credential_logins"].max() > 0
    assert frame["borrowed_session_breadth"].max() == 0


@pytest.fixture(scope="module")
def recorded_main() -> dict[Tier, pd.DataFrame]:
    return {tier: load_recorded(DATA / "dataset" / "main", tier).runs for tier in Tier}


def test_committed_raw_samples_match_recorded_rows_without_context(
    tmp_path: Path, recorded_main: dict[Tier, pd.DataFrame],
) -> None:
    samples = sorted(path for path in (DATA / "raw" / "main").iterdir() if path.is_dir())
    assert samples
    for sample in samples:
        path = tmp_path / f"{sample.name}.jsonl"
        path.write_bytes(gzip.decompress((sample / "trace.jsonl.gz").read_bytes()))
        for tier in Tier:
            actual = run_features(read_trace(path, tier), context=None)
            pd.testing.assert_frame_equal(actual, recorded_main[tier].loc[[sample.name]],
                                          check_exact=True, obj=f"{sample.name}/{tier.value}")


def _renamed_id(agent: str) -> str:
    return f"a-{0xFFFFFFFF - int(agent[2:], 16):08x}"


def _rename_trace(trace: Trace) -> Trace:
    return Trace(trace.run_id, trace.tier, tuple(
        replace(event, agent=_renamed_id(event.agent),
                target=_renamed_id(event.target) if event.tool in ("send", "recv")
                else event.target)
        for event in trace.events
    ))


def _rename_context(ctx: Context) -> Context:
    return replace(
        ctx, credentials={key: _renamed_id(value) for key, value in ctx.credentials.items()},
        handoffs=tuple(replace(handoff, sender=_renamed_id(handoff.sender),
                               receiver=_renamed_id(handoff.receiver))
                       for handoff in ctx.handoffs),
    )


def _assert_renaming_invariant(trace: Trace, ctx: Context) -> None:
    renamed, renamed_ctx = _rename_trace(trace), _rename_context(ctx)
    pairs = pair_features(trace, context=ctx)
    pairs.index = pd.MultiIndex.from_tuples(
        [tuple(sorted(map(_renamed_id, pair))) for pair in pairs.index],
        names=["agent_a", "agent_b"],
    )
    pd.testing.assert_frame_equal(pairs.sort_index(),
                                  pair_features(renamed, context=renamed_ctx))
    pd.testing.assert_frame_equal(run_features(trace, context=ctx),
                                  run_features(renamed, context=renamed_ctx))


@pytest.fixture(scope="module")
def violation_runs(tmp_path_factory: pytest.TempPathFactory) -> dict[str, object]:
    root = tmp_path_factory.mktemp("scope_runs")
    condition = Condition("shared_file", "hub", 5, 2, scope="on", violation_size=5)
    seed = 20261121
    setup = build_run(condition, seed)
    assert setup.violation is not None
    return {
        "collector": setup.violation.worker,
        "violation": run_one(condition, seed, root / "violation"),
        "in_scope": run_one(replace(condition, violation_size=0), seed, root / "in_scope"),
    }


def _load(run_dir: Path, tier: Tier, level: ContextLevel) -> tuple[Trace, Context]:
    return read_trace(run_dir / "trace.jsonl", tier), read_context(run_dir / "context.json",
                                                                   level)


@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize("tier", list(Tier))
def test_invariant_to_agent_renaming(
    violation_runs: dict[str, object], tier: Tier, level: ContextLevel,
) -> None:
    # Hand-built reads carry no content, so they are valid at V0 and V1 only.
    for rows, handoffs in ((FIXTURE_A, HANDOFF_A), (FIXTURE_B, HANDOFF_B), (FIXTURE_C, ()),
                           (FIXTURE_EXCLUSIONS, HANDOFF_EXCLUSIONS)):
        if tier is not Tier.V2:
            _assert_renaming_invariant(make_trace(rows, tier), context(level, handoffs))
    trace, ctx = _load(violation_runs["violation"], tier, level)  # type: ignore[arg-type]
    _assert_renaming_invariant(trace, ctx)
    if tier is not Tier.V0:
        frame = pair_features(trace, context=ctx)
        assert frame["borrowed_session_breadth"].max() > 0
        if level is ContextLevel.C2:
            assert frame["out_of_scope_reads_borrowed"].max() > 0


def test_simulated_violation_adds_exactly_its_out_of_scope_reads(
    violation_runs: dict[str, object],
) -> None:
    collector = violation_runs["collector"]
    values = {}
    for kind in ("violation", "in_scope"):
        run_dir = violation_runs[kind]
        trace, ctx = _load(run_dir, Tier.V1, ContextLevel.C2)  # type: ignore[arg-type]
        lender = next(handoff.sender for handoff in ctx.handoffs
                      if handoff.receiver == collector)
        outcomes = json.loads((run_dir / "outcomes.json").read_text(  # type: ignore[operator]
            encoding="utf-8"))
        if kind == "in_scope":
            assert outcomes["violation"] is None
        else:
            assert outcomes["violation"]["worker"] == collector
            assert len(outcomes["violation"]["read"]) == 5
        values[kind] = int(pair_features(trace, context=ctx).loc[
            tuple(sorted((collector, lender))), "out_of_scope_reads_borrowed"])
    assert values["violation"] >= 5
    assert values["violation"] - values["in_scope"] == 5


def test_scope_features_have_no_agent_level_effect(fixtures_dir: Path) -> None:
    trace = read_trace(fixtures_dir / "credential_relay" / "trace.jsonl", Tier.V1)
    assert tuple(agent_features(trace).columns) == feature_columns(
        "agent", Tier.V1, context=ContextLevel.C2)
