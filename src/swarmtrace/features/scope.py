"""Scope features: what a borrowed session read, judged against defender context.

A session is opened by an ok login of agent ``X``; its reads are ``X``'s ok reads after the
login of files ``X`` had not read ok before it. They are counted as
distinct file ids. A credential's owner is inferred from the trace at C0 (the first agent with
an ok login using it) and taken from the context's directory at C1 and above; a credential
missing from the directory has no owner. Hand-off scopes are used only at C2.
"""

from collections import defaultdict
from collections.abc import Sequence

from swarmtrace.trace.context import Context, ContextLevel
from swarmtrace.trace.io import Trace
from swarmtrace.trace.schema import TraceEvent

from .spec import SCOPE, feature_columns

BREADTH = "borrowed_session_breadth"
BORROWED = "out_of_scope_reads_borrowed"
OWN = "out_of_scope_reads_own"

Pair = tuple[str, str]


def check_context(trace: Trace, context: Context) -> None:
    """Refuse a context that belongs to another run, including one with an unknown run id."""
    if not isinstance(context, Context):
        raise TypeError(f"Expected a Context, got {type(context).__name__}")
    if context.run_id != trace.run_id:
        raise ValueError(
            f"context run_id {context.run_id!r} does not match trace run_id {trace.run_id!r}"
        )


def scope_columns(trace: Trace, context: Context) -> tuple[str, ...]:
    return feature_columns("pair", trace.tier, (SCOPE,), context=context.level)


def scope_pair_values(
    trace: Trace, events: Sequence[TraceEvent], pairs: Sequence[Pair], context: Context,
) -> dict[str, list[int]]:
    """Scope columns available at ``trace.tier`` and ``context.level``, one value per pair."""
    columns = scope_columns(trace, context)
    if not columns:
        return {}
    first_read: dict[tuple[str, str], int] = {}
    logins: list[tuple[str, str, str, int]] = []
    first_user: dict[str, str] = {}
    for event in events:
        if event.result["status"] != "ok":
            continue
        if event.tool == "read":
            first_read.setdefault((event.agent, event.target), event.seq)
        elif event.tool == "login":
            credential = str(event.args["credential"])
            first_user.setdefault(credential, event.agent)
            logins.append((event.agent, event.target, credential, event.seq))

    sessions: dict[str, set[str]] = defaultdict(set)
    for (agent, file), seq in first_read.items():
        sessions[agent].add(file)

    def session(agent: str, opened: int) -> set[str]:
        return {file for file in sessions[agent] if first_read[(agent, file)] > opened}

    directory = context.level is not ContextLevel.C0

    def owner(credential: str) -> str | None:
        if directory:
            return context.credentials.get(credential)
        return first_user[credential]

    # Earliest borrowed login per (borrower, owner): later ones open subsets of its session.
    borrowed_from: dict[Pair, int] = {}
    for agent, _, credential, seq in logins:
        lender = owner(credential)
        if lender is not None and lender != agent:
            borrowed_from.setdefault((agent, lender), seq)
    breadth = {key: len(session(key[0], seq)) for key, seq in borrowed_from.items()}

    values: dict[str, list[int]] = {}
    if BREADTH in columns:
        values[BREADTH] = [
            max(breadth.get((first, second), 0), breadth.get((second, first), 0))
            for first, second in pairs
        ]
    if BORROWED in columns or OWN in columns:
        borrowed: dict[Pair, int] = defaultdict(int)
        own: dict[Pair, int] = defaultdict(int)
        known = set(pairs)
        for handoff in context.handoffs:
            sender, receiver, host = handoff.sender, handoff.receiver, handoff.host
            pair = (sender, receiver) if sender < receiver else (receiver, sender)
            if pair not in known:
                continue
            scope = set(handoff.files)
            at_host = [(credential, seq) for agent, target, credential, seq in logins
                       if agent == receiver and target == host]
            lent = next((seq for credential, seq in at_host
                         if context.credentials.get(credential) == sender), None)
            if lent is not None:
                borrowed[pair] += len(session(receiver, lent) - scope)
            if at_host and context.credentials.get(at_host[0][0]) == receiver:
                own[pair] += len(session(receiver, at_host[0][1]) - scope)
        if BORROWED in columns:
            values[BORROWED] = [borrowed[pair] for pair in pairs]
        if OWN in columns:
            values[OWN] = [own[pair] for pair in pairs]
    return {column: values[column] for column in columns}
