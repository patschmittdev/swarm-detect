import re

import pytest

from swarmtrace.trace.schema import TOOLS
from swarmtrace.world import File, generate_world, tools

A = "a-00000001"
B = "a-00000002"


def test_seeded_world_has_hosts_services_files_credentials_and_zones() -> None:
    first = generate_world(42, 4)
    assert first == generate_world(42, 4)
    assert first != generate_world(43, 4)
    assert len(first.hosts) == 4
    assert first.zones
    for host in first.hosts.values():
        assert re.fullmatch(r"h-[0-9a-f]{8}", host.id)
        assert host.services
        assert host.zone in first.zones
        assert any(file.host == host.id for file in first.files.values())
        assert any(credential.host == host.id for credential in first.credentials.values())
    assert all(re.fullmatch(r"f-[0-9a-f]{8}", key) for key in first.files)
    assert all(re.fullmatch(r"c-[0-9a-f]{8}", key) for key in first.credentials)
    assert all(callable(getattr(tools, tool)) for tool in TOOLS)


def test_zone_permissions_and_credential_login_grant_host_session() -> None:
    world = generate_world(7, 2)
    host, other = tuple(world.hosts.values())
    credential = next(c for c in world.credentials.values() if c.host == other.id)
    world.add_agent(A, zones=(host.zone,), credentials=(credential.id,))
    world.add_agent(B)
    assert tools.scan(world, A, host.id).status == "ok"
    assert tools.scan(world, A, other.id).status == "denied"
    assert tools.login(world, B, other.id, credential.id).status == "denied"
    assert tools.login(world, A, host.id, credential.id).status == "denied"
    assert tools.login(world, A, other.id, credential.id).status == "ok"
    assert (A, other.id) in world.sessions
    assert tools.scan(world, A, other.id).items == other.services
    assert tools.scan(world, B, other.id).status == "denied"


def test_file_tools_create_overwrite_filter_and_measure_utf8_bytes() -> None:
    world = generate_world(8, 1)
    host = next(iter(world.hosts.values()))
    world.add_agent(A, zones=(host.zone,))
    world.add_agent(B)
    target = "f-ffffffff"
    world.files[target] = File(target, host.id, "/output/new.txt")
    assert tools.read(world, A, target).status == "not_found"
    assert tools.write(world, B, target, "secret").status == "denied"
    assert world.files[target].content is None
    result = tools.write(world, A, target, "caf\u00e9")
    assert (result.status, result.size, result.content) == ("ok", 5, "caf\u00e9")
    assert tools.list(world, A, host.id, "/output/").items == (target,)
    assert tools.list(world, A, host.id, "/absent/").items == ()
    assert tools.list(world, B, host.id, "").status == "denied"
    assert tools.read(world, B, target).status == "denied"
    assert tools.read(world, A, target).content == "caf\u00e9"
    assert tools.write(world, A, target, "").content == ""
    assert tools.read(world, A, target).content == ""
    assert tools.read(world, A, target).size == 0


def test_messages_are_consumed_fifo_by_recipient_and_sender() -> None:
    world = generate_world(9, 1)
    world.add_agent(A)
    world.add_agent(B)
    assert tools.send(world, A, B, "caf\u00e9").size == 5
    assert tools.send(world, A, B, "").content == ""
    assert tools.recv(world, A, B).status == "not_found"
    first = tools.recv(world, B, A)
    assert (first.status, first.size, first.content) == ("ok", 5, "caf\u00e9")
    assert tools.recv(world, B, A).content == ""
    assert tools.recv(world, B, A).status == "not_found"
    assert tools.send(world, A, "a-ffffffff", "x").status == "not_found"
    assert tools.send(world, "a-ffffffff", B, "x").status == "denied"


@pytest.mark.parametrize("tool", TOOLS)
def test_quarantine_denies_every_tool_without_content(tool: str) -> None:
    world = generate_world(10, 1)
    host = next(iter(world.hosts))
    file = next(iter(world.files))
    credential = next(iter(world.credentials))
    world.add_agent(A, zones=tuple(world.zones), credentials=(credential,))
    world.add_agent(B)
    world.quarantined.add(A)
    arguments = {
        "scan": (host,), "login": (host, credential), "list": (host, ""),
        "read": (file,), "write": (file, "x"), "send": (B, "x"), "recv": (B,),
    }
    result = getattr(tools, tool)(world, A, *arguments[tool])
    assert (result.status, result.size, result.content) == ("denied", 0, None)


def test_cut_channel_blocks_messages_but_preserves_host_access() -> None:
    world = generate_world(11, 1)
    world.add_agent(A, zones=tuple(world.zones))
    world.add_agent(B)
    tools.send(world, A, B, "queued")
    world.channel_cut = True
    assert tools.send(world, A, B, "x").status == "denied"
    assert tools.recv(world, B, A).status == "denied"
    assert tools.scan(world, A, next(iter(world.hosts))).status == "ok"


@pytest.mark.parametrize("tool,args", [
    ("scan", ("h-ffffffff",)),
    ("login", ("h-ffffffff", "c-ffffffff")),
    ("list", ("h-ffffffff", "")),
    ("read", ("f-ffffffff",)),
    ("write", ("f-ffffffff", "x")),
    ("recv", ("a-ffffffff",)),
])
def test_missing_targets_return_not_found(tool: str, args: tuple[str, ...]) -> None:
    world = generate_world(12, 1)
    world.add_agent(A, zones=tuple(world.zones))
    result = getattr(tools, tool)(world, A, *args)
    assert (result.status, result.size, result.content) == ("not_found", 0, None)
