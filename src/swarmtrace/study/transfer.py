"""Transfer test: the frozen detector and the comparison rules on a real incident write log and
on a benign wiki's 2025 edit history.

Names and page names are replaced by salted hashes; the salt is drawn per run and never written,
so no name, page name or text reaches the outputs, which hold days and counts only. The incident
file is read once and the control file is streamed once: in both, the bytes that are hashed are
the bytes that are parsed, and both must match pinned digests. At these sizes (tens of MB) the
incident file is held in memory whole; that is deliberate. Page bodies are used in memory for
the template-folding rule only, one last body per page. Parse errors name the row
number (and for the control the column index) only.
"""

import bz2
import csv
import gzip
import hashlib
import json
import secrets
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from swarmtrace.study import folding
from swarmtrace.study.fleet_api import BASELINES, Fleet, default_fleet, score_events
from swarmtrace.study.freeze import PACKAGE_ROOT, SCORING_PACKAGES, source_hashes
from swarmtrace.study.stats import proportion

INCIDENT_SHA256 = "60df4a515178230aa952d9f64f6215aea4bd95ab2f05e31e484cf9b887e3f793"
CONTROL_SHA256 = "70bda4e78269c4084f3765e1fbebf39b2a72117efd4991d24b4bf0f580899739"
CONTROL_BYTES = 82295203
RULES_NOTE = ("The two control-calibrated rules flag zero control days by construction: their "
              "thresholds are the control's own maxima.")
NOTICE = datetime(2026, 6, 2, 23, 24, tzinfo=UTC)
CONTROL_YEAR = 2025
MIN_EDITS = 20
SEEDS = range(20)
MODES = ("identity", "no_identity")
CONTROL_COLUMNS = 78
COL = {"entity": 2, "type": 3, "timestamp": 4, "user_text": 9, "bot_by": 15, "page_id": 28,
       "text_bytes": 65, "text_sha1": 67}
BOT_LABELS = ("none", "name", "group", "name+group", "other")
NOT_APPLICABLE = "not applicable (no text)"
NAME_BLANKING_NOTE = ("With identity removed and no reads the detector's score is zero by "
                      "construction; this result shows a limit of the detector, not a test of it.")


@dataclass(frozen=True)
class Edit:
    t: datetime
    name: str | None
    page: str
    content: str | None
    length: int | None


@dataclass(frozen=True)
class Incident:
    edits: list[Edit]
    events: list[tuple[float, str | None, list[str]]]
    sha256: str


def _time(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)


def _name(text) -> str | None:
    return text if isinstance(text, str) and text.strip() else None


def read_incident(path: Path, autojunk: bool = True, keep_newlines: bool = False,
                  page_fallback: bool = False, _test_expected_sha256: str | None = None
                  ) -> Incident:
    """Stored edits in time order and their folding-rule events, from one verified read.

    The expanded bytes must hash to the publisher's SHA-256 (``_test_expected_sha256`` exists
    for synthetic test fixtures only). Each body is compared with the last stored body of the
    same page; a page whose revisions go back in time in file order is an error.
    ``page_fallback`` (off in the study) uses the page name for a blank actor.
    """
    data = Path(path).read_bytes()
    if Path(path).suffix == ".gz":
        data = gzip.decompress(data)
    digest = hashlib.sha256(data).hexdigest()
    if digest != (_test_expected_sha256 or INCIDENT_SHA256):
        raise ValueError("incident file SHA-256 differs from the publisher's")
    edits, events, last = [], [], {}
    for number, raw in enumerate(data.split(b"\n"), 1):
        if not raw.strip():
            continue
        try:
            row = json.loads(raw.decode("utf-8"))
            t, page = _time(row["time"]), str(row["page_key"])
            name, body = _name(row.get("label")), row.get("body")
            if body is None:
                body = ""
            if not isinstance(body, str):
                raise TypeError("body")
            length = row.get("body_len")
            edit = Edit(t, name, page, row.get("body_sha256"),
                        int(length) if length is not None else None)
        except (KeyError, ValueError, TypeError, AttributeError, UnicodeDecodeError) as error:
            raise ValueError(f"incident row {number}: {type(error).__name__}") from None
        before = last.get(page)
        if before is not None and t < before[0]:
            raise ValueError(f"incident row {number}: page revisions out of time order")
        text = folding.sanitise(folding.changed_text(before[1] if before else None, body,
                                                     autojunk), keep_newlines)
        actor = page if name is None and page_fallback else name
        edits.append(edit)
        events.append((t.timestamp(), actor, folding.keys(text)))
        last[page] = (t, body)
    del data, last
    order = sorted(range(len(edits)), key=lambda i: edits[i].t)
    return Incident([edits[i] for i in order], [events[i] for i in order], digest)


def bot_label(value: str) -> str:
    """Closed label for the control's event_user_is_bot_by column."""
    parts = {p for p in value.split(",") if p}
    if not parts:
        return "none"
    if parts == {"name"}:
        return "name"
    if parts == {"group"}:
        return "group"
    if parts == {"name", "group"}:
        return "name+group"
    return "other"


class _Hashing:
    """A binary reader that hashes and counts the bytes passed through it."""

    def __init__(self, handle):
        self.handle, self.digest, self.size = handle, hashlib.sha256(), 0

    def read(self, n=-1):
        chunk = self.handle.read(n)
        self.digest.update(chunk)
        self.size += len(chunk)
        return chunk

    def readable(self):
        return True

    def seekable(self):
        return False


def read_control(path: Path, year: int = CONTROL_YEAR, _test_expected_sha256: str | None = None,
                 _test_expected_bytes: int | None = None) -> tuple[list[Edit], dict]:
    """Revision-create events of the given UTC year, in time order, and row counts by bot label.

    The file is streamed once through a hashing reader, and its SHA-256 and size must equal the
    pinned values (the ``_test_`` overrides exist for synthetic fixtures only).
    """
    edits, by_bot = [], dict.fromkeys(BOT_LABELS, 0)
    with open(path, "rb") as raw:
        hashing = _Hashing(raw)
        with bz2.open(hashing, "rt", encoding="utf-8", newline="\n") as handle:
            for number, line in enumerate(handle, 1):
                parts = line.rstrip("\n").split("\t")
                if len(parts) != CONTROL_COLUMNS:
                    raise ValueError(f"control row {number}: expected {CONTROL_COLUMNS} columns")
                if parts[COL["entity"]] != "revision" or parts[COL["type"]] != "create":
                    continue
                stamp = parts[COL["timestamp"]]
                if not stamp.startswith(f"{year}-"):
                    continue
                column = COL["timestamp"]
                try:
                    t = datetime.fromisoformat(stamp).replace(tzinfo=UTC)
                    column = COL["text_bytes"]
                    size = parts[column]
                    length = int(size) if size else None
                except ValueError:
                    raise ValueError(f"control row {number}: column {column} unreadable") from None
                edits.append(Edit(t, _name(parts[COL["user_text"]]), parts[COL["page_id"]],
                                  parts[COL["text_sha1"]] or None, length))
                by_bot[bot_label(parts[COL["bot_by"]])] += 1
        while hashing.read(1 << 20):
            pass
    digest = hashing.digest.hexdigest()
    if digest != (_test_expected_sha256 or CONTROL_SHA256):
        raise ValueError("control file SHA-256 differs from the pinned value")
    if hashing.size != (_test_expected_bytes or CONTROL_BYTES):
        raise ValueError("control file size differs from the pinned value")
    edits.sort(key=lambda e: e.t)
    return edits, {"rows": len(edits), "by_bot_flag": by_bot, "sha256": digest,
                   "bytes": hashing.size}


class Opaque:
    """Salted hash of names and page names; the salt is never written."""

    def __init__(self, salt: bytes | None = None):
        self._salt = salt if salt is not None else secrets.token_bytes(32)

    def __call__(self, kind: str, value: str | None) -> str | None:
        if value is None:
            return None
        return hashlib.sha256(self._salt + kind.encode() + b"\0" + value.encode()).hexdigest()[:16]


def windows(edits: list[Edit], min_edits: int = MIN_EDITS) -> dict[date, list[Edit]]:
    days: dict[date, list[Edit]] = defaultdict(list)
    for e in edits:
        days[e.t.date()].append(e)
    return {d: rows for d, rows in sorted(days.items()) if len(rows) >= min_edits}


def detector_rows(day_edits: list[Edit], opaque: Opaque, identity: bool) -> list[dict]:
    """The protocol's mapping: one PUT to /notes/<opaque page> per stored edit, timed in seconds
    since the window's first edit."""
    origin = day_edits[0].t
    rows = []
    for seq, e in enumerate(day_edits, 1):
        t = (e.t - origin).total_seconds()
        rows.append({"seq": seq, "t_start": t, "t_end": t,
                     "token_id": opaque("name", e.name) if identity else None,
                     "user_agent": "", "method": "PUT", "path": "/notes/" + opaque("page", e.page),
                     "query": "", "status": 200, "bytes_in": e.length or 0, "bytes_out": 0,
                     "write_sha256": e.content})
    return rows


def _distinct_names(rows: list[Edit]) -> int:
    return len({e.name for e in rows if e.name is not None})


def _distance(edits: list[Edit], end: datetime) -> dict:
    """Distances of an alert measured at the end of the alerting window or bin."""
    return {"days_after_first_edit": (end - edits[0].t).total_seconds() / 86400,
            "edits_through_window": sum(e.t < end for e in edits),
            "days_after_notice": (end - NOTICE).total_seconds() / 86400}


def _day_end(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, tzinfo=UTC) + timedelta(days=1)


def _first_day(edits: list[Edit], alerted: list[date]) -> dict | None:
    if not alerted:
        return None
    first = min(alerted)
    return {"window": first.isoformat(), **_distance(edits, _day_end(first))}


def day_rules(incident: dict[date, list[Edit]], control: dict[date, list[Edit]]) -> dict:
    max_edits = max((len(r) for r in control.values()), default=0)
    max_names = max((_distinct_names(r) for r in control.values()), default=0)
    return {"edits": {"control_max": max_edits,
                      "alerted": [d for d, r in incident.items() if len(r) > max_edits]},
            "names": {"control_max": max_names,
                      "alerted": [d for d, r in incident.items() if _distinct_names(r) > max_names]}}


def _spread(values: list[float]) -> dict | None:
    values = sorted(values)
    if not values:
        return None
    mid = len(values) // 2
    median = values[mid] if len(values) % 2 else (values[mid - 1] + values[mid]) / 2
    return {"min": values[0], "median": median, "max": values[-1]}


def folding_rule(events, edits: list[Edit], eligible: set[date], seeds=SEEDS) -> dict:
    """First alarm and eligible days with at least one hourly alarm, per seed and across seeds."""
    bins = folding.bin_series(events)
    per_seed = []
    for seed in seeds:
        _, alarms = folding.sequential(bins, seed)
        hours = [bins.start + b for b, a in enumerate(alarms) if a]
        days = {datetime.fromtimestamp(h * folding.BIN_SECONDS, UTC).date() for h in hours}
        first = None
        if hours:
            first = _distance(edits, datetime.fromtimestamp((hours[0] + 1) * folding.BIN_SECONDS,
                                                            UTC))
        per_seed.append({"seed": seed, "alarm_bins": len(hours),
                         "eligible_days_with_alarm": len(days & eligible), "first_alarm": first})
    found = [s["first_alarm"] for s in per_seed if s["first_alarm"] is not None]
    return {"bins": len(bins.n), "seeds": len(per_seed),
            "seeds_never_alarm": len(per_seed) - len(found),
            "first_alarm_days_after_first_edit": _spread([f["days_after_first_edit"]
                                                          for f in found]),
            "first_alarm_edits_through_bin": _spread([f["edits_through_window"] for f in found]),
            "first_alarm_days_after_notice": _spread([f["days_after_notice"] for f in found]),
            "eligible_days_with_alarm": _spread([s["eligible_days_with_alarm"]
                                                 for s in per_seed]),
            "eligible_days": len(eligible), "per_seed": per_seed,
            "distance_convention": "end of the first alarming hourly bin"}


def compare_reference(events, reference: list[dict]) -> dict:
    """Agreement of per-bin n and C with a reference timeline of {t, n, C} rows."""
    bins = folding.bin_series(events)
    ours = {}
    for b, (n, c) in enumerate(zip(bins.n, bins.C)):
        t = datetime.fromtimestamp((bins.start + b) * folding.BIN_SECONDS, UTC)
        ours[t.strftime("%Y-%m-%dT%H:%M:%SZ")] = (n, c)
    shared = [r for r in reference if r["t"] in ours]
    dc = [abs(ours[r["t"]][1] - r["C"]) for r in shared]
    return {"bins_ours": len(ours), "bins_reference": len(reference), "bins_shared": len(shared),
            "n_equal": sum(ours[r["t"]][0] == r["n"] for r in shared),
            "C_mean_abs_diff": (sum(dc) / len(dc)) if dc else None,
            "C_max_abs_diff": max(dc, default=None),
            "C_bins_within_0_01": sum(d <= 0.01 for d in dc),
            "C_sum_ours": sum(ours[r["t"]][1] for r in shared),
            "C_sum_reference": sum(r["C"] for r in shared)}


def run_transfer(incident_path: Path, control_path: Path, out: Path, fleet: Fleet | None = None,
                 root: Path = PACKAGE_ROOT, salt: bytes | None = None,
                 _test_expected_sha256: str | None = None,
                 _test_control: tuple[str, int] | None = None, official: dict | None = None
                 ) -> dict:
    """Score every window of both logs in both identity modes; writes windows.csv and
    summary.json (aggregates only), and OFFICIAL.json when ``official`` is given, to out."""
    out = Path(out)
    if out.exists():
        raise FileExistsError(f"{out} already exists")
    incident = read_incident(incident_path, _test_expected_sha256=_test_expected_sha256)
    edits = incident.edits
    control, control_counts = read_control(
        control_path, _test_expected_sha256=_test_control[0] if _test_control else None,
        _test_expected_bytes=_test_control[1] if _test_control else None)
    win = {"incident": windows(edits), "control": windows(control)}
    if not win["control"]:
        raise ValueError("the control has no eligible day")
    fleet = fleet or default_fleet()
    opaque = Opaque(salt)
    rows, alerted = [], {(d, m): [] for d in win for m in MODES}
    for dataset, days in win.items():
        for day, day_edits in days.items():
            for mode in MODES:
                events = fleet.events_from_rows(detector_rows(day_edits, opaque,
                                                              mode == "identity"))
                summary, _, baselines = score_events(fleet, events, mode == "identity")
                if summary["alert"]:
                    alerted[(dataset, mode)].append(day)
                rows.append({"dataset": dataset, "day": day.isoformat(), "identity_mode": mode,
                             "edits": len(day_edits), "distinct_names": _distinct_names(day_edits),
                             "score": summary["score"], "alert": summary["alert"], **baselines})
    report = {"note": "aggregates only; names and pages replaced by unsaved salted hashes",
              "source_sha256": source_hashes(SCORING_PACKAGES, root),
              "incident": {"sha256": incident.sha256, "rows": len(edits),
                           "blank_name_rows": sum(e.name is None for e in edits),
                           "eligible_days": len(win["incident"]),
                           "first_retained_edit_day": edits[0].t.date().isoformat()},
              "official": official is not None,
              **({"record": official} if official else {}),
              "control": {**control_counts,
                          "eligible_days": len(win["control"])},
              "detector": {}}
    for mode in MODES:
        report["detector"][mode] = {
            "control": proportion(len(alerted[("control", mode)]), len(win["control"])),
            "incident": {**proportion(len(alerted[("incident", mode)]), len(win["incident"])),
                         "first": _first_day(edits, alerted[("incident", mode)])}}
    report["detector"]["no_identity"]["note"] = NAME_BLANKING_NOTE
    report["rules"] = {"note": RULES_NOTE}
    for name, rule in day_rules(win["incident"], win["control"]).items():
        report["rules"][name] = {
            "control_max": rule["control_max"],
            "control": proportion(0, len(win["control"])),
            "incident": {**proportion(len(rule["alerted"]), len(win["incident"])),
                         "first": _first_day(edits, rule["alerted"])}}
    report["rules"]["template_folding"] = {
        "incident": folding_rule(incident.events, edits, set(win["incident"])),
        "control": NOT_APPLICABLE}
    out.mkdir(parents=True)
    with open(out / "windows.csv", "w", newline="", encoding="utf-8") as handle:
        fields = ["dataset", "day", "identity_mode", "edits", "distinct_names", "score", "alert",
                  *BASELINES]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    (out / "summary.json").write_text(json.dumps(report, indent=2, default=str) + "\n",
                                      encoding="utf-8")
    if official:
        (out / "OFFICIAL.json").write_text(json.dumps(official, indent=2) + "\n",
                                           encoding="utf-8")
    return report
