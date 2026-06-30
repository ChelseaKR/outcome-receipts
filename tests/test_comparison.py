"""Tests for the period-over-period comparison.

Every number a comparison reports is a figure with a receipt: the two period
values and the change. These tests pin that the change is computed by SQL (not
Python arithmetic over the page), that its receipt records the signed value while
its display is the grounded magnitude, and that the direction word follows the
sign.
"""

from __future__ import annotations

import pytest

from outcome_receipts.clock import FixedClock
from outcome_receipts.comparison import compute_comparison
from outcome_receipts.grounding import ground
from outcome_receipts.models import ComparisonSpec, MetricSpec, PeriodSpec

ROWS = [
    {"client_id": "A", "enrolled_date": "2025-01-10", "exit_date": "2025-02-01",
     "exit_destination": "permanent"},
    {"client_id": "B", "enrolled_date": "2025-02-10", "exit_date": "2025-03-01",
     "exit_destination": "temporary"},
    {"client_id": "C", "enrolled_date": "2025-03-10", "exit_date": "2025-04-01",
     "exit_destination": "permanent"},
    {"client_id": "D", "enrolled_date": "2025-04-10", "exit_date": "2025-05-01",
     "exit_destination": "permanent"},
    {"client_id": "E", "enrolled_date": "2025-05-10", "exit_date": "2025-06-01",
     "exit_destination": "permanent"},
]

Q1 = PeriodSpec(
    period_id="q1",
    label="Q1 2025",
    predicate="enrolled_date >= '2025-01-01' AND enrolled_date < '2025-04-01'",
)
Q2 = PeriodSpec(
    period_id="q2",
    label="Q2 2025",
    predicate="enrolled_date >= '2025-04-01' AND enrolled_date < '2025-07-01'",
)

CLIENTS = MetricSpec(
    metric_id="clients",
    description="distinct clients enrolled in the quarter",
    value_sql="SELECT COUNT(DISTINCT client_id) FROM data WHERE {period}",
    slice_sql="SELECT client_id FROM data WHERE {period}",
)
PERMANENT = MetricSpec(
    metric_id="permanent",
    description="permanent exits in the quarter",
    value_sql="SELECT COUNT(*) FROM data WHERE exit_destination = 'permanent' AND ({period})",
    slice_sql="SELECT * FROM data WHERE exit_destination = 'permanent' AND ({period})",
)


def _spec(*metrics: MetricSpec) -> ComparisonSpec:
    return ComparisonSpec(current="q2", prior="q1", periods=(Q1, Q2), metrics=metrics)


def test_period_figures_take_their_period_value() -> None:
    result = compute_comparison(ROWS, _spec(CLIENTS), clock=FixedClock())
    [row] = result.rows
    assert row.prior.display == "3"  # A, B, C enrolled in Q1
    assert row.current.display == "2"  # D, E enrolled in Q2
    assert result.prior_label == "Q1 2025"
    assert result.current_label == "Q2 2025"


def test_delta_is_signed_in_the_receipt_but_displayed_as_magnitude() -> None:
    result = compute_comparison(ROWS, _spec(CLIENTS), clock=FixedClock())
    [row] = result.rows
    # Current minus prior is 2 - 3 = -1: the receipt keeps the signed value.
    assert row.delta.value == -1.0
    assert row.delta.receipt.value == -1.0
    # The reader sees the magnitude, the token the grounding gate binds.
    assert row.delta.display == "1"
    assert row.direction == "decrease"
    assert row.arrow == "down"


def test_delta_value_comes_from_a_single_subtracting_query() -> None:
    result = compute_comparison(ROWS, _spec(CLIENTS), clock=FixedClock())
    [row] = result.rows
    sql = row.delta.receipt.value_sql
    # Not Python arithmetic: one query subtracts the prior scalar from the current.
    assert sql.count("SELECT") == 3
    assert " - " in sql
    assert "2025-04-01" in sql and "2025-01-01" in sql


def test_delta_slice_is_the_union_of_both_periods() -> None:
    result = compute_comparison(ROWS, _spec(CLIENTS), clock=FixedClock())
    [row] = result.rows
    # Q1 slice has 3 rows, Q2 slice has 2; the delta receipt covers all five.
    assert row.delta.receipt.row_count == 5


def test_no_change_reports_zero_and_flat() -> None:
    result = compute_comparison(ROWS, _spec(PERMANENT), clock=FixedClock())
    [row] = result.rows
    # A and C permanent in Q1; D and E permanent in Q2: two each.
    assert row.prior.display == "2"
    assert row.current.display == "2"
    assert row.delta.display == "0"
    assert row.direction == "no change"
    assert row.arrow == "flat"


def test_every_comparison_figure_grounds_to_itself() -> None:
    result = compute_comparison(ROWS, _spec(CLIENTS, PERMANENT), clock=FixedClock())
    claims = " ".join(figure.display for figure in result.figures)
    grounded = ground(claims, result.figures)
    assert grounded.ok
    assert grounded.total >= 6  # prior, current, delta for each of two metrics


def test_metric_without_placeholder_is_rejected() -> None:
    bad = MetricSpec(
        metric_id="bad",
        description="no period placeholder",
        value_sql="SELECT COUNT(*) FROM data",
        slice_sql="SELECT * FROM data",
    )
    with pytest.raises(ValueError, match="placeholder"):
        compute_comparison(ROWS, _spec(bad), clock=FixedClock())


def test_unknown_period_is_rejected() -> None:
    spec = ComparisonSpec(current="q3", prior="q1", periods=(Q1, Q2), metrics=(CLIENTS,))
    with pytest.raises(KeyError, match="unknown period"):
        compute_comparison(ROWS, spec, clock=FixedClock())
