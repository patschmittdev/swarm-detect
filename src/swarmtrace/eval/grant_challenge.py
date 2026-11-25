"""Check per-grant scope counts against hand-labelled document review workflows."""

from collections import Counter
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from swarmtrace.agents.base import Action
from swarmtrace.features import run_features
from swarmtrace.features.grant_scope import LEGACY_COLUMN, grant_scope_counts
from swarmtrace.features.read_evidence import read_evidence
from swarmtrace.sim.engine import Engine
from swarmtrace.trace.authorization import ReadGrant
from swarmtrace.trace.context import Context, ContextLevel, HandoffScope
from swarmtrace.trace.io import read_trace
from swarmtrace.trace.tiers import Tier
from swarmtrace.world import Credential, File, Host, World

from . import read_attribution as fixture

_REVIEW_FILES = {
    0: fixture.HOME_DOC, 3: fixture.DOC_A, 4: fixture.EXTRA, 5: fixture.EXTRA,
    6: fixture.HOME_NOTE, 8: fixture.DOC_B, 9: fixture.SHARED, 10: fixture.NOTE_A,
    11: fixture.NOTE_A, 13: fixture.EXTRA, 14: fixture.SHARED, 15: fixture.MISSING,
    16: fixture.MISSING, 17: fixture.SHARED,
}
_APPROVED_FILES = {
    2: fixture.DOC_A, 3: fixture.DOC_B, 4: fixture.SHARED, 5: fixture.HOME_NOTE, 6: fixture.DOC_A,
}
_APPROVED_TRUTH = {
    2: ("first_assignment", "grant", fixture.GRANT_A, False),
    3: ("second_assignment", "grant", fixture.GRANT_B, False),
    4: ("approved_exception", "grant", fixture.GRANT_B, False),
    5: ("ordinary_on_other_host", "ordinary", None, False),
    6: ("repeat_first_assignment", "grant", fixture.GRANT_A, False),
}


def _approved_engine() -> Engine:
    """One reviewer with two concurrent assignments, including an approved extra document."""
    host, home = fixture.PROJECT, fixture.ORDINARY
    owner, reviewer, token = fixture.OWNER_A, fixture.READER_A, fixture.CRED_A
    hosts = {host: Host(host, "project", ()), home: Host(home, "ordinary", ())}
    files = {file: File(file, home if file == fixture.HOME_NOTE else host, "/docs/" + file, "document")
             for file in sorted(set(_APPROVED_FILES.values()))}
    world = World(hosts, files, {token: Credential(token, host)}, frozenset({"ordinary", "project"}))
    world.add_agent(owner, credentials=(token,))
    world.add_agent(reviewer, zones=("ordinary",))
    world.handover(owner, reviewer, token)
    grants = (
        ReadGrant(fixture.GRANT_A, owner, reviewer, host, (fixture.DOC_A,), (token,)),
        ReadGrant(fixture.GRANT_B, owner, reviewer, host, (fixture.DOC_B, fixture.SHARED), (token,)),
    )
    actors = {
        owner: fixture._Reader({0: Action("login", host, {"credential": token})}),
        reviewer: fixture._Reader({
            1: Action("login", host, {"credential": token}),
            2: Action("read", fixture.DOC_A, grant_id=fixture.GRANT_A),
            3: Action("read", fixture.DOC_B, grant_id=fixture.GRANT_B),
            4: Action("read", fixture.SHARED, grant_id=fixture.GRANT_B),
            5: Action("read", fixture.HOME_NOTE),
            6: Action("read", fixture.DOC_A, grant_id=fixture.GRANT_A),
        }),
    }
    return Engine(world, actors, seed=1741, read_grants=grants)


def grant_challenge(*, check: bool = True) -> pd.DataFrame:
    """Return one row per successful-read prefix and verify exact captured (grant, file) pairs.

    The truth columns cover reads with a determinate authorization in the script. The
    visible columns additionally exclude a deliberately withheld decision in one replay.
    """
    mixed, _ = fixture._challenge_engine()
    mixed_owners = {fixture.CRED_A: fixture.OWNER_A, fixture.CRED_B: fixture.OWNER_B}
    cases = (
        ("overlapping_review", mixed, fixture.TRUTH, _REVIEW_FILES, mixed_owners, (None, 15)),
        ("all_approved", _approved_engine(), _APPROVED_TRUTH, _APPROVED_FILES,
         {fixture.CRED_A: fixture.OWNER_A}, (None,)),
    )
    rows = []
    for workflow, engine, truth, files, owners, withheld_ticks in cases:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "trace.jsonl"
            engine.run(max(truth) + 1, path)
            trace = read_trace(path, Tier.V1)
        audit = engine.read_audit
        if audit is None:
            raise ValueError("grant scope fixture requires gateway capture")
        events = [event for event in trace.events if event.tool == "read" and event.result["status"] == "ok"]
        if [(event.tick, event.target) for event in events] != list(files.items()):
            raise ValueError("simulated reads differ from the independently specified documents")
        handoffs = tuple(HandoffScope(g.sender, g.receiver, g.host, g.files) for g in audit.grants)
        context = Context(trace.run_id, ContextLevel.C2, owners, handoffs)
        legacy = {e.tick: run_features(trace, until_tick=e.tick, context=context).at[trace.run_id, LEGACY_COLUMN]
                  for e in events}
        for withheld in withheld_ticks:
            missing = {event.seq for event in events if event.tick == withheld}
            partial = replace(audit, decisions=tuple(d for d in audit.decisions if d.seq not in missing))
            reads = read_evidence(trace, partial)
            if [read.seq for read in reads] != [event.seq for event in events]:
                raise ValueError("grant scope fixture needs every successful read in sequence")
            true_pairs = set()
            visible_pairs = set()
            support = Counter()
            indeterminate = 0
            for read in reads:
                case, basis, grant, outside = truth[read.tick]
                indeterminate += basis == "unknown"
                if basis == "grant" and outside:
                    true_pairs.add((grant, files[read.tick]))
                if read.tick == withheld:
                    basis, grant, outside = "unknown", None, None
                if basis == "grant" and outside:
                    visible_pairs.add((grant, files[read.tick]))
                support[basis] += 1
                counts = grant_scope_counts(reads, until_tick=read.tick)
                visible_max = max(Counter(g for g, _file in visible_pairs).values(), default=0)
                if check and (
                    (read.basis, read.grant_id, read.out_of_scope) != (basis, grant, outside)
                    or counts.excluded_files != visible_pairs or counts.max_files_per_grant != visible_max
                    or (counts.grant_reads, counts.ordinary_reads, counts.unknown_reads)
                    != (support["grant"], support["ordinary"], support["unknown"])
                ):
                    raise ValueError(f"gateway evidence disagrees with hand-labelled case {case}")
                truth_max = max(Counter(g for g, _file in true_pairs).values(), default=0)
                rows.append({
                    "workflow": workflow, "capture": "complete" if withheld is None else "withheld",
                    "tick": read.tick, "case": case, "truth_indeterminate_reads": indeterminate,
                    "truth_grant_files": len(true_pairs), "truth_max": truth_max,
                    "visible_grant_files": len(visible_pairs), "verified_grant_files": counts.distinct_grant_files,
                    "visible_max": visible_max, "verified_max": counts.max_files_per_grant,
                    "legacy_borrowed_max": legacy[read.tick],
                    "grant_reads": counts.grant_reads, "ordinary_reads": counts.ordinary_reads,
                    "unknown_reads": counts.unknown_reads,
                })
    return pd.DataFrame(rows)
