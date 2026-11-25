import json

import pytest

from swarmtrace import cli
from swarmtrace.eval.hook_files import review_hook_file


@pytest.mark.parametrize(("provider", "event_key", "event_name"), [
    ("claude", "hook_event_name", "SessionStart"),
    ("grok", "hookEventName", "session_start"),
])
def test_cli_reads_one_native_jsonl_capture_without_echoing_payloads(tmp_path, capsys, provider, event_key, event_name):
    capture = tmp_path / "capture.jsonl"
    path_marker = "/personal/do-not-share"
    hook = {event_key: event_name, "transcript_path": path_marker, "tool_input": {"text": "unpublished note"}}
    capture.write_text("\n" + json.dumps(hook) + "\n", encoding="utf-8-sig")
    cli.main(["review-hook-events", "--provider", provider, "--events", str(capture)])
    output = capsys.readouterr().out
    result = json.loads(output)
    assert result["provider"] == provider and result["counts"]["events"] == 1
    assert "unpublished note" not in output and path_marker not in output


def test_input_files_have_independent_lifecycle_state(tmp_path):
    capture = tmp_path / "native.jsonl"
    hook = {"session_id": "one-session", "agent_id": "worker-A"}
    for event_name, key in [("SubagentStart", "open_at_end"), ("SubagentStop", "orphan_stops")]:
        capture.write_text(json.dumps({**hook, "hook_event_name": event_name}), encoding="utf-8")
        assert review_hook_file(capture, "claude")["counts"]["lifecycle"][key] == 1


def test_optional_links_locate_records_without_printing_identities(tmp_path, capsys):
    path = tmp_path / "native.jsonl"
    start = {"hookEventName": "subagent_start", "sessionId": "private-parent", "subagentId": "private-child"}
    stop = {"hookEventName": "subagent_stop", "sessionId": "private-child", "subagentId": "private-child"}
    path.write_text(json.dumps(start) + "\n\n" + json.dumps(stop), encoding="utf-8")
    cli.main(["review-hook-events", "--events", str(path), "--provider", "grok", "--show-links"])
    output = capsys.readouterr().out
    assert "private-" not in output
    assert json.loads(output)["links"] == [{"start_event": 1, "stop_event": 2}]


def test_grok_compatibility_fields_cannot_select_claude_or_disagree(tmp_path):
    path = tmp_path / "capture.jsonl"
    event = {"hookEventName": "subagent_start", "hook_event_name": "subagent_start",
             "sessionId": "one", "session_id": "one", "subagentId": "child"}
    path.write_text(json.dumps(event), encoding="utf-8")
    assert review_hook_file(path, "grok")["counts"]["start_events"] == 1
    with pytest.raises(ValueError, match="Grok hook format"):
        review_hook_file(path, "claude")
    for change in ({"hook_event_name": "subagent_stop"}, {"session_id": "other"}):
        path.write_text(json.dumps(event | change), encoding="utf-8")
        with pytest.raises(ValueError, match="conflicting native Grok fields"):
            review_hook_file(path, "grok")


def test_benchmark_cli_forwards_local_paths_and_fetch_is_opt_in(tmp_path, monkeypatch):
    from swarmtrace.reproduce import native_hooks

    calls = []
    monkeypatch.setattr(native_hooks, "run_native_hook_benchmark",
                        lambda source, out, *, fetch: calls.append((source, out, fetch)))
    source, out = tmp_path / "input", tmp_path / "out"
    command = ["native-hook-benchmark", "--source-dir", str(source), "--out", str(out)]
    cli.main(command)
    cli.main([*command, "--fetch"])
    assert calls == [(source, out, False), (source, out, True)]


@pytest.mark.parametrize("payload", [
    "\n", "[]", '{"hook_event_name":null}', '{"hook_event_name":"  "}', '{"hookEventName":"session_start"}', '{"private":"never echo',
])
def test_cli_rejects_an_invalid_capture_without_echoing_the_bad_line(tmp_path, capsys, payload):
    capture = tmp_path / "invalid.jsonl"
    capture.write_text(payload, encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        cli.main(["review-hook-events", "--provider", "claude", "--events", str(capture)])
    assert exc.value.code == 2 and "never echo" not in capsys.readouterr().err
