"""Tests for author-declared, pre-compute data-quality checks.

The invariant under test: data checks run before any figure is computed and fail
closed, so a violated precondition blocks the whole run rather than producing a
receipted-but-wrong number.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from outcome_receipts.clock import FixedClock
from outcome_receipts.config import _parse_data_checks, load_spec
from outcome_receipts.engine import (
    DataCheckError,
    compute_figures,
    load_table,
    run_data_checks,
)
from outcome_receipts.models import DataCheck, MetricSpec

# Reuse the in-memory row-dict shape from tests/test_engine.py.
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

# Passes: every row has a non-empty client_id, so the count of blank ids is zero,
# and "no blank ids" is true (1).
NO_BLANK_IDS = DataCheck(
    check_id="no_blank_client_ids",
    description="every row has a client id",
    assert_sql="SELECT COUNT(*) = 0 FROM data WHERE client_id = ''",
    message="found rows with a blank client_id",
)

# Fails: asserts there are zero rows, which is false for a non-empty dataset.
EXPECT_EMPTY = DataCheck(
    check_id="expect_empty",
    description="dataset must be empty (deliberately failing)",
    assert_sql="SELECT COUNT(*) = 0 FROM data",
    message="dataset was not empty",
)


def test_passing_check_lets_compute_proceed() -> None:
    figures = compute_figures(ROWS, [COUNT], clock=FixedClock(), data_checks=[NO_BLANK_IDS])
    assert [f.value for f in figures] == [3.0]
    assert figures[0].display == "3"


def test_failing_check_raises_before_any_figure() -> None:
    with pytest.raises(DataCheckError, match="expect_empty"):
        compute_figures(ROWS, [COUNT], clock=FixedClock(), data_checks=[EXPECT_EMPTY])


def test_failing_check_message_is_appended() -> None:
    with pytest.raises(DataCheckError, match="dataset was not empty"):
        run_data_checks(load_table(ROWS), [EXPECT_EMPTY])


def test_falsy_scalar_variants_fail_closed() -> None:
    for sql in (
        "SELECT 0",
        "SELECT '0'",
        "SELECT ''",
        "SELECT 'false'",
        "SELECT NULL",
    ):
        check = DataCheck(check_id="c", description="", assert_sql=sql)
        with pytest.raises(DataCheckError, match="failed"):
            run_data_checks(load_table(ROWS), [check])


def test_truthy_scalar_passes() -> None:
    check = DataCheck(check_id="c", description="", assert_sql="SELECT 1")
    # Should not raise.
    run_data_checks(load_table(ROWS), [check])


def test_non_scalar_assert_sql_raises() -> None:
    bad = DataCheck(
        check_id="two_columns",
        description="returns two columns, not a scalar",
        assert_sql="SELECT client_id, dest FROM data",
    )
    with pytest.raises(DataCheckError, match="exactly one scalar"):
        run_data_checks(load_table(ROWS), [bad])


def test_multi_row_assert_sql_raises() -> None:
    bad = DataCheck(
        check_id="many_rows",
        description="returns many rows, not one scalar",
        assert_sql="SELECT 1 FROM data",
    )
    with pytest.raises(DataCheckError, match="exactly one scalar"):
        run_data_checks(load_table(ROWS), [bad])


def test_empty_checks_is_a_noop() -> None:
    # No checks declared: compute proceeds and run_data_checks does nothing.
    run_data_checks(load_table(ROWS), [])
    figures = compute_figures(ROWS, [COUNT], clock=FixedClock())
    assert figures[0].value == 3.0


def test_parse_data_checks_missing_id() -> None:
    raw = [{"assert_sql": "SELECT 1"}]
    with pytest.raises(ValueError, match="must set 'id' and 'assert_sql'"):
        _parse_data_checks(raw)


def test_parse_data_checks_missing_assert_sql() -> None:
    raw = [{"id": "c"}]
    with pytest.raises(ValueError, match="must set 'id' and 'assert_sql'"):
        _parse_data_checks(raw)


def test_parse_data_checks_wrong_shape() -> None:
    with pytest.raises(ValueError, match="array of tables"):
        _parse_data_checks({"id": "c", "assert_sql": "SELECT 1"})


def test_parse_data_checks_empty_is_empty_tuple() -> None:
    assert _parse_data_checks(None) == ()
    assert _parse_data_checks([]) == ()


def test_parse_data_checks_full_entry() -> None:
    raw = [
        {
            "id": "no_blank_ids",
            "description": "every row has an id",
            "assert_sql": "SELECT COUNT(*) = 0 FROM data WHERE client_id = ''",
            "message": "blank ids present",
        }
    ]
    (check,) = _parse_data_checks(raw)
    assert check.check_id == "no_blank_ids"
    assert check.description == "every row has an id"
    assert check.message == "blank ids present"


def test_load_spec_wires_data_checks(tmp_path: Path) -> None:
    data_csv = tmp_path / "data.csv"
    data_csv.write_text("client_id,dest\nC1,permanent\n", encoding="utf-8")
    spec_toml = tmp_path / "report.toml"
    spec_toml.write_text(
        """
[data]
path = "data.csv"

[report]
template = "Served {clients} clients."

[metrics.clients]
description = "distinct clients"
value_sql = "SELECT COUNT(DISTINCT client_id) FROM data"
slice_sql = "SELECT client_id FROM data"

[[data_checks]]
id = "no_blank_ids"
assert_sql = "SELECT COUNT(*) = 0 FROM data WHERE client_id = ''"
message = "blank ids present"
""",
        encoding="utf-8",
    )
    spec = load_spec(spec_toml)
    assert len(spec.report.data_checks) == 1
    assert spec.report.data_checks[0].check_id == "no_blank_ids"
    # Sanity: the TOML itself is well-formed.
    with spec_toml.open("rb") as handle:
        assert "data_checks" in tomllib.load(handle)
