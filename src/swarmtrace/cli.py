import argparse
import json
import sys
from pathlib import Path

from swarmtrace.eval import commands as eval_commands
from swarmtrace.reproduce import commands as reproduce_commands
from swarmtrace.reproduce import containment as containment_commands
from swarmtrace.reproduce import figures
from swarmtrace.reproduce.evasion import EvasionConfig, run_evasion
from swarmtrace.reproduce.sharing_sweep import (
    SharingSweepConfig,
    render_sharing_sweep_from_tables,
    run_sharing_sweep,
)
from swarmtrace.reproduce.verify import verify
from swarmtrace.trace.synthetic import generate_synthetic_runs


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="swarmtrace")
    commands = parser.add_subparsers(dest="command", required=True)
    synthetic = commands.add_parser("synthetic", help="Generate planted-signal traces")
    synthetic.add_argument("--out", type=Path, required=True)
    synthetic.add_argument("--runs", type=int, required=True)
    synthetic.add_argument("--seed", type=int, required=True)
    synthetic.add_argument("--signal", type=int, required=True)
    eval_commands.add_parsers(commands)
    reproduce_commands.add_parser(commands)
    read_round = commands.add_parser(
        "read-round", help="Check read attribution and evaluate the held-out second-reader signal")
    read_round.add_argument("--out", type=Path, required=True, help="New study output directory")
    read_round.add_argument("--workers", type=int, default=4)
    read_round.add_argument("--attribution-only", action="store_true",
                            help="Run hand-labelled read cases and role-flip controls")
    calibration = commands.add_parser(
        "calibrate-read-alerts", help="Test a workflow-specific cutoff for the frozen scope model")
    calibration.add_argument("--out", type=Path, required=True, help="New study output directory")
    calibration.add_argument("--study", type=Path, default=Path("benchmarks/read-authorization"),
                             help="Read study containing the original fit and calibration IDs")
    calibration.add_argument("--data", type=Path, default=Path("data"),
                             help="Recorded development archive")
    calibration.add_argument("--workers", type=int, default=4)
    grant = commands.add_parser("grant-round", help="Compare recorded and inferred grant scopes on held-out runs")
    grant.add_argument("--out", type=Path, required=True, help="New study output directory")
    grant.add_argument("--study", type=Path, default=Path("benchmarks/read-authorization"))
    grant.add_argument("--previous-calibration", type=Path, default=Path("benchmarks/read-calibration"))
    grant.add_argument("--data", type=Path, default=Path("data"))
    grant.add_argument("--workers", type=int, default=4)
    grant.add_argument("--checks-only", action="store_true", help="Run labelled cases and role-flipped controls")
    policy = commands.add_parser("grant-policy", help="Confirm an overlap-specific grant alert policy")
    policy.add_argument("--out", type=Path, required=True, help="New study output directory")
    policy.add_argument("--prior", type=Path, default=Path("benchmarks/grant-scope"))
    policy.add_argument("--workers", type=int, default=4)
    assignment = commands.add_parser("assignment-round", help="Compare assignment scores on complete held-out runs")
    assignment.add_argument("--out", type=Path, required=True, help="New study output directory")
    assignment.add_argument("--benchmarks", type=Path, default=Path("benchmarks"))
    assignment.add_argument("--data", type=Path, default=Path("data"))
    assignment.add_argument("--workers", type=int, default=4)
    assignment.add_argument("--checks-only", action="store_true", help="Run the historical role-pair checks")
    margin = commands.add_parser("assignment-margin", help="Confirm assignment scores against whole-run logistic margins")
    margin.add_argument("--study", type=Path, default=Path("benchmarks/assignment"))
    margin.add_argument("--benchmarks", type=Path, default=Path("benchmarks"))
    margin.add_argument("--out", type=Path, required=True, help="New confirmation output directory")
    margin.add_argument("--workers", type=int, default=4)
    transfer = commands.add_parser("assignment-transfer", help="Replay frozen scores on previously published workflows")
    transfer.add_argument("--study", type=Path, default=Path("benchmarks/assignment"))
    transfer.add_argument("--benchmarks", type=Path, default=Path("benchmarks"))
    transfer.add_argument("--out", type=Path, required=True, help="New audit output directory")
    support = commands.add_parser("assignment-support", help="Audit shared-file evidence on the designated focal team")
    support.add_argument("--study", type=Path, default=Path("benchmarks/assignment"))
    support.add_argument("--out", type=Path, required=True, help="New audit output directory")
    support.add_argument("--workers", type=int, default=4)
    recipient = commands.add_parser("recipient-round", help="Replay recipient approvals and object-version receipts")
    recipient.add_argument("--benchmark-dir", type=Path, default=Path("benchmarks/recipient-approval"))
    recipient.add_argument("--out", type=Path, required=True, help="New study output directory")
    dispatch = commands.add_parser("dispatch-contract", help="Compare dispatch and commit warnings by delivery")
    dispatch.add_argument("--benchmark-dir", type=Path, default=Path("benchmarks/recipient-approval"))
    dispatch.add_argument("--out", type=Path, required=True)
    workflows = commands.add_parser("dispatch-workflows", help="Replay public approval tickets through the document office")
    workflows.add_argument("--study", type=Path, default=Path("benchmarks/dispatch-workflows"))
    workflows.add_argument("--source-dir", type=Path, default=Path("results-replay/public-dispatch-inputs"))
    workflows.add_argument("--out", type=Path, required=True, help="New output directory")
    workflows.add_argument("--fetch", action="store_true", help="Download missing hash-pinned public inputs")
    workflows.add_argument("--review-only", action="store_true", help="Emit blinded review packets before scoring")
    reviews = commands.add_parser("dispatch-reviews", help="Score the two dispatch review ballots")
    reviews.add_argument("--study", type=Path, default=Path("benchmarks/dispatch-workflows"))
    reviews.add_argument("--review-one", type=Path)
    reviews.add_argument("--review-two", type=Path)
    reviews.add_argument("--out", type=Path, required=True)
    approval_text = commands.add_parser("approval-text", help="Replay public transfer-requirement text evaluations")
    approval_text.add_argument("--study", type=Path, default=Path("benchmarks/approval-text"))
    approval_text.add_argument("--out", type=Path, required=True)
    hooks = commands.add_parser("review-hook-events", help="Audit worker attribution in one native JSONL hook capture")
    hooks.add_argument("--provider", choices=("claude", "grok"), required=True)
    hooks.add_argument("--events", type=Path, required=True)
    hooks.add_argument("--show-links", action="store_true", help="Include event numbers for verified native matches")
    hook_benchmark = commands.add_parser("native-hook-benchmark", help="Replay pinned public native hook captures")
    hook_benchmark.add_argument("--source-dir", type=Path, default=Path("results-replay/native-hook-inputs"))
    hook_benchmark.add_argument("--out", type=Path, required=True, help="New benchmark output directory")
    hook_benchmark.add_argument("--fetch", action="store_true", help="Fetch missing hash-pinned fixtures")
    operation = commands.add_parser("operation-authority", help="Test permission at the time of a document use")
    operation.add_argument("--study", type=Path, default=Path("benchmarks/operation-authority"))
    operation.add_argument("--dispatch-study", type=Path, default=Path("benchmarks/dispatch-workflows"))
    operation.add_argument("--source-dir", type=Path, default=Path("results-replay/public-dispatch-inputs"))
    operation.add_argument("--out", type=Path, required=True, help="New benchmark output directory")
    operation.add_argument("--fetch", action="store_true", help="Fetch missing hash-pinned public ticket inputs")
    inspect = commands.add_parser("review-assignments", help="Show verified assignment evidence for one run as JSON")
    inspect.add_argument("--run", type=Path, required=True)
    inspect.add_argument("--study", type=Path, help="Optionally score assignments with a saved assignment-round fit")
    sharing = commands.add_parser("sharing-sweep", help="Measure benign credential-sharing rates")
    sharing_output = sharing.add_mutually_exclusive_group(required=True)
    sharing_output.add_argument("--out", type=Path)
    sharing_output.add_argument(
        "--render-from", type=Path,
        help="Rebuild the report from existing run tables without simulation",
    )
    sharing.add_argument("--seed", type=int, required=True)
    sharing.add_argument("--workers", type=int, default=SharingSweepConfig.workers)
    evasion = commands.add_parser("evasion", help="Measure owner-silent relay evasion")
    evasion.add_argument("--out", type=Path, required=True)
    evasion.add_argument("--seed", type=int, required=True)
    evasion.add_argument("--workers", type=int, default=EvasionConfig.workers)
    scope = commands.add_parser("scope", help="Run the scope experiment and identical-policy gate")
    scope.add_argument("--out", type=Path, required=True)
    scope.add_argument("--seed", type=int, required=True)
    scope.add_argument("--workers", type=int, default=4)
    scope.add_argument("--time-runs", type=int,
                       help="Time N simulations and print a projection without writing results")
    containment_commands.add_parser(commands)
    verification = commands.add_parser("verify", help="Verify recorded artifacts and provenance")
    verification.add_argument("--data", type=Path, required=True)
    figure_parser = commands.add_parser("figures", help="Draw SVG figures from recorded reports")
    figure_parser.add_argument("--data", type=Path, default=Path("data"))
    figure_parser.add_argument("--out", type=Path, default=Path("docs/figures"))
    sweep = commands.add_parser("sweep", help="Simulate the scripted experimental grid")
    sweep.add_argument("--out", type=Path, required=True)
    sweep.add_argument("--seed", type=int, required=True)
    sweep.add_argument("--runs-per-condition", type=int, default=1)
    sweep.add_argument("--ticks", type=int, default=160)
    sweep.add_argument("--group-sizes", type=int, nargs="+", default=(0, 2, 3, 5))
    sweep.add_argument("--coordinated-groups", type=int, nargs="+", default=(1, 2, 3))
    sweep.add_argument("--benign-credential-sharing", type=int, default=10)
    sweep.add_argument("--scope", choices=("off", "on"), default="off",
                       help="Include approved handoff file lists in the simulation")
    sweep.add_argument("--capture-authorization", action="store_true",
                       help="Record the gateway authorization basis for each successful read")
    sweep.add_argument("--channels", nargs="+", default=("message", "shared_file", "preplanned"))
    sweep.add_argument("--topologies", nargs="+", default=("hub", "peer"))
    arguments = parser.parse_args(argv)
    if arguments.command == "figures":
        try:
            figures.main(data=arguments.data, out=arguments.out)
        except figures.FigureError as error:
            print(str(error), file=sys.stderr)
            raise SystemExit(1) from None
        return
    if arguments.command == "verify":
        try:
            verify(arguments.data)
        except ValueError as error:
            print(str(error), file=sys.stderr)
            raise SystemExit(1) from None
        return
    try:
        if arguments.command == "assignment-margin":
            from swarmtrace.reproduce.assignment_margin import run_assignment_margin

            run_assignment_margin(arguments.study, arguments.benchmarks, arguments.out, arguments.workers)
            return
        if arguments.command == "assignment-transfer":
            from swarmtrace.reproduce.assignment_transfer import audit_assignment_transfer

            audit_assignment_transfer(arguments.study, arguments.benchmarks, arguments.out)
            return
        if arguments.command == "assignment-support":
            from swarmtrace.reproduce.assignment_support import audit_assignment_support

            audit_assignment_support(arguments.study, arguments.out, arguments.workers)
            return
        if arguments.command == "review-assignments":
            from swarmtrace.eval.assignment_review import review_assignments

            print(json.dumps(review_assignments(arguments.run, arguments.study), indent=2, allow_nan=False))
            return
        if arguments.command == "assignment-round":
            from swarmtrace.reproduce.assignment_round import run_assignment_round

            run_assignment_round(arguments.out, arguments.benchmarks, arguments.data, arguments.workers,
                                 checks_only=arguments.checks_only)
            return
        if arguments.command == "recipient-round":
            from swarmtrace.eval.recipient import run_recipient_study

            run_recipient_study(arguments.benchmark_dir, output_dir=arguments.out)
            return
        if arguments.command == "dispatch-contract":
            from swarmtrace.eval.recipient_dispatch import run_dispatch_study

            run_dispatch_study(arguments.benchmark_dir, output_dir=arguments.out)
            return
        if arguments.command == "dispatch-workflows":
            from swarmtrace.reproduce.dispatch_workflows import run_public_dispatch

            run_public_dispatch(arguments.study, arguments.source_dir, arguments.out,
                                fetch=arguments.fetch, review_only=arguments.review_only)
            return
        if arguments.command == "dispatch-reviews":
            from swarmtrace.eval.dispatch_reviews import run_dispatch_reviews

            run_dispatch_reviews(arguments.study, arguments.out,
                                 review_one=arguments.review_one, review_two=arguments.review_two)
            return
        if arguments.command == "approval-text":
            from swarmtrace.eval.approval_text import run_approval_text

            run_approval_text(arguments.study, arguments.out)
            return
        if arguments.command == "review-hook-events":
            from swarmtrace.eval.hook_files import review_hook_file

            result = review_hook_file(arguments.events, arguments.provider, show_links=arguments.show_links)
            print(json.dumps(result, indent=2, allow_nan=False))
            return
        if arguments.command == "native-hook-benchmark":
            from swarmtrace.reproduce.native_hooks import run_native_hook_benchmark

            run_native_hook_benchmark(arguments.source_dir, arguments.out, fetch=arguments.fetch)
            return
        if arguments.command == "operation-authority":
            from swarmtrace.reproduce.operation_authority import run_operation_authority

            run_operation_authority(arguments.study, arguments.dispatch_study, arguments.source_dir,
                                    arguments.out, fetch=arguments.fetch)
            return
        if arguments.command == "grant-policy":
            from swarmtrace.reproduce.grant_policy import run_grant_policy

            run_grant_policy(arguments.out, arguments.prior, arguments.workers)
            return
        if arguments.command == "grant-round":
            from swarmtrace.reproduce.grant_study import run_grant_study

            run_grant_study(arguments.out, arguments.study, arguments.data, arguments.previous_calibration,
                            arguments.workers, checks_only=arguments.checks_only)
            return
        if arguments.command == "read-round":
            from swarmtrace.reproduce.read_study import run_read_study

            run_read_study(arguments.out, arguments.workers,
                           attribution_only=arguments.attribution_only)
            return
        if arguments.command == "calibrate-read-alerts":
            from swarmtrace.reproduce.read_calibration import run_read_calibration

            run_read_calibration(arguments.out, arguments.study, arguments.data, arguments.workers)
            return
        if arguments.command == "evasion":
            run_evasion(arguments.out, EvasionConfig(seed=arguments.seed,
                                                    workers=arguments.workers))
            return
        if arguments.command == "sharing-sweep":
            config = SharingSweepConfig(seed=arguments.seed, workers=arguments.workers)
            if arguments.render_from is not None:
                render_sharing_sweep_from_tables(arguments.render_from, config)
            else:
                run_sharing_sweep(arguments.out, config)
            return
        if arguments.command == "scope":
            from swarmtrace.reproduce.scope import ScopeConfig, run_scope, time_scope_runs

            config = ScopeConfig(seed=arguments.seed, workers=arguments.workers)
            if arguments.time_runs is not None:
                time_scope_runs(arguments.out, config, arguments.time_runs)
            else:
                run_scope(arguments.out, config)
            return
        if arguments.command == "reproduce":
            reproduce_commands.run(arguments)
            return
        if arguments.command == "containment":
            containment_commands.run(arguments)
            return
        if arguments.command in eval_commands.COMMANDS:
            eval_commands.run(arguments)
            return
        if arguments.command == "sweep":
            from swarmtrace.sim.sweep import condition_grid, run_sweep

            grid = condition_grid(
                group_sizes=arguments.group_sizes, coordinated_groups=arguments.coordinated_groups,
                channels=arguments.channels, topologies=arguments.topologies,
                n_ticks=arguments.ticks,
                benign_credential_sharing=arguments.benign_credential_sharing,
                scope=arguments.scope,
            )
            capture = {"capture_authorization": True} if arguments.capture_authorization else {}
            run_sweep(arguments.out, arguments.seed, runs_per_condition=arguments.runs_per_condition,
                      conditions=grid, **capture)
            return
        generate_synthetic_runs(arguments.out, arguments.runs, arguments.seed, arguments.signal)
    except ValueError as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
