# 0005 — Disclosure scope is the whole report; the recovery check is exhaustive

Status: accepted (supersedes the complementary-scope refinement in 0004)

## Context

Adversarial re-verification of the v0.2 suppression work demonstrated two
remaining recoveries end to end, plus one design gap, after the fixes recorded
in ADR 0004:

1. **Term-cap evasion.** `_disclosing_combination` stopped its search at
   combinations of 4 terms (`_MAX_DISCLOSURE_TERMS`). A total decomposed into
   five named categories (162 = 52 + 30 + 61 + 17 + 2, the fifth suppressed)
   left the suppressed cell exactly recoverable as `total - a - b - c - d`,
   a five-term combination the search never tried. Breakdowns of five or more
   categories are ordinary in HMIS-style reporting, so the cap was not a corner
   case; it was a hole.
2. **Cross-group recovery.** `_group_key` scoped the check so a comparison
   metric's period and delta figures grouped by base metric id while every
   headline metric sat in a separate report-level group. The whole-period
   headline is the sum of its own period figures, so with `exits_permanent`
   at 68 and `exits_permanent__q2` at 63 both visible, the suppressed
   `exits_permanent__q1` (5) printed into the same report.md as their
   difference. Reproduced through the real CLI with the shipped grant-report
   structure.
3. **Percent triangulation.** The complementary pass restricted itself to
   `unit == "count"` figures, so every percent passed through untouched. A
   percent with a visible denominator uniquely determines a suppressed
   numerator via rounding: with `exits` = 14 visible and `pct_permanent` = 71%
   visible, the suppressed numerator can only be 10.

## Decisions

### The disclosure scope is the whole report, split only by unit

ADR 0004 scoped the complementary check to sibling groups to avoid coincidental
numeric collisions between unrelated metrics. That partition severed real
accounting identities. The report spec is a flat metric list over one data
table; a headline is the sum of its own period figures, category counts sum to
totals over the same column, and per-period category counts sum to per-period
totals, so real identities cross any grouping the metric ids could induce.
Every count figure is now checked against every other count figure in the
report, and every percent figure against every other percent figure (counts
and percents are not additive with each other, so they never mix). The
accepted cost is that a coincidental match between unrelated figures can
suppress more than strictly necessary. Over-suppression is the protective
direction; a leak is a defect. Verified against the shipped grant-report
example: after the fixed point, no signed combination of the figures still
visible reconstructs any suppressed cell.

### The recovery search is exhaustive over the group, with pruning

`_disclosing_combination` now searches combinations of every size up to the
full candidate set, so no within-group identity escapes on size. It is a
depth-first search over candidates sorted by descending magnitude with
branch-and-bound pruning: a branch is abandoned once the remaining candidates'
combined magnitude cannot close the gap to the target. A report holds tens of
figures at most, so the pruned search is cheap in practice. No term bound
remains.

### A suppressed period figure takes its delta with it

ADR 0004 already declined to treat a delta as a recovery target (its
derivability from its own periods is definitional). The reverse dependency is
enforced now: when either period figure is suppressed, the delta figure is
suppressed too. A visible delta beside the other period reconstructs the
hidden period directly, and a visible delta beside a visible whole-period
headline pins the hidden period at `(headline - delta) / 2`, a recovery whose
half coefficient the signed-sum search cannot represent. It is closed by rule
rather than by search because no +/- combination expresses it.

### Percents are suppressed whenever any count in the report is suppressed

The correct rule would suppress exactly the percents whose numerator or
denominator metric is suppressed. The data model cannot express that
dependency: a `MetricSpec`'s `value_sql` is opaque SQL, and inferring the
feeding counts from SQL text would be the name-matching heuristic this module
already rejected once. So the conservative rule ships instead, and is
documented as such in the module docstring: when any count figure in the
report is suppressed, every percent figure is suppressed with it, including
percents whose inputs are all visible. If the spec later grows structured
numerator/denominator references, the rule can narrow to the true dependency.

## Consequences

- `tests/test_suppression.py` gained tests reproducing each demonstrated case
  exactly: the 162/five-term breakdown, the 68/63/5 headline-versus-quarter
  recovery run through the real CLI, and the 14/71% triangulation (plus the
  shipped housing-demo's 60% end to end). Each failed against the prior code
  and passes now.
- The shipped examples suppress more than before. grant-report now redacts the
  `exits` headline and the Q1 client count as complementary cells (each is the
  next-smallest cell in a combination that reconstructed a suppressed
  quarter), and every percent in both examples is redacted because both
  reports contain suppressed counts. The demo datasets are small, so heavy
  redaction is the honest output for them.
- `tests/test_grounded_sections.py`'s pinned grant-report comparison row
  changed to match the corrected behavior.
- The `_group_key` function is gone; the scoping rule lives in the
  `suppression.py` module docstring.
