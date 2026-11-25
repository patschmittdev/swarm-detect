"""Run-level credential sharing among connected groups of interacting agents."""

import pandas as pd

from .attribution import propose_groups


def component_score(pairs: pd.DataFrame) -> float:
    """Score one run's V1 or V2 pair features indexed by ``(agent_a, agent_b)``.

    A direct message, read after write, or shared login connects two agents. Count each
    connected component containing a shared login once, and divide by one plus the number
    of components with an observed interaction. Isolated agents contribute to neither count.
    """
    if pairs.index.nlevels != 2:
        raise ValueError("component_score needs pair features for a single run")
    required = ("direct_messages", "read_after_write", "shared_credential_logins")
    missing = [column for column in required if column not in pairs]
    if missing:
        raise ValueError(f"component_score needs pair feature columns {missing}")

    sharing = pairs["shared_credential_logins"] > 0
    if not sharing.any():
        return 0.0
    interacting = sharing | (pairs["direct_messages"] > 0) | (pairs["read_after_write"] > 0)
    groups = propose_groups(interacting, threshold=0)
    sharing_agents = {agent for edge in pairs.index[sharing] for agent in edge}
    sharing_groups = sum(not group.isdisjoint(sharing_agents) for group in groups)
    return sharing_groups / (1 + len(groups))
