"""Command line: `python -m swarmtrace.pilot run|serve|export|batch|publish ...`."""

import argparse
import sys
import time
from pathlib import Path

from swarmtrace.pilot.batch import SETS, batch
from swarmtrace.pilot.harness import CONDITIONS, DEFAULT_MIX, LAUNCHERS, RunConfig, export, run
from swarmtrace.pilot.lookalikes import CLIENTS
from swarmtrace.pilot.publish import PUBLISH_SETS, ReviewRequired, publish
from swarmtrace.pilot.service import Service
from swarmtrace.pilot.tasks import TASKS


def _csv(text: str) -> list[str]:
    return [part.strip() for part in text.split(",") if part.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m swarmtrace.pilot")
    sub = parser.add_subparsers(dest="command", required=True)
    r = sub.add_parser("run", help="run one pilot and write its run directory")
    r.add_argument("--condition", required=True, choices=CONDITIONS)
    r.add_argument("--out", required=True, type=Path)
    r.add_argument("--seed", required=True, type=int)
    r.add_argument("--launcher", default="fake", choices=sorted(LAUNCHERS))
    r.add_argument("--model")
    r.add_argument("--launchers", type=_csv,
                   help="comma-separated launcher per agent process; overrides --launcher")
    r.add_argument("--models", type=_csv,
                   help="comma-separated model per agent process; overrides --model")
    r.add_argument("--agents", type=int, default=3)
    r.add_argument("--subagents", type=int, default=3)
    r.add_argument("--task", nargs="+", default=[], choices=sorted(TASKS))
    r.add_argument("--timeout", type=float, default=900.0)
    r.add_argument("--background", action="store_true")
    r.add_argument("--dry-run", action="store_true",
                   help="use the scripted fake agent in place of the chosen launcher")
    r.add_argument("--mix", nargs="+", default=list(DEFAULT_MIX), choices=sorted(CLIENTS),
                   help="scripted clients for the lookalike condition")
    r.add_argument("--duration", type=float, default=None,
                   help="seconds the scripted clients run (default 120, or 3 with --dry-run)")
    s = sub.add_parser("serve", help="run the service in the foreground")
    s.add_argument("--seed", required=True, type=int)
    s.add_argument("--port", type=int, default=8765)
    s.add_argument("--log", type=Path)
    e = sub.add_parser("export", help="write the log copy without via and peer_port")
    e.add_argument("--run", required=True, type=Path)
    e.add_argument("--out", required=True, type=Path)
    e.add_argument("--no-identity", action="store_true", help="also set token_id to null")
    b = sub.add_parser("batch", help="execute one set of a protocol's run table")
    b.add_argument("--protocol", required=True, type=Path)
    b.add_argument("--set", required=True, choices=sorted(SETS), dest="set_name")
    b.add_argument("--out", required=True, type=Path)
    b.add_argument("--parallel", type=int, default=1, help="runs at once (default 1)")
    b.add_argument("--only", nargs="+", help="run ids to execute; default all rows of the set")
    b.add_argument("--dry-run", action="store_true",
                   help="use the scripted fake agent and 3 s lookalike runs")
    p = sub.add_parser("publish", help="write the publishable record of a batch")
    p.add_argument("--runs", required=True, type=Path)
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--set", dest="set_name", required=True, choices=PUBLISH_SETS)
    p.add_argument("--protocol", required=True, type=Path,
                   help="protocol file whose model names may appear in the record")
    p.add_argument("--review-out", required=True, type=Path,
                   help="where to write every distinct agent-written value (outside --out)")
    p.add_argument("--reviewed-sha256",
                   help="SHA-256 of the review file; without it only the review file is written")
    args = parser.parse_args(argv)
    if args.command == "batch":
        results = batch(args.protocol, args.set_name, args.out, args.parallel, args.only,
                        dry_run=args.dry_run, duration=3.0 if args.dry_run else 150.0)
        return 1 if any("error" in r for r in results) else 0
    if args.command == "publish":
        try:
            index = publish(args.runs, args.out, args.set_name, args.protocol, args.review_out,
                            args.reviewed_sha256)
        except ReviewRequired as notice:
            print(notice, file=sys.stderr)
            return 2
        print(f"published {len(index['runs'])} runs to {args.out}; "
              f"{index['values_reviewed']} reviewed values, review {index['review_sha256']}")
        return 0
    if args.command == "export":
        print(export(args.run, args.out, identity=not args.no_identity))
        return 0
    if args.command == "serve":
        with Service(seed=args.seed, addresses=["127.0.0.1"], log_path=args.log,
                     port=args.port) as svc:
            print(f"serving {svc.base_urls[0]} (help at {svc.base_urls[0]}/help); Ctrl+C stops", flush=True)
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                pass
        return 0
    if args.launchers and set(args.launchers) - set(LAUNCHERS):
        parser.error(f"--launchers must be drawn from {sorted(LAUNCHERS)}")
    quick = args.dry_run
    duration = args.duration if args.duration is not None else (3.0 if quick else 120.0)
    out = run(RunConfig(
        condition=args.condition, out=args.out, seed=args.seed, launcher=args.launcher,
        model=args.model, launchers=args.launchers, models=args.models, agents=args.agents,
        subagents=args.subagents, tasks=args.task,
        timeout=args.timeout, background=args.background, dry_run=args.dry_run, mix=args.mix,
        duration=duration, stagger=0.2 if quick else 2.0, jitter=0.1 if quick else 1.0))
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
