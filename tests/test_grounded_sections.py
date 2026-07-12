"""Merge-blocking: chart and comparison numbers are held to the grounding gate.

The core invariant is that no number reaches an exported report without tracing
to a receipt. v0.2 extends the report with charts and a period comparison, so the
invariant has to hold for their numbers too. These tests prove that every number
the new sections render binds to a figure, and that an injected number that binds
to no figure is caught, the same fail-closed behavior the narrative gate has.
"""

from __future__ import annotations

from pathlib import Path

from outcome_receipts.charts import Chart, render_charts
from outcome_receipts.cli import main
from outcome_receipts.clock import FixedClock
from outcome_receipts.comparison import ComparisonResult, compute_comparison
from outcome_receipts.config import load_spec
from outcome_receipts.engine import compute_figures, read_csv
from outcome_receipts.grounding import ground
from outcome_receipts.models import Figure

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
GRANT = EXAMPLES / "grant-report" / "report.toml"


def _all_figures_and_charts() -> tuple[list[Figure], ComparisonResult, list[Chart]]:
    spec = load_spec(GRANT)
    assert spec.report.comparison is not None
    rows = read_csv(spec.data_path)
    figures = compute_figures(rows, spec.report.metrics, clock=FixedClock())
    comparison = compute_comparison(rows, spec.report.comparison, clock=FixedClock())
    figures = [*figures, *comparison.figures]
    charts = render_charts(spec.report.charts, figures)
    return figures, comparison, charts


def test_every_chart_and_comparison_number_is_grounded() -> None:
    figures, comparison, charts = _all_figures_and_charts()
    claims_parts = [figure.display for figure in comparison.figures]
    for chart in charts:
        claims_parts.append(chart.claims_text)
    result = ground(" ".join(claims_parts), figures)
    assert result.ok
    assert result.unbound == ()
    assert result.total >= 10


def test_an_ungrounded_chart_number_would_be_caught() -> None:
    # Simulate a chart whose value came from a separate path: a number that is no
    # figure's display. The gate must flag it, exactly as it flags a stray number
    # in prose.
    figures, _comparison, charts = _all_figures_and_charts()
    tampered = charts[0].claims_text + " 999"
    result = ground(tampered, figures)
    assert not result.ok
    assert any(span.text == "999" for span in result.unbound)


def test_cli_run_writes_report_charts_and_manifest(tmp_path: Path) -> None:
    out = tmp_path / "grant"
    run_args = ["run", "--config", str(GRANT), "--out", str(out)]
    run_args += ["--reproducible", "--approved-by", "CI"]
    code = main(run_args)
    assert code == 0
    assert (out / "report.md").exists()
    assert (out / "receipts.json").exists()
    assert (out / "charts" / "exits-by-destination.svg").exists()
    assert (out / "charts" / "permanent-by-quarter.svg").exists()
    report = (out / "report.md").read_text(encoding="utf-8")
    assert "## Period comparison" in report
    assert "## Charts" in report
    # The comparison renders period values and a change, all grounded numbers.
    assert "| 12 | 14 | 2 | increase |" in report
    # The accessible data table carries the chart's grounded numbers.
    assert "| Permanent | 13 |" in report
    # The provenance statement is embedded, and the trace view ships alongside.
    assert "## Provenance" in report
    assert "No figure was written by a language model" in report
    assert (out / "trace.html").exists()
