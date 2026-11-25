import math

import numpy as np


def conformal_threshold(control_scores: np.ndarray, alpha: float) -> float:
    """Split-conformal threshold from calibration control scores.

    With n scores the threshold is the ceil((n + 1) * (1 - alpha))-th smallest, or +inf when that
    index exceeds n (too few calibration controls for the target; the detector never fires). A
    score flags when it is strictly greater than the threshold.
    """
    if not 0.0 <= alpha <= 1.0:
        raise ValueError(f"alpha must be within [0, 1], got {alpha}")
    scores = np.sort(np.asarray(control_scores, dtype=float))
    rank = math.ceil((scores.size + 1) * (1.0 - alpha))
    if rank > scores.size:
        return math.inf
    return float(scores[max(rank, 1) - 1])
