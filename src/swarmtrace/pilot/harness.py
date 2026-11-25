"""Run one pilot: start the service, launch agents or scripted clients against it, record the run.

Each top-level process gets its own loopback address on the service, so every logged request can
be mapped back to the process that made it. That mapping and the group structure are written to
`labels.json`, apart from the request log. The prompts never mention the log or the study.
"""

import gzip
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import numpy as np

from swarmtrace.pilot import lookalikes
from swarmtrace.pilot.service import Service
from swarmtrace.pilot.tasks import TASKS

CONDITIONS = ("single", "swarm_native", "swarm_peers", "independent", "duplicates", "lookalike")
DEFAULT_MODELS = {"claude": "sonnet", "codex": "gpt-5-codex", "fake": "scripted"}
DEFAULT_MIX = ("scheduled_fleet", "crawler", "retry_storm", "many_sessions")
HELP_LINE = ("The service is self-describing at {base_url}/help; you only need curl against "
             "{base_url}. In this environment the only command that you, or any helper you "
             "start, may run is one plain curl invocation at a time: no shell variables, pipes, "
             "loops, scripts or other programs.")


def claude_command(model: str, subagents: bool = False) -> list[str]:
    """Permissions go through --settings because subagents inherit them; --allowedTools is not.

    The subagent tool is called Agent in current releases and Task in older ones. It is allowed
    only when the condition asks the agent to fan out, and explicitly disallowed otherwise.
    """
    allow = ["Bash(curl:*)", "Agent", "Task"] if subagents else ["Bash(curl:*)"]
    settings = json.dumps({"permissions": {"allow": allow}}, separators=(",", ":"))
    deny = [] if subagents else ["--disallowedTools", "Agent", "Task"]
    return ["claude", "-p", "--model", model, "--settings", settings, *deny,
            "--no-session-persistence", "--setting-sources", "", "--strict-mcp-config",
            "--no-chrome", "--output-format", "json"]


def codex_command(model: str, last_message: Path) -> list[str]:
    return ["codex", "exec", "-m", model, "-s", "workspace-write", "-c",
            "sandbox_workspace_write.network_access=true", "--skip-git-repo-check",
            "-o", str(last_message), "-"]


FAKE_AGENT = r'''
import json, re, sys, threading, time, urllib.request
prompt = sys.stdin.read()
if "--hang" in sys.argv:
    time.sleep(3600)
base = re.search(r"http://127\.[0-9.]+:[0-9]+", prompt).group(0)
def call(method, path, token=None, body=None):
    headers = {"User-Agent": "curl/8.0"}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(base + path, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read() or b"null") if "json" in r.headers["Content-Type"] else None
    except Exception:
        return None
def work(part, parts, note):
    token = call("POST", "/session")["token"]
    cols = [c["name"] for c in call("GET", "/collections", token)["collections"]]
    seen = []
    for c in cols[part::parts]:
        docs = call("GET", "/collections/" + c, token)["documents"]
        for d in docs[:2]:
            call("GET", "/docs/" + d["id"], token)
            seen.append(d["id"])
    if note:
        call("PUT", "/notes/" + note, token, "\n".join(seen).encode())
    return seen
call("GET", "/help")
names = re.findall(r"note named ([A-Za-z0-9._<>-]+)", prompt)
note = (names[0] if names else "result").replace("<collection>", "all").rstrip(".")
helpers = re.search(r"across (\d+) parallel", prompt)
stats = None
if helpers:
    n = int(helpers.group(1))
    threads = [threading.Thread(target=work, args=(k, n, None)) for k in range(n)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    work(0, 1, note)
    stats = {"spawned": n, "completed": n}
elif "other agents" in prompt:
    token = call("POST", "/session")["token"]
    call("PUT", "/notes/claim-" + str(time.time_ns()), token, b"taking a share")
    work(0, 1, note)
    time.sleep(0.5)
    for existing in call("GET", "/notes", token)["notes"]:
        call("GET", "/notes/" + existing["name"], token)
else:
    work(0, 1, note)
print(json.dumps({"result": "done", "subagent_stats": stats, "usage": {"input_tokens": 0, "output_tokens": 0}}))
'''


@dataclass(frozen=True)
class Launcher:
    """Builds the argv for one top-level agent process and parses its usage numbers."""

    name: str
    build: Callable[[str, Path, bool], list[str]]
    parse_usage: Callable[[str, str], dict | None]
    native_subagents: bool
    version_argv: tuple[str, ...] | None = None


def result_document(stdout: str, key: str | None = None) -> dict | None:
    """The runner's JSON result: the whole output, else the last non-empty line, else the last
    line holding a JSON object with `key`."""
    text = stdout.strip()
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except ValueError:
        pass
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if lines:
        try:
            data = json.loads(lines[-1])
            if isinstance(data, dict):
                return data
        except ValueError:
            pass
    if key:
        for line in reversed(lines):
            if key in line:
                try:
                    data = json.loads(line)
                except ValueError:
                    continue
                if isinstance(data, dict) and key in data:
                    return data
    return None


VERSION = re.compile(r"[0-9]+(\.[0-9]+)+")


def parse_version(text: str) -> str | None:
    """First version-like token in a runner's --version output."""
    match = VERSION.search(text or "")
    return match.group(0) if match else None


def runner_version(launcher: "Launcher") -> str | None:
    """Run the launcher's executable with --version once; this does not start an agent."""
    if launcher.version_argv is None:
        return "0"
    exe = shutil.which(launcher.version_argv[0])
    if exe is None:
        return None
    try:
        done = subprocess.run([exe, *launcher.version_argv[1:]], capture_output=True, text=True,
                              timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    return parse_version(done.stdout + "\n" + done.stderr)


def parse_claude_usage(stdout: str, stderr: str) -> dict | None:
    data = result_document(stdout, "usage")
    if data is None:
        return None
    usage = data.get("usage") or {}
    return {"input_tokens": usage.get("input_tokens"), "output_tokens": usage.get("output_tokens"),
            "cache_read_input_tokens": usage.get("cache_read_input_tokens"),
            "cache_creation_input_tokens": usage.get("cache_creation_input_tokens"),
            "total_cost_usd": data.get("total_cost_usd"), "num_turns": data.get("num_turns")}


def parse_codex_usage(stdout: str, stderr: str) -> dict | None:
    match = re.search(r"tokens used[:\s]*([\d,]+)", stderr + "\n" + stdout, re.IGNORECASE)
    return {"total_tokens": int(match.group(1).replace(",", ""))} if match else None


def fake_launcher(hang: bool = False) -> Launcher:
    extra = ["--hang"] if hang else []
    return Launcher("fake", lambda model, raw, sub: [sys.executable, "-c", FAKE_AGENT, *extra],
                    parse_claude_usage, native_subagents=True)


LAUNCHERS = {
    "claude": Launcher("claude", lambda model, raw, sub: claude_command(model, sub),
                       parse_claude_usage, native_subagents=True,
                       version_argv=("claude", "--version")),
    "codex": Launcher("codex", lambda model, raw, sub: codex_command(model, raw),
                      parse_codex_usage, native_subagents=False,
                      version_argv=("codex", "--version")),
    "fake": fake_launcher(),
}


def agent_prompt(task_id: str, base_url: str, condition: str, launcher: Launcher,
                 agents: int, subagents: int) -> str:
    text = TASKS[task_id].prompt.format(base_url=base_url)
    if condition in ("single", "duplicates"):
        text += " Work on this alone."
    elif condition == "swarm_native":
        if not launcher.native_subagents:
            raise ValueError(f"{launcher.name} launcher has no subagent tool")
        text += (f" Split the work across {subagents} parallel subagents of your own, each "
                 "taking a share of the collections, then combine their results and write the "
                 "final note yourself.")
    elif condition == "swarm_peers":
        text += (f" {agents - 1} other agents are working on this same task at the same time "
                 "against the same service. Coordinate with them through notes on the service "
                 "so that no work is done twice, and make sure the final note is complete.")
    return text + "\n" + HELP_LINE.format(base_url=base_url) + "\n"


@dataclass
class RunConfig:
    condition: str
    out: Path
    seed: int
    launcher: str | Launcher = "fake"
    model: str | None = None
    launchers: list[str] | None = None
    models: list[str] | None = None
    agents: int = 3
    subagents: int = 3
    tasks: list[str] = field(default_factory=list)
    timeout: float = 900.0
    background: bool = False
    dry_run: bool = False
    mix: list[str] = field(default_factory=lambda: list(DEFAULT_MIX))
    duration: float = 120.0
    stagger: float = 2.0
    jitter: float = 1.0
    batch_parallel: int | None = None


def plan(config: RunConfig, rng: np.random.Generator) -> list[dict]:
    """Processes to start, in order: kind, task id or client name, and group id."""
    if config.condition not in CONDITIONS:
        raise ValueError(f"unknown condition {config.condition!r}; use one of {CONDITIONS}")
    task_ids = list(config.tasks)
    for task_id in task_ids:
        if task_id not in TASKS:
            raise ValueError(f"unknown task {task_id!r}; use one of {sorted(TASKS)}")
    all_ids = sorted(TASKS)
    if config.condition == "lookalike":
        rows = [{"kind": "scripted", "client": name, "group_id": f"p{i}"}
                for i, name in enumerate(config.mix)]
    elif config.condition == "independent":
        if config.agents > len(all_ids) or (task_ids and len(set(task_ids)) < config.agents):
            raise ValueError(f"independent needs {config.agents} distinct tasks")
        if not task_ids:
            task_ids = [all_ids[int(k)] for k in
                        rng.choice(len(all_ids), size=config.agents, replace=False)]
        if len(task_ids) != config.agents or len(set(task_ids)) != config.agents:
            raise ValueError("independent needs one distinct task per agent")
        rows = [{"kind": "agent", "task_id": t, "group_id": f"p{i}"}
                for i, t in enumerate(task_ids)]
    else:
        task_id = task_ids[0] if task_ids else all_ids[int(rng.integers(len(all_ids)))]
        count = config.agents if config.condition in ("swarm_peers", "duplicates") else 1
        group = "g0" if config.condition == "swarm_peers" else None
        rows = [{"kind": "agent", "task_id": task_id, "group_id": group or f"p{i}"}
                for i in range(count)]
    if config.background:
        rows.append({"kind": "scripted", "client": "browsing_users", "group_id": "background"})
    for index, row in enumerate(rows):
        row["index"] = index
    return rows


def _assign_launchers(config: RunConfig, rows: list[dict]) -> None:
    """Set launcher, requested launcher name and model on each agent row."""
    agent_rows = [r for r in rows if r["kind"] == "agent"]
    if config.launchers is not None or config.models is not None:
        names = list(config.launchers or [])
        if len(names) != len(agent_rows) or (config.models and len(config.models) != len(names)):
            raise ValueError("--launchers and --models need one entry per agent "
                             f"({len(agent_rows)})")
        models = list(config.models) if config.models else [None] * len(names)
    else:
        names = [config.launcher] * len(agent_rows)
        models = [config.model] * len(agent_rows)
    for row, name, model in zip(agent_rows, names, models):
        if isinstance(name, Launcher):
            launcher = name
        elif name in LAUNCHERS:
            launcher = LAUNCHERS["fake"] if config.dry_run else LAUNCHERS[name]
        else:
            raise ValueError(f"unknown launcher {name!r}")
        requested = name.name if isinstance(name, Launcher) else name
        if config.condition == "swarm_native" and not (
                LAUNCHERS.get(requested, launcher).native_subagents):
            raise ValueError(f"{requested} launcher has no subagent tool")
        row.update(launcher_obj=launcher, requested_launcher=requested,
                   model=model or DEFAULT_MODELS.get(requested, "default"))


def read_log(log_path: Path) -> list[dict]:
    if not log_path.exists():
        return []
    return [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]


def observed(log: list[dict], addresses: list[str]) -> dict:
    """Per listener address: requests and distinct token ids; per token: addresses it used."""
    counts = {a: {"requests": 0, "tokens": set()} for a in addresses}
    token_addresses: dict[str, set] = {}
    for entry in log:
        slot = counts.setdefault(entry["via"], {"requests": 0, "tokens": set()})
        slot["requests"] += 1
        if entry["token_id"]:
            slot["tokens"].add(entry["token_id"])
            token_addresses.setdefault(entry["token_id"], set()).add(entry["via"])
    result = {a: {"requests": c["requests"], "distinct_token_ids": len(c["tokens"])}
              for a, c in counts.items()}
    result["tokens"] = {t: sorted(a) for t, a in sorted(token_addresses.items())}
    result["ambiguous_tokens"] = sorted(t for t, a in token_addresses.items() if len(a) > 1)
    return result


def subagent_stats(stdout: str) -> tuple[int | None, int | None]:
    """Spawned and completed subagent counts from the runner's JSON result, when reported."""
    data = result_document(stdout, "subagent_stats")
    stats = data.get("subagent_stats") if data else None
    if not isinstance(stats, dict):
        return None, None
    as_int = lambda v: v if isinstance(v, int) and not isinstance(v, bool) else None  # noqa: E731
    return as_int(stats.get("spawned")), as_int(stats.get("completed"))


MIN_DOC_READS = 5


def participation(log: list[dict], rows: list[dict], condition: str, stdouts: dict) -> dict:
    """What each agent process actually did, from the log by listener address and its stdout.

    These are bookkeeping facts for the run record, not a detector: they use the listener
    address and the served note versions, which the detector never sees. A note read counts as
    cross-process when the version served was written by a token of a different agent process;
    tokens seen on more than one address never count.
    """
    agents = {r["address"]: r for r in rows if r["kind"] == "agent"}
    token_addresses: dict[str, set] = {}
    for entry in log:
        if entry.get("token_id"):
            token_addresses.setdefault(entry["token_id"], set()).add(entry["via"])
    owner = {t: next(iter(a)) for t, a in token_addresses.items() if len(a) == 1}
    per = {a: {"index": r["index"], "requests": 0, "doc_reads": 0, "note_writes": 0,
               "cross_process_note_reads": 0} for a, r in agents.items()}
    for entry in log:
        via = entry["via"]
        if via not in per:
            continue
        slot = per[via]
        slot["requests"] += 1
        if not 200 <= entry["status"] < 300:
            continue
        if entry["method"] == "GET" and entry["path"].startswith("/docs/"):
            slot["doc_reads"] += 1
        elif entry["method"] == "PUT" and entry.get("note"):
            slot["note_writes"] += 1
        elif entry["method"] == "GET" and entry.get("note_writer"):
            reader, writer = entry.get("token_id"), entry["note_writer"]
            if (reader in owner and writer in owner and owner[reader] == via
                    and owner[writer] in agents and owner[writer] != via):
                slot["cross_process_note_reads"] += 1
    processes = []
    for address, slot in per.items():
        row = agents[address]
        spawned = completed = None
        if row["launcher_obj"].parse_usage is parse_claude_usage:
            spawned, completed = subagent_stats(stdouts.get(row["index"], ""))
        processes.append({"address": address, **slot, "worked": slot["doc_reads"] >= MIN_DOC_READS,
                          "subagents_spawned": spawned, "subagents_completed": completed})
    cross = sum(p["cross_process_note_reads"] for p in processes)
    group_formed = contaminated = reason = None
    if condition == "swarm_native":
        reported = [p["subagents_completed"] for p in processes
                    if p["subagents_completed"] is not None]
        if reported:
            group_formed = any(n >= 2 for n in reported)
        else:
            reason = "runner reported no subagent statistics"
    elif condition == "swarm_peers":
        group_formed = sum(p["worked"] for p in processes) >= 2 and cross >= 1
    if condition in ("duplicates", "independent"):
        contaminated = cross >= 1
    result = {"processes": processes, "cross_process_note_reads": cross,
              "group_formed": group_formed, "negative_contaminated": contaminated}
    if reason:
        result["group_formed_reason"] = reason
    return result


def launch_policy(launcher_name: str, fan_out: bool) -> str:
    if launcher_name == "claude":
        return ("pre-approved: curl commands; subagent tool: "
                f"{'allowed' if fan_out else 'denied'}; other tools: not pre-approved")
    if launcher_name == "codex":
        return "sandbox: workspace-write in an empty directory; network: allowed"
    return "scripted test agent"


EXPORT_FIELDS = ("seq", "t_start", "t_end", "token_id", "user_agent", "method", "path", "query",
                 "status", "bytes_in", "bytes_out", "write_sha256")


def export(run_dir: Path, out: Path, identity: bool = True) -> int:
    """Write the detector-facing copy of a run's log; returns the number of rows."""
    plain, packed = Path(run_dir) / "requests.jsonl", Path(run_dir) / "requests.jsonl.gz"
    if plain.exists():
        log = read_log(plain)
    elif packed.exists():
        with gzip.open(packed, "rt", encoding="utf-8") as handle:
            log = [json.loads(line) for line in handle if line.strip()]
    else:
        raise FileNotFoundError(f"{run_dir} has neither requests.jsonl nor requests.jsonl.gz")
    rows = 0
    with open(out, "x", encoding="utf-8") as handle:
        for entry in log:
            row = {k: entry[k] for k in EXPORT_FIELDS}
            if not identity:
                row["token_id"] = None
            handle.write(json.dumps(row) + "\n")
            rows += 1
    return rows


def kill_tree(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
    else:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


_AFTER_SPAWN = None  # test hook: called with the record right after a child is registered


def _launch(row, base_url, config, raw, fan_out, procs: dict) -> None:
    """Start one agent process and register it in procs before any further file I/O."""
    i, launcher, model = row["index"], row["launcher_obj"], row["model"]
    prompt = agent_prompt(row["task_id"], base_url, config.condition, launcher,
                          config.agents, config.subagents)
    argv = launcher.build(model, raw / f"{i}-last-message.txt", fan_out)
    argv = [shutil.which(argv[0]) or argv[0], *argv[1:]]
    workdir = Path(tempfile.mkdtemp(prefix="pilot-agent-"))
    files = (open(raw / f"{i}-stdout.txt", "wb"), open(raw / f"{i}-stderr.txt", "wb"))
    record = {"argv": argv, "workdir": workdir, "files": files, "prompt_chars": len(prompt)}
    try:
        record["proc"] = subprocess.Popen(
            argv, cwd=workdir, stdin=subprocess.PIPE, stdout=files[0], stderr=files[1],
            start_new_session=os.name != "nt")
    except BaseException:
        _release(record)
        raise
    record["start"] = time.monotonic()
    procs[i] = record
    if _AFTER_SPAWN is not None:
        _AFTER_SPAWN(record)
    try:
        record["proc"].stdin.write(prompt.encode("utf-8"))
        record["proc"].stdin.close()
    except OSError:
        pass
    (raw / f"{i}-prompt.txt").write_text(prompt, encoding="utf-8")


def _release(record: dict) -> None:
    for handle in record["files"]:
        handle.close()
    shutil.rmtree(record["workdir"], ignore_errors=True)


def run(config: RunConfig) -> Path:
    """Execute one run and write its record; returns the run directory.

    If launching a process fails, every process already started is killed, the service is
    stopped, FAILED.txt (the exception class name only) is written and the error is re-raised.
    """
    out = Path(config.out)
    if out.exists():
        raise FileExistsError(f"{out} already exists")
    rng = np.random.default_rng(config.seed)
    rows = plan(config, rng)
    service_seed = int(rng.integers(0, 2**31))
    _assign_launchers(config, rows)
    out.mkdir(parents=True)
    raw = out / "raw"
    raw.mkdir()
    addresses = [f"127.0.0.{i + 1}" for i in range(len(rows))]
    delays = [i * config.stagger + float(rng.uniform(0, config.jitter)) for i in range(len(rows))]
    client_seeds = rng.integers(0, 2**31, size=len(rows))
    duration = min(config.duration, config.timeout)
    started_at = _utc()
    procs: dict[int, dict] = {}
    fan_out = config.condition == "swarm_native"
    threads: list[threading.Thread] = []
    timed_out = False
    for row, address in zip(rows, addresses):
        row["address"] = address
    runner_versions = {}
    for row in rows:
        launcher = row.get("launcher_obj")
        if launcher is not None and launcher.name not in runner_versions:
            runner_versions[launcher.name] = runner_version(launcher)
    drain_timed_out = False
    try:
        with Service(seed=service_seed, addresses=addresses,
                     log_path=out / "requests.jsonl") as svc:
            t0 = time.monotonic()
            deadline = t0 + config.timeout
            try:
                for row, base_url, delay in zip(rows, svc.base_urls, delays):
                    while time.monotonic() < t0 + delay:
                        time.sleep(0.01)
                    i = row["index"]
                    if row["kind"] == "scripted":
                        stop_at = time.monotonic() + duration - delay
                        thread = threading.Thread(
                            target=lookalikes.CLIENTS[row["client"]], daemon=True,
                            args=(base_url, np.random.default_rng(int(client_seeds[i])),
                                  stop_at))
                        thread.start()
                        threads.append(thread)
                    else:
                        _launch(row, base_url, config, raw, fan_out, procs)
            except BaseException:
                for p in procs.values():
                    kill_tree(p["proc"])
                    _release(p)
                raise
            while True:
                for p in procs.values():
                    if "end" not in p and p["proc"].poll() is not None:
                        p["end"] = time.monotonic()
                if all("end" in p for p in procs.values()):
                    break
                if time.monotonic() >= deadline:
                    timed_out = True
                    for p in procs.values():
                        kill_tree(p["proc"])
                    break
                time.sleep(0.1)
            for p in procs.values():
                p.setdefault("end", time.monotonic())
            for thread in threads:
                thread.join(timeout=max(0.0, deadline - time.monotonic()) + 5)
        drain_timed_out = svc.drain_timed_out
    except BaseException as error:
        (out / "FAILED.txt").write_text(type(error).__name__ + "\n", encoding="utf-8")
        raise
    notes = svc.snapshot()
    ended_at = _utc()
    for p in procs.values():
        _release(p)
    entries, stdouts = [], {}
    for row in rows:
        i = row["index"]
        entry = {"index": i, "kind": row["kind"], "task_id": row.get("task_id"),
                 "client": row.get("client"), "launcher": None, "model": None, "command": None,
                 "launch_policy": None, "exit_code": None, "duration_s": None, "usage": None}
        if i in procs:
            p = procs[i]
            stdouts[i] = (raw / f"{i}-stdout.txt").read_text("utf-8", errors="replace")
            stderr_text = (raw / f"{i}-stderr.txt").read_text("utf-8", errors="replace")
            launcher, model = row["launcher_obj"], row["model"]
            entry.update(
                launcher=launcher.name, requested_launcher=row["requested_launcher"], model=model,
                command=[a if a != FAKE_AGENT else "<fake agent script>" for a in p["argv"]]
                + [f"<prompt on stdin: {p['prompt_chars']} chars>"],
                launch_policy=launch_policy(launcher.name, fan_out),
                exit_code=p["proc"].returncode, duration_s=round(p["end"] - p["start"], 2),
                usage=launcher.parse_usage(stdouts[i], stderr_text))
            if config.dry_run and row["requested_launcher"] in LAUNCHERS:
                entry["planned_command"] = LAUNCHERS[row["requested_launcher"]].build(
                    model, raw / f"{i}-last-message.txt", fan_out)
                entry["planned_launch_policy"] = launch_policy(row["requested_launcher"], fan_out)
        entries.append(entry)
    agents_in_group: dict[str, int] = {}
    for row in rows:
        if row["kind"] == "agent":
            agents_in_group[row["group_id"]] = agents_in_group.get(row["group_id"], 0) + 1
    positive = (any(n >= 2 for n in agents_in_group.values())
                or (config.condition == "swarm_native" and config.subagents >= 2))
    manifest = {
        "run_id": out.name, "condition": config.condition, "seed": config.seed,
        "service_seed": service_seed, "started_utc": started_at, "ended_utc": ended_at,
        "timeout_s": config.timeout, "timeout_hit": timed_out, "dry_run": config.dry_run,
        "batch_parallel": config.batch_parallel, "runner_versions": runner_versions,
        "drain_timed_out": drain_timed_out,
        "agents": (config.agents if config.condition in ("swarm_peers", "independent",
                                                          "duplicates") else None),
        "subagents": config.subagents if config.condition == "swarm_native" else None,
        "mix": list(config.mix) if config.condition == "lookalike" else None,
        "background": config.background, "processes": entries,
    }
    log = read_log(out / "requests.jsonl")
    labels = {
        "run_id": out.name, "condition": config.condition, "positive": positive,
        "positive_means": "assigned to a coordination condition by the harness",
        "processes": [{"index": r["index"], "address": r["address"], "kind": r["kind"],
                       "launcher": r["launcher_obj"].name if r["kind"] == "agent" else "scripted",
                       "requested_launcher": r.get("requested_launcher"),
                       "model": r.get("model"),
                       "task_id": r.get("task_id"), "client": r.get("client"),
                       "group_id": r["group_id"],
                       "native_subagents": (config.subagents if config.condition == "swarm_native"
                                            and r["kind"] == "agent" else 0)}
                      for r in rows],
        "expected_subagents": config.subagents if fan_out else None,
        "observed": observed(log, [r["address"] for r in rows]),
        "participation": participation(log, rows, config.condition, stdouts),
    }
    task_ids = sorted({r["task_id"] for r in rows if r.get("task_id")})
    completion = {t: TASKS[t].done(notes) for t in task_ids}
    for name, data in (("manifest", manifest), ("labels", labels), ("notes", notes),
                       ("completion", completion)):
        (out / f"{name}.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    if drain_timed_out:
        (out / "FAILED.txt").write_text("DrainTimeout\n", encoding="utf-8")
    return out
