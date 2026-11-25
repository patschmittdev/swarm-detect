from dataclasses import replace

import pytest

from swarmtrace.eval import grant_challenge as challenge


def test_gateway_counts_match_known_pairs_for_partial_and_complete_capture():
    cases = challenge.grant_challenge()
    assert len(cases) == 33
    assert (cases.visible_grant_files == cases.verified_grant_files).all()
    assert (cases.visible_max == cases.verified_max).all()
    complete, missing = (cases[(cases.workflow == "overlapping_review") & (cases.capture == name)]
                         .set_index("tick") for name in ("complete", "withheld"))
    assert complete.verified_max.tolist() == [0, 0, 1, 1, 1, 1, 2, 2, 2, 2, 2, 2, 2, 2]
    assert complete.verified_grant_files.tolist() == [0, 0, 1, 1, 1, 1, 2, 2, 2, 2, 3, 4, 5, 6]
    assert missing.loc[15, ["truth_grant_files", "verified_grant_files"]].tolist() == [4, 3]
    assert missing.loc[17, ["truth_grant_files", "verified_grant_files"]].tolist() == [6, 5]
    assert complete.loc[17, ["grant_reads", "ordinary_reads", "unknown_reads"]].tolist() == [11, 2, 1]
    assert missing.loc[17, ["grant_reads", "ordinary_reads", "unknown_reads"]].tolist() == [10, 2, 2]
    assert complete.loc[17, "truth_indeterminate_reads"] == missing.loc[17, "truth_indeterminate_reads"] == 1

    approved = cases[cases.workflow == "all_approved"]
    assert set(approved.truth_max) == set(approved.verified_max) == {0}
    assert approved.legacy_borrowed_max.tolist() == [1, 2, 3, 5, 5]
    assert approved.iloc[-1][["grant_reads", "ordinary_reads", "unknown_reads"]].tolist() == [4, 1, 0]


def test_challenge_rejects_a_wrong_grant_even_if_the_aggregate_maximum_is_the_same(monkeypatch):
    original = challenge.grant_scope_counts

    def misassign(*args, **kwargs):
        counts = original(*args, **kwargs)
        return replace(counts, excluded_files=frozenset(("wrong", file) for _, file in counts.excluded_files))

    monkeypatch.setattr(challenge, "grant_scope_counts", misassign)
    with pytest.raises(ValueError, match="single_worker_mistake"):
        challenge.grant_challenge()
