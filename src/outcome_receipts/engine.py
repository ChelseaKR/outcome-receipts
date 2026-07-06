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
import json
import sqlite3
from collections.abc import Sequence
from pathlib import Path

from outcome_receipts.clock import Clock, SystemClock
from outcome_receipts.models import (
    EMPTY_SLICE_HASH,
    Figure,
    MetricSpec,
    Receipt,
)


def load_table(rows: Sequence[dict[str, str]], *, table: str = "data") -> sqlite3.Connection:
    """Load a list of row dicts into an in-memory SQLite table.

    All columns are stored as text, which keeps loading deterministic and lets the
    metric SQL cast where it needs a number. The column set is the union of keys
    in the first row; rows are expected to share a schema (CSV guarantees this).
    """

    # S608 (SQL-injection lint) is a false positive on `table` and `columns`
    # below: `table` defaults to the "data" constant everywhere it is called
    # (grep confirms no caller passes a dynamic value), and `columns` are CSV
    # header names read as identifiers, not values. Neither is user-supplied
    # in the request-body sense the rule guards against.
    conn = sqlite3.connect(":memory:")
    if not rows:
        conn.execute(f'CREATE TABLE "{table}" (_empty TEXT)')
        return conn
    columns = list(rows[0].keys())
    quoted = ", ".join(f'"{c}" TEXT' for c in columns)
    conn.execute(f'CREATE TABLE "{table}" ({quoted})')
    placeholders = ", ".join("?" for _ in columns)
    conn.executemany(
        f'INSERT INTO "{table}" VALUES ({placeholders})',  # noqa: S608
        [tuple(row.get(c, "") for c in columns) for row in rows],
    )
    conn.commit()
    return conn


def read_csv(path: Path) -> list[dict[str, str]]:
    """Read a CSV into a list of row dicts, values stripped."""

    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        return [{k: (v or "").strip() for k, v in row.items()} for row in reader]


def _slice_hash(slice_rows: list[tuple[object, ...]]) -> str:
    """BLAKE2b-256 over the canonical JSON of the slice rows.

    Rows are sorted so the hash does not depend on query row order, and each value
    is stringified so the hash is stable regardless of SQLite's column typing.
    """

    if not slice_rows:
        return EMPTY_SLICE_HASH
    canonical = [[str(value) for value in row] for row in slice_rows]
    canonical.sort()
    payload = json.dumps(canonical, separators=(",", ":"), ensure_ascii=False)
    return hashlib.blake2b(payload.encode("utf-8"), digest_size=32).hexdigest()


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


def compute_figure(
    conn: sqlite3.Connection, spec: MetricSpec, *, clock: Clock | None = None
) -> Figure:
    """Run one MetricSpec against the connection and return a Figure.

    Raises ``ValueError`` if the value query does not return exactly one scalar,
    so a malformed metric fails loudly rather than producing a silent wrong number.
    """

    clock = clock or SystemClock()

    cursor = conn.execute(spec.value_sql)
    value_rows = cursor.fetchall()
    if len(value_rows) != 1 or len(value_rows[0]) != 1:
        raise ValueError(
            f"metric {spec.metric_id!r} value_sql must return exactly one scalar; "
            f"got {len(value_rows)} rows"
        )
    raw_value = value_rows[0][0]
    value = float(raw_value) if raw_value is not None else 0.0

    slice_rows = conn.execute(spec.slice_sql).fetchall()

    receipt = Receipt(
        metric_id=spec.metric_id,
        value_sql=spec.value_sql,
        row_count=len(slice_rows),
        slice_hash=_slice_hash(slice_rows),
        value=value,
        unit=spec.unit,
        computed_at=clock.now_iso(),
        definition=spec.definition,
    )
    return Figure(
        metric_id=spec.metric_id,
        value=value,
        display=_format(value, spec.unit, spec.decimals),
        receipt=receipt,
    )


def compute_figures(
    rows: Sequence[dict[str, str]],
    specs: Sequence[MetricSpec],
    *,
    clock: Clock | None = None,
    table: str = "data",
) -> list[Figure]:
    """Compute every figure for a dataset. One connection, reused per metric."""

    conn = load_table(rows, table=table)
    try:
        return [compute_figure(conn, spec, clock=clock) for spec in specs]
    finally:
        conn.close()
