# 0004 — Metric units beyond count and percent

Status: accepted

## Context

The engine shipped two units: `count` and `percent`. Funder outcome reports also
carry money (aid disbursed, cost per outcome), durations (length of stay, time to
housing), and rates. Each of these is a number a report asserts, so each must be a
figure with a receipt and must pass the fail-closed grounding gate exactly as a
count does. This also makes a first, bounded cut at open question #3 in `CLAUDE.md`
(how a numeric span is parsed and matched: money and unit-suffixed numbers), which
`docs/RESEARCH-ROADMAP.md` R7 asks be recorded in an ADR.

A figure's `display` is the single canonical string the drafter writes and the gate
binds — the stability guarantee is that one figure has exactly one display. Adding a
unit is therefore adding one more canonical form, plus the gate change that lets that
form bind to the span a reader sees in prose.

## Decisions

### Four canonical display forms

`_VALID_UNITS` gains `money`, `duration`, and `rate` alongside `count` and `percent`.
`engine._format` renders one canonical string per unit; `decimals` sets fixed-decimal
places:

- `money` — `$` prefix, thousands separators, fixed decimals: `$1,234.50` (use
  `decimals = 2` for cents). One currency, no code: reports are single-currency and a
  symbol keeps the display a self-describing token.
- `duration` — a thousands-separated fixed-decimal number of **days** with a `days`
  suffix: `30 days`. Days is the one canonical unit; a metric that means hours or
  months converts to days in its SQL, so the display never has to carry which unit it
  is in. (`HH:MM` was rejected: it is not a single grounded number and would need its
  own span rule.)
- `rate` — a thousands-separated fixed-decimal number with no marker: `4.2`. The
  column header or the figure's definition names the denominator. This mirrors how a
  comparison already shows a percentage-point change as a bare number.
- `count` and `percent` are unchanged, so every committed figure, eval, and manifest
  re-derives identically.

### The gate binds a unit-decorated display to its span

The grounding gate must bind these displays to the number a reader sees:

- The number regex gains an optional leading `\$?` so a money display is captured as
  one span (`$1,234.50`) rather than splitting at the `$`.
- `_normalize` strips the decorations a unit adds — a leading `$`, thousands commas,
  and a trailing unit word (the `days`) — from **both** the span and the figure
  display before comparing, so the two normalize to the same bare number.
- A trailing unit word is deliberately **not** captured by the prose regex. Capturing
  an arbitrary following word would swallow the next word after *any* bare number and
  change what an unbound span reports (breaking the merge-blocking gate tests that
  assert the exact unbound token). Instead the suffix is stripped from the figure
  display in `_normalize`, so a `30 days` figure binds to the `30` in prose while a
  stray `30 people` still reports `30` as its span.

Match stays **exact** on the normalized number: no rounding or tolerance is
introduced here. Tolerance, ranges, and written-out numbers remain open under R7.

### A unit-typed delta keeps its unit

A comparison's change figure formats its magnitude with the metric's unit for `money`
and `duration` (so a currency change reads as `$100.00`, not `100`), and as a bare
number for `percent` and `rate` (a percentage-point / per-unit change, named by the
column). The receipt still carries the signed value.

## Consequences

- Money, duration, and rate figures are receipted, formatted, and grounded like counts
  and percents; the no-model constraint and the fail-closed gate are unchanged.
- The three merge-blocking grounding tests stay green because the prose regex still
  captures a bare number as exactly that token.
- The `display` of a figure remains one canonical string per unit, so `receipts verify`
  re-derivation and the receipts manifest are unaffected in shape.
- Open question #3 / R7 is partially settled: money and unit-suffixed numbers now have a
  recorded span rule and an exact match; ranges, written-out numbers, and tolerance are
  still open.
