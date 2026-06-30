# 0002 — Report templates, charts, and period comparison

Status: accepted (v0.2)

## Context

v0.1 shipped one report: a narrative whose every number traces to a receipt. The
next step is to make the tool useful for the reports a nonprofit actually files,
which means more than one report shape, a visual summary of the figures, and a
period-over-period comparison. The risk is that each of these is an easy place to
slip an ungrounded number onto the page: a second template, a chart with its own
data series, or a hand-computed delta. The single load-bearing invariant — no
number reaches an export without a receipt — has to survive all three.

## Decisions

### A template is a spec, and more templates are more specs

A report is already defined entirely by its TOML spec: the title, the narrative
template, and the metrics. So a "grant report" and a "board report" are two more
specs, not a new code path. Each names its own metrics and writes its own
narrative, and both run through the same engine, drafter, and grounding gate.
This keeps the report types data-defined and keeps the trust machinery in one
place. The two new specs live in `examples/grant-report/` and
`examples/board-report/`, each self-contained with its own data.

### Charts read the figures, and never a second data path

A chart names the figures it draws (`metrics = [...]` in a `[[charts]]` entry).
Its bars or points are `figure.value` and every label is `figure.display`, so a
chart has no data of its own; it is a rendering of figures that already carry
receipts. Two surfaces come out of one chart. The SVG is the image: its only
numbers are pixel coordinates derived from the grounded values, and those are
presentation, not claims, so they are written to a standalone `.svg` file and
kept out of the report's prose and out of the grounding gate. The accessible data
table is the text equivalent: it carries the figures as their display strings,
inlined in the report beneath an image reference, and those numbers are grounded
exactly like any number in the narrative. Grounding a chart means grounding its
claims text — the figure displays — not its geometry.

The SVG is assembled as text with the standard library, so the project keeps its
zero-dependency, offline posture. A charting library (matplotlib, plotly) was
rejected: it would add a heavy dependency and a binary-image path for a fixed,
simple set of bar and line charts that a few hundred lines of deterministic SVG
cover, and a library's raster output is harder to make accessible than an SVG
with `role="img"`, a `<title>`, a `<desc>`, and a paired data table.

### A period comparison computes its delta in SQL, not in Python

A comparison runs one set of metrics across two periods. Each metric carries a
`{period}` placeholder; the comparison substitutes a period's predicate (a SQL
boolean, typically a date window) and computes that metric for the prior period
and the current period. Those two are ordinary figures with receipts. The change
is a figure too, and it is not arithmetic over the other two: its value comes from
a single query that subtracts the prior period's scalar from the current period's
scalar inside SQLite, over a slice that is the union of both periods' rows. So the
delta traces to a receipt the same way the period figures do.

The delta receipt records the signed change (current minus prior), an honest
record. The delta's display is the magnitude, because the grounding gate matches
the bare number a reader sees, and the gate's number pattern does not include a
leading minus sign. Direction is reported as a word — increase, decrease, no
change — derived from the sign, so the page asserts no number that is not a
receipt. A rate metric's change is in percentage points, shown without a percent
sign and labeled in the column header, so the displayed token stays a plain
number the gate can bind.

## Consequences

- More report types are added as specs, with no new code and no new trust
  surface. The existing housing-demo spec is unchanged, so the committed eval and
  the v0.1 tests are untouched.
- Charts add no runtime dependency. Every chart ships an accessible data table,
  so the Accessibility standard now applies to the chart output rather than being
  N/A.
- The grounding gate runs over the narrative and over the chart-and-comparison
  claims; an ungrounded number in any of them blocks export. A new merge-blocking
  test (`tests/test_grounded_sections.py`) covers it.
- The comparison reuses one metric definition per row across periods, so a metric
  is written once and compared, not duplicated per period.
- A future move to a charting library or an HTML report stays possible behind the
  same `ChartSpec` surface; it would be a new ADR.
