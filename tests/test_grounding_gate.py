"""Merge-blocking: the grounding gate must catch every ungrounded number.

This is the load-bearing invariant of the project. If a number in a narrative
does not trace to a receipt, the gate must flag it and block export. If this test
fails, the core promise — that no number is invented — is broken, so it gates the
merge.
"""

from __future__ import annotations

from pathlib import Path

from outcome_receipts.clock import FixedClock
from outcome_receipts.config import load_spec
from outcome_receipts.draft import draft
from outcome_receipts.engine import compute_figures, read_csv
from outcome_receipts.grounding import ground, redact_unbound
from outcome_receipts.models import Figure, MetricSpec

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "housing-demo"


def test_drafted_narrative_is_fully_grounded() -> None:
    spec = load_spec(EXAMPLES / "report.toml")
    rows = read_csv(spec.data_path)
    figures = compute_figures(rows, spec.report.metrics, clock=FixedClock())
    narrative = draft(spec.report, figures)

    result = ground(narrative, figures)
    assert result.ok
    assert len(result.unbound) == 0
    # The narrative does contain numbers; they are all bound, not simply absent.
    assert result.total >= 4


def test_injected_unverifiable_number_is_caught() -> None:
    spec = load_spec(EXAMPLES / "report.toml")
    rows = read_csv(spec.data_path)
    figures = compute_figures(rows, spec.report.metrics, clock=FixedClock())
    narrative = draft(spec.report, figures)

    tampered = narrative.rstrip(".\n") + ", and we supported 42 families in crisis."
    result = ground(tampered, figures)

    assert not result.ok
    assert any(span.text == "42" for span in result.unbound)


def test_a_stray_year_is_unbound() -> None:
    # A number that is not a figure — a year, a list marker — is unbound. The gate
    # is strict on purpose: such a number must be removed or made into a figure.
    spec = load_spec(EXAMPLES / "report.toml")
    rows = read_csv(spec.data_path)
    figures = compute_figures(rows, spec.report.metrics, clock=FixedClock())

    result = ground("In 2024 we served everyone.", figures)
    assert not result.ok
    assert any(span.text == "2024" for span in result.unbound)


def test_redact_unbound_replaces_only_the_ungrounded_numbers() -> None:
    spec = load_spec(EXAMPLES / "report.toml")
    rows = read_csv(spec.data_path)
    figures = compute_figures(rows, spec.report.metrics, clock=FixedClock())
    narrative = draft(spec.report, figures)
    tampered = narrative.rstrip(".\n") + ", and we supported 42 families."

    result = ground(tampered, figures)
    cleaned = redact_unbound(tampered, result)

    assert "42" not in cleaned
    assert "[UNVERIFIED]" in cleaned
    # The grounded figures survive redaction.
    assert "12 clients" in cleaned


def test_money_figure_binds_to_its_span_in_prose() -> None:
    # A money display ($1,234.50) placed in narrative must bind to its figure: the
    # gate's regex captures the leading $ and _normalize strips the $ and commas
    # from both the span and the display so they compare equal.
    spec = MetricSpec(
        metric_id="aid",
        description="total aid disbursed",
        value_sql="SELECT 1234.5",
        slice_sql="SELECT 1",
        unit="money",
        decimals=2,
    )
    [figure] = compute_figures([{"x": "1"}], [spec], clock=FixedClock())
    assert figure.display == "$1,234.50"

    result = ground(f"The program disbursed {figure.display} in emergency aid.", [figure])
    assert result.ok
    assert any(span.text == "$1,234.50" for span in result.bound)


def test_duration_figure_binds_to_the_number_a_reader_sees() -> None:
    # A duration display (30 days) binds to the bare "30" span: the suffix is
    # stripped from the display in _normalize, not captured from prose, so it does
    # not swallow the following word.
    spec = MetricSpec(
        metric_id="stay",
        description="median length of stay",
        value_sql="SELECT 30",
        slice_sql="SELECT 1",
        unit="duration",
        decimals=0,
    )
    [figure] = compute_figures([{"x": "1"}], [spec], clock=FixedClock())
    assert figure.display == "30 days"

    result = ground(f"The median length of stay was {figure.display}.", [figure])
    assert result.ok
    assert any(span.text == "30" for span in result.bound)


def test_empty_narrative_grounds_vacuously() -> None:
    figures: list[Figure] = []
    result = ground("No numbers here.", figures)
    assert result.ok
    assert result.total == 0
