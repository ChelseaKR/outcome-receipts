"""Tests for charts drawn from grounded figures.

The load-bearing property is that a chart has no data path of its own: its bars
and points are the figures' values, and every number it renders is a figure
display, so the grounding gate verifies a chart the same way it verifies prose.
These tests pin that, plus the accessible data table and the SVG's image role.
"""

from __future__ import annotations

import pytest

from outcome_receipts.charts import render_chart, render_charts
from outcome_receipts.grounding import ground
from outcome_receipts.models import ChartSpec, Figure, Receipt


def _figure(metric_id: str, value: float, display: str) -> Figure:
    receipt = Receipt(
        metric_id=metric_id,
        value_sql="SELECT 1",
        row_count=1,
        slice_hash="x",
        value=value,
        unit="count",
        computed_at="t",
    )
    return Figure(metric_id=metric_id, value=value, display=display, receipt=receipt)


FIGURES = [
    _figure("permanent", 13.0, "13"),
    _figure("temporary", 3.0, "3"),
    _figure("unknown", 2.0, "2"),
]

BAR = ChartSpec(
    chart_id="exits",
    title="Exits by destination",
    kind="bar",
    metric_ids=("permanent", "temporary", "unknown"),
    labels=("Permanent", "Temporary", "Unknown"),
)


def test_chart_points_are_the_figure_values_not_a_separate_path() -> None:
    chart = render_chart(BAR, FIGURES)
    assert [p.value for p in chart.points] == [13.0, 3.0, 2.0]
    assert chart.displays == ("13", "3", "2")


def test_chart_numbers_all_ground_to_the_figures() -> None:
    chart = render_chart(BAR, FIGURES)
    result = ground(chart.claims_text, FIGURES)
    assert result.ok
    assert result.total == 3


def test_claims_text_excludes_svg_geometry() -> None:
    # The SVG has pixel coordinates; the claims text the gate sees must not, or a
    # presentational number would be mistaken for an ungrounded claim.
    chart = render_chart(BAR, FIGURES)
    assert "640" in chart.svg  # canvas width is in the image
    assert "640" not in chart.claims_text


def test_data_table_carries_the_grounded_numbers() -> None:
    chart = render_chart(BAR, FIGURES)
    assert "| Permanent | 13 |" in chart.data_table
    assert "| Unknown | 2 |" in chart.data_table


def test_svg_is_an_accessible_image() -> None:
    chart = render_chart(BAR, FIGURES)
    assert 'role="img"' in chart.svg
    assert "<title" in chart.svg
    assert "<desc" in chart.svg
    assert "Exits by destination" in chart.svg


def test_line_chart_renders_a_polyline() -> None:
    spec = ChartSpec(
        chart_id="trend", title="Trend", kind="line", metric_ids=("permanent", "temporary")
    )
    chart = render_chart(spec, FIGURES)
    assert "<polyline" in chart.svg
    assert chart.displays == ("13", "3")


def test_label_falls_back_to_metric_id() -> None:
    spec = ChartSpec(chart_id="c", title="t", kind="bar", metric_ids=("permanent",))
    chart = render_chart(spec, FIGURES)
    assert chart.points[0].label == "permanent"


def test_unknown_metric_raises() -> None:
    spec = ChartSpec(chart_id="c", title="t", kind="bar", metric_ids=("missing",))
    with pytest.raises(KeyError, match="unknown metric"):
        render_chart(spec, FIGURES)


def test_unknown_kind_raises() -> None:
    spec = ChartSpec(chart_id="c", title="t", kind="pie", metric_ids=("permanent",))
    with pytest.raises(ValueError, match="kind"):
        render_chart(spec, FIGURES)


def test_render_charts_handles_several() -> None:
    charts = render_charts([BAR, BAR], FIGURES)
    assert len(charts) == 2
