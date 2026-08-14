# 0011 — Numeric canonicalization preserves magnitude

Status: accepted. Amends ADR 0007, which stated the matching policy but not what
the normalization it relies on does and does not preserve.

## Context

ADR 0007 states that "matching is exact after presentational normalization …
numeric values are never rounded and receive no epsilon or tolerance." Issue #80
demonstrated that the normalization itself was lossy in exactly the shape where
losing information is worst.

`grounding._normalize` resolved a lone `.` or `,` by digit shape: a separator
splitting the digits into 1-3 then exactly 3 was read as a thousands group.
That rule was applied to the figure display *and* the prose span, so both
`1.234` and `1,234` canonicalized to `1234`:

```
_normalize('1.234') -> '1234'
_normalize('1,234') -> '1234'
```

A receipted `count` of 1,234 therefore bound a prose span of `1.234`, and a
receipted `rate` of 1.234 bound a prose span of `1,234`. The same collision
reached every unit: `money` with three decimals, `duration`, and `percent` all
export it.

```
ground("Our cost per outcome ratio is 1.234 dollars per client.", [count 1,234])
  ok=True  bound=['1.234']  unbound=[]
```

The load-bearing claim of the project is that a number in the prose which does
not match a receipt blocks export. Here a number differing from its receipt by a
factor of a thousand did not block export: it bound, and the report shipped with
the gate reporting PASS. In a funder report that is a cost per outcome or a
length of stay wrong by three orders of magnitude, carrying a receipt that
appears to back it — not a typo a reviewer catches.

The deterministic drafter writes figure displays verbatim, so `receipts run` on
the default path does not produce it. The two reachable paths are the two where
the prose is not machine-copied: `receipts audit` over a hand-written draft, and
the optional model drafter, which is the reason the gate exists at all.

## Decision

Canonicalization preserves magnitude. The two sides of the comparison are no
longer symmetric, because they are not symmetric in reality.

**A figure display is never ambiguous.** Every display is produced by one
formatter, in which `,` groups thousands and `.` marks the decimal, and figure
displays do not change across `--locale`. So a display is read by that rule and
no heuristic is applied to it: `12.345%` is twelve point three four five
percent, which the digit-shape rule got wrong.

**A prose span in the ambiguous shape is refused a value reading.** That shape is
exactly: one `.` or `,`, 1-3 digits before it, exactly 3 after. Under one
convention it is a thousands group and under the other a decimal point, the two
readings differ by a factor of a thousand, and nothing in the span says which.
Such a span binds only a display it matches character for character — that is,
one written the way the receipt writes it.

**Every other shape still binds across conventions**, because every other shape
resolves on its own: a repeated separator can only group (`1.234.567`); both
separators present fix the right-most as the radix (`12.345,67` and `12,345.67`
both reduce to `12345.67`); a group that is not exactly three digits long cannot
be a thousands group (`3,5` is three and a half); and NBSP-style separators only
ever group.

Of the three options the issue lists, this is (1) — comparing on the value rather
than on a shape-guessed string — with (2), refusing the ambiguous shape, as the
fallback for the one case where a value cannot be recovered from prose. Option
(3), resolving by the run's `--locale`, was rejected: it is wrong for a
mixed-provenance draft, which is precisely the `audit` case this defect is
reachable through.

## Consequences

- The cost is false unbinds in one shape: a Spanish-convention `1.234` for a
  receipted `1,234` is refused rather than guessed at. That is the fail-closed
  direction, it is visible to the author (the number is reported as not binding,
  at its offset), and the remedy is to write the number the way the receipt
  does. Any count from 1,000 to 999,999 written in the report's own convention
  keeps binding, so ordinary reports are unaffected.
- ADR 0007's exactness claim now holds across the normalization as well as
  after it. What normalization preserves: magnitude, the radix position, the
  sign, and the percent marker. What it removes: currency symbols, a trailing
  unit word, and grouping separators. What it never does: round, apply a
  tolerance, add or drop a digit, or convert a written numeral.
- `"0.30"` and `"0.3"` remain distinct. A figure has one canonical display
  (ADR 0004) and matching is exact; treating differently-padded decimals as
  equal would be a second, quieter loosening.
- `eval/grounding-benchmark.jsonl` gains a formatting family. The old benchmark
  could not fail for any reason relating to locale handling: all 100 cases were
  bare three-digit integers with the same integer as the display, so the fifty
  Spanish cases exercised the same code path as the fifty English ones. The new
  cases cover thousands and decimal separators in both conventions, NBSP
  grouping, percent, currency, unit suffixes, and the ambiguous shape, with the
  Spanish half written in Spanish number convention. Each case records its
  expected count of unbound spans, so a failing case cannot begin failing on a
  different span and still count as a pass.
- Two committed tests asserted the defect as correct behaviour and are corrected:
  `test_thousands_grouped_figure_binds_across_locale_separators` listed `1.234`
  among the spellings that must bind a display of `1,234`, and
  `test_stray_year_stays_unbound` asserted the same span was bound.
- Not addressed here, and worth stating: `--locale es` translates the surrounding
  copy but leaves figure displays in US format, so a Spanish-reading funder sees
  `1,234` for one thousand two hundred and thirty-four. That is a display
  decision, it is now relied on by the rule above (a display's separators are
  read one way), and it deserves its own record rather than being changed as a
  side effect of a gate fix.
