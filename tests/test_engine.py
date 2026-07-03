"""Tests for the deterministic metric engine and receipts."""

from __future__ import annotations

import pytest

from outcome_receipts.clock import FixedClock
from outcome_receipts.engine import _format, compute_figure, compute_figures, load_table
from outcome_receipts.models import EMPTY_SLICE_HASH, MetricSpec

ROWS = [
    {"client_id": "C1", "dest": "permanent"},
    {"client_id": "C2", "dest": "permanent"},
    {"client_id": "C3", "dest": "temporary"},
]

COUNT = MetricSpec(
    metric_id="clients",
    description="distinct clients",
    value_sql="SELECT COUNT(DISTINCT client_id) FROM data",
    slice_sql="SELECT client_id FROM data",
    unit="count",
)

PERMANENT = MetricSpec(
    metric_id="permanent",
    description="permanent exits",
    value_sql="SELECT COUNT(*) FROM data WHERE dest = 'permanent'",
    slice_sql="SELECT * FROM data WHERE dest = 'permanent'",
    unit="count",
)


def test_count_figure_value_and_display() -> None:
    [figure] = compute_figures(ROWS, [COUNT], clock=FixedClock())
    assert figure.value == 3.0
    assert figure.display == "3"
    assert figure.receipt.row_count == 3


def test_receipt_is_reproducible_for_same_data() -> None:
    a = compute_figures(ROWS, [PERMANENT], clock=FixedClock())[0]
    b = compute_figures(ROWS, [PERMANENT], clock=FixedClock())[0]
    assert a.receipt.slice_hash == b.receipt.slice_hash
    assert a.receipt.value == b.receipt.value


def test_changed_slice_changes_the_hash() -> None:
    base = compute_figures(ROWS, [PERMANENT], clock=FixedClock())[0]
    more = compute_figures(
        [*ROWS, {"client_id": "C4", "dest": "permanent"}], [PERMANENT], clock=FixedClock()
    )[0]
    assert base.receipt.slice_hash != more.receipt.slice_hash
    assert more.value == 3.0


def test_slice_hash_is_row_order_independent() -> None:
    forward = compute_figures(ROWS, [COUNT], clock=FixedClock())[0]
    reverse = compute_figures(list(reversed(ROWS)), [COUNT], clock=FixedClock())[0]
    assert forward.receipt.slice_hash == reverse.receipt.slice_hash


def test_percent_formatting() -> None:
    spec = MetricSpec(
        metric_id="pct",
        description="permanent share",
        value_sql=(
            "SELECT ROUND(100.0 * SUM(CASE WHEN dest='permanent' THEN 1 ELSE 0 END) "
            "/ COUNT(*)) FROM data"
        ),
        slice_sql="SELECT * FROM data",
        unit="percent",
        decimals=0,
    )
    [figure] = compute_figures(ROWS, [spec], clock=FixedClock())
    assert figure.display == "67%"


def test_money_formatting_is_currency_prefixed_and_separated() -> None:
    assert _format(1234.5, "money", 2) == "$1,234.50"
    assert _format(1000000.0, "money", 0) == "$1,000,000"


def test_duration_formatting_appends_days() -> None:
    assert _format(30.0, "duration", 0) == "30 days"
    assert _format(1234.5, "duration", 1) == "1,234.5 days"


def test_rate_formatting_is_a_bare_fixed_decimal() -> None:
    assert _format(4.25, "rate", 2) == "4.25"
    assert _format(4.0, "rate", 0) == "4"


def test_money_figure_display_from_a_metric() -> None:
    spec = MetricSpec(
        metric_id="funds",
        description="total aid disbursed",
        value_sql="SELECT 1234.5",
        slice_sql="SELECT * FROM data",
        unit="money",
        decimals=2,
    )
    [figure] = compute_figures(ROWS, [spec], clock=FixedClock())
    assert figure.display == "$1,234.50"
    assert figure.receipt.unit == "money"


def test_thousands_separator_in_count_display() -> None:
    rows = [{"client_id": str(i), "dest": "permanent"} for i in range(1234)]
    [figure] = compute_figures(rows, [COUNT], clock=FixedClock())
    assert figure.display == "1,234"


def test_empty_data_gives_empty_slice_hash() -> None:
    spec = MetricSpec(
        metric_id="n",
        description="rows",
        value_sql="SELECT COUNT(*) FROM data",
        slice_sql="SELECT * FROM data",
        unit="count",
    )
    [figure] = compute_figures([], [spec], clock=FixedClock())
    assert figure.value == 0.0
    assert figure.receipt.slice_hash == EMPTY_SLICE_HASH


def test_missing_column_in_value_sql_raises_named_error() -> None:
    bad = MetricSpec(
        metric_id="missing_value",
        description="value query references an absent column",
        value_sql="SELECT COUNT(*) FROM data WHERE missing_col = 'x'",
        slice_sql="SELECT * FROM data",
        unit="count",
    )
    with pytest.raises(ValueError, match="missing_col"):
        compute_figures(ROWS, [bad], clock=FixedClock())


def test_missing_column_in_slice_sql_raises_named_error() -> None:
    bad = MetricSpec(
        metric_id="missing_slice",
        description="slice query references an absent column",
        value_sql="SELECT COUNT(*) FROM data",
        slice_sql="SELECT * FROM data WHERE missing_col = 'x'",
        unit="count",
    )
    with pytest.raises(ValueError, match="missing_col"):
        compute_figures(ROWS, [bad], clock=FixedClock())


def test_other_operational_error_fails_closed_as_value_error() -> None:
    bad = MetricSpec(
        metric_id="missing_table",
        description="query references a table that does not exist",
        value_sql="SELECT COUNT(*) FROM nope",
        slice_sql="SELECT * FROM data",
        unit="count",
    )
    with pytest.raises(ValueError, match="missing_table"):
        compute_figures(ROWS, [bad], clock=FixedClock())


def test_malformed_metric_raises() -> None:
    conn = load_table(ROWS)
    bad = MetricSpec(
        metric_id="bad",
        description="two columns, not a scalar",
        value_sql="SELECT client_id, dest FROM data",
        slice_sql="SELECT * FROM data",
    )
    try:
        with pytest.raises(ValueError, match="exactly one scalar"):
            compute_figure(conn, bad, clock=FixedClock())
    finally:
        conn.close()
