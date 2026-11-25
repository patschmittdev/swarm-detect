"""Replay two publisher-captured hook fixtures from pinned, unmodified source bytes."""

import json
from collections import Counter
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory
from urllib.request import urlopen

from swarmtrace.eval.claude_hooks import review_claude_hooks
from swarmtrace.eval.grok_hooks import review_grok_hooks
from swarmtrace.eval.recipient import _already_published
from swarmtrace.reproduce.public_tickets import digest

REVISION = "d6641fe94841110a2184dd5bb1a1b360666b342d"
BASE_URL = f"https://raw.githubusercontent.com/eneskirca/nodeterm/{REVISION}/src/shared/agents/__fixtures__"
ASSETS = {
    "claude": ("subagent-hook-payloads.json", 144552, "e4fd1f06f12b5e9a9cf04d305c3a569a32e75131643b0bec8a44a01d876d2664"),
    "grok": ("hook-payloads.json", 16450, "831b4d78be4a47cabe8b3383d0952389ecc025db636fc4908f8ebcfc7a4fbad9"),
}
CLAUDE_SCENARIOS = {
    "print_sync": 10, "print_async": 14, "print_parallel_foreground": 16, "print_nested": 14,
    "print_interrupt_foreground": 7, "print_interrupt_background": 8,
    "interactive_background_then_esc": 33, "interactive_parallel": 41, "interactive_nested_resume": 26,
}


def protocol() -> dict:
    return {
        "version": 1, "publisher": "eneskirca/nodeterm", "revision": REVISION,
        "source_kind": "publisher_reported_live_captures_with_redactions",
        "assets": {provider: {"url": f"{BASE_URL}/{provider}/{name}", "filename": name,
                              "bytes": size, "sha256": expected}
                   for provider, (name, size, expected) in ASSETS.items()},
        "claude": {
            "release": "Claude Code 2.1.284", "captured": "2026-09-29",
            "scenario_event_counts": CLAUDE_SCENARIOS,
            "grouping": "Score in recorded order within each named scenario. One scenario continues a previous session. Report distinct child counts only within each scenario.",
        },
        "grok": {
            "release": "Grok 1.0.13 (5e9a58528b76)",
            "captures": {"2026-09-01": "15 selected examples", "2026-09-02": "four lifecycle records for two parallel children"},
            "grouping": "Use the published selection order and split the second capture's four subagent records from the first capture. The selection cannot establish an application-wide timeline.",
        },
        "endpoints": "Count native hook coverage and identity joins. These fixtures have no independent labels for completed policy effects or coordination intent.",
    }


def _source(source_dir, provider, fetch):
    name, size, expected = ASSETS[provider]
    path = source_dir / name
    downloaded = False
    try:
        with path.open("rb") as stream:
            payload = stream.read(size + 1)
    except FileNotFoundError:
        if not fetch:
            raise ValueError(f"missing pinned {provider} capture {name}; supply --source-dir or use --fetch") from None
        with urlopen(f"{BASE_URL}/{provider}/{name}", timeout=45) as response:
            payload = response.read(size + 1)
        downloaded = True
    if len(payload) != size or digest(payload) != expected:
        raise ValueError(f"wrong size or SHA-256 for the original {provider} capture")
    if downloaded:
        source_dir.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(dir=source_dir, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(payload)
        try:
            try:
                path.hardlink_to(temporary)
            except FileExistsError:
                if path.read_bytes() != payload:
                    raise ValueError(f"conflicting published {provider} capture") from None
        finally:
            temporary.unlink(missing_ok=True)
    return json.loads(payload)


def _events(records, expected, name, session):
    if not isinstance(records, list) or len(records) != expected:
        raise ValueError(f"expected {expected} complete native hook records")
    for event in records:
        if not isinstance(event, dict) or any(not isinstance(event.get(k), str) or not event[k].strip()
                                              for k in (name, session)):
            raise ValueError("native hook records need an event kind and session identity")
    return dict(sorted(Counter(e[name] for e in records).items()))


def _claude(document):
    if (not isinstance(document, dict) or set(document) != {"claudeVersion", "_provenance", "scenarios"}
            or document["claudeVersion"] != "2.1.284"
            or not isinstance(document["scenarios"], dict) or document["scenarios"].keys() != CLAUDE_SCENARIOS.keys()):
        raise ValueError("unexpected Claude capture envelope or scenario set")
    cases, sum_counts, parent_sessions = {}, {}, set()
    for name, count in CLAUDE_SCENARIOS.items():
        case = document["scenarios"][name]
        if (not isinstance(case, dict) or set(case) != {"mode", "description", "events"}
                or case["mode"] != name.split("_", 1)[0]):
            raise ValueError(f"unexpected Claude capture scenario {name}")
        events = case["events"]
        by_kind = _events(events, count, "hook_event_name", "session_id")
        parents = {e["session_id"] for e in events if e["hook_event_name"] == "UserPromptSubmit"}
        if len(parents) != 1:
            raise ValueError(f"expected one prompting parent in {name}")
        parent_sessions.update(parents)
        review = review_claude_hooks(events)
        cases[name] = {"mode": case["mode"], "source_event_counts": by_kind, "review": review}
        for group in ("lifecycle", "tools", "latest_open", "lineage"):
            total = sum_counts.setdefault(group, Counter())
            total.update({k: v for k, v in review[group].items() if k != "distinct_children"})
    return {"selected_events": sum(CLAUDE_SCENARIOS.values()), "distinct_prompting_session_ids": len(parent_sessions),
            "scenarios": cases, "sum_of_scenario_review_counts": sum_counts}


def _grok(document):
    if not isinstance(document, dict) or set(document) != {"_provenance", "events"}:
        raise ValueError("unexpected Grok capture envelope")
    events = document["events"]
    by_kind = _events(events, 19, "hookEventName", "sessionId")
    if any(e.get("hook_event_name") != e["hookEventName"] or e.get("session_id") != e["sessionId"] for e in events):
        raise ValueError("conflicting canonical and alternate identifiers in the Grok selection")
    second = {"subagent_start", "subagent_stop"}
    if any((e["hookEventName"] in second) != (i >= 15) for i, e in enumerate(events)):
        raise ValueError("unexpected boundary between the publisher's two Grok captures")
    cases = {}
    for date, subset in (("2026-09-01", events[:15]), ("2026-09-02", events[15:])):
        cases[date] = {"selected_events": len(subset), "review": review_grok_hooks(subset)}
    return {"selected_events": len(events), "source_event_counts": by_kind, "captures": cases}


def run_native_hook_benchmark(source_dir: Path, out: Path, *, fetch: bool = False) -> dict:
    """Read the flat source directory and publish a reproducible aggregate report."""
    source_dir, out = Path(source_dir), Path(out)
    claude = _claude(_source(source_dir, "claude", fetch))
    grok = _grok(_source(source_dir, "grok", fetch))
    spec = protocol()
    summary = {
        "revision": REVISION, "source_kind": spec["source_kind"], "claude": claude, "grok": grok,
        "verified_policy_effect_labels": 0, "verified_coordination_intent_labels": 0,
        "independent_swarm_accuracy_rounds": 0,
    }
    out.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=out) as temporary:
        generated = []
        for name, content in (("protocol.json", spec), ("summary.json", summary)):
            path = Path(temporary) / name
            path.write_bytes((json.dumps(content, sort_keys=True, indent=2, allow_nan=False) + "\n").encode())
            generated.append(path)
        missing = [p for p in generated if not _already_published(out / p.name, p)]
        for path in missing:
            try:
                (out / path.name).hardlink_to(path)
            except FileExistsError:
                if not _already_published(out / path.name, path):
                    raise
    return summary
