# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project aims
for [Semantic Versioning](https://semver.org/spec/v2.0.0.html) from 1.0.

## [Unreleased]

### Added
- **More report templates.** A report type is its TOML spec, so two new ones ship
  as specs alongside the housing demo: a grant report
  (`examples/grant-report/`) and a board report (`examples/board-report/`). Each
  names its own metrics and writes its own narrative, and both run through the
  same engine, drafter, and fail-closed grounding gate.
- **Charts from the grounded figures** (`charts.py`). A `[[charts]]` entry names
  the figures it draws; the chart's bars or points are those figures' values and
  every label is a figure display, so a chart has no data path of its own. Each
  chart renders a standalone SVG (`role="img"`, `<title>`, `<desc>`) and an
  accessible Markdown data table that carries the same grounded numbers. The SVG
  is pure standard library, so no dependency is added. The chart's claim numbers
  run through the grounding gate; its pixel geometry does not.
- **Multi-period comparison** (`comparison.py`). A `[comparison]` section runs one
  set of metrics across two periods (date-window predicates substituted into a
  `{period}` placeholder) and reports the change. The two period values and the
  change are each a figure with a receipt; the change is computed by a single
  subtracting SQL query over the union of both periods, not by arithmetic over the
  page. Direction is a word derived from the sign, so no ungrounded number is
  shown.
- New merge-blocking test `tests/test_grounded_sections.py`: every chart and
  comparison number binds to a receipt, and an injected ungrounded number is
  caught.
- ADR `docs/decisions/0002-templates-charts-comparison.md` records these
  decisions, including why deterministic SVG was chosen over a charting library.
- **Metric `definition` field** (`models.MetricSpec`, `Receipt`). An optional
  plain-language statement of what a figure counts (the window, who is in scope,
  the deduplication rule) that rides in the receipt and renders next to the figure
  in the report, the manifest, and the trace view, so the choice a query encodes is
  legible without reading SQL. Closes the bias-audit TODO on definitional traps.
- **Provenance statement on every export** (`provenance.py`). A standard block in
  the report body, and a machine-readable record in the manifest, stating that each
  number came from a deterministic query, that no figure was written by a model, and
  that the gate bound every number before export, with the count.
- **Funder-facing trace view** (`trace.py`). `receipts run` writes `trace.html`: a
  self-contained, accessible (WCAG 2.2 AA) HTML rendering of the receipts a
  non-engineer can read, with a summary table of every figure and a receipt detail
  per figure. No script, no external asset, opens offline.
- **`receipts verify`** (`verify.py`). Re-derives every figure from the spec and the
  cited data and checks each value, slice hash, row count, and query against a
  receipts manifest; reports every drifted receipt and exits non-zero on any drift.
- New tests `tests/test_definition.py`, `tests/test_provenance.py`,
  `tests/test_trace.py`, and `tests/test_verify.py`, including the failing fixtures
  (tampered manifest is drift, escaped HTML, unbound count marks the gate failed).
- ADR `docs/decisions/0003-definitions-provenance-trace-verify.md` records these
  decisions and why small-cell suppression is held for v0.2.

### Changed
- `receipts run` now computes the comparison figures, renders the charts, grounds
  the narrative and the chart-and-comparison claims, and writes the report, the
  receipts manifest, the trace view, and any chart SVGs. Export is blocked if any
  number in any surface is unbound. The report and manifest carry the provenance
  statement.
- The Accessibility standard now applies to the chart output (SVG plus a paired
  data table) and the trace-view HTML rather than being N/A.

## [0.1.0] — 2026-06-27

### Added
- The deterministic core, with no language model in any path:
  - **Metric engine** (`engine.py`): loads service data into in-memory SQLite and
    runs each metric as a SQL query; the value comes from the query.
  - **Receipts** (`models.Receipt`): every figure carries the exact query, the row
    count of its slice, a BLAKE2b hash of that slice, the value, and a timestamp
    from an injected clock so a committed run is reproducible.
  - **Deterministic drafter** (`draft.py`): fills a report template's
    `{metric_id}` placeholders with figures' display strings; an unknown
    placeholder fails loudly.
  - **Fail-closed grounding gate** (`grounding.py`): binds every number in the
    narrative to a figure display; an unbound number blocks export. The
    merge-blocking invariant, covered by `tests/test_grounding_gate.py`.
  - **Eval** (`evaluate.py`, `report.py`): the gated grounding rate with Wilson
    confidence intervals; committed at `eval/report.md`.
- `receipts run`, `receipts audit`, and `receipts eval` commands.
- A seeded synthetic housing-program fixture (`examples/housing-demo/`), zero real
  personal data.

### Not yet
- The small-cell suppression / aggregate export (v0.2), the optional Claude
  drafting seam guarded by the same gate (v0.3), and the metric-mapping agent over
  schema-variant exports (v0.4). See `docs/ROADMAP.md`.
