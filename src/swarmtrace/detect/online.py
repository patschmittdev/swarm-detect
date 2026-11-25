import math
from collections.abc import Callable, Iterable

import numpy as np
import pandas as pd

from .models import check_labels, check_model, fit_model
from .threshold import conformal_threshold

CHECKPOINT_EVERY = 8
RUN_LEVEL = "run_id"
TICK_LEVEL = "tick"


def checkpoints(last_tick: int, every: int = CHECKPOINT_EVERY) -> tuple[int, ...]:
    """Online scoring ticks: the end of every ``every``-tick block before ``last_tick``, then
    ``last_tick`` itself."""
    if last_tick < 0 or every < 1:
        raise ValueError(f"need last_tick >= 0 and every >= 1, got {last_tick}, {every}")
    return (*range(every - 1, last_tick, every), last_tick)


def first_detection_tick(
    score_at: Callable[[int], float], ticks: Iterable[int], threshold: float
) -> int | None:
    """First tick, in the order given, whose prefix score is strictly above ``threshold``.

    ``score_at`` is called lazily and not after the first crossing.
    """
    for tick in ticks:
        if score_at(tick) > threshold:
            return tick
    return None


class OnlineDetector:
    """Online detector fitted on prefix features, one row per (run, checkpoint).

    ``fit`` takes the fitting runs' prefix rows, indexed by ``(run_id, tick)``, with each run's
    label repeated on its rows. A run's online score is its maximum over checkpoints, and
    ``calibrate`` sets the split-conformal threshold for target rate ``max_fpr`` from those
    maxima over the calibration control runs, scored by the same model. For ``RULE`` the score
    is the ``RULE_COLUMN`` count on each prefix, with nothing fitted.
    """

    def __init__(self, model: str, seed: int, max_fpr: float = 0.05) -> None:
        check_model(model)
        self.model = model
        self.seed = seed
        self.max_fpr = max_fpr
        self.columns: tuple[str, ...] = ()
        self.threshold = float("nan")
        self.calibration_scores = np.empty(0)

    @staticmethod
    def _run_labels(prefixes: pd.DataFrame, labels: np.ndarray) -> pd.Series:
        labels = np.asarray(labels, dtype=bool)
        if labels.shape != (len(prefixes),):
            raise ValueError(f"expected {len(prefixes)} labels, got shape {labels.shape}")
        rows_run = prefixes.index.get_level_values(RUN_LEVEL).to_numpy()
        by_run = pd.Series(labels, index=rows_run).groupby(level=0, sort=True)
        if (by_run.nunique() > 1).any():
            raise ValueError("every prefix row of a run must carry the run's label")
        return by_run.first()

    def fit(self, prefixes: pd.DataFrame, labels: np.ndarray) -> "OnlineDetector":
        labels = check_labels(labels, len(prefixes), model=self.model)
        self._run_labels(prefixes, labels)
        self._fitted = fit_model(self.model, self.seed, prefixes, labels)
        self.columns = tuple(prefixes.columns)
        self.threshold = float("nan")
        self.calibration_scores = np.empty(0)
        return self

    def calibrate(self, prefixes: pd.DataFrame, labels: np.ndarray) -> "OnlineDetector":
        run_labels = self._run_labels(prefixes, labels)
        run_max = self.run_scores(prefixes)
        controls = ~run_labels.reindex(run_max.index).to_numpy(dtype=bool)
        self.calibration_scores = run_max.to_numpy()[controls]
        self.threshold = conformal_threshold(self.calibration_scores, self.max_fpr)
        return self

    def score(self, prefixes: pd.DataFrame) -> np.ndarray:
        if tuple(prefixes.columns) != self.columns:
            raise ValueError(f"expected columns {self.columns}, got {tuple(prefixes.columns)}")
        return self._fitted.predict(prefixes.to_numpy(dtype=float))

    def run_scores(self, prefixes: pd.DataFrame) -> pd.Series:
        """Each run's maximum score over its checkpoints, indexed by run id."""
        rows_run = prefixes.index.get_level_values(RUN_LEVEL).to_numpy()
        return pd.Series(self.score(prefixes), index=rows_run).groupby(level=0, sort=True).max()

    def first_crossings(self, prefixes: pd.DataFrame) -> dict[str, int | None]:
        """First checkpoint tick per run whose score is strictly above the threshold."""
        if math.isnan(self.threshold):
            raise ValueError("calibrate the detector before detecting")
        scores = pd.Series(self.score(prefixes), index=prefixes.index).sort_index()
        crossings: dict[str, int | None] = {}
        for run, series in scores.groupby(level=RUN_LEVEL, sort=True):
            above = series[series > self.threshold]
            ticks = above.index.get_level_values(TICK_LEVEL)
            crossings[str(run)] = int(ticks.min()) if len(above) else None
        return crossings
