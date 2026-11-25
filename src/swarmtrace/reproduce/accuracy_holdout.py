"""Generate independent V1 test tables on the published main and scope simulation grids."""

import argparse
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from swarmtrace.detect import COMPONENT_COLUMN
from swarmtrace.detect.components import component_score
from swarmtrace.eval.data import RunRecord
from swarmtrace.eval.recorded import TableRecord, write_run_table
from swarmtrace.features import feature_columns, pair_features, run_features
from swarmtrace.features.spec import AGGREGATION, SCOPE
from swarmtrace.sim.runner import run_one
from swarmtrace.trace.context import ContextLevel, read_context
from swarmtrace.trace.io import RunPaths, read_labels, read_manifest, read_trace
from swarmtrace.trace.tiers import Tier

from .config import ReproduceConfig, RunJob, make_jobs
from .scope import ScopeConfig, _map, _worker_threads, make_scope_jobs


def _holdout_row(job: RunJob) -> tuple[pd.DataFrame, TableRecord]:
    with TemporaryDirectory() as temporary:
        paths = RunPaths(run_one(job.condition, job.seed, temporary))
        trace = read_trace(paths.trace, Tier.V1)
        aggregation = list(feature_columns("run", Tier.V1, (AGGREGATION,)))
        if job.dataset == "scope":
            context = read_context(paths.context, ContextLevel.C2)
            scope = feature_columns("run", Tier.V1, (SCOPE,), context=context.level)
            frame = run_features(trace, context=context)[[*aggregation, *scope]].rename(
                columns={column: f"{column}__C2" for column in scope}
            )
        else:
            frame = run_features(trace)[aggregation].copy()
            frame[COMPONENT_COLUMN] = component_score(pair_features(trace))
        labels, manifest = read_labels(paths.labels), read_manifest(paths.manifest)
        if not trace.run_id == labels.run_id == manifest.run_id:
            raise ValueError("holdout trace, labels and manifest have different run ids")
        record = RunRecord(trace.run_id, paths.trace, labels, manifest.condition)
        return frame, TableRecord(record.run_id, record.positive, record.condition)


def write_holdout_tables(out: Path, seed: int, workers: int = 4) -> None:
    """Write the two compact test tables to a new directory once all runs succeed."""
    out = Path(out)
    if out.exists():
        raise ValueError(f"holdout output already exists: {out}")
    main = [job for job in make_jobs(ReproduceConfig(seed=seed, workers=workers))
            if job.dataset == "main"]
    scope = make_scope_jobs(ScopeConfig(seed=seed, workers=workers))
    out.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=out.parent) as temporary, _worker_threads():
        tables = Path(temporary) / "tables"
        for name, jobs in (("main", main), ("scope", scope)):
            rows = _map(_holdout_row, jobs, workers)
            frames, records = zip(*rows, strict=True)
            write_run_table(tables / name / "runs.csv.gz", pd.concat(frames).sort_index(), records)
        tables.rename(out)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--workers", type=int, default=4)
    arguments = parser.parse_args()
    try:
        write_holdout_tables(arguments.out, arguments.seed, arguments.workers)
    except ValueError as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
