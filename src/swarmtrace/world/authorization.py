"""Attribute successful simulated reads using the gateway's live authorization state."""

from collections import defaultdict

from swarmtrace.trace.authorization import Basis, ReadAudit, ReadDecision, ReadGrant

from . import tools
from .model import ToolResult, World


class ReadGateway:
    def __init__(self, world: World, run_id: str, grants: tuple[ReadGrant, ...]) -> None:
        # Check grant ids before accepting any reads, including a run with an empty registry.
        ReadAudit(run_id, grants, ())
        self._world = world
        self._run_id = run_id
        self._grants = grants
        self._by_actor_host: dict[tuple[str, str], list[ReadGrant]] = defaultdict(list)
        for grant in grants:
            if (grant.sender not in world.permissions or grant.receiver not in world.permissions
                    or grant.host not in world.hosts or not set(grant.credentials) <= world.credentials.keys()
                    or any(f not in world.files or world.files[f].host != grant.host for f in grant.files)):
                raise ValueError("grant must reference known actors, credentials and files on its host")
            self._by_actor_host[grant.receiver, grant.host].append(grant)
        self._decisions: list[ReadDecision] = []

    @property
    def audit(self) -> ReadAudit:
        return ReadAudit(self._run_id, self._grants, tuple(self._decisions))

    def _basis(self, agent: str, host: str, selected: str | None) -> tuple[Basis, str | None]:
        world = self._world
        permission = world.permissions[agent]
        has_session = (agent, host) in world.sessions
        active = {
            token for actor, target, token in world.successful_logins
            if actor == agent and target == host and token not in world.revoked_credentials
        } if has_session else set()
        candidates = [g for g in self._by_actor_host.get((agent, host), ())
                      if not active.isdisjoint(g.credentials)]
        if selected is not None:
            if any(g.grant_id == selected for g in candidates):
                return "grant", selected
            return "unknown", None

        native = {token for token in active & permission.credentials
                  if world.credentials[token].host == host}
        ordinary = world.hosts[host].zone in permission.zones or bool(native)
        covered = native.union(*(g.credentials for g in candidates))
        if (has_session and not active) or active - covered:
            # A session exists without any attributable credential, or a live credential
            # has no corresponding ordinary permission or approved assignment.
            return "unknown", None
        if ordinary and not candidates:
            return "ordinary", None
        if len(candidates) == 1 and not ordinary:
            return "grant", candidates[0].grant_id
        return "unknown", None

    def read(self, seq: int, agent: str, file: str, selected: str | None) -> ToolResult:
        def authorized(host: str) -> None:
            # The host permission check has passed and the file exists. Capture the basis
            # before the read updates receipts or delivers any file contents.
            basis, grant_id = self._basis(agent, host, selected)
            self._decisions.append(ReadDecision(seq, agent, file, host, basis, grant_id))

        return tools.read(self._world, agent, file, on_authorized=authorized)
