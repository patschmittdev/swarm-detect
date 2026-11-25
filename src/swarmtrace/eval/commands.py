import argparse
from pathlib import Path

from swarmtrace.trace.tiers import Tier

from .data import feature_table
from .diagnostics import write_split_stability
from .harness import FEATURE_SETS, EvalConfig, evaluate
from .report import write_report

COMMANDS = ("features", "eval", "compare-detectors", "benchmark-round", "review-reads")
TIERS = tuple(tier.value for tier in Tier)


def add_parsers(commands: argparse._SubParsersAction) -> None:
    comparison = commands.add_parser(
        "compare-detectors", help="Compare audit-log and scope detectors on held-out runs")
    comparison.add_argument("--data", type=Path, default=Path("data"),
                            help="Recorded study root containing dataset/main and scope")
    comparison.add_argument("--seed", type=int, required=True, help="Archive split and fit seed")
    comparison.add_argument("--test-tables", type=Path,
                            help="Independent test root containing main and scope run tables")
    comparison.add_argument("--out", type=Path, help="Write CSV to this file (default stdout)")
    comparison.add_argument("--scores-out", type=Path,
                            help="Write per-run scores for the independent test tables")
    round_parser = commands.add_parser(
        "benchmark-round", help="Compare one candidate with the incumbent on paired held-out scores")
    round_parser.add_argument("--scores", type=Path, nargs="+", required=True,
                              help="One independent score CSV per disjoint grid")
    round_parser.add_argument("--task", choices=("main", "scope"), required=True)
    round_parser.add_argument("--reference", default="logistic")
    round_parser.add_argument("--candidate", required=True)
    round_parser.add_argument("--min-gain", type=float,
                              help="Prespecified minimum absolute recall gain (main 0.03, scope 0.01)")
    round_parser.add_argument("--out", type=Path, help="Write CSV to this file (default stdout)")
    review = commands.add_parser("review-reads", help="Review authorizations for successful reads")
    review.add_argument("--run", type=Path, required=True, help="Directory containing trace.jsonl")
    review.add_argument("--until-tick", type=int, help="Last observable tick, inclusive")
    review_mode = review.add_mutually_exclusive_group()
    review_mode.add_argument("--breaches-only", action="store_true",
                             help="Show only verified reads outside the authorized grant scope")
    review_mode.add_argument("--by-grant", action="store_true",
                             help="Summarize distinct files by grant, including ordinary and unknown reads")
    review.add_argument("--out", type=Path, help="Write CSV to this file (default stdout)")
    features = commands.add_parser("features", help="Write a feature matrix read from traces")
    features.add_argument("--runs", type=Path, required=True)
    features.add_argument("--tier", choices=TIERS, required=True)
    features.add_argument("--level", choices=("agent", "pair", "run"), required=True)
    features.add_argument("--out", type=Path, required=True)
    evaluation = commands.add_parser("eval", help="Fit detectors and write results tables")
    evaluation.add_argument("--runs", type=Path, required=True)
    evaluation.add_argument("--out", type=Path, required=True)
    evaluation.add_argument("--seed", type=int, required=True)
    evaluation.add_argument("--tiers", nargs="+", choices=TIERS, default=list(TIERS))
    evaluation.add_argument("--hold-out", nargs="*", default=[])
    evaluation.add_argument("--test-fraction", type=float, default=EvalConfig.test_fraction)
    evaluation.add_argument("--bootstrap", type=int, default=EvalConfig.n_bootstrap)
    evaluation.add_argument("--families", nargs="+", choices=FEATURE_SETS,
                            default=list(FEATURE_SETS))
    evaluation.add_argument("--workers", type=int, default=1)
    evaluation.add_argument("--checkpoint-every", type=int, default=EvalConfig.checkpoint_every,
                            help="Raw traces only; recorded datasets retain their saved cadence")
    evaluation.add_argument("--split-stability", action="store_true",
                            help="Recorded data only: write a 20-split full-trace AUROC diagnostic")


def run(arguments: argparse.Namespace) -> None:
    if arguments.command in ("compare-detectors", "benchmark-round", "review-reads"):
        if arguments.command == "compare-detectors":
            from .comparison import compare_detectors

            if (arguments.out is not None and arguments.scores_out is not None
                    and arguments.out.resolve() == arguments.scores_out.resolve()):
                raise ValueError("summary and per-run scores need different output paths")
            table = compare_detectors(arguments.data, arguments.seed, arguments.test_tables,
                                      scores_out=arguments.scores_out)
        elif arguments.command == "benchmark-round":
            from .rounds import benchmark_round

            if arguments.out is not None and any(
                path.resolve() == arguments.out.resolve() for path in arguments.scores
            ):
                raise ValueError("round output must differ from its input score files")
            table = benchmark_round(arguments.scores, arguments.task, arguments.reference,
                                    arguments.candidate, arguments.min_gain)
        else:
            table = _review_reads(arguments)
        if arguments.out is None:
            print(table.to_csv(index=False, lineterminator="\n"), end="")
        else:
            arguments.out.parent.mkdir(parents=True, exist_ok=True)
            table.to_csv(arguments.out, index=False, lineterminator="\n")
        return
    if arguments.command == "features":
        table = feature_table(arguments.runs, arguments.level, Tier(arguments.tier))
        arguments.out.parent.mkdir(parents=True, exist_ok=True)
        table.to_csv(arguments.out, lineterminator="\n")
        return
    config = EvalConfig(
        tiers=tuple(Tier(tier) for tier in arguments.tiers),
        seed=arguments.seed,
        test_fraction=arguments.test_fraction,
        hold_out=tuple(arguments.hold_out),
        n_bootstrap=arguments.bootstrap,
        families=tuple(arguments.families), workers=arguments.workers,
        checkpoint_every=arguments.checkpoint_every,
    )
    if arguments.split_stability:
        write_split_stability(arguments.runs, arguments.out, config)
    else:
        write_report(evaluate(arguments.runs, config), arguments.out)


def _review_reads(arguments: argparse.Namespace):
    from collections import defaultdict

    import pandas as pd

    from swarmtrace.features.grant_scope import grant_scope_counts
    from swarmtrace.features.read_evidence import read_evidence
    from swarmtrace.trace.authorization import read_authorization
    from swarmtrace.trace.io import RunPaths, read_trace

    paths = RunPaths(arguments.run)
    if arguments.out is not None:
        artifacts = (paths.trace, paths.authorization, paths.context, paths.labels,
                     paths.manifest, paths.outcomes, paths.interventions)
        if arguments.out.resolve() in {path.resolve() for path in artifacts}:
            raise ValueError("review output must differ from the run artifacts")
    if not paths.trace.is_file():
        raise ValueError(f"run is missing its trace: {paths.trace}")
    trace = read_trace(paths.trace, Tier.V1)
    try:
        authorization = read_authorization(paths.authorization)
    except FileNotFoundError:
        authorization = None
    reads = read_evidence(trace, authorization, until_tick=arguments.until_tick)
    if arguments.by_grant:
        groups = defaultdict(list)
        for read in reads:
            groups[read.basis, read.grant_id].append(read)
        rows = []
        for (basis, grant_id), group in sorted(groups.items()):
            excluded = None if basis == "unknown" else grant_scope_counts(group).distinct_grant_files
            rows.append((trace.run_id, basis, grant_id, len(group), len({r.file for r in group}), excluded))
        summary = pd.DataFrame(rows, columns=("run_id", "basis", "grant_id", "successful_reads",
                                              "distinct_files", "distinct_excluded_files"))
        summary["distinct_excluded_files"] = summary.distinct_excluded_files.astype("Int64")
        return summary
    columns = ("run_id", "seq", "tick", "agent", "file", "basis", "grant_id", "out_of_scope")
    return pd.DataFrame.from_records(
        [(trace.run_id, r.seq, r.tick, r.agent, r.file, r.basis, r.grant_id, r.out_of_scope)
         for r in reads if not arguments.breaches_only or r.out_of_scope is True], columns=columns)
