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

Disclosure scope: the whole report, per unit. An earlier revision scoped the
complementary check to sibling groups (a comparison metric's period and delta
figures together, every headline metric in a separate report-level group), on
the theory that only figures presented together would be combined by a reader.
That partition severed real accounting identities: a whole-period headline is
the sum of its own period figures (``exits_permanent = __q1 + __q2``), so
``headline - q2`` printed a suppressed ``q1`` into the same report, undetected,
because the two figures sat in different groups. The report spec is a flat
metric list over one data table; per-period category sums, category totals, and
headline/period identities all cross any finer grouping the metric ids could
induce, so any partition can sever an identity a reader actually knows. The
rule now: every count figure in a report is checked against every other count
figure, and every percent figure against every other percent figure (counts and
percents are never additive with each other). The cost is that a coincidental
arithmetic match between unrelated figures can suppress more than strictly
necessary; over-suppression is the protective direction, and a leak is a
defect, so the trade is accepted.

Two relationships need rules of their own, because they are not plain +/- sums:

- A comparison delta is defined as current minus prior. When either period
  figure is suppressed, the delta is suppressed with it: a visible delta beside
  the other period reconstructs the hidden period directly, and a visible delta
  beside a visible whole-period headline pins the hidden period at
  ``(headline - delta) / 2`` -- a recovery with a coefficient the signed-sum
  search cannot represent, so it is closed by rule rather than by search.
- A percent is a ratio of counts, and a percent with a visible denominator
  uniquely determines a suppressed numerator via rounding (71% of 14 exits can
  only be 10). ``MetricSpec`` cannot express which count metrics feed a percent
  (``value_sql`` is opaque SQL), so the conservative rule applies: when any
  count figure in the report is suppressed, every percent figure is suppressed
  with it. This is deliberately blunt -- a percent whose numerator and
  denominator are both visible is suppressed too -- because the dependency
  cannot be traced from the data model, and guessing it from SQL text is the
  name-matching heuristic this module already rejected once.

The guarantee, stated precisely: after suppression reaches its fixed point, no
suppressed figure's exact value is certified to a reader by the figures still
visible -- not by any single +/- combination of same-unit visible figures, not
by a delta definition, and not by a percent with a visible input. Two things
are deliberately outside that guarantee. A suppressed value may still be
*consistent* with the visible figures (a headline of 13 with both period
figures hidden tells the reader the two hidden values sum to 13; an interval
is not a disclosure under the cell-suppression model). And a hidden value may
coincidentally equal some arithmetic on visible figures from unrelated metrics
(nothing certifies the coincidence to the reader, who cannot distinguish it
from the other combinations that do not match). What must never happen is the
demonstrated failures: an accounting identity the reader actually holds --
total minus categories, headline minus a period, one period plus a visible
delta, a percent times its visible denominator -- landing exactly on a
suppressed cell.

Policy basis:
  CMS primary data documentation states that values 1--10, derivable cells, and
  revealing percentages/formulas may not be displayed:
  https://data.cms.gov/sites/default/files/2023-11/51397ef0-8f37-40f6-985f-4a46c61882cb/Data_Dictionary-MSSP-Performance_Year_Financial_and_Quality_Results__2013-2020.pdf
  HUD's HMIS publication guidance requires anonymous aggregate public data and
  avoidance of small-sample inference, but does not prescribe a numeric floor:
  https://files.hudexchange.info/resources/documents/HMISImplementationGuide.pdf
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING

from outcome_receipts.models import EMPTY_SLICE_HASH, Figure

if TYPE_CHECKING:
    from collections.abc import Sequence

    from outcome_receipts.comparison import ComparisonResult, ComparisonRow, ReconciliationResult

# The CMS Cell Size Suppression Policy threshold: counts below this value
# (i.e., 1-10) are suppressed.
SUPPRESSION_THRESHOLD = 11

# The redacted placeholder shown in place of a suppressed figure's value.
_REDACTED_DISPLAY = "[SUPPRESSED]"

# Tolerance for treating a candidate combination's sum as equal to the target.
# Figures are counts (or percents computed to fixed decimals), so exact-match
# with a float epsilon is the right test; nothing here is approximate.
_EPSILON = 1e-9


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

    redacted_receipt = replace(
        figure.receipt,
        row_count=0,
        slice_hash=EMPTY_SLICE_HASH,
        value=0.0,
        column_names=(),
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

    Checks combinations of every size up to the full candidate set, with every
    assignment of + or - to each term, e.g. "total - other_category". The search
    used to stop at four terms, which let a five-category breakdown evade it:
    the only combination recovering the suppressed fifth category
    (``total - a - b - c - d``) has five terms, and breakdowns of five or more
    categories are ordinary in HMIS-style reporting. No within-group identity
    may escape on size, so the search is exhaustive over the group.

    Implemented as a depth-first search over the candidates sorted by descending
    magnitude, with branch-and-bound pruning: a branch is abandoned as soon as
    the remaining candidates' combined magnitude cannot close the gap between
    the partial sum and the target. Report figure sets are small (tens of
    figures at most), so the pruned search is cheap in practice.

    Returns the metric_ids of a combination that reconstructs ``target``, or
    ``None`` if no such combination exists among ``candidates``.
    """

    # Largest magnitudes first, so pruning bites as early as possible. The
    # secondary sort on metric_id keeps the search order, and therefore the
    # returned combination, deterministic.
    ordered = sorted(candidates, key=lambda item: (-abs(item[1]), item[0]))
    values = [value for _, value in ordered]
    # remaining[i]: the combined magnitude of candidates i..end, the most any
    # completion of a partial combination can still move the sum.
    remaining = [0.0] * (len(ordered) + 1)
    for index in range(len(ordered) - 1, -1, -1):
        remaining[index] = remaining[index + 1] + abs(values[index])

    chosen: list[int] = []

    def search(index: int, partial: float) -> bool:
        if chosen and abs(partial - target) < _EPSILON:
            return True
        if index == len(ordered) or abs(partial - target) > remaining[index] + _EPSILON:
            return False
        for sign in (1.0, -1.0):
            chosen.append(index)
            if search(index + 1, partial + sign * values[index]):
                return True
            chosen.pop()
        return search(index + 1, partial)

    if search(0, 0.0):
        return tuple(ordered[index][0] for index in chosen)
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
# other figures down with it. The reverse dependency is real, though: once
# either of a delta's period figures is suppressed, the delta must go with it
# (see `_complementary_suppress`), because a visible delta reconstructs the
# hidden period from the other period, or -- combined with a visible
# whole-period headline -- pins it at (headline - delta) / 2.
_DELTA_SUFFIX = "__delta"


def _sibling_delta_id(metric_id: str) -> str | None:
    """The delta metric_id belonging to a comparison period figure, or None.

    ``exits__q1`` -> ``exits__delta``. A figure that is not suffixed, or is
    itself a delta, has no sibling delta.
    """

    if "__" not in metric_id or metric_id.endswith(_DELTA_SUFFIX):
        return None
    return metric_id.rsplit("__", 1)[0] + _DELTA_SUFFIX


def _suppress_sibling_deltas(
    values_by_id: dict[str, float],
    hidden: Callable[[str], bool],
    complementary: set[str],
) -> bool:
    changed = False
    for metric_id in sorted(values_by_id):
        delta_id = _sibling_delta_id(metric_id)
        if delta_id is None or not hidden(metric_id):
            continue
        if delta_id in values_by_id and not hidden(delta_id):
            complementary.add(delta_id)
            changed = True
    return changed


def _suppress_dependent_rates(
    values_by_id: dict[str, float],
    units_by_id: dict[str, str],
    hidden: Callable[[str], bool],
    hidden_ids: set[str],
    complementary: set[str],
) -> bool:
    if not any(units_by_id[mid] == "count" for mid in hidden_ids):
        return False
    victims = {
        metric_id
        for metric_id in values_by_id
        if units_by_id[metric_id] in {"percent", "rate"} and not hidden(metric_id)
    }
    complementary.update(victims)
    return bool(victims)


def _recovery_victim(
    metric_id: str,
    values_by_id: dict[str, float],
    units_by_id: dict[str, str],
    hidden: Callable[[str], bool],
) -> str | None:
    if metric_id.endswith(_DELTA_SUFFIX) or metric_id not in values_by_id:
        return None
    candidates = [
        (other_id, value)
        for other_id, value in values_by_id.items()
        if other_id != metric_id
        and not hidden(other_id)
        and units_by_id[other_id] == units_by_id[metric_id]
    ]
    combo = _disclosing_combination(values_by_id[metric_id], candidates)
    if combo is None:
        return None
    return min(combo, key=lambda mid: (abs(values_by_id[mid]), mid))


def _complementary_suppress(figures: list[Figure], suppressed_ids: set[str]) -> set[str]:
    """Disclosure-based complementary suppression: real arithmetic, not names.

    Runs three rules to a shared fixed point, since applying any one of them can
    expose work for another:

    1. A suppressed period figure pulls its own delta figure down with it. The
       delta is current minus prior by definition; visible, it reconstructs the
       hidden period from the other period figure or from a whole-period
       headline, and the headline route has a coefficient (a half) the signed
       sum search below cannot represent. See the ``_DELTA_SUFFIX`` note.
    2. Once any count figure is suppressed (primary or complementary), every
       percent figure is suppressed too. A percent with a visible denominator
       uniquely determines a suppressed numerator via rounding, and the data
       model cannot say which counts feed which percent, so the conservative
       rule from the module docstring applies.
    3. For every primary-suppressed figure, the exact-recovery search: can the
       suppressed value be rebuilt by adding or subtracting still-visible
       figures of the same unit anywhere in the report (a total minus its other
       named parts, a headline minus the other period, a sibling category minus
       another)? If a disclosing combination exists, the smallest-valued figure
       in it is suppressed -- the standard "next-smallest cell" rule, the least
       additional information that breaks that recovery -- and the loop repeats,
       since one redaction can leave another combination that discloses the same
       or a different suppressed cell.

    The disclosure scope is the whole report, split only by unit (counts check
    against counts, percents against percents); see the module docstring for why
    any finer grouping severed real accounting identities. A comparison delta
    figure is never a *target* of rule 3 (its recoverability from its own
    periods is definitional, not a discovered disclosure), but it is a candidate
    while visible.
    """

    complementary: set[str] = set()
    values_by_id = {figure.metric_id: figure.value for figure in figures}
    units_by_id = {figure.metric_id: figure.receipt.unit for figure in figures}

    def hidden(metric_id: str) -> bool:
        return metric_id in suppressed_ids or metric_id in complementary

    changed = True
    while changed:
        changed = False

        changed |= _suppress_sibling_deltas(values_by_id, hidden, complementary)
        changed |= _suppress_dependent_rates(
            values_by_id,
            units_by_id,
            hidden,
            suppressed_ids | complementary,
            complementary,
        )

        # Rule 3: the exact-recovery search over same-unit visible figures.
        for metric_id in sorted(suppressed_ids):
            victim = _recovery_victim(metric_id, values_by_id, units_by_id, hidden)
            if victim is None:
                continue
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
    further figures are suppressed until no suppressed value is recoverable from
    the ones still visible: any figure in a disclosing signed combination, the
    delta of any suppressed period figure, and every percent once any count is
    suppressed (see ``_complementary_suppress`` for the three rules and the
    module docstring for the disclosure scope).

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
        if figure.receipt.unit == "count" and _is_below_threshold(figure.value, threshold):
            suppressed_ids.add(figure.metric_id)
        else:
            unsuppressed_ids.add(figure.metric_id)

    # Second pass: real complementary suppression, driven by arithmetic
    # recoverability rather than metric-name substrings.
    complementary_ids: set[str] = set()
    if complementary_rule and suppressed_ids:
        complementary_ids = _complementary_suppress(figures, suppressed_ids)
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
    redacted_figures = tuple(by_id.get(figure.metric_id, figure) for figure in comparison.figures)
    return replace(comparison, rows=rows, figures=redacted_figures)


def redact_reconciliation(
    reconciliation: ReconciliationResult, suppressed_figures: Sequence[Figure]
) -> ReconciliationResult:
    """Rebuild reconciliation rows from the publishable figure set."""

    by_id = {figure.metric_id: figure for figure in suppressed_figures}

    def redact_row(row: ComparisonRow) -> ComparisonRow:
        return replace(
            row,
            prior=by_id.get(row.prior.metric_id, row.prior),
            current=by_id.get(row.current.metric_id, row.current),
            delta=by_id.get(row.delta.metric_id, row.delta),
        )

    rows = tuple(
        replace(
            row,
            outcome=redact_row(row.outcome),
            financial=redact_row(row.financial),
        )
        for row in reconciliation.rows
    )
    figures = tuple(by_id.get(figure.metric_id, figure) for figure in reconciliation.figures)
    return replace(reconciliation, rows=rows, figures=figures)


def filter_for_aggregate_only(figures: list[Figure]) -> list[Figure]:
    """Filter a figure set to aggregate-only (never emit row-level data).

    The export boundary accepts only ``Figure`` values: scalar aggregates plus
    their receipts. Raw input rows are held inside the compute path and are not
    representable in report, manifest, trace, chart, or bundle renderers. Metric
    names are deliberately not inspected; a scalar called ``client_id_count`` is
    still aggregate data, while name heuristics cannot prove privacy.
    """
    return figures
