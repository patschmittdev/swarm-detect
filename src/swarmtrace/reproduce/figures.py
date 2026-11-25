"""Deterministic SVG figures from the four recorded Markdown reports only."""

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn

_HEADLINE_HEADER = (
    "Split", "Tier", "Family", "Detector", "AUROC", "Detection rate at calibrated threshold",
    "FPR", "Online coverage", "Online FPR",
)
_SHARING_HEADER = (
    "rate", "runs", "fitting (positive, control)", "calibration (positive, control)",
    "test (positive, control)", "sharing test controls (q)", "A_s",
    "AUROC vs non-sharing controls", "overall AUROC", "expected 1 - q/2",
    "interval contains 1 - q/2", "interval contains 1 - q", "detection rate", "FPR",
    "calibration controls", "threshold",
)
_SCOPE_HEADER = (
    "Metric", "Strict", "Legacy", "Strict calibration controls", "Legacy calibration controls",
    "Strict class counts", "Legacy class counts",
)
_CONTAINMENT_HEADER = (
    "arm", "pairs", "required reads prevented (pooled)", "prevented fraction, mean per pair",
    "fully prevented", "partly prevented", "not prevented", "pairs with no required read in twin",
    "objective failed with no required read prevented", "reads prevented but objective completed",
    "objective completed (also requires the group's later writes), arm",
    "objective completed, twin",
    "completion difference, arm minus twin", "simulated", "any intervention",
)
_DETECTORS = ("volume", "rule", "logistic", "boosted")
_GROUPS = (("V0", "generic"), ("V1", "aggregation"), ("V2", "all"))
_RATES = ("0", "5", "10", "30")
_EXPECTED = "expected 1 - q/2"
_SCOPE_SECTIONS = (
    "aggregation-only reference: rule", "C0: files_rule", "C0: scope_rule", "C2: scope_rule",
)
_CONTAINMENT_SECTION = "Required out-of-scope reads prevented, then objective (positive pairs)"
_ARMS = (
    "rule-quarantine", "random-rule-quarantine", "rule-revoke", "random-rule-revoke",
    "logistic-quarantine", "random-logistic-quarantine",
    "logistic-revoke", "random-logistic-revoke",
    "boosted-quarantine", "random-boosted-quarantine", "boosted-revoke", "random-boosted-revoke",
    "halt-rule", "halt-logistic", "halt-boosted", "oracle-quarantine", "oracle-revoke",
)
_POINT_STYLES = {
    "volume": ("circle", "#315c7b"),
    "rule": ("square", "#9a5317"),
    "logistic": ("triangle", "#00796b"),
    "boosted": ("diamond", "#68509b"),
    _EXPECTED: ("circle", "#4d5663"),
    "Strict": ("circle", "#315c7b"),
}
_BAR_STYLES = {
    "detector": ("#315c7b", "#f2f7fa"),
    "random": ("#dce8ef", "#718b9b"),
    "halt": ("#80623d", "#fff5e7"),
    "oracle": ("#4c7256", "#f0f8ed"),
}
_SERIES_LABELS = {
    "volume": "volume (family-independent)",
    "halt": "halt-all",
    "oracle": "oracle (label-informed)",
}


class FigureError(Exception):
    """A source report or figure cannot be read, interpreted, or written."""


@dataclass(frozen=True)
class _Mark:
    series: str
    label: str
    value: str
    lo: str
    hi: str


class _Report:
    def __init__(self, path: Path) -> None:
        self.name = path.name
        try:
            self.lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError) as error:
            raise FigureError(f"{self.name}: cannot read report: {error}") from error

    def fail(self, message: str) -> NoReturn:
        raise FigureError(f"{self.name}: {message}")

    def table(
        self, heading: str, header: tuple[str, ...], keys: tuple[str, ...],
    ) -> dict[tuple[str, ...], dict[str, str]]:
        starts = [i for i, line in enumerate(self.lines) if line == f"## {heading}"]
        if len(starts) != 1:
            self.fail(f"expected exactly one section {heading!r}, found {len(starts)}")
        start = starts[0] + 1
        end = next((i for i in range(start, len(self.lines))
                    if self.lines[i].startswith(("# ", "## "))), len(self.lines))
        section = self.lines[start:end]
        indices = [i for i, line in enumerate(section) if line.lstrip().startswith("|")]
        if len(indices) < 3 or indices != list(range(indices[0], indices[-1] + 1)):
            self.fail(f"section {heading!r} must contain one contiguous Markdown table")
        cells = []
        for index in indices:
            line = section[index].strip()
            if not line.endswith("|"):
                self.fail(f"unterminated table row in section {heading!r}")
            row = [cell.strip() for cell in line[1:-1].split("|")]
            if len(row) != len(header) or any(not cell for cell in row):
                self.fail(f"unexpected table width or empty cell in section {heading!r}")
            cells.append(row)
        if tuple(cells[0]) != header:
            self.fail(f"unexpected header in section {heading!r}; expected {' | '.join(header)}")
        if any(re.fullmatch(r":?-{3,}:?", cell) is None for cell in cells[1]):
            self.fail(f"invalid table separator in section {heading!r}")
        rows = {}
        for cells_row in cells[2:]:
            row = dict(zip(header, cells_row, strict=True))
            key = tuple(row[column] for column in keys)
            if key in rows:
                self.fail(f"duplicate row {key!r} in section {heading!r}")
            rows[key] = row
        return rows

    def require_keys(
        self, rows: dict[tuple[str, ...], dict[str, str]], expected: set[tuple[str, ...]],
        heading: str,
    ) -> None:
        missing, extra = sorted(expected - rows.keys()), sorted(rows.keys() - expected)
        if missing or extra:
            self.fail(f"unexpected rows in section {heading!r}; missing={missing}, extra={extra}")

    def mark(
        self, cell: str, series: str, label: str, digits: int,
        prefix: str = "", suffix: str = "", degenerate: bool = False,
    ) -> _Mark:
        number = rf"\d+\.\d{{{digits}}}"
        if degenerate:
            pattern = (rf"({number}) \(degenerate bootstrap interval "
                       rf"\[({number}), ({number})\]: [^\n]+\)")
        else:
            pattern = rf"({number}) \[({number}), ({number})\]"
        match = re.fullmatch(prefix + pattern + suffix, cell)
        if match is None:
            self.fail(f"unparseable measurement for {series!r}, {label!r}")
        value, lo, hi = match.group(1, 2, 3)
        if not 0 <= float(lo) <= float(value) <= float(hi) <= 1:
            self.fail(f"invalid interval for {series!r}, {label!r}")
        if degenerate and not float(lo) == float(value) == float(hi):
            self.fail(f"non-degenerate bounds labelled degenerate for {label!r}")
        return _Mark(series, label, value, lo, hi)


def _tier_marks(data: Path) -> list[_Mark]:
    report = _Report(data / "headline.md")
    heading = "By-run split"
    rows = report.table(heading, _HEADLINE_HEADER, ("Split", "Tier", "Family", "Detector"))
    source_detectors = ("volume (family-independent)", "rule", "logistic", "boosted")
    report.require_keys(rows, {
        ("by run", tier, family, detector)
        for tier in ("V0", "V1", "V2") for family in ("generic", "aggregation", "all")
        for detector in source_detectors
    }, heading)
    marks = []
    for tier, family in _GROUPS:
        for detector, source_name in zip(_DETECTORS, source_detectors, strict=True):
            cell = rows["by run", tier, family, source_name]["AUROC"]
            if (tier, detector) == ("V0", "rule"):
                if cell != "not available at this tier":
                    report.fail("expected unavailable V0 generic rule AUROC")
            else:
                marks.append(report.mark(cell, detector, f"{tier} {family}", 3))
    return marks


def _sharing_marks(data: Path) -> list[_Mark]:
    report = _Report(data / "sharing-sweep.md")
    marks, expectations = [], {}
    for detector in ("rule", "logistic"):
        rows = report.table(detector, _SHARING_HEADER, ("rate",))
        report.require_keys(rows, {(rate,) for rate in _RATES}, detector)
        for rate in _RATES:
            row = rows[rate,]
            mark = report.mark(row["overall AUROC"], detector, rate, 3,
                               suffix=r" \(\d+ of \d+ runs; [^\n]+\)")
            if not 0.5 <= float(mark.lo) <= float(mark.value) <= float(mark.hi) <= 1:
                report.fail(f"AUROC or bounds outside [0.5, 1.0] at rate {rate} in {detector!r}")
            marks.append(mark)
            value = row[_EXPECTED]
            if re.fullmatch(r"\d+\.\d{4}", value) is None:
                report.fail(f"unparseable {_EXPECTED!r} at rate {rate} in {detector!r}")
            if not 0.5 <= float(value) <= 1:
                report.fail(f"{_EXPECTED!r} outside [0.5, 1.0] at rate {rate} in {detector!r}")
            if detector == "rule":
                expectations[rate] = value
            elif expectations[rate] != value:
                report.fail(f"inconsistent {_EXPECTED!r} between detectors at rate {rate}")
    marks.extend(_Mark(_EXPECTED, rate, value, value, value)
                 for rate, value in expectations.items())
    return marks


def _scope_marks(data: Path) -> tuple[list[_Mark], int, int]:
    report = _Report(data / "scope.md")
    marks = []
    totals = set()
    for heading in _SCOPE_SECTIONS:
        rows = report.table(heading, _SCOPE_HEADER, ("Metric",))
        key = ("violation_vs_in_scope_auroc",)
        if key not in rows:
            report.fail(f"missing row {key[0]!r} in section {heading!r}")
        cell = rows[key]["Strict"]
        marks.append(report.mark(cell, "Strict", heading, 4, suffix=r" bootstrap; [^\n]+"))
        counts = re.search(r" bootstrap; (\d+) positive / (\d+) control;", cell)
        if counts is None or min(int(counts[1]), int(counts[2])) < 1:
            report.fail(f"missing or invalid comparison counts in section {heading!r}")
        totals.add((int(counts[1]), int(counts[2])))
    if len(totals) != 1:
        report.fail("inconsistent comparison counts across scope sections")
    positive_runs, control_runs = totals.pop()
    return marks, positive_runs, control_runs


def _containment_marks(data: Path) -> tuple[list[_Mark], int, int]:
    report = _Report(data / "containment.md")
    rows = report.table(_CONTAINMENT_SECTION, _CONTAINMENT_HEADER, ("arm",))
    report.require_keys(rows, {(arm,) for arm in ("twin", *_ARMS)}, _CONTAINMENT_SECTION)
    marks = []
    totals = set()
    for arm in ("twin", *_ARMS):
        row = rows[arm,]
        cell = row["required reads prevented (pooled)"]
        counts = re.match(r"(\d+) of (\d+) files; ", cell)
        if counts is None or re.fullmatch(r"\d+", row["pairs"]) is None:
            report.fail(f"missing or invalid required-read or pair counts for arm {arm!r}")
        required_reads, pairs = int(counts[2]), int(row["pairs"])
        if required_reads < 1 or pairs < 1 or int(counts[1]) > required_reads:
            report.fail(f"invalid required-read or pair counts for arm {arm!r}")
        totals.add((required_reads, pairs))
        if arm == "twin":
            continue
        series = (
            arm.split("-", 1)[0] if arm.startswith(("random-", "halt-", "oracle-"))
            else "detector"
        )
        marks.append(report.mark(cell, series, arm, 3, prefix=r"\d+ of \d+ files; ",
                                 degenerate=" (degenerate bootstrap interval " in cell))
    if len(totals) != 1:
        report.fail("inconsistent required-read or pair counts across containment arms")
    required_reads, pairs = totals.pop()
    return marks, required_reads, pairs


def _format(value: str | int | float) -> str:
    return f"{value:.3f}" if isinstance(value, float) else str(value)


def _add(
    parent: ET.Element, tag: str, text: str | None = None, **attributes: str | int | float,
) -> ET.Element:
    # Insertion order fixes attribute order; ElementTree escapes text and quoted attributes.
    element = ET.SubElement(parent, tag, {
        key.replace("_", "-"): _format(value) for key, value in attributes.items()
    })
    element.text = text
    return element


def _text(parent: ET.Element, x: float, y: float, text: str, **attributes: str | int) -> None:
    _add(parent, "text", text, x=x, y=y, **attributes)


def _svg(title: str, description: str, height: int) -> ET.Element:
    root = ET.Element("svg", {
        "xmlns": "http://www.w3.org/2000/svg", "viewBox": f"0 0 720 {height}",
        "width": "720", "height": str(height), "font-family": "sans-serif", "font-size": "13",
        "fill": "#25313d", "role": "img", "aria-labelledby": "title description",
    })
    _add(root, "title", title, id="title")
    _add(root, "desc", description, id="description")
    _add(root, "rect", x=0, y=0, width=720, height=height, fill="#fafbf9")
    _text(root, 28, 34, title, font_size=22, font_weight="bold")
    return root


def _description(marks: list[_Mark], measure: str) -> str:
    statements = []
    for mark in marks:
        if mark.series == _EXPECTED:
            statements.append(f"{mark.series} at rate {mark.label} percent is {mark.value} "
                              "(theoretical reference, without an uncertainty interval).")
        else:
            series = _SERIES_LABELS.get(mark.series, mark.series)
            statements.append(f"{series} at {mark.label} has {measure} {mark.value}, with "
                              f"interval from {mark.lo} to {mark.hi} (bootstrap bounds).")
    return " ".join(statements)


def _y(
    value: str | float, top: float = 132, bottom: float = 366, minimum: float = 0,
) -> float:
    return bottom - (float(value) - minimum) / (1 - minimum) * (bottom - top)


def _vertical_axes(
    root: ET.Element, xlabel: str, bottom: float = 366, minimum: float = 0,
) -> None:
    ticks = (0.5, 0.6, 0.7, 0.8, 0.9, 1.0) if minimum == 0.5 else (0, 0.25, 0.5, 0.75, 1)
    for value in ticks:
        y = _y(value, bottom=bottom, minimum=minimum)
        _add(root, "line", x1=92, y1=y, x2=692, y2=y, stroke="#dce1e4", stroke_width=1)
        _text(root, 79, y, f"{value:.1f}" if minimum else f"{value:g}",
              text_anchor="end", dominant_baseline="middle")
    _add(root, "line", x1=92, y1=132, x2=92, y2=bottom, stroke="#61717d")
    _text(root, 24, 249, "AUROC (unitless)", text_anchor="middle", transform="rotate(-90 24 249)")
    _text(root, 392, bottom + 76, xlabel, text_anchor="middle")


def _chance_line(root: ET.Element, bottom: float = 366) -> None:
    y = _y(0.5, bottom=bottom)
    _add(root, "line", x1=92, y1=y, x2=692, y2=y, stroke="#6e7780",
         stroke_width=1.5, stroke_dasharray="6 4")


def _symbol(parent: ET.Element, series: str, x: float, y: float) -> None:
    shape, color = _POINT_STYLES[series]
    style = ({"fill": "#fafbf9", "stroke": color, "stroke_width": 1.8} if series == "Strict"
             else {"fill": color, "stroke": "#ffffff", "stroke_width": 1})
    if shape == "circle":
        _add(parent, "circle", cx=x, cy=y, r=5.5, **style)
    elif shape == "square":
        _add(parent, "rect", x=x - 5, y=y - 5, width=10, height=10, **style)
    else:
        points = ([(x, y - 7), (x + 6, y + 3.5), (x - 6, y + 3.5)] if shape == "triangle"
                  else [(x, y - 7), (x + 6, y), (x, y + 7), (x - 6, y)])
        _add(parent, "polygon", points=" ".join(f"{px:.3f},{py:.3f}" for px, py in points),
             **style)


def _point_legend(
    root: ET.Element, series: tuple[str, ...], positions: tuple[int, ...], y: int = 90,
    chance: tuple[int, int] | None = None,
) -> None:
    legend = _add(root, "g", id="legend", aria_label="Legend")
    for name, x in zip(series, positions, strict=True):
        _symbol(legend, name, x, y)
        _text(legend, x + 13, y + 4, _SERIES_LABELS.get(name, name))
    if chance is not None:
        x, y = chance
        _add(legend, "line", x1=x, y1=y, x2=x + 24, y2=y, stroke="#6e7780",
             stroke_width=1.5, stroke_dasharray="6 4")
        _text(legend, x + 32, y + 4, "chance")


def _mark_group(root: ET.Element, mark: _Mark) -> ET.Element:
    return _add(root, "g", data_series=mark.series, data_label=mark.label, data_value=mark.value,
                data_lo=mark.lo, data_hi=mark.hi)


def _point(root: ET.Element, mark: _Mark, x: float, minimum: float = 0) -> None:
    group = _mark_group(root, mark)
    _, color = _POINT_STYLES[mark.series]
    if mark.series == "Strict":
        _symbol(group, mark.series, x, _y(mark.value, minimum=minimum))
    if mark.series != _EXPECTED:
        lo, hi = _y(mark.lo, minimum=minimum), _y(mark.hi, minimum=minimum)
        _add(group, "line", x1=x, y1=lo, x2=x, y2=hi, stroke=color, stroke_width=1.8)
        for y in (lo, hi):
            _add(group, "line", x1=x - 4, y1=y, x2=x + 4, y2=y,
                 stroke=color, stroke_width=1.8)
    if mark.series != "Strict":
        _symbol(group, mark.series, x, _y(mark.value, minimum=minimum))


def _tier_svg(marks: list[_Mark]) -> ET.Element:
    title = "By-run test AUROC by visibility tier"
    description = (_description(marks, "AUROC") + " V0 generic rule is n/a: not available at "
                   "this tier; its n/a label is below the axis. "
                   "The dashed horizontal line is chance AUROC 0.5 (unitless).")
    root = _svg(title, description, 466)
    _text(root, 28, 58, "Recorded by-run split; points and bootstrap intervals")
    _point_legend(root, _DETECTORS, (110, 360, 462, 592), chance=(110, 112))
    _vertical_axes(root, "Visibility tier and feature family")
    _chance_line(root)
    centers = {f"{tier} {family}": x for (tier, family), x in zip(_GROUPS, (190, 392, 594))}
    offsets = dict(zip(_DETECTORS, (-48, -16, 16, 48), strict=True))
    for mark in marks:
        _point(root, mark, centers[mark.label] + offsets[mark.series])
    _add(root, "text", "n/a", x=centers["V0 generic"] + offsets["rule"], y=385,
         text_anchor="middle", data_series="rule", data_label="V0 generic")
    for label, x in centers.items():
        _text(root, x, 410, label, text_anchor="middle")
    return root


def _sharing_svg(marks: list[_Mark]) -> ET.Element:
    subtitle = ("q = realised fraction of test controls with a sharing team; "
                "by-run test split; V1 aggregation")
    description = (subtitle + "; y axis 0.5 to 1.0. " + _description(marks, "AUROC")
                   + " Within each rate, rule is left, logistic is centre and the expected "
                   "reference is right; adjacent series are offset horizontally by 12 pixels.")
    root = _svg("By-run test AUROC by benign sharing rate", description, 466)
    _text(root, 28, 58, subtitle, font_size=12)
    _text(root, 28, 77, "y axis 0.5 to 1.0", font_size=12)
    _point_legend(root, ("rule", "logistic", _EXPECTED), (128, 294, 458), y=105)
    _vertical_axes(root, "Benign sharing rate (%)", minimum=0.5)
    xs = {rate: 110 + int(rate) / 30 * 564 for rate in _RATES}
    offsets = {"rule": -12, "logistic": 0, _EXPECTED: 12}
    for series, dash in (("rule", "none"), ("logistic", "6 4"), (_EXPECTED, "2 4")):
        points = [mark for mark in marks if mark.series == series]
        coordinates = " ".join(
            f"{xs[mark.label] + offsets[series]:.3f},{_y(mark.value, minimum=0.5):.3f}"
            for mark in points
        )
        _add(root, "polyline", points=coordinates, fill="none", stroke=_POINT_STYLES[series][1],
             stroke_width=1.5, stroke_dasharray=dash, data_series=series)
    for mark in marks:
        _point(root, mark, xs[mark.label] + offsets[mark.series], minimum=0.5)
    for rate, x in xs.items():
        _text(root, x, 397, rate, text_anchor="middle")
    return root


def _scope_svg(marks: list[_Mark], positive_runs: int, control_runs: int) -> ET.Element:
    subtitle = ("Strict labelling: scope violations against in-scope relays only "
                f"({positive_runs} against {control_runs} test runs)")
    key = "C0: log only; C2: also each hand-off's file scope"
    description = (subtitle + ". " + key + ". " + _description(marks, "AUROC")
                   + " The aggregation-only reference is shared-login count (no context)."
                   " Hollow markers are drawn below the interval whiskers."
                   + " The dashed horizontal line is chance AUROC 0.5 (unitless).")
    root = _svg("Strict scope discrimination by context", description, 466)
    _text(root, 28, 58, subtitle, font_size=12)
    _text(root, 28, 78, key, font_size=12)
    _point_legend(root, ("Strict",), (280,), y=104, chance=(400, 104))
    _vertical_axes(root, "Defender context and detector")
    _chance_line(root)
    for index, mark in enumerate(marks):
        x = 158 + index * 160
        _point(root, mark, x)
        lines = ("shared-login count", "(no context)") if index == 0 else (mark.label,)
        for line_index, line in enumerate(lines):
            _text(root, x, 393 + line_index * 17, line, text_anchor="middle", font_size=12)
    return root


def _bar_patterns(root: ET.Element) -> None:
    defs = _add(root, "defs")
    for series, (background, ink) in _BAR_STYLES.items():
        pattern = _add(defs, "pattern", id=f"hatch-{series}", patternUnits="userSpaceOnUse",
                       width=8, height=8)
        _add(pattern, "rect", x=0, y=0, width=8, height=8, fill=background)
        if series == "detector":
            _add(pattern, "path", d="M-2 2 L2 -2 M0 8 L8 0 M6 10 L10 6", stroke=ink,
                 stroke_width=1, fill="none")
        elif series == "random":
            _add(pattern, "line", x1=0, y1=4, x2=8, y2=4, stroke=ink, stroke_width=1)
        elif series == "halt":
            _add(pattern, "path", d="M0 4 H8 M4 0 V8", stroke=ink, stroke_width=1, fill="none")
        else:
            _add(pattern, "circle", cx=4, cy=4, r=1.3, fill=ink)


def _containment_svg(marks: list[_Mark], required_reads: int, pairs: int) -> ET.Element:
    reads_caption = f"Fraction of {required_reads} required out-of-scope reads prevented;"
    pairs_caption = f"{pairs} relay runs paired with uncontained twins"
    subtitle = f"{reads_caption} {pairs_caption}"
    description = (subtitle + ". "
                   + _description(marks, "required reads prevented as a pooled fraction")
                   + " Each detector arm is followed by its lighter matched random arm. "
                   "Arm labels identify quarantine or revoke; halt-all stops all agents. "
                   "Oracle intervals are degenerate bootstrap intervals: they describe these "
                   "resamples, not certainty about the population value. The twin is not plotted.")
    root = _svg("Required out-of-scope reads prevented", description, 744)
    _text(root, 28, 58, reads_caption, font_size=12)
    _text(root, 28, 77, pairs_caption, font_size=12)
    _bar_patterns(root)
    legend = _add(root, "g", id="legend", aria_label="Legend")
    for series, x in zip(_BAR_STYLES, (98, 238, 360, 480), strict=True):
        _add(legend, "rect", x=x, y=96, width=18, height=14, fill=f"url(#hatch-{series})",
             stroke="#536575", stroke_width=1)
        _text(legend, x + 25, 108, _SERIES_LABELS.get(series, series))
    left, right, bottom = 260, 688, 648
    for value in (0, 0.25, 0.5, 0.75, 1):
        x = left + value * (right - left)
        _add(root, "line", x1=x, y1=124, x2=x, y2=bottom, stroke="#dce1e4")
        _text(root, x, bottom + 24, f"{value:g}", text_anchor="middle")
    _text(root, left - 12, 122, "Containment arm", text_anchor="end", font_weight="bold")
    _text(root, (left + right) / 2, 704, "Required reads prevented (pooled fraction)",
          text_anchor="middle")
    y = 144
    for index, mark in enumerate(marks):
        label = mark.label.replace("halt-", "halt-all ").replace(
            "oracle-", "oracle (label-informed): ",
        )
        _text(root, left - 12, y + 4, label, text_anchor="end", font_size=12)
        group = _mark_group(root, mark)
        _add(group, "rect", x=left, y=y - 7, width=float(mark.value) * (right - left),
             height=14, fill=f"url(#hatch-{mark.series})", stroke="#536575", stroke_width=1)
        lo, hi = (left + float(value) * (right - left) for value in (mark.lo, mark.hi))
        for stroke, width in (("#ffffff", 4), ("#172a38", 1.6)):
            _add(group, "line", x1=lo, y1=y, x2=hi, y2=y, stroke=stroke, stroke_width=width)
            for x in (lo, hi):
                _add(group, "line", x1=x, y1=y - 5, x2=x, y2=y + 5,
                     stroke=stroke, stroke_width=width)
        y += 26 + (8 if index in (1, 3, 5, 7, 9, 11, 14) else 0)
    _text(root, 28, 730, "Intervals are bootstrap bounds; oracle intervals are degenerate.",
          font_size=12)
    return root


def main(data: Path, out: Path) -> list[Path]:
    """Validate recorded tables and write four byte-stable SVGs, returning their paths.

    Report measurements retain their printed precision. Only drawing coordinates
    are formatted here. No runs, feature tables, clocks, or external resources are used.
    """
    data, out = Path(data), Path(out)
    documents = (
        ("auroc-by-tier.svg", _tier_svg(_tier_marks(data))),
        ("auroc-by-sharing-rate.svg", _sharing_svg(_sharing_marks(data))),
        ("scope-by-context.svg", _scope_svg(*_scope_marks(data))),
        ("containment-prevented.svg", _containment_svg(*_containment_marks(data))),
    )
    rendered = []
    for name, root in documents:
        ET.indent(root, space="  ")
        rendered.append((out / name, ET.tostring(root, encoding="utf-8", xml_declaration=True)
                         + b"\n"))
    try:
        out.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise FigureError(f"{out}: cannot create figure directory: {error}") from error
    for path, content in rendered:
        try:
            path.write_bytes(content)
        except OSError as error:
            raise FigureError(f"{path.name}: cannot write figure: {error}") from error
    return [path for path, _ in rendered]
