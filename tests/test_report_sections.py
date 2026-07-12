"""Tests for rendering the comparison table and charts section."""

from __future__ import annotations

import pytest

from outcome_receipts.charts import render_chart
from outcome_receipts.comparison import ComparisonResult, ComparisonRow
from outcome_receipts.models import ChartSpec, Figure, Receipt
from outcome_receipts.provenance import Provenance
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


# --- EN/ES report-output parity (E9) -------------------------------------


def _receipt(metric_id: str, value: float, definition: str) -> Receipt:
    return Receipt(
        metric_id=metric_id,
        value_sql=f"SELECT count(*) FROM enrollments WHERE metric = '{metric_id}'",  # noqa: S608 — fixture literal, never executed
        row_count=137,
        slice_hash="sha256:9f8c1e",
        value=value,
        unit="count",
        computed_at="2026-07-02T00:00:00Z",
        definition=definition,
    )


def _figure_full(metric_id: str, value: float, display: str, definition: str) -> Figure:
    return Figure(
        metric_id=metric_id,
        value=value,
        display=display,
        receipt=_receipt(metric_id, value, definition),
    )


def _full_report(locale: str) -> str:
    figures = [
        _figure_full("clients_served", 137.0, "137", "Distinct clients enrolled."),
        _figure_full("exit_rate", 0.62, "62.0%", "Share exiting to housing."),
    ]
    comparison = ComparisonResult(
        current_label="Q2 2025",
        prior_label="Q1 2025",
        rows=(_row("Clients enrolled"),),
        figures=(),
    )
    spec = ChartSpec(chart_id="c", title="Outcomes", kind="bar", metric_ids=("a",))
    chart = render_chart(spec, [_figure("a", 5.0, "5")])
    provenance = Provenance(
        numbers_bound=8,
        numbers_unbound=0,
        approved_by="Ana",
        approved_at="2026-07-02T00:00:00Z",
    )
    return render_report(
        "Program report",
        "We served 137 clients; 62.0% exited to housing.",
        figures,
        comparison=comparison,
        charts=[chart],
        provenance=provenance,
        locale=locale,  # type: ignore[arg-type]
    )


def test_default_locale_matches_explicit_english() -> None:
    figures = [_figure_full("clients_served", 137.0, "137", "Distinct clients.")]
    default = render_report("Title", "We served 137 clients.", figures)
    english = render_report("Title", "We served 137 clients.", figures, locale="en")
    assert default == english
    # Guards the current English snapshot: headings and labels unchanged.
    assert "## Receipts" in default
    assert "  - definition: Distinct clients." in default
    assert "  - rows in slice: 137" in default
    assert "  - slice hash: `sha256:9f8c1e`" in default


def test_spanish_translates_prose_and_labels() -> None:
    report = _full_report("es")
    assert "## Comparación de periodos" in report
    assert "## Gráficos" in report
    assert "## Recibos" in report
    assert "## Procedencia" in report
    assert "| Resultado | Q1 2025 | Q2 2025 | Cambio | Dirección |" in report
    assert "puntos porcentuales" in report
    assert "  - definición: " in report
    assert "  - consulta: `" in report
    assert "  - filas en el segmento: 137" in report
    assert "  - hash del segmento: `sha256:9f8c1e`" in report
    assert "  - calculado en: 2026-07-02T00:00:00Z" in report
    assert "  - tipo: output" in report
    assert "| Clients enrolled | 12 | 14 | 2 | aumento |" in report
    assert "Outcomes (véase la tabla de datos a continuación)" in report
    assert "aprobado para su exportación por Ana el 2026-07-02T00:00:00Z" in report
    # English headings must be gone in the Spanish render.
    assert "## Period comparison" not in report
    assert "## Receipts" not in report


def test_figures_and_receipts_are_byte_identical_across_locales() -> None:
    en = _full_report("en")
    es = _full_report("es")
    # Every receipted datum a reader could cite appears verbatim in both locales:
    # numbers, SQL, and hashes are data, not prose, so they never translate.
    for token in (
        "137",
        "62.0%",
        "sha256:9f8c1e",
        "2026-07-02T00:00:00Z",
        "SELECT count(*) FROM enrollments WHERE metric = 'clients_served'",
        "SELECT count(*) FROM enrollments WHERE metric = 'exit_rate'",
    ):
        assert token in en
        assert token in es


@pytest.mark.parametrize("locale", ["en", "es"])
def test_both_locales_render_without_raising(locale: str) -> None:
    report = _full_report(locale)
    assert report.startswith("# Program report")
    assert report.endswith("\n")
