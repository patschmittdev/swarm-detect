"""Named evasion experiment: owner-silent credential relay against frozen detectors."""

import hashlib
import multiprocessing
import os
from concurrent.futures import ProcessPoolExecutor
from contextlib import ExitStack
from dataclasses import dataclass, field, replace
from pathlib import Path
from shutil import copyfile
from tempfile import TemporaryDirectory

import numpy as np
import pandas as pd
from sklearn.utils.parallel import _get_threadpool_controller

from swarmtrace.detect import RULE
from swarmtrace.eval.data import TierData, build_tier_data, load_runs
from swarmtrace.eval.harness import SplitResult, child_seed, family_data
from swarmtrace.eval.recorded import TableRecord, load_recorded, write_recorded, write_run_table
from swarmtrace.sim.runner import Condition, build_run
from swarmtrace.sim.sweep import condition_grid
from swarmtrace.trace.tiers import Tier

from .config import ReproduceConfig, RunJob, make_jobs
from .frozen import frozen_main_models
from .pipeline import _markdown, _rate, _simulate, _write_text
from .sharing_sweep import SharingSweepConfig, plan_sharing_sweep
from .verify import EVASION_HASH_START, EVASION_PATHS, SHARING_HASH_HEADER

MAIN_SEED = 20261120
NAMESPACE = 92
STYLES = ("standard", "owner_silent")
METHODS = (RULE, "logistic", "boosted")
MAX_DATA_BYTES = 20_000_000
SHARED_COLUMNS = tuple(f"shared_credential_logins_{suffix}"
                       for suffix in ("max", "top_k_mean", "n_above"))

PREDICTION = (
    "Prediction (written before the run): with the owner silent, the shared-credential feature "
    "is zero for the relay group, and the frozen detectors flag owner-silent relay runs at "
    "about the rate they flag control runs, because the only remaining shared logins come "
    "from benign sharing teams in the same run."
)
POST_HOC_NOTE = (
    "The breakdown by topology and size was added after an 18-run exploratory probe on other "
    "seeds, run after the prediction was committed and before this sweep; it is post hoc. "
    "The prediction text was not changed."
)
EXPANSION_NOTE = (
    "The aggregation family's other feature, access expansion after receipt, also falls under "
    "owner_silent, because it too reads logins."
)


def render_report_header() -> str:
    return (
        "# Named evasion: owner-silent credential relay against frozen detectors\n\n"
        f"{PREDICTION}\n\n"
    )


def _default_data_root() -> Path:
    """Resolve relative to the package's checkout, never the caller's working directory."""
    return Path(__file__).resolve().parents[3] / "data"


@dataclass(frozen=True)
class EvasionConfig:
    seed: int = MAIN_SEED
    workers: int = ReproduceConfig.workers
    n_bootstrap: int = ReproduceConfig.n_bootstrap
    conditions: tuple[Condition, ...] | None = None
    data_root: Path = field(default_factory=_default_data_root)

    def __post_init__(self) -> None:
        ReproduceConfig(seed=self.seed, workers=self.workers, n_bootstrap=self.n_bootstrap,
                        conditions=self.conditions)
        if self.conditions is not None and any(
            not isinstance(condition, Condition) or condition.offensive_group_size <= 0
            for condition in self.conditions
        ):
            raise ValueError("evasion conditions must be positive Condition instances")


def plan_evasion(config: EvasionConfig) -> tuple[RunJob, ...]:
    """Plan both styles in grid order and reject collisions with the real default experiments."""
    grid = (config.conditions if config.conditions is not None else
            tuple(cell for cell in condition_grid(n_ticks=160) if cell.offensive_group_size > 0))
    grid = tuple(replace(condition, relay_style="standard") for condition in grid)
    if len(set(grid)) != len(grid):
        raise ValueError("evasion conditions must not contain duplicates")
    seeds = tuple(child_seed(config.seed, NAMESPACE, 0, index) for index in range(len(grid)))
    reserved = {job.seed for job in make_jobs(ReproduceConfig()) if job.dataset == "main"}
    reserved.update(job.seed for plan in plan_sharing_sweep(SharingSweepConfig())
                    for job in plan.jobs)
    if len(set(seeds)) != len(seeds) or not set(seeds).isdisjoint(reserved):
        raise ValueError("evasion paired seeds collide with each other or a recorded experiment")
    directories = tuple(np.random.default_rng(seed).bytes(8).hex() for seed in seeds)
    if len(set(directories)) != len(directories):
        raise ValueError("evasion run directories collide")
    return tuple(RunJob(style, directory, seed, replace(condition, relay_style=style))
                 for style in STYLES
                 for condition, seed, directory in zip(grid, seeds, directories, strict=True))


def _round_trip(
    style: str, jobs: tuple[RunJob, ...], config: EvasionConfig, temporary: Path,
) -> TierData:
    by_directory = {job.directory: job for job in jobs if job.dataset == style}
    records = [replace(record, condition={
        **record.condition, "relay_style": style,
        "paired_seed": by_directory[record.trace_path.parent.name].seed,
    }) for record in load_runs(temporary / "raw" / style)]
    # Only full-trace measurements are needed; one final checkpoint avoids prefix work.
    data = build_tier_data(records, Tier.V1, workers=config.workers,
                           checkpoint_every=max(job.condition.n_ticks for job in jobs),
                           retain_traces=False)
    archive = temporary / "recorded" / style
    write_recorded(archive, data)
    return load_recorded(archive, Tier.V1)


def _scores(data: TierData, result: SplitResult) -> pd.DataFrame:
    matrix = family_data(data, "aggregation").runs
    if any(str(column).startswith(("label_", "condition_", "outcome_"))
           for column in matrix.columns):
        raise ValueError("label-side columns reached a detector matrix")
    return pd.DataFrame({method: result.fitted[method].score(matrix) for method in METHODS},
                        index=matrix.index)


def _lender_pair_counts(
    data: TierData, jobs: tuple[RunJob, ...],
) -> dict[str, tuple[int, int]]:
    """Count directed relay requirements from label-side builds, using extracted V1 pairs."""
    by_seed = {job.seed: job for job in jobs if job.dataset == "owner_silent"}
    counts = {}
    for run, record in data.records.items():
        job = by_seed[record.condition["paired_seed"]]
        setup = build_run(job.condition, job.seed)
        pairs = {(relay.owner, relay.recipient) for relay in setup.objective.relays}
        zero = 0
        for owner, borrower in sorted(pairs):
            key = (run, *sorted((owner, borrower)))
            # An inactive endpoint has no pair row and cannot share a successful login.
            value = (data.pairs.loc[key, "shared_credential_logins"]
                     if key in data.pairs.index else 0)
            zero += int(value == 0)
        counts[run] = (zero, len(pairs))
    return counts


def _combined_table(path: Path, datasets: dict[str, TierData]) -> None:
    frames, records = [], []
    for style in STYLES:
        data = datasets[style]
        # The style-qualified id encodes the (style, run_id) key without changing raw ids.
        frames.append(data.runs.rename(index=lambda run: f"{style}:{run}"))
        # Tag the source id so an all-digit hex id stays a string in the portable table.
        records.extend(TableRecord(f"{style}:{run}", record.positive,
                                   {**record.condition, "source_run_id": f"run:{run}"})
                       for run, record in data.records.items())
    runs = pd.concat(frames).sort_index()
    write_run_table(path, runs, records)


def _mean(values: pd.Series) -> float:
    return float(values.mean()) if len(values) else float("nan")


def _main_groups(main: TierData, result: SplitResult) -> tuple[list[str], ...]:
    training = set(result.fitting + result.calibration)
    test = [run for run in main.records if run not in training]
    positives = [run for run in test if main.records[run].positive]
    controls = [run for run in test if not main.records[run].positive]
    nonsharing = [run for run in controls
                  if main.records[run].condition["benign_sharing_teams"] == 0]
    return test, positives, controls, nonsharing


def _silent_shapes(data: TierData) -> list[tuple[str, str, list[str]]]:
    groups = [("0", name, []) for name in ("pairs and peer rings", "hubs of 3", "hubs of 5")]
    groups.append((">=1", "any shape", []))
    for run, record in data.records.items():
        condition = record.condition
        if condition["benign_sharing_teams"] > 0:
            index = 3
        elif condition["topology"] == "peer" or condition["offensive_group_size"] == 2:
            index = 0
        else:
            index = 1 if condition["offensive_group_size"] == 3 else 2
        groups[index][2].append(run)
    return groups


def _verdict(
    datasets: dict[str, TierData], scores: dict[str, pd.DataFrame], result: SplitResult,
    main: TierData, pair_counts: dict[str, tuple[int, int]],
) -> str:
    data = datasets["owner_silent"]
    if set(pair_counts) != set(data.records):
        raise ValueError("lender-borrower counts must cover every owner_silent run")
    zero = sum(count[0] for count in pair_counts.values())
    total = sum(count[1] for count in pair_counts.values())
    if zero != total:
        raise ValueError("owner_silent lender-borrower pairs have shared logins")
    hubs = [run for run, record in data.records.items()
            if record.condition["topology"] == "hub"
            and record.condition["offensive_group_size"] >= 3]
    shared_hubs = int(data.runs.loc[hubs, SHARED_COLUMNS[0]].gt(0).sum())
    thresholds = pd.Series({method: result.thresholds[method] for method in METHODS})
    silent_flags = scores["owner_silent"].gt(thresholds, axis="columns")
    main_flags = _scores(main, result).gt(thresholds, axis="columns")
    nonsharing = _main_groups(main, result)[3]
    groups = _silent_shapes(data)
    pairs, fives = groups[0][2], groups[2][2]

    def counts(frame: pd.DataFrame, ids: list[str], *, named: bool = False) -> str:
        return ", ".join(f"{int(frame.loc[ids, method].sum())} of {len(ids)}"
                         + (f" by {method}" if named else "") for method in METHODS)

    held_pairs = not silent_flags.loc[pairs].to_numpy().any()
    held_fives = not silent_flags.loc[fives].to_numpy().any()
    if held_pairs and held_fives:
        conclusion = "held for both pairs and peer rings and hubs of five."
    elif not held_pairs and not held_fives:
        conclusion = "did not hold for either pairs and peer rings or hubs of five."
    else:
        held, failed = (("pairs and peer rings", "hubs of five") if held_pairs
                        else ("hubs of five", "pairs and peer rings"))
        conclusion = f"held for {held} and did not hold for {failed}."
    return (
        "Outcome: the shared-credential feature is zero for every lender-borrower pair under "
        f"owner_silent ({zero} of {total} pairs). It is not zero for the relay group as a whole "
        "in hubs of three or more members, where two or more borrowers log in with the same "
        f"hub credential ({shared_hubs} runs). Owner-silent runs with no benign sharing team: "
        f"pairs and peer rings flagged {counts(silent_flags, pairs, named=True)}; "
        f"hubs of five flagged {counts(silent_flags, fives)}. "
        f"Main test controls with no sharing team: {counts(main_flags, nonsharing)}. "
        f"The prediction {conclusion}"
    )


def _report_tables(
    datasets: dict[str, TierData], scores: dict[str, pd.DataFrame],
    result: SplitResult, main: TierData,
) -> list[tuple[str, list[dict[str, object]]]]:
    _, positives, controls, nonsharing = _main_groups(main, result)
    calibration = [run for run in result.calibration if not main.records[run].positive]
    if not calibration:
        raise ValueError("main split has no calibration controls for the median comparison")
    main_scores = _scores(main, result)
    thresholds = pd.Series({method: result.thresholds[method] for method in METHODS})
    main_flags = main_scores.gt(thresholds, axis="columns")
    flags = {style: scores[style].gt(thresholds, axis="columns") for style in STYLES}
    # Across-style comparisons are explicit paired joins, after run-id/seed validation.
    standard = flags["standard"]
    silent = flags["owner_silent"].loc[standard.index]
    detection, medians = [], []
    for method in METHODS:
        detection.append({
            "detector": method,
            "main test standard relays": _rate(main_flags.loc[positives, method].tolist()),
            "main test controls": _rate(main_flags.loc[controls, method].tolist()),
            f"main test controls without a sharing team, k of {len(nonsharing)}": _rate(
                main_flags.loc[nonsharing, method].tolist(),
            ),
            "standard": _rate(standard[method].tolist()),
            "owner_silent": _rate(silent[method].tolist()),
            "standard only (paired)": _rate((standard[method] & ~silent[method]).tolist()),
            "owner_silent only (paired)": _rate((~standard[method] & silent[method]).tolist()),
            "threshold": float(result.thresholds[method]),
        })
        median = float(main_scores.loc[calibration, method].median())
        medians.append({
            "detector": method, "calibration controls": len(calibration),
            "median calibration control score": median,
            "owner_silent at or below median": _rate(
                scores["owner_silent"][method].le(median).tolist(),
            ),
        })
    by_shape = []
    for teams, shape, selected in _silent_shapes(datasets["owner_silent"]):
        for method in METHODS:
            by_shape.append({
                "benign sharing teams": teams, "shape": shape, "detector": method,
                "owner_silent flagged": _rate(silent.loc[selected, method].tolist()),
                f"main test controls with no sharing team, k of {len(nonsharing)}": _rate(
                    main_flags.loc[nonsharing, method].tolist(),
                ),
                f"all main test controls, k of {len(controls)}": _rate(
                    main_flags.loc[controls, method].tolist(),
                ),
            })
    features, completion, sharing, shapes, shape_features = [], [], [], [], []
    for style in STYLES:
        data = datasets[style]
        for column in SHARED_COLUMNS:
            features.append({"style": style, "feature": column, "mean": _mean(data.runs[column]),
                             "zero runs": _rate(data.runs[column].eq(0).tolist())})
        for size in (None, 2, 3, 5):
            selected = [run for run, record in data.records.items()
                        if size is None or record.condition["offensive_group_size"] == size]
            completion.append({
                "style": style, "offensive size": "all" if size is None else size,
                "completed": _rate([data.records[run].labels.objective_completed
                                    for run in selected]),
            })
        for teams in (False, True):
            selected = [run for run, record in data.records.items()
                        if (record.condition["benign_sharing_teams"] > 0) == teams]
            for method in METHODS:
                sharing.append({"style": style, "benign sharing teams": ">=1" if teams else "0",
                                "detector": method,
                                "flagged": _rate(flags[style].loc[selected, method].tolist())})
        for topology in ("hub", "peer"):
            for size in (2, 3, 5):
                selected = [run for run, record in data.records.items()
                            if record.condition["topology"] == topology
                            and record.condition["offensive_group_size"] == size]
                shapes.append({
                    "style": style, "topology": topology, "offensive size": size,
                    "positive runs": len(selected), "control runs": 0,
                    "mean shared_credential_logins_max": _mean(
                        data.runs.loc[selected, SHARED_COLUMNS[0]],
                    ),
                    **{method: _rate(flags[style].loc[selected, method].tolist())
                       for method in METHODS},
                })
                for population in ("all runs", "zero benign sharing teams"):
                    subset = [run for run in selected if population == "all runs"
                              or data.records[run].condition["benign_sharing_teams"] == 0]
                    shape_features.append({
                        "population": population, "style": style, "topology": topology,
                        "offensive size": size, "runs": len(subset),
                        **{f"mean {column}": _mean(data.runs.loc[subset, column])
                           for column in SHARED_COLUMNS},
                    })
    return [("Detection by detector", detection), ("Shared credential features", features),
            ("Objective completion", completion), ("Calibration control median", medians),
            ("Benign sharing teams", sharing), ("Topology and group size", shapes),
            ("Owner-silent detection by shape", by_shape),
            ("Shared credential features by topology and size", shape_features)]


def _write_report(
    path: Path, config: EvasionConfig, datasets: dict[str, TierData],
    scores: dict[str, pd.DataFrame], result: SplitResult, main: TierData,
    pair_counts: dict[str, tuple[int, int]], hashes: dict[str, str],
) -> None:
    training = set(result.fitting + result.calibration)
    test = tuple(run for run in main.records if run not in training)
    inventory = [{"seed": MAIN_SEED, "split": "by run", "subset": name,
                  "positive runs": sum(main.records[run].positive for run in ids),
                  "control runs": sum(not main.records[run].positive for run in ids)}
                 for name, ids in (("fitting", result.fitting), ("calibration", result.calibration),
                                   ("test", test))]
    inventory.extend({"seed": config.seed, "split": "paired evasion", "subset": style,
                      "positive runs": len(datasets[style].records), "control runs": 0}
                     for style in STYLES)
    text = render_report_header()
    text += _verdict(datasets, scores, result, main, pair_counts) + "\n\n"
    text += (f"Seed: {config.seed}; V1 aggregation; split: paired evasion against main by run.\n\n"
             "Simulation namespace: child_seed(seed, 92, 0, i), one replicate per positive "
             "condition in grid order, with the same seed for both styles.\n\n"
             "Main reconstruction: seed 20261120, test fraction 0.3, split key (0,), "
             "evaluation key (1, 0), with the harness's unchanged descendant keys.\n\n"
             f"Main reconstruction bootstrap resamples: {config.n_bootstrap}; "
             "reported rates use 95% Wilson intervals and strict score > threshold flags.\n\n")
    text += _markdown(inventory)
    count = len(datasets["standard"].records)
    test_positive = sum(main.records[run].positive for run in test)
    caption = (f"Seed: {config.seed}; split: paired evasion; each style: {count} positive, "
               f"0 control; main by-run test (seed {MAIN_SEED}): {test_positive} positive, "
               f"{len(test) - test_positive} control.\n\n")
    for title, rows in _report_tables(datasets, scores, result, main):
        text += f"\n## {title}\n\n" + caption
        if title == "Owner-silent detection by shape":
            text += POST_HOC_NOTE + "\n\n"
        text += _markdown(rows)
    notes = (
        "owner_silent applies to offensive groups only; benign sharing teams keep standard "
        "behaviour because a benign team would have no reason to hide.",
        "Models and thresholds are frozen from the reconstructed main by-run split, "
        "with no refit or recalibration on either paired dataset.",
        "Detectors never see label_ or condition_ columns.",
        "Objective completion shows whether the evasion broke the offence.",
        "In hubs with at least three members, two borrowers can share the hub's credential.",
        EXPANSION_NOTE,
        "Lender-borrower counts use directed RelayRequirement owner/recipient pairs per run; "
        "their V1 pair-feature counts are kept in memory for the verdict only.",
        "The combined table uses style:run_id as its unique index, and joins use (style, run_id).",
        "condition_source_run_id stores `run:<original-id>` to keep hexadecimal ids as strings, "
        "and condition_paired_seed records the shared simulation seed.",
        "Raw samples are the first peer group of size 3 in grid order, one run per style "
        "with the same seed; a subgrid without that condition records no raw samples.",
        "An empty subgroup has 0 of 0 and an undefined interval.",
    )
    text += "\n## Table notes\n\n" + "\n".join(f"- {note}" for note in notes) + "\n"
    text += "\n## Recorded V1 run table\n\n" + EVASION_HASH_START + "\n"
    text += SHARING_HASH_HEADER + "\n"
    text += "".join(f"{name} | {digest}\n" for name, digest in hashes.items()) + "```\n"
    _write_text(path, text)


def run_evasion(out: str | Path, config: EvasionConfig) -> Path:
    """Publish a paired V1 run table, report, and at most two raw samples to a fresh directory."""
    out = Path(out)
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        raise ValueError(f"output already contains artifacts: {out}; choose a fresh directory")
    jobs = plan_evasion(config)
    names = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")
    previous = {name: os.environ.get(name) for name in names}
    try:
        os.environ.update(dict.fromkeys(names, "1"))
        with ExitStack() as stack:
            stack.enter_context(_get_threadpool_controller().limit(limits=1))
            main_root = Path(config.data_root) / "dataset" / "main"
            main = load_recorded(main_root, Tier.V1)
            result = frozen_main_models(main_root, MAIN_SEED, n_bootstrap=config.n_bootstrap)
            if any(method not in result.fitted or method not in result.thresholds
                   for method in METHODS):
                raise ValueError("recorded main data could not supply all frozen detectors")
            out.mkdir(parents=True, exist_ok=True)
            temporary = Path(stack.enter_context(TemporaryDirectory(
                prefix="swarmtrace-evasion-", dir=out,
            ))).resolve()
            publish = temporary / "publish"
            tasks = [(job, temporary / "raw") for job in jobs]
            if config.workers > 1:
                with ProcessPoolExecutor(max_workers=config.workers,
                                         mp_context=multiprocessing.get_context("spawn")) as pool:
                    list(pool.map(_simulate, tasks))
            else:
                for task in tasks:
                    _simulate(task)
            datasets = {style: _round_trip(style, jobs, config, temporary) for style in STYLES}
            standard, silent = (datasets[style] for style in STYLES)
            if set(standard.records) != set(silent.records) or any(
                record.condition["paired_seed"] != silent.records[run].condition["paired_seed"]
                for run, record in standard.records.items()
            ):
                raise ValueError("paired styles have different run ids or seeds")
            scores = {style: _scores(datasets[style], result) for style in STYLES}
            pair_counts = _lender_pair_counts(silent, jobs)
            table = publish / EVASION_PATHS[0]
            _combined_table(table, datasets)
            sample = next((job for job in jobs if job.dataset == "standard"
                           and job.condition.topology == "peer"
                           and job.condition.offensive_group_size == 3), None)
            if sample is not None:
                for style in STYLES:
                    destination = publish / "evasion" / "raw" / style / sample.directory
                    destination.mkdir(parents=True)
                    for name in ("trace.jsonl", "labels.json", "manifest.json"):
                        copyfile(temporary / "raw" / style / sample.directory / name,
                                 destination / name)
            artifacts = [table, *sorted(
                (path for path in (publish / "evasion/raw").rglob("*") if path.is_file()),
                key=lambda path: path.relative_to(publish).as_posix(),
            )]
            hashes = {path.relative_to(publish).as_posix(): hashlib.sha256(
                path.read_bytes()).hexdigest() for path in artifacts}
            _write_report(publish / "evasion.md", config, datasets, scores, result, main,
                          pair_counts, hashes)
            # Budget the release after replacing this experiment, even when out is elsewhere.
            data_root = Path(config.data_root).resolve()
            existing = sum(path.stat().st_size for path in data_root.rglob("*") if path.is_file()
                           and not path.resolve().is_relative_to(temporary)
                           and not path.is_relative_to(data_root / "evasion")
                           and path != data_root / "evasion.md")
            added = sum(path.stat().st_size for path in publish.rglob("*") if path.is_file())
            if existing + added >= MAX_DATA_BYTES:
                raise ValueError("evasion would exceed the <20 MB total data budget: "
                                 f"{existing + added} bytes")
            (publish / "evasion").replace(out / "evasion")
            (publish / "evasion.md").replace(out / "evasion.md")
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
    return out / "evasion.md"
