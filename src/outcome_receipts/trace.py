"""Funder-facing trace view: a static, accessible HTML rendering of the receipts.

The receipts manifest proves every figure, but it is JSON, so the grant manager or
program officer who actually receives the report cannot read it. This renders the
same receipts as one self-contained HTML page a non-engineer opens in a browser:
a summary table of every figure with its value and plain-language definition, then
a detail block per figure carrying the receipt that backs it (any recorded
logic-model mapping, the query, the row count, the slice hash, the timestamp). No
SQL and no Python are needed to read it.

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
from outcome_receipts.copy import ReportCopy, get_copy, normalize_locale
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
table { border-collapse: collapse; table-layout: fixed; width: 100%; margin: 1rem 0; }
caption { text-align: left; font-weight: bold; margin-bottom: 0.5rem; }
th, td {
  border: 1px solid #cbd5e0;
  padding: 0.5rem 0.6rem;
  text-align: left;
  vertical-align: top;
  overflow-wrap: anywhere;
}
th { background: #edf2f7; }
.value { font-variant-numeric: tabular-nums; font-weight: bold; }
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
@media (max-width: 30rem) {
  body { padding-inline: 0.5rem; }
  dl { grid-template-columns: minmax(0, 1fr); }
}
""".strip()


def _esc(text: str) -> str:
    """Escape text for inclusion in HTML."""

    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )


def _anchor(metric_id: str) -> str:
    return f"metric-{metric_id}"


def _summary_table(figures: Sequence[Figure], copy: ReportCopy) -> list[str]:
    lines = [
        "<table>",
        f"<caption>{_esc(copy.trace_figures_caption)}</caption>",
        "<thead>",
        "<tr>"
        f'<th scope="col">{_esc(copy.trace_header_figure)}</th>'
        f'<th scope="col">{_esc(copy.trace_header_value)}</th>'
        f'<th scope="col">{_esc(copy.trace_header_definition)}</th>'
        f'<th scope="col">{_esc(copy.trace_header_caveat)}</th>'
        f'<th scope="col">{_esc(copy.trace_header_rows)}</th>'
        "</tr>",
        "</thead>",
        "<tbody>",
    ]
    for figure in figures:
        receipt = figure.receipt
        definition = receipt.definition or copy.trace_no_definition
        caveat = receipt.caveat or copy.trace_none
        lines.append(
            "<tr>"
            f'<td><a href="#{_anchor(figure.metric_id)}">{_esc(figure.metric_id)}</a></td>'
            f'<td class="value">{_esc(figure.display)}</td>'
            f"<td>{_esc(definition)}</td>"
            f"<td>{_esc(caveat)}</td>"
            f"<td>{receipt.row_count}</td>"
            "</tr>"
        )
    lines.extend(["</tbody>", "</table>"])
    return lines


def _change_label(row: ComparisonRow, figure: Figure, copy: ReportCopy) -> str:
    """A plain-language direction+magnitude label for a delta figure.

    Direction is ``row.direction`` and the magnitude is ``figure.display`` (the
    delta figure's already-formatted magnitude); neither is recomputed here, so no
    new number is introduced. "No change" carries no magnitude.
    """

    if row.direction == "no change":
        return copy.direction_no_change.capitalize()
    template = (
        copy.trace_increase_template
        if row.direction == "increase"
        else copy.trace_decrease_template
    )
    return template.format(value=_esc(figure.display))


def _figure_detail(figure: Figure, copy: ReportCopy, row: ComparisonRow | None = None) -> list[str]:
    receipt = figure.receipt
    definition = receipt.definition or copy.trace_no_definition
    lines = [
        f'<section class="figure" id="{_anchor(figure.metric_id)}" '
        f'aria-labelledby="{_anchor(figure.metric_id)}-h">',
        f'<h2 id="{_anchor(figure.metric_id)}-h">'
        f'{_esc(figure.metric_id)}: <span class="value">{_esc(figure.display)}</span></h2>',
        f"<p>{_esc(definition)}</p>",
    ]
    if row is not None:
        lines.append(f'<p class="change">{_change_label(row, figure, copy)}</p>')
    if receipt.caveat:
        lines.append(
            f'<p class="caveat">{_esc(copy.receipt_caveat_label.capitalize())}: '
            f"{_esc(receipt.caveat)}</p>"
        )
    lines += [
        "<dl>",
    ]
    # The logic-model mapping ties the figure to a theory-of-change row. Each field
    # is optional, so a mapping term shows only when it was recorded; a figure with
    # no mapping renders exactly as before.
    for label, value in (
        (copy.receipt_indicator_label.capitalize(), receipt.indicator),
        (copy.receipt_data_source_label.capitalize(), receipt.data_source),
        (copy.receipt_collection_frequency_label.capitalize(), receipt.collection_frequency),
    ):
        if value:
            lines.append(f"<dt>{label}</dt><dd>{_esc(value)}</dd>")
    lines.extend(
        [
            f"<dt>{_esc(copy.receipt_query_label.capitalize())}</dt>"
            f"<dd><code>{_esc(receipt.value_sql)}</code></dd>",
            f"<dt>{_esc(copy.receipt_rows_label.capitalize())}</dt><dd>{receipt.row_count}</dd>",
            f"<dt>{_esc(copy.receipt_slice_hash_label.capitalize())}</dt>"
            f'<dd class="hash">{_esc(receipt.slice_hash)}</dd>',
            f"<dt>{_esc(copy.receipt_computed_at_label.capitalize())}</dt>"
            f"<dd>{_esc(receipt.computed_at)}</dd>",
        ]
    )
    if row is not None:
        lines.append(
            f"<dt>{_esc(copy.trace_compared_periods_label)}</dt>"
            "<dd>"
            + copy.trace_compared_periods_template.format(
                prior=(
                    f'<a href="#{_anchor(row.prior.metric_id)}">{_esc(row.prior.metric_id)}</a>'
                ),
                current=(
                    f'<a href="#{_anchor(row.current.metric_id)}">{_esc(row.current.metric_id)}</a>'
                ),
            )
            + "</dd>"
        )
    lines.extend(["</dl>", "</section>"])
    return lines


def render_trace_html(
    title: str,
    figures: Sequence[Figure],
    *,
    provenance: Provenance | None = None,
    comparison: ComparisonResult | None = None,
    locale: str = "en",
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

    selected_locale = normalize_locale(locale)
    copy = get_copy(selected_locale)
    delta_rows: dict[str, ComparisonRow] = (
        {row.delta.metric_id: row for row in comparison.rows} if comparison is not None else {}
    )
    ordered = sorted(figures, key=lambda f: f.metric_id)
    head = [
        "<!doctype html>",
        f'<html lang="{selected_locale}">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{_esc(copy.trace_title_template.format(title=title))}</title>",
        f"<style>{_STYLE}</style>",
        "</head>",
        "<body>",
        "<main>",
        f"<h1>{_esc(copy.trace_title_template.format(title=title))}</h1>",
        f'<p class="muted">{_esc(copy.trace_intro)}</p>',
    ]
    if provenance is not None:
        template = (
            copy.trace_provenance_pass_template
            if provenance.gate_pass
            else copy.trace_provenance_fail_template
        )
        head.append(
            '<p class="provenance">'
            + _esc(
                template.format(
                    bound=provenance.numbers_bound,
                    unbound=provenance.numbers_unbound,
                )
            )
            + "</p>"
        )
    body = _summary_table(ordered, copy)
    body.append(f"<h2>{_esc(copy.trace_details_heading)}</h2>")
    for figure in ordered:
        body.extend(_figure_detail(figure, copy, delta_rows.get(figure.metric_id)))
    tail = ["</main>", "</body>", "</html>"]
    return "\n".join([*head, *body, *tail]) + "\n"
