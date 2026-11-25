import io
import json
from pathlib import Path

import pytest

from swarmtrace.reproduce import native_hooks as bench

ARCHIVE = Path(__file__).resolve().parents[1] / "benchmarks" / "native-hooks"


@pytest.fixture
def captures(monkeypatch):
    # Original test data. Reuse a synthetic session and child ID across independent scenarios.
    def claude(kind, **extra):
        return {"hook_event_name": kind, "session_id": "shared-test-parent", **extra}

    def grok(kind, **extra):
        session = extra.pop("session", "test-parent")
        return {"hookEventName": kind, "hook_event_name": kind, "sessionId": session, "session_id": session, **extra}

    def scenario(*records):
        return {"mode": "print", "description": "do-not-publish-description", "events": list(records)}

    cases = {
        "print_first": scenario(claude("UserPromptSubmit", prompt="do-not-publish-prompt"),
                                claude("SubagentStart", agent_id="test-child")),
        "print_next": scenario(claude("UserPromptSubmit"), claude("SubagentStop", agent_id="test-child")),
    }
    documents = {
        "claude": {"_provenance": "independent synthetic test", "claudeVersion": "2.1.284", "scenarios": cases},
        "grok": {"_provenance": "independent synthetic test",
                 "events": [grok("notification") for _ in range(15)]
                 + [grok("subagent_start", subagentId=k) for k in ("child-a", "child-b")]
                 + [grok("subagent_stop", subagentId=k, session=k) for k in ("child-b", "child-a")]},
    }
    monkeypatch.setattr(bench, "CLAUDE_SCENARIOS", {name: 2 for name in cases})
    raw = {k: json.dumps(v, indent=2).encode() for k, v in documents.items()}
    monkeypatch.setattr(bench, "ASSETS", {k: (f"{k}.json", len(b), bench.digest(b)) for k, b in raw.items()})
    return raw


def test_archived_results_agree_with_direct_counts_of_raw_public_records():
    assert json.loads((ARCHIVE / "protocol.json").read_bytes()) == bench.protocol()
    summary = json.loads((ARCHIVE / "summary.json").read_bytes())
    claude = summary["claude"]
    assert (claude["distinct_prompting_session_ids"], claude["selected_events"]) == (8, 169)
    assert set(claude["scenarios"]) == set(bench.CLAUDE_SCENARIOS)
    for name, count in bench.CLAUDE_SCENARIOS.items():
        case = claude["scenarios"][name]
        assert case["review"]["events"] == sum(case["source_event_counts"].values()) == count
    totals = claude["sum_of_scenario_review_counts"]
    children = totals["lifecycle"]
    assert (children["starts"], children["matched_stops"], children["orphan_stops"], children["open_at_end"]) == (16, 14, 13, 2)
    assert "distinct_children" not in children
    calls = totals["tools"]
    assert (calls["pre"], calls["post"], calls["child_paired_success"], calls["untagged_correlated_success"], calls["missing_result"]) == (35, 33, 21, 12, 2)
    timing = totals["latest_open"]
    assert (timing["correct"], timing["wrong"], timing["overlap_correct"], timing["overlap_wrong"]) == (16, 5, 5, 5)
    first, second = (summary["grok"]["captures"][date] for date in ("2026-09-01", "2026-09-02"))
    assert (first["review"]["other_events"], second["selected_events"]) == (15, 4)
    assert (second["review"]["matched_episodes"], second["review"]["naive_same_session_matches"]) == (2, 0)
    assert summary["independent_swarm_accuracy_rounds"] == summary["verified_coordination_intent_labels"] == 0
    assert summary["verified_policy_effect_labels"] == 0


def test_fetches_exact_bytes_and_replays_offline_with_distinct_boundaries(tmp_path, monkeypatch, captures):
    def fetch(url, *, timeout):
        assert timeout > 0
        provider = url.rsplit("/", 2)[1]
        assert url == f"{bench.BASE_URL}/{provider}/{provider}.json"
        return io.BytesIO(captures[provider])

    def offline(*unused, **kwargs):
        pytest.fail("a cached capture must not make a network request")

    monkeypatch.setattr(bench, "urlopen", fetch)
    source = tmp_path / "sources"
    out = tmp_path / "first"
    result = bench.run_native_hook_benchmark(source, out, fetch=True)
    for k, payload in captures.items():
        assert (source / f"{k}.json").read_bytes() == payload
    monkeypatch.setattr(bench, "urlopen", offline)
    later = tmp_path / "next"
    assert bench.run_native_hook_benchmark(source, later) == result
    assert bench.run_native_hook_benchmark(source, out, fetch=True) == result
    for name in ("protocol.json", "summary.json"):
        data = (out / name).read_bytes()
        assert data == (later / name).read_bytes()
        assert b"\r" not in data and b"do-not-publish" not in data and b"shared-test-parent" not in data
    life = result["claude"]["sum_of_scenario_review_counts"]["lifecycle"]
    assert (life["matched_stops"], life["orphan_stops"], life["open_at_end"]) == (0, 1, 1)
    assert result["grok"]["captures"]["2026-09-02"]["review"]["matched_episodes"] == 2


@pytest.mark.parametrize("transform", [lambda b: b.replace(b"\n", b"\r\n"), lambda b: b.replace(b"print", b"other")])
def test_original_bytes_must_match_even_when_file_remains_valid_json(tmp_path, captures, transform):
    wrong = transform(captures["claude"])
    assert isinstance(json.loads(wrong), dict)
    (tmp_path / "claude.json").write_bytes(wrong)
    with pytest.raises(ValueError, match="size or SHA-256"):
        bench.run_native_hook_benchmark(tmp_path, tmp_path / "out", fetch=True)
    assert (tmp_path / "claude.json").read_bytes() == wrong
    assert not (tmp_path / "out").exists()


def test_missing_and_invalid_download_leave_no_published_artifacts(tmp_path, monkeypatch, captures):
    def damaged(*args, **kwargs):
        return io.BytesIO(captures["claude"][:-1])

    monkeypatch.setattr(bench, "urlopen", damaged)
    with pytest.raises(ValueError, match="missing pinned claude"):
        bench.run_native_hook_benchmark(tmp_path, tmp_path / "out")
    with pytest.raises(ValueError, match="size or SHA-256"):
        bench.run_native_hook_benchmark(tmp_path, tmp_path / "out", fetch=True)
    assert not list(tmp_path.iterdir())


def test_requires_native_envelopes_and_capture_boundaries(captures):
    claude = json.loads(captures["claude"])
    del claude["scenarios"]["print_next"]["events"][0]["session_id"]
    with pytest.raises(ValueError, match="session identity"):
        bench._claude(claude)
    grok = json.loads(captures["grok"])
    grok["events"].reverse()
    with pytest.raises(ValueError, match="boundary"):
        bench._grok(grok)
    grok["events"][0]["session_id"] = "other-session"
    with pytest.raises(ValueError, match="conflicting"):
        bench._grok(grok)


def test_existing_incompatible_report_is_preserved(tmp_path, captures):
    for k, payload in captures.items():
        (tmp_path / f"{k}.json").write_bytes(payload)
    out = tmp_path / "out"
    out.mkdir()
    (out / "summary.json").write_bytes(b"previous")
    with pytest.raises(ValueError, match=r"conflicting benchmark output.*summary\.json"):
        bench.run_native_hook_benchmark(tmp_path, out)
    assert (out / "summary.json").read_bytes() == b"previous"
    assert not (out / "protocol.json").exists()
