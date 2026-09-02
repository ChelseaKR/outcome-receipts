# Refuse a negative-valued chart metric rather than draw it

- Status: Accepted
- Date: 2026-08-27
- Deciders: Chelsea Kelly-Reif

## Context

`charts.py` derives every bar height and every line y-coordinate from
`Figure.value`, on an assumption that was never written down or checked: that a
drawable figure's value is not negative.

It is not always. A comparison or reconciliation delta figure (`comparison.py`,
metric id suffix `__delta`) carries the *signed* change in `Figure.value`.
Nothing stops a `[[charts]]` block from naming one; the delta figures are
ordinary members of the flat figure list a run builds, and a chart spec names
metrics by id.

For a real, non-suppressed, fully receipted negative value, both drawing paths
produced a false picture. `_bar_svg_body` computed `bar_h = (value / scale) *
height if value > 0 else 0.0`, so a decrease took the `else` branch and rendered
`height="0.0"`, flush on the axis baseline, with its own text label and `<title>`
correctly reading `12` directly above it. `_line_svg_body` had no guard at all
and plotted the same point at `y=668.0` on a canvas 360 high, outside the image,
with a polyline running off the bottom of the frame to reach it. `_scale_max`
compounded both: over a set of decreases its `top > 0` test failed and the axis
maximum fell back to `1.0`.

The module's own statement of the rule is "A bar height is a claim." The claim a
zero-height bar makes is "no change", and the receipt said minus twelve.

This is the defect class the project already fixed once for a different cause.
Issue #78 and `docs/decisions/0010-*` established that a cell withheld by
small-cell suppression must be drawn as an explicit absence, never as a zero.
That fix branches on `point.withheld`, which is suppressed-or-`None`. A decreased
delta is neither. It is a normal figure with a real value that happens to be
below zero, and no path was ever taught to handle it.

Two remedies were considered, and issue #117 names both.

**Draw the magnitude.** Rejected, and it is a worse version of the same fault.
PR #121 implemented it; measured against `main` at 80ee14d, values of `-12.0` and
`+8.0` produced `height="248.0"` and `height="165.3"`, byte-identical to what
values of `+12.0` and `+8.0` produce, with an identical `<title>` on the first
bar in both cases. A 12-unit decrease became the tallest bar on the chart with
nothing distinguishing it from a 12-unit increase, which is harder to notice than
the zero-height bar it replaced.

**Draw a signed bar from a zero baseline.** Honest geometry, and refused here for
a reason that is specific to this module rather than to the idea. A chart may put
exactly one kind of text on the page: `figure.display`. That constraint is
load-bearing and is why the grounding gate can verify a chart the same way it
verifies prose (`Chart.claims_text` is the displays and nothing else; the
accessible data table is the displays and nothing else). A delta figure's display
is its *unsigned magnitude* by design: `comparison._magnitude_display` calls
`_format(abs(value), ...)` so the display stays a single token the gate can bind,
and the direction is carried separately as a word on `ComparisonRow`, which a
chart never receives. Signed geometry would therefore ship with no signed text
equivalent anywhere on the page, and a screen-reader user, who has only the
`<title>` and the data table, would read the same `12` for a rise and for a fall.
Fixing that means giving a chart a direction channel of its own, which changes
the chart spec, the data table, the grounding contract for charts, the EN/ES
catalogs, and the accessibility conformance record.

## Decision

`_points` raises `ValueError` when a drawable point's value is below zero, naming
the chart id, the metric id, and the value, and stating both why a chart cannot
render a sign and what the author can do instead: chart the two period figures
rather than their delta, or read the direction from the comparison table, which
states it in words. The check sits in `_points`, so it covers the bar path and
the line path from one place, and it runs before any geometry is computed.

The refusal is scoped to values strictly below zero. Zero is a real, publishable
value and still draws a zero-height bar on the baseline, which is the truthful
geometry for it. A withheld point is untouched and keeps the absence marker ADR
0010 requires; a withheld figure carries no value at all, so the two rules never
contend.

The report fails to build rather than building a picture that is wrong. This
matches how a chart already treats a spec it cannot honour: `render_chart` raises
`KeyError` for a metric id that names no figure and `ValueError` for an unknown
chart kind, "so a misconfigured chart fails loudly rather than drawing nothing or
guessing a value."

## Consequences

A chart naming a metric that decreased no longer renders. That is a real cost and
the intended one. It is not a loss of a working capability, because the picture
it replaces was false in every case it covered: a decrease drawn as no change, or
a point drawn off the canvas.

Charting a period-over-period change is now out of reach until a chart can carry
a direction, and a report that wants to show one uses the comparison table, which
already states direction in words and is already grounded. Adding that channel is
a later decision and needs its own ADR, because it touches the rule that a chart
renders only figure displays.

The check is on the value, not on the metric id, so it does not depend on
recognising a `__delta` suffix or on knowing which metrics may go negative. Any
future source of a negative figure is covered by the same refusal on the same
day it appears.

`_scale_max`'s `top <= 0` fallback now means one thing, "every drawable value is
exactly zero", rather than silently also covering "the largest value is
negative".
