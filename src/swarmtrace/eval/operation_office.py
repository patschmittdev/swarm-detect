"""Execute benign document edits and record the authority in force inside the write transaction."""

import json
import sqlite3
from contextlib import closing, contextmanager
from copy import deepcopy
from dataclasses import dataclass

from swarmtrace.reproduce.public_tickets import Stage, digest, key

from .dispatch_baselines import GatewayDocumentOffice
from .recipient_lab import Commit, Version, Workflow

SPECIALISTS = ("finance_approval_specialist", "legal_approval_specialist", "procurement_approval_specialist")


class PolicyStore:
    """One isolated issuer and ticket. The live table is the evaluator's witness."""

    def __init__(self, db, authority, ticket):
        self.db, self.authority, self.ticket = db, authority, ticket
        db.execute("CREATE TABLE grants (worker, document, digest, mode, PRIMARY KEY(worker, document, digest))")
        db.execute("CREATE TABLE ledger (seq INTEGER PRIMARY KEY, step INTEGER, entry TEXT)")
        db.execute("CREATE TABLE edits (session, call_id, worker, content BLOB, PRIMARY KEY(session, call_id))")

    def permission(self, worker, version):
        row = self.db.execute("SELECT mode FROM grants WHERE worker=? AND document=? AND digest=?",
                              (worker, version.document, version.digest)).fetchone()
        return row[0] if row else None

    def record(self, step, kind, worker, version, **binding):
        entry = dict(authority=self.authority, ticket=self.ticket, worker=worker, document=version.document,
                     digest=version.digest, kind=kind, **binding)
        return self.db.execute("INSERT INTO ledger(step,entry) VALUES (?,?)",
                               (step, json.dumps(entry))).lastrowid

    def change(self, step, kind, worker, version):
        with self.db:
            self.db.execute("DELETE FROM grants WHERE worker=? AND document=? AND digest=?",
                            (worker, version.document, version.digest))
            if kind in ("allow", "once"):
                self.db.execute("INSERT INTO grants VALUES (?,?,?,?)", (worker, version.document, version.digest, kind))
            elif kind != "revoke":
                raise ValueError("unknown policy transition")
            self.record(step, kind, worker, version)

    def consume(self, step, worker, version, session, call_id, delivery):
        # The caller commits this decrement and its audit record in the same transaction.
        self.db.execute("DELETE FROM grants WHERE worker=? AND document=? AND digest=? AND mode='once'",
                        (worker, version.document, version.digest))
        return self.record(step, "use", worker, version, session=session, call_id=call_id, delivery=delivery)

    @contextmanager
    def operation(self):
        with self.db:
            # Acquire the writer lock before observing whether a one-use permission remains.
            self.db.execute("BEGIN IMMEDIATE")
            yield

    def journal(self):
        return [(step, dict(json.loads(body), seq=seq)) for seq, step, body in
                self.db.execute("SELECT seq,step,entry FROM ledger ORDER BY seq")]


@dataclass
class OfficeRun:
    authority: str
    ticket: str
    journal: list
    witnesses: list
    outcomes: list
    end_step: int


class _OperationOffice(GatewayDocumentOffice):
    def __init__(self, stage: Stage, base_id: str, role: str, db):
        other = next((s for s in SPECIALISTS if s not in stage.recipients and s != stage.author), "records_clerk")
        workflow = Workflow("ticket_authority", stage.author, stage.recipients[0], other, stage.document, stage.text)
        super().__init__(workflow, run_id=key("operation-office", base_id)[:16])
        self.role = {"named": "assigned", "other": "alternate"}[role]
        self.person = workflow.worker(self.role)
        self.worker = self._actors[self.person]
        self.store = PolicyStore(db, workflow.authority, self.ticket)
        for name in stage.recipients:
            # Keep the complete recipient list, including specialists who never enter the office.
            self.store.change(0, "allow", self._actors.get(name, f"ticket-role/{name}"), self.current)
        self.named = self.person in stage.recipients
        self.dispatch_permissions = {}
        self.witnesses, self.outcomes = [], []

    def _instruction(self, text):
        self._execute_instruction(self.step + 1, text)

    def _edit(self, mode):
        if mode != "fresh":
            route = {"use": "pinned", "independent": "independent", "current": "current"}[mode]
            self._instruction(f"open {self.role} {route}")
        # This office runs in one process. Publish its native editor state only after
        # both the exact output bytes and grant consumption have committed to SQLite.
        staged = deepcopy(self, {id(self.store): self.store})
        staged._commit_edit(mode)
        self.__dict__ = staged.__dict__

    def _commit_edit(self, mode):
        delivery = self._inboxes[self.person]
        request_id = f"write-{self._recorder.next_seq}"
        with self.store.operation():
            permitted = self.store.permission(self.worker, delivery.version) is not None
            self._instruction(f"submit {self.role} {'fresh' if mode == 'fresh' else 'opened'}")
            commit = self.receipts[-1]
            result = self._recorder.events[-1]
            if (not isinstance(commit, Commit) or result.tool != "write" or result.result["status"] != "ok"
                    or result.target != self._document_files[commit.output.document]):
                raise ValueError("expected a successful native write for this editor commit")
            payload = result.content.encode()
            header = f"Review by {commit.recipient}\n".encode()
            if not payload.startswith(header) or digest(payload) != commit.output.digest:
                raise ValueError("gateway output differs from the committed review")
            source = commit.source
            observed_hash = digest(payload[len(header):]) if source is not None else None
            if source is not None and observed_hash != source.version.digest:
                raise ValueError("written bytes differ from the recorded input version")
            result_id = f"write-{result.seq}"
            receipt_seq = None
            if source is not None and source.delivery is not None:
                receipt_seq = self.store.consume(self.step, result.agent, source.version, result.run_id,
                                                 result_id, source.delivery)
            self.store.db.execute("INSERT INTO edits VALUES (?,?,?,?)",
                                  (result.run_id, result_id, result.agent, payload))
            exact = source is not None and (source.delivery, source.version) == (delivery.key, delivery.version)
            witness = dict(operation=commit.key, ticket=delivery.ticket, session=self.run_id, worker=self.worker,
                           call_id=request_id, delivery=delivery.key, document=delivery.version.document,
                           digest=delivery.version.digest, result_ticket=commit.ticket, result_session=result.run_id,
                           result_call_id=result_id, result_worker=result.agent, receipt_seq=receipt_seq,
                           source_delivery=source.delivery if source else None,
                           source_document=source.version.document if source else None, source_digest=observed_hash)
            self.witnesses.append(witness)
            self.outcomes.append(dict(step=self.step, effect=exact and not permitted,
                                      ticket_allowed=self.named, dispatch_allowed=self.dispatch_permissions[delivery.key]))

    def run(self, steps):
        for op in steps:
            if op in ("allow", "once", "revoke"):
                self.step += 1
                self.store.change(self.step, op, self.worker, self.current)
            elif op == "send":
                self._instruction(f"send {self.role}")
                handle = self._inboxes[self.person].key
                self.dispatch_permissions[handle] = self.store.permission(self.worker, self.current) is not None
            elif op == "revise":
                self._instruction("revise")
            else:
                self._edit(op)
        for obs, fact in zip(self.witnesses, self.outcomes, strict=True):
            version = Version(obs["document"], obs["digest"])
            fact["final_snapshot_allowed"] = self.store.permission(obs["worker"], version) == "allow"
        return OfficeRun(self.workflow.authority, self.ticket, self.store.journal(),
                         self.witnesses, self.outcomes, self.step)


def execute_operation_case(stage: Stage, base_id: str, profile: dict) -> OfficeRun:
    with closing(sqlite3.connect(":memory:")) as db:
        office = _OperationOffice(stage, base_id, profile["worker"], db)
        result = office.run(profile["steps"])
    if [row["effect"] for row in result.outcomes] != profile["effects"]:
        raise ValueError(f"executed effects differ from the frozen expectations for {profile['name']}")
    return result
