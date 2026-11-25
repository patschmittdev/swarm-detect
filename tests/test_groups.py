import numpy as np
import pytest

from swarmtrace.eval.groups import (
    NO_METADATA,
    NOT_SHARING,
    SHARING,
    UNRESOLVED,
    WRONG_CATEGORIES,
    jaccard,
    proposed_group,
    reconstruction,
    team_sharing,
    wrongly_named,
)
from swarmtrace.trace.io import AgentLabel, Labels

OFFENSIVE = frozenset({"a", "b", "c"})


def test_jaccard_of_sets() -> None:
    assert jaccard(frozenset({"a", "b"}), frozenset({"b", "c"})) == pytest.approx(1 / 3)
    assert jaccard(frozenset(), OFFENSIVE) == 0.0
    assert jaccard(OFFENSIVE, OFFENSIVE) == 1.0


def test_exact_reconstruction() -> None:
    groups = [frozenset({"x", "y"}), frozenset({"a", "b", "c"})]
    assert proposed_group(groups, OFFENSIVE) == OFFENSIVE
    assert reconstruction(groups, OFFENSIVE) == (1.0, True)


def test_partial_reconstruction_takes_the_component_with_most_offensive_agents() -> None:
    groups = [frozenset({"c", "x"}), frozenset({"a", "b", "t"})]
    assert proposed_group(groups, OFFENSIVE) == frozenset({"a", "b", "t"})
    score, exact = reconstruction(groups, OFFENSIVE)
    assert score == pytest.approx(2 / 4) and not exact
    superset = [frozenset({"a", "b", "c", "t"})]
    assert reconstruction(superset, OFFENSIVE) == (pytest.approx(3 / 4), False)


def test_ties_break_by_larger_jaccard_then_sorted_agent_ids() -> None:
    offensive = frozenset({"a", "b"})
    by_jaccard = [frozenset({"a", "t1", "t2"}), frozenset({"b", "u"})]
    assert proposed_group(by_jaccard, offensive) == frozenset({"b", "u"})
    by_ids = [frozenset({"b", "u"}), frozenset({"a", "t"})]
    assert proposed_group(by_ids, offensive) == frozenset({"a", "t"})
    assert proposed_group(list(reversed(by_ids)), offensive) == frozenset({"a", "t"})


def test_no_flagged_pair_gives_an_empty_group_and_zero_overlap() -> None:
    assert proposed_group([], OFFENSIVE) == frozenset()
    assert reconstruction([], OFFENSIVE) == (0.0, False)


def test_reconstruction_over_runs_has_known_mean_and_exact_fraction() -> None:
    runs = [
        ([frozenset({"a", "b", "c"})], OFFENSIVE),
        ([frozenset({"a", "b", "t"})], OFFENSIVE),
        ([], OFFENSIVE),
    ]
    scores = np.array([reconstruction(groups, truth)[0] for groups, truth in runs])
    exact = np.array([reconstruction(groups, truth)[1] for groups, truth in runs])
    assert scores.mean() == pytest.approx((1.0 + 0.5 + 0.0) / 3)
    assert int(exact.sum()) == 1


def labels(agents: dict[str, AgentLabel]) -> Labels:
    return Labels("0" * 16, agents, objective_completed=False, objective_tick=None)


ONE_SHARING_TEAM = labels({
    "a": AgentLabel("offensive", "g1"), "b": AgentLabel("offensive", "g1"),
    "t1": AgentLabel("benign_team", "team1"), "t2": AgentLabel("benign_team", "team1"),
    "s": AgentLabel("benign_solo", None), "r": AgentLabel("benign_solo", None),
})


def test_role_table_on_a_run_with_one_sharing_team() -> None:
    groups = [frozenset({"a", "b", "t1"}), frozenset({"t2", "s"})]
    counts = wrongly_named(groups, ONE_SHARING_TEAM, {"benign_sharing_teams": 1})
    assert counts == {"benign_solo": 1, SHARING: 2, NOT_SHARING: 0, UNRESOLVED: 0,
                      NO_METADATA: 0}
    assert tuple(counts) == WRONG_CATEGORIES
    assert sum(counts.values()) == 3
    assert wrongly_named([], ONE_SHARING_TEAM, {"benign_sharing_teams": 1}) == dict.fromkeys(
        WRONG_CATEGORIES, 0)


TWO_TEAMS = labels({
    "t1": AgentLabel("benign_team", "team1"), "t2": AgentLabel("benign_team", "team1"),
    "u1": AgentLabel("benign_team", "team2"), "u2": AgentLabel("benign_team", "team2"),
    "s": AgentLabel("benign_solo", None),
})
ONE_DECLARED = {"benign_sharing_teams": 1}


def test_team_sharing_from_the_declared_count_alone() -> None:
    assert team_sharing(ONE_SHARING_TEAM, ONE_DECLARED) == {"team1": SHARING}
    assert team_sharing(ONE_SHARING_TEAM, {"benign_sharing_teams": 0}) == {"team1": NOT_SHARING}
    assert team_sharing(ONE_SHARING_TEAM, {}) == {"team1": NO_METADATA}
    assert team_sharing(TWO_TEAMS, {"benign_sharing_teams": 2}) == {
        "team1": SHARING, "team2": SHARING}
    with pytest.raises(ValueError):
        team_sharing(TWO_TEAMS, {"benign_sharing_teams": 3})


def test_one_sharing_and_one_non_sharing_team_in_the_same_run() -> None:
    logins = {("t1", "t2")}
    assert team_sharing(TWO_TEAMS, ONE_DECLARED, logins) == {
        "team1": SHARING, "team2": NOT_SHARING}
    counts = wrongly_named([frozenset({"t1", "u1", "u2", "s"})], TWO_TEAMS, ONE_DECLARED, logins)
    assert counts == {"benign_solo": 1, SHARING: 1, NOT_SHARING: 2, UNRESOLVED: 0,
                      NO_METADATA: 0}


def test_a_declared_sharing_team_without_a_login_stays_unresolved() -> None:
    for logins in (None, set(), {("t1", "u1")}, {("t1", "s")}):
        assert team_sharing(TWO_TEAMS, ONE_DECLARED, logins) == {
            "team1": UNRESOLVED, "team2": UNRESOLVED}, logins
    counts = wrongly_named([frozenset({"t1", "u1"})], TWO_TEAMS, ONE_DECLARED, set())
    assert counts[UNRESOLVED] == 2
    three = labels({**TWO_TEAMS.agents, "v1": AgentLabel("benign_team", "team3"),
                    "v2": AgentLabel("benign_team", "team3")})
    assert team_sharing(three, {"benign_sharing_teams": 2}, {("t1", "t2")}) == {
        "team1": SHARING, "team2": UNRESOLVED, "team3": UNRESOLVED}


def test_more_observed_than_declared_sharing_teams_is_unresolved() -> None:
    logins = {("t1", "t2"), ("u1", "u2")}
    assert team_sharing(TWO_TEAMS, ONE_DECLARED, logins) == {
        "team1": UNRESOLVED, "team2": UNRESOLVED}
    assert team_sharing(TWO_TEAMS, {"benign_sharing_teams": 0}, {("t1", "t2")}) == {
        "team1": UNRESOLVED, "team2": UNRESOLVED}


def test_unknown_agent_or_role_is_rejected() -> None:
    with pytest.raises(ValueError):
        wrongly_named([frozenset({"a", "zz"})], ONE_SHARING_TEAM, {"benign_sharing_teams": 1})
    odd = labels({"a": AgentLabel("offensive", "g1"), "q": AgentLabel("auditor", None)})
    with pytest.raises(ValueError):
        wrongly_named([frozenset({"a", "q"})], odd, {})
