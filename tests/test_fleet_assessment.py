import json
import subprocess
import sys
from hashlib import sha256
from math import log

import pytest

from swarmtrace.fleet.baselines import all_baselines
from swarmtrace.fleet.detector import ALERT_THRESHOLD, assess
from swarmtrace.fleet.events import events_from_rows, load_events


def row(seq, token, path, method="GET", *, start=None, end=None, status=200, body=None):
    start = float(seq) if start is None else start
    return {
        "seq": seq,
        "t_start": start,
        "t_end": start if end is None else end,
        "token_id": token,
        "user_agent": "irrelevant",
        "method": method,
        "path": path,
        "query": "",
        "status": status,
        "bytes_in": len(body) if body else 0,
        "bytes_out": 0,
        "write_sha256": sha256(body.encode()).hexdigest() if body is not None else None,
    }


def result(rows):
    return assess(events_from_rows(rows))


def anonymous(rows):
    return [{**request, "token_id": None} for request in rows]


def handoffs():
    return [
        row(1, "a", "/notes/plan", "PUT", body="assign work"),
        row(2, "b", "/notes/plan"),
        row(3, "b", "/notes/result", "PUT", status=201, body="partial results"),
        row(4, "a", "/notes/result"),
        row(5, "a", "/notes/report", "PUT", status=201, body="combined results"),
    ]


def test_handoffs_require_connected_corroboration_and_show_requests():
    assessment = result(handoffs())
    assert ALERT_THRESHOLD == 0.5
    assert assessment.score == 0.75
    assert assessment.alert is True
    assert assessment.groups == [["a", "b"]]
    assert assessment.evidence == [
        {"signal": "read_handoff", "value": 0.75, "seqs": [1, 2, 3]},
        {"signal": "read_handoff", "value": 0.75, "seqs": [3, 4, 5]},
    ]
    lone = result(handoffs()[:3])
    assert lone.score == ALERT_THRESHOLD
    assert lone.alert is False
    assert lone.groups == []

    separate = handoffs()[:3] + [
        row(6, "c", "/notes/second-plan", "PUT", body="other work"),
        row(7, "d", "/notes/second-plan"),
        row(8, "d", "/notes/second-result", "PUT", status=201, body="other results"),
    ]
    assert result(separate).score == ALERT_THRESHOLD
    assert result(separate).groups == []


def test_handoffs_ignore_public_listings_and_terminal_reads():
    requests = handoffs()
    requests[1]["path"] = "/notes"
    requests[3]["path"] = "/notes"
    assert result(requests).evidence == []
    assert result(handoffs()[:2]).evidence == []


def test_handoffs_require_order_and_visible_authorship():
    requests = handoffs()[:3]
    # The read began before the write completed, although the write has the earlier seq.
    requests[0]["t_end"] = 1.9
    requests[1]["t_start"] = 1.5
    assert result(requests).evidence == []
    # A subsequent anonymous version supersedes the identified writer.
    requests = handoffs()[:3] + [
        row(6, None, "/notes/plan", "PUT", start=1.5, body="unknown revision"),
    ]
    assert result(requests).evidence == []


def test_handoffs_require_a_changed_write():
    requests = handoffs()[:2] + [
        row(3, "b", "/notes/plan", "PUT", body="assign work"),
    ]
    assert result(requests).evidence == []
    requests[2] = row(3, "b", "/notes/plan", "PUT", body="assign revised work")
    assert result(requests).evidence[0]["seqs"] == [1, 2, 3]


@pytest.mark.parametrize(
    "status, body, score", [(200, "result", 0.0), (201, "result", 0.5), (201, None, 0.0)],
)
def test_handoffs_require_creation_status_and_digest_without_a_predecessor(status, body, score):
    requests = handoffs()[:2] + [row(3, "b", "/notes/result", "PUT", status=status, body=body)]
    assert result(requests).score == score


def test_handoffs_do_not_treat_a_digestless_replacement_as_changed():
    requests = handoffs()[:2] + [row(3, "b", "/notes/plan", "PUT")]
    assert result(requests).evidence == []


def test_handoffs_keep_the_pending_read_through_a_same_byte_write():
    requests = handoffs()[:2] + [
        row(3, "b", "/notes/plan", "PUT", body="assign work"),
        row(4, "b", "/notes/plan", "PUT", body="assign revised work"),
    ]
    assert result(requests).evidence == [
        {"signal": "read_handoff", "value": 0.5, "seqs": [1, 2, 4]},
    ]

    requests[2]["t_end"] = 3.5
    requests.insert(3, row(4, "b", "/notes/plan", "PUT", start=3.25, end=3.75, body="assign work"))
    requests[4]["seq"] = 5
    assert result(requests).evidence == [
        {"signal": "read_handoff", "value": 0.5, "seqs": [1, 2, 5]},
    ]


def test_handoffs_keep_the_pending_read_through_a_write_overlapping_the_read():
    requests = handoffs()[:2] + [
        row(3, "b", "/notes/draft", "PUT", start=2.25, body="draft"),
        row(4, "b", "/notes/result", "PUT", status=201, body="partial results"),
    ]
    requests[1]["t_end"] = 2.5
    assert result(requests).evidence == [
        {"signal": "read_handoff", "value": 0.5, "seqs": [1, 2, 4]},
    ]


@pytest.mark.parametrize("other_token", ["a", "b", None])
@pytest.mark.parametrize("other_start, other_end", [(0.5, 1), (1.5, 1.75), (1.5, 2.5)])
def test_handoffs_skip_authors_of_overlapping_writes(other_token, other_start, other_end):
    requests = [
        row(1, "a", "/notes/plan", "PUT", start=1, end=2, body="plan a"),
        row(2, other_token, "/notes/plan", "PUT", start=other_start, end=other_end),
        row(3, "c", "/notes/plan"),
        row(4, "c", "/notes/result", "PUT", start=5, status=201, body="results"),
    ]
    assert result(requests).evidence == []

    later = requests[:2] + [row(3, "a", "/notes/plan", "PUT", body="updated plan")]
    later.extend([row(4, "c", "/notes/plan"), {**requests[3], "seq": 5}])
    assert result(later).evidence == [
        {"signal": "read_handoff", "value": 0.5, "seqs": [3, 4, 5]},
    ]


@pytest.mark.parametrize("overlap_token", ["a", "b", "c", None])
def test_handoffs_check_for_writes_that_start_during_the_read(overlap_token):
    requests = [
        row(1, "a", "/notes/plan", "PUT", start=1, end=2, body="plan a"),
        row(2, "c", "/notes/plan", start=3, end=4),
        row(3, overlap_token, "/notes/plan", "PUT", start=3.5, end=4.5),
        row(4, "c", "/notes/result", "PUT", start=5, status=201, body="results"),
    ]
    assert result(requests).evidence == []
    requests[2]["status"] = 403
    assert result(requests).evidence == [
        {"signal": "read_handoff", "value": 0.5, "seqs": [1, 2, 4]},
    ]


def test_handoffs_do_not_chain_reads_during_the_readers_own_writes():
    requests = [
        row(1, "a", "/notes/x", "PUT", start=1, end=2, status=201, body="original"),
        row(2, "b", "/notes/x", start=4),
        row(3, "b", "/notes/x", "PUT", start=3, end=5, body="replaced x"),
        row(4, "b", "/notes/y", "PUT", start=6, status=201, body="second original"),
        row(5, "c", "/notes/y", start=8),
        row(6, "c", "/notes/y", "PUT", start=7, end=9, body="replaced y"),
        row(7, "c", "/notes/z", "PUT", start=10, status=201, body="result"),
    ]
    assessment = result(requests)
    assert assessment.score == 0.0
    assert assessment.groups == []
    assert assessment.evidence == []

    clean = result(request for request in requests if request["seq"] not in (3, 6))
    assert clean.score == 0.75
    assert clean.groups == [["a", "b", "c"]]
    assert [item["seqs"] for item in clean.evidence] == [[1, 2, 4], [4, 5, 7]]


def test_handoffs_require_a_known_predecessor_hash_to_show_a_change():
    requests = [
        row(1, "a", "/notes/plan", "PUT"),
        row(2, "b", "/notes/plan"),
        row(3, "b", "/notes/plan", "PUT", body="updated plan"),
    ]
    assert result(requests).evidence == []


def test_determinism_and_handoffs_without_identity():
    requests = handoffs()
    unchanged = result(requests).to_dict()
    assert result(reversed(requests)).to_dict() == unchanged
    assert json.loads(json.dumps(unchanged)) == unchanged
    assert result([{**r, "user_agent": str(r["seq"])} for r in requests]).to_dict() == unchanged

    assessment = result(anonymous(requests))
    assert assessment.score == 0.0
    assert assessment.alert is False
    assert assessment.groups == []
    assert {"signal": "read_handoff", "reason": "no identity"} in assessment.not_computable
    assert {"signal": "reciprocal_rewrites", "reason": "no identity"} in assessment.not_computable


def alternating_writes():
    return [
        row(seq, "a" if seq % 2 else "b", f"/notes/page-{(seq - 1) // 4}", "PUT",
            body=f"revision {seq}")
        for seq in range(1, 9)
    ]


def test_writes_only_requires_repeated_reciprocity_across_objects():
    requests = alternating_writes()
    assessment = result(requests)
    assert assessment.alert is True
    assert assessment.groups == [["a", "b"]]
    assert assessment.evidence == [
        {"signal": "reciprocal_rewrites", "value": 0.75, "seqs": [1, 2, 3, 4]},
        {"signal": "reciprocal_rewrites", "value": 0.75, "seqs": [5, 6, 7, 8]},
    ]
    assert {item["signal"] for item in assessment.not_computable} == {
        "read_handoff", "resource_interleaving",
    }
    assert result(requests[:2]).score == 0.0
    assert result(requests[:4]).score == 0.25
    assert not result([{**r, "write_sha256": requests[0]["write_sha256"]} for r in requests]).alert
    assert not result(requests[:4] + [{**r, "token_id": "c"} for r in requests[4:]]).alert
    assert not result(requests[:4] + [{**r, "path": "/notes/page-0"} for r in requests[4:]]).alert
    assert not result(anonymous(requests)).alert


@pytest.mark.parametrize("outside_token", ["c", None])
@pytest.mark.parametrize("offsets", [(-3.5, 0.5), (0, 1)])
def test_reciprocity_rejects_outside_writes_intersecting_both_blocks(outside_token, offsets):
    requests = alternating_writes()
    outside = [
        row(9 + i, outside_token, f"/notes/page-{i}", "PUT",
            start=last + offsets[0], end=last + offsets[1])
        for i, last in enumerate((4, 8))
    ]
    assert result(requests).score == 0.75
    assessment = result(requests + outside)
    assert assessment.score == 0.0
    assert assessment.groups == []
    assert assessment.evidence == []


def document_reads(families):
    return [
        row(seq, "a", f"/docs/{family}-{seq}", end=seq + 0.0001)
        for seq, family in enumerate(families, start=1)
    ]


@pytest.mark.parametrize("workers", [2, 3, 6])
def test_merged_sequential_workers_interleave_without_overlap(workers):
    requests = document_reads(list(range(workers)) * 4)
    assessment = result(requests)
    assert assessment.score == 0.75
    assert assessment.alert is True
    assert assessment.groups == [["a"]]
    (evidence,) = assessment.evidence
    assert evidence["signal"] == "resource_interleaving"
    assert evidence["value"] == 0.75
    assert evidence["seqs"] == list(range(1, 4 * workers + 1))
    order = evidence["order"]
    assert order["transitions"] == order["family_changes"] == 4 * workers - 1
    assert order["families"] == order["returning_families"] == workers
    assert order["returns"] == 3 * workers
    assert order["log_null_tail_bound"] <= log(0.01)


def test_interleaving_depends_on_start_order_and_ignores_request_duration():
    requests = document_reads("aabbababbaabababababab")
    assessment = result(requests)
    assert assessment.alert is True
    overlapping = [
        {**r, "seq": len(requests) + 1 - r["seq"], "t_end": 3 * len(requests) - r["seq"]}
        for r in requests
    ]
    (evidence,) = result(reversed(overlapping)).evidence
    assert evidence["value"] == assessment.score
    assert evidence["order"] == assessment.evidence[0]["order"]
    assert evidence["seqs"] == list(range(len(requests), 0, -1))


@pytest.mark.parametrize("families", ["aaaaaabbbbbbcccccc", "aaabaabbbbbbcccccc", "ababab"])
def test_no_interleaving_evidence_for_grouped_reads_or_insufficient_returns(families):
    assessment = result(document_reads(families))
    assert assessment.score == 0
    assert assessment.alert is False
    assert assessment.evidence == []


def test_interleaving_to_one_returning_family_is_uncorroborated():
    requests = document_reads([family for i in range(50) for family in ("hub", f"spoke{i}")])
    assessment = result(requests)
    assert assessment.score == ALERT_THRESHOLD
    assert assessment.alert is False
    (evidence,) = assessment.evidence
    assert evidence["order"]["returning_families"] == 1
    assert evidence["order"]["log_null_tail_bound"] <= log(0.01)


def test_sequential_tokens_interleave_when_pooled_and_stay_capped():
    requests = document_reads(list(range(12)) * 4)
    for request in requests:
        request["token_id"] = str((request["seq"] - 1) % 12)
    identified = result(requests)
    pooled = result(anonymous(requests))
    for assessment in (identified, pooled):
        assert assessment.alert is False
        assert assessment.groups == []
    assert identified.evidence == []
    assert pooled.score == ALERT_THRESHOLD
    (evidence,) = pooled.evidence
    assert evidence["signal"] == "resource_interleaving"
    assert evidence["value"] == ALERT_THRESHOLD
    assert {"signal": "within_token_interleaving", "reason": "no identity"} in pooled.not_computable


@pytest.mark.parametrize("path, status", [("/help", 200), ("/docs/other-1", 403)])
def test_mixed_windows_explain_why_pooling_is_unavailable(path, status):
    requests = anonymous(document_reads("abababab"))
    assert result(requests).score == 0.5
    mixed = result(requests + [row(9, "a", path, status=status)])
    assert mixed.score == 0.0
    assert {
        "signal": "resource_interleaving",
        "reason": "only anonymous reads have identifiable resource families in a mixed window",
    } in mixed.not_computable


def test_mixed_windows_use_eligible_identified_reads():
    requests = document_reads("abababab")
    other = [{**request, "seq": request["seq"] + 8} for request in anonymous(requests)]
    assert result(requests + other).to_dict() == result(requests).to_dict()


@pytest.mark.parametrize("client", ["crawler", "scheduled", "retry", "churn", "browser"])
def test_simple_traffic_lookalikes(client):
    if client == "crawler":
        requests = [
            row(i, "a", f"/docs/{i % 100 // 20}-section-{i % 20}", start=i / 1000)
            for i in range(200)
        ]
    elif client == "scheduled":
        requests = [
            row(i, token, f"/docs/region-{i // 2 % 3}-1", start=i // 6)
            for i, token in enumerate(["a", "b"] * 30)
        ]
    elif client == "retry":
        requests = [row(i, "a", "/docs/failed-1", start=i / 1000, status=503) for i in range(100)]
    elif client == "churn":
        requests = [row(i, str(i // 3), f"/docs/{i % 2}-part-{i}") for i in range(100)]
    else:
        requests = document_reads("abab")
    assert result(requests).evidence == []
    assert result(requests).groups == []


def test_baselines_fold_successful_named_writes_and_count_distinct_authors():
    requests = [
        row(1, "a", "/notes/--REPORT_123.Part9--", "PUT", start=0, end=3),
        row(2, "a", "/notes/report 55:part18", "PUT", start=1, end=2),
        row(3, "b", "/notes/report-0..PART0", "PUT", start=1.5),
        row(4, "c", "/notes/report-1-part5", "PUT", start=1.5, status=403),
        row(5, "c", "/notes/report-2-part6", start=3, end=4),
        row(6, None, "/notes/report-3-part7", "PUT", start=4),
        row(7, "d", "/notes/report-0-part-0", "PUT", start=4),
    ]
    scores = all_baselines(events_from_rows(requests))
    assert scores == {"requests": 7.0, "sessions": 4.0, "concurrency": 3.0,
                      "template_multiplicity": 2.0}
    assert all_baselines(events_from_rows(requests), identity_removed=True) == {
        **scores, "sessions": 0.0, "template_multiplicity": None,
    }


@pytest.mark.parametrize("requests", [[], [row(1, None, "/notes/report", "PUT", status=201)]])
@pytest.mark.parametrize("identity_removed", [False, True])
def test_baselines_use_explicit_export_mode_when_no_tokens_exist(requests, identity_removed):
    assert all_baselines(events_from_rows(requests), identity_removed=identity_removed) == {
        "requests": float(len(requests)),
        "sessions": 0.0,
        "concurrency": float(len(requests)),
        "template_multiplicity": None if identity_removed else 0.0,
    }


def test_template_multiplicity_distinguishes_no_writes_from_no_identity():
    requests = [
        row(1, "a", "/notes/report"),
        row(2, "a", "/notes/report", "PUT", status=403),
        row(3, None, "/notes/report", "PUT"),
    ]
    assert all_baselines(events_from_rows(requests)) == {
        "requests": 3.0, "sessions": 1.0, "concurrency": 1.0, "template_multiplicity": 0.0,
    }
    assert all_baselines(events_from_rows(anonymous(requests))) == {
        "requests": 3.0, "sessions": 0.0, "concurrency": 1.0, "template_multiplicity": 0.0,
    }


def test_concurrency_boundary_and_zero_duration_ties():
    requests = [
        row(1, "a", "/docs/a", start=0, end=2),
        row(2, "a", "/docs/b", start=2, end=4),
        row(3, "b", "/docs/c", start=2),
        row(4, "c", "/docs/c", start=2),
    ]
    assert all_baselines(events_from_rows(requests))["concurrency"] == 1.0


@pytest.mark.parametrize(
    ("changes", "error"),
    [
        ({"seq": True}, "seq must be a nonnegative integer"),
        ({"t_end": -1}, "t_end must be a finite nonnegative number"),
        ({"t_end": 0}, "t_end must be at least t_start"),
        ({"t_start": 2**53 + 1, "t_end": 2**53}, "t_end must be at least t_start"),
        ({"t_start": float("nan")}, "t_start must be a finite nonnegative number"),
        ({"token_id": 42}, "token_id must be a nonempty string or null"),
        ({"path": "docs/a"}, "path must start with /"),
    ],
)
def test_validation_explains_invalid_values(changes, error):
    with pytest.raises(ValueError, match=f"row 2: .*{error}"):
        events_from_rows([row(0, None, "/help"), {**row(1, "a", "/docs/a"), **changes}])


def test_validation_accepts_integer_and_fractional_timestamps(tmp_path):
    path = tmp_path / "timed.jsonl"
    requests = [
        row(1, "a", "/docs/a", start=1, end=2),
        row(2, "a", "/docs/b", start=1.999999, end=2.000001),
    ]
    path.write_text("\n".join(map(json.dumps, requests)) + "\n", encoding="utf8")
    events = load_events(path)
    assert [(event.t_start, event.t_end) for event in events] == [(1.0, 2.0), (1.999999, 2.000001)]


def test_large_integer_timestamps_keep_adjacent_writes_and_reads_separate(tmp_path):
    path = tmp_path / "timed.jsonl"
    start = 2**53
    requests = [
        {**request, "t_start": start + offset, "t_end": start + offset}
        for offset, request in enumerate(handoffs()[:3])
    ]
    path.write_text("\n".join(map(json.dumps, requests)) + "\n", encoding="utf8")
    events = load_events(path)
    for offset, event in enumerate(events):
        assert type(event.t_start) is type(event.t_end) is int
        assert event.t_start == event.t_end == start + offset
    assert assess(events).evidence == [{"signal": "read_handoff", "value": 0.5, "seqs": [1, 2, 3]}]


def test_validation_rejects_missing_fields_duplicate_sequences_and_invalid_json(tmp_path):
    request = row(1, "a", "/docs/a")
    with pytest.raises(ValueError, match="row 2: duplicate seq 1"):
        events_from_rows([request, request])
    del request["query"]
    with pytest.raises(ValueError, match="row 1: missing field query"):
        events_from_rows([request])
    path = tmp_path / "bad.jsonl"
    path.write_text(json.dumps(row(1, "a", "/docs/a")) + "\n{broken\n", encoding="utf8")
    with pytest.raises(ValueError, match=r"bad\.jsonl: row 2: invalid JSON at column 2"):
        load_events(path)


def test_cli_output_schema_and_explanation(tmp_path):
    path = tmp_path / "events.jsonl"
    requests = handoffs()
    path.write_text("\n".join(map(json.dumps, requests)) + "\n", encoding="utf8")
    command = [sys.executable, "-B", "-m", "swarmtrace.fleet"]
    args = ["--events", str(path)]
    scored = subprocess.check_output([*command, "score", *args, "--json"], text=True)
    expected = result(requests).to_dict()
    assert set(expected) == {"score", "alert", "groups", "evidence", "not_computable"}
    assert json.loads(scored) == {
        **expected, "baselines": all_baselines(events_from_rows(requests)),
    }
    removed = subprocess.check_output(
        [*command, "score", *args, "--json", "--identity-removed"], text=True,
    )
    assert json.loads(removed) == {
        **expected, "baselines": all_baselines(events_from_rows(requests), identity_removed=True),
    }
    explanation = subprocess.check_output([*command, "explain", *args], text=True)
    assert "read_handoff" in explanation
    assert "request seq 1, 2, 3" in explanation

    requests = document_reads("abcabcabcabc")
    path.write_text("\n".join(map(json.dumps, requests)) + "\n", encoding="utf8")
    explanation = subprocess.check_output([*command, "explain", *args], text=True)
    assert "resource_interleaving" in explanation
    assert "11 changes in 11 transitions, 9 returns to 3 of 3 families" in explanation
    assert "log null tail bound" in explanation
