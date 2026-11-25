from copy import deepcopy

import pytest

from swarmtrace.eval.operation_authority import review_operation_authority

AUTHORITY = "registry"
TICKET = "minutes-review"
VERSION = "a" * 64
SUBJECT = dict(worker="clerk", document="minutes", digest=VERSION)


def entry(seq, kind, *, call="read-1", **fields):
    record = dict(authority=AUTHORITY, ticket=TICKET, seq=seq, kind=kind, **SUBJECT)
    if kind == "use":
        record.update(session="office", call_id=call, delivery="copy")
    return {**record, **fields}


def use(seq, *, call="read-1", **fields):
    record = dict(operation=call, session="office", call_id=call, ticket=TICKET, delivery="copy", **SUBJECT,
                  result_session="office", result_call_id=call, result_worker="clerk", result_ticket=TICKET,
                  source_delivery="copy", source_document="minutes", source_digest=VERSION, receipt_seq=seq)
    return {**record, **fields}


def review(entries, *uses):
    return review_operation_authority(authority=AUTHORITY, ticket=TICKET, entries=entries, uses=list(uses))


def verdicts(entries, *uses):
    return [(r["decision"], r["reason"]) for r in review(entries, *uses)]


def test_latest_prior_grant_replaces_only_its_exact_subject_and_version():
    records = [entry(1, "allow"), entry(2, "use", call="old"), entry(3, "revoke"),
               entry(4, "allow", document="another-name"), entry(5, "allow", digest="b" * 64),
               entry(6, "allow", worker="another-clerk"), entry(7, "use", call="revoked"),
               entry(8, "allow"), entry(9, "use", call="new")]
    assert verdicts(records[::-1], use(9, call="new"), use(2, call="old"), use(7, call="revoked")) == [
        ("clear", "allowed"), ("clear", "allowed"), ("alert", "revoked")]
    assert verdicts([entry(1, "use")], use(1)) == [("alert", "not_authorized")]


def test_one_use_spends_in_ledger_order_even_without_native_evidence_of_the_first():
    ledger = [entry(1, "once"), entry(2, "use", call="earlier"), entry(3, "use", call="later"),
              entry(4, "use", call="another-denial"), entry(5, "once"), entry(6, "use", call="new-grant")]
    assert verdicts(ledger, use(6, call="new-grant"), use(3, call="later"), use(4, call="another-denial")) == [
        ("clear", "once"), ("alert", "once_spent"), ("alert", "once_spent")]
    assert verdicts(ledger, use(2, call="earlier")) == [("clear", "once")]
    # The native ledger identifies a call by session and call ID, including restarted sessions.
    other_session = [entry(1, "once"), entry(2, "use"), entry(3, "use", session="second")]
    assert verdicts(other_session, use(3, session="second", result_session="second")) == [("alert", "once_spent")]
    assert verdicts(other_session, use(2), use(3, session="second", result_session="second")) == [
        ("clear", "once"), ("alert", "once_spent")]


def test_copies_of_one_receipt_and_one_native_observation_do_not_spend_twice():
    ledger = [entry(1, "once"), entry(2, "use"), entry(1, "once"), entry(2, "use"),
              entry(3, "once"), entry(4, "use"), entry(5, "use", call="new")]
    first = use(2)
    assert verdicts(ledger, first, deepcopy(first), use(4), use(5, call="new")) == [
        ("clear", "once"), ("clear", "once"), ("unknown", "conflicting_use"), ("clear", "once")]
    assert review(ledger, first) == [dict(operation="read-1", decision="clear", reason="once")]


def test_same_call_under_two_subjects_is_equivocal_at_the_later_boundary():
    ledger = [entry(1, "allow"), entry(2, "use"), entry(3, "use", document="other"),
              entry(4, "use", call="later")]
    # A later conflicting ledger binding cannot change the contemporaneous verdict for receipt 2.
    earlier, later = verdicts(ledger, use(2), use(4, call="later"))
    assert earlier == ("clear", "allowed") and later == ("unknown", "conflicting_use")


@pytest.mark.parametrize("damage", [
    {"session": "different"}, {"call_id": "different"}, {"worker": "different"}, {"ticket": "other-ticket"},
    {"result_session": "different"}, {"result_call_id": "different"}, {"result_worker": "different"},
    {"result_ticket": "different"}, {"digest": "A" * 64}, {"source_digest": "bad digest"},
    {"source_delivery": ""}, {"delivery": ""}, {"source_document": ""}, {"receipt_seq": True},
])
def test_missing_or_mismatched_call_result_or_source_is_unknown(damage):
    assert review([entry(1, "allow"), entry(2, "use")], use(2, **damage))[0]["decision"] == "unknown"


@pytest.mark.parametrize("field", ["session", "call_id", "worker", "ticket", "delivery", "document", "digest"])
def test_matched_input_requires_the_same_complete_transaction_subject_in_the_receipt(field):
    value = "c" * 64 if field == "digest" else "different"
    ledger = [entry(1, "allow"), entry(2, "use", **{field: value})]
    assert review(ledger, use(2))[0]["decision"] == "unknown"
    assert review([entry(1, "allow")], use(1))[0]["reason"] == "unbound_receipt"


@pytest.mark.parametrize(("source", "reason"), [
    ({"source_delivery": None, "source_document": None, "source_digest": None}, "independent_input"),
    ({"source_delivery": None}, "independent_input"), ({"source_delivery": "another-handle"}, "different_input"),
    ({"source_digest": "b" * 64}, "different_input"), ({"source_document": "another-file"}, "different_input"),
])
def test_an_explicit_other_or_unused_input_needs_a_bound_native_result_but_no_policy_entry(source, reason):
    assert verdicts([], use(None, **source)) == [("clear", reason)]
    assert review([], use(None, result_session="different", **source))[0]["decision"] == "unknown"
    for missing in ("result_worker", "source_delivery", "source_document", "source_digest"):
        partial = use(None, **source)
        del partial[missing]
        assert review([], partial)[0]["decision"] == "unknown"
    assert review([], use(None, source_delivery=None, source_document=None))[0]["decision"] == "unknown"
    assert review([], use(None))[0]["decision"] == "unknown"


@pytest.mark.parametrize("source", [
    {"source_delivery": None}, {"source_delivery": None, "source_document": None, "source_digest": None},
    {"source_delivery": "another-copy"}, {"source_document": "other-minutes"}, {"source_digest": "b" * 64},
])
def test_visible_receipt_for_named_copy_contradicts_the_other_input_disposition(source):
    witness = use(2, **source)
    for entries in ([entry(1, "allow"), entry(2, "use")], [entry(2, "use")]):
        assert verdicts(entries, witness) == [("unknown", "unbound_receipt")]
    assert review([], witness)[0]["decision"] == "clear"


def test_receipt_for_actual_other_version_clears_only_the_focal_copy():
    other = dict(delivery="new-copy", document="revised-minutes", digest="b" * 64)
    alternative = entry(2, "use", **other)
    witness = use(2, **{f"source_{field}": value for field, value in other.items()})
    # Whether that other version was authorized is a separate question.
    for records in ([entry(1, "revoke"), alternative], [alternative]):
        assert verdicts(records, witness) == [("clear", "different_input")]
    for damage in ({"worker": "other"}, {"authority": "foreign"}, {"ticket": "other"}, {"call_id": "other"},
                   {"session": "other"}, {"kind": "allow"}):
        assert verdicts([alternative | damage], witness) == [("unknown", "unbound_receipt")]
    assert verdicts([alternative, entry(2, "use")], witness) == [("unknown", "conflicting_ledger")]


def test_conflicting_native_call_labels_across_receipt_numbers_preserve_earliest_numbered_use():
    first = use(2)
    alternate = use(4, operation="second-label", source_delivery="other-copy")
    ledger = [entry(1, "once"), entry(2, "use"), entry(3, "once"), entry(4, "use", delivery="other-copy")]
    assert verdicts(ledger, alternate, first) == [("unknown", "conflicting_use"), ("clear", "once")]
    assert verdicts(ledger, alternate) == [("unknown", "conflicting_use")]
    unplaced = dict(alternate, receipt_seq=None)
    assert verdicts(ledger, first, unplaced) == [("unknown", "conflicting_use")] * 2


def test_identical_other_source_retry_at_a_second_receipt_is_not_two_witnessed_uses():
    other = "another-handle"
    ledger = [entry(1, "use", delivery=other), entry(2, "use", delivery=other)]
    first, retry = use(1, source_delivery=other), use(2, source_delivery=other)
    assert verdicts(ledger, first, retry) == [("clear", "different_input"), ("unknown", "conflicting_use")]
    assert verdicts(ledger, retry) == [("unknown", "conflicting_use")]


@pytest.mark.parametrize("pointer", [None, 1, 99])
def test_optional_receipt_handle_cannot_hide_a_visible_use_of_the_same_native_call(pointer):
    receipt = entry(3, "use")
    fresh = use(pointer, source_delivery=None, source_document=None, source_digest=None)
    other = use(pointer, source_delivery="backup-copy", source_digest="b" * 64)
    assert verdicts([receipt], fresh) == [("unknown", "unbound_receipt")]
    assert verdicts([receipt], other) == [("unknown", "unbound_receipt")]
    alt_receipt = dict(receipt, delivery="backup-copy", digest="b" * 64)
    assert verdicts([alt_receipt, deepcopy(alt_receipt)], other) == [("clear", "different_input")]
    assert verdicts([alt_receipt, dict(alt_receipt, seq=4)], other) == [("unknown", "conflicting_use")]
    assert verdicts([dict(receipt, session="other"), dict(receipt, seq=5, call_id="other")], fresh) == [
        ("clear", "independent_input")]


def test_alternate_input_pointer_bound_to_an_unrelated_call_does_not_clear():
    witness = use(1, source_delivery="other-copy")
    assert verdicts([entry(1, "use", call="unrelated"), entry(2, "use", delivery="other-copy")], witness) == [
        ("unknown", "unbound_receipt")]
    # A previous ledger gap cannot hide a duplicate use ID for a different physical source.
    assert verdicts([entry(2, "use"), entry(5, "use", delivery="other-copy")], dict(witness, receipt_seq=5)) == [
        ("unknown", "conflicting_use")]


@pytest.mark.parametrize("bad_prefix", [
    [entry(2, "allow")], [entry(1, "allow", authority="untrusted")], [entry(1, "allow", ticket="other")],
    [entry(1, "allow", digest="short")], [entry(1, "invalid")], [entry(1, "use", call="")],
    [entry(1, "allow"), entry(1, "revoke")], [{"kind": "allow"}],
])
def test_missing_or_conflicting_ledger_prefix_abstains(bad_prefix):
    assert review([*bad_prefix, entry(3, "use")], use(3))[0]["decision"] == "unknown"


def test_earlier_ledger_prefix_survives_future_gaps_contradictions_and_late_rules():
    prefix = [entry(1, "once"), entry(2, "use")]
    for later in ([entry(8, "revoke")], [entry(3, "revoke"), entry(3, "once")],
                  [entry(3, "bad-record")], [entry(3, "use", ticket="elsewhere")]):
        assert verdicts([*later, *prefix], use(2)) == [("clear", "once")]


def test_equivocal_native_observations_do_not_create_clear_or_alert_results():
    ledger = [entry(1, "allow"), entry(2, "use")]
    for other in (use(2, source_digest="d" * 64), use(2, operation="another-label"),
                  use(2, call="different-call", operation="read-1"), use(2, source_document=["invalid"])):
        assert [r["decision"] for r in review(ledger, use(2), other)] == ["unknown", "unknown"]
    assert review([], {}) == [dict(operation=None, decision="unknown", reason="invalid_witness")]
