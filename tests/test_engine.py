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


def test_renamed_column_changes_the_hash() -> None:
    """Identical slice values under a different column name hash differently.

    Canonicalization v1 folds the sorted column names into the payload, so a
    schema change a funder should see is not silent. Under the earlier rows-only
    payload these two slices hashed identically.
    """

    rows = [{"dest": "permanent"}, {"dest": "temporary"}]
    original = MetricSpec(
        metric_id="m",
        description="destinations",
        value_sql="SELECT COUNT(*) FROM data",
        slice_sql="SELECT dest FROM data",
        unit="count",
    )
    renamed = MetricSpec(
        metric_id="m",
        description="destinations",
        value_sql="SELECT COUNT(*) FROM data",
        slice_sql="SELECT dest AS outcome FROM data",
        unit="count",
    )
    a = compute_figures(rows, [original], clock=FixedClock())[0]
    b = compute_figures(rows, [renamed], clock=FixedClock())[0]
    assert a.value == b.value
    assert a.receipt.column_names == ("dest",)
    assert b.receipt.column_names == ("outcome",)
    assert a.receipt.slice_hash != b.receipt.slice_hash


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


def test_empty_slice_gives_empty_slice_hash() -> None:
    # An empty *slice* (a metric whose query matches no row over non-empty data)
    # yields the sentinel hash. Empty *input* is a separate, rejected case; see
    # test_loader_hardening.py.
    spec = MetricSpec(
        metric_id="n",
        description="rows with an impossible destination",
        value_sql="SELECT COUNT(*) FROM data WHERE dest = 'nowhere'",
        slice_sql="SELECT * FROM data WHERE dest = 'nowhere'",
        unit="count",
    )
    [figure] = compute_figures(ROWS, [spec], clock=FixedClock())
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


# --- SQL NULL is the absence of a value, never the value zero -----------------
#
# An earlier revision coerced a NULL scalar to 0.0. Nothing downstream could
# recover it: suppression reads value == 0 as a *true zero* and publishes it,
# verify re-derives the same 0.0 and agrees, and the export renders "0"/"0%"/
# "0 days". These pin the fail-closed behaviour; each one fails on that revision.


def test_null_scalar_fails_closed_instead_of_becoming_zero() -> None:
    """AVG over an empty filtered set is NULL, and must not publish as 0.0."""

    empty_avg = MetricSpec(
        metric_id="avg_days_to_housing",
        description="average days to housing for a cohort with no members",
        value_sql="SELECT AVG(CAST(client_id AS REAL)) FROM data WHERE dest = 'nowhere'",
        slice_sql="SELECT * FROM data WHERE dest = 'nowhere'",
        unit="days",
        decimals=1,
    )
    with pytest.raises(ValueError, match="avg_days_to_housing"):
        compute_figures(ROWS, [empty_avg], clock=FixedClock())


def test_null_scalar_error_names_null_and_suggests_coalesce() -> None:
    """The error has to teach the fix, not just refuse."""

    empty_sum = MetricSpec(
        metric_id="total_cost",
        description="total cost over an empty cohort",
        value_sql="SELECT SUM(CAST(client_id AS REAL)) FROM data WHERE dest = 'nowhere'",
        slice_sql="SELECT * FROM data WHERE dest = 'nowhere'",
        unit="currency",
    )
    with pytest.raises(ValueError, match="NULL"):
        compute_figures(ROWS, [empty_sum], clock=FixedClock())
    with pytest.raises(ValueError, match="COALESCE"):
        compute_figures(ROWS, [empty_sum], clock=FixedClock())


def test_division_by_zero_percentage_fails_closed() -> None:
    """The shipped examples' own percent shape: NULL when the denominator is 0.

    ``ROUND(100.0 * SUM(...) / COUNT(*))`` over an empty cohort is NULL in
    SQLite, which previously published as "0%" -- a rate asserted over nobody.
    """

    rate = MetricSpec(
        metric_id="permanent_exit_rate",
        description="permanent exit rate with no one in the denominator",
        value_sql=(
            "SELECT ROUND(100.0 * SUM(CASE WHEN dest = 'permanent' THEN 1 ELSE 0 END) "
            "/ COUNT(*)) FROM data WHERE dest = 'nowhere'"
        ),
        slice_sql="SELECT * FROM data WHERE dest = 'nowhere'",
        unit="percent",
    )
    with pytest.raises(ValueError, match="permanent_exit_rate"):
        compute_figures(ROWS, [rate], clock=FixedClock())


def test_explicit_coalesce_still_publishes_a_genuine_zero() -> None:
    """The author-declared "zero when empty" case must keep working.

    Fail-closed on NULL must not take the legitimate escape hatch with it:
    an author who means zero says so, and several shipped example specs do.
    """

    coalesced = MetricSpec(
        metric_id="total_cost",
        description="total cost, explicitly zero when the cohort is empty",
        value_sql=(
            "SELECT COALESCE(SUM(CAST(client_id AS REAL)), 0) FROM data WHERE dest = 'nowhere'"
        ),
        slice_sql="SELECT * FROM data WHERE dest = 'nowhere'",
        unit="currency",
    )
    [figure] = compute_figures(ROWS, [coalesced], clock=FixedClock())
    assert figure.value == 0.0
    assert figure.receipt.value == 0.0


def test_counting_zero_rows_is_still_a_true_zero() -> None:
    """COUNT(*) returns 0, not NULL. A genuine zero must stay publishable."""

    [figure] = compute_figures(
        ROWS,
        [
            MetricSpec(
                metric_id="n",
                description="rows with an impossible destination",
                value_sql="SELECT COUNT(*) FROM data WHERE dest = 'nowhere'",
                slice_sql="SELECT * FROM data WHERE dest = 'nowhere'",
                unit="count",
            )
        ],
        clock=FixedClock(),
    )
    assert figure.value == 0.0
    assert figure.display == "0"


def test_non_numeric_scalar_fails_closed_naming_the_metric() -> None:
    """A text scalar must not raise a bare float() error that names no metric."""

    texty = MetricSpec(
        metric_id="not_a_number",
        description="a value query returning text",
        value_sql="SELECT dest FROM data LIMIT 1",
        slice_sql="SELECT * FROM data",
        unit="count",
    )
    with pytest.raises(ValueError, match="not_a_number"):
        compute_figures(ROWS, [texty], clock=FixedClock())
