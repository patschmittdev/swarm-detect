import json
import math
from pathlib import Path

import pandas as pd
import pytest

from swarmtrace.cli import main
from swarmtrace.eval.read_attribution import GRANT_A, _challenge_engine
from swarmtrace.eval.rounds import benchmark_round
from swarmtrace.reproduce import grant_study
from swarmtrace.trace.authorization import write_authorization


def test_review_by_grant_deduplicates_repeated_files_and_keeps_unknown(tmp_path):
    engine, _ = _challenge_engine()
    engine.run(18, tmp_path / "trace.jsonl")
    csv = tmp_path / "by-grant.csv"
    args = ["review-reads", "--run", str(tmp_path), "--by-grant", "--out", str(csv)]
    main(args)
    unknown = pd.read_csv(csv)
    assert unknown.basis.tolist() == ["unknown"] and unknown.distinct_excluded_files.isna().all()
    write_authorization(tmp_path / "authorization.json", engine.read_audit)
    main([*args, "--until-tick", "10"])
    summary = pd.read_csv(csv)
    first = summary.loc[summary.grant_id == GRANT_A].iloc[0]
    assert first.successful_reads == 4 and first.distinct_excluded_files == 2
    assert summary.loc[summary.basis == "ordinary", "distinct_excluded_files"].item() == 0
    assert summary.loc[summary.basis == "unknown", "distinct_excluded_files"].isna().all()


def test_checks_only_replays_real_role_pair_and_labelled_prefixes(tmp_path, monkeypatch):
    jobs = grant_study.make_identical_jobs
    monkeypatch.setattr(grant_study, "make_identical_jobs", lambda config: jobs(config)[:1])
    out = tmp_path / "controls"
    main(["grant-round", "--out", str(out), "--workers", "1", "--checks-only"])
    twins = pd.read_csv(out / "role-twins.csv")
    assert twins.native_identical.tolist() == twins.overlap_identical.tolist() == [True]
    fixtures = pd.read_csv(out / "attribution-checks.csv")
    assert fixtures.visible_max.tolist() == fixtures.verified_max.tolist()
    assert not (out / "protocol.json").exists()
    with pytest.raises(SystemExit):
        main(["grant-round", "--out", str(out), "--checks-only"])


def test_published_grant_thresholds_and_paired_evidence_replay():
    root = Path(__file__).resolve().parents[1] / "benchmarks" / "grant-scope"
    protocol = json.loads((root / "protocol.json").read_bytes())
    seen_by_view = {}
    for view in ("native", "overlap"):
        path = root / view
        cal = pd.read_csv(path / "calibration-controls.csv.gz", dtype={"score": str, "run_id": str})
        for detector, rows in cal.groupby("detector"):
            assert len(rows) == rows.run_id.nunique() == 648 and not rows.positive.any()
            rank = math.ceil((len(rows) + 1) * (1 - protocol["max_fpr"]))
            cutoff = sorted(map(float, rows.score))[rank - 1]
            assert cutoff == protocol["thresholds"][view][detector]
        scores = [path / f"{seed}.csv.gz" for seed in protocol["confirmation_seeds"]]
        result = benchmark_round(scores, "scope", protocol["reference"], protocol["candidate"])
        saved = pd.read_csv(path / "scorecard.csv")
        for col in ("primary_gained", "primary_lost", "candidate_true_positives",
                    "candidate_false_positives", "candidate_primary_hits_at_budget", "evidence"):
            assert result[col].tolist() == saved[col].tolist()
        assert saved.iloc[-1].primary_positives == 540
        ids = set(pd.concat([pd.read_csv(file, usecols=["run_id"], dtype=str) for file in scores]).run_id)
        assert len(ids) == 3780 and ids.isdisjoint(cal.run_id)
        seen_by_view[view] = ids
        assert saved.iloc[-1].round_evidence == protocol["decisions"][view]["round_evidence"]
    assert seen_by_view["native"] == seen_by_view["overlap"]
