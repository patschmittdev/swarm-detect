"""A local document office that issues observations from actual, benign editing operations."""

import hashlib
from dataclasses import dataclass


@dataclass(frozen=True)
class Version:
    document: str
    digest: str


@dataclass(frozen=True)
class Workflow:
    authority: str
    author: str
    assigned: str
    alternate: str
    document: str
    text: str

    def __post_init__(self) -> None:
        actors = {self.authority, self.author, self.assigned, self.alternate}
        if len(actors) != 4 or not all(actors) or not self.document or not self.text:
            raise ValueError("each workflow needs distinct people and a named source document")

    def worker(self, role: str) -> str:
        if role not in ("assigned", "alternate"):
            raise ValueError(f"unknown reviewer role {role}")
        return getattr(self, role)


@dataclass(frozen=True)
class Observation:
    step: int
    actor: str
    tool: str
    target: str
    success: bool = True


@dataclass(frozen=True)
class Receipt:
    step: int
    key: str


@dataclass(frozen=True)
class Approval(Receipt):
    authority: str
    ticket: str
    version: Version
    recipients: frozenset[str]


@dataclass(frozen=True)
class Delivery(Receipt):
    ticket: str
    sender: str
    recipient: str
    version: Version
    approval: str | None


@dataclass(frozen=True)
class Input:
    version: Version
    delivery: str | None


@dataclass(frozen=True)
class Commit(Receipt):
    ticket: str
    recipient: str
    source: Input | None
    output: Version


@dataclass(frozen=True)
class Seal(Receipt):
    receipts: frozenset[str]


@dataclass(frozen=True)
class Arrived:
    at: int
    record: Receipt


class DocumentOffice:
    """An isolated ticket, an immutable document store, a policy register and an editor."""

    def __init__(self, workflow: Workflow):
        self.workflow = workflow
        self.ticket = f"{workflow.document}/review"
        self.observations: list[Observation] = []
        self.receipts: list[Receipt] = []
        self.blobs: dict[Version, bytes] = {}
        self.submissions: dict[int, Version] = {}
        self._policies: dict[Version, Approval] = {}
        self._inboxes: dict[str, Delivery] = {}
        self._opened: dict[str, Input] = {}
        self.current = self._store(workflow.document, workflow.text.encode())
        self.observations.append(Observation(0, workflow.author, "write", workflow.document))

    def _store(self, document: str, content: bytes) -> Version:
        version = Version(document, hashlib.sha256(content).hexdigest())
        self.blobs[version] = content
        return version

    def _approve(self, step: int, roles: list[str]) -> None:
        grant = Approval(step, f"approval:{step}", self.workflow.authority, self.ticket,
                         self.current, frozenset(self.workflow.worker(role) for role in roles))
        self._policies[self.current] = grant
        self.receipts.append(grant)

    def _send(self, step: int, actor: str, *, attach: bool) -> None:
        author = self.workflow.author
        self.observations.extend([Observation(step, author, "send", actor),
                                  Observation(step, actor, "recv", author)])
        if attach:
            policy = self._policies.get(self.current)
            delivery = Delivery(step, f"delivery:{step}", self.ticket, author, actor, self.current,
                                policy.key if policy else None)
            self._inboxes[actor] = delivery
            self.receipts.append(delivery)

    def _open(self, step: int, actor: str, route: str) -> None:
        if route not in {"pinned", "current", "independent"}:
            raise ValueError(f"unknown document opening route {route}")
        delivery = self._inboxes.get(actor) if route != "independent" else None
        success = bool(delivery) or route == "independent"
        self.observations.append(Observation(step, actor, "read", self.workflow.document, success))
        if success:
            version = delivery.version if route == "pinned" else self.current
            self._opened[actor] = Input(version, delivery.key if delivery else None)

    def _submit(self, step: int, actor: str, mode: str) -> None:
        if mode not in {"opened", "fresh"}:
            raise ValueError(f"unknown document submission mode {mode}")
        source = self._opened[actor] if mode == "opened" else None
        # The precise input used by the write transaction supplies the receipt.
        # Merely opening an attachment does not make it a dependency of an output.
        text = self.blobs[source.version] if source else b"An independent draft."
        output = self._store(f"{actor}/review", b"Review by " + actor.encode() + b"\n" + text)
        self.submissions[step] = output
        self.observations.append(Observation(step, actor, "write", output.document))
        self.receipts.append(Commit(step, f"commit:{step}", self.ticket, actor, source, output))

    def _execute_instruction(self, step: int, instruction: str) -> None:
        match instruction.split():
            case ["approve", *roles] if roles:
                self._approve(step, roles)
            case ["revise"]:
                revised = self.blobs[self.current] + b"\nRevision."
                self.current = self._store(self.workflow.document, revised)
                self.observations.append(Observation(step, self.workflow.author, "write",
                                                     self.workflow.document))
            case ["send" | "discuss" as action, role]:
                self._send(step, self.workflow.worker(role), attach=action == "send")
            case ["open", role, route]:
                self._open(step, self.workflow.worker(role), route)
            case ["submit", role, mode]:
                self._submit(step, self.workflow.worker(role), mode)
            case _:
                raise ValueError(f"unknown document office operation {instruction!r}")

    def execute(self, instructions: list[str]) -> None:
        if self.receipts or len(self.observations) != 1:
            raise ValueError("create a fresh document office per case")
        for step, instruction in enumerate(instructions, start=1):
            self._execute_instruction(step, instruction)
        end = len(instructions) + 1
        keys = frozenset(record.key for record in self.receipts)
        self.receipts.append(Seal(end, f"seal:{end}", keys))

    def deliver_audit(self, dropped: list[str], delayed_until: dict[str, int]) -> list[Arrived]:
        """Simulate transport loss or delay after the gateway has executed the actual operations."""
        keys = {record.key for record in self.receipts}
        if not (set(dropped) | delayed_until.keys()) <= keys or set(dropped) & delayed_until.keys():
            raise ValueError("unknown or conflicting receipt transport change")
        arrivals = []
        for record in self.receipts:
            if record.key in dropped:
                continue
            at = delayed_until.get(record.key, record.step)
            if type(at) is not int or at < record.step:
                raise ValueError("a receipt cannot arrive before it was issued")
            arrivals.append(Arrived(at, record))
        return sorted(arrivals, key=lambda arrival: arrival.at)
