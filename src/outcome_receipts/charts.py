"""Charts drawn from grounded figures, with an accessible data table.

A chart here has no data of its own. Its bars or points are the values of figures
that were already computed by a deterministic query and already carry a receipt.
The chart reads ``figure.value`` for geometry and ``figure.display`` for every
label, so there is no second, ungrounded path to a number on the page.

Two surfaces come out of one chart. The SVG is the visual rendering; its only
numbers are pixel coordinates derived from the grounded values, and those
coordinates are presentation, not claims, so they are kept out of the report's
prose and out of the grounding gate. The accessible data table is the text
equivalent: it carries the actual figures as their display strings, and those
are grounded exactly like any number in the narrative. The SVG is written beside
the report and referenced as an image; the data table is inlined as its
alternative, so a screen-reader user reads the same grounded numbers a sighted
reader sees in the bars.

A bar height is a claim. So is the slope of a line. A figure withheld by
small-cell suppression has no value to draw, and drawing it as zero made the
picture assert what the same page refuses to assert in text: an empty bar on the
axis baseline, and a polyline dropping to the floor and recovering, inventing a
collapse across data that was withheld on purpose. A withheld point is therefore
drawn as an explicit absence:

- a bar becomes a full-height hatched slot with a dashed outline in the muted
  grey used for the axis, never the data colour, labelled with the same
  ``[SUPPRESSED]`` marker the rest of the report uses;
- a line breaks. The polyline is emitted once per run of consecutive drawable
  points, so no segment spans a withheld one, and the withheld position gets a
  dashed vertical rule rather than a plotted point;
- withheld figures are excluded from the axis scale, so they cannot flatten the
  points that are drawn by pretending to be zeros.

The absence is announced, not only drawn: the marker carries a ``<title>``, the
chart's ``<desc>`` names how many points are withheld, and the accessible data
table already carries ``[SUPPRESSED]`` as text.

Pure standard library: the SVG is assembled as text, so the project keeps its
zero-dependency, offline posture.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from outcome_receipts.models import ChartSpec, Figure

# Fixed canvas geometry, so the SVG is byte-for-byte reproducible across runs.
_WIDTH = 640
_HEIGHT = 360
_PAD_LEFT = 48
_PAD_RIGHT = 24
_PAD_TOP = 48
_PAD_BOTTOM = 64


@dataclass(frozen=True)
class ChartPoint:
    """One datum: its label, the grounded numeric value, and its display string.

    ``value`` is ``None`` when the figure was withheld by small-cell
    suppression. ``suppressed`` says the same thing from the receipt's side, so
    a caller can branch on the state rather than on the absence of a number; the
    two always agree for a figure that came through ``suppress_figures``, and a
    point counts as withheld if either says so.
    """

    label: str
    value: float | None
    display: str
    suppressed: bool = False

    @property
    def withheld(self) -> bool:
        """True when there is no value here to draw."""

        return self.suppressed or self.value is None


@dataclass(frozen=True)
class Chart:
    """A rendered chart and its accessible equivalent.

    ``svg`` is the standalone image. ``data_table`` is the Markdown table that
    carries the same numbers as text. ``displays`` is every numeric display the
    chart asserts, the tokens the grounding gate must bind, so a caller can verify
    a chart is fully grounded before export.
    """

    chart_id: str
    title: str
    kind: str
    points: tuple[ChartPoint, ...]
    svg: str
    data_table: str

    @property
    def displays(self) -> tuple[str, ...]:
        return tuple(point.display for point in self.points)

    @property
    def claims_text(self) -> str:
        """The chart's numbers as plain text, for the grounding gate.

        Only the figure displays appear here, never the SVG's pixel coordinates,
        so grounding a chart checks its claims and not its presentation.
        """

        return " ".join(point.display for point in self.points)


def _points(spec: ChartSpec, by_id: Mapping[str, Figure]) -> tuple[ChartPoint, ...]:
    points: list[ChartPoint] = []
    for index, metric_id in enumerate(spec.metric_ids):
        if metric_id not in by_id:
            raise KeyError(f"chart {spec.chart_id!r} references unknown metric {metric_id!r}")
        figure = by_id[metric_id]
        points.append(
            ChartPoint(
                label=spec.label_for(index),
                value=figure.value,
                display=figure.display,
                suppressed=figure.receipt.suppressed,
            )
        )
    return tuple(points)


def _esc(text: str) -> str:
    """Escape text for inclusion in SVG/XML."""

    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )


def _plot_box() -> tuple[int, int, int, int]:
    left = _PAD_LEFT
    top = _PAD_TOP
    width = _WIDTH - _PAD_LEFT - _PAD_RIGHT
    height = _HEIGHT - _PAD_TOP - _PAD_BOTTOM
    return left, top, width, height


def _scale_max(points: Sequence[ChartPoint]) -> float:
    """The axis maximum, over the points that actually carry a value.

    A withheld point contributes nothing. Values are evaluated by their absolute
    magnitude so that a negative delta figure scales the axis appropriately.
    """

    top = max((abs(p.value) for p in points if p.value is not None), default=0.0)
    return top if top > 0 else 1.0


def _withheld_label(x: float, top: float, label: str) -> str:
    """The ``[SUPPRESSED]`` text over an absence marker.

    Placed inside the top of the plot box rather than above it: a withheld
    marker spans the full height, so the usual "just above the bar" position
    would collide with the chart title.
    """

    return (
        f'<text x="{x:.1f}" y="{top + 16:.1f}" text-anchor="middle" font-size="13" '
        f'fill="#1a202c">{_esc(label)}</text>'
    )


def _axis_label(x: float, top: float, height: float, label: str) -> str:
    return (
        f'<text x="{x:.1f}" y="{top + height + 18:.1f}" text-anchor="middle" '
        f'font-size="12" fill="#4a5568">{_esc(label)}</text>'
    )


def _bar_svg_body(points: Sequence[ChartPoint], hatch_id: str) -> list[str]:
    left, top, width, height = _plot_box()
    scale = _scale_max(points)
    n = len(points)
    slot = width / n if n else width
    bar_w = slot * 0.6
    body: list[str] = []
    for i, point in enumerate(points):
        x = left + slot * i + (slot - bar_w) / 2
        centre = x + bar_w / 2
        if point.withheld:
            # A full-height hatched, dashed slot in the axis grey. It occupies
            # the position without asserting a magnitude, and it is visibly not
            # a bar: a zero-height rectangle on the baseline said "nobody",
            # which is the one thing the report refuses to say here.
            body.append(
                f'<rect x="{x:.1f}" y="{top:.1f}" width="{bar_w:.1f}" height="{height:.1f}" '
                f'fill="url(#{hatch_id})" stroke="#4a5568" stroke-width="1" '
                'stroke-dasharray="4 3"><title>'
                f"{_esc(point.label)}: {_esc(point.display)} — withheld under the "
                "small-cell suppression policy; this is not a value of zero"
                "</title></rect>"
            )
            body.append(_withheld_label(centre, top, point.display))
            body.append(_axis_label(centre, top, height, point.label))
            continue
        value = abs(point.value) if point.value is not None else 0.0
        bar_h = (value / scale) * height if value > 0 else 0.0
        y = top + height - bar_h
        body.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{bar_h:.1f}" '
            f'fill="#2b6cb0"><title>{_esc(point.label)}: {_esc(point.display)}</title></rect>'
        )
        body.append(
            f'<text x="{centre:.1f}" y="{y - 6:.1f}" text-anchor="middle" '
            f'font-size="13" fill="#1a202c">{_esc(point.display)}</text>'
        )
        body.append(_axis_label(centre, top, height, point.label))
    return body


def _line_segments(
    coords: Sequence[tuple[float, float] | None],
) -> list[list[tuple[float, float]]]:
    """Split plotted coordinates into runs unbroken by a withheld point.

    One polyline per run, so no drawn segment ever spans a gap. Joining across
    one would draw a slope between two real values as though the withheld point
    lay on it, which is a claim about the hidden number.
    """

    segments: list[list[tuple[float, float]]] = []
    current: list[tuple[float, float]] = []
    for coord in coords:
        if coord is None:
            if len(current) > 1:
                segments.append(current)
            current = []
        else:
            current.append(coord)
    if len(current) > 1:
        segments.append(current)
    return segments


def _line_svg_body(points: Sequence[ChartPoint]) -> list[str]:
    left, top, width, height = _plot_box()
    scale = _scale_max(points)
    n = len(points)
    step = width / (n - 1) if n > 1 else 0.0
    body: list[str] = []
    coords: list[tuple[float, float] | None] = []
    xs: list[float] = []
    for i, point in enumerate(points):
        x = left + (step * i if n > 1 else width / 2)
        xs.append(x)
        if point.withheld:
            coords.append(None)
            continue
        value = abs(point.value) if point.value is not None else 0.0
        coords.append((x, top + height - (value / scale) * height))

    for segment in _line_segments(coords):
        path = " ".join(f"{x:.1f},{y:.1f}" for x, y in segment)
        body.append(f'<polyline fill="none" stroke="#2b6cb0" stroke-width="2" points="{path}"/>')

    for x, coord, point in zip(xs, coords, points, strict=True):
        if coord is None:
            # A dashed full-height rule marks where the series is interrupted.
            # No plotted point: there is no y for it, and putting one on the
            # axis floor is what drew the false collapse.
            body.append(
                f'<line x1="{x:.1f}" y1="{top:.1f}" x2="{x:.1f}" y2="{top + height:.1f}" '
                'stroke="#4a5568" stroke-width="1" stroke-dasharray="4 3"><title>'
                f"{_esc(point.label)}: {_esc(point.display)} — withheld under the "
                "small-cell suppression policy; the series is interrupted here"
                "</title></line>"
            )
            body.append(_withheld_label(x, top, point.display))
            body.append(_axis_label(x, top, height, point.label))
            continue
        _, y = coord
        body.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="#2b6cb0"><title>'
            f"{_esc(point.label)}: {_esc(point.display)}</title></circle>"
        )
        body.append(
            f'<text x="{x:.1f}" y="{y - 10:.1f}" text-anchor="middle" font-size="13" '
            f'fill="#1a202c">{_esc(point.display)}</text>'
        )
        body.append(_axis_label(x, top, height, point.label))
    return body


def _hatch_defs(hatch_id: str) -> str:
    """The diagonal hatch used to fill a withheld slot.

    Deliberately not the data colour: a reader scanning the chart has to be able
    to tell at a glance that nothing was plotted there. The id is namespaced by
    chart so several SVGs can be inlined into one document without colliding.
    """

    return (
        f'<defs><pattern id="{hatch_id}" width="8" height="8" '
        'patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
        '<rect width="8" height="8" fill="#ffffff"/>'
        '<line x1="0" y1="0" x2="0" y2="8" stroke="#a0aec0" stroke-width="3"/>'
        "</pattern></defs>"
    )


def _svg(spec: ChartSpec, points: Sequence[ChartPoint]) -> str:
    left, top, width, height = _plot_box()
    title_id = f"{spec.chart_id}-title"
    desc_id = f"{spec.chart_id}-desc"
    hatch_id = f"{spec.chart_id}-withheld"
    n_withheld = sum(1 for point in points if point.withheld)
    desc = (
        f"{spec.kind} chart. The values are listed in the data table below the "
        "chart. Each value is computed by a deterministic query and carries a receipt."
    )
    if n_withheld:
        # Said in the description, not only drawn, because the hatch and the
        # broken line are visual signals a screen-reader user never receives.
        noun = "category is" if n_withheld == 1 else "categories are"
        drawn = "no bar is drawn" if spec.kind == "bar" else "the line is broken"
        desc += (
            f" {n_withheld} {noun} withheld under the small-cell suppression "
            f"policy: {drawn} there, and the position is marked but carries no "
            "value. A withheld category is not a value of zero."
        )
    head = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{_WIDTH}" height="{_HEIGHT}" '
        f'viewBox="0 0 {_WIDTH} {_HEIGHT}" role="img" '
        f'aria-labelledby="{title_id} {desc_id}">',
        f'<title id="{title_id}">{_esc(spec.title)}</title>',
        f'<desc id="{desc_id}">{_esc(desc)}</desc>',
        f'<rect x="0" y="0" width="{_WIDTH}" height="{_HEIGHT}" fill="#ffffff"/>',
        # x-axis baseline
        f'<line x1="{left}" y1="{top + height}" x2="{left + width}" y2="{top + height}" '
        'stroke="#a0aec0" stroke-width="1"/>',
        f'<text x="{left}" y="{top - 18}" font-size="15" fill="#1a202c" '
        f'font-weight="bold">{_esc(spec.title)}</text>',
    ]
    if n_withheld and spec.kind == "bar":
        head.insert(1, _hatch_defs(hatch_id))
    body = _bar_svg_body(points, hatch_id) if spec.kind == "bar" else _line_svg_body(points)
    return "\n".join([*head, *body, "</svg>"]) + "\n"


def _data_table(points: Sequence[ChartPoint]) -> str:
    lines = ["| Category | Value |", "|----------|-------|"]
    for point in points:
        lines.append(f"| {point.label} | {point.display} |")
    return "\n".join(lines)


_KINDS = frozenset({"bar", "line"})


def render_chart(spec: ChartSpec, figures: Sequence[Figure]) -> Chart:
    """Render one chart from the figures it names.

    Raises ``ValueError`` for an unknown chart kind and ``KeyError`` for a metric
    id that names no computed figure, so a misconfigured chart fails loudly rather
    than drawing nothing or guessing a value.
    """

    if spec.kind not in _KINDS:
        raise ValueError(
            f"chart {spec.chart_id!r} kind {spec.kind!r} must be one of {sorted(_KINDS)}"
        )
    by_id = {figure.metric_id: figure for figure in figures}
    points = _points(spec, by_id)
    return Chart(
        chart_id=spec.chart_id,
        title=spec.title,
        kind=spec.kind,
        points=points,
        svg=_svg(spec, points),
        data_table=_data_table(points),
    )


def render_charts(specs: Sequence[ChartSpec], figures: Sequence[Figure]) -> list[Chart]:
    """Render every chart for a report."""

    return [render_chart(spec, figures) for spec in specs]
