"""Rendering for the report, the receipts manifest, and the eval.

The report is the drafted narrative with a receipts manifest appended, so a reader
or auditor can trace every figure to the query and data slice that produced it.
The eval renderer shows the gated grounding rate and whether it passed.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from outcome_receipts.charts import Chart
from outcome_receipts.comparison import ComparisonResult, ReconciliationResult
from outcome_receipts.copy import Locale, get_copy
from outcome_receipts.diff import FigureDelta, ManifestDiff
from outcome_receipts.evaluate import EvalReport
from outcome_receipts.models import (
    HASH_ALGORITHM,
    HASH_CANONICALIZATION,
    HASH_DIGEST_SIZE,
    REDACTED_DISPLAY,
    SCHEMA_VERSION,
    Figure,
)
from outcome_receipts.provenance import Provenance, provenance_markdown, provenance_record


def render_comparison_table(result: ComparisonResult, *, locale: Locale = "en") -> str:
    """Render a period-over-period comparison as a Markdown table.

    Every number in the table is a figure display: the two period values and the
    change. Direction is a word, derived from the sign of the change, so the table
    asserts no number that is not a receipt. The change for a rate metric is in
    percentage points, noted under the table.

    A row whose prior, current, or delta was suppressed also has its direction
    replaced by ``suppression.redact_comparison`` with the same redaction
    sentinel (e.g. ``"[SUPPRESSED]"``) those figures display; ``directions.get``
    falls back to printing that sentinel as-is (never translated -- it is a
    redaction marker, not narrative copy) instead of raising on an unrecognized
    key.
    """

    copy = get_copy(locale)
    directions = {
        "increase": copy.direction_increase,
        "decrease": copy.direction_decrease,
        "no change": copy.direction_no_change,
    }
    lines = [
        copy.comparison_heading,
        "",
        copy.comparing_sentence_template.format(
            current=result.current_label, prior=result.prior_label
        ),
        "",
        f"| {copy.header_outcome} | {result.prior_label} | {result.current_label} "
        f"| {copy.header_change} | {copy.header_direction} |",
        "|---------|------|------|--------|-----------|",
    ]
    for row in result.rows:
        name = row.description or row.base_metric_id
        lines.append(
            f"| {name} | {row.prior.display} | {row.current.display} | "
            f"{row.delta.display} | {directions.get(row.direction, row.direction)} |"
        )
    lines.append("")
    lines.append(copy.rate_metric_note)
    return "\n".join(lines)


def render_reconciliation_table(result: ReconciliationResult, *, locale: Locale = "en") -> str:
    """Render the board reconciliation as Markdown: outcomes beside financial lines.

    Each row is a small table pairing the receipted outcome figure with its
    financial line, and each shows the cross-period change as a magnitude plus a
    direction word, the same display convention as the comparison table. Every
    number is a figure display, so the section asserts nothing that is not a
    receipt, and the change is itself one query, not arithmetic over the page.

    As with the comparison table, a suppressed side's direction is replaced by
    ``suppression.redact_reconciliation`` with the redaction sentinel its
    figures display; ``directions.get`` prints that sentinel unchanged instead
    of raising.
    """

    copy = get_copy(locale)
    directions = {
        "increase": copy.direction_increase,
        "decrease": copy.direction_decrease,
        "no change": copy.direction_no_change,
    }
    lines = [
        copy.reconciliation_heading,
        "",
        copy.reconciliation_sentence_template.format(
            prior=result.prior_label, current=result.current_label
        ),
        "",
    ]
    for row in result.rows:
        outcome = row.outcome
        financial = row.financial
        lines.extend(
            [
                f"### {row.label}",
                "",
                f"| {copy.header_item} | {result.prior_label} | {result.current_label} | "
                f"{copy.header_change} | {copy.header_direction} |",
                "|------|------|------|--------|-----------|",
                f"| {outcome.description or outcome.base_metric_id} ({copy.outcome_suffix}) | "
                f"{outcome.prior.display} | {outcome.current.display} | "
                f"{outcome.delta.display} | "
                f"{directions.get(outcome.direction, outcome.direction)} |",
                f"| {financial.description or financial.base_metric_id} "
                f"({copy.financial_suffix}) | "
                f"{financial.prior.display} | {financial.current.display} | "
                f"{financial.delta.display} | "
                f"{directions.get(financial.direction, financial.direction)} |",
                "",
            ]
        )
    lines.append(copy.rate_metric_note)
    return "\n".join(lines)


def _receipt_display(receipt: Mapping[str, Any]) -> str:
    """A receipt's rendered display string, marker-safe for a foreign manifest.

    ``diff`` is exactly the command that reads a manifest this tool did not
    itself produce, so ``display`` cannot be assumed present. The old fallback
    -- ``receipt.get("display", receipt.get("value", ""))`` -- read a present
    but ``None`` ``value`` (a suppressed schema-2.0 figure) as the literal text
    "None", and a wholly missing ``value`` as a silently blank cell, which
    reads as "unchanged" rather than "could not be shown". Both cases route
    through :func:`_withheld` instead, the same marker the receipts section and
    the trace view already use for a withheld numeric field.
    """

    if "display" in receipt:
        return str(receipt["display"])
    return _withheld(receipt.get("value"))


def _delta_display(delta: FigureDelta, key: str) -> str:
    """The display string for one side of a changed figure, blank if absent."""

    side = delta.prior if key == "prior" else delta.current
    if side is None:
        return ""
    return _receipt_display(side)


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
            lines.append(f"- {metric_id} = {_receipt_display(receipt)}")
        lines.append("")
    if diff.removed:
        lines.append("### Removed")
        lines.append("")
        for receipt in diff.removed:
            metric_id = receipt.get("metric_id", "")
            lines.append(f"- {metric_id} = {_receipt_display(receipt)}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_charts_section(charts: Sequence[Chart], *, chart_dir: str, locale: Locale = "en") -> str:
    """Render the charts as image references with their accessible data tables.

    The SVG is referenced as an image; the data table beneath it is the text
    equivalent and carries the same grounded numbers, so the chart is readable
    without the image and the numbers it shows trace to receipts.
    """

    copy = get_copy(locale)
    lines = [copy.charts_heading, ""]
    for chart in charts:
        lines.append(f"### {chart.title}")
        lines.append("")
        alt = copy.chart_alt_template.format(title=chart.title)
        lines.append(f"![{alt}]({chart_dir}/{chart.chart_id}.svg)")
        lines.append("")
        lines.append(copy.chart_data_caption_template.format(title=chart.title))
        lines.append("")
        lines.append(chart.data_table)
        lines.append("")
    return "\n".join(lines).rstrip()


def _withheld(value: object) -> str:
    """Render a receipt field, or the redaction marker when it was withheld.

    A suppressed receipt carries ``None`` for every numeric field, so printing it
    directly would put ``None`` next to the ``[SUPPRESSED]`` label. Printing a
    ``0`` -- which is what the field used to hold -- told the reader the query
    matched no rows. Neither is what the report means, so both surfaces show the
    same marker the figure itself shows.
    """

    return REDACTED_DISPLAY if value is None else str(value)


def _receipt_lines(figure: Figure, *, locale: Locale = "en") -> list[str]:
    receipt = figure.receipt
    copy = get_copy(locale)
    lines = [
        f"- **{figure.metric_id}** = {figure.display}",
        f"  - {copy.receipt_kind_label}: {receipt.kind}",
    ]
    optional = (
        (copy.receipt_definition_label, receipt.definition),
        (copy.receipt_indicator_label, receipt.indicator),
        (copy.receipt_data_source_label, receipt.data_source),
        (copy.receipt_collection_frequency_label, receipt.collection_frequency),
        (copy.receipt_caveat_label, receipt.caveat),
    )
    lines.extend(f"  - {label}: {value}" for label, value in optional if value)
    lines.extend(
        [
            f"  - {copy.receipt_query_label}: `{receipt.value_sql}`",
            f"  - {copy.receipt_rows_label}: {_withheld(receipt.row_count)}",
            f"  - {copy.receipt_slice_hash_label}: `{_withheld(receipt.slice_hash)}`",
            f"  - {copy.receipt_computed_at_label}: {receipt.computed_at}",
        ]
    )
    return lines


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
    locale: Locale = "en",
) -> str:
    """Render the narrative, optional comparison, reconciliation, and charts, then
    provenance and receipts.

    When ``provenance`` is given, a standard provenance block is embedded before
    the receipts, stating that no figure was written by a model and that the gate
    bound every number in the report's claims before export. The receipts section
    then lists each figure with its plain-language definition and the receipt that
    backs it. That section, and the provenance block itself, print row counts,
    slice hashes, timestamps, and query text; those numerals are receipt metadata
    and were never in the gate's scope, so grounding a whole rendered report
    rather than its narrative region reports them as unbound.
    """

    copy = get_copy(locale)
    lines = [f"# {title}", "", narrative.strip()]
    if comparison is not None:
        lines.extend(["", render_comparison_table(comparison, locale=locale)])
    if reconciliation is not None:
        lines.extend(["", render_reconciliation_table(reconciliation, locale=locale)])
    if charts:
        lines.extend(["", render_charts_section(charts, chart_dir=chart_dir, locale=locale)])
    if provenance is not None:
        lines.extend(["", provenance_markdown(provenance, locale=locale)])
    lines.extend(["", copy.receipts_heading, ""])
    for figure in sorted(figures, key=lambda f: f.metric_id):
        lines.extend(_receipt_lines(figure, locale=locale))
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

    Every receipt carries ``suppressed``. When it is true the withheld numerics
    (``value``, ``row_count``, ``slice_hash``, ``column_names``) are ``null``,
    never zero, so a consumer cannot read a withheld cell as a count of nobody.
    A genuinely zero figure is ``suppressed: false`` with a real ``0``; a figure
    that does not exist has no entry in ``receipts`` at all. Three states, three
    distinguishable renderings.
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
                "suppressed": f.receipt.suppressed,
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
                "column_names": (
                    None if f.receipt.column_names is None else list(f.receipt.column_names)
                ),
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
    # A narrative with zero numeric spans scores grounding_rate 1.0 vacuously
    # (see evaluate.py): no number failed to bind, because there was no
    # number to bind. That is a legitimate reason for the gate to pass, but
    # rendering it as "100.0%" or "(observed 100.0%)" reads as a real
    # measurement over some numbers, when zero numbers were scored. Label the
    # no-data case honestly instead of letting a vacuous rate stand in for one.
    grounding_rate_display = (
        _pct(report.grounding_rate) if report.n_numbers else "N/A (no numeric spans)"
    )
    gate_observed = (
        f"(observed {grounding_rate_display})."
        if report.n_numbers
        else "(no numeric spans in the narrative to bind; the gate passes vacuously, not "
        "on a measured rate)."
    )
    # An eval that scored nothing is not evidence about the gate, whatever the
    # gate's own verdict was. The reader of a committed eval.md has only this
    # file, so the file has to say it; `receipts eval` exits non-zero on the same
    # condition.
    closing = (
        "".join(
            (
                "This committed run scores the drafted narrative, every number of which ",
                "comes from a receipt, so it passes. That the gate catches an injected ",
                "unverifiable number is shown by the merge-blocking test ",
                "`tests/test_grounding_gate.py`, not by failing this report.",
            )
        )
        if report.n_numbers
        else "".join(
            (
                "No numeric span was scored here, so this run is not a measurement of ",
                "the gate and `receipts eval` exits non-zero on it. Either the report ",
                "spec's templates render no figure, or suppression withheld all of ",
                "them. That the gate catches an injected unverifiable number is shown ",
                "by the merge-blocking test `tests/test_grounding_gate.py`.",
            )
        )
    )
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
        "".join(
            (
                "A number in a funder report that is wrong or invented is the expensive, ",
                "sometimes irreversible error. So the gated metric is the grounding rate: ",
                "the share of numbers in the narrative that bind to a receipt. It is ",
                "fail-closed at 100%; a single unbound number blocks export.",
            )
        ),
        "",
        "## What was scored",
        "",
        "".join(
            (
                "The **publishable** figure set, in **every narrative the run would ",
                "export**: each of the spec's report templates is drafted and grounded ",
                "after small-cell suppression, so this scores the artifacts ",
                "`receipts run` exports rather than a pre-suppression draft the ",
                "pipeline would never produce. A suppressed cell renders as ",
                "`[SUPPRESSED]` and carries no number, so it contributes no span to the ",
                "denominator. The denominator is therefore the count of numbers that ",
                "survive suppression, which is smaller than the spec's metric count ",
                "whenever a report has a small cell. A spec that names several funder ",
                "formats is scored across all of them, and a figure written into two of ",
                "them counts twice: each format is a separate exported document, so ",
                "each occurrence is its own chance for an ungrounded number to reach a ",
                "reader.",
            )
        ),
        "",
        "## Results",
        "",
        "| Metric | Value | 95% CI |",
        "|--------|-------|--------|",
        f"| Numbers in narrative | {report.n_numbers} | |",
        f"| Bound to a receipt | {report.n_bound} | |",
        f"| **Grounding rate (gated)** | **{grounding_rate_display}** "
        f"({report.n_bound}/{report.n_numbers}) | {_ci(report.grounding_ci)} |",
        f"| Unverifiable numbers | {report.n_unbound} | |",
        f"| Hallucinated-number rate | {_pct(report.hallucinated_rate)} "
        f"({report.n_unbound}/{report.n_numbers}) | {_ci(report.hallucinated_ci)} |",
        "",
        "## Gate",
        "",
        f"Grounding gate (100% required): **{gate_word}** {gate_observed}",
        "",
        closing,
    ]
    return "\n".join(lines) + "\n"
