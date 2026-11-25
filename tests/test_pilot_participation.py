import gzip
import json
import threading
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from swarmtrace.pilot import harness
from swarmtrace.pilot.service import Service, token_id

ADDRESSES = ["127.0.0.1", "127.0.0.2", "127.0.0.3"]


def call(base, method, path, token=None, body=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        with urlopen(Request(base + path, data=body, method=method, headers=headers),
                     timeout=5) as r:
            return r.status, json.loads(r.read() or b"null")
    except HTTPError as e:
        return e.code, json.loads(e.read() or b"null")


class Store:
    def __init__(self, tmp_path):
        self.log_path = tmp_path / "log.jsonl"
        self.svc = Service(seed=1, addresses=ADDRESSES, log_path=self.log_path).start()
        self.bases = self.svc.base_urls
        self.tokens = [call(b, "POST", "/session")[1]["token"] for b in self.bases]

    def __call__(self, k, method, path, body=None):
        return call(self.bases[k], method, path, self.tokens[k], body)

    def finish(self, condition="independent"):
        self.svc.stop()
        log = harness.read_log(self.log_path)
        rows = [{"kind": "agent", "address": a, "index": i,
                 "launcher_obj": harness.LAUNCHERS["codex"]} for i, a in enumerate(ADDRESSES)]
        return log, harness.participation(log, rows, condition, {})


def reads(part):
    return [p["cross_process_note_reads"] for p in part["processes"]]


def test_alias_of_own_note_does_not_count(tmp_path):
    s = Store(tmp_path)
    s(0, "PUT", "/notes/n", b"from A")
    s(1, "PUT", "/notes/%6E", b"from B")
    assert s(1, "GET", "/notes/n")[1]["text"] == "from B"
    log, part = s.finish()
    assert reads(part) == [0, 0, 0] and part["negative_contaminated"] is False
    get = log[-1]
    assert (get["note"], get["note_version"], get["note_writer"]) == ("n", 2, token_id(s.tokens[1]))
    assert [e["note"] for e in log if e["method"] == "PUT"] == ["n", "n"]


def test_genuine_cross_process_read_counts(tmp_path):
    s = Store(tmp_path)
    s(0, "PUT", "/notes/plan", b"A's plan")
    s(1, "GET", "/notes/plan")
    s(1, "GET", "/notes/missing")
    log, part = s.finish("swarm_peers")
    assert reads(part) == [0, 1, 0] and part["cross_process_note_reads"] == 1
    assert log[-1]["note"] == "missing" and log[-1]["note_version"] is None


def test_own_note_read_does_not_count(tmp_path):
    s = Store(tmp_path)
    s(0, "PUT", "/notes/mine", b"x")
    s(1, "PUT", "/notes/other", b"y")
    s(0, "GET", "/notes/mine")
    _, part = s.finish()
    assert reads(part) == [0, 0, 0]


def test_overlapping_writers_version_not_log_order(tmp_path, monkeypatch):
    """A's PUT is applied first but its response is logged after B's; the reader gets B's."""
    s = Store(tmp_path)
    release = threading.Event()
    original = s.svc.record

    def slow_record(entry):
        if entry["method"] == "PUT" and entry.get("note_version") == 1:
            release.wait(5)
        original(entry)
    s.svc.record = slow_record
    first = threading.Thread(target=s, args=(0, "PUT", "/notes/race", b"A"))
    first.start()
    time.sleep(0.2)
    s(1, "PUT", "/notes/race", b"B")
    s(2, "GET", "/notes/race")
    release.set()
    first.join()
    log, part = s.finish()
    puts = [e for e in log if e["method"] == "PUT"]
    assert [e["note_version"] for e in puts] == [2, 1]
    get = next(e for e in log if e["method"] == "GET")
    assert get["note_writer"] == token_id(s.tokens[1])
    assert reads(part) == [0, 0, 1]


def test_ambiguous_token_never_counts(tmp_path):
    s = Store(tmp_path)
    s(0, "PUT", "/notes/n", b"x")
    call(s.bases[2], "GET", "/collections", s.tokens[0])
    s(1, "GET", "/notes/n")
    _, part = s.finish()
    assert reads(part) == [0, 0, 0]


@pytest.mark.parametrize("stdout,expected", [
    ('{"result": "ok", "subagent_stats": {"spawned": 3, "completed": 2}}', (3, 2)),
    (json.dumps({"result": "ok", "subagent_stats": {"spawned": 4, "completed": 4}}, indent=2),
     (4, 4)),
    ('{"result": "ok", "usage": {}}', (None, None)),
    ("Error: something went wrong\n", (None, None)),
    ('starting\n{"type": "result", "is_error": true, "result": "could not start"}\n',
     (None, None)),
    ('noise\n{"subagent_stats": {"spawned": 2, "completed": 2}}\ntrailing text\n', (2, 2)),
    ('{"subagent_stats": {"spawned": true, "completed": "2"}}', (None, None)),
])
def test_subagent_stats_parsing(stdout, expected):
    assert harness.subagent_stats(stdout) == expected


def test_unknown_subagent_stats_leave_group_unknown():
    rows = [{"kind": "agent", "address": "127.0.0.1", "index": 0,
             "launcher_obj": harness.LAUNCHERS["claude"]}]
    part = harness.participation([], rows, "swarm_native", {0: "not json"})
    assert part["group_formed"] is None
    assert part["group_formed_reason"] == "runner reported no subagent statistics"
    part = harness.participation([], rows, "swarm_native",
                                 {0: '{"subagent_stats": {"spawned": 1, "completed": 1}}'})
    assert part["group_formed"] is False and "group_formed_reason" not in part


@pytest.mark.parametrize("text,version", [
    ("2.1.331 (Claude Code)\n", "2.1.331"), ("codex-cli 0.172.0\n", "0.172.0"),
    ("no version here", None), ("", None)])
def test_parse_version(text, version):
    assert harness.parse_version(text) == version


def test_child_is_killed_when_failure_follows_spawn(tmp_path, monkeypatch):
    spawned = []

    def boom(record):
        spawned.append(record["proc"])
        raise RuntimeError("injected")
    monkeypatch.setattr(harness, "_AFTER_SPAWN", boom)
    out = tmp_path / "run"
    with pytest.raises(RuntimeError, match="injected"):
        harness.run(harness.RunConfig(condition="single", out=out, seed=1,
                                      launcher=harness.fake_launcher(hang=True), stagger=0,
                                      jitter=0.01))
    assert spawned and spawned[0].poll() is not None
    assert (out / "FAILED.txt").read_text().strip() == "RuntimeError"


def test_drain_timeout_marks_run_failed(tmp_path, monkeypatch):
    original_stop = Service.stop

    def stop(self):
        self.drain_timeout = 0.2
        self.enter()  # a handler that never finishes
        original_stop(self)
    monkeypatch.setattr(Service, "stop", stop)
    out = tmp_path / "run"
    harness.run(harness.RunConfig(condition="single", out=out, seed=1, dry_run=True, stagger=0,
                                  jitter=0.01))
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["drain_timed_out"] is True
    assert (out / "FAILED.txt").read_text().strip() == "DrainTimeout"


def test_export_reads_published_form(tmp_path):
    out = tmp_path / "run"
    harness.run(harness.RunConfig(condition="single", out=out, seed=1, dry_run=True, stagger=0,
                                  jitter=0.01))
    plain = (out / "requests.jsonl").read_bytes()
    published = tmp_path / "published"
    published.mkdir()
    (published / "requests.jsonl.gz").write_bytes(gzip.compress(plain, mtime=0))
    harness.export(out, tmp_path / "a.jsonl")
    harness.export(published, tmp_path / "b.jsonl")
    assert (tmp_path / "a.jsonl").read_bytes() == (tmp_path / "b.jsonl").read_bytes()
    with pytest.raises(FileNotFoundError, match="neither"):
        harness.export(tmp_path / "empty", tmp_path / "c.jsonl")


def test_head_logs_zero_body_bytes(tmp_path):
    s = Store(tmp_path)
    call(s.bases[0], "HEAD", "/help")
    log, _ = s.finish()
    assert log[-1]["method"] == "HEAD" and log[-1]["bytes_out"] == 0
