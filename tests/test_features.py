import ast
import inspect
import math
import subprocess
import sys
import typing
from dataclasses import replace
from pathlib import Path

import pandas as pd
import pytest

import swarmtrace.features as features
from swarmtrace.features import (
    THRESHOLDS,
    agent_features,
    feature_columns,
    pair_features,
    run_features,
)
from swarmtrace.features.spec import (
    AGENT_FEATURES,
    PAIR_FEATURES,
    RUN_FEATURES,
    SCOPE_PAIR_FEATURES,
    SCOPE_RUN_FEATURES,
)
from swarmtrace.trace.io import Labels, Manifest, Trace, read_trace
from swarmtrace.trace.schema import TOOLS, TraceEvent, validate_trace
from swarmtrace.trace.tiers import Tier

FIXTURE_NAMES = ("all_benign", "messaging_pair", "shared_file_trio", "benign_team", "denials")
FUNCTIONS = (agent_features, pair_features, run_features)
BLOCKED = ("swarmtrace.sim", "swarmtrace.world", "swarmtrace.agents", "swarmtrace.objectives")


def load(fixtures_dir: Path, name: str, tier: Tier = Tier.V2) -> Trace:
    return read_trace(fixtures_dir / name / "trace.jsonl", tier=tier)


def make_trace(rows: list[tuple[int, str, str, str, str]]) -> Trace:
    events = tuple(
        TraceEvent(
            schema_version=1, run_id="0123456789abcdef", seq=seq, tick=tick, agent=agent,
            tool=tool, target=target, args={}, result={"status": status, "size": 0},
            content=None, provenance=None,
        )
        for seq, (tick, agent, tool, target, status) in enumerate(rows)
    )
    validate_trace(events, tier=Tier.V0)
    return Trace("0123456789abcdef", Tier.V0, events)


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


def prefix(trace: Trace, tick: int) -> Trace:
    return Trace(trace.run_id, trace.tier, tuple(e for e in trace.events if e.tick <= tick))


A, B, C = "a-00000001", "a-00000002", "a-00000003"


def test_pinned_feature_tiers_and_families() -> None:
    expected = {
        "n_events": ("V0", "generic"),
        "tool_frac_scan": ("V0", "generic"),
        "tool_frac_login": ("V0", "generic"),
        "tool_frac_list": ("V0", "generic"),
        "tool_frac_read": ("V0", "generic"),
        "tool_frac_write": ("V0", "generic"),
        "tool_frac_send": ("V0", "generic"),
        "tool_frac_recv": ("V0", "generic"),
        "n_distinct_targets": ("V0", "generic"),
        "denial_rate": ("V0", "generic"),
        "xcorr_lag0": ("V0", "generic"),
        "xcorr_lag1": ("V0", "generic"),
        "xcorr_lag2": ("V0", "generic"),
        "handoff_latency_mean": ("V0", "generic"),
        "target_overlap": ("V0", "generic"),
        "target_complementarity": ("V0", "generic"),
        "direct_messages": ("V0", "generic"),
        "read_after_write": ("V0", "generic"),
        "provenance_links": ("V2", "generic"),
        "access_expansion_after_receipt": ("V0", "aggregation"),
        "shared_credential_logins": ("V1", "aggregation"),
        "xcorr_lag0_max": ("V0", "generic"),
        "xcorr_lag0_top_k_mean": ("V0", "generic"),
        "xcorr_lag0_n_above": ("V0", "generic"),
        "xcorr_lag1_max": ("V0", "generic"),
        "xcorr_lag1_top_k_mean": ("V0", "generic"),
        "xcorr_lag1_n_above": ("V0", "generic"),
        "xcorr_lag2_max": ("V0", "generic"),
        "xcorr_lag2_top_k_mean": ("V0", "generic"),
        "xcorr_lag2_n_above": ("V0", "generic"),
        "handoff_latency_mean_min": ("V0", "generic"),
        "handoff_latency_mean_bottom_k_mean": ("V0", "generic"),
        "handoff_latency_mean_n_at_or_below": ("V0", "generic"),
        "target_overlap_max": ("V0", "generic"),
        "target_overlap_top_k_mean": ("V0", "generic"),
        "target_overlap_n_above": ("V0", "generic"),
        "target_complementarity_max": ("V0", "generic"),
        "target_complementarity_top_k_mean": ("V0", "generic"),
        "target_complementarity_n_above": ("V0", "generic"),
        "direct_messages_max": ("V0", "generic"),
        "direct_messages_top_k_mean": ("V0", "generic"),
        "direct_messages_n_above": ("V0", "generic"),
        "read_after_write_max": ("V0", "generic"),
        "read_after_write_top_k_mean": ("V0", "generic"),
        "read_after_write_n_above": ("V0", "generic"),
        "provenance_links_max": ("V2", "generic"),
        "provenance_links_top_k_mean": ("V2", "generic"),
        "provenance_links_n_above": ("V2", "generic"),
        "access_expansion_after_receipt_max": ("V0", "aggregation"),
        "access_expansion_after_receipt_top_k_mean": ("V0", "aggregation"),
        "access_expansion_after_receipt_n_above": ("V0", "aggregation"),
        "shared_credential_logins_max": ("V1", "aggregation"),
        "shared_credential_logins_top_k_mean": ("V1", "aggregation"),
        "shared_credential_logins_n_above": ("V1", "aggregation"),
        "borrowed_session_breadth": ("V1", "scope"),
        "out_of_scope_reads_borrowed": ("V1", "scope"),
        "out_of_scope_reads_own": ("V1", "scope"),
        "borrowed_session_breadth_max": ("V1", "scope"),
        "borrowed_session_breadth_top_k_mean": ("V1", "scope"),
        "borrowed_session_breadth_n_above": ("V1", "scope"),
        "out_of_scope_reads_borrowed_max": ("V1", "scope"),
        "out_of_scope_reads_borrowed_top_k_mean": ("V1", "scope"),
        "out_of_scope_reads_borrowed_n_above": ("V1", "scope"),
        "out_of_scope_reads_own_max": ("V1", "scope"),
        "out_of_scope_reads_own_top_k_mean": ("V1", "scope"),
        "out_of_scope_reads_own_n_above": ("V1", "scope"),
    }
    declared = (
        AGENT_FEATURES + PAIR_FEATURES + RUN_FEATURES + SCOPE_PAIR_FEATURES + SCOPE_RUN_FEATURES
    )
    assert set(expected) == {spec.name for spec in declared}
    assert len(expected) == len(declared), "Feature names must be unique across levels and families"
    assert {spec.name: (spec.tier.name, spec.family) for spec in declared} == expected


def test_registry_names_and_tiers() -> None:
    assert [spec.name for spec in AGENT_FEATURES] == (
        ["n_events"] + [f"tool_frac_{tool}" for tool in TOOLS]
        + ["n_distinct_targets", "denial_rate"]
    )
    assert [spec.name for spec in PAIR_FEATURES] == [
        "xcorr_lag0", "xcorr_lag1", "xcorr_lag2", "handoff_latency_mean", "target_overlap",
        "target_complementarity", "direct_messages", "read_after_write", "provenance_links",
        "access_expansion_after_receipt", "shared_credential_logins",
    ]
    assert {spec.name: spec.direction for spec in PAIR_FEATURES} == {
        spec.name: "lower" if spec.name == "handoff_latency_mean" else "higher"
        for spec in PAIR_FEATURES
    }
    suffixes = {"higher": ("max", "top_k_mean", "n_above"),
                "lower": ("min", "bottom_k_mean", "n_at_or_below")}
    assert [spec.name for spec in RUN_FEATURES] == [
        f"{spec.name}_{suffix}" for spec in PAIR_FEATURES
        for suffix in suffixes[spec.direction]
    ]
    assert {spec.name: spec.direction for spec in RUN_FEATURES} == {
        f"{spec.name}_{suffix}": spec.direction for spec in PAIR_FEATURES
        for suffix in suffixes[spec.direction]
    }
    assert {spec.direction for spec in AGENT_FEATURES} == {None}
    tiers = {spec.name: spec.tier for spec in AGENT_FEATURES + PAIR_FEATURES + RUN_FEATURES}
    v2 = {"provenance_links", "provenance_links_max", "provenance_links_top_k_mean",
          "provenance_links_n_above"}
    assert {name for name, tier in tiers.items() if tier is Tier.V2} == v2
    v1 = {"shared_credential_logins", "shared_credential_logins_max",
          "shared_credential_logins_top_k_mean", "shared_credential_logins_n_above"}
    assert {name for name, tier in tiers.items() if tier is Tier.V1} == v1
    for spec in AGENT_FEATURES + PAIR_FEATURES + RUN_FEATURES:
        assert spec.description
    assert set(THRESHOLDS) == {spec.name for spec in PAIR_FEATURES}


@pytest.mark.parametrize("tier", list(Tier))
@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_columns_follow_tier(fixtures_dir: Path, name: str, tier: Tier) -> None:
    trace = load(fixtures_dir, name, tier)
    full = load(fixtures_dir, name, Tier.V2)
    for function, level in zip(FUNCTIONS, ("agent", "pair", "run")):
        frame = function(trace)
        assert tuple(frame.columns) == feature_columns(level, tier)
        expected = function(full)[list(frame.columns)]
        pd.testing.assert_frame_equal(frame, expected)
    assert ("provenance_links" in pair_features(trace).columns) == (tier is Tier.V2)


def test_agent_features_all_benign(fixtures_dir: Path) -> None:
    frame = agent_features(load(fixtures_dir, "all_benign"))
    assert list(frame.index) == ["a-4b7d03f1", "a-6d90b7e3", "a-9e2a14c8", "a-c18f6a29"]
    assert frame.index.name == "agent"
    assert frame["n_events"].tolist() == [5, 5, 5, 5]
    assert frame["n_distinct_targets"].tolist() == [2, 2, 2, 2]
    assert frame["denial_rate"].tolist() == [0.0, 0.0, 0.0, 0.0]
    assert frame.loc["a-9e2a14c8", [f"tool_frac_{t}" for t in TOOLS]].tolist() == [
        0.2, 0.2, 0.2, 0.2, 0.2, 0.0, 0.0,
    ]
    assert frame.loc["a-c18f6a29", [f"tool_frac_{t}" for t in TOOLS]].tolist() == [
        0.2, 0.0, 0.2, 0.4, 0.2, 0.0, 0.0,
    ]


def test_agent_features_denials(fixtures_dir: Path) -> None:
    frame = agent_features(load(fixtures_dir, "denials", Tier.V0))
    assert frame.loc["a-2d6b9e01", "denial_rate"] == 0.5
    assert frame.loc["a-a8c315f7", "denial_rate"] == 0.0
    assert frame["n_events"].tolist() == [4, 4]
    assert frame["n_distinct_targets"].tolist() == [3, 3]
    assert frame.loc["a-2d6b9e01", [f"tool_frac_{t}" for t in TOOLS]].tolist() == [
        0.25, 0.25, 0.0, 0.0, 0.25, 0.0, 0.25,
    ]


def test_pair_features_messaging_pair(fixtures_dir: Path) -> None:
    frame = pair_features(load(fixtures_dir, "messaging_pair"))
    assert frame.index.names == ["agent_a", "agent_b"]
    assert len(frame) == 10
    row = frame.loc[("a-3f96c2a1", "a-b024e76d")]
    assert row["xcorr_lag0"] == pytest.approx(-1 / 3)
    assert row["xcorr_lag1"] == pytest.approx(1 / 6)
    assert row["xcorr_lag2"] == pytest.approx(1.0)
    assert row["handoff_latency_mean"] == 1.0
    assert row["target_overlap"] == 1.0
    assert row["target_complementarity"] == 0
    assert row["direct_messages"] == 2
    assert row["read_after_write"] == 0
    assert row["provenance_links"] == 3
    others = frame.drop(index=("a-3f96c2a1", "a-b024e76d"))
    assert (others["direct_messages"] == 0).all()
    assert (others["provenance_links"] == 0).all()
    assert others["handoff_latency_mean"].isna().all()


def test_pair_features_constant_series_is_undefined(fixtures_dir: Path) -> None:
    trace = make_trace([(0, A, "scan", "h-00000001", "ok"), (1, A, "scan", "h-00000001", "ok"),
                        (1, B, "scan", "h-00000001", "ok")])
    row = pair_features(trace).loc[(A, B)]
    assert math.isnan(row["xcorr_lag0"])
    assert math.isnan(row["xcorr_lag1"])
    assert math.isnan(row["xcorr_lag2"])


def test_pair_features_shared_file_trio(fixtures_dir: Path) -> None:
    frame = pair_features(load(fixtures_dir, "shared_file_trio"))
    expected = {
        ("a-27f90c5e", "a-8b14d6a2"): (2 / 3, 1, 2),
        ("a-27f90c5e", "a-e6a352b8"): (1.0, 1, 2),
        ("a-8b14d6a2", "a-e6a352b8"): (2 / 3, 1, 1),
    }
    for pair, (overlap, raw, links) in expected.items():
        row = frame.loc[pair]
        assert row["target_overlap"] == pytest.approx(overlap)
        assert row["read_after_write"] == raw
        assert row["provenance_links"] == links
        assert row["handoff_latency_mean"] == 1.0
        assert row["direct_messages"] == 0
    others = frame.drop(index=list(expected))
    assert (others["read_after_write"] == 0).all()
    assert (others["target_overlap"] == 0).all()
    assert others["handoff_latency_mean"].isna().all()


def test_pair_features_benign_team(fixtures_dir: Path) -> None:
    row = pair_features(load(fixtures_dir, "benign_team")).loc[("a-6e41b0d7", "a-c89d235a")]
    assert row["direct_messages"] == 2
    assert row["handoff_latency_mean"] == 1.0
    assert row["provenance_links"] == 3
    assert row["read_after_write"] == 0


def test_handoff_latency_matches_messages_in_order() -> None:
    trace = make_trace([
        (0, A, "send", B, "ok"), (1, A, "send", B, "ok"), (2, A, "send", B, "denied"),
        (3, B, "recv", A, "ok"), (5, B, "recv", A, "ok"),
        (6, B, "write", "f-00000001", "ok"), (8, A, "read", "f-00000001", "ok"),
    ])
    row = pair_features(trace).loc[(A, B)]
    assert row["handoff_latency_mean"] == pytest.approx((3 + 4 + 2) / 3)
    assert row["direct_messages"] == 2
    assert row["read_after_write"] == 1


def test_target_complementarity() -> None:
    trace = make_trace([
        (0, A, "scan", "h-00000001", "ok"), (0, A, "read", "f-00000001", "ok"),
        (1, A, "read", "f-00000002", "denied"), (1, B, "scan", "h-00000001", "ok"),
        (2, B, "write", "f-00000003", "ok"), (3, C, "read", "f-00000001", "ok"),
        (4, B, "send", C, "ok"),
    ])
    frame = pair_features(trace)
    assert frame.loc[(A, B), "target_complementarity"] == 1
    assert frame.loc[(A, C), "target_complementarity"] == 0
    assert frame.loc[(B, C), "target_complementarity"] == 1
    assert frame.loc[(A, B), "target_overlap"] == 0.25
    assert frame.loc[(A, C), "target_overlap"] == pytest.approx(1 / 3)


def test_target_complementarity_fixtures(fixtures_dir: Path) -> None:
    benign = pair_features(load(fixtures_dir, "all_benign"))
    assert benign["target_complementarity"].tolist() == [2] * 6
    trio = pair_features(load(fixtures_dir, "shared_file_trio"))
    team = [("a-27f90c5e", "a-8b14d6a2"), ("a-27f90c5e", "a-e6a352b8"),
            ("a-8b14d6a2", "a-e6a352b8")]
    assert trio.loc[team, "target_complementarity"].tolist() == [0, 0, 0]
    assert trio.drop(index=team)["target_complementarity"].tolist() == [1] * 7


def test_run_features_shared_file_trio(fixtures_dir: Path) -> None:
    frame = run_features(load(fixtures_dir, "shared_file_trio"))
    assert list(frame.index) == ["74c93be216f8a05d"]
    assert frame.index.name == "run_id"
    row = frame.iloc[0]
    assert row["read_after_write_max"] == 1.0
    assert row["read_after_write_top_k_mean"] == 1.0
    assert row["read_after_write_n_above"] == 3
    assert row["provenance_links_max"] == 2.0
    assert row["provenance_links_top_k_mean"] == pytest.approx(5 / 3)
    assert row["provenance_links_n_above"] == 3
    assert row["target_overlap_max"] == 1.0
    assert row["target_overlap_top_k_mean"] == pytest.approx(7 / 9)
    assert row["target_overlap_n_above"] == 3
    assert row["handoff_latency_mean_min"] == 1.0
    assert row["handoff_latency_mean_bottom_k_mean"] == 1.0
    assert row["handoff_latency_mean_n_at_or_below"] == 3
    assert "handoff_latency_mean_max" not in frame.columns
    assert row["direct_messages_max"] == 0.0
    assert row["target_complementarity_max"] == 1.0
    assert row["target_complementarity_top_k_mean"] == 1.0
    assert row["target_complementarity_n_above"] == 0
    assert row["direct_messages_n_above"] == 0


def test_run_features_parameters(fixtures_dir: Path) -> None:
    trace = load(fixtures_dir, "shared_file_trio")
    row = run_features(trace, top_k=1, thresholds={"provenance_links": 1}).iloc[0]
    assert row["provenance_links_top_k_mean"] == 2.0
    assert row["provenance_links_n_above"] == 2
    assert row["read_after_write_n_above"] == 3


def test_latency_aggregates_point_at_short_handoffs() -> None:
    D = "a-00000004"
    trace = make_trace([
        (0, A, "send", B, "ok"), (0, A, "send", C, "ok"), (0, A, "write", "f-00000001", "ok"),
        (1, B, "recv", A, "ok"), (3, C, "recv", A, "ok"), (5, D, "read", "f-00000001", "ok"),
    ])
    latency = pair_features(trace)["handoff_latency_mean"]
    assert latency.loc[[(A, B), (A, C), (A, D)]].tolist() == [1.0, 3.0, 5.0]
    assert latency.isna().sum() == 3
    row = run_features(trace).iloc[0]
    assert row["handoff_latency_mean_min"] == 1.0
    assert row["handoff_latency_mean_bottom_k_mean"] == 3.0
    assert row["handoff_latency_mean_n_at_or_below"] == 1
    row = run_features(trace, top_k=2, thresholds={"handoff_latency_mean": 3}).iloc[0]
    assert row["handoff_latency_mean_bottom_k_mean"] == 2.0
    assert row["handoff_latency_mean_n_at_or_below"] == 2


def test_latency_aggregates_without_handoffs(fixtures_dir: Path) -> None:
    row = run_features(load(fixtures_dir, "all_benign")).iloc[0]
    assert math.isnan(row["handoff_latency_mean_min"])
    assert math.isnan(row["handoff_latency_mean_bottom_k_mean"])
    assert row["handoff_latency_mean_n_at_or_below"] == 0


def test_run_features_without_pairs(fixtures_dir: Path) -> None:
    trace = make_trace([(0, A, "scan", "h-00000001", "ok")])
    row = run_features(trace).iloc[0]
    assert math.isnan(row["xcorr_lag0_max"])
    assert math.isnan(row["direct_messages_top_k_mean"])
    assert row["direct_messages_n_above"] == 0


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_prefix_at_final_tick_equals_full(fixtures_dir: Path, name: str) -> None:
    trace = load(fixtures_dir, name)
    last = trace.events[-1].tick
    for function in FUNCTIONS:
        pd.testing.assert_frame_equal(function(trace, until_tick=last), function(trace))


@pytest.mark.parametrize("tier", list(Tier))
@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_prefix_uses_no_later_events(fixtures_dir: Path, name: str, tier: Tier) -> None:
    trace = load(fixtures_dir, name, tier)
    for tick in range(-1, trace.events[-1].tick + 2):
        for function, level in zip(FUNCTIONS, ("agent", "pair", "run")):
            frame = function(trace, until_tick=tick)
            assert tuple(frame.columns) == feature_columns(level, tier)
            pd.testing.assert_frame_equal(frame, function(prefix(trace, tick), until_tick=tick))


def test_prefix_drops_inactive_agents(fixtures_dir: Path) -> None:
    trace = load(fixtures_dir, "all_benign")
    assert list(agent_features(trace, until_tick=0).index) == ["a-4b7d03f1", "a-9e2a14c8"]
    assert len(agent_features(trace, until_tick=-1)) == 0
    assert len(pair_features(trace, until_tick=-1)) == 0


@pytest.mark.parametrize("tier", list(Tier))
@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_invariant_to_agent_renaming(fixtures_dir: Path, name: str, tier: Tier) -> None:
    trace = load(fixtures_dir, name, tier)
    renamed = rename(trace)
    assert list(map(renamed_id, trace.agents)) == list(reversed(renamed.agents))
    original = agent_features(trace)
    original.index = original.index.map(renamed_id)
    pd.testing.assert_frame_equal(original.sort_index(), agent_features(renamed))
    pairs = pair_features(trace)
    pairs.index = pd.MultiIndex.from_tuples(
        [tuple(sorted(map(renamed_id, pair))) for pair in pairs.index],
        names=["agent_a", "agent_b"],
    )
    pd.testing.assert_frame_equal(pairs.sort_index(), pair_features(renamed))
    pd.testing.assert_frame_equal(run_features(trace), run_features(renamed))


def test_imports_without_simulation_packages(fixtures_dir: Path) -> None:
    script = f"""
import sys
blocked = {BLOCKED!r}
for name in blocked:
    sys.modules[name] = None
import swarmtrace.features as features
from swarmtrace.trace.io import read_trace
trace = read_trace({str(fixtures_dir / "shared_file_trio" / "trace.jsonl")!r})
features.agent_features(trace)
features.pair_features(trace)
features.run_features(trace)
assert all(sys.modules[name] is None for name in blocked)
"""
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_no_function_accepts_labels_or_manifest() -> None:
    functions = [
        member
        for module in [features, *map(sys.modules.get, sorted(
            name for name in sys.modules if name.startswith("swarmtrace.features.")
        ))]
        for _, member in inspect.getmembers(module, inspect.isfunction)
        if member.__module__.startswith("swarmtrace.features")
    ]
    assert {agent_features, pair_features, run_features, feature_columns} <= set(functions)

    def mentions(hint: object) -> bool:
        if hint in (Labels, Manifest):
            return True
        return any(mentions(argument) for argument in typing.get_args(hint))

    for function in functions:
        hints = typing.get_type_hints(function)
        if not function.__name__.startswith("_"):
            parameters = inspect.signature(function).parameters
            assert set(parameters) | {"return"} == set(hints), function.__name__
        assert not any(mentions(hint) for hint in hints.values()), function.__name__


def test_source_never_touches_label_side() -> None:
    package = Path(features.__file__).parent
    for path in package.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        for forbidden in ("labels.json", "manifest.json", "read_labels", "read_manifest",
                          "Labels", "Manifest", "RunPaths"):
            assert forbidden not in source, (path.name, forbidden)
        for node in ast.walk(ast.parse(source)):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            for name in names:
                assert not name.startswith(BLOCKED), (path.name, name)
                assert not name.lstrip(".").startswith(
                    ("sim", "world", "agents", "objectives")
                ), (path.name, name)
