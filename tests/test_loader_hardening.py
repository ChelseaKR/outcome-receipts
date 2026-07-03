"""Fail-closed loader hardening (FIX-07).

Messy real exports must fail closed with a clear error that names the offending
scope — the file, a column, or a data row — and the rule it broke. Each test
below is one malformed-input mode; the well-formed cases prove the loader neither
corrupts good data nor changes the digest for the same bytes.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from outcome_receipts.engine import (
    LoaderError,
    load_table,
    read_csv,
    read_csv_meta,
)


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "data.csv"
    path.write_text(text, encoding="utf-8")
    return path


def test_duplicate_header_names_the_column(tmp_path: Path) -> None:
    path = _write(tmp_path, "client_id,client_id\nC1,C2\n")
    with pytest.raises(LoaderError, match="duplicate header column 'client_id'"):
        read_csv(path)


def test_blank_header_names_the_column(tmp_path: Path) -> None:
    path = _write(tmp_path, "client_id,  ,dest\nC1,x,permanent\n")
    with pytest.raises(LoaderError, match="column 2 has an empty or whitespace-only header"):
        read_csv(path)


def test_quote_in_header_loads_without_corruption(tmp_path: Path) -> None:
    # A header containing a double-quote must load intact and be queryable, not
    # break or inject the DDL. The value under it survives unchanged.
    path = _write(tmp_path, 'client_id,"weird""col"\nC1,keepme\n')
    rows = read_csv(path)
    assert rows == [{"client_id": "C1", 'weird"col': "keepme"}]

    conn = load_table(rows)
    try:
        [(value,)] = conn.execute('SELECT "weird""col" FROM data').fetchall()
    finally:
        conn.close()
    assert value == "keepme"


def test_ragged_row_too_few_fields_names_the_row(tmp_path: Path) -> None:
    path = _write(tmp_path, "client_id,dest\nC1,permanent\nC2\n")
    with pytest.raises(LoaderError, match="row 3 has 1 fields, expected 2"):
        read_csv(path)


def test_ragged_row_too_many_fields_names_the_row(tmp_path: Path) -> None:
    path = _write(tmp_path, "client_id,dest\nC1,permanent,extra\n")
    with pytest.raises(LoaderError, match="row 2 has 3 fields, expected 2"):
        read_csv(path)


def test_empty_file_names_the_file(tmp_path: Path) -> None:
    path = _write(tmp_path, "")
    with pytest.raises(LoaderError, match="data.csv: file is empty"):
        read_csv(path)


def test_blank_first_line_names_the_file(tmp_path: Path) -> None:
    path = _write(tmp_path, "\nclient_id,dest\nC1,permanent\n")
    with pytest.raises(LoaderError, match="data.csv: no header row"):
        read_csv(path)


def test_header_only_file_names_the_file(tmp_path: Path) -> None:
    path = _write(tmp_path, "client_id,dest\n")
    with pytest.raises(LoaderError, match="data.csv: file has a header but no data rows"):
        read_csv(path)


def test_load_table_rejects_empty_rows() -> None:
    with pytest.raises(LoaderError, match="no data rows"):
        load_table([])


def test_wellformed_csv_returns_rows_and_meta(tmp_path: Path) -> None:
    path = _write(tmp_path, "client_id,dest\nC1,permanent\nC2,temporary\n")
    table = read_csv_meta(path)
    assert table.rows == [
        {"client_id": "C1", "dest": "permanent"},
        {"client_id": "C2", "dest": "temporary"},
    ]
    assert table.columns == ["client_id", "dest"]
    assert table.row_count == 2
    assert len(table.digest) == 64


def test_digest_is_stable_for_same_bytes(tmp_path: Path) -> None:
    text = "client_id,dest\nC1,permanent\n"
    first = read_csv_meta(_write(tmp_path, text)).digest
    other = tmp_path / "copy.csv"
    other.write_text(text, encoding="utf-8")
    assert read_csv_meta(other).digest == first


def test_digest_changes_with_content(tmp_path: Path) -> None:
    a = read_csv_meta(_write(tmp_path, "client_id,dest\nC1,permanent\n")).digest
    other = tmp_path / "other.csv"
    other.write_text("client_id,dest\nC1,temporary\n", encoding="utf-8")
    assert read_csv_meta(other).digest != a


def test_utf8_bom_is_stripped_from_first_header(tmp_path: Path) -> None:
    path = tmp_path / "bom.csv"
    path.write_bytes("client_id,dest\nC1,permanent\n".encode("utf-8-sig"))
    rows = read_csv(path)
    assert rows == [{"client_id": "C1", "dest": "permanent"}]
