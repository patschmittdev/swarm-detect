"""Secondary, outcome-independent reconstruction of focal-team assignment evidence."""

import json
from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from swarmtrace.features.read_evidence import read_evidence
from swarmtrace.sim.runner import build_run, run_one
from swarmtrace.trace.authorization import ReadAudit
from swarmtrace.trace.io import RunPaths, Trace, read_labels

from . import assignment_round as study_round
from . import grant_round, read_round
from .assignment_workflows import WORKFLOWS, make_assignment_view
from .scope import _map, _worker_threads

PUBLISHED_COUNTS = ("shared_verified_documents", "shared_reads_before_component_end",
                    "office_tickets", "exercised_office_tickets", "office_unknown_reads",
                    "office_missing_decisions")
FLAGS = ("positive", "small_positive", "hard_control")
ARMS = (study_round.REFERENCE, study_round.VERIFIED, study_round.POOLED,
        study_round.SHARED_WEIGHTS, study_round.CANDIDATE)


@dataclass(frozen=True)
class _Match:
    reviewer: str
    host: str
    file: str
    native_tick: int
    office_tick: int
    tickets: tuple[str, ...]
    clerk_reads: tuple[tuple[int, int], ...]  # (combined seq, tick)


@dataclass(frozen=True)
class _Evidence:
    run_id: str
    ends: dict[str, int]
    native_keys: Counter
    unknown: Counter
    missing: Counter
    matches: tuple[_Match, ...]
    published_counts: dict[str, int]


def _observation(trace: Trace, native: ReadAudit, view: Trace, extended: ReadAudit,
                 support: dict, family: str) -> _Evidence:
    """Freeze actor/object matches without any focal identity, strict class or model score."""
    if trace.run_id != view.run_id or support["family"] != family or family not in WORKFLOWS:
        raise ValueError("focal evidence needs corresponding native and workflow observations")
    source_reads = read_evidence(trace, native)
    added_reads = read_evidence(view, extended)
    old = {g.grant_id: g for g in native.grants}
    registry = {g.grant_id: g for g in extended.grants}
    if any(registry.get(key) != grant for key, grant in old.items()):
        raise ValueError("workflow registry changed an original grant")
    ends = {e.agent: e.tick for e in trace.events}
    native_calls = {(e.agent, e.tick): e for e in trace.events}
    old_decisions = {d.seq: d for d in native.decisions}
    combined_decisions = {d.seq: d for d in extended.decisions}
    final_writes = {e.target: e.seq for e in trace.events if e.tool == "write" and e.result["status"] == "ok"}
    original_files = {e.target for e in trace.events if e.tool in ("read", "write")}
    latest = -1
    inserted = set()
    sends = defaultdict(list)
    receipts = defaultdict(list)
    for e in view.events:
        source = native_calls.get((e.agent, e.tick))
        if source is not None:
            recorded = combined_decisions.get(e.seq)
            if (source.seq != latest + 1 or replace(e, seq=source.seq) != source
                    or (replace(recorded, seq=source.seq) if recorded else None) != old_decisions.get(source.seq)):
                raise ValueError("workflow replay changed a native event or its authorization")
            latest = source.seq
            continue
        inserted.add(e.seq)
        if e.tool == "write" and e.target in original_files and e.result["status"] == "ok":
            raise ValueError("office changed the version of an original file")
        if e.result["status"] == "ok" and e.tool in ("send", "recv"):
            sender, receiver = (e.agent, e.target) if e.tool == "send" else (e.target, e.agent)
            collection = sends if e.tool == "send" else receipts
            collection[sender, receiver].append((e.seq, e.args["size"], e.args["digest"]))
    if latest + 1 != len(trace.events):
        raise ValueError("workflow replay omitted original events")

    native_witnesses = {}
    unknown, missing = Counter(), Counter()
    for read in source_reads:
        if read.basis == "unknown":
            unknown[read.agent] += 1
            missing[read.agent] += int(read.seq not in old_decisions)
        if read.basis == "grant" and read.out_of_scope is False and read.seq > final_writes.get(read.file, -1):
            native_witnesses.setdefault((read.agent, old[read.grant_id].host, read.file), read.tick)

    # Keep only explicitly exercised office grants and covered reads, independently of
    # whether a different actor/registration could also have approved the same object.
    reviewers = defaultdict(list)
    clerks = defaultdict(list)
    seen_grants = set()
    office_unknown = office_missing = 0
    for read in added_reads:
        if read.seq not in inserted:
            continue
        if read.basis == "unknown":
            office_unknown += int(read.seq in combined_decisions)
            office_missing += int(read.seq not in combined_decisions)
        if read.basis != "grant" or read.grant_id in old:
            continue
        seen_grants.add(read.grant_id)
        if read.out_of_scope is not False:
            continue
        grant = registry[read.grant_id]
        if read.agent in ends:
            key = (read.agent, grant.host, read.file)
            if key in native_witnesses and native_witnesses[key] < read.tick:
                reviewers[key].append((read.seq, read.tick, grant))
        else:
            clerks[grant.host, read.file].append((read.seq, read.tick, grant))

    matches = []
    for (reviewer, host, file), uses in sorted(reviewers.items()):
        witness = native_witnesses[reviewer, host, file]
        linked = set()
        for seq, tick, clerk_ticket in clerks[host, file]:
            if tick <= witness:
                continue
            for review_seq, _, review_ticket in uses:
                if seq >= review_seq:
                    continue
                if family == "record_check":
                    connected = clerk_ticket.sender == review_ticket.sender
                else:
                    clerk = clerk_ticket.receiver
                    connected = clerk == review_ticket.sender and any(
                        seq < sent < got < review_seq and (size, digest) == (received_size, received_digest)
                        for sent, size, digest in sends[clerk, reviewer]
                        for got, received_size, received_digest in receipts[clerk, reviewer])
                if connected:
                    linked.add((seq, tick))
                    break
        matches.append(_Match(reviewer, host, file, witness, min(tick for _, tick, _ in uses),
                              tuple(sorted({g.grant_id for _, _, g in uses})), tuple(sorted(linked))))
    counts = {k: support[k] for k in PUBLISHED_COUNTS}
    direct = (len(registry) - len(old), len(seen_grants), office_unknown, office_missing)
    if direct != tuple(counts[k] for k in PUBLISHED_COUNTS[2:]):
        raise ValueError("office registration, read or missing-decision counts differ from the replay")
    return _Evidence(trace.run_id, ends, Counter(a for a, _, _ in native_witnesses), unknown,
                     missing, tuple(matches), counts)


def _freeze_job(task):
    grid, job, family, metadata = task
    with TemporaryDirectory(dir=metadata) as temp:
        paths = RunPaths(run_one(job.condition, job.seed, temp, capture_authorization=True))
        trace, ctx, audit = study_round._read(paths)
        view, _, extended, support = make_assignment_view(trace, ctx, audit, family=family)
        result = _observation(trace, audit, view, extended, support, family)
        # Retain the unopened native label files. Every observation in the complete
        # study is frozen before the separate focal-roster/strict-class pass starts.
        destination = RunPaths(metadata / str(grid) / job.directory)
        destination.run_dir.mkdir(parents=True)
        paths.labels.replace(destination.labels)
        paths.manifest.replace(destination.manifest)
        return result


def _attribute(evidence: _Evidence, members: frozenset[str] | None) -> dict:
    roster = bool(members)
    members = members or frozenset()
    active = members & evidence.ends.keys()
    end = max((evidence.ends[a] for a in active), default=None)
    matches = [m for m in evidence.matches if m.reviewer in members]
    clerks = {p for m in matches for p in m.clerk_reads}
    early = {p for p in clerks if end is not None and p[1] < end}
    unknown = sum(evidence.unknown[a] for a in members)
    incomplete = not roster or bool(unknown or evidence.published_counts["office_unknown_reads"]
                                    or evidence.published_counts["office_missing_decisions"])

    def status(observed: bool) -> str:
        if observed:
            return "observed"
        return "unknown" if incomplete else "none_observed"

    data = {
        "focal_roster_size": len(members), "observed_focal_workers": len(active),
        "focal_native_verified_keys": sum(evidence.native_keys[a] for a in members),
        "focal_native_unknown_reads": unknown, "focal_native_missing_decisions": sum(evidence.missing[a] for a in members),
        "focal_matched_keys": len(matches), "focal_matched_documents": len({m.file for m in matches}),
        "focal_matched_workers": len({m.reviewer for m in matches}),
        "focal_matched_office_tickets": len({t for m in matches for t in m.tickets}),
        "focal_multiple_ticket_keys": sum(len(m.tickets) > 1 for m in matches),
        "focal_matched_clerk_reads": len(clerks), "focal_clerk_reads_before_end": len(early),
        "focal_documents_with_early_clerk": len({m.file for m in matches if early.intersection(m.clerk_reads)}),
    }
    keys = [dict(reviewer=m.reviewer, host=m.host, file=m.file, native_tick=m.native_tick,
                 first_office_reviewer_tick=m.office_tick, office_tickets=m.tickets,
                 clerk_reads=m.clerk_reads) for m in matches]
    return {
        **{k: v if roster else None for k, v in data.items()}, "focal_last_native_tick": end,
        "focal_link_status": status(bool(matches)),
        "focal_timing_status": status(bool(early)) if end is not None else "unknown",
        "focal_witnesses": json.dumps(keys, separators=(",", ":")) if roster else None,
    }


def _label_job(item):
    (grid, job, family, metadata), evidence = item
    paths = RunPaths(metadata / str(grid) / job.directory)
    truth = grant_round._truth(paths, evidence.run_id)
    setup = build_run(job.condition, job.seed)
    focal = setup.groups[setup.focal_group]
    members = frozenset(focal.members)
    tags = read_labels(paths.labels)
    if not members or members != {a for a, tag in tags.agents.items() if tag.group == focal.id}:
        raise ValueError("native focal roster differs from the recorded group")
    return dict(grid=grid, family=family, run_id=evidence.run_id, **{k: truth[k] for k in FLAGS},
                **evidence.published_counts, focal_group=focal.id, **_attribute(evidence, members))


def _validate(study: Path, rows: pd.DataFrame, seeds: tuple[int, ...]) -> None:
    """Check the original observation and class counts without loading any detector score."""
    protocol = json.loads((study / "protocol.json").read_bytes())
    if (protocol.get("confirmation_seeds") != list(seeds) or protocol.get("primary_view") != "workflow"
            or protocol.get("candidate") != study_round.CANDIDATE):
        raise ValueError("study does not contain the published assignment confirmation")
    if (not rows.run_id.is_unique or set(rows.grid) != set(seeds)
            or not rows.run_id.str.fullmatch(r"[0-9a-f]{16}").all()):
        raise ValueError("focal replay needs unique original run IDs on every confirmation grid")
    folder = study / "workflow"
    meta = ["grid", "family", *FLAGS, *PUBLISHED_COUNTS]
    for i, seed in enumerate(seeds):
        path = folder / f"{seed}.csv.gz"
        raw = pd.read_csv(path, dtype=str, keep_default_na=False,
                          usecols=["run_id", "task", "view", "test_set", "detector", *meta])
        if (set(raw.task) != {"scope"} or set(raw.view) != {"workflow"} or set(raw.test_set) != {"independent"}
                or set(raw.family) != {WORKFLOWS[i % len(WORKFLOWS)]} or set(raw.detector) != set(ARMS)):
            raise ValueError(f"{path} has unexpected tasks, populations or detector arms")
        expected = rows.loc[rows.grid.eq(seed)].set_index("run_id")[meta].sort_index().astype(str)
        for name, group in raw.groupby("detector"):
            published = group.set_index("run_id")[meta].sort_index()
            if not published.index.is_unique or not published.equals(expected):
                raise ValueError(f"{path} differs from replayed IDs, strict labels or support counts for {name}")

    outcomes = ("positives", "controls", "small_positives", "hard_controls")
    card = pd.read_csv(folder / "scorecard.csv", dtype=str, keep_default_na=False,
                       usecols=["reference", "candidate", "population", "source", *outcomes])
    card = card.loc[card.reference.eq(study_round.REFERENCE) & card.candidate.eq(study_round.CANDIDATE)]
    populations = {("grid", f"{s}.csv.gz"): rows.loc[rows.grid.eq(s)] for s in seeds}
    populations["pooled", ""] = rows
    if len(card) != len(populations) or set(zip(card.population, card.source)) != populations.keys():
        raise ValueError("primary scorecard population sources do not match the focal replay")
    for r in card.itertuples(index=False):
        sample = populations[r.population, r.source]
        counts = (sample.positive.sum(), (~sample.positive).sum(), sample.small_positive.sum(), sample.hard_control.sum())
        if tuple(int(getattr(r, k)) for k in outcomes) != counts:
            raise ValueError("primary scorecard strict population counts differ from the focal replay")


def _summary(rows: pd.DataFrame) -> pd.DataFrame:
    summaries = []
    count_columns = ("focal_native_verified_keys", "focal_matched_keys", "focal_matched_documents",
                     "focal_multiple_ticket_keys", "focal_matched_office_tickets", "focal_matched_clerk_reads",
                     "focal_clerk_reads_before_end", "focal_documents_with_early_clerk",
                     "focal_native_unknown_reads", "focal_native_missing_decisions")
    for family in (*WORKFLOWS, "pooled"):
        group = rows if family == "pooled" else rows.loc[rows.family.eq(family)]
        for run_class, sample in (("control", group.loc[~group.positive]), ("positive", group.loc[group.positive]),
                                  ("one_file_positive", group.loc[group.small_positive]),
                                  ("in_scope_control", group.loc[group.hard_control]), ("all", group)):
            record = dict(family=family, run_class=run_class, runs=len(sample),
                          any_native_shared_document_runs=int(sample.shared_verified_documents.gt(0).sum()),
                          runs_with_multiple_focal_tickets=int(sample.focal_multiple_ticket_keys.gt(0).sum()))
            for measure in ("link", "timing"):
                states = sample[f"focal_{measure}_status"]
                for status in ("observed", "none_observed", "unknown"):
                    record[f"{measure}_{status}_runs"] = int(states.eq(status).sum())
                record[f"{measure}_observed_fraction_of_all_runs"] = (
                    float(states.eq("observed").mean()) if len(states) else None)
            for k in count_columns:
                record[k] = int(sample[k].sum()) if sample[k].notna().any() else None
            summaries.append(record)
    return pd.DataFrame(summaries)


def audit_assignment_support(study: Path, out: Path, workers: int = 4) -> None:
    """Replay only the completed confirmation and atomically publish secondary linkage coverage."""
    study, out = Path(study), Path(out)
    seeds = study_round.CONFIRMATION_SEEDS
    if (type(workers) is not int or workers < 1 or out.exists()
            or out.resolve().is_relative_to(study.resolve())):
        raise ValueError("focal support requires positive workers and a separate, new output directory")
    required = [study / "protocol.json", study / "workflow/scorecard.csv",
                *(study / "workflow" / f"{s}.csv.gz" for s in seeds)]
    if not all(p.is_file() for p in required):
        raise ValueError("focal support requires the published workflow scorecard and complete confirmation")
    out.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=out.parent) as temp, _worker_threads():
        metadata, stage = Path(temp) / "metadata", Path(temp) / "support"
        metadata.mkdir()
        stage.mkdir()
        tasks = [(s, job, WORKFLOWS[i % len(WORKFLOWS)], metadata) for i, s in enumerate(seeds)
                 for job in read_round._jobs(s, (read_round.CONFIRMATION_CHANNEL,))]
        observed = _map(_freeze_job, tasks, workers)
        rows = pd.DataFrame(_map(_label_job, list(zip(tasks, observed, strict=True)), workers))
        rows = rows.sort_values(["grid", "run_id"]).reset_index(drop=True)
        _validate(study, rows, seeds)
        grant_round._write_table(stage / "runs.csv.gz", rows)
        _summary(rows).to_csv(stage / "summary.csv", index=False, lineterminator="\n")
        stage.rename(out)
