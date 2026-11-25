"""Run the read-attribution controls before scoring held-out workflows."""

import json
from functools import partial
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from swarmtrace.eval.recorded import write_json
from swarmtrace.eval.rounds import benchmark_round

from .scope import ScopeConfig, _identical_pair, _map, _worker_threads, make_identical_jobs


def _write_scorecard(study: Path) -> None:
    from .read_round import CANDIDATE, CONFIRMATION_SEEDS, REFERENCE

    workflow = study / "workflow"
    paths = [workflow / f"{seed}.csv.gz" for seed in CONFIRMATION_SEEDS]
    scores = benchmark_round(paths, "scope", REFERENCE, CANDIDATE)
    scores["source"] = scores.source.replace(
        {str(path): path.relative_to(study).as_posix() for path in paths})
    protocol = json.loads((workflow / "protocol.json").read_text(encoding="utf-8"))
    pooled = scores.population == "pooled"
    paired = scores.loc[pooled, "evidence"].item()
    support = protocol["feature_varies_in_fit"] and protocol["confirmation_nonzero_runs"] > 0
    evidence = paired if support else "insufficient_feature_support"
    scores["round_evidence"] = ""
    scores.loc[pooled, "round_evidence"] = evidence
    scores.to_csv(study / "scorecard.csv", index=False, lineterminator="\n")
    write_json(study / "decision.json", {
        "candidate": CANDIDATE, "paired_evidence": paired, "round_evidence": evidence,
        "feature_varies_in_fit": protocol["feature_varies_in_fit"],
        "confirmation_nonzero_runs": protocol["confirmation_nonzero_runs"],
        "counts_toward_diminishing_returns": evidence == "below_minimum",
    })


def run_read_study(out: Path, workers: int = 4, *, attribution_only: bool = False) -> None:
    """Publish a complete study into a new directory, or run just its attribution controls."""
    from swarmtrace.eval.read_attribution import attribution_challenge, summarize_attribution

    if out.exists():
        raise ValueError(f"read-round output already exists: {out}")
    config = ScopeConfig(seed=20261120, workers=workers)
    out.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=out.parent) as temporary:
        work = Path(temporary)
        study = work / "study"
        study.mkdir()
        cases = attribution_challenge(check_gateway=True)
        cases.to_csv(study / "attribution-cases.csv", index=False, lineterminator="\n")
        summarize_attribution(cases).to_csv(
            study / "attribution-summary.csv", index=False, lineterminator="\n")

        pairs = make_identical_jobs(config)
        with _worker_threads():
            twins = _map(partial(_identical_pair, capture_authorization=True),
                         [(job, work / "raw") for job in pairs], workers)
        failed = [twin for twin in twins if twin.mismatches]
        if failed:
            first = failed[0]
            raise ValueError(f"role flip changed observable bytes for {len(failed)} pairs, "
                             f"including {first.pair}: {', '.join(first.mismatches)}")
        pd.DataFrame([{"pair": t.pair, "seed": t.seed, "identical": True} for t in twins]).to_csv(
            study / "role-twins.csv", index=False, lineterminator="\n")

        if not attribution_only:
            from .read_round import run_read_round

            run_read_round(study / "workflow", workers)
            _write_scorecard(study)
        study.rename(out)
