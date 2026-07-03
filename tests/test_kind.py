"""Tests for the metric ``kind`` field (output vs outcome).

A metric is an ``output`` (an activity count, such as clients served) or an
``outcome`` (a change in condition, such as a permanent-housing rate). The label
rides in the receipt from the spec so a reader does not misread a busy output as
the outcome it is meant to produce. These tests pin its default, that it loads
from the spec, that an invalid value is rejected, and that it reaches the receipt,
the rendered report, and the manifest.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from outcome_receipts.clock import FixedClock
from outcome_receipts.config import load_spec
from outcome_receipts.engine import compute_figures, read_csv
from outcome_receipts.models import MetricSpec
from outcome_receipts.report import receipts_manifest, render_report

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "housing-demo"


def test_kind_defaults_to_output() -> None:
    spec = MetricSpec(metric_id="x", description="d", value_sql="SELECT 1", slice_sql="SELECT 1")
    assert spec.kind == "output"


def test_config_loads_the_kind() -> None:
    spec = load_spec(EXAMPLES / "report.toml")
    by_id = {m.metric_id: m for m in spec.report.metrics}
    assert by_id["clients_served"].kind == "output"
    assert by_id["pct_permanent"].kind == "outcome"


def test_load_spec_rejects_unknown_kind(tmp_path: Path) -> None:
    bad = tmp_path / "bad.toml"
    bad.write_text(
        '[data]\npath = "x.csv"\n'
        '[report]\ntemplate = "{m}"\n'
        '[metrics.m]\nkind = "impact"\n'
        'value_sql = "SELECT 1"\nslice_sql = "SELECT 1"\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="kind"):
        load_spec(bad)


def test_kind_rides_into_the_receipt() -> None:
    spec = load_spec(EXAMPLES / "report.toml")
    rows = read_csv(spec.data_path)
    figures = compute_figures(rows, spec.report.metrics, clock=FixedClock())
    served = next(f for f in figures if f.metric_id == "clients_served")
    rate = next(f for f in figures if f.metric_id == "pct_permanent")
    assert served.receipt.kind == "output"
    assert rate.receipt.kind == "outcome"


def test_kind_renders_in_the_report_receipts() -> None:
    spec = load_spec(EXAMPLES / "report.toml")
    rows = read_csv(spec.data_path)
    figures = compute_figures(rows, spec.report.metrics, clock=FixedClock())
    report = render_report(spec.report.title, "We served 12 clients.", figures)
    assert "- kind: output" in report
    assert "- kind: outcome" in report


def test_kind_is_in_the_manifest() -> None:
    spec = load_spec(EXAMPLES / "report.toml")
    rows = read_csv(spec.data_path)
    figures = compute_figures(rows, spec.report.metrics, clock=FixedClock())
    manifest = receipts_manifest(figures)
    assert '"kind":' in manifest
    assert '"outcome"' in manifest
