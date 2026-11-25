"""The main models and thresholds are reused unchanged across experiments.

A deterministic refit from the recorded main feature archive, at V1, aggregation family, on the
by-run split, through ``evaluate_split`` with the seeds ``reproduce`` uses. Nothing is pickled:
two calls give identical models and thresholds, and the result's rows are the recorded
by-run V1 aggregation rows.
"""

from collections.abc import Callable, Sequence
from pathlib import Path

from swarmtrace.contain import DetectorController
from swarmtrace.detect import RULE
from swarmtrace.eval.harness import (
    ATTRIBUTION,
    ONLINE_SUFFIX,
    EvalConfig,
    SplitResult,
    child_seed,
    evaluate_split,
)
from swarmtrace.eval.recorded import load_recorded, recorded_root
from swarmtrace.eval.splits import split_by_run
from swarmtrace.trace.schema import TraceEvent
from swarmtrace.trace.tiers import Tier

from .config import ReproduceConfig

FROZEN_TIER = Tier.V1
FROZEN_FAMILY = "aggregation"
TEST_FRACTION = 0.3
"""The by-run split's test fraction in ``reproduce``."""
CONTAINMENT_DETECTORS = ("logistic", "boosted", RULE)


def frozen_main_models(
    data_root: Path, seed: int, *, n_bootstrap: int | None = None,
) -> SplitResult:
    """Refit the by-run V1 aggregation models from ``data_root`` (a reproduce output directory,
    such as ``data``, or the ``dataset/main`` archive itself).

    Keep the archive's checkpoint cadence; ``n_bootstrap`` defaults to the reproduction count.
    """
    data = load_recorded(recorded_root(data_root), FROZEN_TIER)
    ids = sorted(data.records)
    split = split_by_run(ids, [data.records[run].positive for run in ids], TEST_FRACTION,
                         child_seed(seed, 0))
    default_bootstrap = ReproduceConfig(seed=seed).n_bootstrap
    config = EvalConfig(tiers=(FROZEN_TIER,), seed=seed, test_fraction=TEST_FRACTION,
                        families=(FROZEN_FAMILY,),
                        n_bootstrap=default_bootstrap if n_bootstrap is None else n_bootstrap,
                        checkpoint_every=data.checkpoint_every)
    return evaluate_split(data, split, config, child_seed(seed, 1, 0), family=FROZEN_FAMILY)


def detector_controller(models: SplitResult, method: str, lever: str) -> DetectorController:
    """A V1 ``DetectorController`` from the frozen online detector ``method`` and, for a fitted
    detector, the frozen pair scorer; the rule uses the shared-credential pair attribution."""
    if method not in CONTAINMENT_DETECTORS:
        raise ValueError(f"unknown containment detector {method!r}; "
                         f"expected one of {CONTAINMENT_DETECTORS}")
    online = models.fitted[f"{method}{ONLINE_SUFFIX}"]
    scorer = models.fitted[ATTRIBUTION]
    return DetectorController(online, RULE if method == RULE else scorer, lever,
                              online.columns, scorer.columns, tier=FROZEN_TIER)


def live_first_flag_tick(
    make_controller: Callable[[], DetectorController], events: Sequence[TraceEvent],
    n_ticks: int,
) -> int | None:
    """First-flag tick of a fresh controller replayed over an uncontained twin's events.

    Every tick from 0 to ``n_ticks - 1`` is replayed, empty ticks included, so the flag lands on
    the controller's own live grid (7, 15, ...). Containment arms must take first-flag ticks
    from this replay, never from offline first crossings: the offline grid adds a checkpoint at
    the run's last event, so it can flag up to ``every - 1`` ticks earlier than any controller.
    The events must already be projected to the controller's tier.
    """
    if type(n_ticks) is not int or n_ticks < 1:
        raise ValueError("n_ticks must be a positive integer")
    controller = make_controller()
    by_tick: dict[int, list[TraceEvent]] = {}
    for event in events:
        by_tick.setdefault(event.tick, []).append(event)
    for tick in range(n_ticks):
        controller.observe(tick, tuple(by_tick.get(tick, ())))
        if controller.first_flag_tick is not None:
            return controller.first_flag_tick
    return None
