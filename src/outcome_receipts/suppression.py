"""Small-cell suppression: privacy-protecting redaction of aggregate counts.

Suppression logic is modeled on the U.S. CMS Cell Size Suppression Policy:
- Aggregate counts in the range [1, 10] (below the threshold of 11) are suppressed.
- True zeros (count = 0) are preserved unencrypted, as they contain no privacy risk.
- Complementary suppression is applied: when a cell is suppressed, other cells in
  the same crosstab are suppressed as needed so the suppressed value cannot be
  recovered by subtraction. For single-dimension tables with no complementary cells,
  the suppressed value alone is redacted.

A suppressed ``Figure`` is redacted at every layer that could leak the raw count:
its own ``value``/``display``, and its ``Receipt``'s ``value``, ``row_count``, and
``slice_hash``. A caller that reads ``figure.receipt.row_count`` (as the report,
manifest, and trace renderers do) must see the same redaction a caller reading
``figure.value`` sees; a suppressed ``Figure`` sharing an unredacted ``Receipt`` is
not suppression, it is a suppressed label glued to an unsuppressed number.

Sourced from:
  CMS Cell Size Suppression Policy, ResDAC
  https://resdac.org/articles/cms-cell-size-suppression-policy
  HHS Guidance Portal
  https://www.hhs.gov/guidance/document/cms-cell-suppression-policy
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from itertools import combinations, product
from typing import TYPE_CHECKING

from outcome_receipts.models import EMPTY_SLICE_HASH, Figure, Receipt

if TYPE_CHECKING:
    from collections.abc import Sequence

    from outcome_receipts.comparison import ComparisonResult

# The CMS Cell Size Suppression Policy threshold: counts below this value
# (i.e., 1-10) are suppressed.
SUPPRESSION_THRESHOLD = 11

# The redacted placeholder shown in place of a suppressed figure's value.
_REDACTED_DISPLAY = "[SUPPRESSED]"

# The largest combination of candidate figures checked for arithmetic disclosure
# recovery (see `_disclosing_combination`). Report figure sets are small (a
# handful to a few dozen metrics per report), so exhaustively checking every
# combination up to this size is cheap, and it covers the disclosure patterns
# that actually show up in outcome reports: a two-way part/part or total/part
# relationship (2 terms) up through a total decomposed into several named
# categories (up to 4 terms). This is not a general n-way disclosure solver.
_MAX_DISCLOSURE_TERMS = 4


@dataclass(frozen=True)
class SuppressionResult:
    """The outcome of suppression over a figure set.

    ``suppressed`` are the metric_ids of figures whose counts fell below the
    threshold and were redacted. ``complementary_suppressed`` are the metric_ids
    of figures redacted via complementary suppression to prevent recovery of a
    suppressed value. ``unsuppressed`` are the metric_ids of figures that passed
    unredacted (either above threshold or true zeros). ``aggregate_only`` is True
    when no row-level data was emitted in the export (the privacy assertion).

    ``threshold`` and ``values`` are kept so ``ok`` can check the actual privacy
    invariant against the figures suppression saw, rather than against a count of
    ids that says nothing about whether any of them were below threshold.
    """

    suppressed: tuple[str, ...] = field(default_factory=tuple)
    complementary_suppressed: tuple[str, ...] = field(default_factory=tuple)
    unsuppressed: tuple[str, ...] = field(default_factory=tuple)
    aggregate_only: bool = True
    threshold: int = SUPPRESSION_THRESHOLD
    # metric_id -> the figure's original (pre-redaction) value, for every figure
    # suppress_figures was given. Not a public reporting field; it exists so `ok`
    # can verify the invariant it claims to check.
    values: tuple[tuple[str, float], ...] = field(default_factory=tuple)

    @property
    def ok(self) -> bool:
        """True only if no cell below threshold remains unsuppressed.

        This checks the actual privacy invariant: every metric_id in
        ``unsuppressed`` must have an original value that is either a true zero
        or at or above ``threshold``. A metric_id with no recorded value (e.g. a
        ``SuppressionResult`` built by hand, as some tests do) is assumed fine,
        since there is nothing to check it against.
        """

        by_id = dict(self.values)
        for metric_id in self.unsuppressed:
            value = by_id.get(metric_id)
            if value is not None and 1 <= abs(value) < self.threshold:
                return False
        return True


def _is_below_threshold(value: float, threshold: int) -> bool:
    """True if ``value``'s magnitude is a small cell: in [1, threshold).

    Magnitude, not the raw signed value, is what determines suppression. Every
    ordinary count is non-negative, so this is a no-op for them. It matters for a
    comparison's delta figure, whose value is a signed difference: a swing of
    "-1" is exactly as disclosive as a swing of "1" (it still names a change of
    one person), so a negative small delta must be suppressed too, not waved
    through because ``value < 1`` reads False for a negative number.
    """

    return 1 <= abs(value) < threshold


def _redact(figure: Figure) -> Figure:
    """A copy of ``figure`` with every raw-count-bearing field scrubbed.

    Redacting only ``Figure.value``/``display`` and leaving ``figure.receipt``
    attached unchanged is not suppression: ``report.py`` and ``trace.py`` read
    ``receipt.row_count`` directly, and both render it right next to the
    "[SUPPRESSED]" label if the receipt is not also redacted. So every field on
    the receipt that carries the raw count is replaced here: ``value`` and
    ``row_count`` are zeroed, and ``slice_hash`` -- a content hash of the exact
    suppressed rows -- is replaced with the canonical empty-slice hash, since a
    hash of a guessed row set could otherwise be compared against a real one to
    confirm a guess. ``value_sql``, ``unit``, ``computed_at``, and ``definition``
    are not data; they describe the query and are kept for audit purposes.
    """

    receipt = figure.receipt
    redacted_receipt = Receipt(
        metric_id=receipt.metric_id,
        value_sql=receipt.value_sql,
        row_count=0,
        slice_hash=EMPTY_SLICE_HASH,
        value=0.0,
        unit=receipt.unit,
        computed_at=receipt.computed_at,
        definition=receipt.definition,
    )
    return Figure(
        metric_id=figure.metric_id,
        value=0.0,
        display=_REDACTED_DISPLAY,
        receipt=redacted_receipt,
    )


def _disclosing_combination(
    target: float, candidates: list[tuple[str, float]]
) -> tuple[str, ...] | None:
    """Find a signed combination of ``candidates`` that reconstructs ``target``.

    Checks every combination of up to ``_MAX_DISCLOSURE_TERMS`` candidates, with
    every assignment of + or - to each term, e.g. "total - other_category". A
    name match (does a metric_id contain "total"?) is not a disclosure check: it
    catches nothing that isn't named "total" and it flags plenty of figures that
    are not actually recoverable. This is the real check: does some arithmetic
    combination of other still-visible figures equal the suppressed value exactly?

    Returns the metric_ids of a combination that reconstructs ``target``, or
    ``None`` if no such combination exists among ``candidates``.
    """

    limit = min(len(candidates), _MAX_DISCLOSURE_TERMS)
    for r in range(1, limit + 1):
        for combo in combinations(candidates, r):
            ids = tuple(metric_id for metric_id, _ in combo)
            values = [value for _, value in combo]
            for signs in product((1, -1), repeat=r):
                total = sum(
                    sign * value for sign, value in zip(signs, values, strict=True)
                )
                if abs(total - target) < 1e-9:
                    return ids
    return None


# The suffix `comparison.py` gives a period-over-period delta figure's metric_id
# (see `_delta_spec`). A delta is *defined* as current minus prior, so it is
# always "recoverable" from its own two period figures -- that is not a
# disclosure the arithmetic check discovered, it is the delta's definition. If
# it were treated as an ordinary target, any suppressed delta whose own periods
# happen to still be visible (typically because both periods are safely at or
# above the threshold on their own) would cascade into suppressing one of those
# safe period figures for no privacy benefit, since the reader could already
# compute the "protected" delta from the two period values regardless of what
# the delta figure itself displays. So a delta's own suppression stands on its
# own (it still gets redacted if its magnitude is small); it just does not pull
# other figures down with it. It can still act as a *candidate* for its own
# period figures (see `_group_key`): if a delta is ever left visible next to one
# suppressed period, the other period genuinely is recoverable from them, and
# that risk is real, not definitional.
_DELTA_SUFFIX = "__delta"


def _group_key(metric_id: str) -> str:
    """The disclosure-check group a figure belongs to.

    The report spec has no explicit crosstab structure -- metrics are a flat
    list -- so checking every suppressed figure against every other figure in
    the whole export, headline metrics and comparison metrics alike, produces
    false positives: two unrelated aggregates (say, total distinct clients and
    a different quarter's exit count) can coincidentally subtract to the same
    integer as some suppressed cell, with no real relationship and no reason an
    analyst would try that combination. Complementary suppression should only
    fire within an actual sibling group: figures a reader would plausibly
    combine because the spec presents them together.

    A comparison metric's period and delta figures (``exits__q1``,
    ``exits__q2``, ``exits__delta``) share a base metric_id and *do* have a real
    arithmetic relationship (the delta is defined from the two periods), so
    they group together, keyed by that base id. Every other figure -- the
    report's own headline metrics -- has no declared grouping beyond "the
    report", so they all share one group; that is the only crosstab the spec
    actually expresses (see the module docstring's fallback for when a fuller
    grouping model isn't available).
    """

    if "__" in metric_id:
        return metric_id.rsplit("__", 1)[0]
    return "__report__"


def _complementary_suppress(
    figures: list[Figure], suppressed_ids: set[str], threshold: int
) -> set[str]:
    """Disclosure-based complementary suppression: real arithmetic, not names.

    For every already-suppressed figure, checks whether its exact value can be
    reconstructed by adding or subtracting other still-visible figures in the
    same group (see ``_group_key``): a total minus its other named parts, a
    sibling category minus another, a comparison's other period plus its delta,
    and so on. If a disclosing combination exists, the smallest-valued figure in
    it is suppressed too -- the standard "next-smallest cell" complementary
    suppression rule, which suppresses the least additional information needed
    to break that particular recovery -- and the check repeats, since suppressing
    one figure can still leave another combination that discloses the same or a
    different suppressed cell.

    Only "count"-unit figures participate: a percentage is not additive with a
    count, so mixing them would produce meaningless coincidental matches. A
    comparison delta figure (metric_id ending in `_DELTA_SUFFIX`) is never
    treated as a target; see the module note above.
    """

    complementary: set[str] = set()
    counts_by_id = {
        figure.metric_id: figure.value
        for figure in figures
        if figure.receipt.unit == "count"
    }

    changed = True
    while changed:
        changed = False
        for metric_id in sorted(suppressed_ids):
            if metric_id not in counts_by_id or metric_id.endswith(_DELTA_SUFFIX):
                continue
            target = counts_by_id[metric_id]
            group = _group_key(metric_id)
            candidates = [
                (other_id, value)
                for other_id, value in counts_by_id.items()
                if other_id != metric_id
                and other_id not in suppressed_ids
                and other_id not in complementary
                and _group_key(other_id) == group
            ]
            combo = _disclosing_combination(target, candidates)
            if combo is None:
                continue
            # The minimum additional redaction that breaks this recovery: the
            # smallest-valued figure in the disclosing combination. Ties broken
            # by metric_id so the choice is deterministic.
            victim = min(combo, key=lambda mid: (abs(counts_by_id[mid]), mid))
            complementary.add(victim)
            changed = True

    return complementary


def suppress_figures(
    figures: list[Figure],
    *,
    threshold: int = SUPPRESSION_THRESHOLD,
    complementary_rule: bool = True,
) -> tuple[list[Figure], SuppressionResult]:
    """Apply small-cell suppression to a figure set.

    Figures with values in [1, threshold-1] (by magnitude; see
    ``_is_below_threshold``) are marked as suppressed; true zeros (value = 0) are
    preserved. If ``complementary_rule`` is True and a figure is suppressed,
    other figures are checked for actual arithmetic recoverability of the
    suppressed value (see ``_complementary_suppress``) and suppressed too if a
    disclosing combination is found.

    Returns a tuple of (suppressed_figures, suppression_result). Every field of a
    suppressed figure that carries a raw count -- the figure's own value and
    display, and its receipt's value, row_count, and slice_hash -- is replaced;
    see ``_redact``. This is what makes suppression hold for every artifact that
    is later rendered from these figures (the narrative, the charts, the
    receipts manifest, and the trace view), not only for a figure's own display.

    This function implements the CMS Cell Size Suppression Policy for HHS/HUD
    aggregate reporting. Do not alter thresholds or complementary rules without
    confirming against the cited primary guidance and recording the change in an
    ADR.
    """

    suppressed_ids: set[str] = set()
    unsuppressed_ids: set[str] = set()

    # First pass: identify figures that must be suppressed (magnitude in
    # [1, threshold)). True zeros (value = 0) are not suppressed.
    for figure in figures:
        if _is_below_threshold(figure.value, threshold):
            suppressed_ids.add(figure.metric_id)
        else:
            unsuppressed_ids.add(figure.metric_id)

    # Second pass: real complementary suppression, driven by arithmetic
    # recoverability rather than metric-name substrings.
    complementary_ids: set[str] = set()
    if complementary_rule and suppressed_ids:
        complementary_ids = _complementary_suppress(figures, suppressed_ids, threshold)
        unsuppressed_ids -= complementary_ids

    # Third pass: redact every figure that ended up suppressed, primary or
    # complementary, at every field that carries its raw count.
    redacted: list[Figure] = []
    for figure in figures:
        if figure.metric_id in suppressed_ids or figure.metric_id in complementary_ids:
            redacted.append(_redact(figure))
        else:
            redacted.append(figure)

    result = SuppressionResult(
        suppressed=tuple(sorted(suppressed_ids)),
        complementary_suppressed=tuple(sorted(complementary_ids)),
        unsuppressed=tuple(sorted(unsuppressed_ids)),
        aggregate_only=True,
        threshold=threshold,
        values=tuple((figure.metric_id, figure.value) for figure in figures),
    )

    return redacted, result


def redact_comparison(
    comparison: ComparisonResult, suppressed_figures: Sequence[Figure]
) -> ComparisonResult:
    """Rebuild a ``ComparisonResult`` from an already-suppressed figure set.

    ``compute_comparison`` returns its own copies of the period and delta
    figures, embedded in ``ComparisonResult.rows`` and ``ComparisonResult.figures``,
    independent of whatever flat figure list a caller later runs through
    ``suppress_figures``. Left alone, ``render_comparison_table`` would render
    those original, unredacted figures -- so a quarter's count or a delta could
    leak through the comparison table even though the identical metric_id was
    correctly redacted everywhere else. This looks up each row's prior, current,
    and delta figure (and every figure in the flat list) by metric_id in
    ``suppressed_figures``, so the comparison table renders the same redaction
    the report, manifest, and trace view do; a caller applies this once, right
    after ``suppress_figures``, before any rendering happens.
    """

    by_id = {figure.metric_id: figure for figure in suppressed_figures}
    rows = tuple(
        replace(
            row,
            prior=by_id.get(row.prior.metric_id, row.prior),
            current=by_id.get(row.current.metric_id, row.current),
            delta=by_id.get(row.delta.metric_id, row.delta),
        )
        for row in comparison.rows
    )
    redacted_figures = tuple(
        by_id.get(figure.metric_id, figure) for figure in comparison.figures
    )
    return replace(comparison, rows=rows, figures=redacted_figures)


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
