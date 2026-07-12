# 0004 — Ground before and after the suppression boundary

Status: accepted; the complementary-scope refinement ("grouped by crosstab",
`_group_key`) is superseded by 0005, which found that the per-group scope
severed real accounting identities and widened the disclosure scope to the
whole report.

Amended 2026-07-11: the original decision correctly required every publishable
surface to be built from redacted figures, but suppression before the only
grounding pass could hide a number invented by a future model drafter. The
pipeline now grounds once against raw receipts, suppresses, rebuilds every
publishable surface, and grounds again before approval.

## Context

Code review of the v0.2 small-cell suppression work (`9deb8cf`) found that the
implementation faithfully followed the order recorded in `CLAUDE.md` and
`docs/ROADMAP.md` — `compute → draft → ground → suppress → approve → export` —
and that this order is itself the bug. `_cmd_run` drafted the narrative and
rendered the charts from the figures the metric engine computed, ran the
grounding gate against that same pre-suppression set, and only called
`suppress_figures` afterward, on the figures written to the receipts section.
The documented rationale was that suppression should be "the last transform
before a human sees the report, so what they approve is what ships" — but no
human-approval step exists in the code; `approve` in the diagram names a step
that was never built. With nothing between grounding and export, a report
shipped with the drafted narrative's plain English stating a below-threshold
count in full ("Of the 10 who exited the program, 6 moved into permanent
housing"), directly above a receipts section marking those same metrics
`[SUPPRESSED]`. The same gap let a comparison table read its period and delta
figures from `ComparisonResult`, a structure independent of whatever
suppression later did to the flat figure list, so a quarter's small count
could leak through the comparison table even when the identical metric_id was
correctly redacted everywhere else.

Separately, `suppress_figures` itself only redacted a figure's own `value` and
`display`; the `Receipt` attached to a "suppressed" figure was the original,
unredacted one, unchanged. `report.py`, `receipts_manifest`, and `trace.py` all
read `receipt.row_count` and `receipt.value` directly, not `Figure.value`, so
every rendered artifact showed the raw row count and value next to the
"[SUPPRESSED]" label regardless of drafting order. Both defects had to be
fixed together: reordering alone does not help if the receipt a correctly-timed
caller reads is still unredacted, and redacting the receipt alone does not help
if the narrative was already drafted from the raw value before suppression ran.

## Decisions

### Suppression is the publishable-data boundary, between two grounding gates

New order: `compute → receipt → draft → ground → suppress → re-draft →
re-ground → human-approve → export`. The first gate proves that drafting did not
invent a number. Suppression then redacts the full figure set and rebuilds the
comparison, reconciliation, charts, and templates. The second gate proves the
publishable result contains only numbers backed by redacted receipts. Raw
drafts and charts are validation intermediates and are never written.

### A suppressed figure's receipt is redacted, not reused

`suppress_figures` now constructs a new `Receipt` for every redacted figure,
zeroing `value` and `row_count` and replacing `slice_hash` with the canonical
empty-slice hash (`EMPTY_SLICE_HASH`), rather than attaching the original
receipt "for audit trail." A hash of the exact suppressed rows is itself a
verification oracle against a guessed row set; it is redacted along with the
count. `value_sql`, `unit`, `computed_at`, and `definition` are kept, since
they describe the query rather than the data.

### `ComparisonResult` is rebuilt from the suppressed figure set

`redact_comparison` takes an already-suppressed flat figure list and rebuilds
`ComparisonResult.rows` and `.figures` by metric_id lookup, so
`render_comparison_table` renders the same redaction the report, manifest, and
trace view do. `_cmd_run` calls it once, immediately after `suppress_figures`,
before the comparison is used anywhere else.

### Complementary suppression is a real arithmetic check, grouped by crosstab

The complementary pass no longer matches metric_id substrings ("total", "all",
"sum", "aggregate"). It checks, for every suppressed figure, whether its exact
value is reconstructable by adding or subtracting other still-visible figures
in the same group, and suppresses the smallest-valued figure in a disclosing
combination (the standard next-smallest-cell rule), repeating to a fixed point.
Two refinements were necessary to keep this from over- or under-suppressing:

- The check is scoped to a group (`_group_key`): a comparison metric's period
  and delta figures (`exits__q1`, `exits__q2`, `exits__delta`) group by their
  base metric_id, and every other figure — the report's own headline metrics —
  shares one group. Checking arbitrary figures against each other, across
  unrelated metric families, produced coincidental numeric collisions with no
  real relationship behind them (verified against `examples/grant-report/`: an
  unrelated headline count and a different quarter's exit count happened to
  subtract to the same integer as a suppressed cell).
- A delta figure (`_DELTA_SUFFIX`) is never scanned as a target. A delta is
  *defined* as current minus prior, so it is tautologically "recoverable" from
  its own two period figures; treating that as a discovered disclosure
  cascaded into suppressing an already-safe period figure for no privacy
  benefit, since the reader could already compute the delta from the two
  period values regardless of what the delta figure itself displays. A delta
  can still act as a candidate for reconstructing one of its own periods if it
  is left visible while that period is suppressed — that risk is real, not
  definitional.

### `SuppressionResult.ok` checks the invariant it claims to check

`ok` now verifies that no metric_id in `unsuppressed` has an original value
below threshold, using a `values` field carried on the result for exactly this
purpose, replacing a count comparison (`len(unsuppressed) < len(suppressed)`)
that could not detect a single leaked cell with nothing to compare it against.

## Consequences

- The privacy invariant — a sub-threshold count never appears in an exported
  artifact — is enforced by construction: raw surfaces exist only in memory for
  the first gate, while every renderer and gate in the export path receives the
  rebuilt suppressed figure set.
- `tests/test_suppression.py` gained an end-to-end integration test that runs
  `receipts run` on `examples/housing-demo` and string-searches the actual
  rendered `report.md`, `receipts.json`, and `trace.html` for the raw
  suppressed values, rather than only asserting on the in-memory `Figure`.
- A few existing tests asserted the old, name-heuristic complementary-
  suppression behavior (suppressing whatever was named "total" regardless of
  whether it actually discloses anything, or leaving an accidentally-named
  figure alone regardless of a real relationship). Those assertions changed to
  match verified-correct behavior; see `tests/test_suppression.py` and
  `tests/test_grounded_sections.py`.
- `CLAUDE.md` and `docs/ROADMAP.md`'s architecture order are updated to match;
  neither described the fix, only the order that produced the bug.
