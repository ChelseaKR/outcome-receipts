# 0008 — Non-figure presentation fields are inside the disclosure boundary

Status: accepted

## Context

Issue #75 demonstrated that a `ComparisonRow`'s `direction` (and its derived
`arrow` property) could survive redaction intact while the row's `prior`,
`current`, and `delta` figures all rendered `[SUPPRESSED]`. `direction` is set
once, in `comparison.py::_compare_metric`, from the sign of the raw,
unredacted delta value (`_direction(raw_delta.value)`); it is a plain `str`,
not a `Figure`. `redact_comparison` and `redact_reconciliation` (added under
ADR 0004, widened under ADR 0005) rebuild a row's `prior`/`current`/`delta`
by metric_id lookup in the suppressed figure set, but neither touched
`direction`. `suppress_figures`'s exhaustive same-unit recovery search (ADR
0005) ranges only over `Figure` values, so it never saw `direction` either —
there was no mechanism anywhere in the suppression pipeline positioned to
catch it.

The sharpest reproduction: two quarters of a below-threshold count, equal to
each other (8 and 8). Both periods and the delta redact to `[SUPPRESSED]`, but
`direction` still read `"no change"` — an exact equality claim, `prior ==
current`, printed beside three cells the report had just decided were too
small to publish. A weaker form shipped in the committed `examples/
grant-report` demo: a row with one suppressed period and one visible period
still printed a correct `"increase"`/`"decrease"`, narrowing the hidden
period's plausible range beyond what the visible figures alone would allow.

Why the existing tests didn't catch it: `tests/test_grounded_sections.py` had
a pinned assertion, `"| [SUPPRESSED] | 14 | [SUPPRESSED] | increase |" in
report`, that encoded the leak as expected behavior rather than catching it —
a demonstration of how easily a "the redacted cells look right" review misses
a field that isn't one of the redacted cells.

## Decision

`redact_comparison` and `redact_reconciliation` now also redact a row's
`direction` (and therefore its `arrow`, which is derived from `direction` and
carries no independent state) whenever any of that row's `prior`, `current`,
or `delta` figures is in the redacted state (`Figure.display ==
"[SUPPRESSED]"`) after the by-metric_id rebuild. This mirrors the delta's own
rule from ADR 0005 ("a suppressed period figure takes its delta with it"): it
is closed by direct rule at the row level, not by adding `direction` to the
general-purpose figure search, because `direction` is not a `Figure` and has
no receipt or unit to search over.

The redacted value is the same sentinel string a suppressed `Figure` already
displays (`"[SUPPRESSED]"`), not a new sentinel, a locale-translated word, or
an `Optional[str]`/`None`. This was chosen over the alternatives because:

- It reuses an existing, already-understood convention instead of adding a
  second "this is redacted" representation for renderers to special-case.
- `direction`/`arrow` stay plain `str`, so no consumer's type changes; a
  renderer that previously assumed one of three literal values now assumes
  one of four, and every such renderer (the comparison and reconciliation
  Markdown tables in `report.py`, the trace view's `_change_label` in
  `trace.py`, and the `arrow` property itself) was audited and updated to
  fall back to printing the sentinel instead of raising `KeyError` or, worse,
  silently mis-selecting the wrong increase/decrease copy template.
- It is not run through the gettext copy catalog (`copy.direction_increase`
  and friends): like a suppressed `Figure`'s own `"[SUPPRESSED]"` display, a
  redaction marker is not narrative prose and does not need a Spanish
  translation, so this fix requires no `i18n` catalog changes.

## Consequences

- `direction`/`arrow` are documented, in `ComparisonRow`'s docstring and in
  `suppression.py`'s module docstring, as being inside the disclosure
  boundary despite not being `Figure`s: any future presentation field that is
  *derived from* a figure's raw value without itself being a `Figure` needs
  the same treatment by default, not by omission.
- The pinned `tests/test_grounded_sections.py` assertion that encoded the leak
  is corrected to assert the fixed behavior, plus an explicit negative
  assertion that the old row text does not appear.
- `tests/test_suppression.py` gained the direct reproduction (the 8-and-8
  no-change case, through `redact_comparison` directly and through the real
  CLI end to end against `report.md` and `trace.html`), a not-suppressed
  control case proving the fix does not touch a row with nothing hidden, and
  a `redact_reconciliation` case proving the same fix applies per-side
  (`outcome` and `financial` are redacted independently).
- No change to thresholds, the complementary-suppression search, or how a
  `Figure` itself is redacted; this is scoped to the two presentation fields
  the issue named.
