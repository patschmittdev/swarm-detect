"""Score replicated signs of coordination in one request window.

A named state read followed by a changed write can link its reader to the previous author.
On that object, no successful write may touch or overlap the read, and no other successful
write may touch or overlap the credited write. This includes anonymous writes. Writes by
different identities that merely touch in time make authorship ambiguous.
A changed write needs a known digest and either a creation status or a predecessor with
a different known digest.
Under independent work, a solitary link can be incidental, so an alert needs two connected
links that differ in direction, participants, or object. With or without reads, a second
test looks for consecutive A-B-A-B versions with distinct bodies and no other write
intersecting the block's span. Ordinary co-editing can produce one such exchange, so the
same pair must repeat it on a different object.
Both tests break timestamp ties by completion sequence.

For shared-token workers, measure family returns among first visits to resources in request
start order, breaking ties by sequence. Infer families from parent paths or names with a
delimited numeric suffix. A family-by-family traversal makes F - 1 changes for F families.
Each extra change returns to a previously visited family, as can happen when several
sequential workers with different families share a token.

The single-worker null allows occasional backtracking: at any of the N - 1 transitions
in a stream of N first visits, the conditional probability of a family return given the
preceding visits is at most 1/4. For an observed return fraction q > 1/4, use the one-sided
binomial Chernoff bound exp(-(N - 1) * D(q || 1/4)), where D is Bernoulli relative entropy.
Require a bound of 0.01 or less over the whole stream. The bound allows dependence under
that conditional null. An identified stream scores 0.75 if it also returns to at
least two distinct families, so repeated visits to a single hub cannot corroborate the
signal. Other streams meeting the tail cut score 0.5, including pooled anonymous reads.
Anonymous pooling applies only when every row in the window has a null token. In a mixed
window, interleaving uses only identified reads. When the evidence is interleaving under
one token, groups is [[token]], naming one implicated credential. The workers behind it
remain uncounted and unidentified.

Take the strongest signal on a fixed evidence scale with a strict 0.5 alert threshold.
Serialized subagents, workers reading the same family, coordination off the service, and
one-way edits without reads can be missed. A single worker using a round-robin traversal
can produce the same order and alert, as can unrelated workers sharing a token. Ordinary
collaborative editing can mimic the write signals.
"""

import re
from bisect import bisect_left, bisect_right
from collections import defaultdict
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from math import log
from urllib.parse import unquote

from swarmtrace.fleet.events import Event

ALERT_THRESHOLD: float = 0.5

STATE_READ = "state_read"
STATE_WRITE = "state_write"
RESOURCE_READ = "resource_read"
REQUEST_ROLES = {
    ("GET", "notes"): STATE_READ,
    ("PUT", "notes"): STATE_WRITE,
    ("GET", "collections"): RESOURCE_READ,
    ("GET", "docs"): RESOURCE_READ,
    ("GET", "search"): RESOURCE_READ,
}
# Successful note PUT statuses that indicate creation.
CREATED_STATUSES = {201}

READ_HANDOFF = "read_handoff"
RECIPROCAL_REWRITES = "reciprocal_rewrites"
RESOURCE_INTERLEAVING = "resource_interleaving"
NULL_RETURN_RATE = 0.25
INTERLEAVING_TAIL_CUTOFF = 0.01


@dataclass(slots=True)
class Assessment:
    score: float
    alert: bool
    groups: list[list[str]]
    evidence: list[dict]
    not_computable: list[dict]

    def to_dict(self) -> dict:
        """Return the public assessment fields as JSON-serializable values."""
        return {
            "score": self.score,
            "alert": self.alert,
            "groups": self.groups,
            "evidence": self.evidence,
            "not_computable": self.not_computable,
        }


@dataclass(frozen=True, slots=True)
class _Action:
    event: Event
    role: str
    key: tuple[str, str]

    @property
    def token(self) -> str | None:
        return self.event.token_id


@dataclass(slots=True)
class _Finding:
    score: float
    tokens: tuple[str, ...]
    evidence: list[dict]


@dataclass(slots=True)
class _Observation:
    link: tuple[str, str, tuple[str, str]]
    source: _Action
    read: _Action
    version: _Action


class _WriteHistory:
    def __init__(self, writes: list[_Action]) -> None:
        self.writes = writes
        self.starts = [write.event.t_start for write in writes]
        self.ends = sorted(write.event.t_end for write in writes)

    def overlap_count(self, start: int | float, end: int | float) -> int:
        """Count closed intervals starting by end, excluding those ending before start."""
        return bisect_right(self.starts, end) - bisect_left(self.ends, start)


def request_target(event: Event) -> tuple[str, tuple[str, str]] | None:
    """Return the role and decoded target of a successful mapped request."""
    if not 200 <= event.status < 300:
        return None
    segment, _, name = event.path[1:].partition("/")
    role = REQUEST_ROLES.get((event.method, segment))
    if role is None or (role in (STATE_READ, STATE_WRITE) and not name):
        return None
    return role, (segment, unquote(name))


def _start(action: _Action) -> tuple[int | float, int]:
    return action.event.t_start, action.event.seq


def _finish(action: _Action) -> tuple[int | float, int]:
    return action.event.t_end, action.event.seq


def _evidence(signal: str, value: float, actions: Iterable[_Action]) -> dict:
    return {"signal": signal, "value": value, "seqs": [action.event.seq for action in actions]}


def _components(groups: Iterable[tuple[str, ...]]) -> list[tuple[str, ...]]:
    neighbors = defaultdict(set)
    for group in groups:
        for token in group:
            neighbors[group[0]].add(token)
            neighbors[token].add(group[0])
    components = []
    remaining = set(neighbors)
    for token in sorted(neighbors):
        if token not in remaining:
            continue
        remaining.remove(token)
        pending = [token]
        members = []
        while pending:
            member = pending.pop()
            members.append(member)
            unseen = neighbors[member] & remaining
            remaining.difference_update(unseen)
            pending.extend(unseen)
        components.append(tuple(sorted(members)))
    return components


def _conflicting_write_seqs(writes: list[_Action]) -> set[int]:
    """Find writes overlapping a different token for same-byte write-through checks."""
    endpoints = defaultdict(list)
    for write in writes:
        event = write.event
        endpoints[write.key].extend((
            (event.t_start, False, write),
            (event.t_end, True, write),
        ))

    ambiguous = set()
    for history in endpoints.values():
        active = defaultdict(int)
        last_overlap = float("-inf")
        # Starts sort before ends at the same time because these intervals are closed.
        for time, ending, write in sorted(history, key=lambda endpoint: endpoint[:2]):
            token = write.token
            if not ending:
                active[token] += 1
                if len(active) > 1:
                    last_overlap = time
                continue
            # A conflict at any point while this write was active makes its author ambiguous.
            if write.event.t_start <= last_overlap:
                ambiguous.add(write.event.seq)
            active[token] -= 1
            if active[token] == 0:
                del active[token]
    return ambiguous


def _read_handoffs(
    actions: list[_Action], writes: list[_Action], histories: dict[tuple[str, str], _WriteHistory],
) -> Iterator[_Finding]:
    latest = {}
    pending = {}
    links = {}
    conflicts = _conflicting_write_seqs(writes)
    completed = iter(sorted(writes, key=_finish))
    next_write = next(completed, None)
    for action in actions:
        if action.role == RESOURCE_READ:
            continue
        while next_write is not None and _finish(next_write) < _start(action):
            observation = pending.get(next_write.token)
            digest = next_write.event.write_sha256
            # A reader can write back the same version before making a substantive edit.
            if (
                observation is not None
                and latest.get(next_write.key) is observation.version
                and next_write.event.seq not in conflicts
                and digest is not None
                and digest == observation.version.event.write_sha256
            ):
                observation.version = next_write
            latest[next_write.key] = next_write
            next_write = next(completed, None)
        token = action.token
        if token is None:
            continue
        previous = latest.get(action.key)
        if action.role == STATE_READ:
            if previous is None or previous.token in (None, token):
                continue
            history = histories[action.key]
            if history.overlap_count(action.event.t_start, action.event.t_end):
                continue
            if history.overlap_count(previous.event.t_start, previous.event.t_end) != 1:
                continue
            link = (previous.token, token, action.key)
            if link not in links:
                pending[token] = _Observation(link, previous, action, previous)
            continue
        observation = pending.get(token)
        if observation is None:
            continue
        read = observation.read
        digest = action.event.write_sha256
        changed = digest is not None and (
            action.event.status in CREATED_STATUSES
            or (
                previous is not None
                and previous.event.write_sha256 is not None
                and digest != previous.event.write_sha256
            )
        )
        if (
            changed
            and _finish(read) < _start(action)
            and (action.key != read.key or previous is observation.version)
        ):
            links[observation.link] = (observation.source, read, action)
            del pending[token]

    components = _components((writer, reader) for writer, reader, _ in links)
    by_token = {token: group for group in components for token in group}
    by_group = defaultdict(list)
    for (writer, _, _), witness in links.items():
        by_group[by_token[writer]].append(witness)
    for group, witnesses in by_group.items():
        score = 0.75 if len(witnesses) >= 2 else 0.5
        yield _Finding(
            score, group, [_evidence(READ_HANDOFF, score, witness) for witness in witnesses]
        )


def _reciprocal_rewrites(histories: Iterable[_WriteHistory]) -> Iterator[_Finding]:
    by_pair = defaultdict(list)
    for history in histories:
        writes = history.writes
        seen = set()
        for i in range(len(writes) - 3):
            block = writes[i:i + 4]
            a, b, c, d = (write.token for write in block)
            if a is None or b is None or a == b or (a, b) != (c, d):
                continue
            pair = tuple(sorted((a, b)))
            if pair in seen or len(by_pair.get(pair, ())) == 2:
                continue
            digests = {write.event.write_sha256 for write in block}
            if None in digests or len(digests) != 4:
                continue
            if any(_finish(left) >= _start(right) for left, right in zip(block, block[1:])):
                continue
            if history.overlap_count(block[0].event.t_start, block[-1].event.t_end) != len(block):
                continue
            seen.add(pair)
            by_pair[pair].append(block)
    for pair, witnesses in by_pair.items():
        score = 0.75 if len(witnesses) == 2 else 0.25
        yield _Finding(
            score, pair, [_evidence(RECIPROCAL_REWRITES, score, block) for block in witnesses]
        )


def _resource_family(action: _Action) -> tuple[str, str] | None:
    segment, name = action.key
    parent, separator, _ = name.rpartition("/")
    if separator and parent:
        return segment, parent
    match = re.fullmatch(r"(.+)[-_.]\d+", name)
    return (segment, match[1]) if match else None


def _streams(
    actions: list[_Action], identified: bool,
) -> dict[str | None, list[tuple[tuple[str, str], _Action]]]:
    streams = defaultdict(list)
    seen = defaultdict(set)
    for action in actions:
        if action.role != RESOURCE_READ or (identified and action.token is None):
            continue
        family = _resource_family(action)
        if family is not None and action.key not in seen[action.token]:
            seen[action.token].add(action.key)
            streams[action.token].append((family, action))
    return streams


def _interleaving(
    token: str | None, stream: list[tuple[tuple[str, str], _Action]],
) -> _Finding | None:
    seen = set()
    returning_families = set()
    previous = None
    returns = 0
    for family, _ in stream:
        if family != previous and family in seen:
            returns += 1
            returning_families.add(family)
        seen.add(family)
        previous = family

    transitions = len(stream) - 1
    if transitions <= 0 or returns <= transitions * NULL_RETURN_RATE:
        return None

    rate = returns / transitions
    # Log of the upper-tail bound exp(-transitions * D(rate || NULL_RETURN_RATE)).
    log_bound = returns * log(NULL_RETURN_RATE / rate)
    log_bound += (transitions - returns) * log((1 - NULL_RETURN_RATE) / (1 - rate))
    if log_bound > log(INTERLEAVING_TAIL_CUTOFF):
        return None

    score = 0.75 if token is not None and len(returning_families) >= 2 else 0.5
    tokens = (token,) if token is not None else ()
    evidence = _evidence(RESOURCE_INTERLEAVING, score, (action for _, action in stream))
    evidence["order"] = {
        "transitions": transitions,
        "families": len(seen),
        "family_changes": len(seen) - 1 + returns,
        "returns": returns,
        "returning_families": len(returning_families),
        "log_null_tail_bound": log_bound,
    }
    return _Finding(score, tokens, [evidence])


def assess(events: Sequence[Event]) -> Assessment:
    """Score the strongest observed signal and name only corroborated memberships."""
    identified = any(event.token_id is not None for event in events)
    actions = []
    for event in events:
        target = request_target(event)
        if target is not None:
            actions.append(_Action(event, *target))
    actions.sort(key=_start)
    writes = [action for action in actions if action.role == STATE_WRITE]
    by_object = defaultdict(list)
    for write in writes:
        by_object[write.key].append(write)
    histories = {key: _WriteHistory(history) for key, history in by_object.items()}
    findings = []
    skipped = []

    read_reasons = []
    if not identified:
        read_reasons.append("no identity")
    state_reads = [action for action in actions if action.role == STATE_READ]
    if not state_reads:
        read_reasons.append("no successful reads of named shared objects")
    elif identified and not any(action.token is not None for action in state_reads):
        read_reasons.append("no identified reads of named shared objects")
    if read_reasons:
        skipped.append({"signal": READ_HANDOFF, "reason": " and ".join(read_reasons)})
    else:
        findings.extend(_read_handoffs(actions, writes, histories))

    if not identified:
        skipped.append({"signal": RECIPROCAL_REWRITES, "reason": "no identity"})
    elif not any(write.token is not None and write.event.write_sha256 for write in writes):
        skipped.append(
            {"signal": RECIPROCAL_REWRITES, "reason": "no identified writes with hashes"}
        )
    else:
        findings.extend(_reciprocal_rewrites(histories.values()))

    streams = _streams(actions, identified)
    if not streams:
        reason = "no successful reads of resources with identifiable families"
        if identified and any(
            action.role == RESOURCE_READ and action.token is None
            and _resource_family(action) is not None
            for action in actions
        ):
            reason = "only anonymous reads have identifiable resource families in a mixed window"
        skipped.append({"signal": RESOURCE_INTERLEAVING, "reason": reason})
    else:
        if not identified:
            skipped.append({"signal": "within_token_interleaving", "reason": "no identity"})
        for token, stream in streams.items():
            finding = _interleaving(token, stream)
            if finding is not None:
                findings.append(finding)

    score = max((finding.score for finding in findings), default=0.0)
    groups = _components(
        finding.tokens for finding in findings if finding.score > ALERT_THRESHOLD
    )
    evidence = [item for finding in findings for item in finding.evidence]
    return Assessment(
        score, score > ALERT_THRESHOLD, [list(group) for group in groups], evidence, skipped
    )
