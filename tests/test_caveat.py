"""Tests for the metric ``caveat`` field (an optional qualifying note).

A caveat is a qualifying note (e.g. a data-quality limitation) that rides in the
receipt from the spec, so a limitation on the figure travels inside the receipt
chain and renders next to the figure instead of living as loose prose. These
tests pin that it loads from the spec, reaches the receipt and the rendered
report, lands in the manifest, and renders in the trace HTML.
"""

from __future__ import annotations

from pathlib import Path

from outcome_receipts.clock import FixedClock
from outcome_receipts.config import load_spec
from outcome_receipts.engine import compute_figures, read_csv
from outcome_receipts.models import MetricSpec
from outcome_receipts.report import receipts_manifest, render_report
from outcome_receipts.trace import render_trace_html

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "housing-demo"


def test_caveat_defaults_to_empty() -> None:
    spec = MetricSpec(metric_id="x", description="d", value_sql="SELECT 1", slice_sql="SELECT 1")
    assert spec.caveat == ""


def test_config_loads_the_caveat() -> None:
    spec = load_spec(EXAMPLES / "report.toml")
    by_id = {m.metric_id: m for m in spec.report.metrics}
    assert "incomplete intake data" in by_id["clients_served"].caveat


def test_caveat_rides_into_the_receipt() -> None:
    spec = load_spec(EXAMPLES / "report.toml")
    rows = read_csv(spec.data_path)
    figures = compute_figures(rows, spec.report.metrics, clock=FixedClock())
    served = next(f for f in figures if f.metric_id == "clients_served")
    assert "incomplete intake data" in served.receipt.caveat


def test_caveat_renders_in_the_report_receipts() -> None:
    spec = load_spec(EXAMPLES / "report.toml")
    rows = read_csv(spec.data_path)
    figures = compute_figures(rows, spec.report.metrics, clock=FixedClock())
    report = render_report(spec.report.title, "We served 12 clients.", figures)
    assert "- caveat: Client records missing a client_id" in report


def test_caveat_is_in_the_manifest() -> None:
    spec = load_spec(EXAMPLES / "report.toml")
    rows = read_csv(spec.data_path)
    figures = compute_figures(rows, spec.report.metrics, clock=FixedClock())
    manifest = receipts_manifest(figures)
    assert '"caveat":' in manifest
    assert "incomplete intake data" in manifest


def test_caveat_renders_in_the_trace_html() -> None:
    spec = load_spec(EXAMPLES / "report.toml")
    rows = read_csv(spec.data_path)
    figures = compute_figures(rows, spec.report.metrics, clock=FixedClock())
    html = render_trace_html(spec.report.title, figures)
    assert "incomplete intake data" in html
