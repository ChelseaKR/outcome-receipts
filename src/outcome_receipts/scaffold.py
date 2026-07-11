"""Deterministic starter-spec scaffolding.

``scaffold_spec`` inspects an export and emits a commented TOML metric spec with
one stub metric and a full column inventory. It is a zero-model convenience: it
reads the CSV's header to tell the author which columns exist, and it writes the
spec's shape, but it never guesses a definition or a query. Every stub is left
empty on purpose so ``config.load_spec`` fails loudly until a human fills it in.
The output is a pure function of the input CSV (columns in file order, no
timestamps, no randomness), so the same export always scaffolds byte-identically.
"""

from __future__ import annotations

import csv
from pathlib import Path


def _columns(csv_path: Path) -> list[str]:
    """The CSV's column names in file order.

    Reads only the header row: a scaffold needs the column inventory, not the
    data, so a header-only export is a legitimate ``receipts init`` input even
    though the engine loader (``read_csv``) rightly fails closed on it — the
    two paths serve different moments (authoring a spec vs. computing figures).
    Names are stripped the same way the loader strips them, so a column listed
    in the scaffold inventory is the name the engine will load. Raises
    ``ValueError`` if the file has no header row at all, so a headerless file
    fails clearly here rather than producing a spec with no columns.
    """

    with csv_path.open(newline="", encoding="utf-8-sig") as handle:
        header = next(csv.reader(handle), None)
    if not header or not any(name.strip() for name in header):
        raise ValueError(f"{csv_path} has no header row; cannot derive a column inventory")
    return [name.strip() for name in header]


def _toml_basic_string(value: str) -> str:
    """Render a value as a TOML basic string, escaping what the spec requires."""

    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )
    return f'"{escaped}"'


def scaffold_spec(csv_path: Path, title: str | None = None) -> str:
    """Scaffold a starter TOML metric spec for ``csv_path``.

    Emits a spec mirroring the shape of a real report spec: a comment banner, a
    ``[data]`` path, a ``[report]`` title and placeholder template, one stub
    ``[metrics.row_count]`` table, and the full column inventory as comments. The
    stub's ``value_sql``, ``slice_sql``, and ``definition`` are deliberately empty
    so the spec fails to load until a human fills them; nothing here invents a
    definition or a query. Deterministic: identical input yields identical output.
    """

    columns = _columns(csv_path)
    filename = csv_path.name
    report_title = title if title is not None else "Outcome report (scaffold)"

    lines = [
        "# Starter spec scaffolded by `receipts init` — NOT ready to run.",
        "#",
        "# Every metric below is a STUB: its value_sql, slice_sql, and definition",
        "# are empty on purpose, so `receipts run` fails loudly until you fill them",
        "# in by hand. This tool never guesses a definition or a query; it only",
        "# lists the columns your export actually has (see the inventory below) and",
        "# writes the spec's shape. Fill each stub in, then add one metric table per",
        "# figure your report needs.",
        "",
        "[data]",
        f"path = {_toml_basic_string(filename)}",
        "",
        "[report]",
        f"title = {_toml_basic_string(report_title)}",
        "# Narrative template. Reference each metric by id as {metric_id}; every",
        "# number in the rendered text must bind to a figure or export is blocked.",
        'template = "This report covered {row_count} records."',
        "",
        "# --- Column inventory (from the export header, in file order) ---",
        "# These are the columns available to your SQL. Names only; no semantics.",
    ]
    lines.extend(f"#   - {column}" for column in columns)
    lines.extend(
        [
            "",
            "# One stub metric. Fill value_sql (a single scalar), slice_sql (the rows",
            "# it is computed over), and definition (plain language: window, who is in",
            "# scope, dedup rule). Leave nothing empty — an empty stub will not load.",
            "[metrics.row_count]",
            'description = "Number of records in the export."',
            'definition = ""',
            'value_sql = ""',
            'slice_sql = ""',
            'unit = "count"',
        ]
    )
    return "\n".join(lines) + "\n"
