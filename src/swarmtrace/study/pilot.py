"""Score one set of pilot runs with the frozen detector, as the protocol's endpoints specify.

Scoring needs the freeze file and checks every hash against it. The test set is read only from a
published directory: its index.json, every listed file hash, the exact file set of every run,
the run ids, the assignment of every process and every log row are validated before the
detector sees any run, and every problem found is reported at once. The detector sees the
detector-facing fields of each log, once with session identity and once with token_id nulled.
Ground truth is read from labels.json and from the harness-only log fields (listener address
and the served-version record), which only this module sees. All decisions are made in integer
arithmetic on pair counts and permutation counts; floats are for display only.
"""

import csv
import gzip
import hashlib
import json
import math
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from swarmtrace.study import stats
from swarmtrace.study.fleet_api import BASELINES, Fleet, default_fleet, score_events
from swarmtrace.study.freeze import (
    PACKAGE_ROOT,
    SCORING_PACKAGES,
    check_freeze,
    source_hashes,
)

SETS = {"development": "development_runs", "test": "test_runs"}
MODES = ("identity", "no_identity")
POSITIVE_CONDITIONS = ("swarm_native", "swarm_peers")
PRIMARY_NEGATIVES = ("independent", "duplicates")
DETECTOR_FIELDS = ("seq", "t_start", "t_end", "token_id", "user_agent", "method", "path",
                   "query", "status", "bytes_in", "bytes_out", "write_sha256")
PUBLISHED_FILES = ("requests.jsonl.gz", "labels.json", "notes.json", "completion.json",
                   "manifest.json")
RAW_LOG = "requests.jsonl"
JSON_FILES = ("labels.json", "manifest.json", "notes.json", "completion.json")
RESULTS = PACKAGE_ROOT.parents[1] / "benchmarks" / "agent-pilot" / "results"
DEVELOPMENT_LABEL = "development runs: not a result"
EXCHANGEABILITY = ("The exact p-value assumes runs are exchangeable under the null; conditions "
                   "ran in blocks, all swarm_native runs use one runner and machine load varies, "
                   "so it is conditional on that assumption.")
# go criterion: AUROC >= 0.80, i.e. (2W + T) / (2N) >= 8 / 10; p < 1 / 20
GO_NUM, GO_DEN = 8, 10
GO_P_DEN = 20
# prediction 1: 0.35 <= AUROC <= 0.65; prediction 5: drop >= 0.10 (all as num / 100)
P1_LOW, P1_HIGH, P5_DROP = 35, 65, 10
P2_MIN_RUNS = 3
P3_MIN_RUNS = 4
P4_MIN_FLAGGED = 1


def _int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _num(v) -> bool:
    return (isinstance(v, (int, float)) and not isinstance(v, bool)) and math.isfinite(v)


def _str(v) -> bool:
    return isinstance(v, str)


def _opt_str(v) -> bool:
    return v is None or isinstance(v, str)


ROW_TYPES = {"seq": _int, "t_start": _num, "t_end": _num, "token_id": _opt_str,
             "user_agent": _str, "method": _str, "path": _str, "query": _str, "status": _int,
             "bytes_in": _int, "bytes_out": _int, "write_sha256": _opt_str, "via": _str}
OPTIONAL_TYPES = {"note": _opt_str, "note_writer": _opt_str,
                  "note_version": lambda v: v is None or _int(v)}


class Inputs:
    """SHA-256 of every input file read, keyed by its path relative to the runs directory."""

    def __init__(self):
        self.hashes: dict[str, str] = {}

    def read_bytes(self, path: Path, key: str) -> bytes:
        data = Path(path).read_bytes()
        self.hashes[key] = hashlib.sha256(data).hexdigest()
        return data

    def read_json(self, path: Path, key: str):
        return json.loads(self.read_bytes(path, key).decode("utf-8"))


def parse_log(name: str, data: bytes, problems: list[str], where: str) -> list[dict]:
    """Rows of a log, checking JSON validity, required fields and types; problems are appended."""
    if name.endswith(".gz"):
        try:
            data = gzip.decompress(data)
        except OSError:
            problems.append(f"{where}: not a gzip file")
            return []
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        problems.append(f"{where}: not UTF-8")
        return []
    rows = []
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError:
            problems.append(f"{where} line {number}: not JSON")
            continue
        if not isinstance(row, dict):
            problems.append(f"{where} line {number}: not an object")
            continue
        bad = [k for k, ok in ROW_TYPES.items() if k not in row or not ok(row[k])]
        bad += [k for k, ok in OPTIONAL_TYPES.items() if k in row and not ok(row[k])]
        if bad:
            problems.append(f"{where} line {number}: missing or mistyped {', '.join(bad)}")
            continue
        rows.append(row)
    return rows


def detector_rows(log: list[dict], identity: bool) -> list[dict]:
    """The detector-facing allowlist of every row; token_id nulled without identity."""
    rows = []
    for entry in log:
        row = {k: entry[k] for k in DETECTOR_FIELDS}
        if not identity:
            row["token_id"] = None
        rows.append(row)
    return rows


def agent_processes(labels: dict) -> list[dict]:
    return sorted((p for p in labels["processes"] if p["kind"] == "agent"),
                  key=lambda p: p["index"])


def group_addresses(labels: dict) -> set[str]:
    """Addresses of the coordinated group's processes; empty for negatives.

    Agent processes sharing a group_id with at least one other agent process form the group; for
    swarm_native the launched agent's address. Scripted processes never count.
    """
    agents = agent_processes(labels)
    if labels["condition"] == "swarm_native":
        return {p["address"] for p in agents}
    counts: dict[str, int] = {}
    for p in agents:
        counts[p["group_id"]] = counts.get(p["group_id"], 0) + 1
    return {p["address"] for p in agents if counts[p["group_id"]] >= 2}


def tokens_by_address(log: list[dict]) -> dict[str, set[str]]:
    seen: dict[str, set[str]] = {}
    for entry in log:
        if entry.get("token_id"):
            seen.setdefault(entry["via"], set()).add(entry["token_id"])
    return seen


def ambiguous_tokens(labels: dict) -> set[str]:
    return set((labels.get("observed") or {}).get("ambiguous_tokens") or [])


def group_tokens(labels: dict, log: list[dict]) -> set[str]:
    """Tokens seen on the group's addresses (ambiguous tokens not yet removed)."""
    seen = tokens_by_address(log)
    return set().union(*(seen.get(a, set()) for a in group_addresses(labels)))


def _ok(entry: dict) -> bool:
    return 200 <= int(entry["status"]) < 300


def one_token_on_launched_agent(labels: dict, log: list[dict]) -> bool:
    """Every row with a token on the launched agent's address carries one and the same token."""
    addresses = {p["address"] for p in agent_processes(labels)}
    tokens = {e["token_id"] for e in log if e["via"] in addresses and e.get("token_id")}
    return len(tokens) == 1


def cross_process_fetch(labels: dict, log: list[dict]) -> bool | None:
    """A successful GET of a note by name whose served version was written by a token of a
    different agent process than the reader's, from the harness's served-version record.

    A token's process is the agent listener address its rows arrive on. None when the log has no
    served-version record (no row carries ``note_writer``).
    """
    if not any("note_writer" in e for e in log):
        return None
    agents = {p["address"] for p in agent_processes(labels)}
    homes: dict[str, set[str]] = {}
    for e in log:
        if e.get("token_id") and e["via"] in agents:
            homes.setdefault(e["token_id"], set()).add(e["via"])
    for e in log:
        if e["method"] != "GET" or not _ok(e) or e.get("note") is None:
            continue
        writer, reader = e.get("note_writer"), e.get("token_id")
        if not writer or not reader or writer == reader or e["via"] not in agents:
            continue
        writer_home = homes.get(writer, set())
        if writer_home and e["via"] not in writer_home:
            return True
    return False


def expected_positive(condition: str) -> bool:
    return condition in POSITIVE_CONDITIONS


def _table_problems(row: dict, manifest: dict, labels: dict, completion, notes) -> list[str]:
    run, problems = row["run"], []

    def check(what, actual, expected):
        if actual != expected:
            problems.append(f"{run}: {what} is {actual!r}, protocol says {expected!r}")

    check("labels run_id", labels.get("run_id"), run)
    check("manifest run_id", manifest.get("run_id"), run)
    check("manifest condition", manifest.get("condition"), row["condition"])
    check("labels condition", labels.get("condition"), row["condition"])
    check("positive", labels.get("positive"), expected_positive(row["condition"]))
    check("seed", manifest.get("seed"), row["seed"])
    check("background", manifest.get("background"), bool(row.get("background")))
    check("dry_run", manifest.get("dry_run"), False)
    if not isinstance(completion, dict):
        problems.append(f"{run}: completion.json is not an object")
    if not isinstance(notes, list):
        problems.append(f"{run}: notes.json is not a list")
    procs = sorted(manifest.get("processes") or [], key=lambda p: p.get("index", 0))
    agents = [p for p in procs if p.get("kind") == "agent"]
    label_agents = agent_processes(labels)
    if row["condition"] == "lookalike":
        scripted = [p.get("client") for p in sorted(labels["processes"], key=lambda p: p["index"])
                    if p["kind"] == "scripted" and p.get("group_id") != "background"]
        check("agent processes", len(label_agents) + len(agents), 0)
        check("mix", scripted, list(row["mix"]))
        return problems
    launchers, models = list(row["launchers"]), list(row["models"])
    tasks = list(row.get("tasks") or [])
    if len(tasks) == 1 and len(launchers) > 1:
        tasks = tasks * len(launchers)
    check("agent process count", len(agents), len(launchers))
    check("labels agent process count", len(label_agents), len(launchers))
    for i in range(min(len(agents), len(launchers))):
        check(f"process {i} launcher", agents[i].get("launcher"), launchers[i])
        check(f"process {i} model", agents[i].get("model"), models[i])
    for i in range(min(len(label_agents), len(tasks))):
        check(f"process {i} task", label_agents[i].get("task_id"), tasks[i])
        if agents[i:i + 1] and "task_id" in agents[i]:
            check(f"process {i} manifest task", agents[i].get("task_id"), tasks[i])
    if row["condition"] == "swarm_native":
        check("subagents", labels.get("expected_subagents"), int(row.get("subagents", 3)))
    return problems


def load_inventory(runs: Path, table: list[dict], set_name: str, frozen_utc: str | None,
                   inputs: Inputs, published_only: bool) -> tuple[list[dict], dict | None]:
    """Every row's run, fully validated against the table; raises once listing every problem."""
    runs = Path(runs)
    problems: list[str] = []
    index = None
    names = [row["run"] for row in table]
    for name in sorted({n for n in names if names.count(n) > 1}):
        problems.append(f"{name}: listed more than once in the protocol table")
    if (runs / "index.json").exists():
        index = inputs.read_json(runs / "index.json", "index.json")
        if index.get("set") != set_name:
            problems.append(f"index.json: set is {index.get('set')!r}, expected {set_name!r}")
    elif published_only:
        raise ValueError(f"{runs} is not a published directory (no index.json)")
    present = sorted(p.name for p in runs.iterdir() if p.is_dir()) if runs.is_dir() else []
    for extra in sorted(set(present) - set(names)):
        problems.append(f"{extra}: directory not in the protocol table")
    listed = {e.get("run"): e for e in (index or {}).get("runs", [])}
    if index is not None:
        for extra in sorted(set(listed) - set(names)):
            problems.append(f"{extra}: listed in index.json but not in the protocol table")
    frozen = datetime.fromisoformat(frozen_utc.replace("Z", "+00:00")) if frozen_utc else None
    items = []
    for row in table:
        run, run_dir = row["run"], runs / row["run"]
        if not run_dir.is_dir():
            problems.append(f"{run}: missing")
            continue
        files = sorted(p.name for p in run_dir.iterdir())
        if "FAILED.txt" in files:
            problems.append(f"{run}: FAILED.txt present")
        if index is not None:
            entry = listed.get(run)
            if entry is None:
                problems.append(f"{run}: not listed in index.json")
                continue
            if entry.get("condition") != row["condition"] or entry.get("seed", row["seed"]) != \
                    row["seed"]:
                problems.append(f"{run}: index.json condition or seed differs from the table")
            expected = sorted((entry.get("files") or {}).keys())
            if files != expected:
                problems.append(f"{run}: files {files} differ from index.json {expected}")
            if set(expected) != set(PUBLISHED_FILES):
                problems.append(f"{run}: index.json lists {expected}, expected "
                                f"{sorted(PUBLISHED_FILES)}")
        else:
            needed = set(JSON_FILES) | {RAW_LOG}
            if not needed <= set(files):
                problems.append(f"{run}: missing files {sorted(needed - set(files))}")
        log_name = "requests.jsonl.gz" if "requests.jsonl.gz" in files else RAW_LOG
        if not all(n in files for n in (*JSON_FILES, log_name)):
            continue
        docs = {}
        for name in (*JSON_FILES, log_name):
            data = inputs.read_bytes(run_dir / name, f"{run}/{name}")
            if index is not None:
                listed_sha = (listed[run].get("files") or {}).get(name)
                if hashlib.sha256(data).hexdigest() != listed_sha:
                    problems.append(f"{run}/{name}: SHA-256 differs from index.json")
            if name == log_name:
                docs["log"] = parse_log(name, data, problems, f"{run}/{name}")
            else:
                try:
                    docs[name] = json.loads(data.decode("utf-8"))
                except (UnicodeDecodeError, ValueError):
                    problems.append(f"{run}/{name}: not valid JSON")
        if any(n not in docs for n in JSON_FILES):
            continue
        manifest, labels = docs["manifest.json"], docs["labels.json"]
        try:
            problems.extend(_table_problems(row, manifest, labels, docs["completion.json"],
                                            docs["notes.json"]))
        except (KeyError, TypeError, AttributeError):
            problems.append(f"{run}: manifest.json or labels.json lacks required fields")
            continue
        if set_name == "test":
            try:
                when = datetime.fromisoformat(str(manifest.get("started_utc")).replace(
                    "Z", "+00:00"))
                if frozen is None or not when > frozen:
                    problems.append(f"{run}: started_utc not later than the freeze")
            except ValueError:
                problems.append(f"{run}: started_utc missing or unreadable")
        items.append({"row": row, "dir": run_dir, "manifest": manifest, "labels": labels,
                      "completion": docs["completion.json"], "log": docs["log"]})
    if problems:
        raise ValueError("inventory does not match the protocol table:\n  " + "\n  ".join(problems))
    return items, index


def score_run(item: dict, fleet: Fleet, scratch: Path) -> dict:
    """Per-run record: facts from the harness files and the detector's output in both modes."""
    run_dir, labels, manifest = item["dir"], item["labels"], item["manifest"]
    completion, log = item["completion"], item["log"]
    name = run_dir.name
    participation = labels.get("participation") or {}
    record = {
        "run": name, "condition": labels["condition"], "positive": bool(labels["positive"]),
        "timeout_hit": bool(manifest.get("timeout_hit")),
        "tasks": len(completion), "tasks_completed": sum(bool(v) for v in completion.values()),
        "requests": len(log),
        "tokens": len({e["token_id"] for e in log if e.get("token_id")}),
        "group_tokens": sorted(group_tokens(labels, log)),
        "task_ids": sorted({p.get("task_id") for p in agent_processes(labels)
                            if p.get("task_id")}),
        "ambiguous": sorted(ambiguous_tokens(labels)),
        "group_formed": participation.get("group_formed"),
        "negative_contaminated": participation.get("negative_contaminated"),
        "one_token": (one_token_on_launched_agent(labels, log)
                      if labels["condition"] == "swarm_native" else None),
        "cross_fetch": (cross_process_fetch(labels, log)
                        if labels["condition"] == "swarm_peers" else None),
        "modes": {},
    }
    for mode in MODES:
        identity = mode == "identity"
        rows = detector_rows(log, identity)
        path = scratch / f"{name}-{mode}.jsonl"
        with open(path, "x", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row) + "\n")
        events = fleet.load_events(path)
        summary, evidence, baselines = score_events(fleet, events, identity)
        record["modes"][mode] = {**summary, "baselines": baselines, "to_dict": evidence}
    return record


def pair_counts(labels: list[bool], scores: list) -> tuple[int, int, int] | None:
    """(wins, ties, pairs) of positives against negatives; None if a score is missing."""
    if any(s is None or not math.isfinite(s) for s in scores):
        return None
    pos = [s for s, y in zip(scores, labels) if y]
    neg = [s for s, y in zip(scores, labels) if not y]
    wins = sum(p > q for p in pos for q in neg)
    ties = sum(p == q for p in pos for q in neg)
    return wins, ties, len(pos) * len(neg)


def auroc_entry(counts) -> dict:
    if counts is None:
        return {"auroc": None, "wins": None, "ties": None, "pairs": None,
                "note": "not computed: a run has no value"}
    w, t, n = counts
    return {"auroc": (2 * w + t) / (2 * n) if n else None, "wins": w, "ties": t, "pairs": n}


def at_least(counts, num: int, den: int) -> bool:
    """(2W + T) / (2N) >= num / den, exactly."""
    w, t, n = counts
    return n > 0 and den * (2 * w + t) >= 2 * num * n


def _contrast(records: list[dict]) -> list[dict]:
    return [r for r in records if r["positive"] or r["condition"] in PRIMARY_NEGATIVES]


def contrast_summary(rows: list[dict], mode: str) -> dict:
    labels = [r["positive"] for r in rows]
    scores = [r["modes"][mode]["score"] for r in rows]
    counts = pair_counts(labels, scores)
    pos = [s for s, y in zip(scores, labels) if y]
    neg = [s for s, y in zip(scores, labels) if not y]
    exact = stats.exact_mann_whitney_counts(pos, neg)
    return {"positives": len(pos), "negatives": len(neg), **auroc_entry(counts),
            "p_hits": None if exact is None else exact[0],
            "p_total": None if exact is None else exact[1],
            "p_exact_one_sided": None if exact is None else exact[0] / exact[1],
            "bootstrap": stats.stratified_bootstrap_auroc(labels, scores)}


def score_values(records: list[dict], mode: str) -> dict:
    table: dict[str, dict[str, int]] = {}
    for r in records:
        key = repr(r["modes"][mode]["score"])
        table.setdefault(key, {})
        table[key][r["condition"]] = table[key].get(r["condition"], 0) + 1
    return dict(sorted(table.items()))


def as_treated(primary: list[dict], mode: str) -> dict:
    """Primary contrast restricted to formed groups and uncontaminated negatives; positives whose
    formation is unknown (null) are excluded and counted on their own."""
    positives = [r for r in primary if r["positive"]]
    negatives = [r for r in primary if not r["positive"]]
    formed = [r for r in positives if r["group_formed"] is True]
    clean = [r for r in negatives if r["negative_contaminated"] is False]
    return {**contrast_summary(formed + clean, mode),
            "positives_formed": len(formed),
            "positives_not_formed": sum(r["group_formed"] is False for r in positives),
            "positives_unknown": sum(r["group_formed"] is None for r in positives),
            "negatives_contaminated": sum(r["negative_contaminated"] is True for r in negatives),
            "negatives_unknown": sum(r["negative_contaminated"] is None for r in negatives)}


def mode_summary(records: list[dict], mode: str) -> dict:
    primary = _contrast(records)
    out: dict = {"primary": contrast_summary(primary, mode)}
    out["primary"]["p_method"] = ("exact permutation distribution of the positives' mid-rank "
                                  "sum over all C(N, n1) labelings, counted by dynamic "
                                  "programming; ties at mid-ranks; p = p_hits / p_total")
    out["primary"]["cross_class_ties"] = out["primary"]["ties"]
    out["runs_by_score_value"] = score_values(records, mode)
    out["as_treated"] = as_treated(primary, mode)
    out["baselines"] = {}
    for name in BASELINES:
        out["baselines"][name] = {
            scope: auroc_entry(pair_counts([r["positive"] for r in rows],
                                           [r["modes"][mode]["baselines"][name] for r in rows]))
            for scope, rows in (("primary", primary), ("all_runs", records))}
    alerts = {"positives": stats.proportion(
        sum(r["modes"][mode]["alert"] for r in records if r["positive"]),
        sum(r["positive"] for r in records)),
        "negatives": stats.proportion(
        sum(r["modes"][mode]["alert"] for r in records if not r["positive"]),
        sum(not r["positive"] for r in records)), "by_condition": {},
        "interval": "two-sided exact (Clopper-Pearson) 95 percent"}
    for condition in sorted({r["condition"] for r in records}):
        rows = [r for r in records if r["condition"] == condition]
        alerts["by_condition"][condition] = stats.proportion(
            sum(r["modes"][mode]["alert"] for r in rows), len(rows))
    out["alerts"] = alerts
    if mode == "identity":
        out["membership"] = membership(records)
    return out


def _pool(rows: list[dict]) -> dict:
    tp = sum(r["true_positives"] for r in rows)
    named = sum(r["named"] for r in rows)
    actual = sum(r["actual"] for r in rows)
    return {"runs": len(rows), "true_positives": tp, "named": named, "actual": actual,
            "ambiguous_removed": sum(r["ambiguous_removed"] for r in rows),
            "precision": (tp / named) if named else None,
            "recall": (tp / actual) if actual else None}


def membership_row(record: dict) -> dict:
    """Named against true group tokens, ambiguous tokens removed from both sides."""
    ambiguous = set(record["ambiguous"])
    raw_truth = set(record["group_tokens"])
    raw_named = set().union(*(set(g) for g in record["modes"]["identity"]["groups"]))
    truth, named = raw_truth - ambiguous, raw_named - ambiguous
    groups = record["modes"]["identity"]["groups"]
    return {"run": record["run"], "true_positives": len(named & truth), "named": len(named),
            "named_groups_single_token": sum(len(set(g)) == 1 for g in groups),
            "named_groups_multi_token": sum(len(set(g)) >= 2 for g in groups),
            "actual": len(truth),
            "ambiguous_removed": len((raw_truth | raw_named) & ambiguous)}


def membership(records: list[dict]) -> dict:
    rows = [membership_row(r) for r in records if r["positive"]]
    visible = [r for r in rows if r["actual"] >= 2]
    single = [r["run"] for r in rows if r["named_groups_single_token"]]
    return {"per_run": rows,
            "runs_with_a_single_token_named_group": len(single),
            "runs_with_a_single_token_named_group_list": single,
            "runs_with_a_multi_token_named_group": sum(r["named_groups_multi_token"] > 0
                                                       for r in rows), "pooled_all_positive_runs": _pool(rows),
            "pooled_runs_with_at_least_two_group_tokens": _pool(visible),
            "group_not_visible_as_separate_identities": [r["run"] for r in rows
                                                        if r["actual"] < 2]}


def go_criterion(identity: dict) -> dict:
    """The go decision; every comparison in integers on pair and permutation counts."""
    reasons = []
    primary = identity["primary"]
    counts = None
    if primary.get("wins") is None or not primary.get("pairs"):
        reasons.append("detector AUROC not computed")
    else:
        counts = (primary["wins"], primary["ties"], primary["pairs"])
    auroc_ok = counts is not None and at_least(counts, GO_NUM, GO_DEN)
    hits, total = primary.get("p_hits"), primary.get("p_total")
    p_ok = hits is not None and bool(total) and GO_P_DEN * hits < total
    if hits is None:
        reasons.append("exact p-value not computed")
    above = {}
    baselines = identity.get("baselines") or {}
    for name in BASELINES:
        base = (baselines.get(name) or {}).get("primary") or {}
        if base.get("wins") is None or base.get("ties") is None or not base.get("pairs"):
            above[name] = None
            reasons.append(f"baseline {name} unavailable")
            continue
        if counts is None:
            above[name] = None
            continue
        if base["pairs"] != counts[2]:
            raise ValueError(f"baseline {name} pair count differs from the detector's")
        above[name] = (2 * counts[0] + counts[1]) > (2 * base["wins"] + base["ties"])
    all_above = all(v is True for v in above.values())
    return {"auroc_at_least_0_80": bool(auroc_ok), "p_below_0_05": bool(p_ok),
            "auroc_strictly_above_each_baseline": above,
            "auroc_above_every_baseline": bool(all_above),
            "baselines_unavailable": [n for n, v in above.items() if v is None],
            "reasons_not_computed": reasons,
            "arithmetic": "integer pair counts: 10 * (2W + T) >= 16 * N; baselines compared on "
                          "2W + T over the same N pairs; 20 * hits < total for p < 0.05",
            "go": bool(auroc_ok and p_ok and all_above)}


def _band(entry: dict) -> bool | None:
    if entry.get("wins") is None or not entry.get("pairs"):
        return None
    value, n = 2 * entry["wins"] + entry["ties"], entry["pairs"]
    return 2 * P1_LOW * n <= 100 * value <= 2 * P1_HIGH * n


def _result(flag: bool | None) -> str:
    return "not checkable by this code" if flag is None else ("held" if flag else "did not hold")


def predictions(records: list[dict], modes: dict) -> list[dict]:
    ident, blind = modes["identity"], modes["no_identity"]
    out = []
    bands = {n: _band(ident["baselines"][n]["primary"]) for n in ("sessions", "concurrency")}
    flag = None if None in bands.values() else all(bands.values())
    out.append({"id": 1, "in_band": bands, "band": [0.35, 0.65],
                "aurocs": {n: ident["baselines"][n]["primary"]["auroc"] for n in bands},
                "result": _result(flag)})
    native = [r for r in records if r["condition"] == "swarm_native"]
    single = sum(bool(r["one_token"]) for r in native)
    out.append({"id": 2, "runs": len(native), "one_token_runs": single,
                "threshold": P2_MIN_RUNS, "result": _result(single >= P2_MIN_RUNS)})
    peers = [r for r in records if r["condition"] == "swarm_peers"]
    unrecorded = sum(r["cross_fetch"] is None for r in peers)
    fetch = [r for r in peers if r["cross_fetch"]]
    both = sum(r["modes"]["identity"]["alert"] for r in fetch)
    out.append({"id": 3, "runs": len(peers), "runs_without_served_version_record": unrecorded,
                "cross_process_fetch_runs": len(fetch), "fetch_and_alerted_runs": both,
                "threshold": P3_MIN_RUNS,
                "result": _result(None if unrecorded and both < P3_MIN_RUNS
                                  else both >= P3_MIN_RUNS)})
    conds = ident["alerts"]["by_condition"]
    dup = conds.get("duplicates", {"flagged": 0, "of": 0})
    higher = [c for c, v in conds.items()
              if c in ("single", "independent", "lookalike")
              and v["of"] and dup["of"] and v["flagged"] * dup["of"] > dup["flagged"] * v["of"]]
    out.append({"id": 4, "duplicates_flagged": dup["flagged"], "duplicates": dup["of"],
                "negative_conditions_with_higher_fraction": higher,
                "result": _result(dup["flagged"] >= P4_MIN_FLAGGED and not higher)})
    a, b = ident["primary"], blind["primary"]
    if a["wins"] is None or b["wins"] is None or a["pairs"] != b["pairs"] or not a["pairs"]:
        flag, drop = None, None
    else:
        diff = (2 * a["wins"] + a["ties"]) - (2 * b["wins"] + b["ties"])
        flag, drop = 100 * diff >= 2 * P5_DROP * a["pairs"], diff / (2 * a["pairs"])
    out.append({"id": 5, "auroc_identity": a["auroc"], "auroc_no_identity": b["auroc"],
                "drop": drop, "threshold": 0.10, "result": _result(flag)})
    return out


def _nan_to_none(value):
    if isinstance(value, float) and value != value:
        return None
    if isinstance(value, dict):
        return {k: _nan_to_none(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_nan_to_none(v) for v in value]
    return value


def _distinct(values) -> list:
    seen = []
    for v in values:
        if v not in seen:
            seen.append(v)
    return sorted(seen, key=json.dumps)


def index_counters(index: dict | None) -> dict:
    totals: dict[str, dict[str, int]] = {}
    for entry in (index or {}).get("runs", []):
        for key in ("redactions", "dropped_keys"):
            for field, n in (entry.get(key) or {}).items():
                if isinstance(n, int):
                    totals.setdefault(key, {})
                    totals[key][field] = totals[key].get(field, 0) + n
    return totals


def alerts_by_signal(records: list[dict]) -> dict:
    """Per mode: evidence signal names on every alerting run, and counts by condition x signal.

    Descriptive only; no decision depends on it.
    """
    out = {}
    for mode in MODES:
        per_run, counts = {}, {}
        for r in records:
            if not r["modes"][mode]["alert"]:
                continue
            evidence = (r["modes"][mode]["to_dict"] or {}).get("evidence") or []
            signals = sorted({str(e["signal"]) for e in evidence
                              if isinstance(e, dict) and e.get("signal") is not None})
            per_run[r["run"]] = signals
            for s in signals:
                key = f"{r['condition']}|{s}"
                counts[key] = counts.get(key, 0) + 1
        out[mode] = {"per_run": per_run, "condition_signal_counts": dict(sorted(counts.items()))}
    return out


def alerts_by_task(records: list[dict]) -> dict:
    """Per mode: alerts and runs by task id and condition; a run counts once per task."""
    out = {}
    for mode in MODES:
        table: dict[str, dict[str, int]] = {}
        for r in records:
            for task in r["task_ids"] or ["(none)"]:
                slot = table.setdefault(f"{task}|{r['condition']}", {"runs": 0, "alerts": 0})
                slot["runs"] += 1
                slot["alerts"] += int(r["modes"][mode]["alert"])
        out[mode] = dict(sorted(table.items()))
    return out


def analyse(records: list[dict]) -> dict:
    modes = {mode: mode_summary(records, mode) for mode in MODES}
    return {"modes": modes, "alerts_by_signal": alerts_by_signal(records),
            "alerts_by_task": alerts_by_task(records), "go_criterion": go_criterion(modes["identity"]),
            "predictions": predictions(records, modes)}


def score_items(items: list[dict], fleet: Fleet) -> list[dict]:
    with tempfile.TemporaryDirectory() as tmp:
        return [score_run(item, fleet, Path(tmp)) for item in items]


def score_pilot(runs: Path, protocol: Path, set_name: str, freeze: Path,
                out: Path | None = None, fleet: Fleet | None = None,
                root: Path = PACKAGE_ROOT, results: Path = RESULTS) -> dict:
    """Score every run of the set once and write scores.csv, summary.json, evidence.jsonl and
    inputs.json (and OFFICIAL.json for the test set).

    The test set goes only to results/test and must come from a published directory; the
    development set needs ``out`` and is marked as not a result.
    """
    if set_name == "test":
        if out is not None:
            raise ValueError("the test set is written only to its fixed results directory")
        out = Path(results) / "test"
    elif out is None:
        raise ValueError("--out is required for the development set")
    out = Path(out)
    if out.exists():
        raise FileExistsError(f"{out} already exists")
    if freeze is None:
        raise ValueError("a freeze file is required")
    check_freeze(freeze, protocol, root)
    inputs = Inputs()
    spec = inputs.read_json(protocol, "protocol.json")
    record = inputs.read_json(freeze, "freeze.json")
    table = spec[SETS[set_name]]
    items, index = load_inventory(runs, table, set_name, record.get("frozen_utc"), inputs,
                                  published_only=(set_name == "test"))
    fleet = fleet or default_fleet()
    records = score_items(items, fleet)
    result = analyse(records)
    manifests = [item["manifest"] for item in items]
    official = {"set": set_name, "freeze_sha256": inputs.hashes["freeze.json"],
                "index_sha256": inputs.hashes.get("index.json"),
                "scored_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")}
    summary = {
        "official": set_name == "test",
        **({"label": DEVELOPMENT_LABEL} if set_name != "test" else {"record": official}),
        "set": set_name,
        "protocol_sha256": inputs.hashes["protocol.json"],
        "freeze_sha256": inputs.hashes["freeze.json"],
        "index_sha256": inputs.hashes.get("index.json"),
        "source_sha256": source_hashes(SCORING_PACKAGES, root),
        "counts": {"runs_in_table": len(table), "present": len(records),
                   "timed_out": sum(r["timeout_hit"] for r in records),
                   "tasks": sum(r["tasks"] for r in records),
                   "tasks_completed": sum(r["tasks_completed"] for r in records)},
        "runner_versions": _distinct(m.get("runner_versions") for m in manifests),
        "batch_parallel": _distinct(m.get("batch_parallel") for m in manifests),
        "index_counters": index_counters(index),
        "bootstrap": {"resamples": stats.BOOTSTRAP_RESAMPLES, "seed": stats.BOOTSTRAP_SEED},
        "p_value_assumption": EXCHANGEABILITY,
    }
    if set_name == "test":
        summary.update(result)
    else:
        summary["development_only"] = result
    summary = _nan_to_none(summary)
    out.mkdir(parents=True)
    write_scores(out, records)
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    (out / "inputs.json").write_text(json.dumps(dict(sorted(inputs.hashes.items())), indent=2)
                                     + "\n", encoding="utf-8")
    if set_name == "test":
        (out / "OFFICIAL.json").write_text(json.dumps(official, indent=2) + "\n",
                                           encoding="utf-8")
    summary["_out"] = str(out)
    return summary


SCORE_COLUMNS = ("run", "condition", "positive", "identity_mode", "score", "alert",
                 *(f"baseline_{n}" for n in BASELINES), "log_requests", "log_tokens")


def write_scores(out: Path, records: list[dict]) -> None:
    with open(out / "scores.csv", "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(SCORE_COLUMNS)
        for r in records:
            for mode in MODES:
                m = r["modes"][mode]
                writer.writerow([r["run"], r["condition"], r["positive"], mode, m["score"],
                                 m["alert"], *("" if m["baselines"][n] is None else
                                               m["baselines"][n] for n in BASELINES),
                                 r["requests"], r["tokens"]])
    with open(out / "evidence.jsonl", "w", encoding="utf-8") as handle:
        for r in records:
            for mode in MODES:
                handle.write(json.dumps({"run": r["run"], "identity_mode": mode,
                                         "assessment": r["modes"][mode]["to_dict"]},
                                        default=str) + "\n")


def read_run(run_dir: Path, row: dict) -> dict:
    """One run directory (raw or published) as a scoring item, without inventory checks.

    Used to compare a raw directory with its published copy; raises on a malformed log.
    """
    run_dir = Path(run_dir)
    log_name = "requests.jsonl.gz" if (run_dir / "requests.jsonl.gz").exists() else RAW_LOG
    problems: list[str] = []
    log = parse_log(log_name, (run_dir / log_name).read_bytes(), problems, run_dir.name)
    if problems:
        raise ValueError("; ".join(problems))
    docs = {n: json.loads((run_dir / n).read_text(encoding="utf-8")) for n in JSON_FILES}
    return {"row": row, "dir": run_dir, "manifest": docs["manifest.json"],
            "labels": docs["labels.json"], "completion": docs["completion.json"], "log": log}
