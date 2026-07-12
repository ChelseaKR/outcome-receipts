"""Rendering for the report, the receipts manifest, and the eval.

The report is the drafted narrative with a receipts manifest appended, so a reader
or auditor can trace every figure to the query and data slice that produced it.
The eval renderer shows the gated grounding rate and whether it passed.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence

from outcome_receipts.charts import Chart
from outcome_receipts.comparison import ComparisonResult
from outcome_receipts.diff import FigureDelta, ManifestDiff
from outcome_receipts.evaluate import EvalReport
from outcome_receipts.models import (
    HASH_ALGORITHM,
    HASH_CANONICALIZATION,
    HASH_DIGEST_SIZE,
    SCHEMA_VERSION,
    Figure,
)
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


def _delta_display(delta: FigureDelta, key: str) -> str:
    """The display string for one side of a changed figure, blank if absent."""

    side = delta.prior if key == "prior" else delta.current
    if side is None:
        return ""
    return str(side.get("display", side.get("value", "")))


def render_diff_markdown(
    diff: ManifestDiff,
    *,
    prior_label: str = "prior",
    current_label: str = "current",
) -> str:
    """Render a manifest-to-manifest diff as a Markdown "Receipts diff" section.

    A summary line counts the added, removed, changed, and unchanged figures. A
    table then lists each changed figure with its before and after value and the
    reasons it moved, followed by bulleted Added and Removed lists. Every value in
    the table is copied from a receipt, so the diff asserts no number that is not
    already grounded in one of the two manifests.
    """

    lines = [
        "## Receipts diff",
        "",
        f"Comparing {current_label} with {prior_label}. "
        f"{len(diff.added)} added, {len(diff.removed)} removed, "
        f"{len(diff.changed)} changed, {len(diff.unchanged)} unchanged. "
        "Each figure is a receipt; a move is reported only when the value, row "
        "count, slice hash, or query differs, never the timestamp alone.",
        "",
    ]
    if diff.changed:
        lines.append(f"| Metric | {prior_label} value | {current_label} value | why |")
        lines.append("|--------|------------|--------------|-----|")
        for delta in diff.changed:
            why = "; ".join(delta.reasons)
            lines.append(
                f"| {delta.metric_id} | {_delta_display(delta, 'prior')} | "
                f"{_delta_display(delta, 'current')} | {why} |"
            )
        lines.append("")
    if diff.added:
        lines.append("### Added")
        lines.append("")
        for receipt in diff.added:
            metric_id = receipt.get("metric_id", "")
            display = receipt.get("display", receipt.get("value", ""))
            lines.append(f"- {metric_id} = {display}")
        lines.append("")
    if diff.removed:
        lines.append("### Removed")
        lines.append("")
        for receipt in diff.removed:
            metric_id = receipt.get("metric_id", "")
            display = receipt.get("display", receipt.get("value", ""))
            lines.append(f"- {metric_id} = {display}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


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
    charts: Sequence[Chart] = (),
    chart_dir: str = "charts",
    provenance: Provenance | None = None,
) -> str:
    """Render the narrative, optional comparison and charts, provenance, receipts.

    When ``provenance`` is given, a standard provenance block is embedded before
    the receipts, stating that no number was written by a model and that the gate
    bound every number before export. The receipts section then lists each figure
    with its plain-language definition and the receipt that backs it.
    """

    lines = [f"# {title}", "", narrative.strip()]
    if comparison is not None:
        lines.extend(["", render_comparison_table(comparison)])
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
        if receipt.indicator:
            lines.append(f"  - indicator: {receipt.indicator}")
        if receipt.data_source:
            lines.append(f"  - data source: {receipt.data_source}")
        if receipt.collection_frequency:
            lines.append(f"  - collection frequency: {receipt.collection_frequency}")
        if receipt.caveat:
            lines.append(f"  - caveat: {receipt.caveat}")
        lines.append(f"  - query: `{receipt.value_sql}`")
        lines.append(f"  - rows in slice: {receipt.row_count}")
        lines.append(f"  - slice hash: `{receipt.slice_hash}`")
        lines.append(f"  - computed at: {receipt.computed_at}")
    return "\n".join(lines) + "\n"


def receipts_manifest(
    figures: Sequence[Figure],
    *,
    provenance: Provenance | None = None,
    artifacts: Mapping[str, str] | None = None,
) -> str:
    """Render the receipts as a JSON manifest for machine verification.

    When ``provenance`` is given, the manifest also carries the machine-readable
    provenance attestation, so a consumer can check the no-model and gate-passed
    claims without re-reading the prose.

    When ``artifacts`` is given (a mapping of bundle-relative path to its sha256
    hex digest), the manifest records those digests so ``verify --bundle`` can
    check that the sibling files were not swapped after export. The manifest never
    hashes itself; the hash relation is one-directional. See ADR 0006.

    The manifest is versioned: ``schema_version`` names the manifest schema and
    ``hash`` describes exactly how every ``slice_hash`` was produced (algorithm,
    digest size, canonicalization rule set), so a consumer can validate and
    re-derive without reading the engine. See ``docs/schema/receipts.schema.json``
    and ADR 0005.
    """

    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "hash": {
            "algorithm": HASH_ALGORITHM,
            "digest_size": HASH_DIGEST_SIZE,
            "canonicalization": HASH_CANONICALIZATION,
        },
        "receipts": [
            {
                "metric_id": f.receipt.metric_id,
                "value": f.receipt.value,
                "display": f.display,
                "unit": f.receipt.unit,
                "kind": f.receipt.kind,
                "definition": f.receipt.definition,
                "indicator": f.receipt.indicator,
                "data_source": f.receipt.data_source,
                "collection_frequency": f.receipt.collection_frequency,
                "caveat": f.receipt.caveat,
                "value_sql": f.receipt.value_sql,
                "row_count": f.receipt.row_count,
                "slice_hash": f.receipt.slice_hash,
                "column_names": list(f.receipt.column_names),
                "computed_at": f.receipt.computed_at,
            }
            for f in sorted(figures, key=lambda f: f.metric_id)
        ],
    }
    if provenance is not None:
        payload["provenance"] = provenance_record(provenance)
    if artifacts is not None:
        payload["artifacts"] = dict(sorted(artifacts.items()))
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
