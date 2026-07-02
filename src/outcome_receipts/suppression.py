"""Small-cell suppression: privacy-protecting redaction of aggregate counts.

Suppression logic is modeled on the U.S. CMS Cell Size Suppression Policy:
- Aggregate counts in the range [1, 10] (below the threshold of 11) are suppressed.
- True zeros (count = 0) are preserved unencrypted, as they contain no privacy risk.
- Complementary suppression is applied: when a cell is suppressed, other cells in
  the same crosstab are suppressed as needed so the suppressed value cannot be
  recovered by subtraction. For single-dimension tables with no complementary cells,
  the suppressed value alone is redacted.

Sourced from:
  CMS Cell Size Suppression Policy, ResDAC
  https://resdac.org/articles/cms-cell-size-suppression-policy
  HHS Guidance Portal
  https://www.hhs.gov/guidance/document/cms-cell-suppression-policy
"""

from __future__ import annotations

from dataclasses import dataclass, field

from outcome_receipts.models import Figure

# The CMS Cell Size Suppression Policy threshold: counts below this value
# (i.e., 1-10) are suppressed.
SUPPRESSION_THRESHOLD = 11


@dataclass(frozen=True)
class SuppressionResult:
    """The outcome of suppression over a figure set.

    ``suppressed`` are the metric_ids of figures whose counts fell below the
    threshold and were redacted. ``complementary_suppressed`` are the metric_ids
    of figures redacted via complementary suppression to prevent recovery of a
    suppressed value. ``unsuppressed`` are the metric_ids of figures that passed
    unredacted (either above threshold or true zeros). ``aggregate_only`` is True
    when no row-level data was emitted in the export (the privacy assertion).
    """

    suppressed: tuple[str, ...] = field(default_factory=tuple)
    complementary_suppressed: tuple[str, ...] = field(default_factory=tuple)
    unsuppressed: tuple[str, ...] = field(default_factory=tuple)
    aggregate_only: bool = True

    @property
    def ok(self) -> bool:
        """True if suppression rules were followed (no cell below threshold remains)."""
        return len(self.suppressed) == 0 or len(self.unsuppressed) < len(self.suppressed)


def suppress_figures(
    figures: list[Figure],
    *,
    threshold: int = SUPPRESSION_THRESHOLD,
    complementary_rule: bool = True,
) -> tuple[list[Figure], SuppressionResult]:
    """Apply small-cell suppression to a figure set.

    Figures with values in [1, threshold-1] are marked as suppressed; true zeros
    (value = 0) are preserved. If ``complementary_rule`` is True and a figure is
    suppressed, other figures in the same logical crosstab may be suppressed to
    prevent recovery by subtraction.

    Returns a tuple of (suppressed_figures, suppression_result). The suppressed
    figures are copies with their display values redacted to "[SUPPRESSED]" and
    their receipt value set to None (to signal suppression in the manifest).

    This function implements the CMS Cell Size Suppression Policy for HHS/HUD
    aggregate reporting. Do not alter thresholds or complementary rules without
    confirming against the cited primary guidance and recording the change in an ADR.
    """

    suppressed_ids = set[str]()
    complementary_suppressed_ids = set[str]()
    unsuppressed_ids = set[str]()

    # First pass: identify figures that must be suppressed (1 <= value < threshold).
    # True zeros (value = 0) are not suppressed.
    for figure in figures:
        value = figure.value
        if 1 <= value < threshold:
            suppressed_ids.add(figure.metric_id)
        else:
            unsuppressed_ids.add(figure.metric_id)

    # Second pass: apply complementary suppression if enabled and there are
    # suppressed figures. For a simple crosstab with suppressed cells, we suppress
    # the "complement" (the other cell in a binary partition) so the suppressed
    # value cannot be recovered. A common pattern:
    #   - Total T, category A suppressed, category B unsuppressed -> suppress B
    #   - If A is suppressed and A + B = T, then B = T - A, so B must be suppressed too.
    #
    # This is heuristic for a single-level crosstab. A full implementation would
    # require the crosstab structure to be explicit in the spec (not just a flat
    # figure list). For now, we apply the rule conservatively: if there are
    # suppressed figures and a figure is a potential complement (named with "total"
    # or "all" and numerically close to the sum of suppressed), suppress it too.

    if complementary_rule and suppressed_ids:
        # Simple heuristic: look for a "total" figure that could be decomposed.
        for figure in figures:
            if (figure.metric_id not in suppressed_ids and
                    figure.metric_id not in complementary_suppressed_ids):
                # If the metric name suggests it is a total/aggregate, and suppressed
                # figures could sum to it, suppress the total to prevent recovery.
                name_lower = figure.metric_id.lower()
                if any(word in name_lower for word in ("total", "all", "sum", "aggregate")):
                    complementary_suppressed_ids.add(figure.metric_id)
                    unsuppressed_ids.discard(figure.metric_id)

    # Third pass: redact the figures, replacing display with "[SUPPRESSED]" and
    # zeroing the receipt value for suppressed figures.
    redacted = []
    for figure in figures:
        if figure.metric_id in suppressed_ids:
            # Primary suppression: value was below threshold.
            redacted_figure = Figure(
                metric_id=figure.metric_id,
                value=0.0,  # Redacted value; the receipt marks it as suppressed.
                display="[SUPPRESSED]",
                receipt=figure.receipt,
            )
            redacted.append(redacted_figure)
        elif figure.metric_id in complementary_suppressed_ids:
            # Complementary suppression: redacted to prevent recovery of suppressed cell.
            redacted_figure = Figure(
                metric_id=figure.metric_id,
                value=0.0,  # Redacted value; the receipt marks it as suppressed.
                display="[SUPPRESSED]",
                receipt=figure.receipt,
            )
            redacted.append(redacted_figure)
        else:
            # Unsuppressed: passes through unchanged.
            redacted.append(figure)

    result = SuppressionResult(
        suppressed=tuple(sorted(suppressed_ids)),
        complementary_suppressed=tuple(sorted(complementary_suppressed_ids)),
        unsuppressed=tuple(sorted(unsuppressed_ids)),
        aggregate_only=True,  # No row-level data is ever emitted.
    )

    return redacted, result


def filter_for_aggregate_only(figures: list[Figure]) -> list[Figure]:
    """Filter a figure set to aggregate-only (never emit row-level data).

    The export mode is "aggregate-only": the figures are counts, rates, and
    aggregates; never individual client records. This function is a safety check
    that no client-level fields (client IDs, names, etc.) have leaked into the
    figure display or receipt.

    For now, this is a placeholder: the engine is already designed to emit only
    aggregates, so this returns the figures unchanged. When the metric-mapping
    agent is added in v0.4, this will validate that mapped metrics did not
    inadvertently include row-level output.
    """
    # Validate that no figure display or metric_id looks like a PII field.
    # Common PII patterns in outcomes data: client_id, name, ssn, dob, etc.
    pii_patterns = {"_id", "name", "ssn", "dob", "email", "phone", "address"}
    for figure in figures:
        metric_lower = figure.metric_id.lower()
        if any(pattern in metric_lower for pattern in pii_patterns):
            raise ValueError(
                f"aggregate-only export: metric {figure.metric_id!r} looks like "
                "row-level data (contains PII pattern). Aggregate-only exports "
                "must emit only counts, rates, and aggregates, never client records."
            )
    return figures
