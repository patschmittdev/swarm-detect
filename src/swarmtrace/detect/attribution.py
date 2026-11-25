from collections.abc import Iterable

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier

from swarmtrace.features import LOWER, PAIR_FEATURES

from .models import check_labels, seed_states

RUN_LEVEL = "run_id"
DIRECTIONS = {spec.name: -1.0 if spec.direction == LOWER else 1.0 for spec in PAIR_FEATURES}
CANDIDATES = 101


def _components(edges: Iterable[tuple[str, str]]) -> list[frozenset[str]]:
    parent: dict[str, str] = {}

    def root(agent: str) -> str:
        while parent[agent] != agent:
            parent[agent] = parent[parent[agent]]
            agent = parent[agent]
        return agent

    for first, second in edges:
        parent.setdefault(first, first)
        parent.setdefault(second, second)
        parent[root(first)] = root(second)
    components: dict[str, set[str]] = {}
    for agent in parent:
        components.setdefault(root(agent), set()).add(agent)
    return sorted((frozenset(group) for group in components.values()), key=sorted)


def propose_groups(scores: pd.Series, threshold: float) -> list[frozenset[str]]:
    """Connected components of the graph whose edges are pairs scoring strictly above threshold.

    ``scores`` is indexed by ``(agent_a, agent_b)``.
    """
    return _components(pair for pair, value in scores.items() if value > threshold)


def _by_run(scores: pd.Series) -> dict[str, tuple[list[tuple[str, str]], np.ndarray]]:
    runs: dict[str, tuple[list[tuple[str, str]], list[float]]] = {}
    for (run, first, second), value in scores.items():
        edges, values = runs.setdefault(str(run), ([], []))
        edges.append((first, second))
        values.append(value)
    return {run: (edges, np.array(values)) for run, (edges, values) in sorted(runs.items())}


def _propose(
    runs: dict[str, tuple[list[tuple[str, str]], np.ndarray]], threshold: float
) -> dict[str, list[frozenset[str]]]:
    return {
        run: _components(edge for edge, above in zip(edges, values > threshold) if above)
        for run, (edges, values) in runs.items()
    }


def _agent_f1(groups: dict[str, list[frozenset[str]]], truth: dict[str, set[str]]) -> float:
    tp = fp = fn = 0
    for run, members in truth.items():
        flagged = set().union(*groups.get(run, []))
        tp += len(flagged & members)
        fp += len(flagged - members)
        fn += len(members - flagged)
    return 2 * tp / (2 * tp + fp + fn) if tp else 0.0


class PairScorer:
    """Scores agent pairs for coordination and proposes groups as connected components.

    Features are oriented so larger always means more coordinated (``LOWER`` features are
    negated), missing values are set to the least coordinated value seen in the rows a model is
    trained on (recomputed inside each internal fold), and a
    gradient-boosted model is constrained to be non-decreasing in every oriented feature. The
    pair threshold maximises pooled per-agent F1 over training runs, using out-of-fold scores
    from folds that keep each run whole and deal runs with a coordinated pair round-robin first,
    so two such runs suffice for every fold to train on one.
    """

    def __init__(self, seed: int, n_folds: int = 5) -> None:
        self.seed = seed
        self.n_folds = n_folds
        self.columns: tuple[str, ...] = ()
        self.fill = np.empty(0)
        self.threshold = float("nan")
        self.oof_scores = np.empty(0)

    def _orient(self, pairs: pd.DataFrame) -> np.ndarray:
        if tuple(pairs.columns) != self.columns:
            raise ValueError(f"expected columns {self.columns}, got {tuple(pairs.columns)}")
        signs = np.array([DIRECTIONS[column] for column in self.columns])
        return pairs.to_numpy(dtype=float) * signs

    def _model(self, state: int) -> HistGradientBoostingClassifier:
        return HistGradientBoostingClassifier(
            early_stopping=False,
            monotonic_cst=[1] * len(self.columns),
            random_state=state,
        )

    @staticmethod
    def _least_coordinated(oriented: np.ndarray) -> np.ndarray:
        observed = ~np.isnan(oriented)
        return np.array([
            oriented[observed[:, i], i].min() if observed[:, i].any() else 0.0
            for i in range(oriented.shape[1])
        ])

    @staticmethod
    def _impute_with(oriented: np.ndarray, fill: np.ndarray) -> np.ndarray:
        return np.where(np.isnan(oriented), fill, oriented)

    def _impute(self, oriented: np.ndarray) -> np.ndarray:
        return self._impute_with(oriented, self.fill)

    def fit(self, pairs: pd.DataFrame, labels: np.ndarray) -> "PairScorer":
        unknown = [column for column in pairs.columns if column not in DIRECTIONS]
        if unknown:
            raise ValueError(f"columns without a declared direction: {unknown}")
        labels = check_labels(labels, len(pairs))
        self.columns = tuple(pairs.columns)
        oriented = self._orient(pairs)
        fold_state, model_state = seed_states(self.seed, 2)
        runs = pairs.index.get_level_values(RUN_LEVEL).to_numpy()
        unique_runs = np.unique(runs)
        folds = min(self.n_folds, unique_runs.size)
        if folds < 2:
            raise ValueError("training needs pairs from at least two runs")
        rng = np.random.default_rng(fold_state)
        has_positive = np.isin(unique_runs, np.unique(runs[labels]))
        ordered = np.concatenate([
            rng.permutation(unique_runs[has_positive]), rng.permutation(unique_runs[~has_positive])
        ])
        fold_of_run = dict(zip(ordered, np.arange(ordered.size) % folds))
        fold = np.array([fold_of_run[run] for run in runs])
        oof = np.empty(len(labels))
        fold_fills = []
        for index in range(folds):
            held = fold == index
            if labels[~held].all() or not labels[~held].any():
                raise ValueError("every training fold needs both coordinated and other pairs")
            fill = self._least_coordinated(oriented[~held])
            fold_fills.append(fill)
            model = self._model(model_state).fit(
                self._impute_with(oriented[~held], fill), labels[~held]
            )
            oof[held] = model.predict_proba(self._impute_with(oriented[held], fill))[:, 1]
        self.fill = self._least_coordinated(oriented)
        self._fitted = self._model(model_state).fit(self._impute(oriented), labels)
        self.oof_scores = oof
        self.folds = fold
        self.fold_fills = np.array(fold_fills)
        self.threshold = self._fit_threshold(pairs.index, oof, labels)
        return self

    def _fit_threshold(self, index: pd.MultiIndex, oof: np.ndarray, labels: np.ndarray) -> float:
        truth: dict[str, set[str]] = {str(run): set() for run in index.get_level_values(RUN_LEVEL)}
        for (run, first, second), positive in zip(index, labels):
            if positive:
                truth[str(run)].update((first, second))
        runs = _by_run(pd.Series(oof, index=index))
        candidates = np.unique(np.quantile(oof, np.linspace(0.0, 1.0, CANDIDATES)))
        best, best_f1 = float(candidates[-1]), -1.0
        for candidate in candidates[::-1]:
            f1 = _agent_f1(_propose(runs, float(candidate)), truth)
            if f1 > best_f1:
                best, best_f1 = float(candidate), f1
        return best

    def score(self, pairs: pd.DataFrame) -> np.ndarray:
        if pairs.empty:
            return np.empty(0)
        return self._fitted.predict_proba(self._impute(self._orient(pairs)))[:, 1]

    def propose(self, pairs: pd.DataFrame) -> dict[str, list[frozenset[str]]]:
        """Proposed groups per run for a frame indexed by ``(run_id, agent_a, agent_b)``."""
        return _propose(_by_run(pd.Series(self.score(pairs), index=pairs.index)), self.threshold)
