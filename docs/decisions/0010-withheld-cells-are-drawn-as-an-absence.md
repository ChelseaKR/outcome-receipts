# 0010 — A withheld cell is drawn as an absence, never as a quantity

Status: accepted

## Context

Issue #78 demonstrated that `charts.py` drew a suppressed figure as a zero. The
chart module reads `figure.value` for geometry, and a redacted figure carried
`value = 0.0`, so:

- a bar became `height="0.0"` sitting on the axis baseline — byte-identical
  geometry to a figure that is genuinely zero;
- a line chart put the point on the axis floor and ran the `<polyline>` straight
  through it, drawing a collapse and a recovery across data that was withheld on
  purpose;
- `_scale_max` took the maximum over all values, so a withheld cell also took
  part in scaling the bars that *were* drawn, as a zero.

The label above the bar and the accessible data table both said `[SUPPRESSED]`.
The bar said zero. For a small provider that is the difference between "we cannot
report this quarter" and "we housed nobody this quarter", and the second one is
what the picture said. The shipped `examples/grant-report` demo exported exactly
this: `out/charts/permanent-by-quarter.svg`, titled "Permanent-housing exits by
quarter", with two empty bars on the baseline.

Nothing tested it. `tests/test_charts.py` had ten tests and none involved a
suppressed figure. ADR 0004's consequences list an end-to-end string search over
`report.md`, `receipts.json`, and `trace.html`; the chart SVGs are exported
artifacts, are digest-listed in `receipts.json` and `bundle.json`, and were not
in that list.

## Decision

A bar height is a claim, and so is the slope of a line. Neither may be drawn for
a figure the report declines to state. Concretely:

- **`Figure.value` is `None` for a withheld figure.** This is the root of it. A
  renderer that reads the field gets nothing to draw rather than a zero, and the
  type checker names every reader that has to decide what to do about it. This
  extends ADR 0009 (issue #77), which made the *receipt's*
  numerics `None`, to the field renderers actually read for geometry.
- **A bar becomes a full-height hatched slot** with a dashed outline in the axis
  grey (`#4a5568` stroke over an `#a0aec0` diagonal hatch), never the data blue,
  carrying the same `[SUPPRESSED]` label. A full-height slot cannot be misread as
  a small value; the hatch and dashed outline mean it is not read as a large one
  either. This is the issue's option 1.
- **A line breaks.** The `<polyline>` is emitted once per run of consecutive
  drawable points, so no drawn segment ever spans a withheld one, and the
  withheld position gets a dashed full-height rule instead of a plotted point.
  Joining across the gap would assert that the hidden value lies on the drawn
  slope. This is the issue's option 2.
- **`_scale_max` ignores withheld points**, so a hidden cell takes no part in
  scaling the points that are drawn. This one was latent rather than observable:
  the scale is a maximum, and a withheld cell arriving as `0.0` could only have
  raised it if every real value were already at or below zero, where the clamp to
  `1.0` produced the same answer anyway. It is fixed structurally so it stays
  true if the scaling rule ever becomes something other than a maximum, and the
  test asserts the property rather than a changed output.
- **The absence is announced, not only drawn.** The marker carries a `<title>`
  naming the policy and stating that this is not a value of zero; the chart's
  `<desc>` says how many categories are withheld and what was done instead. The
  hatch and the break are visual signals a screen-reader user never receives.

Option 3 from the issue (refuse to render a chart with any suppressed figure and
emit only the data table) was not taken. It is trivially correct and it is also a
worse report: a grant report over quarterly data with one small quarter would
lose its chart entirely, and the chart is the part people look at. Drawing the
absence keeps the comparison the reader came for while making the gap the most
visible thing on the page.

## Consequences

- `ChartPoint.value` is `float | None` and the type gains `suppressed` and a
  `withheld` property; a point counts as withheld if either signal says so, which
  is the fail-closed direction for a hand-built point.
- `comparison.py` refuses to compute a direction or a magnitude from a figure
  with no value, rather than treating it as zero. Comparison runs before
  suppression, so this cannot fire today; it is a guard against a redacted figure
  entering the compute path later.
- `suppress_figures` refuses an already-redacted input set. A second pass would
  have no value to test and would list a withheld cell under `unsuppressed`.
- `tests/test_charts.py` covers a withheld figure for both `bar` and `line`,
  asserting on SVG geometry: that a withheld bar and a true-zero bar do not share
  `(y, height)`, that a line with a withheld point emits no polyline spanning it,
  that a five-point series with one gap emits exactly two segments neither of
  which contains the gap's x, and that the drawn bar's height is identical
  whether or not a withheld figure is in the chart.
- The end-to-end artifact search in `tests/test_suppression.py` now includes the
  chart SVGs, closing the gap ADR 0004 left. It asserts the set of `<text>`
  contents in every exported SVG is a subset of the publishable figure displays,
  the category labels, and the chart title — so a raw withheld count cannot
  appear as a coincidence — and that no bar sits flat on the baseline.
- The chart `<desc>` remains English-only in every locale. That is pre-existing
  (`charts.py` has never taken a locale, and its whole description was already
  hardcoded English), and the redaction marker itself is untranslated by design,
  so a Spanish reader still sees `[SUPPRESSED]` and the hatched slot. Localizing
  the description is left as its own change.
