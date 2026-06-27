"""Tests for the deterministic drafter and the spec loader."""

from __future__ import annotations

from pathlib import Path

import pytest

from outcome_receipts.clock import FixedClock
from outcome_receipts.config import load_spec
from outcome_receipts.draft import draft
from outcome_receipts.engine import compute_figures, read_csv
from outcome_receipts.models import Figure, MetricSpec, Receipt, ReportSpec

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "housing-demo"


def _figure(metric_id: str, display: str) -> Figure:
    receipt = Receipt(
        metric_id=metric_id,
        value_sql="SELECT 1",
        row_count=1,
        slice_hash="x",
        value=1.0,
        unit="count",
        computed_at="t",
    )
    return Figure(metric_id=metric_id, value=1.0, display=display, receipt=receipt)


def test_draft_substitutes_displays() -> None:
    spec = ReportSpec(title="t", template="served {a} of {b}", metrics=())
    out = draft(spec, [_figure("a", "12"), _figure("b", "20")])
    assert out == "served 12 of 20"


def test_draft_raises_on_unknown_metric() -> None:
    spec = ReportSpec(title="t", template="served {missing}", metrics=())
    with pytest.raises(KeyError, match="unknown metric"):
        draft(spec, [_figure("a", "12")])


def test_load_spec_reads_metrics_and_template() -> None:
    spec = load_spec(EXAMPLES / "report.toml")
    assert spec.report.title == "Housing Program Outcome Report"
    ids = {m.metric_id for m in spec.report.metrics}
    assert ids == {"clients_served", "exits", "exits_permanent", "pct_permanent"}
    assert spec.data_path.name == "services.csv"


def test_load_spec_rejects_unknown_unit(tmp_path: Path) -> None:
    bad = tmp_path / "bad.toml"
    bad.write_text(
        '[data]\npath = "x.csv"\n'
        '[report]\ntemplate = "{m}"\n'
        '[metrics.m]\nunit = "furlongs"\n'
        'value_sql = "SELECT 1"\nslice_sql = "SELECT 1"\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="unit"):
        load_spec(bad)


def test_load_spec_requires_a_metric(tmp_path: Path) -> None:
    bad = tmp_path / "bad.toml"
    bad.write_text('[data]\npath = "x.csv"\n[report]\ntemplate = "none"\n', encoding="utf-8")
    with pytest.raises(ValueError, match="at least one"):
        load_spec(bad)


def test_demo_metric_specs_compute_expected_values() -> None:
    spec = load_spec(EXAMPLES / "report.toml")
    rows = read_csv(spec.data_path)
    computed = compute_figures(rows, spec.report.metrics, clock=FixedClock())
    figures = {f.metric_id: f for f in computed}
    assert figures["clients_served"].display == "12"
    assert figures["exits"].display == "10"
    assert figures["exits_permanent"].display == "6"
    assert figures["pct_permanent"].display == "60%"


def test_unused_metricspec_fields_are_accessible() -> None:
    # Guard the MetricSpec surface the spec loader depends on.
    m = MetricSpec(metric_id="x", description="d", value_sql="SELECT 1", slice_sql="SELECT 1")
    assert m.unit == "count"
    assert m.decimals == 0
