import gzip
import hashlib
import json

import pytest

from swarmtrace.pilot import batch as pb
from swarmtrace.pilot import publish as pp
from swarmtrace.pilot.__main__ import main

ROWS = [
    {"run": "dev-01", "condition": "swarm_peers", "seed": 11, "background": False,
     "launchers": ["claude", "claude"], "models": ["sonnet", "sonnet"], "tasks": ["owners"]},
    {"run": "dev-02", "condition": "single", "seed": 12, "background": False,
     "launchers": ["codex"], "models": ["m2"], "tasks": ["orphans"]},
]
SENTINEL_USER = "sentinel" + "-user"


def drive_path() -> str:
    return "X" + ":" + "\\tmp\\sentinel"


@pytest.fixture
def setup(tmp_path):
    protocol = tmp_path / "protocol.json"
    protocol.write_text(json.dumps({"development_runs": ROWS, "test_runs": ROWS}))
    runs = tmp_path / "runs"
    pb.batch(protocol, "test", runs, dry_run=True, echo=lambda line: None)
    return protocol, runs


def publish_twice(tmp_path, protocol, runs, out_name="pub"):
    review = tmp_path / f"{out_name}-review.json"
    with pytest.raises(pp.ReviewRequired):
        pp.publish(runs, tmp_path / out_name, "test", protocol, review)
    assert not (tmp_path / out_name).exists()
    digest = hashlib.sha256(review.read_bytes()).hexdigest()
    return pp.publish(runs, tmp_path / out_name, "test", protocol, review, digest), review


def rewrite_log(run_dir, edit):
    log = run_dir / "requests.jsonl"
    rows = [json.loads(x) for x in log.read_text().splitlines()]
    edit(rows)
    log.write_text("".join(json.dumps(r) + "\n" for r in rows))


def test_two_step_publish_and_index(tmp_path, setup):
    protocol, runs = setup
    index, review = publish_twice(tmp_path, protocol, runs)
    assert index["set"] == "test" and index["review_sha256"] == hashlib.sha256(
        review.read_bytes()).hexdigest()
    fields = json.loads(review.read_text())["fields"]
    assert set(fields) == {"note_name", "notes_path_segment", "search_query", "user_agent"}
    assert index["values_reviewed"] == sum(len(v) for v in fields.values())
    assert {"value": "owners", "count": fields["note_name"][-1]["count"]} in fields["note_name"]
    assert [(r["run"], r["condition"], r["seed"], r["positive"]) for r in index["runs"]] == [
        ("dev-01", "swarm_peers", 11, True), ("dev-02", "single", 12, False)]
    pub = tmp_path / "pub"
    for entry in index["runs"]:
        run_dir = pub / entry["run"]
        assert {p.name for p in run_dir.iterdir()} == set(pp.PUBLISHED)
        for name, digest in entry["files"].items():
            assert hashlib.sha256((run_dir / name).read_bytes()).hexdigest() == digest
        assert entry["redactions"] == {}
        log = gzip.decompress((run_dir / "requests.jsonl.gz").read_bytes()).splitlines()
        source = (runs / entry["run"] / "requests.jsonl").read_text().splitlines()
        assert [json.loads(x) for x in log] == [json.loads(x) for x in source]
        assert (run_dir / "requests.jsonl.gz").read_bytes()[4:8] == b"\0\0\0\0"
        manifest = json.loads((run_dir / "manifest.json").read_text())
        assert {"dry_run", "batch_parallel", "timeout_s", "runner_versions"} <= set(manifest)
        assert manifest["processes"][0]["launch_policy"] == "scripted test agent"
        text = (run_dir / "manifest.json").read_text()
        assert "command" not in text and "planned" not in text
        assert entry["dropped_keys"]["manifest.json"] >= 2
    again, _ = publish_twice(tmp_path, protocol, runs, "pub2")
    assert [r["files"] for r in again["runs"]] == [r["files"] for r in index["runs"]]
    with pytest.raises(FileExistsError):
        pp.publish(runs, pub, "test", protocol, tmp_path / "r.json")


def test_publish_cli_two_steps(tmp_path, setup, capsys):
    protocol, runs = setup
    review = tmp_path / "review.json"
    argv = ["publish", "--runs", str(runs), "--out", str(tmp_path / "pub"), "--set", "test",
            "--protocol", str(protocol), "--review-out", str(review)]
    assert main(argv) == 2
    assert "--reviewed-sha256" in capsys.readouterr().err
    assert main(argv + ["--reviewed-sha256", "0" * 64]) == 2
    digest = hashlib.sha256(review.read_bytes()).hexdigest()
    assert main(argv + ["--reviewed-sha256", digest]) == 0
    assert (tmp_path / "pub" / "index.json").exists()
    with pytest.raises(SystemExit):
        main(argv[:7] + ["other"] + argv[8:])


def test_publish_redacts_by_shape(tmp_path, setup):
    protocol, runs = setup

    def edit(rows):
        rows[0]["path"] = "/notes/what%20ever"
        rows[1]["user_agent"] = "agent-of-sorts/1"
        rows[2]["query"] = "x=1"
        rows[3]["method"] = "BREW"
        rows[4]["bytes_in"] = "12"
        rows[5]["write_sha256"] = "not-hex"
        rows[6]["extra"] = 1
    run_dir = runs / "dev-01"
    rewrite_log(run_dir, edit)
    manifest = json.loads((run_dir / "manifest.json").read_text())
    manifest["processes"][0]["usage"] = {"input_tokens": 5, "model_name": "x", "num_turns": "3"}
    manifest["processes"][0]["model"] = "unlisted-model"
    (run_dir / "manifest.json").write_text(json.dumps(manifest))
    index, _ = publish_twice(tmp_path, protocol, runs)
    entry = index["runs"][0]
    assert entry["redactions"] == {
        "manifest.json:processes.model": 1, "manifest.json:processes.usage.num_turns": 1,
        "requests.jsonl:bytes_in": 1, "requests.jsonl:method": 1, "requests.jsonl:path": 1,
        "requests.jsonl:query": 1, "requests.jsonl:user_agent": 1,
        "requests.jsonl:write_sha256": 1}
    assert entry["dropped_keys"]["requests.jsonl"] == 1
    pub = tmp_path / "pub" / "dev-01"
    rows = [json.loads(x) for x in
            gzip.decompress((pub / "requests.jsonl.gz").read_bytes()).splitlines()]
    assert rows[0]["path"] == "/[redacted]" and rows[1]["user_agent"] == "[redacted]"
    assert rows[2]["query"] == "[redacted]" and rows[3]["method"] == "[redacted]"
    assert "extra" not in rows[6]
    assert {"via", "peer_port", "auth", "note", "note_version", "note_writer"} <= set(rows[0])
    usage = json.loads((pub / "manifest.json").read_text())["processes"][0]["usage"]
    assert usage == {"input_tokens": 5, "num_turns": "[redacted]"}


def test_shapes():
    assert pp.path_ok("/") and pp.path_ok("/notes/a-1.txt") and pp.path_ok("/docs/x%2Dy")
    assert not pp.path_ok("/notes/a b") and not pp.path_ok("/notes/" + "a" * 65)
    assert not pp.path_ok("/notes/a%2Fb") and not pp.path_ok("notes")
    assert pp.query_ok("") and pp.query_ok("q=risk register") and pp.query_ok("q=a%20b")
    assert not pp.query_ok("q=a&x=1") and not pp.query_ok("x=1")
    assert not pp.query_ok("q=" + "a" * 81)
    assert pp.agent_ok("curl/8.7.1") and pp.agent_ok("Python-urllib/3.12")
    assert pp.agent_ok("docstore-client/1.0 crawler") and not pp.agent_ok("curl/8 (x)")


def test_publish_checks_decoded_values(tmp_path, setup, monkeypatch):
    protocol, runs = setup
    run_dir = runs / "dev-01"
    encoded = drive_path().replace(":", "%3A").replace("\\", "%5C")

    def drive(rows):
        rows[0]["path"] = "/notes/" + encoded
    rewrite_log(run_dir, drive)
    with pytest.raises(ValueError, match="requests.jsonl line 1: field path"):
        pp.publish(runs, tmp_path / "pub", "test", protocol, tmp_path / "r.json")

    def user(rows):
        rows[0]["path"], rows[0]["query"] = "/search", "q=" + SENTINEL_USER.upper()
    rewrite_log(run_dir, user)
    monkeypatch.setenv("USERNAME", SENTINEL_USER)
    with pytest.raises(ValueError, match="requests.jsonl line 1: field query"):
        pp.publish(runs, tmp_path / "pub", "test", protocol, tmp_path / "r.json")
    assert not (tmp_path / "pub").exists()


def test_check_clean_sentinels(monkeypatch):
    monkeypatch.setenv("USERNAME", SENTINEL_USER)
    needles = pp._forbidden()
    pp.check_clean("f", {"a": ["fine", 1, None]}, needles)
    for bad in ({"a": drive_path()}, {"a": [drive_path().replace("\\", "/")]},
                {"p": [{"ua": "by " + SENTINEL_USER.upper()}]}, {"h": str(pp.Path.home())}):
        with pytest.raises(ValueError, match="f: field"):
            pp.check_clean("f", bad, needles)


def test_publish_refusals(tmp_path, setup):
    protocol, runs = setup
    review = tmp_path / "r.json"
    with pytest.raises(ValueError, match="set must be"):
        pp.publish(runs, tmp_path / "pub", "other", protocol, review)
    with pytest.raises(ValueError, match="outside"):
        pp.publish(runs, tmp_path / "pub", "test", protocol, tmp_path / "pub" / "r.json")
    (runs / "dev-02" / "FAILED.txt").write_text("OSError\n")
    with pytest.raises(ValueError, match="dev-02 is not a complete run"):
        pp.publish(runs, tmp_path / "pub", "test", protocol, review)
    (runs / "dev-02" / "FAILED.txt").unlink()
    (runs / "dev-02" / "notes.json").unlink()
    with pytest.raises(ValueError, match="dev-02 is not a complete run"):
        pp.publish(runs, tmp_path / "pub", "test", protocol, review)
    (runs / "dev-02").rename(runs / "bad run")
    with pytest.raises(ValueError, match="run id"):
        pp.publish(runs, tmp_path / "pub", "test", protocol, review)
