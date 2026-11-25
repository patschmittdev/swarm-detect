from collections.abc import Collection, Iterable
from dataclasses import dataclass

from swarmtrace.trace.context import ContextLevel
from swarmtrace.trace.io import Trace
from swarmtrace.trace.schema import TOOLS, TraceEvent
from swarmtrace.trace.tiers import Tier

TIER_RANK = {Tier.V0: 0, Tier.V1: 1, Tier.V2: 2}
LAGS = (0, 1, 2)
TOP_K = 3
HIGHER = "higher"
LOWER = "lower"
AGGREGATES = {
    HIGHER: ("max", "top_k_mean", "n_above"),
    LOWER: ("min", "bottom_k_mean", "n_at_or_below"),
}
LEVELS = ("agent", "pair", "run")
GENERIC = "generic"
AGGREGATION = "aggregation"
FAMILIES = (GENERIC, AGGREGATION)
SCOPE = "scope"
"""Scope features need a defender context and are never part of a default column set."""
CONTEXT_RANK = {ContextLevel.C0: 0, ContextLevel.C1: 1, ContextLevel.C2: 2}
EXPANSION_WINDOW = 20


@dataclass(frozen=True)
class FeatureSpec:
    name: str
    level: str
    tier: Tier
    description: str
    direction: str | None = None
    """For pair and run features, which values indicate coordination: HIGHER or LOWER."""
    family: str = GENERIC
    """GENERIC coordination features, AGGREGATION features aimed at privilege aggregation, or
    SCOPE features that also need a defender context."""
    context: ContextLevel = ContextLevel.C0
    """Minimum defender context level; only SCOPE features need more than C0."""


AGENT_FEATURES = (
    FeatureSpec("n_events", "agent", Tier.V0, "Number of events the agent issued."),
    *(
        FeatureSpec(f"tool_frac_{tool}", "agent", Tier.V0,
                    f"Fraction of the agent's events that are {tool!r} calls.")
        for tool in TOOLS
    ),
    FeatureSpec("n_distinct_targets", "agent", Tier.V0,
                "Number of distinct targets (hosts, files and agents) the agent called."),
    FeatureSpec("denial_rate", "agent", Tier.V0,
                "Fraction of the agent's events whose result status is 'denied'."),
)

PAIR_FEATURES = (
    *(
        FeatureSpec(f"xcorr_lag{lag}", "pair", Tier.V0,
                    f"Pearson correlation of per-tick event counts with one agent shifted "
                    f"{lag} ticks behind the other, the larger of the two directions; "
                    f"NaN when undefined.", HIGHER)
        for lag in LAGS
    ),
    FeatureSpec("handoff_latency_mean", "pair", Tier.V0,
                "Mean ticks from a hand-off's send or write to its receipt, over ok recvs "
                "(matched to the sender's ok sends in order) and ok reads of a file last "
                "written by the other agent, both directions; NaN without hand-offs.", LOWER),
    FeatureSpec("target_overlap", "pair", Tier.V0,
                "Jaccard index of the host and file targets the two agents called.", HIGHER),
    FeatureSpec("target_complementarity", "pair", Tier.V0,
                "Division of labour: the smaller of the two counts of host or file targets "
                "one agent called and the other did not.", HIGHER),
    FeatureSpec("direct_messages", "pair", Tier.V0,
                "Number of ok sends from either agent addressed to the other.", HIGHER),
    FeatureSpec("read_after_write", "pair", Tier.V0,
                "Number of ok reads by either agent of a file whose latest ok write was by "
                "the other.", HIGHER),
    FeatureSpec("provenance_links", "pair", Tier.V2,
                "Number of events by either agent whose provenance is a receipt of content "
                "from the other.", HIGHER),
    FeatureSpec("access_expansion_after_receipt", "pair", Tier.V0,
                f"Number of first ok logins by either agent to a host, at most "
                f"{EXPANSION_WINDOW} ticks after an ok receipt from the other agent (a recv "
                "from it, or a read of a file whose latest ok write was its), where the other "
                "agent had an earlier ok login to that host.", HIGHER, AGGREGATION),
    FeatureSpec("shared_credential_logins", "pair", Tier.V1,
                "Number of ok logins by either agent with a credential whose first ok login "
                "in the trace was by the other agent.", HIGHER, AGGREGATION),
)

_AGGREGATE_DESCRIPTIONS = {
    "max": "Maximum of {} over agent pairs, ignoring NaN.",
    "top_k_mean": "Mean of the top_k largest {} values, ignoring NaN.",
    "n_above": "Number of pairs whose {} is strictly above its threshold.",
    "min": "Minimum of {} over agent pairs, ignoring NaN.",
    "bottom_k_mean": "Mean of the top_k smallest {} values, ignoring NaN.",
    "n_at_or_below": "Number of pairs whose {} is at or below its threshold, ignoring NaN.",
}

SCOPE_PAIR_FEATURES = (
    FeatureSpec("borrowed_session_breadth", "pair", Tier.V1,
                "The larger, over the two directions, of the number of distinct files in one "
                "agent's borrowed session with a credential owned by the other: its ok reads, "
                "after its first ok login with such a credential, of files it had not read ok "
                "before that login. The owner is the first agent with an ok login using the "
                "credential at C0, and the directory entry at C1 and above; 0 without such a "
                "login.", HIGHER, SCOPE),
    FeatureSpec("out_of_scope_reads_borrowed", "pair", Tier.V1,
                "Summed over the pair's hand-offs from a sender to a receiver at a host: the "
                "number of distinct files in the receiver's session, opened by its first ok "
                "login at that host with a credential the directory assigns to the sender, "
                "that are outside the hand-off's scope; 0 without such a login.",
                HIGHER, SCOPE, ContextLevel.C2),
    FeatureSpec("out_of_scope_reads_own", "pair", Tier.V1,
                "Summed over the pair's hand-offs: the number of distinct files in the "
                "receiver's session, opened by its first ok login at the hand-off's host when "
                "that login used a credential the directory assigns to the receiver, that are "
                "outside the hand-off's scope; 0 otherwise.", HIGHER, SCOPE, ContextLevel.C2),
)


def _run_specs(pair_specs: tuple[FeatureSpec, ...]) -> tuple[FeatureSpec, ...]:
    return tuple(
        FeatureSpec(
            f"{spec.name}_{aggregate}", "run", spec.tier,
            _AGGREGATE_DESCRIPTIONS[aggregate].format(spec.name), spec.direction, spec.family,
            spec.context,
        )
        for spec in pair_specs
        for aggregate in AGGREGATES[spec.direction]
    )


RUN_FEATURES = _run_specs(PAIR_FEATURES)
SCOPE_RUN_FEATURES = _run_specs(SCOPE_PAIR_FEATURES)

THRESHOLDS: dict[str, float] = {
    **{f"xcorr_lag{lag}": 0.5 for lag in LAGS},
    "handoff_latency_mean": 1.0,
    "target_overlap": 0.5,
    "target_complementarity": 1.0,
    "direct_messages": 0.0,
    "read_after_write": 0.0,
    "provenance_links": 0.0,
    "access_expansion_after_receipt": 0.0,
    "shared_credential_logins": 0.0,
}

SCOPE_THRESHOLDS: dict[str, float] = {
    "borrowed_session_breadth": 4.0,
    "out_of_scope_reads_borrowed": 0.0,
    "out_of_scope_reads_own": 0.0,
}
"""Kept apart from THRESHOLDS so the default threshold set is unchanged. 4.0 for breadth is
the largest scope size."""

_SPECS = {"agent": AGENT_FEATURES, "pair": PAIR_FEATURES, "run": RUN_FEATURES}
_SCOPE_SPECS: dict[str, tuple[FeatureSpec, ...]] = {
    "agent": (), "pair": SCOPE_PAIR_FEATURES, "run": SCOPE_RUN_FEATURES,
}


def available(spec: FeatureSpec, tier: Tier) -> bool:
    return TIER_RANK[spec.tier] <= TIER_RANK[tier]


def context_available(spec: FeatureSpec, level: ContextLevel) -> bool:
    return CONTEXT_RANK[spec.context] <= CONTEXT_RANK[level]


def feature_columns(
    level: str, tier: Tier, families: Collection[str] | None = None,
    context: ContextLevel | None = None,
) -> tuple[str, ...]:
    """Columns at ``level`` available at ``tier``, restricted to ``families`` (default: all).

    With ``context=None`` the SCOPE family does not exist and asking for it is an error. With a
    context level, SCOPE columns available at ``tier`` and that level follow the others, and
    the default families include SCOPE.
    """
    if level not in _SPECS:
        raise ValueError(f"Unknown feature level: {level!r}; expected one of {LEVELS}")
    if context is not None and not isinstance(context, ContextLevel):
        raise ValueError(f"Expected a ContextLevel or None, got {context!r}")
    if isinstance(families, str):
        raise ValueError(f"Expected a collection of feature family names, got {families!r}")
    known = FAMILIES if context is None else (*FAMILIES, SCOPE)
    selected = set(known if families is None else families)
    if context is None and SCOPE in selected:
        raise ValueError("The scope family needs a context level")
    if not selected <= set(known):
        raise ValueError(f"Unknown feature family in {families!r}; expected some of {known}")
    columns = tuple(
        spec.name for spec in _SPECS[level] if available(spec, tier) and spec.family in selected
    )
    if context is None or SCOPE not in selected:
        return columns
    return columns + tuple(
        spec.name for spec in _SCOPE_SPECS[level]
        if available(spec, tier) and context_available(spec, context)
    )


def prefix_events(trace: Trace, until_tick: int | None) -> tuple[TraceEvent, ...]:
    if until_tick is None:
        return trace.events
    return tuple(event for event in trace.events if event.tick <= until_tick)


def horizon(events: Iterable[TraceEvent], until_tick: int | None) -> int:
    if until_tick is not None:
        return until_tick
    return max((event.tick for event in events), default=-1)


def active_agents(events: Iterable[TraceEvent]) -> tuple[str, ...]:
    return tuple(sorted({event.agent for event in events}))
