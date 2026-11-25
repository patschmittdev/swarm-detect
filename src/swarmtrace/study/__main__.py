"""Command line: `python -m swarmtrace.study pilot|transfer|freeze|fetch-control ...`."""

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

from swarmtrace.study.fetch import fetch_control
from swarmtrace.study.fleet_api import stub_fleet
from swarmtrace.study.freeze import check_freeze, sha256_file, write_freeze
from swarmtrace.study.pilot import DEVELOPMENT_LABEL, RESULTS, SETS, score_pilot
from swarmtrace.study.transfer import run_transfer

DEFAULT_PROTOCOL = Path("benchmarks/agent-pilot/protocol.json")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m swarmtrace.study")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("pilot", help="score one set of pilot runs",
                       description="Score one set. The test set is read from a published "
                       "directory and written only to benchmarks/agent-pilot/results/test/.")
    p.add_argument("--runs", required=True, type=Path,
                   help="published directory (with index.json); required form for the test set")
    p.add_argument("--protocol", required=True, type=Path)
    p.add_argument("--set", required=True, choices=sorted(SETS), dest="set_name")
    p.add_argument("--freeze", required=True, type=Path)
    p.add_argument("--out", type=Path,
                   help="output directory; development set only (required there)")
    t = sub.add_parser("transfer", help="score the incident and control logs",
                       description="Score the transfer test once, into "
                       "benchmarks/agent-pilot/results/transfer/.")
    t.add_argument("--incident", required=True, type=Path)
    t.add_argument("--control", required=True, type=Path)
    t.add_argument("--freeze", required=True, type=Path)
    t.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    t.add_argument("--dev-out", type=Path,
                   help="test-only output directory; requires --stub-detector")
    t.add_argument("--stub-detector", action="store_true",
                   help="use a never-alerting stub instead of the detector (with --dev-out only)")
    f = sub.add_parser("freeze", help="record the hashes of the protocol and the code")
    f.add_argument("--protocol", required=True, type=Path)
    f.add_argument("--out", required=True, type=Path)
    c = sub.add_parser("fetch-control", help="download the control history dump")
    c.add_argument("--out", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "freeze":
        write_freeze(args.protocol, args.out)
        print(f"wrote {args.out}")
        return 0
    if args.command == "fetch-control":
        record = fetch_control(args.out)
        print(f"{record['bytes']} bytes, sha256 {record['sha256']}")
        return 0
    if args.command == "pilot":
        if args.set_name == "test" and args.out is not None:
            parser.error("the test set has a fixed output directory; --out is not accepted")
        if args.set_name != "test" and args.out is None:
            parser.error("--out is required for the development set")
        summary = score_pilot(args.runs, args.protocol, args.set_name, args.freeze, args.out)
        digest = summary["freeze_sha256"][:12]
        if args.set_name == "test":
            print(f"official result: set test, freeze {digest}, written to {summary['_out']}")
        else:
            print(f"{DEVELOPMENT_LABEL}: set {args.set_name}, freeze {digest}, "
                  f"written to {summary['_out']}")
        return 0
    if (args.dev_out is None) != (not args.stub_detector):
        parser.error("--dev-out and --stub-detector go together")
    check_freeze(args.freeze, args.protocol)
    digest = sha256_file(args.freeze)
    if args.dev_out is not None:
        run_transfer(args.incident, args.control, args.dev_out, fleet=stub_fleet())
        print(f"stub detector, not a result: freeze {digest[:12]}, written to {args.dev_out}")
        return 0
    out = RESULTS / "transfer"
    official = {"set": "transfer", "freeze_sha256": digest, "index_sha256": None,
                "scored_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")}
    run_transfer(args.incident, args.control, out, official=official)
    print(f"official result: transfer, freeze {digest[:12]}, written to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
