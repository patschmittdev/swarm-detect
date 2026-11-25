import re
from collections import deque
from dataclasses import dataclass, field

import numpy as np


@dataclass(frozen=True)
class Host:
    id: str
    zone: str
    services: tuple[str, ...]


@dataclass
class File:
    """A file location; None content reserves the location for a future write."""

    id: str
    host: str
    path: str
    content: str | None = None


@dataclass(frozen=True)
class Credential:
    id: str
    host: str


@dataclass(frozen=True)
class Permission:
    zones: frozenset[str] = frozenset()
    credentials: frozenset[str] = frozenset()


@dataclass(frozen=True)
class ToolResult:
    status: str
    size: int
    content: str | None = None
    items: tuple[str, ...] = ()


@dataclass
class World:
    hosts: dict[str, Host]
    files: dict[str, File]
    credentials: dict[str, Credential]
    zones: frozenset[str]
    permissions: dict[str, Permission] = field(default_factory=dict)
    sessions: set[tuple[str, str]] = field(default_factory=set)
    messages: dict[tuple[str, str], deque[str]] = field(default_factory=dict)
    quarantined: set[str] = field(default_factory=set)
    channel_cut: bool = False
    received_credentials: dict[str, set[str]] = field(default_factory=dict)
    credential_grants: set[tuple[str, str]] = field(default_factory=set)
    scheduled_grants: dict[int, list[tuple[str, str, str, str | None]]] = field(default_factory=dict)
    successful_logins: set[tuple[str, str, str]] = field(default_factory=set)
    file_credentials: dict[str, tuple[str, ...]] = field(default_factory=dict)
    message_credentials: dict[tuple[str, str], deque[tuple[str, ...]]] = field(default_factory=dict)
    file_writers: dict[str, str] = field(default_factory=dict)
    receipts: set[tuple[str, str]] = field(default_factory=set)
    file_reads: set[tuple[str, str]] = field(default_factory=set)
    file_writes: set[tuple[str, str]] = field(default_factory=set)
    revoked_credentials: set[str] = field(default_factory=set)

    def add_agent(
        self, agent: str, zones: tuple[str, ...] = (), credentials: tuple[str, ...] = (),
    ) -> None:
        if agent in self.permissions:
            raise ValueError(f"agent already registered: {agent}")
        if not set(zones) <= self.zones:
            raise ValueError("zones must exist in the world")
        if not set(credentials) <= self.credentials.keys():
            raise ValueError("credentials must exist in the world")
        self.permissions[agent] = Permission(frozenset(zones), frozenset(credentials))

    def holds_credential(self, agent: str, credential: str) -> bool:
        permission = self.permissions.get(agent)
        return permission is not None and (
            credential in permission.credentials
            or credential in self.received_credentials.get(agent, ())
        )

    def revoke(self, credential: str) -> None:
        """End sessions with no remaining credential used successfully on that host."""
        if credential not in self.credentials:
            raise ValueError("revocation requires a known credential")
        self.revoked_credentials.add(credential)
        affected = {(agent, host) for agent, host, used in self.successful_logins
                    if used == credential}
        valid = {(agent, host) for agent, host, used in self.successful_logins
                 if used not in self.revoked_credentials}
        self.sessions.difference_update(affected - valid)

    def credentials_in_content(self, agent: str, content: str) -> tuple[str, ...]:
        """Snapshot transferable tokens when content is published, not when consumed."""
        return tuple(sorted({token for token in re.findall(r"\bc-[0-9a-f]{8}\b", content)
                             if self.holds_credential(agent, token)}))

    def handover(self, sender: str, recipient: str, credential: str) -> None:
        """Transfer possession without changing the credential's owner or validity."""
        if recipient not in self.permissions or not self.holds_credential(sender, credential):
            raise ValueError("handover requires a known recipient and a credential held by sender")
        self.received_credentials.setdefault(recipient, set()).add(credential)

    def _validate_grant(self, agent: str, host: str, credential: str) -> None:
        if (agent not in self.permissions or host not in self.hosts
                or credential not in self.permissions[agent].credentials):
            raise ValueError("grant requires a known host and the agent's own credential")

    def grant_access(self, agent: str, host: str, credential: str) -> None:
        """Administratively authorize an owned credential for an additional host."""
        self._validate_grant(agent, host, credential)
        self.credential_grants.add((credential, host))

    def schedule_grant(
        self, tick: int, agent: str, host: str, credential: str,
        *, after_receipt_from: str | None = None,
    ) -> None:
        if type(tick) is not int or tick < 0:
            raise ValueError("grant tick must be a non-negative integer")
        self._validate_grant(agent, host, credential)
        if after_receipt_from is not None and after_receipt_from not in self.permissions:
            raise ValueError("receipt prerequisite requires a known sender")
        self.scheduled_grants.setdefault(tick, []).append(
            (agent, host, credential, after_receipt_from)
        )

    def apply_grants(self, tick: int) -> None:
        for due in sorted(due for due in self.scheduled_grants if due <= tick):
            waiting = []
            for agent, host, credential, sender in self.scheduled_grants.pop(due):
                if sender is not None and (agent, sender) not in self.receipts:
                    waiting.append((agent, host, credential, sender))
                else:
                    self.grant_access(agent, host, credential)
            if waiting:
                self.scheduled_grants[due] = waiting

    def allows(self, agent: str, host: str) -> bool:
        permission = self.permissions.get(agent)
        return (
            permission is not None
            and agent not in self.quarantined
            and host in self.hosts
            and (self.hosts[host].zone in permission.zones or (agent, host) in self.sessions)
        )


def generate_world(seed: int, n_hosts: int) -> World:
    """Generate one zone and credential per host, with source and output file locations."""
    if type(seed) is not int or seed < 0:
        raise ValueError("seed must be a non-negative integer")
    if type(n_hosts) is not int or n_hosts < 1:
        raise ValueError("n_hosts must be a positive integer")
    id_seed, service_seed = np.random.SeedSequence(seed).spawn(2)
    id_rng = np.random.default_rng(id_seed)
    service_rng = np.random.default_rng(service_seed)
    used: set[str] = set()

    def identifier(prefix: str) -> str:
        while True:
            candidate = prefix + id_rng.bytes(4).hex()
            if candidate not in used:
                used.add(candidate)
                return candidate

    hosts: dict[str, Host] = {}
    files: dict[str, File] = {}
    credentials: dict[str, Credential] = {}
    services = ("files", "jobs", "metrics")
    for index in range(n_hosts):
        host_id, zone = identifier("h-"), identifier("z-")
        count = int(service_rng.integers(1, len(services) + 1))
        selected = tuple(sorted(
            services[int(i)] for i in service_rng.permutation(len(services))[:count]
        ))
        hosts[host_id] = Host(host_id, zone, selected)
        for path, content in (("/data/state.txt", f"host {index}"), ("/data/output.txt", None)):
            file_id = identifier("f-")
            files[file_id] = File(file_id, host_id, path, content)
        credential_id = identifier("c-")
        credentials[credential_id] = Credential(credential_id, host_id)
    return World(hosts, files, credentials, frozenset(host.zone for host in hosts.values()))
