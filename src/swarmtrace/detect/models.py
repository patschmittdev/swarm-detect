import math

import numpy as np
import pandas as pd
from sklearn.base import ClassifierMixin
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline, make_pipeline
from sklearn.preprocessing import StandardScaler

from .threshold import conformal_threshold

LOGISTIC_MARGIN = "logistic_margin"
RUN_MODELS = ("logistic", "boosted", LOGISTIC_MARGIN)
RULE = "rule"
"""No-parameter baseline: a run's score is its number of agent pairs with a shared-credential login."""
RULE_COLUMN = "shared_credential_logins_n_above"
"""Pairs whose ``shared_credential_logins`` is above its threshold of 0, so pairs with at least one."""
SCOPE_RULE = "scope_rule"
"""No-parameter scope baseline: a run's score is one scope column, unchanged."""
SCOPE_RULE_COLUMNS = ("out_of_scope_reads_borrowed_max", "borrowed_session_breadth_max")
"""The first of these present is scored. The out-of-scope count exists only at context C2, so
``scope_rule`` scores it at C2 and the breadth maximum at C0 and C1."""
SCOPE_BREADTH_RULE = "scope_breadth_rule"
"""Use both C2 maxima to rank runs with the same positive out-of-scope count by breadth."""
FILES_RULE = "files_rule"
FILES_RULE_COLUMN = "distinct_files_read_max"
"""Diagnostic only, outside every feature family; explicitly selected for ``files_rule``."""
COMPONENT_RULE = "component_rule"
COMPONENT_COLUMN = "sharing_component_fraction"
"""The run's component score, computed from the audit-log pair features."""
SHARING_LOGISTIC = "sharing_logistic"
SCOPE_LOGISTIC = "scope_logistic"
_LOGISTIC_GATES = {SHARING_LOGISTIC: RULE_COLUMN, SCOPE_LOGISTIC: SCOPE_RULE_COLUMNS[0]}
DETECTOR_MODELS = (
    *RUN_MODELS, RULE, SCOPE_RULE, FILES_RULE, SCOPE_BREADTH_RULE, COMPONENT_RULE, *_LOGISTIC_GATES,
)
_SINGLE_RULE_COLUMNS = {
    RULE: RULE_COLUMN,
    FILES_RULE: FILES_RULE_COLUMN,
    COMPONENT_RULE: COMPONENT_COLUMN,
}
VOLUME_COLUMNS = (
    "n_agents",
    "n_events",
    "events_per_agent_mean",
    "events_per_agent_max",
    "events_per_agent_std",
)


def seed_states(seed: int, count: int) -> list[int]:
    return [int(child.generate_state(1)[0]) for child in np.random.SeedSequence(seed).spawn(count)]


def volume_features(agents: pd.DataFrame, run_id: str) -> pd.DataFrame:
    """Volume-only run features from an ``agent_features`` frame: agent and event counts."""
    counts = agents["n_events"].to_numpy(dtype=float)
    if counts.size:
        values = [counts.size, counts.sum(), counts.mean(), counts.max(), counts.std()]
    else:
        values = [0.0] * len(VOLUME_COLUMNS)
    return pd.DataFrame(
        [[float(value) for value in values]],
        columns=list(VOLUME_COLUMNS),
        index=pd.Index([run_id], name="run_id"),
    )


def build_model(model: str, random_state: int) -> Pipeline | ClassifierMixin:
    if model in ("logistic", LOGISTIC_MARGIN):
        return make_pipeline(
            SimpleImputer(strategy="median", add_indicator=True),
            StandardScaler(),
            LogisticRegression(max_iter=1000),
        )
    if model == "boosted":
        return HistGradientBoostingClassifier(early_stopping=False, random_state=random_state)
    raise ValueError(f"Unknown run model {model!r}; expected one of {RUN_MODELS}")


def check_model(model: str) -> None:
    if model not in DETECTOR_MODELS:
        raise ValueError(f"Unknown run model {model!r}; expected one of {DETECTOR_MODELS}")


class _Rule:
    """A rule baseline: one column's value, unchanged. Nothing is learned."""

    def __init__(self, columns: tuple[str, ...], column: str) -> None:
        self.index = columns.index(column)

    def predict(self, values: np.ndarray) -> np.ndarray:
        return values[:, self.index].copy()


def _rule(model: str, columns: tuple[str, ...]) -> _Rule:
    if model in _SINGLE_RULE_COLUMNS:
        column = _SINGLE_RULE_COLUMNS[model]
        if column not in columns:
            raise ValueError(f"the {model!r} detector needs the {column!r} column")
        return _Rule(columns, column)
    column = next((name for name in SCOPE_RULE_COLUMNS if name in columns), None)
    if column is None:
        raise ValueError(f"the {SCOPE_RULE!r} detector needs one of {SCOPE_RULE_COLUMNS}")
    return _Rule(columns, column)


class _ScopeBreadthRule:
    """Score a positive out-of-scope count m as m + b/(1+b), using run-wide breadth b.

    The two maxima can come from different pairs. A missing maximum contributes zero.
    """

    def __init__(self, columns: tuple[str, ...]) -> None:
        if any(columns.count(name) != 1 for name in SCOPE_RULE_COLUMNS):
            raise ValueError(f"{SCOPE_BREADTH_RULE!r} needs one copy of each C2 column "
                             f"{SCOPE_RULE_COLUMNS}")
        self.indices = [columns.index(name) for name in SCOPE_RULE_COLUMNS]

    def predict(self, values: np.ndarray) -> np.ndarray:
        counts = values[:, self.indices]
        counts = np.where(np.isnan(counts), 0.0, counts)
        valid = np.isfinite(counts) & (counts >= 0) & (counts == np.floor(counts))
        if not valid.all():
            raise ValueError(f"{SCOPE_BREADTH_RULE!r} needs non-negative integer counts or NaN")
        outside, breadth = counts.T
        score = outside + breadth / (1.0 + breadth)
        # At large counts, rounding can otherwise turn the fraction into a whole extra read.
        upper = np.nextafter(outside + 1.0, outside)
        return np.where(outside > 0, np.minimum(score, upper), 0.0)


def fit_model(
    model: str, seed: int, features: pd.DataFrame, labels: np.ndarray
) -> "_Fitted | _Rule | _ScopeBreadthRule | _ConditionalLogistic":
    if model == SCOPE_BREADTH_RULE:
        return _ScopeBreadthRule(tuple(features.columns))
    if model in _SINGLE_RULE_COLUMNS or model == SCOPE_RULE:
        return _rule(model, tuple(features.columns))
    (model_state,) = seed_states(seed, 1)
    if model in _LOGISTIC_GATES:
        return _ConditionalLogistic(_LOGISTIC_GATES[model], model_state, features, labels)
    fitted = _LogisticMargin if model == LOGISTIC_MARGIN else _Fitted
    return fitted(model, model_state, features.to_numpy(dtype=float), labels)


class _Fitted:
    """A model fitted on the columns that have at least one observed value in its training rows."""

    def __init__(self, model: str, random_state: int, values: np.ndarray, labels: np.ndarray) -> None:
        self.observed = ~np.isnan(values).all(axis=0)
        self.model = build_model(model, random_state).fit(values[:, self.observed], labels)

    def predict(self, values: np.ndarray) -> np.ndarray:
        return self.model.predict_proba(values[:, self.observed])[:, 1]

    def margin(self, values: np.ndarray) -> np.ndarray:
        return self.model.decision_function(values[:, self.observed])


class _LogisticMargin(_Fitted):
    """Use the fitted logistic decision function for scoring and calibration."""

    def predict(self, values: np.ndarray) -> np.ndarray:
        return self.margin(values)


class _ConditionalLogistic:
    """Fit logistic regression within the subset with an observed positive evidence count."""

    def __init__(
        self, gate: str, random_state: int, features: pd.DataFrame, labels: np.ndarray,
    ) -> None:
        columns = tuple(features.columns)
        if columns.count(gate) != 1:
            raise ValueError(f"conditional logistic needs exactly one {gate!r} column")
        self.index = columns.index(gate)
        eligible = features[gate].to_numpy(dtype=float) > 0
        eligible_labels = labels[eligible]
        positives = int(eligible_labels.sum())
        self.fitted = None
        if 0 < positives < eligible_labels.size:
            values = features.loc[eligible].to_numpy(dtype=float)
            self.fitted = _Fitted("logistic", random_state, values, eligible_labels)
        self.smoothed_rate = (positives + 1) / (eligible_labels.size + 2)

    def predict(self, values: np.ndarray) -> np.ndarray:
        eligible = values[:, self.index] > 0
        scores = np.zeros(len(values), dtype=float)
        if eligible.any():
            scores[eligible] = (self.smoothed_rate if self.fitted is None
                                else self.fitted.predict(values[eligible]))
        return scores


def check_labels(labels: np.ndarray, rows: int, *, model: str | None = None) -> np.ndarray:
    labels = np.asarray(labels, dtype=bool)
    if labels.shape != (rows,):
        raise ValueError(f"expected {rows} labels, got shape {labels.shape}")
    if model in _LOGISTIC_GATES:
        if rows == 0:
            raise ValueError("conditional logistic fitting needs at least one row")
    elif labels.all() or not labels.any():
        raise ValueError("training labels must contain both classes")
    return labels


class RunDetector:
    """Run-level detector: a model fitted on a fitting set, thresholded on a calibration set.

    ``fit`` fits imputation, scaling and the classifier on the fitting runs only. For ``RULE``
    it fits nothing: the score is the ``RULE_COLUMN`` count and ``seed`` is unused; likewise for
    ``SCOPE_RULE``, whose score is the first ``SCOPE_RULE_COLUMNS`` column present. ``calibrate``
    scores the calibration control runs with that same model and sets the split-conformal
    threshold for target false-positive rate ``max_fpr``.

    ``logistic`` scores and calibrates positive-class probabilities. The opt-in
    ``logistic_margin`` uses the same fit and scores and calibrates positive-class log odds.

    ``FILES_RULE`` likewise scores only ``FILES_RULE_COLUMN``, which must be explicitly
    supplied from the run table's diagnostics rather than from a feature family.
    ``COMPONENT_RULE`` takes the precomputed component score in ``COMPONENT_COLUMN``.
    ``SCOPE_BREADTH_RULE`` requires both ``SCOPE_RULE_COLUMNS`` at C2 and breaks ties
    between positive out-of-scope counts by borrowed-session breadth.

    ``SHARING_LOGISTIC`` and ``SCOPE_LOGISTIC`` score zero without shared-login evidence
    and borrowed out-of-scope read evidence, respectively. They fit logistic regression
    on fitting rows with that evidence. When fewer than two classes occur among those
    rows, their score given evidence is (positive rows + 1) / (eligible rows + 2).
    """

    def __init__(self, model: str, seed: int, max_fpr: float = 0.05) -> None:
        check_model(model)
        self.model = model
        self.seed = seed
        self.max_fpr = max_fpr
        self.columns: tuple[str, ...] = ()
        self.threshold = float("nan")
        self.calibration_scores = np.empty(0)

    def fit(self, features: pd.DataFrame, labels: np.ndarray) -> "RunDetector":
        labels = check_labels(labels, len(features), model=self.model)
        self._fitted = fit_model(self.model, self.seed, features, labels)
        self.columns = tuple(features.columns)
        self.threshold = float("nan")
        self.calibration_scores = np.empty(0)
        return self

    def calibrate(self, features: pd.DataFrame, labels: np.ndarray) -> "RunDetector":
        labels = np.asarray(labels, dtype=bool)
        if labels.shape != (len(features),):
            raise ValueError(f"expected {len(features)} labels, got shape {labels.shape}")
        self.calibration_scores = self.score(features)[~labels]
        self.threshold = conformal_threshold(self.calibration_scores, self.max_fpr)
        return self

    def _values(self, features: pd.DataFrame) -> np.ndarray:
        if tuple(features.columns) != self.columns:
            raise ValueError(f"expected columns {self.columns}, got {tuple(features.columns)}")
        return features.to_numpy(dtype=float)

    def score(self, features: pd.DataFrame) -> np.ndarray:
        values = self._values(features)
        return self._fitted.predict(values)

    def score_margin(self, features: pd.DataFrame) -> np.ndarray:
        """Return positive-class log odds from this ordinary logistic fit.

        The fitted imputer, missingness indicators, scaler and classifier are reused.
        This read leaves the detector's existing calibration in its original score units.
        """
        if self.model not in ("logistic", LOGISTIC_MARGIN):
            raise ValueError("score_margin requires an ordinary logistic detector")
        if not hasattr(self, "_fitted"):
            raise ValueError("fit the logistic detector before scoring margins")
        return self._fitted.margin(self._values(features))

    def flag(self, features: pd.DataFrame) -> np.ndarray:
        if math.isnan(self.threshold):
            raise ValueError("calibrate the detector before flagging")
        return self.score(features) > self.threshold

