"""Tests for the logic-model mapping fields (indicator, data source, frequency).

A figure earns more trust when it names the theory-of-change indicator it measures,
the system its data comes from, and how often that data is collected. These optional
fields ride from the spec into the receipt the same way ``definition`` does, so the
mapping travels with the number. These tests pin that they load from the spec, reach
the receipt and the rendered report, land in the manifest when set, are omitted when
empty, and that a spec without them still loads and renders unchanged.
"""

from __future__ import annotations

from pathlib import Path

from outcome_receipts.clock import FixedClock
from outcome_receipts.config import load_spec
from outcome_receipts.engine import compute_figures, read_csv
from outcome_receipts.models import Figure, MetricSpec
from outcome_receipts.report import receipts_manifest, render_report
from outcome_receipts.trace import render_trace_html

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "housing-demo"


def _figures() -> list[Figure]:
    spec = load_spec(EXAMPLES / "report.toml")
    rows = read_csv(spec.data_path)
    return compute_figures(rows, spec.report.metrics, clock=FixedClock())


def test_mapping_fields_default_to_empty() -> None:
    spec = MetricSpec(metric_id="x", description="d", value_sql="SELECT 1", slice_sql="SELECT 1")
    assert spec.indicator == ""
    assert spec.data_source == ""
    assert spec.collection_frequency == ""


def test_config_loads_the_mapping_fields() -> None:
    spec = load_spec(EXAMPLES / "report.toml")
    by_id = {m.metric_id: m for m in spec.report.metrics}
    served = by_id["clients_served"]
    assert served.indicator == "Number of unduplicated individuals served"
    assert served.data_source == "HMIS enrollment records"
    assert served.collection_frequency == "Continuous, reported quarterly"
    # A metric without the fields still loads and defaults them to empty.
    assert by_id["exits"].indicator == ""
    assert by_id["exits"].data_source == ""
    assert by_id["exits"].collection_frequency == ""


def test_mapping_rides_into_the_receipt() -> None:
    figures = _figures()
    served = next(f for f in figures if f.metric_id == "clients_served")
    assert served.receipt.indicator == "Number of unduplicated individuals served"
    assert served.receipt.data_source == "HMIS enrollment records"
    assert served.receipt.collection_frequency == "Continuous, reported quarterly"
    # An unmapped metric carries empty strings forward, not None.
    exits = next(f for f in figures if f.metric_id == "exits")
    assert exits.receipt.indicator == ""
    assert exits.receipt.data_source == ""
    assert exits.receipt.collection_frequency == ""


def test_mapping_renders_in_the_report_receipts() -> None:
    figures = _figures()
    report = render_report("Report", "We served 12 clients.", figures)
    assert "- indicator: Number of unduplicated individuals served" in report
    assert "- data source: HMIS enrollment records" in report
    assert "- collection frequency: Continuous, reported quarterly" in report


def test_empty_mapping_is_omitted_from_the_report() -> None:
    spec = MetricSpec(
        metric_id="only", description="d", value_sql="SELECT 3", slice_sql="SELECT 1"
    )
    figures = compute_figures([{"a": "1"}], [spec], clock=FixedClock())
    report = render_report("Report", "There were 3.", figures)
    assert "indicator:" not in report
    assert "data source:" not in report
    assert "collection frequency:" not in report


def test_mapping_is_in_the_manifest_when_set() -> None:
    figures = _figures()
    manifest = receipts_manifest(figures)
    assert '"indicator":' in manifest
    assert '"data_source":' in manifest
    assert '"collection_frequency":' in manifest
    assert "Number of unduplicated individuals served" in manifest
    assert "HMIS enrollment records" in manifest


def test_manifest_mapping_is_empty_string_when_unmapped() -> None:
    spec = MetricSpec(
        metric_id="only", description="d", value_sql="SELECT 3", slice_sql="SELECT 1"
    )
    figures = compute_figures([{"a": "1"}], [spec], clock=FixedClock())
    manifest = receipts_manifest(figures)
    # The keys are always present so a consumer can rely on the shape; empty means
    # not mapped.
    assert '"indicator": ""' in manifest
    assert '"data_source": ""' in manifest
    assert '"collection_frequency": ""' in manifest


def test_mapping_renders_in_the_trace_view_when_set() -> None:
    figures = _figures()
    html = render_trace_html("Report", figures)
    assert "Indicator" in html
    assert "Number of unduplicated individuals served" in html
    assert "Data source" in html
    assert "HMIS enrollment records" in html
    assert "Collection frequency" in html
    assert "Continuous, reported quarterly" in html


def test_trace_omits_mapping_labels_when_unmapped() -> None:
    spec = MetricSpec(
        metric_id="only", description="d", value_sql="SELECT 3", slice_sql="SELECT 1"
    )
    figures = compute_figures([{"a": "1"}], [spec], clock=FixedClock())
    html = render_trace_html("Report", figures)
    assert "<dt>Indicator</dt>" not in html
    assert "<dt>Data source</dt>" not in html
    assert "<dt>Collection frequency</dt>" not in html
