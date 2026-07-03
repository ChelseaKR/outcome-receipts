"""Tests for parsing the optional [[charts]], [comparison], and [reconciliation]
spec sections."""

from __future__ import annotations

from pathlib import Path

import pytest

from outcome_receipts.config import load_spec

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def test_grant_report_parses_charts_and_comparison() -> None:
    spec = load_spec(EXAMPLES / "grant-report" / "report.toml")
    assert spec.report.title == "Housing Program Grant Report"
    chart_ids = {c.chart_id for c in spec.report.charts}
    assert chart_ids == {"exits-by-destination", "permanent-by-quarter"}
    comparison = spec.report.comparison
    assert comparison is not None
    assert comparison.current == "q2"
    assert comparison.prior == "q1"
    assert {p.period_id for p in comparison.periods} == {"q1", "q2"}
    assert {m.metric_id for m in comparison.metrics} == {
        "clients_served",
        "exits",
        "exits_permanent",
        "pct_permanent",
    }


def test_board_report_uses_a_line_chart() -> None:
    spec = load_spec(EXAMPLES / "board-report" / "report.toml")
    [chart] = spec.report.charts
    assert chart.kind == "line"
    assert chart.metric_ids == ("clients_served__q1", "clients_served__q2")


def test_board_report_parses_reconciliation() -> None:
    spec = load_spec(EXAMPLES / "board-report" / "report.toml")
    reconciliation = spec.report.reconciliation
    assert reconciliation is not None
    assert reconciliation.current == "q2"
    assert reconciliation.prior == "q1"
    assert {p.period_id for p in reconciliation.periods} == {"q1", "q2"}
    [row] = reconciliation.rows
    assert row.label == "Permanent-housing exits vs. program spend"
    # Each side is a metric with the {period} placeholder, id-derived from the label.
    assert row.outcome.metric_id.endswith("_outcome")
    assert row.financial.metric_id.endswith("_financial")
    assert "{period}" in row.outcome.value_sql
    assert "{period}" in row.financial.value_sql


def test_existing_housing_demo_has_no_optional_sections() -> None:
    spec = load_spec(EXAMPLES / "housing-demo" / "report.toml")
    assert spec.report.charts == ()
    assert spec.report.comparison is None
    assert spec.report.reconciliation is None


def _write(tmp_path: Path, body: str) -> Path:
    spec = tmp_path / "report.toml"
    spec.write_text(
        '[data]\npath = "x.csv"\n[report]\ntemplate = "{m}"\n'
        '[metrics.m]\nvalue_sql = "SELECT 1"\nslice_sql = "SELECT 1"\n' + body,
        encoding="utf-8",
    )
    return spec


def test_chart_with_unknown_kind_is_rejected(tmp_path: Path) -> None:
    spec = _write(tmp_path, '[[charts]]\nid = "c"\nkind = "pie"\nmetrics = ["m"]\n')
    with pytest.raises(ValueError, match="kind"):
        load_spec(spec)


def test_chart_without_metrics_is_rejected(tmp_path: Path) -> None:
    spec = _write(tmp_path, '[[charts]]\nid = "c"\nkind = "bar"\nmetrics = []\n')
    with pytest.raises(ValueError, match="at least one metric"):
        load_spec(spec)


def test_comparison_without_current_is_rejected(tmp_path: Path) -> None:
    spec = _write(
        tmp_path,
        '[comparison]\nprior = "q1"\n'
        '[[comparison.periods]]\nid = "q1"\npredicate = "1=1"\n'
        '[comparison.metrics.x]\nvalue_sql = "SELECT 1"\nslice_sql = "SELECT 1"\n',
    )
    with pytest.raises(ValueError, match="current"):
        load_spec(spec)


def test_comparison_referencing_unknown_period_is_rejected(tmp_path: Path) -> None:
    spec = _write(
        tmp_path,
        '[comparison]\ncurrent = "q9"\nprior = "q1"\n'
        '[[comparison.periods]]\nid = "q1"\npredicate = "1=1"\n'
        '[comparison.metrics.x]\nvalue_sql = "SELECT 1"\nslice_sql = "SELECT 1"\n',
    )
    with pytest.raises(ValueError, match="unknown period"):
        load_spec(spec)


# The reconciliation shares the period machinery with the comparison, so its parse
# and validation cases mirror the comparison's, plus the per-row outcome/financial
# metric pair that is unique to it.

_RECON_PERIODS = (
    '[[reconciliation.periods]]\nid = "q1"\npredicate = "1=1"\n'
    '[[reconciliation.periods]]\nid = "q2"\npredicate = "1=1"\n'
)
_RECON_ROW = (
    '[[reconciliation.rows]]\nlabel = "L"\n'
    '[reconciliation.rows.outcome]\nvalue_sql = "SELECT 1"\nslice_sql = "SELECT 1"\n'
    '[reconciliation.rows.financial]\nvalue_sql = "SELECT 1"\nslice_sql = "SELECT 1"\n'
)


def test_reconciliation_without_periods_is_rejected(tmp_path: Path) -> None:
    spec = _write(
        tmp_path,
        '[reconciliation]\ncurrent = "q2"\nprior = "q1"\n' + _RECON_ROW,
    )
    with pytest.raises(ValueError, match="periods"):
        load_spec(spec)


def test_reconciliation_without_rows_is_rejected(tmp_path: Path) -> None:
    spec = _write(
        tmp_path,
        '[reconciliation]\ncurrent = "q2"\nprior = "q1"\n' + _RECON_PERIODS,
    )
    with pytest.raises(ValueError, match="rows"):
        load_spec(spec)


def test_reconciliation_row_without_outcome_is_rejected(tmp_path: Path) -> None:
    spec = _write(
        tmp_path,
        '[reconciliation]\ncurrent = "q2"\nprior = "q1"\n' + _RECON_PERIODS
        + '[[reconciliation.rows]]\nlabel = "L"\n'
        '[reconciliation.rows.financial]\nvalue_sql = "SELECT 1"\nslice_sql = "SELECT 1"\n',
    )
    with pytest.raises(ValueError, match="outcome"):
        load_spec(spec)


def test_reconciliation_row_without_financial_is_rejected(tmp_path: Path) -> None:
    spec = _write(
        tmp_path,
        '[reconciliation]\ncurrent = "q2"\nprior = "q1"\n' + _RECON_PERIODS
        + '[[reconciliation.rows]]\nlabel = "L"\n'
        '[reconciliation.rows.outcome]\nvalue_sql = "SELECT 1"\nslice_sql = "SELECT 1"\n',
    )
    with pytest.raises(ValueError, match="financial"):
        load_spec(spec)


def test_reconciliation_referencing_unknown_period_is_rejected(tmp_path: Path) -> None:
    spec = _write(
        tmp_path,
        '[reconciliation]\ncurrent = "q9"\nprior = "q1"\n' + _RECON_PERIODS + _RECON_ROW,
    )
    with pytest.raises(ValueError, match="unknown period"):
        load_spec(spec)
