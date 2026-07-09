"""Tests for rendering the comparison table and charts section."""

from __future__ import annotations

from outcome_receipts.charts import render_chart
from outcome_receipts.comparison import ComparisonResult, ComparisonRow
from outcome_receipts.models import ChartSpec, Figure, Receipt
from outcome_receipts.report import (
    render_charts_section,
    render_comparison_table,
    render_report,
)


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


def _row(description: str) -> ComparisonRow:
    return ComparisonRow(
        base_metric_id="clients",
        description=description,
        prior=_figure("clients__q1", 12.0, "12"),
        current=_figure("clients__q2", 14.0, "14"),
        delta=_figure("clients__delta", 2.0, "2"),
        direction="increase",
    )


def test_comparison_table_renders_values_change_and_direction() -> None:
    result = ComparisonResult(
        current_label="Q2 2025",
        prior_label="Q1 2025",
        rows=(_row("Clients enrolled"),),
        figures=(),
    )
    table = render_comparison_table(result)
    assert "Comparing Q2 2025 with Q1 2025" in table
    assert "| Clients enrolled | 12 | 14 | 2 | increase |" in table
    assert "percentage points" in table


def test_comparison_table_falls_back_to_metric_id_when_no_description() -> None:
    result = ComparisonResult(current_label="Q2", prior_label="Q1", rows=(_row(""),), figures=())
    table = render_comparison_table(result)
    assert "| clients |" in table


def test_charts_section_links_image_and_inlines_data_table() -> None:
    spec = ChartSpec(chart_id="c", title="Outcomes", kind="bar", metric_ids=("a",))
    chart = render_chart(spec, [_figure("a", 5.0, "5")])
    section = render_charts_section([chart], chart_dir="charts")
    assert "![Outcomes (see data table below)](charts/c.svg)" in section
    assert "| Category | Value |" in section
    assert "| a | 5 |" in section


def test_render_report_without_optional_sections_is_just_narrative_and_receipts() -> None:
    figures = [_figure("a", 5.0, "5")]
    report = render_report("Title", "We served 5 clients.", figures)
    assert "## Period comparison" not in report
    assert "## Charts" not in report
    assert "## Receipts" in report
    assert "We served 5 clients." in report
