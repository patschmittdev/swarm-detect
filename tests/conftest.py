from pathlib import Path

import pytest

from swarmtrace.trace.schema import TraceEvent


@pytest.fixture
def event() -> TraceEvent:
    return TraceEvent(
        schema_version=1,
        run_id="0123456789abcdef",
        seq=0,
        tick=0,
        agent="a-12345678",
        tool="scan",
        target="h-12345678",
        args={},
        result={"status": "ok", "size": 0},
        content=None,
        provenance=None,
    )


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent / "fixtures" / "runs"
