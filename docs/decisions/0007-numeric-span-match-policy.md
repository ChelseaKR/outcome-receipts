# 0007 — Numeric-span matching is exact and written numerals fail closed

Status: accepted

## Context

The grounding gate is the enforcement boundary for generated prose. R7 left
ranges, written-out numbers, and tolerance unresolved after locale, money, and
duration normalization landed. Ignoring a written numeral is fail-open: a draft
containing “twelve” previously produced no numeric span and could pass.

## Decision

- Matching is exact after presentational normalization. Currency symbols,
  thousands separators, locale decimal separators, percent markers, and canonical
  unit suffixes are normalized; numeric values are never rounded and receive no
  epsilon or tolerance.
- Each endpoint of a range is an independent span. Both must bind to a receipt.
- A leading sign is part of the span and survives normalization. Negative five
  cannot bind a positive-five receipt.
- Common English and Spanish cardinal and ordinal words are detected but never
  converted or bound. Each is unbound and blocks export. This deliberately trades
  false positives for the protective direction; drafters must use the receipted
  digit display.

## Consequences

The rule is deterministic, locale-aware, and fail-closed. It does not attempt
natural-language number interpretation, infer rounding intent, or guess whether a
range is inclusive. A future expansion may add another language only by extending
the detection vocabulary with merge-blocking tests; it may not silently ignore
numeric words.
