import argparse
from pathlib import Path

from .config import ReproduceConfig
from .pipeline import reproduce


def add_parser(commands: argparse._SubParsersAction) -> None:
    parser = commands.add_parser("reproduce", help="Run and record the credential-relay experiment")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--workers", type=int, default=ReproduceConfig.workers)
    parser.add_argument("--runs-per-condition", type=int,
                        default=ReproduceConfig.runs_per_condition)
    parser.add_argument("--control-repeats", type=int, default=ReproduceConfig.control_repeats)
    parser.add_argument("--ticks", type=int, default=ReproduceConfig.n_ticks)
    parser.add_argument("--checkpoint-every", type=int, default=ReproduceConfig.checkpoint_every)
    parser.add_argument("--bootstrap", type=int, default=ReproduceConfig.n_bootstrap)
    parser.add_argument("--shuffle-repeats", type=int, default=ReproduceConfig.shuffle_repeats)
    parser.add_argument("--sample-runs", type=int, default=ReproduceConfig.sample_runs)
    parser.add_argument("--hold-out", nargs="*", default=list(ReproduceConfig.hold_out))
    parser.add_argument("--readme", type=Path,
                        help="Paste a short results block between the generated-results markers "
                             "of the given Markdown file (the full headline stays in headline.md)")


def run(arguments: argparse.Namespace) -> None:
    config = ReproduceConfig(
        seed=arguments.seed, workers=arguments.workers,
        runs_per_condition=arguments.runs_per_condition, control_repeats=arguments.control_repeats,
        n_ticks=arguments.ticks, checkpoint_every=arguments.checkpoint_every,
        n_bootstrap=arguments.bootstrap, shuffle_repeats=arguments.shuffle_repeats,
        sample_runs=arguments.sample_runs, hold_out=tuple(arguments.hold_out),
    )
    reproduce(arguments.out, config, readme=arguments.readme)
