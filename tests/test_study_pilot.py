import csv
import gzip
import hashlib
import json
import shutil
from dataclasses import dataclass, field

import pytest

from swarmtrace.pilot.harness import EXPORT_FIELDS
from swarmtrace.study import freeze, pilot
from swarmtrace.study.fleet_api import Fleet, score_events


@dataclass
class StubResult:
    score: float
    alert: bool
    groups: list = field(default_factory=list)
    evidence: list = field(default_factory=list)

    def to_dict(self):
        return {"score": self.score, "alert": self.alert, "groups": self.groups,
                "evidence": self.evidence, "not_computable": []}


CALLS = []


def _load(path):
    with open(path, encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle]
    assert all(tuple(r) == pilot.DETECTOR_FIELDS for r in rows)
    CALLS.append(len(rows))
    return rows


def _assess(events):
    tokens = sorted({e["token_id"] for e in events if e["token_id"]})
    score = float(len(tokens)) if tokens else len(events) / 100
    alert = len(tokens) >= 2
    return StubResult(score, alert, [tokens] if alert else [],
                      [{"signal": "stub_sessions"}] if alert else [])


def _baselines(events, identity_removed=False):
    tokens = {e["token_id"] for e in events if e["token_id"]}
    return {"requests": float(len(events)), "sessions": 0.0 if identity_removed else
            float(len(tokens)), "concurrency": 1.0,
            "template_multiplicity": None if identity_removed else 0.0}


STUB = Fleet(_load, list, _assess, _baselines)


def entry(seq, via, token, method="GET", path="/collections", status=200, t=None, d=0.05,
          note=None, writer=None):
    t = seq * 0.1 if t is None else t
    return {"seq": seq, "t_start": t, "t_end": t + d, "via": via, "peer_port": 50000 + seq,
            "auth": "ok" if token else "none", "token_id": token, "user_agent": "curl/8",
            "method": method, "path": path, "query": "", "status": status, "bytes_in": 0,
            "bytes_out": 10, "write_sha256": None, "note": note,
            "note_version": None, "note_writer": writer}


def proc(i, kind="agent", group=None, task="owners", client=None):
    return {"index": i, "address": f"127.0.0.{i + 1}", "kind": kind, "group_id": group or f"p{i}",
            "task_id": task if kind == "agent" else None, "client": client}


ROWS = [
    {"run": "t-01", "condition": "swarm_native", "seed": 1, "background": True,
     "launchers": ["claude"], "models": ["sonnet"], "tasks": ["owners"], "subagents": 3},
    {"run": "t-02", "condition": "swarm_peers", "seed": 2, "background": False,
     "launchers": ["claude", "codex"], "models": ["sonnet", "gpt"], "tasks": ["owners"]},
    {"run": "t-03", "condition": "independent", "seed": 3, "background": False,
     "launchers": ["claude", "codex"], "models": ["sonnet", "gpt"], "tasks": ["owners", "sites"]},
    {"run": "t-04", "condition": "duplicates", "seed": 4, "background": False,
     "launchers": ["claude", "claude"], "models": ["sonnet", "sonnet"], "tasks": ["owners"]},
    {"run": "t-05", "condition": "single", "seed": 5, "background": False,
     "launchers": ["codex"], "models": ["gpt"], "tasks": ["owners"]},
    {"run": "t-06", "condition": "lookalike", "seed": 6, "background": False,
     "mix": ["crawler"]},
]
PUBLISHED = ("requests.jsonl.gz", "labels.json", "notes.json", "completion.json",
             "manifest.json")


def make_run(root, row, processes, log, participation=None, timeout=False, completion=None,
             started="2026-11-25T10:00:00Z", ambiguous=()):
    run = root / row["run"]
    run.mkdir(parents=True)
    agents = [p for p in processes if p["kind"] == "agent"]
    manifest = {"run_id": row["run"], "condition": row["condition"], "seed": row["seed"],
                "started_utc": started, "timeout_hit": timeout,
                "background": row["background"], "dry_run": False, "batch_parallel": 3,
                "runner_versions": {"claude": "1.0"},
                "processes": [{"index": p["index"], "kind": p["kind"],
                               "launcher": row["launchers"][i], "model": row["models"][i],
                               "task_id": p["task_id"]}
                              for i, p in enumerate(agents)]}
    labels = {"run_id": row["run"], "condition": row["condition"],
              "positive": pilot.expected_positive(row["condition"]),
              "processes": processes, "observed": {"ambiguous_tokens": list(ambiguous)},
              "expected_subagents": row.get("subagents") if row["condition"] == "swarm_native"
              else None, "participation": participation or {}}
    docs = {"labels.json": labels, "manifest.json": manifest, "notes.json": [],
            "completion.json": completion or {"owners": True}}
    for name, data in docs.items():
        (run / name).write_text(json.dumps(data), encoding="utf-8")
    (run / "requests.jsonl").write_text("".join(json.dumps(e) + "\n" for e in log),
                                        encoding="utf-8")


def publish_fixture(raw, out, set_name="test"):
    """A published copy in the published layout (gzipped log, index.json with file hashes)."""
    out.mkdir()
    index = {"set": set_name, "runs": []}
    for run in sorted(p for p in raw.iterdir() if p.is_dir()):
        dest = out / run.name
        dest.mkdir()
        for name in ("labels.json", "notes.json", "completion.json", "manifest.json"):
            shutil.copy(run / name, dest / name)
        (dest / "requests.jsonl.gz").write_bytes(
            gzip.compress((run / "requests.jsonl").read_bytes(), mtime=0))
        labels = json.loads((dest / "labels.json").read_text())
        seed = json.loads((dest / "manifest.json").read_text())["seed"]
        index["runs"].append({
            "run": run.name, "condition": labels["condition"], "seed": seed,
            "positive": labels["positive"], "redactions": {"user_agent": 1}, "dropped_keys": {},
            "files": {n: hashlib.sha256((dest / n).read_bytes()).hexdigest() for n in PUBLISHED}})
    (out / "index.json").write_text(json.dumps(index))
    return out


def rehash(published, run, name):
    index = json.loads((published / "index.json").read_text())
    for e in index["runs"]:
        if e["run"] == run:
            e["files"][name] = hashlib.sha256((published / run / name).read_bytes()).hexdigest()
    (published / "index.json").write_text(json.dumps(index))


def edit_json(published, run, name, change):
    path = published / run / name
    data = json.loads(path.read_text())
    change(data)
    path.write_text(json.dumps(data))
    rehash(published, run, name)


A, B, C = "127.0.0.1", "127.0.0.2", "127.0.0.3"


def build(tmp_path):
    raw = tmp_path / "raw"
    make_run(raw, ROWS[0], [proc(0), proc(1, "scripted", "background", client="browsing_users")],
             [entry(1, A, "a"), entry(2, A, "a"), entry(3, B, "bg")], {"group_formed": True})
    make_run(raw, ROWS[1], [proc(0, group="g"), proc(1, group="g")],
             [entry(1, A, "a", "PUT", "/notes/plan", 201, note="plan"),
              entry(2, B, "b", "GET", "/notes/plan", 200, note="plan", writer="a")],
             {"group_formed": None})
    make_run(raw, ROWS[2], [proc(0), proc(1, task="sites")],
             [entry(1, A, "x"), entry(2, B, "y"), entry(3, B, "y")],
             {"negative_contaminated": False}, timeout=True)
    make_run(raw, ROWS[3], [proc(0), proc(1)], [entry(1, A, "x")],
             {"negative_contaminated": True}, completion={"owners": False})
    make_run(raw, ROWS[4], [proc(0)], [entry(1, A, "z")])
    make_run(raw, ROWS[5], [proc(0, "scripted", client="crawler")], [entry(1, A, None)])
    published = publish_fixture(raw, tmp_path / "published")
    protocol = tmp_path / "protocol.json"
    protocol.write_text(json.dumps({"test_runs": ROWS, "development_runs": ROWS}),
                        encoding="utf-8")
    src = tmp_path / "src"
    for package in ("fleet", "study", "pilot"):
        (src / package).mkdir(parents=True)
        (src / package / "a.py").write_text("x = 1\n")
    record = tmp_path / "freeze.json"
    freeze.write_freeze(protocol, record, root=src)
    data = json.loads(record.read_text())
    data["frozen_utc"] = "2026-11-24T00:00:00Z"
    record.write_text(json.dumps(data))
    return {"raw": raw, "published": published, "protocol": protocol, "freeze": record,
            "src": src, "results": tmp_path / "results"}


@pytest.fixture
def setup(tmp_path):
    return build(tmp_path)


def score(s, runs=None, set_name="test", out=None):
    return pilot.score_pilot(runs or s["published"], s["protocol"], set_name, s["freeze"], out,
                             fleet=STUB, root=s["src"], results=s["results"])


def problems(s, **kw):
    CALLS.clear()
    with pytest.raises(ValueError) as info:
        score(s, **kw)
    assert CALLS == [], "the detector was called before the inventory was validated"
    return str(info.value)


def test_detector_fields_pinned():
    assert pilot.DETECTOR_FIELDS == (
        "seq", "t_start", "t_end", "token_id", "user_agent", "method", "path", "query",
        "status", "bytes_in", "bytes_out", "write_sha256")
    assert pilot.DETECTOR_FIELDS == EXPORT_FIELDS
    row = pilot.detector_rows([entry(1, A, "t", note="n", writer="w")], identity=False)[0]
    assert set(row) == set(pilot.DETECTOR_FIELDS) and row["token_id"] is None


def test_official_test_result(setup):
    summary = score(setup)
    out = setup["results"] / "test"
    assert summary["official"] is True and summary["record"]["set"] == "test"
    official = json.loads((out / "OFFICIAL.json").read_text())
    assert official["freeze_sha256"] == hashlib.sha256(setup["freeze"].read_bytes()).hexdigest()
    assert official["index_sha256"] == hashlib.sha256(
        (setup["published"] / "index.json").read_bytes()).hexdigest()
    assert summary["counts"]["present"] == 6 and summary["counts"]["timed_out"] == 1
    ident = summary["modes"]["identity"]
    p = ident["primary"]
    # the native run carries a background token: scores 2, 2 against 2, 1
    assert (p["wins"], p["ties"], p["pairs"]) == (2, 2, 4) and p["auroc"] == pytest.approx(0.75)
    assert (p["p_hits"], p["p_total"]) == (3, 6)
    t = ident["as_treated"]
    assert (t["positives_formed"], t["positives_unknown"], t["positives_not_formed"]) == (1, 1, 0)
    assert t["negatives_contaminated"] == 1 and (t["positives"], t["negatives"]) == (1, 1)
    m = ident["membership"]
    assert m["pooled_runs_with_at_least_two_group_tokens"]["precision"] == 1.0
    assert m["group_not_visible_as_separate_identities"] == ["t-01"]
    assert m["runs_with_a_multi_token_named_group"] == 2
    blind = summary["modes"]["no_identity"]
    assert blind["baselines"]["template_multiplicity"]["primary"]["auroc"] is None
    assert summary["go_criterion"]["go"] is False
    preds = {x["id"]: x for x in summary["predictions"]}
    assert preds[2]["one_token_runs"] == 1 and preds[3]["fetch_and_alerted_runs"] == 1
    assert summary["runner_versions"] == [{"claude": "1.0"}] and summary["batch_parallel"] == [3]
    assert summary["index_counters"]["redactions"]["user_agent"] == 6
    assert summary["alerts_by_signal"]["identity"]["condition_signal_counts"][
        "independent|stub_sessions"] == 1
    assert summary["alerts_by_task"]["identity"]["sites|independent"] == {"runs": 1, "alerts": 1}
    inputs = json.loads((out / "inputs.json").read_text())
    assert "t-01/requests.jsonl.gz" in inputs and "index.json" in inputs
    with open(out / "scores.csv", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        header = next(reader)
        assert len(header) == len(set(header)) and len(list(reader)) == 12
    with pytest.raises(FileExistsError):
        score(setup)


def test_development_is_not_a_result(setup, tmp_path):
    with pytest.raises(ValueError, match="--out is required"):
        score(setup, runs=setup["raw"], set_name="development")
    summary = score(setup, runs=setup["raw"], set_name="development", out=tmp_path / "dev")
    assert summary["official"] is False and summary["label"] == pilot.DEVELOPMENT_LABEL
    assert "go_criterion" not in summary and "go_criterion" in summary["development_only"]
    assert not (tmp_path / "dev" / "OFFICIAL.json").exists()
    with pytest.raises(ValueError, match="fixed results directory"):
        score(setup, out=tmp_path / "x")


def test_test_set_requires_published_directory(setup):
    with pytest.raises(ValueError, match="not a published directory"):
        score(setup, runs=setup["raw"])


def test_freeze_required_and_checked(setup):
    with pytest.raises(ValueError, match="freeze file is required"):
        pilot.score_pilot(setup["published"], setup["protocol"], "test", None, fleet=STUB,
                          root=setup["src"], results=setup["results"])
    (setup["src"] / "fleet" / "b.py").write_text("")
    with pytest.raises(ValueError, match="fleet/b.py"):
        score(setup)


def test_dry_run_lookalike_posing_as_test_run(setup):
    edit_json(setup["published"], "t-06", "manifest.json", lambda m: m.update(dry_run=True))
    assert "t-06: dry_run is True" in problems(setup)


def test_swapped_tasks_in_independent_run(setup):
    def swap(labels):
        a, b = labels["processes"][0], labels["processes"][1]
        a["task_id"], b["task_id"] = b["task_id"], a["task_id"]
    edit_json(setup["published"], "t-03", "labels.json", swap)
    text = problems(setup)
    assert "t-03: process 0 task" in text and "t-03: process 1 task" in text


def test_extra_directory(setup):
    shutil.copytree(setup["published"] / "t-05", setup["published"] / "t-05-again")
    assert "t-05-again: directory not in the protocol table" in problems(setup)


def test_tampered_file_hash(setup):
    path = setup["published"] / "t-02" / "completion.json"
    path.write_text(json.dumps({"owners": False}))
    assert "t-02/completion.json: SHA-256 differs from index.json" in problems(setup)


def test_positive_flag_contradicting_condition(setup):
    edit_json(setup["published"], "t-04", "labels.json", lambda d: d.update(positive=True))
    assert "t-04: positive is True" in problems(setup)


def test_malformed_row_in_last_run_fails_before_scoring(setup):
    path = setup["published"] / "t-06" / "requests.jsonl.gz"
    rows = gzip.decompress(path.read_bytes()).decode() + '{"seq": "x"}\nnot json\n'
    path.write_bytes(gzip.compress(rows.encode(), mtime=0))
    rehash(setup["published"], "t-06", "requests.jsonl.gz")
    text = problems(setup)
    assert "t-06/requests.jsonl.gz line 2: missing or mistyped" in text
    assert "t-06/requests.jsonl.gz line 3: not JSON" in text


def test_many_problems_reported_together(setup):
    pub = setup["published"]
    shutil.rmtree(pub / "t-05")
    (pub / "t-04" / "FAILED.txt").write_text("RuntimeError\n")
    (pub / "t-03" / "notes.json").unlink()
    edit_json(pub, "t-02", "manifest.json", lambda m: m.update(seed=99, background=True,
                                                               started_utc="2026-11-01T00:00:00Z"))
    edit_json(pub, "t-02", "manifest.json",
              lambda m: m["processes"][1].update(launcher="claude", model="x"))
    edit_json(pub, "t-01", "labels.json", lambda d: d.update(expected_subagents=6))
    index = json.loads((pub / "index.json").read_text())
    index["set"] = "development"
    (pub / "index.json").write_text(json.dumps(index))
    text = problems(setup)
    for needle in ("index.json: set is 'development'", "t-05: missing",
                   "t-04: FAILED.txt present", "t-03: files", "t-02: seed",
                   "t-02: background", "t-02: started_utc not later than the freeze",
                   "t-02: process 1 launcher", "t-02: process 1 model", "t-01: subagents"):
        assert needle in text, needle


def test_raw_and_published_copies_score_identically(setup, tmp_path):
    raw_index = publish_fixture(setup["raw"], tmp_path / "raw-published", "development")
    a = score(setup, runs=setup["raw"], set_name="development", out=tmp_path / "a")
    b = score(setup, runs=raw_index, set_name="development", out=tmp_path / "b")
    assert a["development_only"] == b["development_only"]
    for name in ("scores.csv", "evidence.jsonl"):
        assert (tmp_path / "a" / name).read_text() == (tmp_path / "b" / name).read_text()


def test_real_publish_equivalence(tmp_path):
    from swarmtrace.pilot.batch import batch
    from swarmtrace.pilot.publish import ReviewRequired, publish

    rows = [{"run": "e-01", "condition": "single", "seed": 11, "background": False,
             "launchers": ["claude"], "models": ["sonnet"], "tasks": ["owners"]},
            {"run": "e-02", "condition": "lookalike", "seed": 12, "background": False,
             "mix": ["crawler"]}]
    protocol = tmp_path / "protocol.json"
    protocol.write_text(json.dumps({"development_runs": rows, "test_runs": []}))
    raw = tmp_path / "raw"
    results = batch(protocol, "development", raw, parallel=2, dry_run=True, duration=1.0,
                    echo=lambda *a: None)
    assert not any("error" in r for r in results)
    log = raw / "e-02" / "requests.jsonl"
    lines = log.read_text().splitlines()
    first = json.loads(lines[0])
    first["user_agent"] = "\x01 not a fitting agent string"
    log.write_text("\n".join([json.dumps(first), *lines[1:]]) + "\n")
    published, review = tmp_path / "published", tmp_path / "review.json"
    with pytest.raises(ReviewRequired):
        publish(raw, published, "development", protocol, review)
    publish(raw, published, "development", protocol, review,
            hashlib.sha256(review.read_bytes()).hexdigest())
    for row in rows:
        a = pilot.score_items([pilot.read_run(raw / row["run"], row)], STUB)[0]
        b = pilot.score_items([pilot.read_run(published / row["run"], row)], STUB)[0]
        assert a["modes"] == b["modes"] and a["cross_fetch"] == b["cross_fetch"]
        assert a["requests"] == b["requests"] and a["tokens"] == b["tokens"]
    raw_rows = pilot.read_run(raw / "e-02", rows[1])["log"]
    pub_rows = pilot.read_run(published / "e-02", rows[1])["log"]
    changed = {k for r, q in zip(raw_rows, pub_rows) for k in pilot.DETECTOR_FIELDS
               if r[k] != q[k]}
    assert changed == {"user_agent"}


def test_exact_auroc_decisions():
    first, second = (56, 16, 80), (52, 24, 80)
    assert pilot.at_least(first, 8, 10) and pilot.at_least(second, 8, 10)
    assert 2 * first[0] + first[1] == 2 * second[0] + second[1]
    assert not pilot.at_least((55, 17, 80), 8, 10)
    assert pilot._band({"wins": 28, "ties": 0, "pairs": 80})  # 0.35 exactly
    assert pilot._band({"wins": 52, "ties": 0, "pairs": 80})  # 0.65 exactly
    assert not pilot._band({"wins": 52, "ties": 1, "pairs": 80})


def _identity(baselines, hits=1, total=100):
    return {"primary": {"wins": 56, "ties": 16, "pairs": 80, "p_hits": hits, "p_total": total},
            "baselines": baselines}


def test_go_helper():
    beaten = {n: {"primary": {"wins": 40, "ties": 0, "pairs": 80}}
              for n in ("requests", "sessions", "concurrency", "template_multiplicity")}
    assert pilot.go_criterion(_identity(beaten))["go"] is True
    go = pilot.go_criterion(_identity({}))
    assert go["go"] is False and len(go["baselines_unavailable"]) == 4
    tied = dict(beaten, requests={"primary": {"wins": 52, "ties": 24, "pairs": 80}})
    assert pilot.go_criterion(_identity(tied))["go"] is False
    none = dict(beaten, sessions={"primary": {"wins": None, "ties": None, "pairs": None}})
    assert pilot.go_criterion(_identity(none))["baselines_unavailable"] == ["sessions"]
    assert pilot.go_criterion(_identity(beaten, hits=5, total=100))["go"] is False
    assert pilot.go_criterion(_identity(beaten, hits=4, total=81))["go"] is True
    with pytest.raises(ValueError, match="pair count"):
        pilot.go_criterion(_identity(dict(beaten, concurrency={
            "primary": {"wins": 1, "ties": 0, "pairs": 79}})))


def test_identity_mode_passed_to_baselines():
    _, _, with_id = score_events(STUB, [], identity=True)
    _, _, without = score_events(STUB, [], identity=False)
    assert with_id["template_multiplicity"] == 0.0
    assert without["template_multiplicity"] is None


def test_membership_removes_ambiguous_tokens_on_both_sides():
    record = {"run": "r", "group_tokens": ["good", "amb"], "ambiguous": ["amb"],
              "modes": {"identity": {"groups": [["good", "amb"]]}}}
    row = pilot.membership_row(record)
    assert (row["true_positives"], row["named"], row["actual"]) == (1, 1, 1)
    assert row["ambiguous_removed"] == 1
    assert row["true_positives"] / row["named"] == 1.0


LABELS = {"condition": "swarm_peers",
          "processes": [proc(0, group="g"), proc(1, group="g"),
                        proc(2, "scripted", "background", client="browsing_users")]}


@pytest.mark.parametrize("log,expected", [
    ([entry(1, A, "a", "PUT", "/notes/plan", 201, note="plan"),
      entry(2, B, "b", "GET", "/notes/plan", note="plan", writer="a")], True),
    # overwrite only: a second PUT is not a fetch
    ([entry(1, A, "a", "PUT", "/notes/plan", 201, note="plan"),
      entry(2, B, "b", "PUT", "/notes/plan", note="plan")], False),
    # intervening self-write: the served version is the reader's own
    ([entry(1, A, "a", "PUT", "/notes/plan", 201, note="plan"),
      entry(2, B, "b", "PUT", "/notes/plan", note="plan"),
      entry(3, B, "b", "GET", "/notes/plan", note="plan", writer="b")], False),
    # percent-encoded name of the same note, served A's version
    ([entry(1, A, "a", "PUT", "/notes/my-plan", 201, note="my-plan"),
      entry(2, B, "b", "GET", "/notes/my%2Dplan", note="my-plan", writer="a")], True),
    # overlapping requests: whatever the service served is what counts (here B's own)
    ([entry(1, A, "a", "PUT", "/notes/plan", 201, t=0.0, d=1.0, note="plan"),
      entry(2, B, "b", "PUT", "/notes/plan", t=0.2, note="plan"),
      entry(3, B, "b", "GET", "/notes/plan", t=0.5, note="plan", writer="b")], False),
    # alias: A PUT n, B PUT %6E (the same note), B GET n is served B's version
    ([entry(1, A, "a", "PUT", "/notes/n", 201, note="n"),
      entry(2, B, "b", "PUT", "/notes/%6E", note="n"),
      entry(3, B, "b", "GET", "/notes/n", note="n", writer="b")], False),
    # read from a scripted process's address
    ([entry(1, A, "a", "PUT", "/notes/plan", 201, note="plan"),
      entry(2, C, "c", "GET", "/notes/plan", note="plan", writer="a")], False),
    # failed read
    ([entry(1, A, "a", "PUT", "/notes/plan", 201, note="plan"),
      entry(2, B, "b", "GET", "/notes/plan", 404, note="plan")], False),
])
def test_cross_process_fetch(log, expected):
    assert pilot.cross_process_fetch(LABELS, log) is expected


def test_cross_process_fetch_without_record():
    rows = [{k: v for k, v in entry(1, A, "a").items() if k != "note_writer"}]
    assert pilot.cross_process_fetch(LABELS, rows) is None


def test_one_token_on_launched_agent():
    labels = {"condition": "swarm_native", "processes": [proc(0)]}
    assert pilot.one_token_on_launched_agent(labels, [entry(1, A, "a"), entry(2, A, None),
                                                      entry(3, B, "z")])
    assert not pilot.one_token_on_launched_agent(labels, [entry(1, A, "a"), entry(2, A, "b")])
    assert not pilot.one_token_on_launched_agent(labels, [entry(1, A, None)])


def test_freeze_detects_changes(tmp_path):
    src = tmp_path / "src"
    for package in ("fleet", "study", "pilot"):
        (src / package).mkdir(parents=True)
        (src / package / "a.py").write_text("x = 1\n")
    protocol = tmp_path / "protocol.json"
    protocol.write_text("{}")
    record = tmp_path / "freeze.json"
    freeze.write_freeze(protocol, record, root=src)
    with pytest.raises(FileExistsError):
        freeze.write_freeze(protocol, record, root=src)
    freeze.check_freeze(record, protocol, root=src)
    (src / "fleet" / "b.py").write_text("")
    with pytest.raises(ValueError, match="fleet/b.py"):
        freeze.check_freeze(record, protocol, root=src)
    (src / "fleet" / "b.py").unlink()
    protocol.write_text("{ }")
    with pytest.raises(ValueError, match="protocol"):
        freeze.check_freeze(record, protocol, root=src)
