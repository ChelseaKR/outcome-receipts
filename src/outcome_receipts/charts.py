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
    """One datum: its label, the grounded numeric value, and its display string."""

    label: str
    value: float
    display: str


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
            ChartPoint(label=spec.label_for(index), value=figure.value, display=figure.display)
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
    top = max((p.value for p in points), default=0.0)
    return top if top > 0 else 1.0


def _bar_svg_body(points: Sequence[ChartPoint]) -> list[str]:
    left, top, width, height = _plot_box()
    scale = _scale_max(points)
    n = len(points)
    slot = width / n if n else width
    bar_w = slot * 0.6
    body: list[str] = []
    for i, point in enumerate(points):
        bar_h = (point.value / scale) * height if point.value > 0 else 0.0
        x = left + slot * i + (slot - bar_w) / 2
        y = top + height - bar_h
        body.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{bar_h:.1f}" '
            f'fill="#2b6cb0"><title>{_esc(point.label)}: {_esc(point.display)}</title></rect>'
        )
        body.append(
            f'<text x="{x + bar_w / 2:.1f}" y="{y - 6:.1f}" text-anchor="middle" '
            f'font-size="13" fill="#1a202c">{_esc(point.display)}</text>'
        )
        body.append(
            f'<text x="{x + bar_w / 2:.1f}" y="{top + height + 18:.1f}" text-anchor="middle" '
            f'font-size="12" fill="#4a5568">{_esc(point.label)}</text>'
        )
    return body


def _line_svg_body(points: Sequence[ChartPoint]) -> list[str]:
    left, top, width, height = _plot_box()
    scale = _scale_max(points)
    n = len(points)
    step = width / (n - 1) if n > 1 else 0.0
    coords: list[tuple[float, float]] = []
    for i, point in enumerate(points):
        x = left + (step * i if n > 1 else width / 2)
        y = top + height - (point.value / scale) * height
        coords.append((x, y))
    body: list[str] = []
    if len(coords) > 1:
        path = " ".join(f"{x:.1f},{y:.1f}" for x, y in coords)
        body.append(f'<polyline fill="none" stroke="#2b6cb0" stroke-width="2" points="{path}"/>')
    for (x, y), point in zip(coords, points, strict=True):
        body.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="#2b6cb0"><title>'
            f"{_esc(point.label)}: {_esc(point.display)}</title></circle>"
        )
        body.append(
            f'<text x="{x:.1f}" y="{y - 10:.1f}" text-anchor="middle" font-size="13" '
            f'fill="#1a202c">{_esc(point.display)}</text>'
        )
        body.append(
            f'<text x="{x:.1f}" y="{top + height + 18:.1f}" text-anchor="middle" font-size="12" '
            f'fill="#4a5568">{_esc(point.label)}</text>'
        )
    return body


def _svg(spec: ChartSpec, points: Sequence[ChartPoint]) -> str:
    left, top, width, height = _plot_box()
    title_id = f"{spec.chart_id}-title"
    desc_id = f"{spec.chart_id}-desc"
    desc = (
        f"{spec.kind} chart. The values are listed in the data table below the "
        "chart. Each value is computed by a deterministic query and carries a receipt."
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
    body = _bar_svg_body(points) if spec.kind == "bar" else _line_svg_body(points)
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
