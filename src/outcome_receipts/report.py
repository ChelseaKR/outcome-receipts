"""Rendering for the report, the receipts manifest, and the eval.

The report is the drafted narrative with a receipts manifest appended, so a reader
or auditor can trace every figure to the query and data slice that produced it.
The eval renderer shows the gated grounding rate and whether it passed.
"""

from __future__ import annotations

import json
from collections.abc import Sequence

from outcome_receipts.charts import Chart
from outcome_receipts.comparison import ComparisonResult, ReconciliationResult
from outcome_receipts.evaluate import EvalReport
from outcome_receipts.models import Figure
from outcome_receipts.provenance import Provenance, provenance_markdown, provenance_record


def render_comparison_table(result: ComparisonResult) -> str:
    """Render a period-over-period comparison as a Markdown table.

    Every number in the table is a figure display: the two period values and the
    change. Direction is a word, derived from the sign of the change, so the table
    asserts no number that is not a receipt. The change for a rate metric is in
    percentage points, noted under the table.
    """

    lines = [
        "## Period comparison",
        "",
        f"Comparing {result.current_label} with {result.prior_label}. Each value is "
        "a figure with a receipt; the change is itself computed by a single query, "
        "not arithmetic over the page.",
        "",
        f"| Outcome | {result.prior_label} | {result.current_label} | Change | Direction |",
        "|---------|------|------|--------|-----------|",
    ]
    for row in result.rows:
        name = row.description or row.base_metric_id
        lines.append(
            f"| {name} | {row.prior.display} | {row.current.display} | "
            f"{row.delta.display} | {row.direction} |"
        )
    lines.append("")
    lines.append("Change for a rate metric is in percentage points.")
    return "\n".join(lines)


def render_reconciliation_table(result: ReconciliationResult) -> str:
    """Render the board reconciliation as Markdown: outcomes beside financial lines.

    Each row is a small table pairing the receipted outcome figure with its
    financial line, and each shows the cross-period change as a magnitude plus a
    direction word, the same display convention as the comparison table. Every
    number is a figure display, so the section asserts nothing that is not a
    receipt, and the change is itself one query, not arithmetic over the page.
    """

    lines = [
        "## Board reconciliation",
        "",
        f"Pairing each receipted outcome figure with its financial line, "
        f"{result.prior_label} to {result.current_label}. Every value is a figure "
        "with a receipt; each change is computed by a single query, not arithmetic "
        "over the page.",
        "",
    ]
    for row in result.rows:
        outcome = row.outcome
        financial = row.financial
        lines.extend(
            [
                f"### {row.label}",
                "",
                f"| Line | {result.prior_label} | {result.current_label} | Change | Direction |",
                "|------|------|------|--------|-----------|",
                f"| {outcome.description or outcome.base_metric_id} (outcome) | "
                f"{outcome.prior.display} | {outcome.current.display} | "
                f"{outcome.delta.display} | {outcome.direction} |",
                f"| {financial.description or financial.base_metric_id} (financial) | "
                f"{financial.prior.display} | {financial.current.display} | "
                f"{financial.delta.display} | {financial.direction} |",
                "",
            ]
        )
    lines.append("Change for a rate metric is in percentage points.")
    return "\n".join(lines)


def render_charts_section(charts: Sequence[Chart], *, chart_dir: str) -> str:
    """Render the charts as image references with their accessible data tables.

    The SVG is referenced as an image; the data table beneath it is the text
    equivalent and carries the same grounded numbers, so the chart is readable
    without the image and the numbers it shows trace to receipts.
    """

    lines = ["## Charts", ""]
    for chart in charts:
        lines.append(f"### {chart.title}")
        lines.append("")
        lines.append(f"![{chart.title} (see data table below)]({chart_dir}/{chart.chart_id}.svg)")
        lines.append("")
        lines.append(f"Data for the chart above ({chart.title}):")
        lines.append("")
        lines.append(chart.data_table)
        lines.append("")
    return "\n".join(lines).rstrip()


def render_report(
    title: str,
    narrative: str,
    figures: Sequence[Figure],
    *,
    comparison: ComparisonResult | None = None,
    reconciliation: ReconciliationResult | None = None,
    charts: Sequence[Chart] = (),
    chart_dir: str = "charts",
    provenance: Provenance | None = None,
) -> str:
    """Render the narrative, optional comparison, reconciliation, and charts, then
    provenance and receipts.

    When ``provenance`` is given, a standard provenance block is embedded before
    the receipts, stating that no number was written by a model and that the gate
    bound every number before export. The receipts section then lists each figure
    with its plain-language definition and the receipt that backs it.
    """

    lines = [f"# {title}", "", narrative.strip()]
    if comparison is not None:
        lines.extend(["", render_comparison_table(comparison)])
    if reconciliation is not None:
        lines.extend(["", render_reconciliation_table(reconciliation)])
    if charts:
        lines.extend(["", render_charts_section(charts, chart_dir=chart_dir)])
    if provenance is not None:
        lines.extend(["", provenance_markdown(provenance)])
    lines.extend(["", "## Receipts", ""])
    for figure in sorted(figures, key=lambda f: f.metric_id):
        receipt = figure.receipt
        lines.append(f"- **{figure.metric_id}** = {figure.display}")
        lines.append(f"  - kind: {receipt.kind}")
        if receipt.definition:
            lines.append(f"  - definition: {receipt.definition}")
        lines.append(f"  - query: `{receipt.value_sql}`")
        lines.append(f"  - rows in slice: {receipt.row_count}")
        lines.append(f"  - slice hash: `{receipt.slice_hash}`")
        lines.append(f"  - computed at: {receipt.computed_at}")
    return "\n".join(lines) + "\n"


def receipts_manifest(figures: Sequence[Figure], *, provenance: Provenance | None = None) -> str:
    """Render the receipts as a JSON manifest for machine verification.

    When ``provenance`` is given, the manifest also carries the machine-readable
    provenance attestation, so a consumer can check the no-model and gate-passed
    claims without re-reading the prose.
    """

    payload: dict[str, object] = {
        "receipts": [
            {
                "metric_id": f.receipt.metric_id,
                "value": f.receipt.value,
                "display": f.display,
                "unit": f.receipt.unit,
                "kind": f.receipt.kind,
                "definition": f.receipt.definition,
                "value_sql": f.receipt.value_sql,
                "row_count": f.receipt.row_count,
                "slice_hash": f.receipt.slice_hash,
                "computed_at": f.receipt.computed_at,
            }
            for f in sorted(figures, key=lambda f: f.metric_id)
        ]
    }
    if provenance is not None:
        payload["provenance"] = provenance_record(provenance)
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def _ci(interval: tuple[float, float]) -> str:
    low, high = interval
    return f"[{_pct(low)}, {_pct(high)}]"


def render_eval_markdown(report: EvalReport, *, dataset: str) -> str:
    """Render the committed eval report as Markdown."""

    gate_word = "PASS" if report.gate_pass else "FAIL"
    lines = [
        "# Eval report",
        "",
        f"Dataset: `{dataset}`. Generated by `receipts eval`. This file is "
        "committed and regenerated on release. The fixtures are seeded synthetic "
        "service data with planted ground-truth figures; there is no real personal "
        "data.",
        "",
        "## Why this metric",
        "",
        "A number in a funder report that is wrong or invented is the expensive, "
        "sometimes irreversible error. So the gated metric is the grounding rate: "
        "the share of numbers in the narrative that bind to a receipt. It is "
        "fail-closed at 100%; a single unbound number blocks export.",
        "",
        "## Results",
        "",
        "| Metric | Value | 95% CI |",
        "|--------|-------|--------|",
        f"| Numbers in narrative | {report.n_numbers} | |",
        f"| Bound to a receipt | {report.n_bound} | |",
        f"| **Grounding rate (gated)** | **{_pct(report.grounding_rate)}** "
        f"({report.n_bound}/{report.n_numbers}) | {_ci(report.grounding_ci)} |",
        f"| Unverifiable numbers | {report.n_unbound} | |",
        f"| Hallucinated-number rate | {_pct(report.hallucinated_rate)} "
        f"({report.n_unbound}/{report.n_numbers}) | {_ci(report.hallucinated_ci)} |",
        "",
        "## Gate",
        "",
        f"Grounding gate (100% required): **{gate_word}** "
        f"(observed {_pct(report.grounding_rate)}).",
        "",
        "This committed run scores the drafted narrative, every number of which "
        "comes from a receipt, so it passes. That the gate catches an injected "
        "unverifiable number is shown by the merge-blocking test "
        "`tests/test_grounding_gate.py`, not by failing this report.",
    ]
    return "\n".join(lines) + "\n"
