import json
from dataclasses import replace

import pytest

from swarmtrace.agents.base import Action
from swarmtrace.sim.engine import Engine
from swarmtrace.sim.runner import Condition, run_one
from swarmtrace.trace.authorization import (
    ReadAudit,
    ReadDecision,
    ReadGrant,
    read_authorization,
    write_authorization,
)
from swarmtrace.trace.io import RunPaths, read_trace
from swarmtrace.world import File, generate_world

SENDER = "a-00000001"
WORKER = "a-00000002"
OTHER = "a-00000003"
EXTRA = "f-00000001"


class Worker:
    def __init__(self, actions):
        self.actions = actions

    def act(self, observation):
        return self.actions[observation.tick]


def assignment(*, ordinary=False):
    world = generate_world(12, 2)
    host = next(iter(world.hosts))
    own = next(c.id for c in world.credentials.values() if c.host == host)
    source = next(f.id for f in world.files.values() if f.host == host and f.content is not None)
    world.files[EXTRA] = File(EXTRA, host, "/other.txt", "other file")
    world.add_agent(SENDER, credentials=(own,))
    world.add_agent(WORKER, zones=(world.hosts[host].zone,) if ordinary else ())
    world.handover(SENDER, WORKER, own)
    return world, ReadGrant("assignment-1", SENDER, WORKER, host, (source,), (own,))


def capture(tmp_path, world, grants, actions, after_tick=None):
    engine = Engine(world, {WORKER: Worker(actions)}, 31, read_grants=grants, after_tick=after_tick)
    events = engine.run(len(actions), tmp_path / "trace.jsonl")
    return events, engine.read_audit


def test_only_successful_reads_are_bound_at_the_gateway(tmp_path):
    world, grant = assignment()
    source, = grant.files
    reserved = next(f.id for f in world.files.values()
                    if f.host == grant.host and f.content is None)
    events, audit = capture(tmp_path, world, (grant,), [
        Action("read", source, grant_id=grant.grant_id),  # No session yet.
        Action("login", grant.host, {"credential": grant.credentials[0]}),
        Action("read", reserved),
        Action("read", source),
        Action("read", EXTRA),
        Action("read", source, grant_id="unregistered"),
    ])
    assert [event.result["status"] for event in events] == [
        "denied", "ok", "not_found", "ok", "ok", "ok",
    ]
    assert audit.grants == (grant,) and audit.run_id == events[0].run_id
    assert audit.decisions == (
        ReadDecision(3, WORKER, source, grant.host, "grant", grant.grant_id),
        ReadDecision(4, WORKER, EXTRA, grant.host, "grant", grant.grant_id),
        ReadDecision(5, WORKER, source, grant.host, "unknown"),
    )
    assert events[-1].args == {}


def test_two_assignments_cannot_be_disambiguated_by_file_membership(tmp_path):
    world, first = assignment()
    second = replace(first, grant_id="assignment-2", files=(EXTRA,))
    _, audit = capture(tmp_path, world, (first, second), [
        Action("login", first.host, {"credential": first.credentials[0]}),
        Action("read", EXTRA),
        Action("read", EXTRA, grant_id=first.grant_id),  # Excluded by the selected task.
        Action("read", EXTRA, grant_id=second.grant_id),
    ])
    assert [(d.basis, d.grant_id) for d in audit.decisions] == [
        ("unknown", None), ("grant", first.grant_id), ("grant", second.grant_id),
    ]


def test_ordinary_access_competes_with_active_delegation_and_survives_revocation(tmp_path):
    world, grant = assignment(ordinary=True)
    cred, = grant.credentials
    _, audit = capture(tmp_path, world, (grant,), [
        Action("read", EXTRA),
        Action("login", grant.host, {"credential": cred}),
        Action("read", EXTRA),
        Action("read", EXTRA, grant_id=grant.grant_id),
        Action("read", EXTRA, grant_id=grant.grant_id),
        Action("read", EXTRA),
    ], after_tick=lambda tick: world.revoke(cred) if tick == 3 else None)
    assert [(d.basis, d.grant_id) for d in audit.decisions] == [
        ("ordinary", None), ("unknown", None), ("grant", grant.grant_id),
        ("unknown", None), ("ordinary", None),
    ]


def test_unregistered_session_and_wrong_receiver_are_unknown(tmp_path):
    world, grant = assignment()
    world.add_agent(OTHER)
    wrong_actor = replace(grant, receiver=OTHER)
    _, audit = capture(tmp_path, world, (wrong_actor,), [
        Action("login", grant.host, {"credential": grant.credentials[0]}),
        Action("read", EXTRA, grant_id=grant.grant_id), Action("read", EXTRA),
    ])
    assert [d.basis for d in audit.decisions] == ["unknown", "unknown"]


def test_native_login_is_ordinary_and_unrelated_host_binding_is_unknown(tmp_path):
    world, grant = assignment()
    native = next(c for c in world.credentials.values() if c.host != grant.host)
    world.add_agent(OTHER, credentials=(native.id,))
    source = next(f.id for f in world.files.values() if f.host == native.host and f.content is not None)
    engine = Engine(world, {OTHER: Worker([
        Action("login", native.host, {"credential": native.id}), Action("read", source),
        Action("read", source, grant_id=grant.grant_id),
    ])}, 3, read_grants=(grant,))
    engine.run(3, tmp_path / "trace.jsonl")
    assert [d.basis for d in engine.read_audit.decisions] == ["ordinary", "unknown"]


def test_an_untracked_live_credential_prevents_unqualified_attribution(tmp_path):
    world, grant = assignment()
    other = next(c for c in world.credentials.values() if c.host != grant.host)
    world.add_agent(OTHER, credentials=(other.id,))
    world.grant_access(OTHER, grant.host, other.id)
    world.handover(OTHER, WORKER, other.id)
    _, audit = capture(tmp_path, world, (grant,), [
        Action("login", grant.host, {"credential": grant.credentials[0]}),
        Action("login", grant.host, {"credential": other.id}),
        Action("read", EXTRA), Action("read", EXTRA, grant_id=grant.grant_id),
        Action("read", EXTRA),
    ], after_tick=lambda tick: world.revoke(other.id) if tick == 3 else None)
    assert [d.basis for d in audit.decisions] == ["unknown", "grant", "grant"]


@pytest.mark.parametrize("scope", ["on", "off"])
def test_run_one_sidecar_preserves_seeded_base_artifacts_and_covers_reads(tmp_path, scope):
    condition = Condition(scope=scope, coordinated_groups=1, benign_credential_sharing=100)
    default = RunPaths(run_one(condition, 19, tmp_path / "default"))
    captured = RunPaths(run_one(condition, 19, tmp_path / "captured", capture_authorization=True))
    assert not default.authorization.exists()
    for before in default.run_dir.iterdir():
        assert before.read_bytes() == (captured.run_dir / before.name).read_bytes()
    audit = read_authorization(captured.authorization)
    trace = read_trace(captured.trace)
    assert len(audit.grants) > 0 if scope == "on" else not audit.grants
    assert audit.run_id == trace.run_id
    assert [(d.seq, d.agent, d.file) for d in audit.decisions] == [
        (e.seq, e.agent, e.target) for e in trace.events if e.tool == "read" and e.result["status"] == "ok"
    ]
    assert any(d.basis == "ordinary" for d in audit.decisions)
    assert any(d.basis == ("grant" if scope == "on" else "unknown") for d in audit.decisions)
    roundtrip = tmp_path / "roundtrip.json"
    write_authorization(roundtrip, audit)
    assert roundtrip.read_bytes() == captured.authorization.read_bytes()


def test_read_audit_allows_partial_capture_and_rejects_stale_references(tmp_path):
    world, grant = assignment()
    first = ReadDecision(2, WORKER, EXTRA, grant.host, "grant", grant.grant_id)
    second = replace(first, seq=5)
    audit = ReadAudit("test-run", (grant,), (first, second))
    assert replace(audit, decisions=(second,)).decisions == (second,)
    with pytest.raises(ValueError, match="strictly increasing"):
        replace(audit, decisions=(second, first))
    with pytest.raises(ValueError, match="grant for its actor"):
        replace(audit, grants=())
    with pytest.raises(ValueError, match="duplicate grant"):
        Engine(world, {}, 1, read_grants=(grant, grant))
    with pytest.raises(ValueError, match="on its host"):
        Engine(world, {}, 1, read_grants=(replace(grant, host=next(h for h in world.hosts if h != grant.host)),))
    path = tmp_path / "authorization.json"
    write_authorization(path, audit)
    record = json.loads(path.read_bytes())
    record["schema_version"] = True
    path.write_text(json.dumps(record))
    with pytest.raises(ValueError, match="schema version"):
        read_authorization(path)
    with pytest.raises(FileNotFoundError):
        read_authorization(tmp_path / "missing.json")


def test_capture_mode_refuses_existing_sidecar_and_bindings_on_other_tools(tmp_path):
    assert Engine(generate_world(12, 1), {}, 31).read_audit is None
    with pytest.raises(ValueError, match="only a read"):
        Action("write", EXTRA, grant_id="assignment")
    paths = RunPaths(tmp_path)
    paths.authorization.write_text("existing capture")
    with pytest.raises(ValueError, match="artifacts already exist"):
        run_one(Condition(), 19, tmp_path, capture_authorization=True)
    assert paths.authorization.read_text() == "existing capture" and not paths.trace.exists()
