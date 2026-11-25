"""Compare a recipient warning at document dispatch with the later verified use of that copy."""

import csv
import hashlib
import json
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from .recipient import (
    Decision,
    _already_published,
    _read_frozen,
    _score,
    _timing,
    peer_read_proxy,
    recipient_use,
)
from .recipient_lab import (
    Approval,
    Arrived,
    Commit,
    Delivery,
    DocumentOffice,
    Input,
    Seal,
    Version,
    Workflow,
)

PROTOCOL_SHA256 = "b2493e11f98919ffcda296af53114aa63888891d99898616de48c5df903f988c"
METHODS = ("dispatch", "commit", "proxy")
UNKNOWN = Decision("unknown")
CLEAR = Decision("clear")


@dataclass(frozen=True)
class _Action:
    step: int
    recipient: str
    version: Version
    authorized: bool | None


class DispatchOffice(DocumentOffice):
    """Capture evaluation witnesses at the real dispatch, editor read and write transactions."""

    def __init__(self, workflow: Workflow):
        super().__init__(workflow)
        self.dispatches: dict[str, _Action] = {}
        self.read_inputs: dict[tuple[int, str, str], Input] = {}
        self.first_exact_use: dict[str, int] = {}

    def _send(self, step: int, actor: str, *, attach: bool) -> None:
        active = self._policies.get(self.current)
        super()._send(step, actor, attach=attach)
        if attach:
            handle = self._inboxes[actor].key
            self.dispatches[handle] = _Action(step, actor, self.current,
                                              actor in active.recipients if active else None)

    def _open(self, step: int, actor: str, route: str) -> None:
        super()._open(step, actor, route)
        event = self.observations[-1]
        if event.success:
            self.read_inputs[step, actor, event.target] = self._opened[actor]

    def _submit(self, step: int, actor: str, mode: str) -> None:
        source = self._opened.get(actor) if mode == "opened" else None
        super()._submit(step, actor, mode)
        if source is not None and source.delivery is not None:
            action = self.dispatches[source.delivery]
            if action.recipient == actor and action.version == source.version:
                self.first_exact_use.setdefault(source.delivery, step)


def _valid_version(version: Version) -> bool:
    return (isinstance(version, Version) and isinstance(version.document, str) and bool(version.document)
            and isinstance(version.digest, str) and re.fullmatch("[0-9a-f]{64}", version.digest) is not None)


def _audit(arrivals: list[Arrived]):
    records = {}
    times = {}
    for event in arrivals:
        r = event.record
        if (type(event.at) is not int or type(r.step) is not int or r.step < 0
                or event.at < r.step or not isinstance(r.key, str) or not r.key):
            raise ValueError("each receipt needs an identity and an arrival at or after issuance")
        if r.key in records and records[r.key] != r:
            raise ValueError(f"conflicting receipt for {r.key}")
        records[r.key] = r
        times[r.key] = min(event.at, times.get(r.key, event.at))
    seals = [r for r in records.values() if isinstance(r, Seal)]
    complete = (len(seals) == 1 and records.keys() - {seals[0].key} == seals[0].receipts
                and all(records[k].step < seals[0].step for k in seals[0].receipts))
    return records, times, complete


def _valid_delivery(d: Delivery) -> bool:
    return (all(isinstance(v, str) and v for v in (d.sender, d.recipient, d.ticket))
            and _valid_version(d.version))


def _dispatches(records, times, authority):
    if not isinstance(authority, str) or not authority:
        raise ValueError("expected an independent policy authority")
    dispatch = {}
    for d in records.values():
        if not isinstance(d, Delivery):
            continue
        approval = records.get(d.approval)
        valid_delivery = _valid_delivery(d)
        valid_policy = (valid_delivery and isinstance(approval, Approval) and approval.step < d.step
                        and (approval.authority, approval.ticket, approval.version) == (authority, d.ticket, d.version)
                        and authority not in (d.sender, d.recipient)
                        and isinstance(approval.recipients, frozenset)
                        and all(isinstance(w, str) and w for w in approval.recipients))
        if valid_policy and any(isinstance(r, Approval)
                                and (r.authority, r.ticket, r.version) == (authority, d.ticket, d.version)
                                and approval.step < r.step < d.step for r in records.values()):
            raise ValueError("dispatch identifies an approval superseded before it was issued")
        if valid_delivery and d.sender == d.recipient:
            dispatch[d.key] = CLEAR
        elif not valid_policy:
            dispatch[d.key] = UNKNOWN
        elif d.recipient in approval.recipients:
            dispatch[d.key] = CLEAR
        else:
            dispatch[d.key] = Decision("alert", max(times[d.key], times[approval.key]))
    return dispatch


def _aggregate(decisions, complete):
    first = min((d.first_alert for d in decisions if d.first_alert is not None), default=None)
    if first is not None:
        return Decision("alert", first)
    return CLEAR if complete and all(d.status == "clear" for d in decisions) else UNKNOWN


def _decisions(arrivals: list[Arrived], authority: str):
    records, times, sealed = _audit(arrivals)
    dispatch = _dispatches(records, times, authority)
    commits: dict[str, list[Commit]] = defaultdict(list)
    for record in records.values():
        if isinstance(record, Commit) and record.source is not None and record.source.delivery is not None:
            commits[record.source.delivery].append(record)
    use = {}
    for handle, decision in dispatch.items():
        d = records[handle]
        unknown = not _valid_delivery(d)
        first = None
        for c in commits.get(d.key, ()):
            if (c.step <= d.step or (c.ticket, c.recipient) != (d.ticket, d.recipient)
                    or not _valid_version(c.output) or not _valid_version(c.source.version)):
                unknown = True
                continue
            if c.source.version != d.version or c.recipient == d.sender:
                continue
            if decision.status == "unknown":
                unknown = True
            elif decision.first_alert is not None:
                at = max(decision.first_alert, times[c.key])
                first = at if first is None else min(first, at)
        use[d.key] = Decision("alert", first) if first is not None else (CLEAR if sealed and not unknown else UNKNOWN)
    return (dispatch, use, _aggregate(dispatch.values(), sealed),
            _aggregate(use.values(), sealed and commits.keys() <= dispatch.keys()))


def dispatch_warnings(arrivals: list[Arrived], authority: str) -> dict[str, Decision]:
    """Expose the policy result per observed delivery. The alert time uses only the two necessary receipts."""
    evidence = [r for r in arrivals if isinstance(r.record, (Approval, Delivery))]
    records, times, _ = _audit(evidence)
    return _dispatches(records, times, authority)


def committed_use_by_delivery(arrivals: list[Arrived], authority: str) -> dict[str, Decision]:
    """Verify the earliest available exact delivered input and unapproved committed use per handle."""
    return _decisions(arrivals, authority)[1]


def _peer_matches(office: DispatchOffice):
    writers, matched = {}, {}
    peers = defaultdict(set)
    fires = unpaired = 0
    first = None
    for e in office.observations:
        if not e.success:
            continue
        if e.tool == "write":
            writers[e.target] = e.actor
        elif e.tool == "recv" and e.target != e.actor:
            peers[e.actor].add(e.target)
        elif e.tool == "read" and writers.get(e.target) in peers[e.actor]:
            fires += 1
            if first is None:
                first = e.step
            # Offline attribution starts only after the native proxy has fired.
            source = office.read_inputs.get((e.step, e.actor, e.target))
            d = office.dispatches.get(source.delivery) if source else None
            if d is not None and (d.recipient, d.version) == (e.actor, source.version):
                matched.setdefault(source.delivery, e.step)
            else:
                unpaired += 1
    proxy = peer_read_proxy(office.observations)
    if proxy.first_alert != first:
        raise ValueError("per-read proxy replay disagrees with the original first alert")
    return proxy, matched, fires, unpaired


def evaluate_office(office: DispatchOffice, arrivals: list[Arrived]) -> tuple[dict, list[dict]]:
    """Return case and delivery rows, retaining the office's complete action journal only for scoring."""
    dispatch, use, warning, commit = _decisions(arrivals, office.workflow.authority)
    proxy, matched, fires, unpaired = _peer_matches(office)
    rows = []
    for key, d in office.dispatches.items():
        exact = office.first_exact_use.get(key)
        effect = exact if d.authorized is False else None
        earlier = dispatch.get(key, UNKNOWN)
        later = use.get(key, UNKNOWN)
        rows.append({
            "delivery": key, "dispatched_step": d.step, "recipient": d.recipient, "document": d.version.document,
            "version": d.version.digest, "authorized": {True: "yes", False: "no", None: "unknown"}[d.authorized],
            "exact_use_step": exact, "effect_step": effect,
            "policy_effect": ("yes" if effect is not None else
                              ("unknown" if exact is not None and d.authorized is None else "no")),
            "dispatch": earlier.status, "dispatch_step": earlier.first_alert,
            "commit": later.status, "commit_step": later.first_alert,
            "proxy": "alert" if key in matched else "clear", "proxy_step": matched.get(key),
        })
    effects = [r for r in rows if r["effect_step"] is not None]
    first_effect = min(effects, key=lambda r: r["effect_step"]) if effects else {}
    case = {
        "deliveries": len(rows), "exact_uses": sum(r["exact_use_step"] is not None for r in rows),
        "unapproved_uses": len(effects), "effect_step": first_effect.get("effect_step"),
        "policy_effect": "yes" if effects else ("unknown" if any(r["policy_effect"] == "unknown" for r in rows)
                                               else "no"),
        "effect_delivery": first_effect.get("delivery"), "proxy_trigger_reads": fires, "unpaired_proxy_reads": unpaired,
        "dispatch": warning.status, "dispatch_step": warning.first_alert,
        "commit": commit.status, "commit_step": commit.first_alert,
        "proxy": proxy.status, "proxy_step": proxy.first_alert,
    }
    for method in METHODS:
        case[f"{method}_matched_step"] = first_effect.get(f"{method}_step")
    return case, rows


def delivery_results(office: DispatchOffice, arrivals: list[Arrived]) -> list[dict]:
    return evaluate_office(office, arrivals)[1]


def case_results(office: DispatchOffice, arrivals: list[Arrived]) -> dict:
    return evaluate_office(office, arrivals)[0]


def _results(cases: list[dict], deliveries: list[dict]) -> dict:
    methods = {}
    for method in METHODS:
        matched = f"{method}_matched"
        methods[method] = {
            "delivery_effect": _score(deliveries, method, "policy_effect"),
            "delivery_timing": _timing(deliveries, method),
            "matched_delivery_lead_steps": sorted(
                r["effect_step"] - r[f"{method}_step"] for r in deliveries
                if r["effect_step"] is not None and r[f"{method}_step"] is not None),
            "unused_delivery_alerts": sum(r["exact_use_step"] is None and r[method] == "alert" for r in deliveries),
            "case_effect_any_alert": _score(cases, method, "policy_effect"),
            "case_intent_any_alert": _score(cases, method, "intended"),
            "first_case_effect_matched_timing": _timing(cases, matched),
            "case_positive_with_only_unmatched_warnings": sum(
                r["policy_effect"] == "yes" and r[method] == "alert" and r[f"{matched}_step"] is None
                for r in cases),
        }
    return {"cases": len(cases), "cases_without_dispatch": sum(not r["deliveries"] for r in cases),
            "deliveries": len(deliveries), "unused_deliveries": sum(r["exact_use_step"] is None for r in deliveries),
            "methods": methods}


def _write_report(directory: Path, cases: list[dict], deliveries: list[dict], summary: dict) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=directory) as tmp:
        staging = Path(tmp)
        tables = [("cases.csv", cases), ("deliveries.csv", deliveries)]
        for name, rows in tables:
            with (staging / name).open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, rows[0].keys(), lineterminator="\n")
                writer.writeheader()
                writer.writerows(rows)
        (staging / "summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n",
                                               encoding="utf-8", newline="\n")
        outputs = [staging / name for name in ("cases.csv", "deliveries.csv", "summary.json")]
        missing = [source for source in outputs if not _already_published(directory / source.name, source)]
        for source in missing:
            target = directory / source.name
            try:
                target.hardlink_to(source)
            except FileExistsError:
                if not _already_published(target, source):
                    raise


def run_dispatch_study(benchmark_dir: Path, *, output_dir: Path | None = None) -> dict:
    root = Path(benchmark_dir)
    protocol = (root.parent / "recipient-dispatch-contract/protocol.json").read_text(encoding="utf-8")
    if hashlib.sha256(protocol.encode()).hexdigest() != PROTOCOL_SHA256:
        raise ValueError("the dispatch protocol differs from its frozen hash")
    fixtures, _, frozen = _read_frozen(root)
    if frozen != json.loads(protocol)["upstream_sha256"]:
        raise ValueError("the dispatch contract requires the original released partition")
    cases, deliveries = [], []
    for split in ("development", "confirmation"):
        for fixture in fixtures[split]:
            workflow = fixture["workflow"]
            office = DispatchOffice(Workflow(**fixtures["workflows"][workflow]))
            office.execute(fixture["steps"])
            arrivals = office.deliver_audit(fixture.get("drop", []), fixture.get("delay_to", {}))
            case, copies = evaluate_office(office, arrivals)
            original = recipient_use(arrivals, office.workflow.authority)
            if (case["commit"], case["commit_step"]) != (original.status, original.first_alert):
                raise ValueError("delivery-level commit replay differs from the released complete-use rule")
            identity = {"case_id": fixture["id"], "split": split, "workflow": workflow}
            cases.append({**identity, **case})
            deliveries.extend({**identity, **r} for r in copies)
    with (root / "labels.csv").open(encoding="utf-8", newline="") as stream:
        labels = {r["case_id"]: r for r in csv.DictReader(stream)}
    if set(labels) != {r["case_id"] for r in cases}:
        raise ValueError("the frozen adjudications and replayed cases differ")
    for case in cases:
        label = labels[case["case_id"]]
        first = int(label["effect_step"]) if label["effect_step"] else None
        if (case["policy_effect"], case["effect_step"]) != (label["policy_effect"], first):
            raise ValueError(f"executed effect differs from the released adjudication for {case['case_id']}")
        case.update(intent=label["intent"], intended="yes" if label["intent"] == "coordinated" else "no")
    summary = {"protocol_sha256": PROTOCOL_SHA256, "upstream_sha256": frozen, "splits": {}}
    for split in ("development", "confirmation"):
        selected = [r for r in cases if r["split"] == split]
        copies = [r for r in deliveries if r["split"] == split]
        workflows = {k: _results([r for r in selected if r["workflow"] == k],
                                 [r for r in copies if r["workflow"] == k])
                     for k in sorted({r["workflow"] for r in selected})}
        summary["splits"][split] = {**_results(selected, copies), "workflows": workflows}
    if output_dir is not None:
        _write_report(Path(output_dir), cases, deliveries, summary)
    return summary
