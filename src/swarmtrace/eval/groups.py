"""Label-side scoring of proposed groups: reconstruction of the offensive group, and the roles of
agents named wrongly. Labels are read here, inside ``swarmtrace.eval``, and nowhere upstream."""

from collections.abc import Collection, Mapping, Sequence

from swarmtrace.trace.io import Labels

from .data import BENIGN_TEAM, OFFENSIVE

BENIGN_SOLO = "benign_solo"
SHARING = "benign_team, sharing team"
NOT_SHARING = "benign_team, non-sharing team"
UNRESOLVED = "benign_team, sharing unresolved"
"""Observed shared-credential logins do not reconcile with the run's declared count."""
NO_METADATA = "benign_team, no sharing metadata"
"""The run's condition has no ``benign_sharing_teams`` count."""
WRONG_CATEGORIES = (BENIGN_SOLO, SHARING, NOT_SHARING, UNRESOLVED, NO_METADATA)
SHARING_KEY = "benign_sharing_teams"


def jaccard(first: frozenset[str], second: frozenset[str]) -> float:
    """Overlap of two agent sets; 0 when both are empty."""
    union = first | second
    return len(first & second) / len(union) if union else 0.0


def proposed_group(groups: Sequence[frozenset[str]], offensive: frozenset[str]) -> frozenset[str]:
    """The proposed group with the most offensive members.

    Ties go to the larger Jaccard overlap with ``offensive``, then to the group whose sorted agent
    ids come first. Empty when nothing is proposed.
    """
    if not groups:
        return frozenset()
    return min(groups, key=lambda group: (
        -len(group & offensive), -jaccard(group, offensive), sorted(group),
    ))


def reconstruction(
    groups: Sequence[frozenset[str]], offensive: frozenset[str],
) -> tuple[float, bool]:
    """``(Jaccard overlap, reconstructed exactly)`` of the proposed group against ``offensive``."""
    group = proposed_group(groups, offensive)
    return jaccard(group, offensive), group == offensive


def team_sharing(
    labels: Labels, condition: Mapping[str, int | str],
    shared_logins: Collection[tuple[str, str]] | None = None,
) -> dict[str, str]:
    """Sharing category of each benign team in a run.

    The condition declares how many benign teams share credentials (``SHARING_KEY``); it does
    not say which. A team is observed sharing when two of its members have a shared-credential
    login (``shared_logins``, pairs from the V1 pair table). A non-sharing team cannot produce
    one, but a sharing team may not have by the end of the run, so absence is not conclusive.
    A team is also sharing when the declared count equals the number of teams. When the
    sharing teams found this way number exactly the declared count, the remaining teams are
    non-sharing; otherwise the remaining teams are ``UNRESOLVED``, as are all teams when more
    are observed than declared. ``None`` means no login evidence is available.
    """
    members: dict[str, set[str]] = {}
    for agent, label in labels.agents.items():
        if label.role == BENIGN_TEAM:
            if label.group is None:
                raise ValueError(f"benign team agent {agent!r} has no group id")
            members.setdefault(label.group, set()).add(agent)
    teams = sorted(members)
    count = condition.get(SHARING_KEY)
    if count is None:
        return dict.fromkeys(teams, NO_METADATA)
    if type(count) is not int or not 0 <= count <= len(teams):
        raise ValueError(f"{SHARING_KEY}={count!r} does not fit {len(teams)} benign teams")
    observed = {team for team in teams if any(
        first in members[team] and second in members[team]
        for first, second in shared_logins or ()
    )}
    sharing = set(teams) if count == len(teams) else observed
    if len(sharing) > count:
        return dict.fromkeys(teams, UNRESOLVED)
    rest = NOT_SHARING if len(sharing) == count else UNRESOLVED
    return {team: SHARING if team in sharing else rest for team in teams}


def wrongly_named(
    groups: Sequence[frozenset[str]], labels: Labels, condition: Mapping[str, int | str],
    shared_logins: Collection[tuple[str, str]] | None = None,
) -> dict[str, int]:
    """Count, by ``WRONG_CATEGORIES``, the non-offensive agents in any proposed group of a run.

    ``shared_logins`` is the run's evidence for ``team_sharing``.
    """
    counts = dict.fromkeys(WRONG_CATEGORIES, 0)
    sharing = None
    for agent in sorted(set().union(*groups)):
        label = labels.agents.get(agent)
        if label is None:
            raise ValueError(f"agent {agent!r} has no label in run {labels.run_id}")
        if label.role == OFFENSIVE:
            continue
        if label.role == BENIGN_SOLO:
            counts[BENIGN_SOLO] += 1
        elif label.role == BENIGN_TEAM:
            if sharing is None:
                sharing = team_sharing(labels, condition, shared_logins)
            counts[sharing[label.group]] += 1
        else:
            raise ValueError(f"unknown role {label.role!r} for agent {agent!r}")
    return counts
