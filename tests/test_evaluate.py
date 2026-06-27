"""Tests for eval scoring."""

from __future__ import annotations

from outcome_receipts.evaluate import evaluate, wilson_interval
from outcome_receipts.models import GroundingResult, NumericSpan


def _span(text: str) -> NumericSpan:
    return NumericSpan(text=text, start=0, end=len(text))


def test_wilson_zero_successes() -> None:
    low, high = wilson_interval(0, 10)
    assert low == 0.0
    assert 0.25 < high < 0.35


def test_wilson_no_trials_is_widest() -> None:
    assert wilson_interval(0, 0) == (0.0, 1.0)


def test_evaluate_all_bound_passes_gate() -> None:
    result = GroundingResult(bound=(_span("12"), _span("6")), unbound=())
    report = evaluate(result)
    assert report.n_numbers == 2
    assert report.grounding_rate == 1.0
    assert report.hallucinated_rate == 0.0
    assert report.gate_pass is True


def test_evaluate_one_unbound_fails_gate() -> None:
    result = GroundingResult(bound=(_span("12"),), unbound=(_span("42"),))
    report = evaluate(result)
    assert report.n_unbound == 1
    assert report.gate_pass is False
    assert 0.0 < report.grounding_rate < 1.0


def test_evaluate_no_numbers_passes_vacuously() -> None:
    report = evaluate(GroundingResult(bound=(), unbound=()))
    assert report.n_numbers == 0
    assert report.grounding_rate == 1.0
    assert report.gate_pass is True
