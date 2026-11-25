import pandas as pd

from swarmtrace.trace.io import Trace
from swarmtrace.trace.schema import TOOLS

from .spec import active_agents, feature_columns, prefix_events


def agent_features(trace: Trace, until_tick: int | None = None) -> pd.DataFrame:
    """Per-agent features, one row per agent active by ``until_tick``, indexed by ``agent``."""
    events = prefix_events(trace, until_tick)
    rows = {}
    for agent in active_agents(events):
        own = [event for event in events if event.agent == agent]
        total = len(own)
        row: dict[str, float] = {"n_events": total}
        for tool in TOOLS:
            row[f"tool_frac_{tool}"] = sum(event.tool == tool for event in own) / total
        row["n_distinct_targets"] = len({event.target for event in own})
        row["denial_rate"] = sum(event.result["status"] == "denied" for event in own) / total
        rows[agent] = row
    columns = list(feature_columns("agent", trace.tier))
    frame = pd.DataFrame.from_dict(rows, orient="index", columns=columns)
    frame.index = pd.Index(list(rows), dtype="str", name="agent")
    return frame.astype({column: _dtype(column) for column in columns})


def _dtype(column: str) -> str:
    return "int64" if column.startswith("n_") else "float64"
