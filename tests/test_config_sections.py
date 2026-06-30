"""Tests for parsing the optional [[charts]] and [comparison] spec sections."""

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
        "clients_served", "exits", "exits_permanent", "pct_permanent"
    }


def test_board_report_uses_a_line_chart() -> None:
    spec = load_spec(EXAMPLES / "board-report" / "report.toml")
    [chart] = spec.report.charts
    assert chart.kind == "line"
    assert chart.metric_ids == ("clients_served__q1", "clients_served__q2")


def test_existing_housing_demo_has_no_optional_sections() -> None:
    spec = load_spec(EXAMPLES / "housing-demo" / "report.toml")
    assert spec.report.charts == ()
    assert spec.report.comparison is None


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
