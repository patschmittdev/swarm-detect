import json
import subprocess
import sys
from pathlib import Path
from urllib.request import urlopen

import pytest

from swarmtrace.pilot import harness
from swarmtrace.pilot.__main__ import main
from swarmtrace.pilot.tasks import TASKS

EXPORT_FIELDS = ("seq", "t_start", "t_end", "token_id", "user_agent", "method", "path", "query",
                 "status", "bytes_in", "bytes_out", "write_sha256")
RUN_FILES = {"requests.jsonl", "manifest.json", "labels.json", "notes.json", "completion.json",
             "raw"}


def test_claude_command():
    tail = ["--no-session-persistence", "--setting-sources", "", "--strict-mcp-config",
            "--no-chrome", "--output-format", "json"]
    head = ["claude", "-p", "--model", "sonnet", "--settings"]
    assert harness.claude_command("sonnet") == head + [
        '{"permissions":{"allow":["Bash(curl:*)"]}}', "--disallowedTools", "Agent", "Task"] + tail
    assert harness.claude_command("sonnet", subagents=True) == head + [
        '{"permissions":{"allow":["Bash(curl:*)","Agent","Task"]}}'] + tail
    assert "--allowedTools" not in harness.claude_command("sonnet")


def test_codex_command():
    assert harness.codex_command("m1", Path("out.txt")) == [
        "codex", "exec", "-m", "m1", "-s", "workspace-write", "-c",
        "sandbox_workspace_write.network_access=true", "--skip-git-repo-check", "-o", "out.txt",
        "-"]
    assert not harness.LAUNCHERS["codex"].native_subagents
    assert harness.LAUNCHERS["claude"].native_subagents


def test_usage_parsers():
    out = json.dumps({"total_cost_usd": 0.5, "num_turns": 4,
                      "usage": {"input_tokens": 10, "output_tokens": 3}})
    usage = harness.parse_claude_usage("noise\n" + out, "")
    assert usage["total_cost_usd"] == 0.5 and usage["input_tokens"] == 10
    assert harness.parse_claude_usage("not json", "") is None
    assert harness.parse_codex_usage("", "tokens used\n12,345\n") == {"total_tokens": 12345}
    assert harness.parse_codex_usage("", "") is None


def test_prompts_are_plain():
    for task in TASKS.values():
        assert "{base_url}" in task.prompt and "note named" in task.prompt
        assert not task.done([])
    for condition in ("single", "swarm_native", "swarm_peers", "independent", "duplicates"):
        for launcher in harness.LAUNCHERS.values():
            if condition == "swarm_native" and not launcher.native_subagents:
                continue
            text = harness.agent_prompt("owners", "http://127.0.0.9:1", condition, launcher, 3, 2)
            assert "http://127.0.0.9:1/help" in text
            for word in ("log", "monitor", "detect", "swarm", "study"):
                assert word not in text.lower()
    with pytest.raises(ValueError, match="no subagent tool"):
        harness.agent_prompt("owners", "u", "swarm_native", harness.LAUNCHERS["codex"], 3, 2)
    fake = harness.LAUNCHERS["fake"]
    assert (harness.agent_prompt("owners", "u", "duplicates", fake, 3, 2)
            == harness.agent_prompt("owners", "u", "single", fake, 3, 2))


def dry(tmp_path, condition, **kw):
    out = tmp_path / condition
    harness.run(harness.RunConfig(condition=condition, out=out, seed=5, dry_run=True,
                                  duration=1.0, stagger=0.05, jitter=0.05, timeout=60, **kw))
    assert {p.name for p in out.iterdir()} == RUN_FILES
    load = lambda n: json.loads((out / f"{n}.json").read_text())  # noqa: E731
    log = [json.loads(x) for x in (out / "requests.jsonl").read_text().splitlines()]
    return load("manifest"), load("labels"), load("notes"), load("completion"), log


@pytest.mark.parametrize("condition,kw,groups,positive", [
    ("single", {}, 1, False),
    ("swarm_native", {"subagents": 3}, 1, True),
    ("swarm_peers", {"agents": 3}, 1, True),
    ("independent", {"agents": 3}, 3, False),
    ("duplicates", {"agents": 3}, 3, False),
    ("lookalike", {"mix": ["crawler", "many_sessions"]}, 2, False),
])
def test_dry_run_each_condition(tmp_path, condition, kw, groups, positive):
    manifest, labels, notes, completion, log = dry(tmp_path, condition, **kw)
    procs = labels["processes"]
    assert labels["positive"] is positive and len({p["group_id"] for p in procs}) == groups
    assert manifest["condition"] == condition and manifest["timeout_hit"] is False
    assert [p["index"] for p in manifest["processes"]] == [p["index"] for p in procs]
    assert len({p["address"] for p in procs}) == len(procs)
    assert {e["via"] for e in log} == {p["address"] for p in procs}
    assert [e["seq"] for e in log] == list(range(1, len(log) + 1))
    for p in manifest["processes"]:
        if p["kind"] == "agent":
            assert p["exit_code"] == 0 and p["duration_s"] is not None
            assert "<fake agent script>" in p["command"]
        assert "via" not in p and "address" not in p and "group_id" not in p
    if condition != "lookalike":
        assert all(completion.values()) and set(completion) <= set(TASKS)
        assert notes
    if condition == "swarm_native":
        assert len({e["token_id"] for e in log if e["token_id"]}) == 4
        assert labels["expected_subagents"] == 3
    else:
        assert labels["expected_subagents"] is None
    if condition == "duplicates":
        assert len({p["task_id"] for p in procs}) == 1
    if condition == "independent":
        assert len({p["task_id"] for p in procs}) == 3
    for p in procs:
        rows = [e for e in log if e["via"] == p["address"]]
        assert labels["observed"]["ambiguous_tokens"] == []
        for token in {e["token_id"] for e in rows if e["token_id"]}:
            assert labels["observed"]["tokens"][token] == [p["address"]]
        assert labels["observed"][p["address"]] == {
            "requests": len(rows),
            "distinct_token_ids": len({e["token_id"] for e in rows if e["token_id"]})}


def test_background_and_planned_command(tmp_path):
    out = tmp_path / "bg"
    harness.run(harness.RunConfig(condition="single", out=out, seed=2, launcher="claude",
                                  dry_run=True, background=True, duration=1.0, stagger=0.05,
                                  jitter=0.05))
    labels = json.loads((out / "labels.json").read_text())
    manifest = json.loads((out / "manifest.json").read_text())
    assert [p["group_id"] for p in labels["processes"]] == ["p0", "background"]
    assert manifest["processes"][0]["planned_command"][0] == "claude"


def test_refuses_existing_directory(tmp_path):
    with pytest.raises(FileExistsError):
        harness.run(harness.RunConfig(condition="single", out=tmp_path, seed=1, dry_run=True))


def test_timeout_kills_hung_agent(tmp_path):
    out = tmp_path / "hung"
    harness.run(harness.RunConfig(condition="single", out=out, seed=1,
                                  launcher=harness.fake_launcher(hang=True), timeout=2.0,
                                  stagger=0, jitter=0.01))
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["timeout_hit"] is True
    assert manifest["processes"][0]["exit_code"] not in (0, None)
    assert manifest["processes"][0]["duration_s"] < 10


def test_cli_dry_run(tmp_path, capsys):
    out = tmp_path / "cli"
    assert main(["run", "--condition", "independent", "--agents", "2", "--dry-run",
                 "--seed", "3", "--out", str(out), "--task", "owners", "orphans"]) == 0
    labels = json.loads((out / "labels.json").read_text())
    assert [p["task_id"] for p in labels["processes"]] == ["owners", "orphans"]


def test_per_process_launchers_and_models(tmp_path):
    out = tmp_path / "mixed"
    harness.run(harness.RunConfig(condition="duplicates", out=out, seed=4, dry_run=True,
                                  agents=3, launchers=["claude", "codex", "claude"],
                                  models=["m-a", "m-b", "m-c"], stagger=0.05, jitter=0.05))
    labels = json.loads((out / "labels.json").read_text())
    manifest = json.loads((out / "manifest.json").read_text())
    assert [p["requested_launcher"] for p in labels["processes"]] == ["claude", "codex", "claude"]
    assert [p["model"] for p in labels["processes"]] == ["m-a", "m-b", "m-c"]
    assert [p["model"] for p in manifest["processes"]] == ["m-a", "m-b", "m-c"]
    planned = [p["planned_command"] for p in manifest["processes"]]
    assert planned[0][0] == "claude" and "--disallowedTools" in planned[0]
    assert planned[1][:2] == ["codex", "exec"] and "m-b" in planned[1]


@pytest.mark.parametrize("kw", [{"launchers": ["claude", "claude"]},
                                {"launchers": ["claude"] * 3, "models": ["a"]},
                                {"launchers": ["claude", "nope", "claude"]}])
def test_launcher_count_mismatch(tmp_path, kw):
    with pytest.raises(ValueError):
        harness.run(harness.RunConfig(condition="swarm_peers", out=tmp_path / "x", seed=1,
                                      agents=3, dry_run=True, **kw))
    assert not (tmp_path / "x").exists()


def test_codex_swarm_native_is_an_error(tmp_path):
    for dry_run in (True, False):
        with pytest.raises(ValueError, match="no subagent tool"):
            harness.run(harness.RunConfig(condition="swarm_native", out=tmp_path / "x", seed=1,
                                          launcher="codex", dry_run=dry_run))


def test_independent_needs_distinct_tasks(tmp_path):
    with pytest.raises(ValueError):
        harness.run(harness.RunConfig(condition="independent", out=tmp_path / "a", seed=1,
                                      agents=9, dry_run=True))
    with pytest.raises(ValueError):
        harness.run(harness.RunConfig(condition="independent", out=tmp_path / "b", seed=1,
                                      agents=2, tasks=["owners", "owners"], dry_run=True))


def test_swarm_native_claude_allows_task(tmp_path):
    out = tmp_path / "native"
    harness.run(harness.RunConfig(condition="swarm_native", out=out, seed=1, launcher="claude",
                                  dry_run=True, stagger=0, jitter=0.01))
    manifest = json.loads((out / "manifest.json").read_text())
    planned = manifest["processes"][0]["planned_command"]
    assert json.loads(planned[5])["permissions"]["allow"] == ["Bash(curl:*)", "Agent", "Task"]
    assert "--disallowedTools" not in planned


def test_export(tmp_path, capsys):
    manifest, labels, notes, completion, log = dry(tmp_path, "swarm_peers", agents=2)
    run_dir = tmp_path / "swarm_peers"
    with_id, without_id = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
    assert main(["export", "--run", str(run_dir), "--out", str(with_id)]) == 0
    assert main(["export", "--run", str(run_dir), "--out", str(without_id),
                 "--no-identity"]) == 0
    a = [json.loads(x) for x in with_id.read_text().splitlines()]
    b = [json.loads(x) for x in without_id.read_text().splitlines()]
    assert len(a) == len(b) == len(log)
    assert all(tuple(r) == EXPORT_FIELDS for r in a + b)
    assert all("auth" in e and "via" in e for e in log)
    assert [r["token_id"] for r in a] == [e["token_id"] for e in log]
    assert all(r["token_id"] is None for r in b)
    assert [{k: v for k, v in r.items() if k != "token_id"} for r in a] ==         [{k: v for k, v in r.items() if k != "token_id"} for r in b]
    with pytest.raises(FileExistsError):
        harness.export(run_dir, with_id)


def participation_of(tmp_path, condition, **kw):
    manifest, labels, notes, completion, log = dry(tmp_path, condition, **kw)
    return labels, manifest, log


def test_participation_peers_and_duplicates(tmp_path):
    labels, manifest, log = participation_of(tmp_path, "swarm_peers", agents=3)
    part = labels["participation"]
    assert labels["positive_means"] == "assigned to a coordination condition by the harness"
    assert all(p["worked"] and p["doc_reads"] >= 5 and p["note_writes"] >= 2
               for p in part["processes"])
    assert part["cross_process_note_reads"] >= 1 and part["group_formed"] is True
    assert part["negative_contaminated"] is None
    for p in part["processes"]:
        rows = [e for e in log if e["via"] == p["address"]]
        assert p["requests"] == len(rows)
        assert p["doc_reads"] == sum(e["path"].startswith("/docs/") and e["status"] == 200
                                     for e in rows)
    policies = {p["launch_policy"] for p in manifest["processes"]}
    assert policies == {"scripted test agent"}

    labels, _, _ = participation_of(tmp_path, "duplicates", agents=3)
    part = labels["participation"]
    assert part["cross_process_note_reads"] == 0 and part["negative_contaminated"] is False
    assert part["group_formed"] is None and labels["positive"] is False


def test_swarm_native_group_formed_from_subagent_stats(tmp_path):
    labels, _, _ = participation_of(tmp_path, "swarm_native", subagents=3)
    proc = labels["participation"]["processes"][0]
    assert proc["subagents_spawned"] == 3 and proc["subagents_completed"] == 3
    assert labels["participation"]["group_formed"] is True
    assert harness.subagent_stats('{"subagent_stats": {"spawned": 2}}') == (2, None)
    assert harness.subagent_stats("not json") == (None, None)


def test_launch_policies():
    assert harness.launch_policy("claude", True) == (
        "pre-approved: curl commands; subagent tool: allowed; other tools: not pre-approved")
    assert "subagent tool: denied" in harness.launch_policy("claude", False)
    assert harness.launch_policy("codex", False) == (
        "sandbox: workspace-write in an empty directory; network: allowed")


def test_launch_failure_cleans_up(tmp_path):
    calls = []

    def build(model, raw, sub):
        calls.append(1)
        if len(calls) == 1:
            return harness.fake_launcher(hang=True).build(model, raw, sub)
        return ["definitely-not-a-real-program-xyz"]

    launcher = harness.Launcher("fake", build, harness.parse_claude_usage, True)
    out = tmp_path / "fail"
    with pytest.raises(OSError):
        harness.run(harness.RunConfig(condition="duplicates", out=out, seed=1, agents=2,
                                      launcher=launcher, stagger=0, jitter=0.01))
    assert (out / "FAILED.txt").read_text().strip() in ("FileNotFoundError", "OSError")
    assert not (out / "manifest.json").exists()


def test_serve_cli_starts():
    proc = subprocess.Popen([sys.executable, "-m", "swarmtrace.pilot", "serve", "--seed", "1",
                             "--port", "0"], stdout=subprocess.PIPE, text=True)
    try:
        line = proc.stdout.readline()
        assert line.startswith("serving http://127.0.0.1:")
        base = line.split()[1]
        with urlopen(base + "/help", timeout=5) as response:
            assert response.status == 200
    finally:
        harness.kill_tree(proc)
