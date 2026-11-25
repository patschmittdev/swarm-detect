"""Inventory only field names, counts and sidecar names in the pre-existing raw trace archives."""

import argparse
import gzip
import json
from collections import Counter, defaultdict
from pathlib import Path


def inventory(roots: list[Path]) -> dict:
    runs, tools = Counter(), Counter()
    fields: set[str] = set()
    sidecars: Counter[str] = Counter()
    handoff_fields: set[str] = set()
    arguments: dict[str, set[str]] = defaultdict(set)
    for root in roots:
        if not root.is_dir():
            raise ValueError(f"missing archive root {root}")
        for trace in sorted(root.rglob("trace.jsonl*")):
            if trace.name not in {"trace.jsonl", "trace.jsonl.gz"}:
                continue
            runs[root.as_posix()] += 1
            opener = gzip.open if trace.suffix == ".gz" else open
            with opener(trace, "rt", encoding="utf-8") as stream:
                for line in stream:
                    event = json.loads(line)
                    fields.update(event)
                    tools[event["tool"]] += 1
                    arguments[event["tool"]].update(event["args"])
            for path in sorted(trace.parent.iterdir()):
                if path == trace or not path.is_file():
                    continue
                name = path.name.removesuffix(".gz")
                sidecars[name] += 1
                if name == "context.json":
                    opener = gzip.open if path.suffix == ".gz" else open
                    with opener(path, "rt", encoding="utf-8") as stream:
                        context = json.load(stream)
                    for handoff in context["handoffs"]:
                        handoff_fields.update(handoff)
    return {
        "trace_files_by_root": dict(sorted(runs.items())), "events": sum(tools.values()),
        "events_by_tool": dict(sorted(tools.items())), "event_fields": sorted(fields),
        "argument_fields_by_tool": {tool: sorted(keys) for tool, keys in sorted(arguments.items())},
        "co_located_sidecars": dict(sorted(sidecars.items())), "handoff_fields": sorted(handoff_fields),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("roots", type=Path, nargs="+")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    result = json.dumps(inventory(args.roots), indent=2) + "\n"
    if args.out:
        args.out.write_text(result, encoding="utf-8", newline="\n")
    else:
        print(result, end="")


if __name__ == "__main__":
    main()
