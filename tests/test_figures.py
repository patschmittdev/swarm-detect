"""Figures are checked against the committed reports, never the production parser.

Mark identities use detector names and '<tier> <family>' labels for the tier plot;
detector names (or 'expected 1 - q/2') and rate labels for the sharing plot;
'Strict' and the section headings for scope; and detector/random/halt/oracle
series with full arm names for containment. A point without an interval uses
its value for both bounds. Numeric strings retain the source precision.
"""

import ast
import re
import shutil
import sys
import xml.etree.ElementTree as ET
from importlib.util import resolve_name
from pathlib import Path

import pytest

from swarmtrace.cli import main as cli_main
from swarmtrace.reproduce import figures

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA = PROJECT_ROOT / "data"
SVG = "{http://www.w3.org/2000/svg}"
FIGURE_COUNTS = {
    "auroc-by-tier.svg": 11,
    "auroc-by-sharing-rate.svg": 12,
    "scope-by-context.svg": 4,
    "containment-prevented.svg": 17,
}
TIER_GROUPS = (("V0", "generic"), ("V1", "aggregation"), ("V2", "all"))
SCOPE_SECTIONS = (
    "aggregation-only reference: rule", "C0: files_rule", "C0: scope_rule", "C2: scope_rule",
)
CONTAINMENT_SECTION = "Required out-of-scope reads prevented, then objective (positive pairs)"
CONTAINMENT_ARMS = (
    "rule-quarantine", "random-rule-quarantine",
    "rule-revoke", "random-rule-revoke",
    "logistic-quarantine", "random-logistic-quarantine",
    "logistic-revoke", "random-logistic-revoke",
    "boosted-quarantine", "random-boosted-quarantine",
    "boosted-revoke", "random-boosted-revoke",
    "halt-rule", "halt-logistic", "halt-boosted", "oracle-quarantine", "oracle-revoke",
)
MARK_ATTRIBUTES = ("data-series", "data-label", "data-value", "data-lo", "data-hi")
NUMBER = r"\d+\.\d+"
INTERVAL = rf"({NUMBER}) \[({NUMBER}), ({NUMBER})\]"


def _section(markdown: str, heading: str) -> str:
    matches = re.findall(
        rf"^## {re.escape(heading)}\n(.*?)(?=^## |\Z)", markdown, re.MULTILINE | re.DOTALL,
    )
    assert len(matches) == 1, heading
    return matches[0]


def _table_lines(section: str) -> list[str]:
    lines = re.findall(r"^\|[^\n]*\|[ \t]*$", section, re.MULTILINE)
    assert len(lines) >= 3, "Expected a header, separator and data rows"
    assert re.fullmatch(r"[| :\-]+", lines[1])
    return lines


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in re.findall(r"\|([^|]*)(?=\|)", line)]


def _rows(filename: str, heading: str) -> list[dict[str, str]]:
    markdown = (DATA / filename).read_text(encoding="utf-8")
    lines = _table_lines(_section(markdown, heading))
    header = _cells(lines[0])
    assert len(header) == len(set(header)), (filename, heading)
    return [dict(zip(header, _cells(line), strict=True)) for line in lines[2:]]


def _one(rows: list[dict[str, str]], **wanted: str) -> dict[str, str]:
    found = [row for row in rows if all(row[key] == value for key, value in wanted.items())]
    assert len(found) == 1, wanted
    return found[0]


def _interval(cell: str, prefix: str = "", suffix: str = "") -> tuple[str, str, str]:
    match = re.fullmatch(prefix + INTERVAL + suffix, cell)
    assert match is not None, cell
    return match[1], match[2], match[3]


def _expected_marks(name: str) -> dict[tuple[str, str], tuple[str, str, str]]:
    expected = {}
    if name == "auroc-by-tier.svg":
        rows = _rows("headline.md", "By-run split")
        for tier, family in TIER_GROUPS:
            for detector in ("volume", "rule", "logistic", "boosted"):
                source_name = "volume (family-independent)" if detector == "volume" else detector
                row = _one(rows, Split="by run", Tier=tier, Family=family, Detector=source_name)
                if (tier, detector) == ("V0", "rule"):
                    assert row["AUROC"] == "not available at this tier"
                    continue
                expected[detector, f"{tier} {family}"] = _interval(row["AUROC"])
    elif name == "auroc-by-sharing-rate.svg":
        expected_by_rate = {}
        for detector in ("rule", "logistic"):
            rows = _rows("sharing-sweep.md", detector)
            assert [row["rate"] for row in rows] == ["0", "5", "10", "30"]
            for row in rows:
                rate = row["rate"]
                expected[detector, rate] = _interval(
                    row["overall AUROC"], suffix=r" \(\d+ of \d+ runs; [^\n]+\)",
                )
                value = row["expected 1 - q/2"]
                assert re.fullmatch(r"\d+\.\d{4}", value), value
                if detector == "rule":
                    expected_by_rate[rate] = value
                    expected["expected 1 - q/2", rate] = (value, value, value)
                else:
                    assert value == expected_by_rate[rate]
    elif name == "scope-by-context.svg":
        for heading in SCOPE_SECTIONS:
            row = _one(_rows("scope.md", heading), Metric="violation_vs_in_scope_auroc")
            expected["Strict", heading] = _interval(row["Strict"], suffix=r" bootstrap; .+")
    else:
        assert name == "containment-prevented.svg"
        rows = _rows("containment.md", CONTAINMENT_SECTION)
        for arm in CONTAINMENT_ARMS:
            row = _one(rows, arm=arm)
            cell = row["required reads prevented (pooled)"]
            series = (
                arm.split("-", 1)[0] if arm.startswith(("random-", "halt-", "oracle-"))
                else "detector"
            )
            if arm.startswith("oracle-"):
                match = re.fullmatch(
                    rf"\d+ of \d+ files; ({NUMBER}) \(degenerate bootstrap interval "
                    rf"\[({NUMBER}), ({NUMBER})\]: [^\n]+\)", cell,
                )
                assert match is not None, cell
                values = (match[1], match[2], match[3])
                assert values == ("1.000", "1.000", "1.000")
            else:
                values = _interval(cell, prefix=r"\d+ of \d+ files; ")
            expected[series, arm] = values
    assert len(expected) == FIGURE_COUNTS[name]
    return expected


def _marks(root: ET.Element) -> list[ET.Element]:
    marks = []
    for element in root.iter():
        if any(attribute in element.attrib for attribute in MARK_ATTRIBUTES[2:]):
            assert all(attribute in element.attrib for attribute in MARK_ATTRIBUTES), element.attrib
            assert element.tag in {
                SVG + tag for tag in ("g", "circle", "rect", "path", "polygon", "ellipse", "use")
            }, "Measurements must annotate plotted marks, not hidden metadata or text"
            marks.append(element)
    return marks


def _text(element: ET.Element) -> str:
    return " ".join(" ".join(element.itertext()).split())


@pytest.fixture(scope="module")
def generated(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    out = tmp_path_factory.mktemp("figures") / "first"
    paths = figures.main(data=DATA, out=out)
    assert isinstance(paths, list)
    assert len(paths) == 4
    assert all(isinstance(path, Path) and path.parent == out for path in paths)
    assert {path.name for path in paths} == set(FIGURE_COUNTS)
    assert {path.name for path in out.iterdir()} == set(FIGURE_COUNTS)
    return {path.name: path for path in paths}


@pytest.mark.parametrize("name", FIGURE_COUNTS)
def test_every_mark_matches_independently_parsed_source(
    generated: dict[str, Path], name: str,
) -> None:
    root = ET.parse(generated[name]).getroot()
    marks = _marks(root)
    assert len(marks) == FIGURE_COUNTS[name]
    actual = {}
    for mark in marks:
        key = (mark.attrib["data-series"], mark.attrib["data-label"])
        assert key not in actual, f"Duplicate plotted mark: {key}"
        values = tuple(mark.attrib[attribute] for attribute in MARK_ATTRIBUTES[2:])
        assert all(re.fullmatch(r"\d+\.\d{3,4}", value) for value in values), (key, values)
        actual[key] = values
    expected = _expected_marks(name)
    assert actual == expected

    description = root.find(SVG + "desc")
    assert description is not None
    prose = _text(description)
    # Every identity and every verbatim bound must also be accessible as ordinary text.
    for (series, label), values in expected.items():
        assert series in prose and label in prose, (series, label)
        for value in values:
            assert re.search(rf"(?<![\d.]){re.escape(value)}(?![\d.])", prose), value


def _axis_ticks(root: ET.Element, axis: str) -> dict[float, float]:
    # Read visible labels, never production scales or data-value/lo/hi attributes.
    anchor = "end" if axis == "y" else "middle"
    nodes = [node for node in root.iter(SVG + "text")
             if node.get("text-anchor") == anchor
             and re.fullmatch(r"\d+(?:\.\d+)?", _text(node))]
    assert len(nodes) >= 3
    if axis == "y":
        assert all(node.get("dominant-baseline") == "middle" for node in nodes)
        assert len({node.attrib["x"] for node in nodes}) == 1
    else:
        assert len({node.attrib["y"] for node in nodes}) == 1
    ticks = {float(_text(node)): float(node.attrib[axis]) for node in nodes}
    assert len(ticks) == len(nodes)
    return ticks


def _axis_scale(root: ET.Element, axis: str) -> tuple[float, float]:
    ticks = _axis_ticks(root, axis)
    low, high = min(ticks), max(ticks)
    slope = (high - low) / (ticks[high] - ticks[low])
    intercept = low - slope * ticks[low]
    for value, position in ticks.items():
        assert slope * position + intercept == pytest.approx(value, abs=abs(slope) / 2)
    return slope, intercept


def _vertices(node: ET.Element) -> list[tuple[float, float]]:
    return [tuple(map(float, pair.split(","))) for pair in node.attrib["points"].split()]


def _marker(mark: ET.Element) -> ET.Element:
    shapes = [node for node in mark if node.tag in {SVG + tag for tag in
              ("circle", "rect", "polygon")}]
    assert len(shapes) == 1
    return shapes[0]


def _marker_center(mark: ET.Element) -> tuple[float, float]:
    node = _marker(mark)
    if node.tag == SVG + "circle":
        return float(node.attrib["cx"]), float(node.attrib["cy"])
    if node.tag == SVG + "rect":
        return (float(node.attrib["x"]) + float(node.attrib["width"]) / 2,
                float(node.attrib["y"]) + float(node.attrib["height"]) / 2)
    # Area centroid works for both triangles and diamonds, without a series-specific offset.
    points = _vertices(node)
    edges = list(zip(points, points[1:] + points[:1], strict=True))
    crosses = [x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in edges]
    area = sum(crosses)
    assert area != 0
    return tuple(sum((p[axis] + q[axis]) * cross
                     for (p, q), cross in zip(edges, crosses, strict=True)) / (3 * area)
                 for axis in (0, 1))


def _assert_geometry(root: ET.Element, name: str) -> None:
    horizontal = name == "containment-prevented.svg"
    axis, cross_axis = ("x", "y") if horizontal else ("y", "x")
    slope, intercept = _axis_scale(root, axis)
    tolerance = abs(slope) / 2  # Half a pixel, expressed in the axis's value units.
    expected = _expected_marks(name)
    marks = _marks(root)
    assert len(marks) == len(expected)
    assert not any(node.get("transform") for node in root.iter() if node.tag != SVG + "text")

    def check(position: float, value: float) -> None:
        assert slope * position + intercept == pytest.approx(value, abs=tolerance), (
            name, position, value,
        )

    centers = {}
    for mark in marks:
        key = mark.attrib["data-series"], mark.attrib["data-label"]
        value, lo, hi = map(float, expected[key])
        if horizontal:
            bar = _marker(mark)
            assert bar.tag == SVG + "rect"
            start = float(bar.attrib["x"])
            check(start, 0)
            check(start + float(bar.attrib["width"]), value)
        else:
            centers[key] = _marker_center(mark)
            check(centers[key][1], value)
        lines = list(mark.iter(SVG + "line"))
        if key[0] == "expected 1 - q/2":
            assert not lines
            continue
        stems, caps = [], []
        for line in lines:
            ends = [float(line.attrib[f"{axis}{end}"]) for end in (1, 2)]
            if line.attrib[f"{cross_axis}1"] == line.attrib[f"{cross_axis}2"]:
                stems.append(line)
                actual = sorted(slope * end + intercept for end in ends)
                assert actual == pytest.approx([lo, hi], abs=tolerance)
            else:
                assert ends[0] == ends[1]
                caps.append(slope * ends[0] + intercept)
        # A halo may duplicate each stroke, but every copy must have the correct geometry.
        assert len(stems) in (1, 2) and len(caps) == 2 * len(stems)
        assert sorted(caps) == pytest.approx(sorted([lo, hi] * len(stems)), abs=tolerance)

    if name in {"auroc-by-tier.svg", "scope-by-context.svg"}:
        references = [line for line in root.findall(SVG + "line")
                      if line.get("stroke-dasharray")]
        assert len(references) == 1
        line = references[0]
        assert line.attrib["y1"] == line.attrib["y2"]
        assert float(line.attrib["x2"]) - float(line.attrib["x1"]) >= 360
        check(float(line.attrib["y1"]), 0.5)

    if name == "auroc-by-sharing-rate.svg":
        x_slope, x_intercept = _axis_scale(root, "x")
        offsets = {}
        for (series, rate), (x, _) in centers.items():
            tick_x = (float(rate) - x_intercept) / x_slope
            offset = x - tick_x
            if series == "logistic":
                assert abs(offset) <= 0.5
            else:
                assert 8 <= (-offset if series == "rule" else offset) <= 14
            if series in offsets:
                assert offset == pytest.approx(offsets[series], abs=0.5)
            offsets[series] = offset
        curves = root.findall(SVG + "polyline")
        assert len(curves) == 3
        assert {curve.attrib["data-series"] for curve in curves} == set(offsets)
        for curve in curves:
            series = curve.attrib["data-series"]
            points = _vertices(curve)
            assert len(points) == 4
            for (x, y), rate in zip(points, ("0", "5", "10", "30"), strict=True):
                assert x == pytest.approx(centers[series, rate][0], abs=0.5)
                check(y, float(expected[series, rate][0]))


@pytest.mark.parametrize("name", FIGURE_COUNTS)
def test_drawn_geometry_matches_source_within_half_a_pixel(
    generated: dict[str, Path], name: str,
) -> None:
    _assert_geometry(ET.parse(generated[name]).getroot(), name)


@pytest.mark.parametrize("name", FIGURE_COUNTS)
def test_geometry_rejects_shifted_markers_and_shortened_bars(
    generated: dict[str, Path], name: str,
) -> None:
    root = ET.parse(generated[name]).getroot()
    _assert_geometry(root, name)
    node = _marker(_marks(root)[0])
    if name == "containment-prevented.svg":
        node.set("width", str(float(node.attrib["width"]) * 0.9))
    else:
        slope, _ = _axis_scale(root, "y")
        shift = -0.1 / slope
        if node.tag == SVG + "polygon":
            node.set("points", " ".join(f"{x},{y + shift}" for x, y in _vertices(node)))
        else:
            coordinate = "cy" if node.tag == SVG + "circle" else "y"
            node.set(coordinate, str(float(node.attrib[coordinate]) + shift))
    with pytest.raises(AssertionError):
        _assert_geometry(root, name)


def test_tier_rule_has_exactly_one_unavailable_slot(generated: dict[str, Path]) -> None:
    root = ET.parse(generated["auroc-by-tier.svg"]).getroot()
    unavailable = [node for node in root.iter(SVG + "text") if _text(node) == "n/a"]
    assert len(unavailable) == 1
    assert unavailable[0].get("data-series") == "rule"
    assert unavailable[0].get("data-label") == "V0 generic"
    assert not any(attribute in unavailable[0].attrib for attribute in MARK_ATTRIBUTES[2:])
    assert ("rule", "V0 generic") not in {
        (mark.get("data-series"), mark.get("data-label")) for mark in _marks(root)
    }
    assert float(unavailable[0].attrib["y"]) > max(_axis_ticks(root, "y").values()) + 10


@pytest.mark.parametrize(("name", "phrases"), [
    ("auroc-by-tier.svg", ("volume (family-independent)", "chance")),
    ("auroc-by-sharing-rate.svg", (
        "q = realised fraction of test controls with a sharing team; by-run test split; "
        "V1 aggregation", "y axis 0.5 to 1.0",
    )),
    ("scope-by-context.svg", (
        "Strict labelling: scope violations against in-scope relays only "
        "(144 against 48 test runs)",
        "shared-login count (no context)", "C0: log only; C2: also each hand-off's file scope",
        "chance",
    )),
    ("containment-prevented.svg", (
        "Fraction of 432 required out-of-scope reads prevented; "
        "162 relay runs paired with uncontained twins", "halt-all", "oracle (label-informed)",
    )),
])
def test_explanatory_labels_are_visible_and_accessible(
    generated: dict[str, Path], name: str, phrases: tuple[str, ...],
) -> None:
    root = ET.parse(generated[name]).getroot()
    visible = " ".join(_text(node) for node in root.iter(SVG + "text"))
    description = root.find(SVG + "desc")
    assert description is not None
    for phrase in phrases:
        assert phrase in visible
        assert phrase in _text(description)
    if name == "auroc-by-sharing-rate.svg":
        assert sorted(_axis_ticks(root, "y")) == [0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
    elif name == "containment-prevented.svg":
        labels = {_text(node) for node in root.iter(SVG + "text")}
        assert "halt" not in labels and "oracle" not in labels
        for arm in CONTAINMENT_ARMS:
            label = arm.replace("halt-", "halt-all ").replace(
                "oracle-", "oracle (label-informed): ",
            )
            assert label in labels


@pytest.mark.parametrize("name", ["auroc-by-tier.svg", "scope-by-context.svg"])
def test_chance_is_identified_in_the_legend(generated: dict[str, Path], name: str) -> None:
    root = ET.parse(generated[name]).getroot()
    legend = root.find(f"{SVG}g[@id='legend']")
    assert legend is not None and "chance" in _text(legend)
    assert any(line.get("stroke-dasharray") for line in legend.iter(SVG + "line"))


def test_scope_intervals_are_drawn_over_hollow_markers(generated: dict[str, Path]) -> None:
    root = ET.parse(generated["scope-by-context.svg"]).getroot()
    for mark in _marks(root):
        marker = _marker(mark)
        assert marker.get("fill") in {"none", "white", "#ffffff", "#fafbf9"}
        assert all(list(mark).index(line) > list(mark).index(marker)
                   for line in mark.findall(SVG + "line"))


def test_bar_outlines_and_whisker_halos(generated: dict[str, Path]) -> None:
    root = ET.parse(generated["containment-prevented.svg"]).getroot()
    for mark in _marks(root):
        if mark.get("data-series") == "random":
            assert float(_marker(mark).get("stroke-width", "0")) >= 1
        lines = mark.findall(SVG + "line")
        halos = [line for line in lines if line.get("stroke") in {"white", "#ffffff"}]
        ink = [line for line in lines if line not in halos]
        assert len(halos) == len(ink) == 3
        for halo, line in zip(halos, ink, strict=True):
            assert [halo.get(key) for key in ("x1", "y1", "x2", "y2")] == [
                line.get(key) for key in ("x1", "y1", "x2", "y2")
            ]
            assert float(halo.attrib["stroke-width"]) > float(line.attrib["stroke-width"])
            assert list(mark).index(halo) < list(mark).index(line)


@pytest.mark.parametrize(("name", "labels"), [
    ("scope-by-context.svg", SCOPE_SECTIONS),
    ("containment-prevented.svg", CONTAINMENT_ARMS),
])
def test_required_mark_order(
    generated: dict[str, Path], name: str, labels: tuple[str, ...],
) -> None:
    root = ET.parse(generated[name]).getroot()
    assert [mark.attrib["data-label"] for mark in _marks(root)] == list(labels)


@pytest.mark.parametrize("name", FIGURE_COUNTS)
def test_svg_structure_accessibility_and_local_resources(
    generated: dict[str, Path], name: str,
) -> None:
    raw = generated[name].read_bytes()
    root = ET.fromstring(raw)
    assert root.tag == SVG + "svg"
    viewbox = root.attrib["viewBox"].split()
    assert len(viewbox) == 4 and viewbox[:3] == ["0", "0", "720"]
    assert float(viewbox[3]) > 0
    assert root.get("font-family") == "sans-serif"
    for tag in ("title", "desc"):
        node = root.find(SVG + tag)
        assert node is not None and _text(node)
    texts = [_text(node) for node in root.iter(SVG + "text")]
    visible = " ".join(texts)
    title = root.find(SVG + "title")
    assert title is not None and _text(title) in visible, "The title must also be visible"
    assert len({text for text in texts if re.fullmatch(r"\d+(?:\.\d+)?%?", text)}) >= 3
    assert re.search(r"fraction|proportion|unitless|0\s*(?:to|-)\s*1", visible, re.IGNORECASE)
    if name == "containment-prevented.svg":
        assert re.search(r"required.*reads.*prevented", visible, re.IGNORECASE)
        assert all(word in visible.lower() for word in ("detector", "random", "halt", "oracle"))
    else:
        assert "AUROC" in visible
        if name == "auroc-by-tier.svg":
            assert all(f"{tier} {family}" in visible for tier, family in TIER_GROUPS)
            assert all(series in visible for series in ("volume", "rule", "logistic", "boosted"))
        elif name == "auroc-by-sharing-rate.svg":
            assert re.search(r"sharing.*(?:%|percent)", visible, re.IGNORECASE)
            assert all(series in visible for series in ("rule", "logistic", "expected 1 - q/2"))
        else:
            assert "context" in visible.lower() and "Strict" in visible
    assert not root.findall(".//" + SVG + "script")
    assert not root.findall(".//" + SVG + "foreignObject")
    assert b"<!DOCTYPE" not in raw and b"<!ENTITY" not in raw
    assert b"@font-face" not in raw and b"@import" not in raw
    for element in root.iter():
        for attribute, value in element.attrib.items():
            assert not attribute.lower().startswith("on"), attribute
            if attribute.rsplit("}", 1)[-1] == "href":
                assert value.startswith("#"), value
            for resource in re.findall(r"url\(([^)]+)\)", value):
                assert resource.strip("\"' ").startswith("#"), resource
        if element.tag == SVG + "style":
            for resource in re.findall(r"url\(([^)]+)\)", element.text or ""):
                assert resource.strip("\"' ").startswith("#"), resource


@pytest.mark.parametrize("name", FIGURE_COUNTS)
def test_svg_has_a_light_background(generated: dict[str, Path], name: str) -> None:
    root = ET.parse(generated[name]).getroot()
    height = float(root.attrib["viewBox"].split()[3])
    backgrounds = [
        node for node in root.iter(SVG + "rect")
        if node.get("x", "0") == "0" and node.get("y", "0") == "0"
        and node.get("width") in {"100%", "720", "720.0", "720.000"}
        and (node.get("height") == "100%" or float(node.get("height", "0")) >= height)
    ]
    assert backgrounds, "A full-size light background is required"
    fill = backgrounds[0].get("fill", "")
    if fill == "white":
        return
    assert re.fullmatch(r"#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?", fill), fill
    digits = fill[1:]
    if len(digits) == 3:
        digits = "".join(digit * 2 for digit in digits)
    assert min(int(digits[index:index + 2], 16) for index in (0, 2, 4)) >= 230


@pytest.mark.parametrize("name", ["auroc-by-tier.svg", "scope-by-context.svg"])
def test_chance_reference_is_horizontal_at_half(generated: dict[str, Path], name: str) -> None:
    root = ET.parse(generated[name]).getroot()
    ticks = [node for node in root.iter(SVG + "text")
             if re.fullmatch(r"0\.50*", _text(node)) and "y" in node.attrib]
    assert ticks, "The 0.5 tick must be labelled"
    assert any(
        line.get("y1") == line.get("y2")
        and abs(float(line.get("x2", "0")) - float(line.get("x1", "0"))) >= 360
        and any(abs(float(line.get("y1", "-100")) - float(tick.attrib["y"])) <= 12
                for tick in ticks)
        for line in root.iter(SVG + "line")
    ), "Expected a full-width horizontal reference at AUROC 0.5"


@pytest.mark.parametrize("name", ["auroc-by-tier.svg", "auroc-by-sharing-rate.svg"])
def test_point_series_use_distinct_markers(generated: dict[str, Path], name: str) -> None:
    root = ET.parse(generated[name]).getroot()
    signatures = {}
    for mark in _marks(root):
        series = mark.attrib["data-series"]
        if series in signatures:
            continue
        shapes = []
        for node in mark.iter():
            tag = node.tag.removeprefix(SVG)
            if tag in {"circle", "rect", "ellipse", "use", "path", "polygon"}:
                # Ignore position/size, retaining the marker shape or referenced symbol.
                detail = node.get("href", node.get("{http://www.w3.org/1999/xlink}href", ""))
                if tag == "path":
                    detail = "".join(re.findall(r"[A-Za-z]", node.get("d", "")))
                elif tag == "polygon":
                    coordinates = [float(value) for value in re.findall(
                        r"-?\d+(?:\.\d+)?", node.attrib["points"],
                    )]
                    xs, ys = coordinates[::2], coordinates[1::2]
                    width, height = max(xs) - min(xs), max(ys) - min(ys)
                    assert width > 0 and height > 0
                    detail = str([(round((x - min(xs)) / width, 3),
                                   round((y - min(ys)) / height, 3))
                                  for x, y in zip(xs, ys, strict=True)])
                shapes.append((tag, detail))
        assert shapes, series
        signatures[series] = tuple(shapes)
    assert len(set(signatures.values())) == len(signatures)


def test_containment_bars_use_distinct_hatch_patterns(generated: dict[str, Path]) -> None:
    root = ET.parse(generated["containment-prevented.svg"]).getroot()
    patterns = {node.attrib["id"]: node for node in root.iter(SVG + "pattern")}
    assert len(patterns) >= 2
    used = set()
    for mark in _marks(root):
        assert any(node.tag == SVG + "rect" for node in mark.iter()), "Expected a bar"
        for node in mark.iter():
            for value in node.attrib.values():
                used.update(re.findall(r"url\(#([^)]+)\)", value))
    assert len(used) >= 2 and used <= patterns.keys()
    assert all(list(patterns[name]) for name in used), "Hatches must contain drawable geometry"


def test_outputs_are_byte_identical_lf_only_and_without_timestamps(
    generated: dict[str, Path], tmp_path: Path,
) -> None:
    second = figures.main(data=DATA, out=tmp_path / "different-directory")
    assert {path.name for path in second} == set(FIGURE_COUNTS)
    assert len(second) == 4
    for path in second:
        raw = path.read_bytes()
        assert raw == generated[path.name].read_bytes()
        assert raw.endswith(b"\n") and b"\r" not in raw
        assert not re.search(rb"\b\d{4}-\d{2}-\d{2}\b|\b\d{2}:\d{2}:\d{2}\b", raw)
        assert not re.search(rb"timestamp|generated[-_ ]at|created[-_ ]at", raw, re.IGNORECASE)


def test_cli_writes_the_same_four_figures(
    generated: dict[str, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    out = tmp_path / "cli-figures"
    assert cli_main(["figures", "--data", str(DATA), "--out", str(out)]) is None
    assert not capsys.readouterr().err
    assert {path.name for path in out.iterdir()} == set(FIGURE_COUNTS)
    for name, path in generated.items():
        assert (out / name).read_bytes() == path.read_bytes()


def _damage_table(
    original: str, heading: str, wanted: dict[str, str], column: str, damage: str,
    *, replacement: str = "",
) -> str:
    section = _section(original, heading)
    lines = _table_lines(section)
    cells = [_cells(line) for line in lines]
    header = cells[0]
    index = header.index(column)
    matching = [
        i for i in range(2, len(cells))
        if all(cells[i][header.index(key)] == value for key, value in wanted.items())
    ]
    assert len(matching) == 1, wanted
    target = matching[0]
    if damage == "missing-column":
        for row in cells:
            del row[index]
    elif damage == "reordered-header":
        header[0], header[1] = header[1], header[0]
    elif damage == "missing-row":
        del cells[target]
    elif damage == "duplicate-row":
        cells.insert(target, cells[target].copy())
    elif damage == "unparseable-cell":
        cells[target][index] = "not a measurement"
    elif damage == "replace-cell":
        cells[target][index] = replacement
    else:
        raise AssertionError(damage)
    replacement = "\n".join("| " + " | ".join(row) + " |" for row in cells)
    changed_section = section.replace("\n".join(lines), replacement, 1)
    assert changed_section != section
    return original.replace(section, changed_section, 1)


@pytest.mark.parametrize(("filename", "heading", "wanted", "column"), [
    ("headline.md", "By-run split",
     {"Split": "by run", "Tier": "V1", "Family": "aggregation", "Detector": "logistic"}, "AUROC"),
    ("sharing-sweep.md", "rule", {"rate": "5"}, "overall AUROC"),
    ("sharing-sweep.md", "logistic", {"rate": "30"}, "expected 1 - q/2"),
    ("scope.md", "C0: scope_rule", {"Metric": "violation_vs_in_scope_auroc"}, "Strict"),
    ("containment.md", CONTAINMENT_SECTION, {"arm": "oracle-revoke"},
     "required reads prevented (pooled)"),
])
def test_bad_tables_raise_named_error_and_cli_exits_nonzero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], filename: str,
    heading: str, wanted: dict[str, str], column: str,
) -> None:
    # Copy once per source/section, then restore after each mutation. No raw runs are evaluated.
    data = tmp_path / "data"
    shutil.copytree(DATA, data)
    source = data / filename
    original_bytes = source.read_bytes()
    original = source.read_text(encoding="utf-8")
    for damage in ("missing-file", "missing-section", "missing-column", "reordered-header",
                   "missing-row", "duplicate-row", "unparseable-cell"):
        try:
            if damage == "missing-file":
                source.unlink()
            elif damage == "missing-section":
                source.write_text(original.replace(f"## {heading}\n", "## absent\n", 1),
                                  encoding="utf-8", newline="\n")
            else:
                source.write_text(_damage_table(original, heading, wanted, column, damage),
                                  encoding="utf-8", newline="\n")
            with pytest.raises(figures.FigureError, match=re.escape(filename)) as error:
                figures.main(data=data, out=tmp_path / f"api-{damage}")
            message = str(error.value)
            assert message.strip() and issubclass(figures.FigureError, Exception)
            with pytest.raises(SystemExit) as exit_error:
                cli_main(["figures", "--data", str(data), "--out", str(tmp_path / f"cli-{damage}")])
            assert isinstance(exit_error.value.code, int) and exit_error.value.code != 0
            stderr = capsys.readouterr().err
            assert filename in stderr and message in stderr, (filename, damage, stderr)
            assert "Traceback" not in stderr
        finally:
            source.write_bytes(original_bytes)


def _copy_figure_reports(tmp_path: Path) -> Path:
    data = tmp_path / "data"
    data.mkdir()
    for name in ("headline.md", "sharing-sweep.md", "scope.md", "containment.md"):
        shutil.copyfile(DATA / name, data / name)
    return data


@pytest.mark.parametrize("filename,figure,expected", [
    ("scope.md", "scope-by-context.svg", "(12 against 4 test runs)"),
    ("containment.md", "containment-prevented.svg",
     "Fraction of 24 required out-of-scope reads prevented; "
     "8 relay runs paired with uncontained twins"),
])
def test_subtitles_use_report_counts_for_smaller_grids(
    tmp_path: Path, filename: str, figure: str, expected: str,
) -> None:
    data = _copy_figure_reports(tmp_path)
    source = data / filename
    text = source.read_text(encoding="utf-8")
    if filename == "scope.md":
        for heading in SCOPE_SECTIONS:
            wanted = {"Metric": "violation_vs_in_scope_auroc"}
            cell = _one(_rows(filename, heading), **wanted)["Strict"]
            cell = re.sub(r"\d+ positive / \d+ control", "12 positive / 4 control", cell)
            text = _damage_table(text, heading, wanted, "Strict", "replace-cell",
                                 replacement=cell)
    else:
        for arm in ("twin", *CONTAINMENT_ARMS):
            wanted = {"arm": arm}
            cell = ("0 of 24 files; 0.000 [0.000, 0.000]" if arm == "twin" else
                    "24 of 24 files; 1.000 [1.000, 1.000]" if arm.startswith("oracle-") else
                    "12 of 24 files; 0.500 [0.250, 0.750]")
            text = _damage_table(text, CONTAINMENT_SECTION, wanted, "pairs", "replace-cell",
                                 replacement="8")
            text = _damage_table(text, CONTAINMENT_SECTION, wanted,
                                 "required reads prevented (pooled)", "replace-cell",
                                 replacement=cell)
    source.write_text(text, encoding="utf-8", newline="\n")
    out = tmp_path / "figures"
    figures.main(data=data, out=out)
    root = ET.parse(out / figure).getroot()
    assert expected in " ".join(_text(node) for node in root.iter(SVG + "text"))
    description = root.find(SVG + "desc")
    assert description is not None and expected in _text(description)


@pytest.mark.parametrize("filename,heading,wanted,column,pattern,replacement", [
    ("scope.md", "C0: scope_rule", {"Metric": "violation_vs_in_scope_auroc"}, "Strict",
     r"\d+ positive / \d+ control", "143 positive / 48 control"),
    ("scope.md", "C0: scope_rule", {"Metric": "violation_vs_in_scope_auroc"}, "Strict",
     r"\d+ positive / \d+ control", "missing class counts"),
    ("scope.md", "C0: scope_rule", {"Metric": "violation_vs_in_scope_auroc"}, "Strict",
     r"\d+ positive / \d+ control", "0 positive / 48 control"),
    *[("containment.md", CONTAINMENT_SECTION, {"arm": arm}, "pairs", r"\d+", "161")
      for arm in ("twin", "rule-quarantine")],
    *[("containment.md", CONTAINMENT_SECTION, {"arm": "rule-quarantine"}, "pairs", r"\d+",
       value) for value in ("not a count", "0")],
    *[("containment.md", CONTAINMENT_SECTION, {"arm": arm},
       "required reads prevented (pooled)", r" of \d+ files;", " of 433 files;")
      for arm in ("twin", "rule-quarantine")],
    *[("sharing-sweep.md", "rule", {"rate": "5"}, "overall AUROC", INTERVAL, value)
      for value in ("0.499 [0.490, 0.510]", "0.600 [0.499, 0.700]", "0.490 [0.480, 0.499]",
                    "1.001 [0.900, 1.002]", "0.900 [0.800, 1.001]", "1.002 [1.001, 1.003]")],
])
def test_invalid_counts_and_sharing_bounds_raise_named_error_and_cli_exits_nonzero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], filename: str, heading: str,
    wanted: dict[str, str], column: str, pattern: str, replacement: str,
) -> None:
    data = _copy_figure_reports(tmp_path)
    source = data / filename
    original = source.read_text(encoding="utf-8")
    cell = _one(_rows(filename, heading), **wanted)[column]
    changed, count = re.subn(pattern, replacement, cell, count=1)
    assert count == 1 and changed != cell
    source.write_text(_damage_table(original, heading, wanted, column, "replace-cell",
                                    replacement=changed), encoding="utf-8", newline="\n")
    with pytest.raises(figures.FigureError, match=re.escape(filename)) as error:
        figures.main(data=data, out=tmp_path / "api")
    with pytest.raises(SystemExit) as exit_error:
        cli_main(["figures", "--data", str(data), "--out", str(tmp_path / "cli")])
    assert isinstance(exit_error.value.code, int) and exit_error.value.code != 0
    stderr = capsys.readouterr().err
    assert filename in stderr and str(error.value) in stderr
    assert "Traceback" not in stderr
    assert not (tmp_path / "api").exists() and not (tmp_path / "cli").exists()


@pytest.mark.parametrize("value", ("0.5000", "1.0000", "0.4999", "1.0001"))
def test_sharing_axis_bounds_apply_to_measurements_and_expected_reference(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], value: str,
) -> None:
    data = _copy_figure_reports(tmp_path)
    source = data / "sharing-sweep.md"
    text = source.read_text(encoding="utf-8")
    for detector in ("rule", "logistic"):
        text = _damage_table(text, detector, {"rate": "5"}, "expected 1 - q/2", "replace-cell",
                             replacement=value)
        if value in ("0.5000", "1.0000"):
            cell = _one(_rows(source.name, detector), rate="5")["overall AUROC"]
            rounded = value[:-1]
            cell = re.sub(INTERVAL, f"{rounded} [{rounded}, {rounded}]", cell, count=1)
            text = _damage_table(text, detector, {"rate": "5"}, "overall AUROC", "replace-cell",
                                 replacement=cell)
    source.write_text(text, encoding="utf-8", newline="\n")
    out = tmp_path / "figures"
    if value in ("0.5000", "1.0000"):
        figures.main(data=data, out=out)
        root = ET.parse(out / "auroc-by-sharing-rate.svg").getroot()
        assert sorted(_axis_ticks(root, "y")) == [0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
        marks = [mark for mark in _marks(root) if mark.get("data-label") == "5"]
        assert len(marks) == 3
        assert all(float(mark.get(attribute)) == float(value)
                   for mark in marks for attribute in MARK_ATTRIBUTES[2:])
    else:
        with pytest.raises(figures.FigureError, match="sharing-sweep.md") as error:
            figures.main(data=data, out=out)
        with pytest.raises(SystemExit) as exit_error:
            cli_main(["figures", "--data", str(data), "--out", str(out)])
        assert isinstance(exit_error.value.code, int) and exit_error.value.code != 0
        stderr = capsys.readouterr().err
        assert "sharing-sweep.md" in stderr and str(error.value) in stderr
        assert "Traceback" not in stderr and not out.exists()


def test_figures_imports_only_stdlib_and_swarmtrace() -> None:
    path = PROJECT_ROOT / "src" / "swarmtrace" / "reproduce" / "figures.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        names = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            name = "." * node.level + (node.module or "")
            names = [resolve_name(name, "swarmtrace.reproduce") if node.level else name]
        for name in names:
            assert name.split(".", 1)[0] in sys.stdlib_module_names | {"swarmtrace"}, (
                node.lineno, name,
            )


def test_committed_figures_equal_fresh_generation(generated: dict[str, Path]) -> None:
    committed = PROJECT_ROOT / "docs" / "figures"
    assert {path.name for path in committed.glob("*.svg")} == set(FIGURE_COUNTS)
    for name, path in generated.items():
        assert (committed / name).read_bytes() == path.read_bytes(), name
