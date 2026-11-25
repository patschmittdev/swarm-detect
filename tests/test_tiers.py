from dataclasses import replace

import pytest

from swarmtrace.trace.schema import TraceEvent, TraceSchemaError, validate_event, validate_trace
from swarmtrace.trace.tiers import Tier, project


def test_pinned_tier_vocabulary() -> None:
    assert [(name, tier.value) for name, tier in Tier.__members__.items()] == [
        ("V0", "V0"),
        ("V1", "V1"),
        ("V2", "V2"),
    ]


@pytest.mark.parametrize("tier", [Tier.V0, Tier.V1, Tier.V2])
def test_projection(event: TraceEvent, tier: Tier) -> None:
    full = replace(
        event, seq=2, tick=3, tool="send", target="a-87654321",
        args={"size": 4, "digest": "0123456789abcdef"},
        result={"status": "ok", "size": 4}, content="text", provenance=1,
    )
    projected = project(full, tier)
    validate_event(projected, tier=tier)
    if tier is Tier.V2:
        assert projected is full
    elif tier is Tier.V1:
        assert projected == replace(full, content=None, provenance=None)
    else:
        assert projected == replace(
            full, content=None, provenance=None, args={}, result={"status": "ok", "size": 0}
        )
    assert full.content == "text"
    assert full.provenance == 1


@pytest.mark.parametrize("tier", [Tier.V0, Tier.V1])
@pytest.mark.parametrize(
    ("changes", "field"),
    [({"content": ""}, "content"), ({"content": "text"}, "content"),
     ({"provenance": 0}, "provenance")],
)
def test_lower_tiers_reject_v2_fields(
    event: TraceEvent, tier: Tier, changes: dict[str, object], field: str
) -> None:
    received = replace(
        event, tool="recv", target="a-87654321",
        args={"size": 4, "digest": "0123456789abcdef"},
        result={"status": "ok", "size": 4}, content="text",
    )
    followup = replace(event, seq=1, provenance=0)
    projected = [project(received, tier), project(followup, tier)]
    validate_trace(projected, tier=tier)
    invalid = replace(projected[1], **changes)
    with pytest.raises(TraceSchemaError, match=field):
        validate_event(invalid, tier=tier)
    with pytest.raises(TraceSchemaError, match=field):
        validate_trace([projected[0], invalid], tier=tier)


def test_v0_requires_empty_args_and_zero_result_size(event: TraceEvent) -> None:
    full = replace(
        event, tool="send", target="a-87654321",
        args={"size": 4, "digest": "0123456789abcdef"},
        result={"status": "ok", "size": 4}, content="text",
    )
    v0 = project(full, Tier.V0)
    validate_event(v0, tier=Tier.V0)
    validate_trace([v0], tier=Tier.V0)
    for invalid, field in [
        (replace(v0, args=full.args), "args"),
        (replace(v0, result=full.result), "result.size"),
    ]:
        with pytest.raises(TraceSchemaError, match=field):
            validate_event(invalid, tier=Tier.V0)
        with pytest.raises(TraceSchemaError, match=field):
            validate_trace([invalid], tier=Tier.V0)
    v1 = project(full, Tier.V1)
    validate_event(v1, tier=Tier.V1)
    validate_trace([v1], tier=Tier.V1)
    with pytest.raises(TraceSchemaError, match="args"):
        validate_event(replace(v1, args={}), tier=Tier.V1)
    with pytest.raises(TraceSchemaError, match="args"):
        validate_trace([replace(v1, args={})], tier=Tier.V1)
    with pytest.raises(TraceSchemaError, match="content"):
        validate_event(v1)
    with pytest.raises(TraceSchemaError, match="content"):
        validate_trace([v1])
