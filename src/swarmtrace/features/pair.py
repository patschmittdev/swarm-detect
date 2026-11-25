import math
from collections import Counter, defaultdict, deque
from collections.abc import Sequence
from itertools import combinations

import pandas as pd

from swarmtrace.trace.context import Context
from swarmtrace.trace.io import Trace

from .scope import check_context, scope_pair_values
from .spec import (
    EXPANSION_WINDOW,
    LAGS,
    PAIR_FEATURES,
    active_agents,
    available,
    feature_columns,
    horizon,
    prefix_events,
)

COUNT_COLUMNS = frozenset({
    "target_complementarity", "direct_messages", "read_after_write", "provenance_links",
    "access_expansion_after_receipt", "shared_credential_logins",
})
MESSAGE_TOOLS = frozenset({"send", "recv"})
PROVENANCE = next(spec for spec in PAIR_FEATURES if spec.name == "provenance_links")
SHARED_CREDENTIAL = next(
    spec for spec in PAIR_FEATURES if spec.name == "shared_credential_logins"
)

Pair = tuple[str, str]


def _pair(first: str, second: str) -> Pair:
    return (first, second) if first < second else (second, first)


def _correlation(x: Sequence[int], y: Sequence[int]) -> float:
    n = len(x)
    if n < 2:
        return math.nan
    mean_x, mean_y = sum(x) / n, sum(y) / n
    sxy = sum((a - mean_x) * (b - mean_y) for a, b in zip(x, y))
    sxx = sum((a - mean_x) ** 2 for a in x)
    syy = sum((b - mean_y) ** 2 for b in y)
    if sxx == 0 or syy == 0:
        return math.nan
    return sxy / math.sqrt(sxx * syy)


def _lagged_correlation(x: Sequence[int], y: Sequence[int], lag: int) -> float:
    n = len(x)
    if lag == 0:
        return _correlation(x, y)
    values = [
        value
        for value in (_correlation(x[: n - lag], y[lag:]), _correlation(y[: n - lag], x[lag:]))
        if not math.isnan(value)
    ]
    return max(values, default=math.nan)


def pair_features(
    trace: Trace, until_tick: int | None = None, *, context: Context | None = None,
) -> pd.DataFrame:
    """Features for each unordered pair of agents active by ``until_tick``.

    Rows are indexed by ``(agent_a, agent_b)`` with ``agent_a < agent_b``; every feature is
    symmetric in the pair. With a ``context`` for the same run, the SCOPE columns available at
    its level follow the others; with ``context=None`` there are none.
    """
    if context is not None:
        check_context(trace, context)
    events = prefix_events(trace, until_tick)
    agents = active_agents(events)
    length = horizon(events, until_tick) + 1
    series = {agent: [0] * max(length, 0) for agent in agents}
    resources: dict[str, set[str]] = defaultdict(set)
    messages: Counter[Pair] = Counter()
    reads: Counter[Pair] = Counter()
    links: Counter[Pair] = Counter()
    latencies: dict[Pair, list[int]] = defaultdict(list)
    queues: dict[Pair, deque[int]] = defaultdict(deque)
    writers: dict[str, tuple[str, int]] = {}
    receipt_source: dict[int, str] = {}
    expansions: Counter[Pair] = Counter()
    shared_logins: Counter[Pair] = Counter()
    logged_in: set[tuple[str, str]] = set()
    latest_receipt: dict[str, dict[str, int]] = defaultdict(dict)
    first_user: dict[str, str] = {}
    with_provenance = available(PROVENANCE, trace.tier)
    with_credentials = available(SHARED_CREDENTIAL, trace.tier)

    for event in events:
        agent, target, ok = event.agent, event.target, event.result["status"] == "ok"
        series[agent][event.tick] += 1
        if event.tool not in MESSAGE_TOOLS:
            resources[agent].add(target)
        if with_provenance and event.provenance in receipt_source:
            links[_pair(agent, receipt_source[event.provenance])] += 1
        if not ok:
            continue
        if event.tool == "send" and target != agent:
            queues[(agent, target)].append(event.tick)
            messages[_pair(agent, target)] += 1
        elif event.tool == "recv" and target != agent:
            receipt_source[event.seq] = target
            latest_receipt[agent][target] = event.tick
            queue = queues[(target, agent)]
            if queue:
                latencies[_pair(agent, target)].append(event.tick - queue.popleft())
        elif event.tool == "read" and target in writers and writers[target][0] != agent:
            writer, written = writers[target]
            receipt_source[event.seq] = writer
            latest_receipt[agent][writer] = event.tick
            reads[_pair(agent, writer)] += 1
            latencies[_pair(agent, writer)].append(event.tick - written)
        elif event.tool == "write":
            writers[target] = (agent, event.tick)
        elif event.tool == "login":
            if (agent, target) not in logged_in:
                logged_in.add((agent, target))
                for sender, tick in latest_receipt[agent].items():
                    recent = event.tick - tick <= EXPANSION_WINDOW
                    if recent and (sender, target) in logged_in:
                        expansions[_pair(agent, sender)] += 1
            if with_credentials:
                owner = first_user.setdefault(str(event.args["credential"]), agent)
                if owner != agent:
                    shared_logins[_pair(agent, owner)] += 1

    pairs = list(combinations(agents, 2))
    rows = []
    for first, second in pairs:
        pair = (first, second)
        row: dict[str, float] = {
            f"xcorr_lag{lag}": _lagged_correlation(series[first], series[second], lag)
            for lag in LAGS
        }
        handoffs = sorted(latencies[pair])
        row["handoff_latency_mean"] = sum(handoffs) / len(handoffs) if handoffs else math.nan
        union = resources[first] | resources[second]
        shared = resources[first] & resources[second]
        row["target_overlap"] = len(shared) / len(union) if union else math.nan
        row["target_complementarity"] = min(
            len(resources[first] - resources[second]), len(resources[second] - resources[first])
        )
        row["direct_messages"] = messages[pair]
        row["read_after_write"] = reads[pair]
        if with_provenance:
            row["provenance_links"] = links[pair]
        row["access_expansion_after_receipt"] = expansions[pair]
        if with_credentials:
            row["shared_credential_logins"] = shared_logins[pair]
        rows.append(row)

    columns = list(feature_columns("pair", trace.tier))
    index = pd.MultiIndex.from_arrays(
        [pd.Index([pair[position] for pair in pairs], dtype="str") for position in (0, 1)],
        names=["agent_a", "agent_b"],
    )
    frame = pd.DataFrame(rows, columns=columns, index=index)
    frame = frame.astype(
        {column: "int64" if column in COUNT_COLUMNS else "float64" for column in columns}
    )
    if context is None:
        return frame
    for column, values in scope_pair_values(trace, events, pairs, context).items():
        frame[column] = pd.Series(values, index=index, dtype="int64")
    return frame
