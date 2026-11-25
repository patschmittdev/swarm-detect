"""Write the publishable record of a finished batch.

Each published run holds the service log (gzip, fixed mtime), labels, notes, completion and a
manifest. Every published JSON file follows an explicit schema: unknown keys are dropped and
counted, and values that do not fit their field's pattern become "[redacted]" and are counted.
Agent-chosen values (note names, search queries, user agents) stay readable, because the detector
reads them and scores must be reproducible from the published files; instead, every distinct
such value is written to a review file, and publishing proceeds only when the caller passes the
SHA-256 of that file. Any string holding a drive-letter path, the home directory or the login
name, also after percent-decoding, stops the publish.
"""

import gzip
import hashlib
import json
import os
import re
import shutil
from collections import Counter
from pathlib import Path
from urllib.parse import unquote, unquote_plus

from swarmtrace.pilot.harness import CONDITIONS, LAUNCHERS, launch_policy
from swarmtrace.pilot.lookalikes import CLIENTS, USER_AGENTS
from swarmtrace.pilot.tasks import TASKS

PUBLISH_SETS = ("development", "test")
RUN_FILES = ("requests.jsonl", "labels.json", "manifest.json", "notes.json", "completion.json")
PUBLISHED = ("requests.jsonl.gz", "labels.json", "notes.json", "completion.json",
             "manifest.json")
REDACTED = "[redacted]"
DRIVE_PATH = re.compile(r"(?<![A-Za-z])[A-Za-z]:[\\/]")
SAFE_ID = re.compile(r"[A-Za-z0-9._-]{1,64}")
SEGMENT = re.compile(r"[A-Za-z0-9._-]{1,64}")
QUERY_VALUE = re.compile(r"[A-Za-z0-9 ._+%-]{0,80}")
AGENT = re.compile(r"(curl|python-urllib|Python-urllib)/[0-9.]+")
HEX12, HEX64 = re.compile(r"[0-9a-f]{12}"), re.compile(r"[0-9a-f]{64}")
VIA = re.compile(r"127\.\d{1,3}\.\d{1,3}\.\d{1,3}")
UTC = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00")
VERSION = re.compile(r"[0-9]+(\.[0-9]+)*")
GROUP = re.compile(r"g\d+|p\d+|background")
METHODS = {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS", "CONNECT", "TRACE"}
USAGE_KEYS = ("input_tokens", "output_tokens", "cache_read_input_tokens",
              "cache_creation_input_tokens", "total_tokens", "total_cost_usd", "num_turns")
POLICIES = {launch_policy(name, fan_out) for name in LAUNCHERS for fan_out in (True, False)}
POSITIVE_MEANS = {"assigned to a coordination condition by the harness"}
GROUP_REASONS = {"runner reported no subagent statistics"}


class ReviewRequired(Exception):
    """The review file was written; publish again with its SHA-256."""


# Validators return True when a value may be published as it is.

def _int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _bool(v) -> bool:
    return isinstance(v, bool)


def _opt(check):
    return lambda v: v is None or check(v)


def _match(pattern: re.Pattern):
    return lambda v: isinstance(v, str) and bool(pattern.fullmatch(v))


def _one_of(values):
    values = set(values)
    return lambda v: isinstance(v, str) and v in values


def path_ok(path) -> bool:
    if not isinstance(path, str) or not path.startswith("/") or len(path) > 200:
        return False
    if path == "/":
        return True
    parts = path[1:].rstrip("/").split("/")
    return all(SEGMENT.fullmatch(unquote(p)) for p in parts)


def query_ok(query) -> bool:
    if query == "":
        return True
    return (isinstance(query, str) and query.startswith("q=")
            and bool(QUERY_VALUE.fullmatch(query[2:])))


def agent_ok(value) -> bool:
    return isinstance(value, str) and (bool(AGENT.fullmatch(value)) or value in USER_AGENTS)


def _schemas(launchers: set, models: set) -> dict:
    launcher = _one_of(launchers)
    model = _one_of(models)
    task, client = _one_of(TASKS), _one_of(CLIENTS)
    usage = ("dict", {k: _opt(_num) for k in USAGE_KEYS})
    row = {
        "seq": _int, "t_start": _num, "t_end": _num, "via": _match(VIA), "peer_port": _int,
        "token_id": _opt(_match(HEX12)), "auth": _one_of({"none", "invalid", "ok"}),
        "user_agent": agent_ok, "method": _one_of(METHODS), "path": path_ok, "query": query_ok,
        "status": _int, "bytes_in": _int, "bytes_out": _int,
        "write_sha256": _opt(_match(HEX64)), "note": _opt(_match(SEGMENT)),
        "note_version": _opt(_int), "note_writer": _opt(_match(HEX12)),
    }
    manifest = {
        "run_id": _match(SAFE_ID), "condition": _one_of(CONDITIONS), "seed": _int,
        "service_seed": _int, "started_utc": _match(UTC), "ended_utc": _match(UTC),
        "timeout_s": _num, "timeout_hit": _bool, "dry_run": _bool, "batch_parallel": _opt(_int),
        "background": _bool, "drain_timed_out": _bool, "agents": _opt(_int),
        "subagents": _opt(_int), "mix": ("optional", ("list", client)),
        "runner_versions": ("map", launcher, _opt(_match(VERSION))),
        "processes": ("list", {
            "index": _int, "kind": _one_of({"agent", "scripted"}), "launcher": _opt(launcher),
            "model": _opt(model), "task_id": _opt(task), "client": _opt(client),
            "requested_launcher": _opt(launcher), "exit_code": _opt(_int),
            "duration_s": _opt(_num),
            "launch_policy": _opt(_one_of(POLICIES)), "usage": ("optional", usage)}),
    }
    labels = {
        "run_id": _match(SAFE_ID), "condition": _one_of(CONDITIONS), "positive": _bool,
        "positive_means": _one_of(POSITIVE_MEANS), "expected_subagents": _opt(_int),
        "processes": ("list", {
            "index": _int, "address": _match(VIA), "kind": _one_of({"agent", "scripted"}),
            "launcher": _one_of(launchers | {"scripted"}), "requested_launcher": _opt(launcher),
            "model": _opt(model), "task_id": _opt(task), "client": _opt(client),
            "group_id": _match(GROUP), "native_subagents": _int}),
        "observed": ("observed", None),
        "participation": ("dict", {
            "processes": ("list", {
                "address": _match(VIA), "index": _int, "requests": _int, "doc_reads": _int,
                "note_writes": _int, "cross_process_note_reads": _int, "worked": _bool,
                "subagents_spawned": _opt(_int), "subagents_completed": _opt(_int)}),
            "cross_process_note_reads": _int, "group_formed": _opt(_bool),
            "negative_contaminated": _opt(_bool),
            "group_formed_reason": _one_of(GROUP_REASONS)}),
    }
    notes = ("list", {"name": _match(SEGMENT), "length": _int, "sha256": _match(HEX64),
                      "created_by": _match(HEX12), "last_written_by": _match(HEX12),
                      "updates": _int})
    completion = ("map", task, _bool)
    return {"row": row, "manifest.json": ("dict", manifest), "labels.json": ("dict", labels),
            "notes.json": notes, "completion.json": completion}


OBSERVED_ADDRESS = {"requests": _int, "distinct_token_ids": _int}


class _Cleaner:
    """Applies a schema, counting redactions and dropped keys per file."""

    def __init__(self, file: str, redactions: Counter, dropped: Counter):
        self.file, self.redactions, self.dropped = file, redactions, dropped

    def apply(self, value, schema, field: str):
        if isinstance(schema, dict):
            schema = ("dict", schema)
        if callable(schema):
            if schema(value):
                return value
            self.redactions[f"{self.file}:{field}"] += 1
            return "/" + REDACTED if field == "path" else REDACTED
        kind, spec = schema[0], schema[1]
        if kind == "optional":
            return None if value is None else self.apply(value, spec, field)
        if kind == "list":
            if not isinstance(value, list):
                return self.apply(value, lambda v: False, field)
            return [self.apply(v, spec, field) for v in value]
        if kind == "map":
            if not isinstance(value, dict):
                return self.apply(value, lambda v: False, field)
            out = {}
            for k, v in value.items():
                if spec(k):
                    out[k] = self.apply(v, schema[2], field)
                else:
                    self.dropped[self.file] += 1
            return out
        if kind == "observed":
            return self._observed(value, field)
        if not isinstance(value, dict):
            return self.apply(value, lambda v: False, field)
        out = {}
        for k, v in value.items():
            if k in spec:
                out[k] = self.apply(v, spec[k], f"{field}.{k}" if field else k)
            else:
                self.dropped[self.file] += 1
        return out

    def _observed(self, value, field):
        out = {}
        for k, v in (value or {}).items():
            if k == "tokens":
                out[k] = self.apply(v, ("map", _match(HEX12), ("list", _match(VIA))), k)
            elif k == "ambiguous_tokens":
                out[k] = self.apply(v, ("list", _match(HEX12)), k)
            elif VIA.fullmatch(k):
                out[k] = self.apply(v, ("dict", OBSERVED_ADDRESS), "observed.address")
            else:
                self.dropped[self.file] += 1
        return out


def _forbidden() -> list[str]:
    needles = [str(Path.home()), str(Path.home()).replace("\\", "/")]
    for key in ("USERNAME", "USER"):
        name = os.environ.get(key, "")
        if len(name) >= 3:
            needles.append(name)
    return [n.lower() for n in needles if n]


def _strings(value, field: str = ""):
    if isinstance(value, str):
        yield field, value
    elif isinstance(value, dict):
        for k, v in value.items():
            path = f"{field}.{k}" if field else str(k)
            yield path, str(k)
            yield from _strings(v, path)
    elif isinstance(value, list):
        for i, v in enumerate(value):
            yield from _strings(v, f"{field}[{i}]")


def check_clean(name: str, value, needles: list[str]) -> None:
    """Raise if any string in value holds a drive path, the home directory or the login name."""
    for field, text in _strings(value):
        for candidate in (text, unquote_plus(text)):
            lowered = candidate.lower()
            if DRIVE_PATH.search(candidate) or any(n in lowered for n in needles):
                raise ValueError(f"{name}: field {field or '<value>'} holds a local path or "
                                 "user name")


def _complete(run_dir: Path) -> bool:
    return all((run_dir / n).exists() for n in RUN_FILES) and not (run_dir / "FAILED.txt").exists()


def protocol_models(protocol: Path) -> set[str]:
    data = json.loads(Path(protocol).read_text(encoding="utf-8"))
    models = {"scripted"}
    for key in ("development_runs", "test_runs"):
        for row in data.get(key, []):
            models.update(row.get("models") or [])
    return models


def review_values(logs: dict[str, list[dict]], notes: dict[str, list[dict]]) -> dict:
    """Every distinct agent-written value by field, with counts, across the runs."""
    fields = {"note_name": Counter(), "notes_path_segment": Counter(),
              "search_query": Counter(), "user_agent": Counter()}
    for rows in logs.values():
        for row in rows:
            path = row.get("path") if isinstance(row.get("path"), str) else ""
            if path.startswith("/notes/"):
                for part in path[len("/notes/"):].split("/"):
                    fields["notes_path_segment"][unquote(part)] += 1
            if row.get("note") is not None:
                fields["note_name"][str(row["note"])] += 1
            if path == "/search":
                fields["search_query"][unquote_plus(str(row.get("query", "")))] += 1
            fields["user_agent"][str(row.get("user_agent"))] += 1
    for run_notes in notes.values():
        for note in run_notes:
            fields["note_name"][str(note.get("name"))] += 1
    return {name: [{"value": v, "count": n} for v, n in sorted(counter.items())]
            for name, counter in fields.items()}


def _dumps(data) -> bytes:
    return (json.dumps(data, indent=2, sort_keys=True) + "\n").encode("utf-8")


def publish(runs: Path, out: Path, set_name: str, protocol: Path, review_out: Path,
            reviewed_sha256: str | None = None) -> dict:
    """Publish every run under `runs` into `out` (which must be new or empty).

    The review file is always written first. Without a matching `reviewed_sha256` nothing is
    published and ReviewRequired is raised.
    """
    runs, out, review_out = Path(runs), Path(out), Path(review_out)
    if set_name not in PUBLISH_SETS:
        raise ValueError(f"set must be one of {PUBLISH_SETS}")
    if review_out.resolve().is_relative_to(out.resolve()):
        raise ValueError("the review file must be outside the output directory")
    if out.exists() and any(out.iterdir()):
        raise FileExistsError(f"{out} is not empty")
    sources = sorted(p for p in runs.iterdir() if p.is_dir() and not p.name.startswith("."))
    for source in sources:
        if not SAFE_ID.fullmatch(source.name):
            raise ValueError(f"run id {source.name!r} must match [A-Za-z0-9._-]{{1,64}}")
        if not _complete(source):
            raise ValueError(f"{source.name} is not a complete run (missing files or FAILED.txt)")
    schemas = _schemas(set(LAUNCHERS), protocol_models(protocol))
    needles = _forbidden()
    staged_runs, raw_logs, raw_notes = {}, {}, {}
    for source in sources:
        redactions, dropped = Counter(), Counter()
        load = lambda n: json.loads((source / n).read_text(encoding="utf-8"))  # noqa: E731
        docs = {}
        for name in ("manifest.json", "labels.json", "notes.json", "completion.json"):
            data = load(name)
            if name == "notes.json":
                raw_notes[source.name] = data
            docs[name] = _Cleaner(name, redactions, dropped).apply(data, schemas[name], "")
            check_clean(f"{source.name}/{name}", docs[name], needles)
        rows = [json.loads(x) for x in
                (source / "requests.jsonl").read_text(encoding="utf-8").splitlines() if x]
        raw_logs[source.name] = rows
        cleaner = _Cleaner("requests.jsonl", redactions, dropped)
        lines = []
        for number, row in enumerate(rows, 1):
            where = f"{source.name}/requests.jsonl line {number}"
            check_clean(where, {k: row.get(k) for k in ("path", "query", "user_agent", "note")},
                        needles)
            clean = cleaner.apply(row, ("dict", schemas["row"]), "")
            check_clean(where, clean, needles)
            lines.append(json.dumps(clean) + "\n")
        staged_runs[source.name] = (docs, "".join(lines).encode("utf-8"), redactions, dropped,
                                    len(rows))
    values = review_values(raw_logs, raw_notes)
    review_bytes = _dumps({"set": set_name, "runs": sorted(staged_runs), "fields": values})
    review_sha = hashlib.sha256(review_bytes).hexdigest()
    review_out.parent.mkdir(parents=True, exist_ok=True)
    review_out.write_bytes(review_bytes)
    if reviewed_sha256 != review_sha:
        raise ReviewRequired(
            f"wrote {sum(len(v) for v in values.values())} distinct agent-written values to "
            f"{review_out}; read them, then publish again with --reviewed-sha256 {review_sha}")
    out.mkdir(parents=True, exist_ok=True)
    index = {"set": set_name, "review_sha256": review_sha,
             "values_reviewed": sum(len(v) for v in values.values()), "runs": []}
    try:
        for run_id, (docs, log_bytes, redactions, dropped, count) in staged_runs.items():
            run_dir = out / run_id
            run_dir.mkdir()
            for name, data in docs.items():
                (run_dir / name).write_bytes(_dumps(data))
            with open(run_dir / "requests.jsonl.gz", "wb") as raw:
                with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as handle:
                    handle.write(log_bytes)
            labels, manifest = docs["labels.json"], docs["manifest.json"]
            index["runs"].append({
                "run": run_id, "condition": labels.get("condition"), "seed": manifest.get("seed"),
                "positive": labels.get("positive"), "requests": count,
                "redactions": dict(sorted(redactions.items())),
                "dropped_keys": dict(sorted(dropped.items())),
                "files": {n: hashlib.sha256((run_dir / n).read_bytes()).hexdigest()
                          for n in PUBLISHED}})
        (out / "index.json").write_bytes(_dumps(index))
    except BaseException:
        shutil.rmtree(out, ignore_errors=True)
        raise
    return index
