"""Fit a linear assignment score using one outcome per complete run."""

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

TEMPERATURE = 0.25


def _sigmoid(values):
    return np.exp(-np.logaddexp(0., -values))


def _loss(params, features, labels, sizes, starts):
    weights, intercept = params[:-1], params[-1]
    margins = features @ weights + intercept
    largest = np.maximum.reduceat(margins, starts)
    exponentials = np.exp((margins - np.repeat(largest, sizes)) / TEMPERATURE)
    totals = np.add.reduceat(exponentials, starts)
    # A smooth maximum weights every run once and is invariant to duplicating its whole bag.
    pooled = largest + TEMPERATURE * np.log(totals / sizes)
    residual = _sigmoid(pooled) - labels
    shares = exponentials / np.repeat(totals, sizes)
    loss = np.logaddexp(0, (1 - 2 * labels) * pooled).sum() + 0.5 * (weights @ weights)
    gradient = features.T @ (np.repeat(residual, sizes) * shares) + weights
    return loss, np.append(gradient, residual.sum())


def _fit_weights(features, labels, sizes, starts):
    """Backtracking gradient descent on the small, fixed-dimensional fitting problem."""
    params = np.zeros(features.shape[1] + 1)
    loss, grad = _loss(params, features, labels, sizes, starts)
    step = 1. / len(labels)
    for _ in range(5000):
        if np.max(np.abs(grad)) <= 1e-6:
            return params
        step *= 1.5
        slope = grad @ grad
        for _ in range(50):
            trial = params - step * grad
            value, derivative = _loss(trial, features, labels, sizes, starts)
            if value <= loss - 0.0001 * step * slope:
                break
            step *= 0.5
        else:
            raise ValueError("assignment fit could not find a descending step")
        params, loss, grad = trial, value, derivative
    raise ValueError("assignment fit did not converge")


@dataclass(frozen=True)
class AssignmentLogistic:
    center: np.ndarray
    scale: np.ndarray
    weights: np.ndarray
    intercept: float

    @classmethod
    def from_parameters(cls, model: dict, n_features: int) -> "AssignmentLogistic":
        try:
            arrays = [np.asarray(model[key], dtype=float) for key in ("center", "scale", "weights")]
            intercept = float(model["intercept"])
        except (TypeError, KeyError, ValueError) as error:
            raise ValueError("invalid assignment model parameters") from error
        if (not all(a.shape == (n_features,) and np.isfinite(a).all() for a in arrays)
                or (arrays[1] <= 0).any() or not np.isfinite(intercept)):
            raise ValueError("invalid assignment model scales, weights or intercept")
        return cls(*arrays, intercept)

    @classmethod
    def fit(cls, bags: Sequence[np.ndarray], labels: Sequence[bool]) -> "AssignmentLogistic":
        y = np.asarray(labels)
        if not len(bags) or y.shape != (len(bags),) or y.dtype != np.bool_:
            raise ValueError("each run needs one boolean label")
        rows = [np.asarray(bag, dtype=float) for bag in bags]
        if (any(b.ndim != 2 or not np.isfinite(b).all() for b in rows)
                or len({b.shape[1] for b in rows}) != 1 or rows[0].shape[1] == 0):
            raise ValueError("assignment bags need finite observations and matching columns")
        lengths = np.array([len(b) for b in rows])
        labels = y[lengths > 0].astype(float)
        if len(np.unique(labels)) != 2:
            raise ValueError("fitting needs an exercised assignment in both classes")
        sizes = lengths[lengths > 0]
        observations = np.concatenate(rows)
        row_weights = np.repeat(1 / sizes, sizes)
        center = np.average(observations, axis=0, weights=row_weights)
        variance = np.average((observations - center) ** 2, axis=0, weights=row_weights)
        scale = np.where(variance > 1e-24, np.sqrt(variance), 1.)
        starts = np.r_[0, np.cumsum(sizes)[:-1]]
        params = _fit_weights((observations - center) / scale, labels, sizes, starts)
        return cls(center, scale, params[:-1], float(params[-1]))

    def _contributions(self, bag: np.ndarray) -> np.ndarray:
        rows = np.asarray(bag, dtype=float)
        if rows.ndim != 2 or rows.shape[1] != len(self.weights) or not np.isfinite(rows).all():
            raise ValueError("assignment rows must match the finite fitted input columns")
        return (rows - self.center) / self.scale * self.weights

    def assignment_scores(self, bag: np.ndarray) -> np.ndarray:
        return _sigmoid(self._contributions(bag).sum(axis=1) + self.intercept)

    def pooled_evidence_score(self, bag: np.ndarray) -> float:
        """Combine each coefficient's strongest contribution across grants at fixed weights."""
        contributions = self._contributions(bag)
        if not len(contributions):
            return 0.
        return float(_sigmoid(contributions.max(axis=0).sum() + self.intercept))

    def score(self, bag: np.ndarray) -> float:
        """Largest score for a real, exercised grant. An empty bag supplies no alert."""
        return float(self.assignment_scores(bag).max(initial=0.))
