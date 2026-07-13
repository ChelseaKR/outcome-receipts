# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project aims
for [Semantic Versioning](https://semver.org/spec/v2.0.0.html) from 1.0.

Version `0.1.0` is the first beta release. It includes the deterministic core
and the privacy, verification, mapping, localization, optional drafting, and
release-hardening work completed before the first public tag.

## [Unreleased]

### Added
- Full portfolio-standards v1.0.1 conformance gate: CodeQL, OpenSSF Scorecard,
  standards pin/fetch, source and documentation hygiene, critical-module
  coverage, npm/OSV/security scans, and live repository hardening.
- WCAG 2.2 AA browser gates (axe, pa11y, Lighthouse, 320px reflow, reduced
  motion) plus ACR, statement, and an honest manual screen-reader review record.
- AI governance evidence for the optional Bedrock seam: canonical generated
  model/data cards, 100-case bilingual benchmark, risk register, impact
  assessment, SoA, red-team report, and residual-risk register.
- Definition of Done, canonical ADR log, incident and secret runbooks, operations
  recovery procedure, and per-source data-governance cards.

### Changed
- Reviewer-facing English and Spanish copy now ships as compiled gettext
  catalogs with extraction, compilation, BCP 47, key, and placeholder gates.
  The trace view is fully localized instead of always rendering English.
- `make verify` now reproduces the complete applicable AUTO-GATE set used by CI,
  including security, i18n, accessibility, generated cards, and eval drift.
- The active main ruleset now requires pull requests, signed linear history,
  resolved threads, strict checks, and no bypass actors. The zero approval count
  is an explicit solo-maintainer ADR, not a silent missing rule.

### Fixed
- The required CodeQL job now fails closed when SARIF output is missing or
  contains any finding, while retaining the SARIF artifact for diagnosis.
- Compiled English and Spanish gettext catalogs now have explicit, deterministic
  metadata and a byte-reproducibility regression test, preventing Babel from
  embedding the compilation time in committed `.mo` files.
- The security-tool installer now authenticates cached executables as well as
  downloads, rejects symlink and directory substitution, verifies exact binary
  versions, and uses the repository's Python 3.12 runtime for `uvx` scanners.
- The release workflow now uses the maintained `actions/attest` v4 SBOM path,
  emits and validates CycloneDX 1.7, and adds the deterministic UUIDv5 serial that
  GitHub requires but `cyclonedx-bom --output-reproducible` omits. The first
  `v0.1.0` attempts stopped before release publication when the SBOM predicate
  detector rejected the document as an unsupported format.
- Release verification now pulls the published PyPI version and verifies the
  Sigstore-backed GitHub attestation after publication.

## [0.1.0] - 2026-07-11

### Added
- **Repository discovery and practitioner-feedback kit.** Added a five-minute
  demo walkthrough, an exact-text social preview asset, structured demo and
  schema-mapping issue forms, a Discussions template, a pull-request checklist,
  an executable six-week discovery campaign, channel-ready outreach drafts, a
  canonical explainer, and a rolling GitHub-traffic snapshot script. The public
  call to action is a verified demo run rather than a vanity star count, and all
  feedback paths warn against posting client-level data or real service exports.
- **Human approval sign-off gate before export (R8).** `receipts run` now
  records a named human approver after the grounding gate passes and before
  any file is written. `--approved-by NAME` records the approver
  non-interactively (for CI); an interactive run prompts for a typed name;
  a non-interactive run with no approver aborts fail-closed with the new
  exit code 3 (`EXIT_APPROVAL_FAIL`) and writes nothing. The approver and
  approval time are recorded in the report's provenance statement and in the
  manifest (`provenance.approved_by`, `provenance.approved_at`; `approved_by`
  is stated explicitly as `null` when nothing was approved). `run --json`
  carries the approval in the payload and never prompts. New merge-blocking
  `tests/test_approval.py`.
- **Machine-readable CLI output and an explicit exit-code contract (FIX-09).**
  Every command (`init`, `run`, `audit`, `verify`, `verify-ledger`, `eval`)
  accepts `--json`, before or after the subcommand, and then emits one JSON
  object on stdout instead of the human-readable lines. Exit codes are
  single-sourced module constants documented in the README: 0 success, 1 a
  failed audit/verify/verify-ledger/eval check, 2 the grounding gate refused
  to export. The JSON is presentational only; it never changes the exit code
  or what is written to disk. New `tests/test_cli.py` pins the JSON shapes
  and the code table.
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
  - `docs/rulesets/main.json`: the intended full branch ruleset for `main`. The
    live `protect-main` ruleset currently enforces required checks, blocks
    force-pushes and deletion, and has no bypass actors. Pull-request, review,
    linear-history, and signed-commit rules remain recorded here for a future
    multi-maintainer policy update (CICD-12).
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

- **Reusable CI action** (`action.yml`). The `receipts verify` gate is packaged as
  a composite GitHub Action, so a downstream repo can gate CI on receipt drift with
  a commit-pinned `uses: ChelseaKR/outcome-receipts@<sha>` and the two inputs `config` and `receipts`
  (mirroring the CLI flags). The CLI already exits non-zero on drift, so the action
  fails closed. It is dogfooded in CI against `examples/housing-demo/receipts.json`,
  and usage plus supply-chain pinning guidance live in `docs/ci-action.md`.
- **Receipts diff between reporting cycles** (`diff.py`, `receipts diff`). Change
  accounting between two receipted runs: `receipts diff PRIOR.json CURRENT.json`
  compares two receipts manifests and reports which figures moved, were added, or
  removed, and *why* each moved (value change, row-count change, slice-hash change,
  or query change). It is a pure manifest-to-manifest comparison — distinct from the
  in-run period-over-period `comparison.py` — reading only the JSON, so it needs no
  data table or SQL engine. The `computed_at` timestamp is never a reason, mirroring
  `verify`, so a re-run alone is not a move. `render_diff_markdown` renders a
  "Receipts diff" section with summary counts, a table of changed figures, and Added
  / Removed lists.
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
- **Tooling enforces the declared code-quality bar.** `ruff` now runs CLAUDE.md's
  full select set (`E,W,F,I,UP,B,SIM,S,C90,RUF`) with `max-complexity = 10`, so
  security (`S`), complexity (`C90`), and Ruff-specific (`RUF`) rules are
  merge-blocking. `pytest` runs under `pytest-cov` with a `--cov-fail-under=90`
  branch-coverage gate (currently 93%), wired into the pytest addopts so
  `make verify` and CI enforce the same bar. Tests ignore `S101` (assert use),
  and the engine's deterministic spec-driven SQL composition ignores `S608` in
  `engine.py` and `comparison.py`.

### Fixed
- **Small-cell suppression did not suppress.** Code review of the v0.2
  suppression work (`9deb8cf`) found the drafted narrative, the rendered charts,
  and the comparison table were all built from the pre-suppression figures, so a
  below-threshold count could appear in plain English (and in a chart or the
  comparison table) directly above a receipts section marking the same metric
  `[SUPPRESSED]`. A suppressed `Figure` also kept its original, unredacted
  `Receipt`, so `receipt.row_count` and `receipt.value` — what `report.py` and
  `trace.py` actually render — carried the raw count regardless. Fixed by
  reordering the pipeline (`compute → suppress → draft → ground → export`;
  suppression is now the first transform, not the last) and by redacting every
  raw-count-bearing field of a suppressed figure's receipt, not just its own
  `value`/`display`. See `docs/decisions/0004-suppression-runs-before-drafting.md`.
- **Complementary suppression matched metric names, not arithmetic.** A category
  like `clients_black` could be suppressed while `clients_served` and
  `clients_white` passed through unredacted even though the suppressed value was
  trivially recoverable as `clients_served - clients_white`, because neither
  name matched the `"total"/"all"/"sum"/"aggregate"` keyword heuristic.
  Complementary suppression is now a real arithmetic disclosure check, scoped to
  a figure's crosstab group so it does not fire on coincidental numeric
  collisions between unrelated metrics.
- **`SuppressionResult.ok` compared two counts, not the privacy invariant.** It
  now checks that no figure recorded as unsuppressed had an original value
  below threshold.
- New tests in `tests/test_suppression.py` run the full `receipts run` pipeline
  and string-search the actual rendered `report.md`, `receipts.json`, and
  `trace.html` for the raw suppressed values, rather than asserting only on the
  in-memory `Figure`.
- **The disclosure search stopped at four terms.** A total decomposed into five
  or more categories evaded complementary suppression: the only combination
  recovering the suppressed fifth category (`total - a - b - c - d`) has five
  terms, one past the cap, so it was never tried. The search now covers
  combinations of every size up to the full figure group, as a pruned
  depth-first search, with no term bound. Demonstrated by adversarial
  re-verification with a 162 = 52 + 30 + 61 + 17 + 2 breakdown; the suppressed
  2 was exactly recoverable.
- **A headline and its own period figures were never checked against each
  other.** The complementary check grouped `exits_permanent__q1/__q2/__delta`
  by base metric id while the whole-period headline `exits_permanent` sat in a
  separate report-level group, so `headline(68) - q2(63)` printed the
  suppressed `q1(5)` into the same report.md (reproduced through the real CLI
  with the shipped grant-report structure). The disclosure scope is now the
  whole report, split only by unit, because the spec's flat metric list admits
  accounting identities across any finer grouping. A suppressed period figure
  now also takes its delta figure down with it, since a visible delta beside a
  visible headline pins the hidden period at `(headline - delta) / 2`. See
  `docs/decisions/0005-disclosure-scope-and-exhaustive-recovery-check.md`.
- **Percents could triangulate suppressed counts.** The complementary check
  restricted itself to count figures, and a percent with a visible denominator
  uniquely determines a suppressed numerator via rounding (`exits` = 14 visible
  and `pct_permanent` = 71% force the suppressed numerator to 10). The metric
  data model cannot express which counts feed a percent (`value_sql` is opaque
  SQL), so the conservative rule ships: when any count figure in the report is
  suppressed, every percent figure is suppressed with it, documented as such in
  the module docstring.

### Initial core
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
