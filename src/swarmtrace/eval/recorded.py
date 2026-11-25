"""Portable, deterministic feature archives. All label joins stay on the eval side."""

import gzip
import io
import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Protocol

import numpy as np
import pandas as pd

from swarmtrace.detect import FILES_RULE_COLUMN
from swarmtrace.trace.io import AgentLabel, Labels
from swarmtrace.trace.tiers import Tier

from .data import BENIGN_TEAM, SHARED_LOGINS, RunRecord, TierData, shared_login_pairs

FORMAT = "swarmtrace-features-v1"
TABLES = ("runs", "volume", "pairs", "prefix_runs", "prefix_volume")


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
                    + "\n", encoding="utf-8", newline="\n")


def write_gzip(path: Path, content: bytes) -> None:
    """No timestamp, filename, platform-dependent text conversion, or temporary path in bytes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as target:
        with gzip.GzipFile(filename="", fileobj=target, mode="wb", mtime=0) as stream:
            stream.write(content)


def is_recorded(root: str | Path) -> bool:
    path = Path(root) / "manifest.json"
    return path.is_file() and json.loads(path.read_text(encoding="utf-8")).get("format") == FORMAT


def recorded_root(root: str | Path) -> Path:
    """Accept either a feature archive or a complete reproduce output directory."""
    root = Path(root)
    return root / "dataset" / "main" if (root / "experiment.json").is_file() else root


def write_recorded(root: str | Path, data: TierData) -> None:
    """Write full/prefix/pair matrices and label-side metadata, retaining numeric dtypes."""
    root = Path(root)
    manifest_path = root / "manifest.json"
    records = [
        {"run_id": record.run_id, "labels": asdict(record.labels),
         "condition": dict(record.condition)}
        for record in data.records.values()
    ]
    manifest = {"format": FORMAT, "records": records, "tiers": {}}
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest["format"] != FORMAT or manifest["records"] != records:
            raise ValueError("recorded tiers must describe exactly the same runs")
    schemas = {}
    for name in TABLES:
        frame = getattr(data, name).copy()
        if name == "pairs":
            frame["label_pair"] = data.pair_labels.astype(int)
        if name == "runs":
            frame["label_positive"] = [data.records[run].positive for run in frame.index]
            factors = sorted({key for record in data.records.values() for key in record.condition})
            for factor in factors:
                frame[f"condition_{factor}"] = [data.records[run].condition.get(factor)
                                                 for run in frame.index]
        schemas[name] = {"index": list(frame.index.names),
                         "dtypes": {column: str(dtype) for column, dtype in frame.dtypes.items()}}
        with np.errstate(invalid="ignore"):
            csv = frame.to_csv(lineterminator="\n", float_format="%.17g")
        write_gzip(root / data.tier.value / f"{name}.csv.gz", csv.encode("utf-8"))
    manifest["tiers"][data.tier.value] = {"tables": schemas,
                                          "checkpoint_every": data.checkpoint_every}
    write_json(manifest_path, manifest)


def load_recorded(root: str | Path, tier: Tier) -> TierData:
    """Load without opening, requiring, or reconstructing a trace or simulator."""
    root = Path(root)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("format") != FORMAT or tier.value not in manifest["tiers"]:
        raise ValueError(f"no recorded feature dataset for {tier.value} under {root}")
    records = {}
    for entry in manifest["records"]:
        value = entry["labels"]
        labels = Labels(value["run_id"],
                        {agent: AgentLabel(**label) for agent, label in value["agents"].items()},
                        value["objective_completed"], value["objective_tick"])
        run = entry["run_id"]
        records[run] = RunRecord(run, root / "raw" / run / "trace.jsonl",
                                 labels, entry["condition"])
    metadata = manifest["tiers"][tier.value]
    tables = {}
    for name in TABLES:
        schema = metadata["tables"][name]
        with gzip.open(root / tier.value / f"{name}.csv.gz", "rb") as source:
            frame = pd.read_csv(io.BytesIO(source.read()), dtype=str, keep_default_na=False)
        # Python's float parser round-trips the writer's 17 significant digits.
        # Empty numeric cells represent NaN; string identifiers must stay intact.
        for column, dtype in schema["dtypes"].items():
            if dtype.startswith("float"):
                frame[column] = [float(value) if value else float("nan")
                                 for value in frame[column]]
            elif dtype == "bool":
                frame[column] = [{"True": True, "False": False}[value]
                                 for value in frame[column]]
        if "tick" in schema["index"]:
            frame["tick"] = frame["tick"].astype("int64")
        frame = frame.set_index(schema["index"]).astype(schema["dtypes"])
        tables[name] = frame
    pair_labels = tables["pairs"].pop("label_pair").to_numpy(dtype=bool)
    tables["runs"] = tables["runs"].drop(columns=[
        name for name in tables["runs"] if name == "label_positive" or name.startswith("condition_")
    ])
    expected = list(records)
    if list(tables["runs"].index) != expected or list(tables["volume"].index) != expected:
        raise ValueError("recorded matrices are not aligned with run metadata")
    for name in ("pairs", "prefix_runs", "prefix_volume"):
        if sorted(set(tables[name].index.get_level_values("run_id"))) != sorted(expected):
            raise ValueError(f"recorded {name} does not cover every run")
    return TierData(tier=tier, records=records, traces={}, pair_labels=pair_labels,
                    checkpoint_every=metadata["checkpoint_every"],
                    shared_logins=_shared_logins(root, manifest, tier, tables["pairs"], records),
                    **tables)


LABEL_PREFIX, CONDITION_PREFIX, OUTCOME_PREFIX = "label_", "condition_", "outcome_"
LABEL_SIDE_PREFIXES = (LABEL_PREFIX, CONDITION_PREFIX, OUTCOME_PREFIX)
RUN_ID = "run_id"
_INTEGER = re.compile(r"-?[0-9]+")


@dataclass(frozen=True)
class TableRecord:
    """Label-side facts for one run of a run table: what eval needs, with no trace."""

    run_id: str
    positive: bool
    condition: Mapping[str, int | str]
    outcomes: Mapping[str, int | str] = field(default_factory=dict)


@dataclass(frozen=True)
class RunTable:
    features: pd.DataFrame
    """Run features indexed by ``run_id``, with every label-side column removed."""
    records: tuple[TableRecord, ...]
    diagnostics: pd.DataFrame = field(default_factory=pd.DataFrame)
    """Non-family diagnostics, excluded from features and available only by explicit selection."""


class _Record(Protocol):
    @property
    def run_id(self) -> str: ...
    @property
    def positive(self) -> bool: ...
    @property
    def condition(self) -> Mapping[str, int | str]: ...


def _value_cell(kind: str, name: str, value: object) -> str:
    """An int or a non-numeric, non-empty string, so the loader recovers its type exactly."""
    if type(value) is int:
        return str(value)
    if type(value) is str and value and not _INTEGER.fullmatch(value):
        return value
    raise ValueError(f"{kind} {name!r} must be an int or a non-numeric, non-empty string, "
                     f"got {value!r}")


def _value(cell: str) -> int | str:
    return int(cell) if _INTEGER.fullmatch(cell) else cell


def write_run_table(
    path: str | Path, runs: pd.DataFrame, records: Sequence[_Record],
    extra: Mapping[str, Mapping[str, int | str]] | None = None,
) -> None:
    """One gzip CSV: ``run_id``, the feature columns in order, ``label_positive``, then
    ``condition_`` and ``outcome_`` columns in sorted order. Opt-in diagnostics follow those
    columns so adding one preserves all existing column positions. ``extra`` gives outcomes.

    Bytes are deterministic: LF line ends, no gzip timestamp, floats in shortest round-trip
    form (always with a point or exponent, so an integral float stays distinct from an int),
    NaN as an empty cell. Feature columns must be int64 or float64.
    """
    if not len(runs.index):
        raise ValueError("refusing to write an empty run table: with no rows an int64 column "
                         "would read back as float64")
    ordered = sorted(records, key=lambda record: record.run_id)
    ids = [record.run_id for record in ordered]
    if len(set(ids)) != len(ids) or list(runs.index) != ids or runs.index.name != RUN_ID:
        raise ValueError("runs must be indexed by run_id, in sorted order of the records' run ids")
    extra = dict(extra or {})
    if set(extra) - set(ids):
        raise ValueError("extra names runs that are not in the records")
    table: dict[str, list[str]] = {RUN_ID: ids}
    diagnostics: dict[str, list[str]] = {}
    for column in runs.columns:
        if column == RUN_ID or str(column).startswith(LABEL_SIDE_PREFIXES):
            raise ValueError(f"feature column {column!r} uses a reserved label_ or run_id name")
        dtype = str(runs[column].dtype)
        destination = diagnostics if column == FILES_RULE_COLUMN else table
        if dtype == "int64":
            destination[column] = [str(int(value)) for value in runs[column]]
        elif dtype == "float64":
            destination[column] = ["" if math.isnan(value) else repr(float(value))
                                   for value in runs[column]]
        else:
            raise ValueError(f"feature column {column!r} has dtype {dtype}; "
                             "expected int64 or float64")
    table[f"{LABEL_PREFIX}positive"] = [str(bool(record.positive)) for record in ordered]
    for prefix, kind, values in (
        (CONDITION_PREFIX, "condition", [record.condition for record in ordered]),
        (OUTCOME_PREFIX, "outcome", [extra.get(run, {}) for run in ids]),
    ):
        for name in sorted({key for value in values for key in value}):
            table[f"{prefix}{name}"] = [
                _value_cell(kind, name, value[name]) if name in value else "" for value in values
            ]
    table.update(diagnostics)
    text = pd.DataFrame(table).to_csv(index=False, lineterminator="\n")
    write_gzip(Path(path), text.encode("utf-8"))


def load_run_table(path: str | Path) -> RunTable:
    """Read a run table; labels go to records and opt-in diagnostics stay outside features."""
    with gzip.open(Path(path), "rb") as source:
        frame = pd.read_csv(io.BytesIO(source.read()), dtype=str, keep_default_na=False)
    ids = list(frame[RUN_ID])
    index = pd.Index(ids, name=RUN_ID)
    features: dict[str, pd.Series] = {}
    for column in frame.columns:
        if column == RUN_ID or column.startswith(LABEL_SIDE_PREFIXES):
            continue
        cells = list(frame[column])
        # The writer gives every float a point, an exponent, "inf" or an empty cell.
        if cells and all(_INTEGER.fullmatch(cell) for cell in cells):
            features[column] = pd.Series([int(cell) for cell in cells], index, dtype="int64")
        else:
            features[column] = pd.Series([float(cell) if cell else math.nan for cell in cells],
                                         index, dtype="float64")
    diagnostics = pd.DataFrame({column: features.pop(column) for column in (FILES_RULE_COLUMN,)
                                if column in features}, index=index)
    table = pd.DataFrame(features, index=index)

    def values(prefix: str, row: int) -> dict[str, int | str]:
        return {column.removeprefix(prefix): _value(frame[column].iloc[row])
                for column in frame.columns
                if column.startswith(prefix) and frame[column].iloc[row] != ""}

    positive = {"True": True, "False": False}
    records = tuple(
        TableRecord(run, positive[frame[f"{LABEL_PREFIX}positive"].iloc[row]],
                    values(CONDITION_PREFIX, row), values(OUTCOME_PREFIX, row))
        for row, run in enumerate(ids)
    )
    return RunTable(table, records, diagnostics)


def _shared_logins(
    root: Path, manifest: dict, tier: Tier, pairs: pd.DataFrame, records: dict[str, RunRecord],
) -> dict[str, frozenset[tuple[str, str]]]:
    """Role-table evidence at V1, read from this tier's pairs or the recorded V1 pairs table.

    Empty when neither carries ``SHARED_LOGINS`` (for example, a V0-only archive).
    """
    if SHARED_LOGINS not in pairs and Tier.V1.value in manifest["tiers"]:
        with gzip.open(root / Tier.V1.value / "pairs.csv.gz", "rb") as source:
            pairs = pd.read_csv(io.BytesIO(source.read()), dtype=str, keep_default_na=False,
                                usecols=["run_id", "agent_a", "agent_b", SHARED_LOGINS])
        pairs[SHARED_LOGINS] = pairs[SHARED_LOGINS].astype("int64")
        pairs = pairs.set_index(["run_id", "agent_a", "agent_b"])
    if SHARED_LOGINS not in pairs:
        return {}
    teams = {run for run, record in records.items()
             if any(label.role == BENIGN_TEAM for label in record.labels.agents.values())}
    return {run: found for run, found in shared_login_pairs(pairs).items() if run in teams}
