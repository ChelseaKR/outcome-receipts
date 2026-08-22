# Source: HUD 2024 PIT Counts by CoC

## Origin

- Publisher: U.S. Department of Housing and Urban Development (HUD), Office of
  Community Planning and Development.
- Series: Point-in-Time (PIT) Count, part of the Annual Homeless Assessment
  Report (AHAR) to Congress. The January 2024 sheltered-and-unsheltered count.
- Landing page: [2024 AHAR: Part 1 - Point-in-Time Estimates](https://www.huduser.gov/portal/datasets/ahar/2024-ahar-part-1-pit-estimates-of-homelessness-in-the-us.html),
  linked from [HUD Exchange: AHAR Reports](https://www.hudexchange.info/homelessness-assistance/ahar/).
- Direct file: `https://www.huduser.gov/portal/sites/default/files/xls/2007-2024-PIT-Counts-by-CoC.xlsb`
- License: U.S. Government work, public domain (17 U.S.C. §105). No usage
  restriction; not redistributed under this repository's Apache-2.0 license
  because it is not this repository's own content.

## Retrieval

- Retrieved: 2026-08-21, via `curl` with a standard browser `User-Agent`
  header (the file 404s without one; HUD's CDN appears to reject the default
  `curl` UA specifically, not general programmatic access -- confirmed by the
  identical 404 body/length regardless of path, and by the request succeeding
  immediately once a UA string was added).
- Server `Last-Modified`: 2024-12-27T14:22:09Z (the 2024-data revision of the
  file; HUD appends each new year's data to the same workbook rather than
  publishing a new filename).
- Original file SHA-256: `ae88fbb58dadfbfccc254619b714d37e0720bd9854a31a16ad0e381fa14959ed`
  (`2007-2024-PIT-Counts-by-CoC.xlsb`, 9,914,004 bytes, one worksheet per
  year 2007-2024, 390 CoC rows × 1,308 columns in the `2024` sheet covering
  sheltered/unsheltered breakdowns by age, gender, race/ethnicity, and named
  HUD subpopulations).
- The original `.xlsb` is not committed (9.9 MB of mostly-irrelevant
  demographic cross-tabs this evaluation doesn't use). What's committed is
  the extract below, plus this file and `extract.py`, so the extraction is
  independently re-runnable against a fresh copy of the same HUD file.

## Extraction

`extract.py` (this directory) reads the `2024` worksheet, keeps only the 363
of 390 CoCs whose `Count Types` is `"Sheltered and Unsheltered Count"` (the
27 remaining CoCs did a sheltered-only count that year under HUD's biennial
unsheltered-count policy for certain CoC categories; their unsheltered cells
are blank/not-applicable, not a true zero, so mixing them in would silently
relabel "not counted" as "counted as zero"), and pulls the Overall/Sheltered
Total/Unsheltered triple for 10 named subpopulation groups: the base Overall
Homeless count, Veterans, Chronically Homeless (aggregate, and its
Individuals/People-in-Families split), Unaccompanied Youth (Under 25, and its
Under-18/18-24 age-band split), Parenting Youth (Under 25), and Children of
Parenting Youth.

Requires `pandas`, `pyxlsb`, and `openpyxl` (not project dependencies; this
is a one-time data-preparation script, run outside `make verify`):

```sh
uv run --with pandas --with pyxlsb --with openpyxl python3 extract.py
```

- Extract: `hud_pit_2024_by_coc_subpopulation.csv`
- Extract SHA-256: `b27565a7122bf3e26e78018cf3102e611d35d3af04be2c95a0dc75b51df73496`
  (re-running `extract.py` against a fresh copy of the source `.xlsb`
  reproduces this exact digest)
- Rows: 3,630 (363 CoCs × 10 subpopulation groups)
- Verified identities (see `tests/test_hud_suppression_calibration.py`):
  `overall == sheltered_total + unsheltered` holds exactly for all 3,630
  rows; `unaccompanied_youth_under25 == unaccompanied_youth_under18 +
  unaccompanied_youth_18to24` and `chronically_homeless ==
  chronically_homeless_individuals + chronically_homeless_in_families` each
  hold exactly for all 363 CoCs.

## Tier and governance

L1 — public, non-sensitive: an openly licensed U.S. government aggregate
statistical release with no personal or identity content (aggregate counts
only, no client-level rows, no PII). See
[docs/data/hud-coc-pit-subpopulations.md](../../docs/data/hud-coc-pit-subpopulations.md)
for the full data card, including the currency stamp -- this file is a
retrieval record for one fixed extract, not a living claim, in the same
spirit as `tests/fixtures/compat/v0.1.0/SOURCE.md`: do not regenerate it
against a newer HUD file without a deliberate decision to re-run the
evaluation (a newer PIT year is a real, meaningful re-run, not routine
maintenance).
