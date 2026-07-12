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
from outcome_receipts.models import Figure, Receipt
from outcome_receipts.provenance import Provenance
from outcome_receipts.trace import render_trace_html

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
