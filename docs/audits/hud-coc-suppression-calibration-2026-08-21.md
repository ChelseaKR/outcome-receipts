# Findings: does the shipped suppression default match real practice? — 2026-08-21

## The question

`docs/ROADMAP.md` has framed this gap since the privacy invariant shipped:
`SUPPRESSION_THRESHOLD = 11` is the U.S. CMS Cell Size Suppression Policy's
number, not HUD's — "HUD's HMIS publication guide leaves the numeric rule to
the applicable local policy." Every fixture this repository has ever run the
suppression engine against is synthetic. This is the first run against real,
public, non-synthetic data: HUD's own published Continuum of Care (CoC)
subpopulation counts.

**The answer, stated plainly first:** the shipped default does not, and
cannot, "match" a HUD-published numeric small-cell rule, because none exists
to match — HUD's own CoC-level Point-in-Time (PIT) reports are published with
no suppression at all, down to and including exact zeros (see
[Why this isn't the comparison it looks like](#why-this-isnt-the-comparison-it-looks-like)
below). What real HUD data *can* and does show: applied to the shape of
reporting this tool actually targets — a single organization's participant
counts broken out by the named subpopulations HUD itself defines — the
threshold of 11 is not a rarely-triggered background control. It suppresses a
majority of granular subpopulation cells, and complementary suppression is
empirically necessary, not a theoretical edge case, in data with the nested
additive structure HUD's own subpopulation categories create. That is
evidence the default is calibrated to actually protect this domain's small
cells, not evidence it was validated against a number HUD publishes, because
no such number exists.

## The data

HUD 2024 PIT Count by CoC, extracted from the official workbook HUD links
from its [2024 AHAR: Part 1](https://www.huduser.gov/portal/datasets/ahar/2024-ahar-part-1-pit-estimates-of-homelessness-in-the-us.html)
page:

- **URL:** `https://www.huduser.gov/portal/sites/default/files/xls/2007-2024-PIT-Counts-by-CoC.xlsb`
- **Retrieved:** 2026-08-21
- **Original file SHA-256:** `ae88fbb58dadfbfccc254619b714d37e0720bd9854a31a16ad0e381fa14959ed`
- **Extract committed at:** `eval/hud/hud_pit_2024_by_coc_subpopulation.csv`
  (SHA-256 `b27565a7122bf3e26e78018cf3102e611d35d3af04be2c95a0dc75b51df73496`)

Full retrieval and extraction detail, including why 27 of the workbook's 390
CoC rows are excluded (a sheltered-only count that year has no true
unsheltered figure to test against — see the note in
[Scope discipline](#scope-discipline)), is in
[`eval/hud/SOURCE.md`](../../eval/hud/SOURCE.md) and the data card,
[`docs/data/hud-coc-pit-subpopulations.md`](../data/hud-coc-pit-subpopulations.md).

**363 CoCs**, each with **10 named subpopulation groups** (the base Overall
Homeless count; Veterans; Chronically Homeless, split into Individuals and
People in Families; Unaccompanied Youth Under 25, split into Under-18 and
18-24 age bands; Parenting Youth Under 25; Children of Parenting Youth), each
with an **Overall / Sheltered Total / Unsheltered** triple — **10,890 real,
published count cells** in total. Two arithmetic identities hold exactly
across the whole dataset (independently reproven in
`tests/test_hud_suppression_calibration.py`): `overall == sheltered_total +
unsheltered` for every one of the 3,630 (CoC, subpopulation) rows, and the
age-band and individual/family splits sum to their parent subpopulation for
every one of the 363 CoCs.

## Method

`scripts/hud_suppression_calibration.py` builds one report-shaped `Figure`
set per CoC (30 count figures: 10 subpopulations × 3 components — the same
scale `suppress_figures`'s own docstring assumes a real report has) and runs
the actual, unmodified `outcome_receipts.suppression.suppress_figures` —
not a reimplementation — against each one, at the shipped default
`SUPPRESSION_THRESHOLD = 11`. `tests/test_hud_suppression_calibration.py`
recomputes every number below from the committed CSV and fails if it drifts
from what's reported here.

## Results

### 1. How many published cells fall in 1–10 (what the default would withhold)

| | Cells | Share of all 10,890 |
|---|---:|---:|
| Primary-suppressed (magnitude 1–10) | 2,832 | 26.0% |
| Complementary-suppressed (recoverable by arithmetic if left visible) | 3,781 | 34.7% |
| **Total withheld** | **6,613** | **60.7%** |

A quarter of all published cells fall directly in the suppressed range, and
once complementary suppression closes the recoverable combinations it finds,
the majority of cells in a report this granular would be withheld. That
number is driven almost entirely by *which* subpopulation is being reported,
not by CoCs being unusually small:

| Subpopulation | Primary-suppression rate |
|---|---:|
| Overall Homeless (whole-CoC total) | **1.0%** |
| Chronically Homeless | 12.1% |
| Chronically Homeless Individuals | 14.0% |
| Unaccompanied Youth (Under 25) | 26.8% |
| Chronically Homeless, People in Families | 27.9% |
| Unaccompanied Youth, 18–24 | 28.8% |
| Veterans | 31.0% |
| Unaccompanied Youth, Under 18 | 35.8% |
| Children of Parenting Youth | 38.4% |
| Parenting Youth (Under 25) | 44.3% |

The whole-CoC total is suppressed in about 1 CoC in 100 — a whole
jurisdiction's overall homeless count is rarely small. Every named
subpopulation breakdown is suppressed far more often, from 1 in 8 (Chronically
Homeless) to nearly half (Parenting Youth). This is the finding worth taking
seriously: **the threshold bites hardest on exactly the granular
subpopulation breakdowns a funder report is likely to ask for** ("how many
veterans did you serve," "how many unaccompanied youth"), not on the
aggregate totals a synthetic fixture might default to testing.

### 2. How often a suppressed cell would be recoverable by subtraction

352 of 363 CoCs (97.0%) have at least one cell that falls below the
threshold. Of those, **346 (95.3% of all CoCs, 98.3% of CoCs with any
suppressed cell) require complementary suppression** — meaning at least one
primary-suppressed value in that CoC's report would have been reconstructible
by arithmetic from other cells if the engine suppressed only the values
directly below 11. Complementary suppression is not a rare safeguard for an
edge case here; on data with HUD's own nested subpopulation structure
(sheltered + unsheltered = overall; age bands sum to their parent category;
individuals + families sum to the chronically-homeless total), it is the
common case.

One concrete example, Continuum of Care `AK-500` (reproduced exactly in
`tests/test_hud_suppression_calibration.py::test_a_named_real_example_from_the_write_up_reproduces`):

| Metric | Value | Suppressed? |
|---|---:|---|
| Unaccompanied youth, overall (under 25) | 141 | visible |
| Unaccompanied youth, 18–24 (overall) | 131 | **complementary** |
| Unaccompanied youth, under 18 (overall) | 10 | primary |

`141 - 131 = 10`. If the 18–24 figure (131, well above the threshold on its
own) were left visible alongside the visible 141 total, a reader would
recover the suppressed under-18 count exactly. The engine correctly
suppresses the 18–24 figure too.

### 3. Whether real published tables contain true zeros adjacent to small cells

**630 of 3,630 (CoC, subpopulation) rows (17.4%) have a true zero sitting in
the same Overall/Sheltered/Unsheltered triple as a value in [1, 10].** Across
the whole dataset, 2,005 of 10,890 cells (18.4%) are true zeros. This is not
a contrived synthetic corner case: real HUD data routinely reports an exact
`0` right beside a small nonzero figure in the same identity group, and the
engine must — and, per `tests/test_suppression.py` plus the reproduction
here, does — keep that zero visible while withholding its nonzero sibling.
Example from the same `AK-500` row: Parenting Youth (Under 25) reports
Sheltered Total = 8, Unsheltered = 0. The 8 is suppressed; the 0 is published
as a genuine, disclosed zero, not folded into the suppression the way an
earlier version of this codebase's chart renderer did before #77/#78 fixed
serializing a withheld cell as a zero.

## Why this isn't the comparison it looks like

It would be a mistake to read this as "HUD suppresses X%, we suppress 60.7%,
therefore we're stricter than HUD." HUD's CoC-level PIT reports are published
with **zero suppression** — every cell in the source workbook, including
counts as small as 6 or 8, is an exact published integer. But a CoC PIT count
is a HUD-conducted, congressionally-mandated, jurisdiction-wide census
covering an entire metro area or region, produced and reviewed under an
entirely different disclosure framework than a single nonprofit program
reporting its own participants to one funder — which is this tool's actual
target (`AGENTS.md`: "turning 'unduplicated clients exiting to permanent
housing' into a correct deterministic query over one specific org's messy
HMIS or CSV export"). The ROADMAP's original framing holds: HUD's own HMIS
publication guidance deliberately leaves the small-cell number to local
policy for exactly this reason — a whole-CoC PIT count and a single
program's HMIS-derived funder report are not the same disclosure risk, and
HUD does not claim they are.

## Conclusion: does the threshold stay, move, or become configurable?

**The default (11) stays, as a documented, evidence-backed choice rather
than an unvalidated placeholder — with the calibration finding recorded
plainly rather than left silent.** Three things support this:

1. There is no HUD-published numeric small-cell rule to adopt instead; CMS's
   is the closest documented analogue for HMIS-derived aggregate reporting,
   and this repository already cites it as such.
2. Applied to real subpopulation-shaped data, the threshold is neither inert
   (it withholds a majority of granular cells) nor absurd (whole-program
   totals pass through freely at a ~1% suppression rate) — it does real,
   differentiated work exactly where a nonprofit's own reporting is most
   likely to have genuinely small, re-identification-sensitive counts.
3. Complementary suppression, exercised on data with real nested identities
   for the first time (rather than synthetic fixtures authored to trigger
   it), fires on 95% of CoCs — confirming it is addressing a common real
   disclosure path, not overengineering for a case that doesn't occur in
   practice.

This does not mean 11 is provably optimal — no such proof is possible without
a ground-truth re-identification-risk study this repository has no access to.
It means the number is not naive, and the domain-shaped evidence that was
missing before this write-up now exists and is gated by a test.

## Scope discipline

No individual CoC is named in this document in a way that implies anything
about that CoC's own disclosure practices or data quality — every number here
is either an aggregate across all 363 CoCs, a suppression-rate-by-subpopulation
aggregate, or a single fully public, already-published CoC-level total cited
as a worked arithmetic example, exactly the kind of number HUD itself
publishes without restriction. The 27 CoCs excluded from this analysis (of
390 in the source workbook) did a sheltered-only count in 2024 under HUD's
biennial unsheltered-count policy for certain CoC categories; their
unsheltered cells are blank/not-applicable that year, not a true zero, and
including them would have silently relabeled "not counted" as "counted as
zero" — the same absence-rendered-as-a-value defect class this portfolio has
found and fixed elsewhere, caught here at the data-ingestion boundary before
it could enter the analysis at all.

*Last verified: 2026-08-21 · Recheck cadence: on any re-run against a newer HUD PIT year, and at least annually.*
