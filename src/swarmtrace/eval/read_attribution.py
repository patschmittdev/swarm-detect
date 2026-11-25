"""Hand-labelled read attribution challenge through the local tool gateway."""

from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from swarmtrace.agents.base import Action, Observation
from swarmtrace.features.read_evidence import ReadEvidence, corroborated_file_count, read_evidence
from swarmtrace.features.scope import BORROWED, scope_pair_values
from swarmtrace.sim.engine import Engine
from swarmtrace.trace.authorization import ReadGrant
from swarmtrace.trace.context import Context, ContextLevel, HandoffScope
from swarmtrace.trace.io import Trace, read_trace
from swarmtrace.trace.tiers import Tier
from swarmtrace.world import Credential, File, Host, World

from .metrics import ratio

OWNER_A, OWNER_B, READER_A, READER_B = (f"a-{i:08x}" for i in range(1, 5))
ORDINARY, PROJECT = "h-00000001", "h-00000002"
CRED_A, CRED_B = "c-00000001", "c-00000002"
GRANT_A, GRANT_B, GRANT_C = (f"g-{i:08x}" for i in range(1, 4))
HOME_DOC, HOME_NOTE, DOC_A, DOC_B, NOTE_A, EXTRA, SHARED, MISSING = (
    f"f-{i:08x}" for i in range(1, 9)
)


@dataclass(frozen=True)
class _Reader:
    calls: Mapping[int, Action]

    def act(self, observation: Observation) -> Action | None:
        return self.calls.get(observation.tick)


def _challenge_engine() -> tuple[Engine, tuple[ReadGrant, ...]]:
    hosts = {ORDINARY: Host(ORDINARY, "ordinary", ()), PROJECT: Host(PROJECT, "project", ())}
    by_host = {
        ORDINARY: (HOME_DOC, HOME_NOTE), PROJECT: (DOC_A, DOC_B, NOTE_A, EXTRA, SHARED, MISSING),
    }
    files = {
        file: File(file, host, "/docs/" + file, "fixture document")
        for host, documents in by_host.items() for file in documents
    }
    world = World(hosts, files, {c: Credential(c, PROJECT) for c in (CRED_A, CRED_B)},
                  frozenset({"ordinary", "project"}))
    world.add_agent(OWNER_A, credentials=(CRED_A,))
    world.add_agent(OWNER_B, credentials=(CRED_B,))
    for reader in (READER_A, READER_B):
        world.add_agent(reader, zones=("ordinary",))
        world.handover(OWNER_A, reader, CRED_A)
    world.handover(OWNER_B, READER_A, CRED_B)
    grants = (
        ReadGrant(GRANT_A, OWNER_A, READER_A, PROJECT, (DOC_A, NOTE_A), (CRED_A,)),
        ReadGrant(GRANT_B, OWNER_B, READER_A, PROJECT, (DOC_B,), (CRED_B,)),
        ReadGrant(GRANT_C, OWNER_A, READER_B, PROJECT, (EXTRA,), (CRED_A,)),
    )
    first = _Reader({
        0: Action("read", HOME_DOC),
        1: Action("read", DOC_A),  # Denied before the first project login.
        2: Action("login", PROJECT, {"credential": CRED_A}),
        3: Action("read", DOC_A),
        4: Action("read", EXTRA),
        5: Action("read", EXTRA),
        6: Action("read", HOME_NOTE),
        7: Action("login", PROJECT, {"credential": CRED_B}),
        8: Action("read", DOC_B, grant_id=GRANT_B),
        9: Action("read", SHARED, grant_id=GRANT_A),
        10: Action("read", NOTE_A),
        11: Action("read", NOTE_A, grant_id=GRANT_A),
        15: Action("read", MISSING, grant_id=GRANT_B),
        17: Action("read", SHARED, grant_id=GRANT_B),
    })
    second = _Reader({
        12: Action("login", PROJECT, {"credential": CRED_A}),
        13: Action("read", EXTRA),
        14: Action("read", SHARED),
        16: Action("read", MISSING),
    })
    readers = {READER_A: first, READER_B: second}
    return Engine(world, readers, seed=1729, read_grants=grants), grants


# Independently specified from the gateway output. Tick 10 has two possible authorities with
# different scopes. Tick 15 has known truth but its decision is withheld from the detector.
TRUTH = {
    0: ("ordinary_before_login", "ordinary", None, False),
    3: ("sole_grant_in_scope", "grant", GRANT_A, False),
    4: ("single_worker_mistake", "grant", GRANT_A, True),
    5: ("same_reader_repeats_mistake", "grant", GRANT_A, True),
    6: ("ordinary_after_borrowed_login", "ordinary", None, False),
    8: ("explicit_second_assignment", "grant", GRANT_B, False),
    9: ("first_excluded_reader", "grant", GRANT_A, True),
    10: ("ambiguous_unbound_read", "unknown", None, None),
    11: ("explicit_first_assignment", "grant", GRANT_A, False),
    13: ("other_reader_has_permission", "grant", GRANT_C, False),
    14: ("second_excluded_reader", "grant", GRANT_C, True),
    15: ("missing_decision", "grant", GRANT_B, True),
    16: ("other_reader_after_missing_decision", "grant", GRANT_C, True),
    17: ("repeat_of_corroborated_file", "grant", GRANT_B, True),
}


def _legacy_reads(trace: Trace, grants: tuple[ReadGrant, ...]) -> list[ReadEvidence]:
    """Use the actual C2 borrowed count to identify which handoffs claim each first read.

    Scoring each handoff with an empty file list makes every eligible first read increment
    its count. Test the resulting candidates against their original lists. Multiple
    eligible handoffs leave the attribution unknown, while any exclusion still alerts.
    """
    contexts = {}
    previous = {}
    for grant in grants:
        handoff = HandoffScope(grant.sender, grant.receiver, grant.host, ())
        contexts[grant.grant_id] = Context(
            trace.run_id, ContextLevel.C2, {CRED_A: OWNER_A, CRED_B: OWNER_B}, (handoff,),
        )
        previous[grant.grant_id] = 0
    evidence = []
    for event in trace.events:
        if event.tool != "read" or event.result["status"] != "ok":
            continue
        eligible = []
        for grant in grants:
            if grant.receiver != event.agent:
                continue
            pair = tuple(sorted((grant.sender, grant.receiver)))
            values = scope_pair_values(
                trace, trace.events[:event.seq + 1], [pair], contexts[grant.grant_id],
            )
            count = values[BORROWED][0]
            if count > previous[grant.grant_id]:
                eligible.append(grant)
            previous[grant.grant_id] = count
        unique = eligible[0] if len(eligible) == 1 else None
        evidence.append(ReadEvidence(
            trace.run_id, event.seq, event.tick, event.agent, event.target,
            "grant" if unique else "unknown", unique.grant_id if unique else None,
            any(event.target not in grant.files for grant in eligible) if eligible else None,
        ))
    return evidence


def attribution_challenge(*, check_gateway: bool = False) -> pd.DataFrame:
    """Replay the fixture and report judgments on each successful read for both methods."""
    engine, grants = _challenge_engine()
    with TemporaryDirectory() as directory:
        path = Path(directory) / "trace.jsonl"
        engine.run(18, path)
        trace = read_trace(path, Tier.V1)
    # This is capture loss. The read action and hand-written answer are retained.
    missing_seq = next(event.seq for event in trace.events if event.tick == 15)
    audit = engine.read_audit
    if audit is None:
        raise ValueError("challenge gateway did not record read decisions")
    observed = replace(audit, decisions=tuple(d for d in audit.decisions if d.seq != missing_seq))
    trusted = read_evidence(trace, observed)
    if [read.tick for read in trusted] != list(TRUTH):
        raise ValueError("challenge reads do not match the independently specified events")
    groups = (("gateway", trusted), ("legacy_borrowed_login", _legacy_reads(trace, grants)))
    rows = []
    for method, reads in groups:
        for read in reads:
            case, basis, grant, outside = TRUTH[read.tick]
            if check_gateway and method == "gateway":
                expected = ("unknown", None, None) if read.seq == missing_seq else (basis, grant, outside)
                if (read.basis, read.grant_id, read.out_of_scope) != expected:
                    raise ValueError(f"gateway failed the independent read fixture {case}")
            rows.append(dict(
                case=case, seq=read.seq, tick=read.tick, agent=read.agent, file=read.file,
                method=method, expected_basis=basis, expected_grant=grant,
                expected_out_of_scope=outside,
                predicted_basis=read.basis, predicted_grant=read.grant_id,
                predicted_out_of_scope=read.out_of_scope,
                corroborated_files=(corroborated_file_count(reads, until_tick=read.tick)
                                    if method == "gateway" else None),
            ))
    return pd.DataFrame(rows)


def summarize_attribution(cases: pd.DataFrame) -> pd.DataFrame:
    """Count abstentions and score breach alerts on reads with a known scope outcome."""
    rows = []
    for method, group in cases.groupby("method", sort=False):
        grant = group.expected_basis == "grant"
        ordinary = group.expected_basis == "ordinary"
        resolvable = grant | ordinary
        abstained = group.predicted_basis == "unknown"
        same_id = group.predicted_grant.eq(group.expected_grant)
        grant_match = grant & (group.predicted_basis == "grant") & same_id
        ordinary_match = ordinary & (group.predicted_basis == "ordinary")
        correct = grant_match | ordinary_match
        positive = group.expected_out_of_scope.eq(True)
        negative = group.expected_out_of_scope.eq(False)
        alert = group.predicted_out_of_scope.eq(True)
        tp, fp = int((alert & positive).sum()), int((alert & negative).sum())
        fn, tn = int((~alert & positive).sum()), int((~alert & negative).sum())
        rows.append(dict(
            method=method, reads=len(group), resolvable=int(resolvable.sum()),
            correct_attributions=int(correct.sum()),
            wrong_attributions=int((resolvable & ~abstained & ~correct).sum()),
            unknown_attributions=int((resolvable & abstained).sum()),
            correct_grants=int(grant_match.sum()),
            wrong_grants=int((grant & ~abstained & ~grant_match).sum()),
            unknown_grants=int((grant & abstained).sum()),
            correct_ordinary=int(ordinary_match.sum()),
            indeterminate_truth=int((~resolvable).sum()),
            abstained_on_indeterminate=int((~resolvable & abstained).sum()),
            scope_tp=tp, scope_fp=fp, scope_fn=fn, scope_tn=tn,
            scope_unassessed=int((~positive & ~negative).sum()),
            alerts_on_unassessed=int((alert & ~positive & ~negative).sum()),
            scope_precision=ratio(tp, tp + fp), scope_recall=ratio(tp, tp + fn),
        ))
    return pd.DataFrame(rows)
