import json
from pathlib import Path

import pytest

from swarmtrace.reproduce.authority_vectors import (
    ARCHIVE_SHA256,
    _publish,
    check_vectors,
    consumption_status,
)


def approval():
    return {"approvalId": "permit", "session": "work", "actionDigest": {"sha256": "a" * 64}}


def packed(value):
    return json.dumps(value).encode("utf-8")


def test_identity_requires_approval_session_and_action_across_generations():
    request = approval()
    same_metadata_changed = {**request, "extra": "reissued"}
    for unrelated in ({**request, "session": "elsewhere"},
                      {**request, "actionDigest": {"sha256": "b" * 64}}):
        assert consumption_status(request, packed([unrelated])) == ("no_match", "already_spent")
    assert consumption_status(request, packed([{**request, "approvalId": "another"}])) == (
        "no_match", "no_match"
    )
    history = {"current": [], "older": [same_metadata_changed]}
    assert consumption_status(request, packed(history)) == ("already_spent", "already_spent")
    assert consumption_status(request, b"[]") == ("no_match", "no_match")


@pytest.mark.parametrize("state", [
    b'{"truncated":', b'null', b'[null]', b'{"compacted":{"entryCount":1}}',
    packed([{**approval(), "actionDigest": {"sha256": "A" * 64}}]),
    packed([{**approval(), "actionDigest": {"sha256": "a" * 64, "other": "ignored"}}]),
    packed({"current": [approval()], "prior": [{**approval(), "session": ""}]}),
])
def test_invalid_entries_or_generations_preempt_a_consumption_decision(state):
    assert consumption_status(approval(), state) == ("unusable_view", None)


def test_invalid_request_is_distinct_from_invalid_consumption_state():
    with pytest.raises(ValueError, match="approval input"):
        consumption_status({"approvalId": "incomplete"}, b"[]")


def test_archive_identity_precedes_parsing():
    with pytest.raises(ValueError, match="SHA-256"):
        check_vectors(b"unverified")


def test_report_publication_accepts_a_retry_and_preserves_conflicting_content(tmp_path):
    path = tmp_path / "output" / "report.json"
    _publish(path, b"initial")
    _publish(path, b"initial")
    with pytest.raises(ValueError, match="conflicting"):
        _publish(path, b"other")
    assert path.read_bytes() == b"initial"
    assert list(path.parent.iterdir()) == [path]


def test_release_report_preserves_publishers_refusal_reasons():
    root = Path(__file__).resolve().parents[1]
    report = json.loads((root / "benchmarks/operation-authority/consumption-vectors.json").read_bytes())
    assert report["source"]["archive_sha256"] == ARCHIVE_SHA256
    assert report["counts"] == {
        "id_only_false_spent": 2, "id_only_matches_on_readable": 4,
        "independent_swarm_accuracy_rounds": 0, "match_publisher": 12, "no_match": 3,
        "readable_for_id_only": 6, "spent": 3, "unusable_supplied_view": 6, "vectors": 12,
    }
    actual = {row["name"]: row for row in report["vectors"]}
    groups = {
        "already_spent": {"F10", "F13", "F77"},
        "no_match": {"V1-accept", "G14a", "G14b"},
        "unusable_view": {"F71", "G16c", "CS1", "CS2", "CS3", "CS4"},
    }
    assert set(actual) == set.union(*groups.values())
    for status, names in groups.items():
        assert all(actual[name]["reference"] == actual[name]["full_identity"] == status for name in names)
