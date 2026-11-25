"""Replay third-party approval tickets with locally instrumented dispatch and document use."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from swarmtrace.eval.dispatch_baselines import (
    DESK_COPY,
    ITEMS,
    SETUP_TICKS,
    DispatchBaselines,
    GatewayDocumentOffice,
)
from swarmtrace.eval.dispatch_scorecard import METHODS, report
from swarmtrace.eval.recipient_dispatch import evaluate_office
from swarmtrace.eval.recipient_lab import Approval, Commit, Delivery, Seal, Workflow
from swarmtrace.features.read_evidence import read_evidence

from . import grant_round
from .public_tickets import Stage, Ticket, digest, key, read_tickets, split_tickets

PROTOCOL_SHA256 = "24a91d17bcac2ba71ef8baee829577f032e75c14265b2f0e1be03a9b540e7133"
PROBES = ("late_clerical_slip", "matched_deliberate_review")


def read_protocol(root: Path) -> dict:
    source = (root / "protocol.json").read_text(encoding="utf-8").encode()
    if digest(source) != PROTOCOL_SHA256:
        raise ValueError("public dispatch protocol has changed since the round was frozen")
    return json.loads(source)


def design(task: Ticket, protocol: dict):
    def select(purpose, size):
        return int(key(protocol["salt"], purpose, task.base_id), 16) % size

    focal = select("stage", len(task.stages))
    profiles = [name for name in protocol["profiles"]
                if name != "preapproved_second_reviewer" or len(task.stages[focal].recipients) > 1]
    return focal, profiles, profiles[select("primary", len(profiles))]


def _execute(stage: Stage, profile: str, run_id: str, protocol: dict, *, excluded_role: str = "unlisted_records_clerk",
             office_factory=GatewayDocumentOffice):
    substitute = profile == "preapproved_second_reviewer"
    if substitute and len(stage.recipients) < 2:
        raise ValueError("ticket has no preapproved second recipient for this version")
    if not substitute and (excluded_role in stage.recipients or excluded_role == stage.author):
        raise ValueError("the excluded recipient must be a distinct worker outside the document's routing list")
    alternate = stage.recipients[1] if substitute else excluded_role
    office = office_factory(
        Workflow("ticket_authority", stage.author, stage.recipients[0], alternate, stage.document, stage.text),
        run_id=run_id, read_scopes={"assigned": ("source", "worksheet"),
                                    "alternate": ("source", "worksheet") if substitute else ("worksheet",)})
    office.execute(protocol["profiles"][profile])
    transport = protocol["transport"].get(profile, {})
    arrivals = office.deliver_audit(transport.get("drop", []), transport.get("delay_to", {}))
    return office, arrivals, transport.get("missing_read_steps", ())


def _panel(office: GatewayDocumentOffice, case_id: str, base_id: str) -> dict:
    """Build a blind, complete referee record before labels or detector predictions are opened."""
    trace, _, audit = office.snapshot()
    people = (office.workflow.author, office.workflow.assigned, office.workflow.alternate)
    ordered = sorted(people, key=lambda who: key(base_id, who))
    aliases = {who: f"P{i + 1}" for i, who in enumerate(ordered)}
    native = {f"a-{i:08x}": aliases[who] for i, who in enumerate(people, 1)}
    objects = {value: item for item, value in ITEMS.items()} | {DESK_COPY: "personal_copy"}
    grant_ids = {g.grant_id: "grant_" + native[g.receiver] for g in audit.grants}
    scopes = {grant_ids[g.grant_id]: {"holder": native[g.receiver],
                                      "files": sorted(objects[f] for f in g.files)} for g in audit.grants}
    events = []
    for r in office.receipts:
        if isinstance(r, Approval):
            events.append(dict(id=r.key, at=r.step, event="approval", version=r.version.digest,
                               allowed=sorted(aliases[p] for p in r.recipients)))
        elif isinstance(r, Delivery):
            events.append(dict(id=r.key, at=r.step, event="delivery", version=r.version.digest,
                               sender=aliases[r.sender], recipient=aliases[r.recipient], approval=r.approval))
        elif isinstance(r, Commit):
            events.append(dict(id=r.key, at=r.step, event="commit", worker=aliases[r.recipient],
                               version=r.source.version.digest if r.source else None,
                               delivery=r.source.delivery if r.source else None))
        elif isinstance(r, Seal):
            events.append(dict(id=r.key, at=r.step, event="seal"))
    for r in read_evidence(trace, audit):
        events.append(dict(id=f"read:{r.seq}", at=r.tick - SETUP_TICKS, event="read", worker=native[r.agent],
                           file=objects[r.file], grant=grant_ids.get(r.grant_id), basis=r.basis))
    return dict(case_id=case_id, grants=scopes, events=sorted(events, key=lambda e: (e["at"], e["id"])))


def blind_packets(tickets, groups, protocol):
    packets, mapping = [], []
    probe_done = False
    for task in tickets:
        if groups[task.base_id][0] != "confirmation":
            continue
        focal, _, primary = design(task, protocol)
        if len(task.stages) != 1:
            raise ValueError("the frozen confirmation review panel requires single-stage source tickets")
        profiles = [primary]
        if not probe_done and primary not in PROBES:
            profiles.extend(PROBES)
            probe_done = True
        for profile in profiles:
            case_id = key(protocol["salt"], "blind", task.base_id, profile)[:16]
            run_id = key(protocol["salt"], "gateway", task.base_id, profile, str(focal))[:16]
            office, _, _ = _execute(task.stages[focal], profile, run_id, protocol)
            packets.append(_panel(office, case_id, task.base_id))
            mapping.append(dict(case_id=case_id, base_id=task.base_id, profile=profile, primary=profile == primary))
    if len({p["case_id"] for p in packets}) != len(packets) or not probe_done:
        raise ValueError("invalid blind packet membership")
    return sorted(packets, key=lambda p: p["case_id"]), sorted(mapping, key=lambda r: r["case_id"])


def _first(*times):
    return min((t for t in times if t is not None), default=None)


def _stage_result(stage, profile, run_id, protocol, baselines):
    office, arrivals, missing = _execute(stage, profile, run_id, protocol)
    fact, deliveries = evaluate_office(office, arrivals)
    timeline = baselines.score_timeline(office, range(office.step + 1), missing_read_steps=missing)
    final = timeline[-1]
    trace, _, complete = office.snapshot()
    excluded = {r.file for r in read_evidence(trace, complete) if r.out_of_scope is True}
    end = max([office.step, *(arrival.at for arrival in arrivals)])
    row = dict(policy_effect=fact["policy_effect"], effect_step=fact["effect_step"],
               source_sha256=digest(stage.text.encode()), read_excluded_files=len(excluded),
               observed_excluded_files=final.distinct_excluded_files, unknown_reads=final.unknown_reads,
               missing_decisions=final.missing_decisions, stage_end=end)
    for name in ("margin", "assignment"):
        alert = getattr(final, f"{name}_alert")
        crossing = next((s.step for s in timeline if getattr(s, f"{name}_alert")), None)
        row.update({name: "alert" if alert else "clear", f"{name}_score": getattr(final, name),
                    f"{name}_step": crossing, f"{name}_matched_step": None})
    for name, released in (("dispatch", "dispatch"), ("commit", "commit"), ("peer_read", "proxy")):
        row[name] = fact[released]
        row[f"{name}_step"] = fact[f"{released}_step"]
        row[f"{name}_matched_step"] = fact[f"{released}_matched_step"]
        row[f"{name}_score"] = float(row[name] == "alert")
    row["margin_or_dispatch"] = "alert" if final.margin_alert else row["dispatch"]
    row["margin_or_dispatch_score"] = float(row["margin_or_dispatch"] == "alert")
    row["margin_or_dispatch_step"] = _first(row["margin_step"], row["dispatch_step"])
    row["margin_or_dispatch_matched_step"] = row["dispatch_matched_step"]
    return row, deliveries


def _aggregate(stages):
    offsets, elapsed = [], 0
    for stage in stages:
        offsets.append(elapsed)
        elapsed += stage["stage_end"] + 1
    first = next((i for i, r in enumerate(stages) if r["effect_step"] is not None), None)
    policy_effect = "yes" if first is not None else "no"
    if first is None and any(stage["policy_effect"] == "unknown" for stage in stages):
        policy_effect = "unknown"
    result = dict(policy_effect=policy_effect,
                  effect_step=None if first is None else offsets[first] + stages[first]["effect_step"],
                  read_excluded_files=sum(s["read_excluded_files"] for s in stages),
                  unknown_reads=sum(s["unknown_reads"] for s in stages),
                  missing_decisions=sum(s["missing_decisions"] for s in stages))
    for method in METHODS:
        states = [s[method] for s in stages]
        result[method] = "alert" if "alert" in states else "unknown" if "unknown" in states else "clear"
        result[f"{method}_score"] = max(s[f"{method}_score"] for s in stages)
        crossings = (offset + stage[f"{method}_step"] for offset, stage in zip(offsets, stages, strict=True)
                     if stage[f"{method}_step"] is not None)
        result[f"{method}_step"] = min(crossings, default=None)
        linked = None if first is None else stages[first][f"{method}_matched_step"]
        result[f"{method}_matched_step"] = None if linked is None else offsets[first] + linked
    return result


def _write_packets(path, packets):
    payload = "".join(json.dumps(row, separators=(",", ":"), sort_keys=True) + "\n" for row in packets)
    path.write_bytes(payload.encode())


def run_public_dispatch(benchmark: Path, sources: Path, out: Path, *, fetch=False, review_only=False):
    if out.exists():
        raise ValueError("dispatch workflow replay requires a new output directory")
    protocol = read_protocol(benchmark)
    tickets = read_tickets(sources, protocol, fetch=fetch)
    groups = split_tickets(tickets, protocol["integration_tasks"])
    packets, mapping = blind_packets(tickets, groups, protocol)
    out.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=out.parent) as tmp:
        dest = Path(tmp) / "public"
        dest.mkdir()
        _write_packets(dest / "review-packets.jsonl", packets)
        if review_only:
            dest.rename(out)
            return
        baselines = DispatchBaselines.load(benchmark.parent)
        runs, stages, deliveries, source_rows = [], [], [], []
        for task in tickets:
            focal, profiles, primary = design(task, protocol)
            split, component = groups[task.base_id]
            for s in task.stages:
                source_rows.append(dict(base_id=task.base_id, stage_id=s.stage_id, split=split,
                                        template_group=component, family=task.family, topic=s.topic,
                                        ticket_sha256=s.ticket_digest, document=s.document,
                                        document_sha256=digest(s.text.encode()), named_recipients="|".join(s.recipients)))
            for profile in profiles:
                meta = dict(base_id=task.base_id, family=task.family, split=split, template_group=component,
                            profile=profile, primary=primary == profile)
                observed = []
                for i, stage in enumerate(task.stages):
                    run_id = key(protocol["salt"], "gateway", task.base_id, profile, str(i))[:16]
                    row, items = _stage_result(stage, profile if i == focal else "routine", run_id, protocol, baselines)
                    token = dict(stage_id=stage.stage_id, run_id=run_id, focal=i == focal)
                    stages.append({**meta, **token, **row})
                    deliveries.extend({**meta, **token, **d} for d in items)
                    observed.append(row)
                runs.append({**meta, **_aggregate(observed)})
        for name, records in (("runs", runs), ("stages", stages), ("deliveries", deliveries)):
            grant_round._write_table(dest / f"{name}.csv.gz", pd.DataFrame(records))
        pd.DataFrame(source_rows).to_csv(dest / "sources.csv", index=False, lineterminator="\n")
        pd.DataFrame(mapping).to_csv(dest / "review-membership.csv", index=False, lineterminator="\n")
        report(dest, protocol, {"margin": baselines.margin_cutoff, "assignment": baselines.assignment_cutoff})
        dest.rename(out)
