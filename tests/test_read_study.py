import json
from dataclasses import replace
from pathlib import Path
from shutil import copyfile

import pandas as pd
import pytest

from swarmtrace.cli import main
from swarmtrace.eval import read_attribution
from swarmtrace.reproduce import read_study
from swarmtrace.reproduce.read_round import CANDIDATE, CONFIRMATION_SEEDS
from swarmtrace.trace.authorization import read_authorization
from swarmtrace.trace.io import RunPaths


def test_sweep_and_review_cli_work_without_outcomes_or_labels(tmp_path):
    main(["sweep", "--seed", "42", "--out", str(tmp_path / "runs"), "--group-sizes", "0",
          "--coordinated-groups", "1", "--channels", "message", "--topologies", "peer",
          "--benign-credential-sharing", "100", "--scope", "on", "--capture-authorization"])
    paths = RunPaths(next((tmp_path / "runs").glob("*/trace.jsonl")).parent)
    audit = read_authorization(paths.authorization)
    minimal = RunPaths(tmp_path / "observations")
    minimal.run_dir.mkdir()
    copyfile(paths.trace, minimal.trace)
    output = tmp_path / "reads.csv"
    main(["review-reads", "--run", str(minimal.run_dir), "--out", str(output)])
    legacy = pd.read_csv(output)
    assert len(legacy) == len(audit.decisions) > 0
    assert set(legacy.basis) == {"unknown"} and legacy.out_of_scope.isna().all()

    copyfile(paths.authorization, minimal.authorization)
    main(["review-reads", "--run", str(minimal.run_dir), "--out", str(output)])
    known = pd.read_csv(output)
    assert set(known.basis) >= {"ordinary", "grant"}
    assert tuple(known.seq) == tuple(d.seq for d in audit.decisions)
    main(["review-reads", "--run", str(minimal.run_dir), "--until-tick", "30",
          "--breaches-only", "--out", str(output)])
    breaches = pd.read_csv(output)
    assert list(breaches.seq) == list(known.loc[(known.tick <= 30) & known.out_of_scope.eq(True), "seq"])
    with pytest.raises(SystemExit):
        main(["review-reads", "--run", str(minimal.run_dir), "--out", str(minimal.labels)])
    assert not minimal.labels.exists()


def test_attribution_study_exercises_gate_and_role_twins(tmp_path, monkeypatch):
    jobs = read_study.make_identical_jobs
    monkeypatch.setattr(read_study, "make_identical_jobs", lambda config: jobs(config)[:2])
    out = tmp_path / "attribution"
    main(["read-round", "--attribution-only", "--workers", "1", "--out", str(out)])
    counts = pd.read_csv(out / "attribution-summary.csv").set_index("method")
    assert counts.loc["gateway", ["correct_attributions", "wrong_attributions"]].tolist() == [12, 0]
    assert pd.read_csv(out / "role-twins.csv").identical.tolist() == [True, True]
    assert not (out / "workflow").exists()


def test_attribution_contract_failure_is_reported_before_confirmation(tmp_path, monkeypatch):
    original = read_attribution.read_evidence

    def false_grant_attribution(*args, **kwargs):
        reads = original(*args, **kwargs)
        reads[0] = replace(reads[0], basis="unknown", out_of_scope=None)
        return reads

    monkeypatch.setattr(read_attribution, "read_evidence", false_grant_attribution)
    out = tmp_path / "failed"
    with pytest.raises(ValueError, match="ordinary_before_login"):
        read_study.run_read_study(out, 1)
    assert not out.exists()


def test_published_read_scorecard_replays_from_held_out_scores(tmp_path):
    source = Path(__file__).resolve().parents[1] / "benchmarks" / "read-authorization"
    workflow = tmp_path / "workflow"
    workflow.mkdir()
    for name in ["protocol.json", *(f"{seed}.csv.gz" for seed in CONFIRMATION_SEEDS)]:
        copyfile(source / "workflow" / name, workflow / name)
    read_study._write_scorecard(tmp_path)
    for name in ("scorecard.csv", "decision.json"):
        assert (source / name).read_bytes() == (tmp_path / name).read_bytes()
    pooled = pd.read_csv(tmp_path / "scorecard.csv").set_index("population").loc["pooled"]
    assert pooled[["candidate_true_positives", "candidate_false_positives",
                   "candidate_small_true_positives", "candidate_primary_hits_at_budget",
                   "primary_gained", "primary_lost"]].tolist() == [309, 33, 94, 48, 0, 0]


@pytest.mark.parametrize(("varies", "observed", "qualifies"), [
    (False, 0, False), (True, 0, False), (False, 1, False), (True, 1, True),
])
def test_round_qualifies_paired_result_with_feature_support(tmp_path, varies, observed, qualifies):
    workflow = tmp_path / "workflow"
    workflow.mkdir()
    for seed in CONFIRMATION_SEEDS:
        rows = []
        for i in range(330):
            positive = i < 300
            shared = dict(task="scope", test_set="independent", split_seed=20261120,
                          run_id=f"{seed}-{i}", positive=positive, hard_control=not positive,
                          small_positive=positive, score=float(positive), threshold=.5)
            for name in ("logistic", CANDIDATE):
                rows.append(dict(shared, detector=name))
        pd.DataFrame(rows).to_csv(workflow / f"{seed}.csv.gz", index=False)
    (workflow / "protocol.json").write_text(json.dumps({
        "feature_varies_in_fit": varies, "confirmation_nonzero_runs": observed,
    }), encoding="utf-8")
    read_study._write_scorecard(tmp_path)
    decision = json.loads((tmp_path / "decision.json").read_text(encoding="utf-8"))
    scores = pd.read_csv(tmp_path / "scorecard.csv")
    assert decision["paired_evidence"] == "below_minimum"
    assert decision["counts_toward_diminishing_returns"] is qualifies
    assert decision["round_evidence"] == ("below_minimum" if qualifies else "insufficient_feature_support")
    assert scores.loc[scores.population == "pooled", "round_evidence"].item() == decision["round_evidence"]
    assert scores.loc[scores.population == "grid", "source"].tolist() == [
        f"workflow/{seed}.csv.gz" for seed in CONFIRMATION_SEEDS]
