"""Tests for the deterministic `receipts init` spec scaffolder.

The scaffolder must be a pure function of the input export (determinism), must
surface every column so the author knows what SQL can reference (inventory), and
must emit stubs that parse as TOML yet fail to load as a spec (fail loudly). It
must never invent a definition or a query.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from outcome_receipts.config import load_spec
from outcome_receipts.scaffold import scaffold_spec

_HEADER = "client_id,program,enrolled_date,exit_date,exit_destination"
_COLUMNS = _HEADER.split(",")


def _fixture_csv(tmp_path: Path) -> Path:
    csv_path = tmp_path / "services.csv"
    csv_path.write_text(
        _HEADER + "\n"
        "C001,housing,2025-01-08,2025-03-20,permanent\n"
        "C002,housing,2025-01-12,2025-04-02,temporary\n",
        encoding="utf-8",
    )
    return csv_path


def test_scaffold_is_deterministic(tmp_path: Path) -> None:
    csv_path = _fixture_csv(tmp_path)
    first = scaffold_spec(csv_path)
    second = scaffold_spec(csv_path)
    assert first == second


def test_every_column_appears_in_inventory(tmp_path: Path) -> None:
    csv_path = _fixture_csv(tmp_path)
    text = scaffold_spec(csv_path)
    for column in _COLUMNS:
        assert f"#   - {column}" in text


def test_columns_are_listed_in_file_order(tmp_path: Path) -> None:
    csv_path = _fixture_csv(tmp_path)
    text = scaffold_spec(csv_path)
    positions = [text.index(column) for column in _COLUMNS]
    assert positions == sorted(positions)


def test_data_path_is_the_csv_basename(tmp_path: Path) -> None:
    nested = tmp_path / "exports"
    nested.mkdir()
    csv_path = _fixture_csv(nested)
    parsed = tomllib.loads(scaffold_spec(csv_path))
    assert parsed["data"]["path"] == "services.csv"


def test_scaffold_parses_as_toml(tmp_path: Path) -> None:
    csv_path = _fixture_csv(tmp_path)
    parsed = tomllib.loads(scaffold_spec(csv_path))
    assert parsed["metrics"]["row_count"]["value_sql"] == ""
    assert parsed["metrics"]["row_count"]["slice_sql"] == ""
    assert parsed["metrics"]["row_count"]["definition"] == ""


def test_stub_fails_to_load_because_sql_is_empty(tmp_path: Path) -> None:
    csv_path = _fixture_csv(tmp_path)
    spec_path = tmp_path / "scaffold.toml"
    spec_path.write_text(scaffold_spec(csv_path), encoding="utf-8")
    with pytest.raises(ValueError, match="value_sql and slice_sql"):
        load_spec(spec_path)


def test_title_override_is_used(tmp_path: Path) -> None:
    csv_path = _fixture_csv(tmp_path)
    parsed = tomllib.loads(scaffold_spec(csv_path, title="My Program"))
    assert parsed["report"]["title"] == "My Program"


def test_header_only_csv_still_scaffolds(tmp_path: Path) -> None:
    csv_path = tmp_path / "empty.csv"
    csv_path.write_text(_HEADER + "\n", encoding="utf-8")
    text = scaffold_spec(csv_path)
    for column in _COLUMNS:
        assert f"#   - {column}" in text


def test_headerless_csv_errors_clearly(tmp_path: Path) -> None:
    csv_path = tmp_path / "nohdr.csv"
    csv_path.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="no header"):
        scaffold_spec(csv_path)
