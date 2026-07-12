"""Tests for the board/financial reconciliation view.

A reconciliation pairs a receipted outcome figure with its financial line over two
periods and reports the change in each. The core invariant carries over from the
comparison: every number a reconciliation renders is a figure with a receipt, and
each change is one subtracting SQL query, not Python arithmetic over the page.
These tests pin that, that the section renders, that the reconciliation figures
flow into the receipts manifest, and that the grounding gate passes for the
example board report so its financial numbers are held to the same gate.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from outcome_receipts.cli import main
from outcome_receipts.clock import FixedClock
from outcome_receipts.comparison import compute_reconciliation
from outcome_receipts.config import load_spec
from outcome_receipts.engine import read_csv
from outcome_receipts.grounding import ground
from outcome_receipts.models import (
    MetricSpec,
    PeriodSpec,
    ReconciliationRow,
    ReconciliationSpec,
)
from outcome_receipts.report import render_reconciliation_table

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
BOARD = EXAMPLES / "board-report" / "report.toml"

ROWS = [
    {
        "client_id": "A",
        "enrolled_date": "2025-01-10",
        "exit_destination": "permanent",
        "cost": "1000",
    },
    {
        "client_id": "B",
        "enrolled_date": "2025-02-10",
        "exit_destination": "temporary",
        "cost": "500",
    },
    {
        "client_id": "C",
        "enrolled_date": "2025-03-10",
        "exit_destination": "permanent",
        "cost": "1500",
    },
    {
        "client_id": "D",
        "enrolled_date": "2025-04-10",
        "exit_destination": "permanent",
        "cost": "2000",
    },
    {
        "client_id": "E",
        "enrolled_date": "2025-05-10",
        "exit_destination": "permanent",
        "cost": "800",
    },
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

PERMANENT = MetricSpec(
    metric_id="row_outcome",
    description="permanent exits in the quarter",
    value_sql="SELECT COUNT(*) FROM data WHERE exit_destination = 'permanent' AND ({period})",
    slice_sql="SELECT * FROM data WHERE exit_destination = 'permanent' AND ({period})",
)
SPEND = MetricSpec(
    metric_id="row_financial",
    description="program spend in the quarter",
    value_sql=(
        "SELECT CAST(COALESCE(SUM(CAST(cost AS REAL)), 0) AS INTEGER) FROM data WHERE ({period})"
    ),
    slice_sql="SELECT * FROM data WHERE ({period})",
)


def _spec() -> ReconciliationSpec:
    return ReconciliationSpec(
        current="q2",
        prior="q1",
        periods=(Q1, Q2),
        rows=(
            ReconciliationRow(
                label="Permanent exits vs. spend", outcome=PERMANENT, financial=SPEND
            ),
        ),
    )


def test_outcome_and_financial_take_their_period_values() -> None:
    result = compute_reconciliation(ROWS, _spec(), clock=FixedClock())
    [row] = result.rows
    # Q1 permanent exits: A, C. Q2: D, E.
    assert row.outcome.prior.display == "2"
    assert row.outcome.current.display == "2"
    # Q1 spend: 1000 + 500 + 1500 = 3000. Q2 spend: 2000 + 800 = 2800.
    assert row.financial.prior.display == "3,000"
    assert row.financial.current.display == "2,800"
    assert result.prior_label == "Q1 2025"
    assert result.current_label == "Q2 2025"


def test_financial_delta_comes_from_a_single_subtracting_query() -> None:
    result = compute_reconciliation(ROWS, _spec(), clock=FixedClock())
    [row] = result.rows
    sql = row.financial.delta.receipt.value_sql
    # Not Python arithmetic: one query subtracts the prior scalar from the current.
    assert sql.count("SELECT") == 3
    assert " - " in sql
    # The receipt keeps the signed value; the reader sees the magnitude.
    assert row.financial.delta.receipt.value == -200.0
    assert row.financial.delta.display == "200"
    assert row.financial.direction == "decrease"


def test_delta_slice_is_the_union_of_both_periods() -> None:
    result = compute_reconciliation(ROWS, _spec(), clock=FixedClock())
    [row] = result.rows
    # Q1 has 3 enrolled rows, Q2 has 2; the financial delta covers all five.
    assert row.financial.delta.receipt.row_count == 5


def test_every_reconciliation_figure_is_a_figure_with_a_receipt() -> None:
    result = compute_reconciliation(ROWS, _spec(), clock=FixedClock())
    assert len(result.figures) == 6  # outcome and financial: prior, current, delta each
    for figure in result.figures:
        assert figure.receipt.metric_id == figure.metric_id
        assert figure.receipt.value_sql
    claims = " ".join(figure.display for figure in result.figures)
    grounded = ground(claims, result.figures)
    assert grounded.ok
    assert grounded.total >= 6


def test_unknown_period_is_rejected() -> None:
    spec = ReconciliationSpec(
        current="q3",
        prior="q1",
        periods=(Q1, Q2),
        rows=(ReconciliationRow(label="x", outcome=PERMANENT, financial=SPEND),),
    )
    with pytest.raises(KeyError, match="unknown period"):
        compute_reconciliation(ROWS, spec, clock=FixedClock())


def test_table_renders_outcome_beside_financial_with_change_and_direction() -> None:
    result = compute_reconciliation(ROWS, _spec(), clock=FixedClock())
    table = render_reconciliation_table(result)
    assert "## Board reconciliation" in table
    assert "### Permanent exits vs. spend" in table
    assert "(outcome)" in table and "(financial)" in table
    assert "| 3,000 | 2,800 | 200 | decrease |" in table


def test_example_board_report_grounds_and_gate_passes(tmp_path: Path) -> None:
    out = tmp_path / "board"
    code = main(
        [
            "run",
            "--config",
            str(BOARD),
            "--out",
            str(out),
            "--reproducible",
            "--approved-by",
            "CI",
        ]
    )
    assert code == 0
    report = (out / "report.md").read_text(encoding="utf-8")
    assert "## Board reconciliation" in report
    assert "Permanent-housing exits vs. program spend" in report
    # The financial figures for the example are grounded numbers in the section.
    assert "55,100" in report and "52,100" in report
    # The reconciliation figures flow into the receipts manifest.
    manifest = json.loads((out / "receipts.json").read_text(encoding="utf-8"))
    ids = {r["metric_id"] for r in manifest["receipts"]}
    assert any("_financial__q1" in i for i in ids)
    assert any("_outcome__q1" in i for i in ids)


def test_example_reconciliation_figures_are_grounded_directly() -> None:
    spec = load_spec(BOARD)
    assert spec.report.reconciliation is not None
    rows = read_csv(spec.data_path)
    result = compute_reconciliation(rows, spec.report.reconciliation, clock=FixedClock())
    claims = " ".join(figure.display for figure in result.figures)
    grounded = ground(claims, result.figures)
    assert grounded.ok
    assert grounded.unbound == ()
