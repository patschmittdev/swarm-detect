"""Score or explain a service request window."""

import argparse
import json

from swarmtrace.fleet.baselines import all_baselines
from swarmtrace.fleet.detector import ALERT_THRESHOLD, assess
from swarmtrace.fleet.events import load_events


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m swarmtrace.fleet")
    commands = parser.add_subparsers(dest="command", required=True)
    score = commands.add_parser("score", help="print the assessment and reference scores")
    score.add_argument("--events", required=True)
    score.add_argument("--json", action="store_true")
    score.add_argument(
        "--identity-removed", action="store_true", help="use identity-removed baseline scores",
    )
    explain = commands.add_parser("explain", help="print evidence and supporting requests")
    explain.add_argument("--events", required=True)
    args = parser.parse_args()
    try:
        events = load_events(args.events)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    assessment = assess(events)

    if args.command == "score":
        baselines = all_baselines(events, identity_removed=args.identity_removed)
        if args.json:
            print(json.dumps({**assessment.to_dict(), "baselines": baselines}))
            return

    print(
        f"Score {assessment.score:g} | alert {str(assessment.alert).lower()}"
        f" | threshold > {ALERT_THRESHOLD:g}"
    )
    for group in assessment.groups:
        print("Group " + ", ".join(group))
    for item in assessment.evidence:
        seqs = ", ".join(map(str, item["seqs"]))
        print(f"{item['signal']} = {item['value']:g} (request seq {seqs})")
        if order := item.get("order"):
            print(
                f"  {order['family_changes']} changes in {order['transitions']} transitions, "
                f"{order['returns']} returns to {order['returning_families']} of "
                f"{order['families']} families, log null tail bound "
                f"{order['log_null_tail_bound']:.3g}"
            )
    if not assessment.evidence:
        print("No supporting requests")
    for item in assessment.not_computable:
        print(f"{item['signal']} unavailable ({item['reason']})")
    if args.command == "score":
        for name, value in baselines.items():
            print(f"{name} = {f'{value:g}' if value is not None else 'not computable'}")


if __name__ == "__main__":
    main()
