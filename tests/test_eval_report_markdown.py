"""Tests for the committed eval Markdown rendering.

A narrative with zero numeric spans scores ``grounding_rate`` at 1.0
vacuously (see ``tests/test_evaluate.py::test_evaluate_no_numbers_passes_vacuously``):
no number failed to bind because there was no number to bind. That is a
legitimate reason for the fail-closed gate to pass, but the committed
``eval.md`` must not render that vacuous rate as if it were a measurement --
"Grounding gate (100% required): PASS (observed 100.0%)" reads to a reviewer
as "we scored some numbers and all of them bound," when in fact zero numbers
were scored.
"""

from __future__ import annotations

from outcome_receipts.evaluate import evaluate
from outcome_receipts.models import GroundingResult, NumericSpan
from outcome_receipts.report import render_eval_markdown


def _span(text: str) -> NumericSpan:
    return NumericSpan(text=text, start=0, end=len(text))


def test_zero_numeric_spans_does_not_render_as_an_observed_measurement() -> None:
    report = evaluate(GroundingResult(bound=(), unbound=()))
    assert report.n_numbers == 0
    assert report.gate_pass is True  # vacuously: nothing failed to bind

    markdown = render_eval_markdown(report, dataset="empty-fixture")

    assert "observed 100.0%" not in markdown
    assert "**100.0%**" not in markdown
    assert "N/A (no numeric spans)" in markdown
    assert "PASS" in markdown
    assert "vacuously" in markdown


def test_a_real_fully_grounded_narrative_still_reports_the_measured_rate() -> None:
    report = evaluate(GroundingResult(bound=(_span("12"), _span("6")), unbound=()))
    assert report.n_numbers == 2

    markdown = render_eval_markdown(report, dataset="housing-demo")

    assert "observed 100.0%" in markdown
    assert "**100.0%** (2/2)" in markdown
    assert "N/A" not in markdown
