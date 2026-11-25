"""Review the authorization in force when a document office actually consumed a delivered copy."""

import re
from collections.abc import Mapping

_SUBJECT = ("worker", "document", "digest")
_BINDING = ("session", "call_id", "worker", "ticket", "delivery", "document", "digest")
_WITNESS = ("operation", *_BINDING, "result_session", "result_call_id", "result_worker", "result_ticket",
            "source_delivery", "source_document", "source_digest", "receipt_seq")
_MISSING = object()


def _id(value):
    return isinstance(value, str) and bool(value.strip())


def _digest(value):
    return isinstance(value, str) and re.fullmatch("[0-9a-f]{64}", value) is not None


def _seq(value):
    return type(value) is int and value >= 1


def _index(entries, authority, ticket):
    numbered, uses_by_call, positioned = {}, {}, True
    for entry in entries:
        if not isinstance(entry, Mapping) or not _seq(entry.get("seq")):
            positioned = False
            continue
        seq = entry["seq"]
        if seq in numbered and entry != numbered[seq]:
            numbered[seq] = None
        else:
            numbered[seq] = entry
        if (entry.get("authority") == authority and entry.get("ticket") == ticket and entry.get("kind") == "use"
                and _id(entry.get("session")) and _id(entry.get("call_id"))):
            uses_by_call.setdefault((entry["session"], entry["call_id"]), set()).add(seq)
    return numbered, uses_by_call, positioned


def _ledger(numbered, positioned, authority, ticket):
    """Save use decisions at their own sequence boundaries. Later events cannot revise them."""
    if not positioned:
        # A delivery batch is not an ordering proof for a record with no usable sequence.
        return {}, 1, "incomplete_ledger"
    grants, first_call, results = {}, {}, {}
    next_seq = 1
    for seq, e in sorted(numbered.items()):
        if seq != next_seq:
            break
        if e is None:
            return results, seq, "conflicting_ledger"
        kind = e.get("kind")
        if (e.get("authority") != authority or e.get("ticket") != ticket
                or not _id(e.get("worker")) or not _id(e.get("document")) or not _digest(e.get("digest"))
                or kind not in ("allow", "once", "revoke", "use")):
            return results, seq, "incomplete_ledger"
        subject = tuple(e[k] for k in _SUBJECT)
        if kind != "use":
            grants[subject] = kind
        else:
            if not all(_id(e.get(k)) for k in ("session", "call_id", "delivery")):
                return results, seq, "incomplete_ledger"
            binding = tuple(e[k] for k in _BINDING)
            call = (e["session"], e["call_id"])
            if call in first_call:
                if first_call[call] != binding:
                    return results, seq, "conflicting_use"
                # The same operation at a second sequence is not a new consumption.
                decision = ("unknown", "conflicting_use")
            else:
                first_call[call] = binding
                state = grants.get(subject)
                if state == "allow":
                    decision = ("clear", "allowed")
                elif state == "once":
                    decision = ("clear", "once")
                    grants[subject] = "spent"
                else:
                    reason = {"revoke": "revoked", "spent": "once_spent"}.get(state, "not_authorized")
                    decision = ("alert", reason)
            results[seq] = (binding, decision)
        next_seq += 1
    return results, next_seq, "incomplete_ledger"


def _claims(uses):
    """Group duplicate native IDs. Only their first numbered use can be a new operation."""
    groups, conflicts = {}, set()
    for index, u in enumerate(uses):
        if not isinstance(u, Mapping):
            continue
        seq = u.get("receipt_seq")
        position = seq if _seq(seq) else None
        values = (u.get(field, _MISSING) for field in _WITNESS[:-1])
        claim = tuple((type(value), value) for value in values)
        for key in _claim_keys(u):
            groups.setdefault(key, {}).setdefault(position, []).append((index, claim))
    for at in groups.values():
        first = min((seq for seq in at if seq is not None), default=None)
        # An unplaced conflicting witness cannot be ordered to one side of a numbered use.
        unplaced = at.get(None)
        ambiguous = unplaced and any(c != unplaced[0][1] for rows in at.values() for _, c in rows)
        for seq, rows in at.items():
            if ambiguous or (seq is not None and seq != first) or any(c != rows[0][1] for _, c in rows):
                conflicts.update(index for index, _ in rows)
    return conflicts


def _claim_keys(u):
    if _id(u.get("session")) and _id(u.get("operation")):
        yield ("operation", u["session"], u["operation"])
    if _id(u.get("session")) and _id(u.get("call_id")):
        yield ("call", u["session"], u["call_id"])


def _other_input(u, source, authority, numbered, uses_by_call):
    """Reconcile a native non-use disposition with any corresponding visible use receipt."""
    seq = u["receipt_seq"]
    positions = uses_by_call.get((u["session"], u["call_id"]), ())
    if seq not in numbered:
        if len(positions) > 1:
            return "unknown", "conflicting_use"
        seq = next(iter(positions), None)
    elif positions and min(positions) < seq:
        return "unknown", "conflicting_use"
    if seq in numbered:
        e = numbered[seq]
        if e is None:
            return "unknown", "conflicting_ledger"
        binding = tuple(u[k] for k in _BINDING[:4]) + source
        if (source[0] is None or e.get("authority") != authority or e.get("kind") != "use"
                or tuple(e.get(k, _MISSING) for k in _BINDING) != binding):
            return "unknown", "unbound_receipt"
    return "clear", "independent_input" if source[0] is None else "different_input"


def _classify(u, authority, ticket, ledger, numbered, uses_by_call):
    if not isinstance(u, Mapping) or not _id(authority) or not _id(ticket) or any(k not in u for k in _WITNESS):
        return "unknown", "invalid_witness"
    if (not all(_id(u[k]) for k in ("operation", "session", "call_id", "worker", "ticket", "delivery", "document"))
            or not _digest(u["digest"]) or u["ticket"] != ticket
            or any(u["result_" + k] != u[k] for k in ("session", "call_id", "worker", "ticket"))):
        return "unknown", "invalid_witness"
    seq = u["receipt_seq"]
    if seq is not None and not _seq(seq):
        return "unknown", "unbound_receipt"
    handle, document, digest = (u[k] for k in ("source_delivery", "source_document", "source_digest"))
    has_source = _id(document) and _digest(digest)
    if handle is None:
        if not (has_source or (document is None and digest is None)):
            return "unknown", "invalid_witness"
    elif not _id(handle) or not has_source:
        return "unknown", "invalid_witness"
    source = (handle, document, digest)
    if source != (u["delivery"], u["document"], u["digest"]):
        return _other_input(u, source, authority, numbered, uses_by_call)
    if seq is None:
        return "unknown", "unbound_receipt"
    results, boundary, reason = ledger
    if seq >= boundary:
        return "unknown", reason
    receipt = results.get(seq)
    if receipt is None or receipt[0] != tuple(u[k] for k in _BINDING):
        return "unknown", "unbound_receipt"
    return receipt[1]


def review_operation_authority(*, authority: str, ticket: str, entries: list[dict], uses: list[dict]) -> list[dict]:
    """Return one access/use finding per supplied native operation, in supplied order.

    Trust is in the named issuer's complete serialized ledger and the editor's independent
    account of its actual input. An issued one-time grant is spent by the first matching use
    receipt even when the reviewer never sees that operation's separate native result.
    """
    numbered, uses_by_call, positioned = _index(entries, authority, ticket)
    ledger = _ledger(numbered, positioned, authority, ticket)
    conflicts = _claims(uses)
    rows = []
    for index, u in enumerate(uses):
        decision, reason = ("unknown", "conflicting_use") if index in conflicts else _classify(
            u, authority, ticket, ledger, numbered, uses_by_call)
        operation = u.get("operation") if isinstance(u, Mapping) else None
        rows.append(dict(operation=operation if _id(operation) else None, decision=decision, reason=reason))
    return rows
