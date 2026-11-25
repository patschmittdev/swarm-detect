"""Inspect the facts and optional fitted score for each exercised grant in a saved run."""

import json
from pathlib import Path

from swarmtrace.detect.assignment import AssignmentLogistic
from swarmtrace.features.assignment import ASSIGNMENT_COLUMNS, assignment_features
from swarmtrace.trace.authorization import read_authorization
from swarmtrace.trace.context import read_context
from swarmtrace.trace.io import RunPaths, read_trace
from swarmtrace.trace.tiers import Tier


def review_assignments(directory: Path, study: Path | None = None) -> dict:
    paths = RunPaths(directory)
    if not all(p.is_file() for p in (paths.trace, paths.context)):
        raise ValueError("assignment review needs trace.jsonl and its C2 context.json")
    trace = read_trace(paths.trace, Tier.V1)
    audit = read_authorization(paths.authorization) if paths.authorization.is_file() else None
    bag = assignment_features(trace, read_context(paths.context), audit)
    rows = bag.features.copy()
    result = dict(run_id=trace.run_id, capture_present=bag.capture_present,
                  successful_reads=bag.successful_reads, grant_reads=bag.grant_reads,
                  ordinary_reads=bag.ordinary_reads, unknown_reads=bag.unknown_reads,
                  missing_decisions=bag.missing_reads)
    if study is not None:
        source = study / "protocol.json"
        if not source.is_file():
            raise ValueError(f"assignment study needs a protocol at {source}")
        protocol = json.loads(source.read_bytes())
        if (protocol.get("candidate") != "assignment-logistic"
                or protocol.get("assignment_columns") != list(ASSIGNMENT_COLUMNS)):
            raise ValueError("unexpected assignment model or input columns")
        model = AssignmentLogistic.from_parameters(protocol.get("model"), len(ASSIGNMENT_COLUMNS))
        scores = model.assignment_scores(rows.to_numpy())
        rows["review_score"] = scores
        result["max_observed_score"] = float(scores.max()) if len(scores) else None
        rows = rows.sort_values("review_score", ascending=False, kind="stable")
    result["assignments"] = rows.reset_index().to_dict(orient="records")
    return result
