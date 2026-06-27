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


def test_empty_narrative_grounds_vacuously() -> None:
    figures = compute_figures([], (), clock=FixedClock())
    result = ground("No numbers here.", figures)
    assert result.ok
    assert result.total == 0
