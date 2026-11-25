from collections import deque
from collections.abc import Callable

from .model import ToolResult, World


class SimulatedToolError(Exception):
    """An expected in-world tool failure, rather than a simulator defect."""


def _host_status(world: World, agent: str, target: str) -> str:
    if agent not in world.permissions or agent in world.quarantined:
        return "denied"
    if target not in world.hosts:
        return "not_found"
    return "ok" if world.allows(agent, target) else "denied"


def _file_status(world: World, agent: str, target: str) -> str:
    if agent not in world.permissions or agent in world.quarantined:
        return "denied"
    file = world.files.get(target)
    return "not_found" if file is None else _host_status(world, agent, file.host)


def _message_status(world: World, agent: str, target: str) -> str:
    if agent not in world.permissions or agent in world.quarantined or world.channel_cut:
        return "denied"
    if target not in world.permissions:
        return "not_found"
    return "ok"


def scan(world: World, agent: str, target: str) -> ToolResult:
    status = _host_status(world, agent, target)
    if status != "ok":
        return ToolResult(status, 0)
    services = world.hosts[target].services
    return ToolResult("ok", len(services), items=services)


def login(world: World, agent: str, target: str, credential: str) -> ToolResult:
    if agent not in world.permissions or agent in world.quarantined:
        return ToolResult("denied", 0)
    if target not in world.hosts or credential not in world.credentials:
        return ToolResult("not_found", 0)
    if credential in world.revoked_credentials:
        return ToolResult("denied", 0)
    valid_host = (world.credentials[credential].host == target
                  or (credential, target) in world.credential_grants)
    if not world.holds_credential(agent, credential) or not valid_host:
        return ToolResult("denied", 0)
    world.sessions.add((agent, target))
    world.successful_logins.add((agent, target, credential))
    return ToolResult("ok", 0)


def list(world: World, agent: str, target: str, prefix: str) -> ToolResult:
    status = _host_status(world, agent, target)
    if status != "ok":
        return ToolResult(status, 0)
    files = tuple(sorted(
        file.id for file in world.files.values()
        if file.host == target and file.path.startswith(prefix) and file.content is not None
    ))
    return ToolResult("ok", len(files), items=files)


def read(
    world: World, agent: str, target: str, *, on_authorized: Callable[[str], None] | None = None,
) -> ToolResult:
    status = _file_status(world, agent, target)
    if status != "ok":
        return ToolResult(status, 0)
    content = world.files[target].content
    if content is None:
        return ToolResult("not_found", 0)
    size = len(content.encode("utf-8"))
    if on_authorized is not None:
        on_authorized(world.files[target].host)
    world.file_reads.add((agent, target))
    world.received_credentials.setdefault(agent, set()).update(
        world.file_credentials.get(target, ())
    )
    writer = world.file_writers.get(target)
    if writer is not None and writer != agent:
        world.receipts.add((agent, writer))
    return ToolResult("ok", size, content)


def write(world: World, agent: str, target: str, content: str) -> ToolResult:
    """Create content at a reserved file location, or overwrite an existing file."""
    status = _file_status(world, agent, target)
    if status != "ok":
        return ToolResult(status, 0)
    world.files[target].content = content
    world.file_writers[target] = agent
    world.file_writes.add((agent, target))
    world.file_credentials[target] = world.credentials_in_content(agent, content)
    return ToolResult("ok", len(content.encode("utf-8")), content)


def send(world: World, agent: str, target: str, content: str) -> ToolResult:
    status = _message_status(world, agent, target)
    if status != "ok":
        return ToolResult(status, 0)
    world.messages.setdefault((target, agent), deque()).append(content)
    world.message_credentials.setdefault((target, agent), deque()).append(
        world.credentials_in_content(agent, content)
    )
    return ToolResult("ok", len(content.encode("utf-8")), content)


def recv(world: World, agent: str, target: str) -> ToolResult:
    status = _message_status(world, agent, target)
    if status != "ok":
        return ToolResult(status, 0)
    queue = world.messages.get((agent, target))
    if not queue:
        return ToolResult("not_found", 0)
    content = queue.popleft()
    credentials = world.message_credentials.get((agent, target))
    if credentials:
        world.received_credentials.setdefault(agent, set()).update(credentials.popleft())
    if target != agent:
        world.receipts.add((agent, target))
    return ToolResult("ok", len(content.encode("utf-8")), content)
