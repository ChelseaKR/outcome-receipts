# Data card: organization-provided service export

- Source: a nonprofit operator's own system of record; no fixed external URL or
  publisher exists because the operator supplies the file.
- License: operator-controlled data, not redistributed under this repository's
  Apache-2.0 license.
- Tier: L3 while client-level rows are in process; only L2 aggregates and
  provenance metadata may be emitted.
- Fetch and refresh cadence: operator-selected for each reporting run. The CLI
  records the loaded path, row/column counts, content digest, and receipt
  computation timestamp; it does not silently claim the export is current.
- Retention: the tool does not copy or persist source rows. The input remains
  subject to the operator's system-of-record retention and deletion policy.
- Dataset version: N/A because this repo does not publish or redistribute the
  operator's dataset.

## Lineage and validation

The CSV loader rejects empty inputs, duplicate or blank headers, malformed row
widths, and invalid text. Author-declared data checks run before computation.
Each scalar figure records its deterministic query, row count, canonical BLAKE2b
slice hash, column names, and computation time. The aggregate report, trace, and
manifest receive figures, not source rows.

## Known limitations

A valid file can still be incomplete, miscoded, nonconsensual, or based on an
unfair metric definition. Receipts prove derivation, not collection quality or
fitness for a funder's definition. The operator must review source freshness,
authority, consent, and metric definitions before approval.

*Last verified: 2026-07-12 · Recheck: on any loader, lineage, or retention change.*
