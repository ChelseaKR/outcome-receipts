# Data card: HUD 2024 PIT Count by CoC (subpopulation extract)

- Source: U.S. Department of Housing and Urban Development (HUD), Office of
  Community Planning and Development — the Point-in-Time (PIT) Count portion
  of the Annual Homeless Assessment Report (AHAR) to Congress. Direct file:
  `https://www.huduser.gov/portal/sites/default/files/xls/2007-2024-PIT-Counts-by-CoC.xlsb`,
  linked from HUD's [2024 AHAR: Part 1](https://www.huduser.gov/portal/datasets/ahar/2024-ahar-part-1-pit-estimates-of-homelessness-in-the-us.html)
  page.
- License: U.S. Government work, public domain (17 U.S.C. §105). Not
  redistributed under this repository's Apache-2.0 license because it is not
  this repository's own content; the extract is a small, clearly-attributed
  excerpt of an openly licensed public statistical release.
- Tier: L1 — public, non-sensitive. Aggregate CoC-level counts only; no
  client-level rows, no PII, no identity content of any kind. This is a
  jurisdiction-wide statistical release, not the participant-level data this
  tool's own product operates on.
- Fetch and refresh cadence: retrieved once, 2026-08-21, for the calibration
  finding in [`docs/audits/hud-coc-suppression-calibration-2026-08-21.md`](../audits/hud-coc-suppression-calibration-2026-08-21.md).
  Not refreshed automatically; a future HUD PIT year would be a deliberate
  re-run of the evaluation, not routine maintenance (`eval/hud/SOURCE.md`
  documents the retrieval and extraction recipe for exactly that).
- Retention: indefinite, as evaluation evidence for a committed, gated
  finding — the same retention rationale as the synthetic eval fixtures.
- Dataset version: HUD's `2007-2024-PIT-Counts-by-CoC.xlsb`, server
  `Last-Modified` 2024-12-27T14:22:09Z (the 2024-data revision), SHA-256
  `ae88fbb58dadfbfccc254619b714d37e0720bd9854a31a16ad0e381fa14959ed`. The
  committed extract, `eval/hud/hud_pit_2024_by_coc_subpopulation.csv`, is
  SHA-256 `b27565a7122bf3e26e78018cf3102e611d35d3af04be2c95a0dc75b51df73496`.

## Coverage and limitations

363 of 390 CoCs in HUD's 2024 workbook: every CoC that reported a full
sheltered-and-unsheltered count that year. The excluded 27 did a
sheltered-only count under HUD's biennial unsheltered-count policy for
certain CoC categories; their unsheltered figures are not applicable that
year, not a true zero, and are excluded rather than treated as zero (see
`eval/hud/extract.py`). 10 named subpopulation groups per CoC (Overall,
Veterans, Chronically Homeless with its Individuals/Families split,
Unaccompanied Youth Under 25 with its Under-18/18-24 split, Parenting Youth
Under 25, Children of Parenting Youth), each as an Overall/Sheltered
Total/Unsheltered triple — 10,890 real published count cells.

This is a real, non-synthetic dataset used for exactly one purpose: measuring
how the shipped small-cell suppression default (`SUPPRESSION_THRESHOLD = 11`
in `src/outcome_receipts/suppression.py`) behaves against realistic,
subpopulation-shaped count data, not to compute or publish anything about
this repository's own product. HUD's PIT counts represent an entirely
different disclosure context than the tool's actual target (a single
nonprofit's own HMIS-derived participant counts) — see "Why this isn't the
comparison it looks like" in the linked findings write-up for why a direct
HUD-vs-shipped-default suppression-rate comparison would be a category error.

## Lineage and validation

`eval/hud/extract.py` is the full, reproducible extraction recipe (requires
`pandas`, `pyxlsb`, `openpyxl` — not project dependencies, run outside `make
verify`). `tests/test_hud_suppression_calibration.py` independently reproves,
from the committed CSV, that `overall == sheltered_total + unsheltered` holds
for all 3,630 rows and that the age-band and individual/family nesting
identities hold for all 363 CoCs, before using the same CSV to recompute
every number in the findings write-up.

*Last verified: 2026-08-21 · Recheck cadence: on any re-run against a newer HUD PIT year, and at least annually.*
