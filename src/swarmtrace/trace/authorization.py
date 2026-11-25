"""Versioned gateway observations for successful reads, independent of actor labels."""

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from .io import _serialize

Basis = Literal["grant", "ordinary", "unknown"]


def _identifier(value: object) -> bool:
    return isinstance(value, str) and bool(value)


@dataclass(frozen=True)
class ReadGrant:
    """A trusted assignment, its approved files, and the credentials usable for it."""

    grant_id: str
    sender: str
    receiver: str
    host: str
    files: tuple[str, ...]
    credentials: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not all(_identifier(x) for x in (self.grant_id, self.sender, self.receiver, self.host)):
            raise ValueError("grant identifiers must be nonempty strings")
        for identifiers in (self.files, self.credentials):
            if (not isinstance(identifiers, tuple) or not all(map(_identifier, identifiers))
                    or len(identifiers) != len(set(identifiers))):
                raise ValueError("grant files and credentials must be tuples of distinct identifiers")


@dataclass(frozen=True)
class ReadDecision:
    """One successful read. Its unique event key is (run_id, seq) within the audit."""

    seq: int
    agent: str
    file: str
    host: str
    basis: Basis
    grant_id: str | None = None

    def __post_init__(self) -> None:
        if type(self.seq) is not int or self.seq < 0:
            raise ValueError("read decision seq must be a non-negative integer")
        if not all(_identifier(x) for x in (self.agent, self.file, self.host)):
            raise ValueError("read decision identifiers must be nonempty strings")
        if self.basis not in ("grant", "ordinary", "unknown"):
            raise ValueError("unknown read authorization basis")
        if self.basis == "grant" and not _identifier(self.grant_id):
            raise ValueError("a delegated read needs a grant id")
        if self.basis != "grant" and self.grant_id is not None:
            raise ValueError("only a delegated read can name a grant")


@dataclass(frozen=True)
class ReadAudit:
    run_id: str
    grants: tuple[ReadGrant, ...]
    decisions: tuple[ReadDecision, ...]

    def __post_init__(self) -> None:
        if not _identifier(self.run_id):
            raise ValueError("read audit needs a run id")
        if not isinstance(self.grants, tuple) or not all(isinstance(g, ReadGrant) for g in self.grants):
            raise ValueError("read audit grants must be a tuple of ReadGrant")
        if (not isinstance(self.decisions, tuple)
                or not all(isinstance(d, ReadDecision) for d in self.decisions)):
            raise ValueError("read audit decisions must be a tuple of ReadDecision")
        by_id = {grant.grant_id: grant for grant in self.grants}
        if len(by_id) != len(self.grants):
            raise ValueError("duplicate grant id in read audit")
        previous = -1
        for decision in self.decisions:
            if decision.seq <= previous:
                raise ValueError("read decisions must have strictly increasing event sequences")
            previous = decision.seq
            if decision.basis == "grant":
                grant = by_id.get(decision.grant_id)
                if grant is None or (grant.receiver, grant.host) != (decision.agent, decision.host):
                    raise ValueError("read decision must reference a grant for its actor and host")


def _fields(row: object, keys: tuple[str, ...]) -> dict:
    if not isinstance(row, dict) or row.keys() != set(keys):
        raise ValueError(f"read authorization record must have fields {', '.join(keys)}")
    return row


def _array(value: object) -> list:
    if not isinstance(value, list):
        raise ValueError("read authorization arrays must be JSON lists")
    return value


def read_authorization(path: str | Path) -> ReadAudit:
    row = _fields(json.loads(Path(path).read_text(encoding="utf-8")),
                  ("schema_version", "run_id", "grants", "decisions"))
    if type(row["schema_version"]) is not int or row["schema_version"] != 1:
        raise ValueError("unsupported read authorization schema version")
    grants = []
    for item in _array(row["grants"]):
        grant = _fields(item, ("grant_id", "sender", "receiver", "host", "files", "credentials"))
        grants.append(ReadGrant(grant["grant_id"], grant["sender"], grant["receiver"], grant["host"],
                                tuple(_array(grant["files"])), tuple(_array(grant["credentials"]))))
    decisions = tuple(
        ReadDecision(**_fields(item, ("seq", "agent", "file", "host", "basis", "grant_id")))
        for item in _array(row["decisions"])
    )
    return ReadAudit(row["run_id"], tuple(grants), decisions)


def write_authorization(path: str | Path, audit: ReadAudit) -> None:
    Path(path).write_text(_serialize({"schema_version": 1, **asdict(audit)}),
                          encoding="utf-8", newline="\n")
