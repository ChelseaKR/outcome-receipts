"""Tests for the funder-facing trace-view HTML.

The trace view renders the receipts a non-engineer can read: a summary table of
every figure with its value and definition, then a receipt detail per figure. These
tests pin the accessible structure (one ``<h1>``, ``lang``, table headers with
``scope``, a caption), that the definition and provenance show, and that values
from the data are HTML-escaped so a stray angle bracket cannot break the markup.
"""

from __future__ import annotations

from pathlib import Path

from outcome_receipts.cli import main
from outcome_receipts.clock import FixedClock
from outcome_receipts.comparison import ComparisonResult, compute_comparison
from outcome_receipts.models import ComparisonSpec, Figure, MetricSpec, PeriodSpec, Receipt
from outcome_receipts.provenance import Provenance
from outcome_receipts.trace import _anchor, render_trace_html

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
GRANT = EXAMPLES / "grant-report" / "report.toml"


def _figure(metric_id: str, display: str, *, definition: str = "") -> Figure:
    receipt = Receipt(
        metric_id=metric_id,
        value_sql="SELECT 1",
        row_count=1,
        slice_hash="abc123",
        value=1.0,
        unit="count",
        computed_at="1970-01-01T00:00:00+00:00",
        definition=definition,
    )
    return Figure(metric_id=metric_id, value=1.0, display=display, receipt=receipt)


def test_trace_is_an_accessible_html_document() -> None:
    html = render_trace_html("Report", [_figure("a", "5")])
    assert html.startswith("<!doctype html>")
    assert '<html lang="en">' in html
    assert html.count("<h1") == 1
    assert "<caption>Figures in this report</caption>" in html
    assert html.count('scope="col"') == 5


def test_trace_shows_value_and_definition() -> None:
    html = render_trace_html(
        "Report", [_figure("clients_served", "12", definition="Distinct people, once each.")]
    )
    assert "clients_served" in html
    assert ">12<" in html
    assert "Distinct people, once each." in html


def test_trace_shows_the_receipt_fields() -> None:
    html = render_trace_html("Report", [_figure("a", "5")])
    assert "abc123" in html  # slice hash
    assert "SELECT 1" in html  # query
    assert "1970-01-01T00:00:00+00:00" in html  # computed at


def test_trace_embeds_provenance_when_given() -> None:
    html = render_trace_html("Report", [_figure("a", "5")], provenance=Provenance(numbers_bound=1))
    assert "No figure was written by a language model" in html
    assert "1 number(s) in the report bound to a receipt" in html


def test_trace_escapes_data() -> None:
    html = render_trace_html("Report", [_figure("a", "5", definition="x < y & z")])
    assert "x &lt; y &amp; z" in html
    assert "x < y & z" not in html


def test_missing_definition_is_labelled_not_blank() -> None:
    html = render_trace_html("Report", [_figure("a", "5")])
    assert "(no definition recorded)" in html


def test_cli_run_writes_the_trace_view(tmp_path: Path) -> None:
    out = tmp_path / "grant"
    run_args = ["run", "--config", str(GRANT), "--out", str(out)]
    run_args += ["--reproducible", "--approved-by", "CI"]
    assert main(run_args) == 0
    trace = (out / "trace.html").read_text(encoding="utf-8")
    assert trace.startswith("<!doctype html>")
    # A grant-report figure and its definition reach the page.
    assert "exits_permanent" in trace
    assert "taken as recorded" in trace
    # The provenance attestation heads the page.
    assert "No figure was written by a language model" in trace


# A small comparison mirroring tests/test_comparison.py: clients enrolled by quarter.
_CMP_ROWS = [
    {"client_id": "A", "enrolled_date": "2025-01-10"},
    {"client_id": "B", "enrolled_date": "2025-02-10"},
    {"client_id": "C", "enrolled_date": "2025-03-10"},
    {"client_id": "D", "enrolled_date": "2025-04-10"},
    {"client_id": "E", "enrolled_date": "2025-05-10"},
]
_Q1 = PeriodSpec(
    period_id="q1",
    label="Q1 2025",
    predicate="enrolled_date >= '2025-01-01' AND enrolled_date < '2025-04-01'",
)
_Q2 = PeriodSpec(
    period_id="q2",
    label="Q2 2025",
    predicate="enrolled_date >= '2025-04-01' AND enrolled_date < '2025-07-01'",
)
_CLIENTS = MetricSpec(
    metric_id="clients",
    description="distinct clients enrolled in the quarter",
    value_sql="SELECT COUNT(DISTINCT client_id) FROM data WHERE {period}",
    slice_sql="SELECT client_id FROM data WHERE {period}",
)


def _comparison(rows: list[dict[str, str]] = _CMP_ROWS) -> ComparisonResult:
    spec = ComparisonSpec(current="q2", prior="q1", periods=(_Q1, _Q2), metrics=(_CLIENTS,))
    return compute_comparison(rows, spec, clock=FixedClock())


def test_trace_labels_delta_direction_magnitude_and_cross_links() -> None:
    comparison = _comparison()
    [row] = comparison.rows
    # Q1 has 3 clients, Q2 has 2: a decrease of 1.
    assert row.direction == "decrease"
    html = render_trace_html("Report", comparison.figures, comparison=comparison)
    # Direction word and magnitude both appear in the delta figure's detail block.
    assert "Decrease" in html
    assert "Decrease of 1" in html
    # Cross-links point at both period figures' detail sections.
    assert f'href="#{_anchor(row.prior.metric_id)}"' in html
    assert f'href="#{_anchor(row.current.metric_id)}"' in html
    # The linked ids are the two period figures, which are on the page.
    assert f'id="{_anchor(row.prior.metric_id)}"' in html
    assert f'id="{_anchor(row.current.metric_id)}"' in html
    assert "Compared periods" in html


def test_trace_labels_increase_direction() -> None:
    # One client in Q1, two in Q2: an increase of 1.
    rows = [
        {"client_id": "A", "enrolled_date": "2025-02-10"},
        {"client_id": "D", "enrolled_date": "2025-04-10"},
        {"client_id": "E", "enrolled_date": "2025-05-10"},
    ]
    comparison = _comparison(rows)
    assert comparison.rows[0].direction == "increase"
    html = render_trace_html("Report", comparison.figures, comparison=comparison)
    assert "Increase of 1" in html


def test_trace_labels_no_change() -> None:
    # Two clients each quarter: no change, and no magnitude in the label.
    rows = [
        {"client_id": "A", "enrolled_date": "2025-01-10"},
        {"client_id": "B", "enrolled_date": "2025-02-10"},
        {"client_id": "D", "enrolled_date": "2025-04-10"},
        {"client_id": "E", "enrolled_date": "2025-05-10"},
    ]
    comparison = _comparison(rows)
    assert comparison.rows[0].direction == "no change"
    html = render_trace_html("Report", comparison.figures, comparison=comparison)
    assert '<p class="change">No change</p>' in html


def test_trace_renders_without_comparison() -> None:
    # The comparison binding is optional; the page renders unchanged when omitted.
    html = render_trace_html("Report", [_figure("a", "5")])
    assert html.startswith("<!doctype html>")
    assert "Compared periods" not in html
    assert "Decrease of" not in html
    # An explicit comparison=None is equivalent to omitting it.
    assert render_trace_html("Report", [_figure("a", "5")], comparison=None) == html
