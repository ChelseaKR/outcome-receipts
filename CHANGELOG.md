# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project aims
for [Semantic Versioning](https://semver.org/spec/v2.0.0.html) from 1.0.

Version `0.1.0` is the first beta release. It includes the deterministic core
and the privacy, verification, mapping, localization, optional drafting, and
release-hardening work completed before the first public tag.

## [Unreleased]

### Added
- Digest-pinned, non-root Docker self-hosting with a one-command demo,
  networkless/read-only smoke test, and blocking Trivy HIGH/CRITICAL scan.
- A `1.0` report-spec schema and compatibility policy beside the existing
  receipts-manifest schema; scaffolds and maintained examples declare the
  version, and unsupported versions fail before compute.
- Deterministic, fail-closed CLI workflows for restatements, migration
  equivalence, requirement changes, contract evidence, federated rollups, and
  suppression-aware equity reviews, with typed relationships, receipt-composed
  derived figures, a versioned artifact schema, and passing/failing fixtures.
- `receipts verify-workflow` plus generated, drift-checked version-1.0
  compatibility fixtures for all six workflow artifact kinds.
- A byte-for-byte compatibility baseline from signed tag `v0.1.0`; current code
  loads its unversioned beta report spec and re-derives its version-1.0 receipt
  manifest in CI.
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
- The wave 3 adversarial fixture set for the federated rollup workflow in
  `tests/test_rollup_adversarial.py`: a forged bundle, a swapped narrative,
  incompatible definitions, periods and suppression policies, a suppressed
  partner cell, overlapping populations under both overlap declarations, and
  every ordering of three partners.

### Changed
- **Breaking (receipts manifest schema `1.0` → `2.0`).** Every receipt gains a
  required `suppressed` boolean, and `value`, `row_count`, `slice_hash`, and
  `column_names` widen to a union with `null`. A consumer that reads a numeric
  field without branching on `suppressed` now sees `null` where it used to see a
  `0` it had no way to question. `receipts verify` reads both versions and
  compares a `1.0` manifest against that manifest's own rendering, so the frozen
  `v0.1.0` baseline still re-derives; nothing writes `1.0` any more. The
  deterministic field mapping is in
  [`docs/SPEC-STABILITY.md`](docs/SPEC-STABILITY.md). The workflow-artifact
  schema version is unchanged at `1.0`: its envelope did not change, only the
  receipts it embeds, which are governed by the manifest contract.
- The release workflow now follows the portfolio trusted-main shape: it is
  dispatched from `main` with the signed tag as an input and delegates the
  trust step to the standards-owned reusable `release-authorize` workflow
  (pinned by full commit SHA), which verifies the annotated tag's SSH signer
  against the new committed `.github/allowed_signers` file and proves the
  tagged commit is reachable from `origin/main`. GitHub release publication
  moved into a checkout-free `contents: write` job that re-compares the live
  tag object against the authorizer's immutable identifier immediately before
  publishing, the PyPI job performs the same recheck, and the release notes
  are now the tag's own CHANGELOG section rather than generated notes. The
  build, Sigstore attestation, SBOM, artifact hand-off, and post-publication
  verification stages are unchanged.
- Every SHA-pinned Action comment now names the exact release the SHA
  resolves to (`# vX.Y.Z`), replacing the imprecise `# v4` and `# v6` labels.
- Reviewer-facing English and Spanish copy now ships as compiled gettext
  catalogs with extraction, compilation, BCP 47, key, and placeholder gates.
  The trace view is fully localized instead of always rendering English.
- `make verify` now reproduces the complete applicable AUTO-GATE set used by CI,
  including security, i18n, accessibility, generated cards, and eval drift.
- The active main ruleset now requires pull requests, signed linear history,
  resolved threads, strict checks, and no bypass actors. The zero approval count
  is an explicit solo-maintainer ADR, not a silent missing rule.

### Fixed
- Every gate now runs on every commit. `make verify` and `make security` were
  prerequisite lists and single recipes, and make stops both at the first
  failure. An unpatched HIGH advisory in the npm accessibility toolchain
  (GHSA-jmr9-qjv8-65gv in `extract-zip`, no fixed release) failed the second
  line of `security`, so OSV-Scanner, gitleaks, Semgrep and zizmor never ran —
  and because `verify` stopped at `security`, neither did `cards`,
  `eval-check`, or `compat`. Six gates silently stopped executing, for weeks,
  while the jobs reported red for a reason that had nothing to do with them.
  Each scanner is now its own target, `scripts/run_gates.sh` runs every gate in
  a set and reports each result, and any failure still fails the job.
- The one advisory behind that is recorded in `waivers.yml` as WVR-007, with
  the package and version, the full dependency path, an owner, and a
  2026-11-15 expiry. `scripts/check_npm_audit.py` matches it on advisory id,
  package, and severity together, so a new advisory, a second advisory in
  `extract-zip`, or the same advisory escalated in severity all still fail;
  `tests/test_npm_audit_gate.py` pins that boundary.
- `receipts migrate-check` aborted on any suppressed metric, so it failed on all
  four shipped example specs compared against themselves. `build_migration_check`
  composed a delta receipt for every metric unconditionally and `_composed_receipt`
  refuses a suppressed input, so one small cell anywhere in a spec reported
  nothing about the metrics that could have been compared — and any real
  human-services export has one. A metric withheld on either side is now
  classified `indeterminate` with `delta_status: "suppressed"` and no delta
  receipt, matching `contract-check`'s vocabulary and the sibling `restate`
  workflow. `receipts verify-workflow` gained a check that a metric carries a
  delta receipt exactly when its status says it can. The status vocabulary is
  published in `docs/schema/workflow-artifact.schema.json`, described in
  `docs/NOVEL-USE-CASES.md` UC-2 (which promised a third status the code never
  produced), and pinned by a test that fails if the three disagree.
  ([#79](https://github.com/ChelseaKR/outcome-receipts/issues/79))
- The grounding gate's canonicalization was lossy in exactly the shape where
  losing information is worst: `1.234` and `1,234` reduced to the same token, so
  a narrative could state a number a thousand times its receipt, or a thousandth
  of it, and bind. `ground("Our cost per outcome ratio is 1.234 …", [count
  1,234])` returned `ok=True`. Every unit was exposed — any count in the
  1,000–999,999 range, and any `rate`, `duration`, `money`, or `percent` with
  three decimals. Canonicalization now preserves magnitude: a figure display is
  read by the one rule the engine writes it with, and a prose span in the
  ambiguous shape (one separator, 1–3 digits then exactly 3) binds only a
  display it matches character for character. Every other shape still binds
  across conventions. `eval/grounding-benchmark.jsonl` gains a formatting family
  covering separators in both conventions, NBSP grouping, percent, currency,
  unit suffixes, and the ambiguous shape, with the Spanish half written in
  Spanish number convention; the previous 100 cases were bare integers and could
  not fail for any locale-related reason. Recorded in
  [ADR 0011](docs/decisions/0011-canonicalization-preserves-magnitude.md), which
  amends ADR 0007.
  ([#80](https://github.com/ChelseaKR/outcome-receipts/issues/80))
- Charts drew a suppressed cell as a zero. A bar rendered `height="0.0"` on the
  axis baseline, geometry identical to a figure that is genuinely zero; a line
  chart put the point on the axis floor and ran the polyline straight through
  it, inventing a collapse and a recovery across data withheld on purpose; and
  `_scale_max` let the hidden cell scale the bars that were drawn, as a zero.
  `Figure.value` is now `None` for a withheld figure, a withheld bar is a
  hatched dashed full-height slot in the axis grey, a line breaks rather than
  interpolating, and withheld figures take no part in the axis scale. The
  absence is announced as well as drawn, in the marker's `<title>` and the
  chart's `<desc>`. The end-to-end artifact search now covers the chart SVGs,
  closing the gap ADR 0004's consequences left. Recorded in
  [ADR 0010](docs/decisions/0010-withheld-cells-are-drawn-as-an-absence.md).
  ([#78](https://github.com/ChelseaKR/outcome-receipts/issues/78))
- A suppressed cell serialised as a zero. `_redact` wrote `value: 0.0`,
  `row_count: 0`, and the all-zero slice-hash sentinel — byte-identical, in
  every field the manifest schema constrains, to a figure that is genuinely
  zero. The prose said `[SUPPRESSED]`; the numbers said nobody, and every
  machine consumer (`receipts.json`, the trace view's Rows column, the report's
  receipts appendix, the six evidence workflows) read the numbers. A withheld
  receipt now carries `suppressed: true` with `null` for `value`, `row_count`,
  `slice_hash`, and `column_names`, so a consumer that sums or plots the field
  fails loudly instead of silently counting a protected group as zero. The
  report appendix and trace view render `[SUPPRESSED]` in place of the row count
  and slice hash. An equity review containing a withheld group now states
  suppression in its `interpretation_limits`, and `receipts verify-workflow`
  fails an artifact whose withheld receipt still carries a number, or whose
  equity review withholds a group without saying so. Recorded in
  [ADR 0009](docs/decisions/0009-withheld-cells-are-null-not-zero.md).
  ([#77](https://github.com/ChelseaKR/outcome-receipts/issues/77))
- `suppress_figures` now refuses an already-redacted figure set instead of
  reading a redacted `value` as a true zero and reporting the cell as
  unsuppressed — a false all-clear on the invariant it exists to assert.
- That waiver is now retired, because the advisory turned out to be removable
  rather than unfixable. `@puppeteer/browsers` 2.x unpacked the downloaded
  Chrome build with `extract-zip`, which has no patched release; 3.x does not
  depend on it at all. An `overrides` entry pinning `@puppeteer/browsers` to
  `^3.0.2` — the same mechanism already used for `inquirer`, `tmp`, and `uuid`
  — takes the vulnerable package out of the dependency graph entirely.
  `extract-zip` no longer appears anywhere in `package-lock.json`, `npm audit`
  reports zero vulnerabilities, and WVR-007 is deleted rather than left to
  outlive the finding it described. No gate was loosened, no ignore file added,
  and no VEX statement was needed. The npm-audit gate's accept-and-refuse
  boundary is still fully tested, now against a fixture registry, so the
  mechanism does not go untested just because nothing is currently waived.
- `receipts audit` grounded a narrative against the **unsuppressed** figures, so
  a draft stating the protected small cells bound every one of them and exited
  `0` — the command the README offers for checking a hand-written draft
  certified a disclosure. `audit` now grounds against the publishable
  (post-suppression) figure set, computed over the whole report rather than the
  narrative metrics alone, and reports a span that states a redacted figure as
  its own category, naming the metric it discloses instead of calling it
  "unbound". `--json` gains a `suppressed` array distinct from `unbound`. A
  number that is simultaneously a published figure and a protected cell's raw
  value is reported as a disclosure and flagged `ambiguous`, not silently
  resolved to the convenient reading. `receipts eval` likewise drafts and scores
  the exported narrative rather than a pre-suppression draft the pipeline never
  produces; `eval/report.md` now states which figure set it scored.
  ([#76](https://github.com/ChelseaKR/outcome-receipts/issues/76))
- The comparison and reconciliation tables' `direction`/`arrow` no longer
  survive redaction when the row's own figures do not. `direction` is a word
  computed from the sign of the raw delta, not a `Figure`, so
  `suppress_figures`'s figure-only search never saw it and `redact_comparison`
  only rebuilt `prior`/`current`/`delta`; a fully suppressed row could still
  print a real "no change" (an exact equality claim about two hidden numbers)
  or a real "increase"/"decrease" beside three `[SUPPRESSED]` cells.
  `redact_comparison` and `redact_reconciliation` now redact a row's direction
  to the same `[SUPPRESSED]` sentinel whenever any of its three figures was
  actually redacted. ADR
  [`docs/decisions/0008-non-figure-presentation-fields-are-in-scope.md`](docs/decisions/0008-non-figure-presentation-fields-are-in-scope.md)
  records the decision.
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
- `receipts rollup` no longer accepts a plan that declares partner populations
  `disjoint` when the partner receipts contradict that declaration or cannot
  support it. Two receipts carrying the same non-empty slice hash counted the
  same rows, so the combined figure overstated the people served while the
  artifact claimed no overlap. A receipt reporting a non-zero count over an
  empty data slice publishes the sentinel hash every empty slice shares, which
  can be compared against no one, so it is refused rather than exempted. The
  lead agency reaches both conclusions from the hashes partners already publish,
  without holding a client row. Two partners both reporting a true zero are
  still not a collision, and a plan labeled `not_deduplicated` keeps its
  operator-supplied label. When one partner submits two bundles carrying the
  same rows, the error identifies each submission by its bundle digest. ADR
  [`docs/adr/0004-fail-closed-disjoint-rollup-slice-check.md`](docs/adr/0004-fail-closed-disjoint-rollup-slice-check.md)
  records the decision and its residual risk.

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

- **SAST (2026-07-10, SEC-07).** `ci.yml`'s `security` job gains a Semgrep step
  (`p/default` + `p/python`, pinned scanner version, `--severity ERROR --error`)
  that blocks the build on any ERROR-severity finding. The two findings it
  surfaced on first run (`sqlalchemy-execute-raw-query` on the same
  already-triaged `load_table` identifiers the `S608` waiver below covers) are
  suppressed with inline `# nosemgrep:` comments tracked in the new
  `.semgrep-waivers.yml` ledger, per SEC-10 waiver hygiene.

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
- Two `S608` ruff findings in `comparison.py` and `engine.py` triaged as false
  positives (spec SQL and internal table/column identifiers are author-trusted,
  not user-supplied, per `SECURITY.md`'s Scope section) and suppressed per-line
  with justification; `S101` (assert) is ignored under `tests/*` only, since
  pytest's own idiom relies on it.
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

[Unreleased]: https://github.com/ChelseaKR/outcome-receipts/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/ChelseaKR/outcome-receipts/releases/tag/v0.1.0
