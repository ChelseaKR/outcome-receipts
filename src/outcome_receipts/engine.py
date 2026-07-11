"""The deterministic metric engine.

Service data is loaded into an in-memory SQLite database (standard library, no
external dependency), and each MetricSpec is run as a SQL query. The value comes
from the query, never from generated text. Every figure carries a receipt: the
exact query, the count of rows in its slice, a BLAKE2b hash of those rows, the
value, and a timestamp. The same data and spec always produce the same figure and
the same receipt.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import sqlite3
from collections.abc import Sequence
from pathlib import Path
from typing import NamedTuple

from outcome_receipts.clock import Clock, SystemClock
from outcome_receipts.models import (
    EMPTY_SLICE_HASH,
    HASH_DIGEST_SIZE,
    DataCheck,
    Figure,
    MetricSpec,
    Receipt,
)

# Scalar values that count as a failed data check. A check's ``assert_sql`` returns
# a single scalar; anything in this set (plus None) is treated as falsy so a check
# fails closed rather than silently passing on an empty or "false" result.
_FALSY = frozenset({0, "0", "", "false", "False", "FALSE"})


class DataCheckError(Exception):
    """Raised when an author-declared data-quality check fails or is malformed.

    A data check runs before any figure is computed, so this exception fails the
    whole run closed: no receipt is produced from data that violated a declared
    precondition.
    """


class LoaderError(Exception):
    """Raised when input data is malformed and must fail closed.

    The message always names the offending scope — the file, a column, or a data
    row — and the rule that was violated, so a messy real export produces a clear,
    actionable error instead of a silently wrong table or an opaque failure far
    downstream. Every loader guard raises this rather than swallowing bad input.
    """


class LoadedTable(NamedTuple):
    """The validated result of reading a data file.

    ``rows`` are the stripped row dicts (what the rest of the engine consumes).
    ``columns`` is the header in file order. ``row_count`` is the number of data
    rows, and ``digest`` is a BLAKE2b-256 hex digest of the raw file bytes, so the
    exact input can be recorded and re-identified: the same bytes always produce
    the same digest.
    """

    rows: list[dict[str, str]]
    columns: list[str]
    row_count: int
    digest: str


def _quote_ident(name: str) -> str:
    """Quote a SQL identifier, escaping embedded double-quotes by doubling them.

    A header like ``client "id"`` or one containing a quote must not be able to
    break out of its quoting and change or inject DDL. Doubling the embedded quote
    is the SQL-standard escape and preserves the real column name, so genuine HMIS
    headers (which do contain punctuation) load intact rather than being rejected.
    """

    return '"' + name.replace('"', '""') + '"'


def load_table(rows: Sequence[dict[str, str]], *, table: str = "data") -> sqlite3.Connection:
    """Load a list of row dicts into an in-memory SQLite table.

    All columns are stored as text, which keeps loading deterministic and lets the
    metric SQL cast where it needs a number. The column set is the keys of the
    first row; rows are expected to share a schema (CSV guarantees this).

    Fails closed on an empty ``rows``: an empty table would surface only as an
    opaque error deep in a metric query, so it is rejected here with a clear
    ``LoaderError`` instead of silently creating a placeholder table.
    """

    # S608 (SQL-injection lint) is a false positive on `table` and `columns`
    # below: `table` defaults to the "data" constant everywhere it is called
    # (grep confirms no caller passes a dynamic value), and `columns` are CSV
    # header names read as identifiers, not values; both pass through
    # _quote_ident, which doubles any embedded double-quote. Neither is
    # user-supplied in the request-body sense the rule guards against.
    if not rows:
        raise LoaderError("cannot load table: no data rows (an empty dataset is rejected)")
    conn = sqlite3.connect(":memory:")
    columns = list(rows[0].keys())
    quoted = ", ".join(f"{_quote_ident(c)} TEXT" for c in columns)
    conn.execute(f"CREATE TABLE {_quote_ident(table)} ({quoted})")
    placeholders = ", ".join("?" for _ in columns)
    conn.executemany(
        f"INSERT INTO {_quote_ident(table)} VALUES ({placeholders})",  # noqa: S608
        [tuple(row.get(c, "") for c in columns) for row in rows],
    )
    conn.commit()
    return conn


def read_csv_meta(path: Path) -> LoadedTable:
    """Read and validate a CSV, failing closed on malformed input.

    Every check names its scope so the caller can fix the file: an empty or
    header-only file names the file; a duplicate or blank header names the column;
    a row whose field count does not match the header names the row number. On
    success the raw bytes are digested (BLAKE2b-256) so the exact input can be
    recorded and reproduced.
    """

    raw = path.read_bytes()
    digest = hashlib.blake2b(raw, digest_size=32).hexdigest()

    reader = csv.reader(io.StringIO(raw.decode("utf-8-sig")))
    try:
        header = next(reader)
    except StopIteration:
        raise LoaderError(f"{path}: file is empty; a header row is required") from None
    if not header:
        raise LoaderError(f"{path}: no header row; a header row is required")

    seen: set[str] = set()
    columns: list[str] = []
    for index, name in enumerate(header, start=1):
        column = name.strip()
        if not column:
            raise LoaderError(f"{path}: column {index} has an empty or whitespace-only header")
        if column in seen:
            raise LoaderError(f"{path}: duplicate header column {column!r}")
        seen.add(column)
        columns.append(column)

    rows: list[dict[str, str]] = []
    for line_number, record in enumerate(reader, start=2):
        if len(record) != len(columns):
            raise LoaderError(
                f"{path}: row {line_number} has {len(record)} fields, expected {len(columns)}"
            )
        rows.append({col: (val or "").strip() for col, val in zip(columns, record, strict=True)})

    if not rows:
        raise LoaderError(f"{path}: file has a header but no data rows")

    return LoadedTable(rows=rows, columns=columns, row_count=len(rows), digest=digest)


def read_csv(path: Path) -> list[dict[str, str]]:
    """Read a CSV into a list of validated row dicts, values stripped.

    A thin wrapper over :func:`read_csv_meta` for callers that only need the rows;
    the same fail-closed validation applies. Use :func:`read_csv_meta` when the
    file digest or row/column counts are needed (for provenance at load time).
    """

    return read_csv_meta(path).rows


def _slice_hash(column_names: Sequence[str], slice_rows: list[tuple[object, ...]]) -> str:
    """BLAKE2b-256 over the canonical JSON of the slice's columns and rows.

    Rows are sorted so the hash does not depend on query row order, and each value
    is stringified so the hash is stable regardless of SQLite's column typing. The
    sorted column names are folded into the payload (canonicalization ``v1``), so a
    slice whose values are unchanged but whose columns were renamed hashes
    differently — under the earlier rules a rename was invisible.

    A slice with zero rows still returns ``EMPTY_SLICE_HASH`` regardless of its
    columns, preserving the invariant that an empty slice is a single visible
    sentinel rather than a family of column-dependent hashes. See ADR 0005.
    """

    if not slice_rows:
        return EMPTY_SLICE_HASH
    canonical_rows = [[str(value) for value in row] for row in slice_rows]
    canonical_rows.sort()
    payload = json.dumps(
        {"columns": sorted(column_names), "rows": canonical_rows},
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.blake2b(payload.encode("utf-8"), digest_size=HASH_DIGEST_SIZE).hexdigest()


def _format(value: float, unit: str, decimals: int) -> str:
    """Render a value to its display string, deterministically.

    A count is an integer with thousands separators; a percent appends ``%``. The
    display is what the drafter writes and what the grounding gate matches, so it
    must be a single canonical form per figure.
    """

    if unit == "percent":
        return f"{value:.{decimals}f}%"
    if decimals == 0:
        return f"{round(value):,}"
    return f"{value:,.{decimals}f}"


def _execute(conn: sqlite3.Connection, sql: str, spec: MetricSpec) -> sqlite3.Cursor:
    """Run a metric's SQL, failing closed on a missing column.

    A query that references a column absent from the export raises a sqlite3
    ``OperationalError`` ("no such column: <name>"). Catch it and re-raise a
    ``ValueError`` naming the missing column and the metric, so the operator sees
    what is wrong rather than a raw driver error. Any other OperationalError is
    re-raised as a ValueError too, so a bad spec never silent-passes.
    """

    try:
        return conn.execute(sql)
    except sqlite3.OperationalError as exc:
        message = str(exc)
        if message.startswith("no such column:"):
            col = message.split(":", 1)[1].strip()
            raise ValueError(
                f"metric {spec.metric_id!r} references column {col!r} which is not in the export"
            ) from exc
        raise ValueError(f"metric {spec.metric_id!r} query failed: {message}") from exc


def compute_figure(
    conn: sqlite3.Connection, spec: MetricSpec, *, clock: Clock | None = None
) -> Figure:
    """Run one MetricSpec against the connection and return a Figure.

    Raises ``ValueError`` if the value query does not return exactly one scalar,
    so a malformed metric fails loudly rather than producing a silent wrong number.
    Also raises ``ValueError`` naming any column a query references that is absent
    from the export, so a bad spec against a messy export fails closed.
    """

    clock = clock or SystemClock()

    cursor = _execute(conn, spec.value_sql, spec)
    value_rows = cursor.fetchall()
    if len(value_rows) != 1 or len(value_rows[0]) != 1:
        raise ValueError(
            f"metric {spec.metric_id!r} value_sql must return exactly one scalar; "
            f"got {len(value_rows)} rows"
        )
    raw_value = value_rows[0][0]
    value = float(raw_value) if raw_value is not None else 0.0

    slice_cursor = _execute(conn, spec.slice_sql, spec)
    slice_rows = slice_cursor.fetchall()
    columns = tuple(d[0] for d in slice_cursor.description or ())

    receipt = Receipt(
        metric_id=spec.metric_id,
        value_sql=spec.value_sql,
        row_count=len(slice_rows),
        slice_hash=_slice_hash(columns, slice_rows),
        value=value,
        unit=spec.unit,
        computed_at=clock.now_iso(),
        definition=spec.definition,
        kind=spec.kind,
        column_names=columns,
    )
    return Figure(
        metric_id=spec.metric_id,
        value=value,
        display=_format(value, spec.unit, spec.decimals),
        receipt=receipt,
    )


def run_data_checks(conn: sqlite3.Connection, checks: Sequence[DataCheck]) -> None:
    """Assert every author-declared data-quality precondition, fail closed.

    Each check's ``assert_sql`` must return exactly one scalar (mirroring
    ``compute_figure``'s scalar guard); a wrong shape raises ``DataCheckError``
    because a precondition that cannot be evaluated is not a precondition that
    passed. A falsy scalar (None, 0, "0", "", "false") is a violated precondition
    and raises ``DataCheckError`` naming the check and its author message. Runs
    before any figure is computed, so a failure blocks the whole run.
    """

    for check in checks:
        rows = conn.execute(check.assert_sql).fetchall()
        if len(rows) != 1 or len(rows[0]) != 1:
            raise DataCheckError(
                f"data check {check.check_id!r} assert_sql must return exactly one "
                f"scalar; got {len(rows)} rows"
            )
        scalar = rows[0][0]
        if scalar is None or scalar in _FALSY:
            detail = f": {check.message}" if check.message else ""
            raise DataCheckError(f"data check {check.check_id!r} failed{detail}")


def compute_figures(
    rows: Sequence[dict[str, str]],
    specs: Sequence[MetricSpec],
    *,
    clock: Clock | None = None,
    table: str = "data",
    data_checks: Sequence[DataCheck] = (),
) -> list[Figure]:
    """Compute every figure for a dataset. One connection, reused per metric.

    Author-declared ``data_checks`` run first, on the same connection the metrics
    use, so the checks and the figures see identical loaded data. A failing check
    raises ``DataCheckError`` before any figure is produced -- fail closed.
    """

    conn = load_table(rows, table=table)
    try:
        run_data_checks(conn, data_checks)
        return [compute_figure(conn, spec, clock=clock) for spec in specs]
    finally:
        conn.close()
