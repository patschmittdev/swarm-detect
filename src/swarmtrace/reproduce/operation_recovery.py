"""Recover original dispatch decisions from a separately retained issuer copy at case end."""

import csv
import gzip
from dataclasses import dataclass, replace
from pathlib import Path

from swarmtrace.eval.dispatch_baselines import GatewayDocumentOffice
from swarmtrace.eval.recipient_dispatch import _audit, _decisions, evaluate_office
from swarmtrace.eval.recipient_lab import Approval, Arrived, Delivery, Version
from swarmtrace.reproduce import dispatch_workflows as workflow
from swarmtrace.reproduce.public_tickets import Ticket, digest, key


@dataclass(frozen=True)
class EffectiveApproval:
    dispatch_step: int
    approval: Approval


class IssuerArchiveOffice(GatewayDocumentOffice):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._issued: dict[tuple[str, str, Version], list[Approval]] = {}

    def _approve(self, step: int, roles: list[str]) -> None:
        super()._approve(step, roles)
        # Copy the issuer's own register during the transaction, before dispatch or transport.
        # Later writes to the same version replace the live policy but preserve issued handles.
        published = replace(self._policies[self.current])
        self._issued.setdefault((published.authority, published.ticket, published.version), []).append(published)

    def lookup(self, authority, ticket, handle, version, dispatch_step):
        """Return the requested grant only if it was active for this exact scope at dispatch."""
        if type(dispatch_step) is not int or dispatch_step < 1:
            return None
        history = self._issued.get((authority, ticket, version), ())
        active = next((p for p in reversed(history) if p.step < dispatch_step), None)
        return EffectiveApproval(dispatch_step, active) if active and active.key == handle else None


def _valid_reply(reply, request):
    if not isinstance(reply, EffectiveApproval) or type(reply.dispatch_step) is not int:
        return False
    approval = reply.approval
    return (isinstance(approval, Approval)
            and (approval.authority, approval.ticket, approval.key, approval.version, reply.dispatch_step) == request
            and type(approval.step) is int and 0 <= approval.step < reply.dispatch_step
            and isinstance(approval.recipients, frozenset)
            and all(isinstance(r, str) and r for r in approval.recipients))


def recover_at_end(arrivals, authority, lookup, *, end):
    """Verify a missing handle at each dispatch. Counts are distinct requested and restored approvals."""
    records, _, _ = _audit(arrivals)
    missing = {}
    for delivery in records.values():
        if isinstance(delivery, Delivery) and delivery.approval and delivery.approval not in records:
            request = (authority, delivery.ticket, delivery.approval, delivery.version, delivery.step)
            missing.setdefault(request, set()).add(delivery.key)
    candidates = {}
    for request in missing:
        reply = lookup(*request)
        if _valid_reply(reply, request):
            candidates[request] = reply.approval
    policies = [r for r in records.values() if isinstance(r, Approval)] + list(candidates.values())
    restored, certified = {}, set()
    for request, answer in candidates.items():
        scope = answer.authority, answer.ticket, answer.version
        if any((p.key == answer.key and p != answer) or
               ((p.authority, p.ticket, p.version) == scope and answer.step < p.step < request[-1])
               for p in policies):
            continue
        certified.update(missing[request])
        restored[answer.key] = answer
    # A single restored grant can be referenced by several deliveries. Withhold its
    # binding in the review view for any dispatch the issuer could not certify.
    uncertified = {key for keys in missing.values() for key in keys} - certified
    observed = [replace(a, record=replace(a.record, approval=None)) if a.record.key in uncertified else a
                for a in arrivals]
    end = max([end, *(a.at for a in arrivals)])
    # The same released aggregate receipt decision is applied with and without recovered evidence.
    decision = _decisions([*observed, *(Arrived(end, grant) for grant in restored.values())], authority)[3]
    return decision.status, len({r[:4] for r in missing}), len(restored)


def _counts(rows, method):
    effects = [r for r in rows if r["policy_effect"] == "yes"]
    controls = [r for r in rows if r["policy_effect"] == "no"]
    if len(effects) + len(controls) != len(rows):
        raise ValueError("a historical physical outcome is not adjudicated")
    return dict(detections=sum(r[method] == "alert" for r in effects),
                false_alerts=sum(r[method] == "alert" for r in controls),
                unknown_positive=sum(r[method] == "unknown" for r in effects),
                unknown_control=sum(r[method] == "unknown" for r in controls))


def historical_recovery(tickets: list[Ticket], groups: dict, dispatch_study: Path) -> tuple[list[dict], dict]:
    protocol = workflow.read_protocol(dispatch_study)
    with gzip.open(dispatch_study / "runs.csv.gz", "rt", encoding="utf-8", newline="") as stream:
        saved = [r for r in csv.DictReader(stream) if r["primary"] == "True" and r["split"] == "confirmation"]
    archived = {r["base_id"]: r for r in saved}
    with (dispatch_study / "sources.csv").open(encoding="utf-8", newline="") as stream:
        source_rows = [s for s in csv.DictReader(stream) if s["split"] == "confirmation"]
    sources = {s["base_id"]: s for s in source_rows}
    confirmed = sorted((t for t in tickets if groups[t.base_id][0] == "confirmation"), key=lambda t: t.base_id)
    if (len(saved) != len(archived) or len(confirmed) != len(archived) or len(source_rows) != len(sources)
            or set(sources) != set(archived) or set(archived) != {t.base_id for t in confirmed}):
        raise ValueError("historical primary membership differs from the dispatch release")
    rows = []
    for task in confirmed:
        if len(task.stages) != 1:
            raise ValueError("historical dispatch confirmation requires one stage per base")
        stage, = task.stages
        source = sources[task.base_id]
        if (stage.stage_id, stage.document, digest(stage.text.encode()), stage.ticket_digest, stage.recipients) != (
                source["stage_id"], source["document"], source["document_sha256"], source["ticket_sha256"],
                tuple(source["named_recipients"].split("|"))):
            raise ValueError("historical stage, document version or designated recipients differ from the release")
        focal, _, profile = workflow.design(task, protocol)
        run_id = key(protocol["salt"], "gateway", task.base_id, profile, str(focal))[:16]
        office, arrivals, _ = workflow._execute(stage, profile, run_id, protocol, office_factory=IssuerArchiveOffice)
        fact, _ = evaluate_office(office, arrivals)
        old = archived[task.base_id]
        group = groups[task.base_id][1]
        if (profile, group, fact["policy_effect"], fact["commit"]) != (
                old["profile"], old["template_group"], old["policy_effect"], old["commit"]):
            raise ValueError("historical primary schedule, physical outcome or committed-use decision differs")
        authority = office.workflow.authority
        result, requested, restored = recover_at_end(arrivals, authority, office.lookup, end=office.step + 1)
        unavailable, _, _ = recover_at_end(arrivals, authority, lambda *_: None, end=office.step + 1)
        if unavailable != old["commit"]:
            raise ValueError("empty issuer response changed the historical decision")
        rows.append(dict(base_id=task.base_id, stage_id=stage.stage_id, run_id=run_id, template_group=group,
                         profile=profile, policy_effect=fact["policy_effect"], original_commit=old["commit"],
                         issuer_commit=result, empty_issuer_commit=unavailable,
                         requested_approvals=requested, recovered_approvals=restored))
    methods = {m: _counts(rows, m) for m in ("original_commit", "issuer_commit", "empty_issuer_commit")}
    summary = dict(cases=len(rows), positives=sum(r["policy_effect"] == "yes" for r in rows),
                   controls=sum(r["policy_effect"] == "no" for r in rows),
                   requested_approvals=sum(r["requested_approvals"] for r in rows),
                   recovered_approvals=sum(r["recovered_approvals"] for r in rows), methods=methods,
                   newly_detected_effects=sum(r["policy_effect"] == "yes" and r["issuer_commit"] == "alert"
                                              and r["original_commit"] != "alert" for r in rows),
                   independent_swarm_rounds=0)
    return rows, summary
