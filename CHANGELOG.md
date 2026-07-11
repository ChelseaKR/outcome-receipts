# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project aims
for [Semantic Versioning](https://semver.org/spec/v2.0.0.html) from 1.0.

**No version of this project has been tagged or released yet** (`git tag` and
`gh release list` are both empty as of 2026-07-05). The `[0.1.0]` section below
groups the changes that make up the intended first release and is dated by
when that scope was completed on `main`, not by a release date. It will be
retitled with the real release date when `v0.1.0` is tagged and
`release.yml` publishes it (see `docs/ROADMAP.md`).

## [Unreleased]

### Added
- **Release integrity hardening (2026-07-09).**
  - `release.yml`'s `pypi-publish` job now publishes the exact `dist/` bytes the
    `release` job built and Sigstore-attested (artifact hand-off plus a
    `sha256sum -c` re-check) instead of rebuilding — the published files are
    provably the attested files (BUG-2).
  - `release.yml`'s `verify` job fails closed unless the release tag is an
    annotated tag that carries a signature and points at the verified commit
    (REL-08 / BUG-3).
  - `__version__` is single-sourced from package metadata
    (`importlib.metadata.version`), so pyproject.toml is the only place the
    version is written; new `tests/test_version.py` pins `__version__`,
    `receipts --version`, and the installed metadata together (REL-02 / BUG-4).
  - `docs/rulesets/main.json`: the exported branch ruleset of record for `main`
    (require PR; required checks `verify`/`security`/`accessibility`; dismiss
    stale reviews; no force-push; linear history; signed commits; no bypass
    actors), ready for the owner to apply (CICD-12).
  - `ci.yml` hygiene: `setup-uv` aligned to the same v6 SHA as `release.yml`
    with `version: "0.11.19"` pinned everywhere, dependency cache keyed on
    `uv.lock`, and the pa11y step reads `$GITHUB_WORKSPACE` from the
    environment instead of interpolating `${{ github.workspace }}` into the
    shell body (BUG-7).

- **Standards-conformance remediation (2026-07-05).** Closes the P0/P1 gaps found
  by the 2026-07-05 audit against the portfolio `STANDARDS/`:
  - `release.yml` gains a `verify` job (`make install && make verify` at the
    tagged commit, plus a CHANGELOG-section check) that `release` and
    `pypi-publish` now depend on, so nothing is signed or published without a
    green gate at that commit. Tag name flows through `env.RELEASE_TAG` instead
    of interpolating `${{ github.ref_name }}` into `run:` bodies; `enable-cache`
    is off on every `setup-uv` step in the signing/publish path; both jobs share
    a `concurrency` group.
  - `ci.yml` gains a `security` job (`pip-audit`, `osv-scanner --lockfile
    uv.lock`, `gitleaks`, `zizmor`) and an `accessibility` job (`pa11y
    --standard WCAG2AA` against the built `trace.html`).
  - `pytest` now gates on branch coverage (`--cov-fail-under=90`) and runs with
    `--strict-markers --strict-config --import-mode=importlib`; `ruff`'s select
    set grows to the full bar CLAUDE.md already promised (`S`, `C90`, `RUF`) with
    `max-complexity = 10`; `make lint` adds `ruff format --check`.
  - Dev dependencies move to PEP 735 `[dependency-groups]`; `uv.lock` is
    committed and `make install` runs `uv sync --frozen`.
  - Python floor raised to 3.12 (`requires-python`, classifiers, `.python-version`,
    `mypy`, `Makefile`, `release.yml`'s SBOM venv), matching what CLAUDE.md
    already specified.
  - New `.github/CODEOWNERS` and `docs/I18N.md` (N/A-with-reason artifact).
  - CONTRIBUTING.md, SECURITY.md, README.md, and CITATION.cff corrected to stop
    claiming branch protection and a released `v0.1.0` that don't exist yet
    (see the 2026-07-05 remediation log for the evidence).

### Added
- **SAST (2026-07-10, SEC-07).** `ci.yml`'s `security` job gains a Semgrep step
  (`p/default` + `p/python`, pinned scanner version, `--severity ERROR --error`)
  that blocks the build on any ERROR-severity finding. The two findings it
  surfaced on first run (`sqlalchemy-execute-raw-query` on the same
  already-triaged `load_table` identifiers the `S608` waiver below covers) are
  suppressed with inline `# nosemgrep:` comments tracked in the new
  `.semgrep-waivers.yml` ledger, per SEC-10 waiver hygiene.

### Fixed
- Two `S608` ruff findings in `comparison.py` and `engine.py` triaged as false
  positives (spec SQL and internal table/column identifiers are author-trusted,
  not user-supplied, per `SECURITY.md`'s Scope section) and suppressed per-line
  with justification; `S101` (assert) is ignored under `tests/*` only, since
  pytest's own idiom relies on it.

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

## [0.1.0] — scope completed 2026-06-27, not yet tagged/released

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
