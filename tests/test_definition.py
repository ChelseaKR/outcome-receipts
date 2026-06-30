"""Tests for the metric ``definition`` field (what window, who counts, dedup rule).

A figure is only as fair as its definition. The definition rides in the receipt
from the spec, so a reviewer can see and contest the choices a query encodes
without reading the SQL. These tests pin that it loads from the spec, reaches the
receipt and the rendered report, and lands in the manifest.
"""

from __future__ import annotations

from pathlib import Path

from outcome_receipts.clock import FixedClock
from outcome_receipts.config import load_spec
from outcome_receipts.engine import compute_figures, read_csv
from outcome_receipts.models import MetricSpec
from outcome_receipts.report import receipts_manifest, render_report

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "housing-demo"


def test_definition_defaults_to_empty() -> None:
    spec = MetricSpec(metric_id="x", description="d", value_sql="SELECT 1", slice_sql="SELECT 1")
    assert spec.definition == ""


def test_config_loads_the_definition() -> None:
    spec = load_spec(EXAMPLES / "report.toml")
    by_id = {m.metric_id: m for m in spec.report.metrics}
    assert "counted once by client_id" in by_id["clients_served"].definition


def test_definition_rides_into_the_receipt() -> None:
    spec = load_spec(EXAMPLES / "report.toml")
    rows = read_csv(spec.data_path)
    figures = compute_figures(rows, spec.report.metrics, clock=FixedClock())
    served = next(f for f in figures if f.metric_id == "clients_served")
    assert "counted once by client_id" in served.receipt.definition


def test_definition_renders_in_the_report_receipts() -> None:
    spec = load_spec(EXAMPLES / "report.toml")
    rows = read_csv(spec.data_path)
    figures = compute_figures(rows, spec.report.metrics, clock=FixedClock())
    report = render_report(spec.report.title, "We served 12 clients.", figures)
    assert "- definition: Each person enrolled" in report


def test_definition_is_in_the_manifest() -> None:
    spec = load_spec(EXAMPLES / "report.toml")
    rows = read_csv(spec.data_path)
    figures = compute_figures(rows, spec.report.metrics, clock=FixedClock())
    manifest = receipts_manifest(figures)
    assert '"definition":' in manifest
    assert "counted once by client_id" in manifest
