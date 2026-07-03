"""Funder-facing trace view: a static, accessible HTML rendering of the receipts.

The receipts manifest proves every figure, but it is JSON, so the grant manager or
program officer who actually receives the report cannot read it. This renders the
same receipts as one self-contained HTML page a non-engineer opens in a browser:
a summary table of every figure with its value and plain-language definition, then
a detail block per figure carrying the receipt that backs it (the query, the row
count, the slice hash, the timestamp). No SQL and no Python are needed to read it.

The page is a single file with inline styling and no script, so it travels beside
the report and opens offline, keeping the project's zero-dependency posture. It is
assembled from the same figures and provenance the report and manifest use, so it
introduces no second path to a number; it is a rendering of receipts that already
exist. The markup is semantic and high-contrast (one ``<h1>``, table headers with
``scope``, a ``<caption>``, dark text on white) so the trace view meets WCAG 2.2 AA
the way the chart output does.
"""

from __future__ import annotations

from collections.abc import Sequence

from outcome_receipts.comparison import ComparisonResult, ComparisonRow
from outcome_receipts.models import Figure
from outcome_receipts.provenance import Provenance

_STYLE = """
:root { color-scheme: light; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica,
    Arial, sans-serif;
  color: #1a202c;
  background: #ffffff;
  line-height: 1.5;
  max-width: 52rem;
  margin: 0 auto;
  padding: 2rem 1.25rem 4rem;
}
h1 { font-size: 1.6rem; margin-bottom: 0.25rem; }
h2 { font-size: 1.15rem; margin-top: 2rem; }
.provenance {
  border-left: 4px solid #2b6cb0;
  background: #f7fafc;
  padding: 0.75rem 1rem;
  margin: 1.25rem 0;
}
table { border-collapse: collapse; width: 100%; margin: 1rem 0; }
caption { text-align: left; font-weight: bold; margin-bottom: 0.5rem; }
th, td {
  border: 1px solid #cbd5e0;
  padding: 0.5rem 0.6rem;
  text-align: left;
  vertical-align: top;
}
th { background: #edf2f7; }
.value { font-variant-numeric: tabular-nums; font-weight: bold; white-space: nowrap; }
.figure { margin-top: 1.75rem; padding-top: 0.5rem; border-top: 1px solid #e2e8f0; }
dl { display: grid; grid-template-columns: max-content 1fr; gap: 0.35rem 1rem; }
dt { font-weight: bold; }
dd { margin: 0; }
code, .hash {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.9rem;
  word-break: break-all;
}
.muted { color: #4a5568; }
.change { font-weight: bold; margin: 0.5rem 0; }
""".strip()


def _esc(text: str) -> str:
    """Escape text for inclusion in HTML."""

    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )


def _anchor(metric_id: str) -> str:
    return f"metric-{metric_id}"


def _summary_table(figures: Sequence[Figure]) -> list[str]:
    lines = [
        "<table>",
        "<caption>Figures in this report</caption>",
        "<thead>",
        "<tr>"
        '<th scope="col">Figure</th>'
        '<th scope="col">Value</th>'
        '<th scope="col">What it counts</th>'
        '<th scope="col">Rows</th>'
        "</tr>",
        "</thead>",
        "<tbody>",
    ]
    for figure in figures:
        receipt = figure.receipt
        definition = receipt.definition or "(no definition recorded)"
        lines.append(
            "<tr>"
            f'<td><a href="#{_anchor(figure.metric_id)}">{_esc(figure.metric_id)}</a></td>'
            f'<td class="value">{_esc(figure.display)}</td>'
            f"<td>{_esc(definition)}</td>"
            f"<td>{receipt.row_count}</td>"
            "</tr>"
        )
    lines.extend(["</tbody>", "</table>"])
    return lines


def _change_label(row: ComparisonRow, figure: Figure) -> str:
    """A plain-language direction+magnitude label for a delta figure.

    Direction is ``row.direction`` and the magnitude is ``figure.display`` (the
    delta figure's already-formatted magnitude); neither is recomputed here, so no
    new number is introduced. "No change" carries no magnitude.
    """

    if row.direction == "no change":
        return "No change"
    word = "Increase" if row.direction == "increase" else "Decrease"
    return f"{word} of {_esc(figure.display)}"


def _figure_detail(figure: Figure, row: ComparisonRow | None = None) -> list[str]:
    receipt = figure.receipt
    definition = receipt.definition or "(no definition recorded)"
    lines = [
        f'<section class="figure" id="{_anchor(figure.metric_id)}" '
        f'aria-labelledby="{_anchor(figure.metric_id)}-h">',
        f'<h2 id="{_anchor(figure.metric_id)}-h">'
        f'{_esc(figure.metric_id)}: <span class="value">{_esc(figure.display)}</span></h2>',
        f"<p>{_esc(definition)}</p>",
    ]
    if row is not None:
        lines.append(f'<p class="change">{_change_label(row, figure)}</p>')
    lines.extend(
        [
            "<dl>",
            f"<dt>Query</dt><dd><code>{_esc(receipt.value_sql)}</code></dd>",
            f"<dt>Rows in slice</dt><dd>{receipt.row_count}</dd>",
            f'<dt>Slice hash</dt><dd class="hash">{_esc(receipt.slice_hash)}</dd>',
            f"<dt>Computed at</dt><dd>{_esc(receipt.computed_at)}</dd>",
        ]
    )
    if row is not None:
        lines.append(
            "<dt>Compared periods</dt>"
            "<dd>"
            f'<a href="#{_anchor(row.prior.metric_id)}">{_esc(row.prior.metric_id)}</a>'
            " and "
            f'<a href="#{_anchor(row.current.metric_id)}">{_esc(row.current.metric_id)}</a>'
            "</dd>"
        )
    lines.extend(["</dl>", "</section>"])
    return lines


def render_trace_html(
    title: str,
    figures: Sequence[Figure],
    *,
    provenance: Provenance | None = None,
    comparison: ComparisonResult | None = None,
) -> str:
    """Render the receipts as a single accessible HTML page.

    Figures are listed in metric-id order, matching the report's receipts section,
    so a reader moving between the two documents sees the same order. When a
    ``provenance`` is given, the no-model and gate-passed attestation heads the
    page, the same statement the report carries.

    When a ``comparison`` is given, each delta figure's detail block gains a
    plain-language direction+magnitude label and cross-links to the two period
    figures it compares. The direction and magnitude come from the comparison's
    own rows, never recomputed, so no second path to a number is introduced.
    """

    delta_rows: dict[str, ComparisonRow] = (
        {row.delta.metric_id: row for row in comparison.rows} if comparison is not None else {}
    )
    ordered = sorted(figures, key=lambda f: f.metric_id)
    head = [
        "<!doctype html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{_esc(title)}: trace this number</title>",
        f"<style>{_STYLE}</style>",
        "</head>",
        "<body>",
        "<main>",
        f"<h1>{_esc(title)}: trace this number</h1>",
        '<p class="muted">Every number in the report traces to a figure below. Each '
        "figure was computed by a deterministic query over the organization's own "
        "service data and carries a receipt: the exact query, the rows it drew from, "
        "a content hash of that data slice, and a timestamp.</p>",
    ]
    if provenance is not None:
        gate = "passed" if provenance.gate_pass else "did not pass"
        head.append(
            '<p class="provenance">No figure was written by a language model. The '
            f"grounding gate {gate}: {provenance.numbers_bound} number(s) in the "
            "report bound to a receipt, "
            f"{provenance.numbers_unbound} did not.</p>"
        )
    body = _summary_table(ordered)
    body.append("<h2>Figure details</h2>")
    for figure in ordered:
        body.extend(_figure_detail(figure, delta_rows.get(figure.metric_id)))
    tail = ["</main>", "</body>", "</html>"]
    return "\n".join([*head, *body, *tail]) + "\n"
