# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project aims
for [Semantic Versioning](https://semver.org/spec/v2.0.0.html) from 1.0.

Version `0.1.0` is the first beta release. It includes the deterministic core
and the privacy, verification, mapping, localization, optional drafting, and
release-hardening work completed before the first public tag.

## [Unreleased]

### Fixed
- **The release checklist named three of the six files that carry the version,
  and the three it omitted are the ones that drifted.** `docs/RELEASING.md`
  step 1 read *"Update `pyproject.toml`, `CHANGELOG.md`, and generated
  cards … in one pull request"*, so `uv.lock`, `CITATION.cff` and the README
  status note were carried by memory. The promotion to `0.2.1` moved
  `CHANGELOG.md` alone and the rest sat at `0.2.0` behind a green gate set.
  The step now names every one of them and what moves in each, says which are
  machine-checked (`make release-version`, and `uv lock --check` inside `make
  install`) and which are still read by a person, and records that
  `action.yml`'s `version` default moves *after* publication rather than with
  the bump, because it names a tag a consumer can install and that is not true
  until the release exists.
- **Nothing compared the version the release would publish against the tag it
  would publish it under, and the two had already drifted.** `main` carried a
  dated `## [0.2.1] - 2026-09-07` CHANGELOG section and a signed `v0.2.1` tag
  while `pyproject.toml` still read `version = "0.2.0"`: the release-prep
  commit for `v0.2.0` moved the CHANGELOG *and* bumped every place carrying the
  version together, and the promotion to `0.2.1` did only the first half.
  `make verify` was green, `ci` was green, and `release.yml`'s one version
  check — that `CHANGELOG.md` contains a section for the tag — was satisfied by
  that tree.

  What a `v0.2.1` dispatch would have done: `uv build` reads `pyproject.toml`,
  so `build` produces a `0.2.0` wheel, Sigstore attests those bytes, the
  GitHub release for `v0.2.1` publishes them, and `pypi-publish` uploads them —
  which PyPI accepts, because it has never seen `0.2.0` and this is a first
  upload. The first job that would notice is `verify-published`, which runs
  `uvx --from "outcome-receipts==0.2.1"` *after* the upload, against a version
  the index does not have and now never can, because the filename is spent.
  The gate that would have caught it ran after the irreversible step.

  `scripts/check_release_version.py` makes the comparison before the first one:
  `pyproject.toml`, `CITATION.cff` and `CHANGELOG.md`'s newest dated section
  must agree, `CITATION.cff`'s `date-released` must be that section's date, and
  with `--tag` the tag must name what the tree declares. An unreadable
  declaration — no `project.version`, no dated section, `## [0.2.1]` with the
  date dropped — is unmeasurable and fails; a malformed newest heading is not
  skipped in favour of the release below it, which would report agreement
  reached by ignoring the release under test. It runs as its own `make` gate
  rather than a fourth line of `hygiene`, so a source-hygiene failure cannot
  take it down with it, and again in `release.yml` with the tag.

  `pyproject.toml`, `uv.lock` and `CITATION.cff` are moved to `0.2.1` here, so
  the tree the gate now guards is one it passes, and the README status note —
  which said `v0.2.0` was "the current tagged release" after `v0.2.1` was
  tagged — now separates what this tree declares from what anyone can actually
  obtain.
- **A `Last verified:` stamp dated in the future satisfied the staleness gate
  permanently, and a date-shaped stamp that is not a date took the whole
  conformance run down with it.** `doc_staleness_failures` compared
  `(today - verified).days` against the cadence and failed only when the age
  was *greater*. A stamp dated tomorrow gives a negative age, so it passed —
  and went on passing every day after that, forever. That is the one edit that
  most obviously fakes currency, and it was the one edit the gate could never
  report. An age check needs three outcomes, not two: fresh, stale, and
  unmeasurable; a future date is not fresh data, it is a wrong clock or a wrong
  entry.

  `LAST_VERIFIED_RE` also matches a date *shape*, not a date. `2026-13-40`
  satisfies `\d{4}-\d{2}-\d{2}` and raised `ValueError` out of
  `date.fromisoformat`, aborting the entire conformance run on a traceback that
  named neither the file nor the stamp — so one typo in one footer suppressed
  every other conformance failure in the same run, including real ones in
  documents later in the walk. Both now fail closed, per document, naming the
  file and the stamp, and the scan continues past them.

  This repository had already found and fixed this exact class once, in the
  BASELINE graduation check recorded in `docs/PR-TRIAGE.md` (*"a date-shaped
  string that is not a date (`2026-13-40`) parsed as 'a date is present' and
  passed. It now fails closed."*). This is the same defect in the second
  checker. No document in the tree is currently in either state; every stamp is
  a well-formed past date, so this changes no current verdict.

## [0.2.1] - 2026-09-07

### Added
- **Nothing bound a requirement set to an export, so a spec that omitted a
  required metric ran, grounded, was approved, and exported a report that was
  fully receipted and silently incomplete.** `map` returned per-requirement
  candidates that could come back `blocked`, `requirements-diff` compared two
  requirement documents by stable id, and `contract-check` refused a milestone
  whose metric was absent — and none of them looked at what an export actually
  published. A requirement nobody could answer and a requirement nobody was
  asked about rendered identically, as nothing on the page, which is the error
  ADR 0009 already refuses one level down inside a figure.
  A spec may now declare `[requirements] path = "..."` and each metric a
  `requirement_id`. Export accounts for every requirement in the bound document
  as `answered`, `withheld` (a suppressed cell — answered, and reading as
  unanswered nowhere), or `unanswerable`; anything else refuses the export,
  writes nothing, and names the requirement, on the new exit code **4**.
  An `unanswerable` declaration carries **both** the machine-readable blocker
  and a human-authored reason, and neither is sufficient: the blocker is
  re-derived at export by running `mapping.build_mapping_queue` over the same
  data and document, so a blocker the mapper does not produce is refused with
  what the mapper did say, and a requirement that maps cleanly cannot be
  declared unanswerable at all.
  The coverage table renders in the report appendix in EN and ES, the
  requirement document's sha256 rides in `receipts.json`, and `verify --bundle`
  re-derives both — an edited requirement document fails naming the digest, and
  a doctored coverage record fails as a mismatch against what the spec and data
  produce. A spec with no binding is unchanged in every byte: its manifest
  carries no `requirements` key at all, and `verify --bundle` reports
  `not checked` rather than `ok`.
  `examples/requirement-coverage/` demonstrates all three exportable states.
  See [ADR 0013](docs/decisions/0013-requirement-coverage-is-proven-at-export.md)
  and `docs/SPEC-STABILITY.md`.

- The comparative-claim gate. `grounding` finds numbers, so a sentence carrying no
  numeral was invisible to it and "placements rose this quarter" blocked nothing. The
  drafter was forbidden to invent a digit and not forbidden to invent a direction.
  A closed, bilingual vocabulary of comparative and quantifying forms is now detected
  in the drafted narrative, and each claim must bind to a receipted comparison
  direction or it refuses export exactly as an unbound number does. A claim every
  declared comparison contradicts is named alongside what the receipts actually say.
  A claim that agrees only with a comparison suppression withheld is reported as a
  disclosure rather than as unbound, because the remedies differ: that one is the #75
  leak arriving through prose instead of through the table.
  Four kinds are detected and can never bind, which is the `_NUMBER_WORD` precedent
  and not an omission. An evaluative word ("improved") asserts a direction whose sign
  depends on a metric polarity no spec declares. A magnitude word ("doubled") asserts
  a ratio, and `compute_reconciliation` deliberately computes no ratios. A quantifier
  ("most") asserts a share of a whole no figure states. A superlative ("highest")
  asserts a rank over a set the gate does not model. Each is reported with the reason
  it cannot be checked rather than passed in silence.
  The gate is scoped to the drafted narrative, which is the surface a model writes;
  an author's metric caveat is not drafted and is not gated. `receipts run`,
  `receipts audit` and the MCP `audit_narrative` tool answer from the same
  computation and emit the same payload. ADR 0012 records the decision, including
  what it deliberately leaves open.
  Measured while building it: every comparison row in the committed grant-report
  example is withheld, so its direction column already renders as the suppression
  sentinel while a sentence could have stated the direction anyway.
  A narrative containing no vocabulary entry gates exactly as before.
- The refusal half of the release-compatibility evidence, which the matrix in
  `docs/SPEC-STABILITY.md` had only the accepting half of. Every row read PASS: a
  released spec loads, a released manifest re-derives. None of them could
  distinguish a discriminating verifier from one that accepts anything, and a
  verifier that accepts anything accepts a released artifact too, so those rows
  were carrying less weight than they appeared to. `tests/test_release_compatibility.py`
  now exercises the same frozen artifacts with one field changed and asserts that
  each refusal is *attributable*: a `v0.1.0` manifest relabelled to a manifest
  major nothing implements fails on `schema_version` while all four of its
  receipts still re-derive, so the refusal is the declared version and not the
  data; a `v0.1.0` manifest with one figure edited by hand — one client added to a
  count, small enough to be plausible — fails as drift on that metric by name; and
  a `v0.2.0` spec relabelled to a report-spec major nothing implements is refused
  before any figure is computed, with the error naming both the version it was
  handed and the one this package implements, and with the `--out` directory left
  empty. The last of those is asserted by pointing the relabelled spec's
  `[data] path` at a CSV that does not exist: if the version check ever moved to
  after the read, the missing file would raise first and the test would say so
  rather than passing for the wrong reason. Three rows added to the compatibility
  matrix. This closes issue 65's third and fourth acceptance criteria, which asked
  for exactly these cases; what it does not do is manufacture the cross-release
  evidence the issue's title asks for, which still needs a release that moves a
  contract.
- A second release baseline, `tests/fixtures/compat/v0.2.0/`, and the honest
  reading of what it does and does not prove. `docs/SPEC-STABILITY.md` said
  cross-release execution evidence "begins with the next two tags"; both of those
  tags have since shipped, so the sentence was describing a state the repository
  had already left. `v0.2.0`'s spec, data and manifest are now frozen byte for
  byte beside `v0.1.0`'s, and `tests/test_release_compatibility.py` re-derives the
  second tag's manifest with current code as it already did for the first.
  What that establishes is narrower than a green row implies, and the matrix now
  says so rather than counting it twice: `v0.2.0`'s `services.csv` and
  `receipts.json` are **byte-identical** to `v0.1.0`'s, so the second released
  implementation produced exactly the artifact the first one did. The only thing
  that moved between them is that `v0.2.0`'s spec declares
  `schema_version = "1.0"` where `v0.1.0`'s carried no key and was read as `1.0`
  by default — a real property, pinned by a new test, and not the same thing as a
  contract surviving a release boundary. Issue 65's remaining criteria need a
  release that actually moves a contract, and reading two identical artifacts as
  a compatibility result would be this repository's own dominant defect turned on
  its own evidence.
- A clock on the Semgrep waiver reviews. Issues 52 and 53 are the audit owners
  CQ-35 and SEC-10 require, and both commit to reviewing their waiver
  *quarterly*. `last_reviewed` was validated as an ISO date and then never read
  again, so that commitment was a sentence in two issue bodies with nothing
  behind it: a waiver reviewed once in July passed identically forever, and the
  issues could stay open indefinitely with no gate able to say the promise in
  them had lapsed. `scripts/check_semgrep_waivers.py` now fails when a row's
  review is more than 92 days old — the same span `check_conformance`'s
  `CADENCE_DAYS` maps "quarter" to, so a quarter means one thing in both gates —
  and the message names the tracking issue that owns the re-review rather than
  only the rule. Two adjacent holes closed with it: a `last_reviewed` in the
  *future* is refused, because a date ahead of today can never lapse and would
  buy a row unlimited green; and the review date must also appear in
  `docs/RESPONSIBLE-TECH-AUDITS.md`, which issue 52's acceptance criteria name
  as the second record and which nothing compared against the first, so one
  could be updated and the other forgotten. A missing audits document is
  reported as the second record being unreadable, once, rather than as every row
  disagreeing with it. Proven against the real ledger with its dates aged to
  2024-01-01: the previous check exited 0, this one exits 1 with both rows
  overdue by 882 days. Eight tests in `tests/test_semgrep_ledger.py`, one of
  which runs the committed ledger past its own quarter so "the cadence is
  enforced" is a claim about the document and not about a fixture. A green run
  now prints the date the next review is due (2026-11-28), so it says when it
  stops being green instead of implying it never will.
- The Performance standard's artifacts, closing the open gap the README
  declared. `perf/baseline.json` is the committed comparand the standard's
  10%-regression rule needs, with `meta` provenance, an explicit `null` for
  every metric this project has no route to measure, and a per-metric direction
  so the comparison is mechanical. `perf/README.md` records the budgets and
  which controls apply: k6 latency is declared N/A with its reason, there being
  no hosted route and no preview environment, rather than skipped. The single
  `lighthouserc.cjs` now asserts `categories:performance` at 0.9 alongside the
  accessibility score, and a script-transfer budget of zero bytes on the
  generated trace, which is tighter than the standard's 204,800 on purpose: the
  trace is a static document a funder opens, the project ships no web
  application, and at 204,800 the assertion could not fail until 200 KB of
  JavaScript had already reached a funder's browser. `scripts/check_perf_baseline.py`
  (`make perf`, wired into `make verify` after `a11y`) is the regression half.
  It reads the report `a11y` produced rather than measuring twice, because the
  standard requires one Lighthouse config per repository, and it refuses a
  report older than the trace it would be scored against, or no report at all,
  so a failed Lighthouse run cannot leave a stale green behind it. Proven able
  to fail against the real toolchain: a 1 KB script injected into
  `out/a11y/trace.html` takes the measurement to 0.411 KB and fails both the
  Lighthouse assertion and the baseline check. Twelve tests in
  `tests/test_perf_baseline.py`.
- `verify-ledger` blind-spot tests on hand-tampered fixtures: entries deleted
  from the tail verify clean, and a wholesale rewrite with recomputed hashes
  verifies clean. Both are documented limits of a keyless hash chain; the tests
  keep the documentation honest in both directions. Middle-entry deletion and
  reordering, which the chain does detect, are now pinned too.
- `scripts/check_semgrep_waivers.py`, run by `make hygiene`: `.semgrep-waivers.yml`
  is now compared against the tree in both directions. Its header had asserted
  since July that every entry there must have a matching inline suppression in
  the code, and nothing checked it, so a row could outlive the suppression it
  documented and an undocumented suppression could be added with every gate
  still green. Both states were reproduced against the real repository, and in
  both of them `check_source_hygiene.py` and `check_conformance.py` exited 0.
  Python files are read through `tokenize`, so a directive quoted in a docstring
  or a test fixture is not counted as a live suppression.
  `tests/test_semgrep_ledger.py` covers a row with no suppression behind it, a
  suppression with no row in front of it, a row naming a file that does not
  carry it, an unqualified suppression, a missing field, an unparseable date,
  and a missing ledger.
- `src/outcome_receipts/py.typed`. Without the PEP 561 marker, every annotation
  the package ships is discarded by a downstream type checker, and by this
  repository's own `scripts/`, where mypy reported `module is installed, but
  missing library stubs or py.typed marker` for all three modules that import
  `outcome_receipts`. `tests/test_public_api.py` looks for the marker beside the
  imported package, so an install that drops it fails as well.
- `tests/test_source_hygiene.py`. `scripts/check_source_hygiene.py` had run on
  every commit with no test of its own, so nothing distinguished "reported
  nothing because the repository is clean" from "reported nothing because it
  stopped looking".
- `tests/test_gate_scope.py`, which fails if `make lint` or `make type` is
  narrowed back to a scope that skips `scripts/`.
- The AI-Development Measurement standard's scope declaration and the graduation
  dates its BASELINE state requires, closing the second open gap the README
  declared. `docs/ROADMAP.md` gains the `AI-DEV-MEASUREMENT: APPLIES` ledger
  line the standard asks every repository for, and the DORA and quality-debt
  numbers move from a prose paragraph into dated rows so each names the date its
  graduation decision is due (2026-10-11, one quarter from the 2026-07-11
  collection). A metric may not sit in BASELINE indefinitely; a row with no date
  is a metric nobody has committed to ever decide about, which the standard
  treats exactly as an aspirational one. The unreviewed-merge row records that
  its decision collides with ADR 0002, which holds required approving reviews at
  zero while there is one maintainer, so gating on it needs a superseding ADR
  rather than a quiet threshold change. `scripts/check_conformance.py` gains
  `ai_dev_measurement_failures`, wired into `make hygiene`, which fails when the
  scope line is absent, when any BASELINE row's gate cell names no date, when
  that date is unreadable, and when it has passed. The last two conditions are
  the check itself: the date is read out of the gate cell and not out of the
  row, because every row in this ledger also states when its number was
  measured, so a row-wide search reports a graduation date on a row that names
  none; and the date is compared against today, because asking only whether a
  date is *present* turns every dated row permanently green the day after the
  date it prints, which is the metric parked in BASELINE indefinitely that the
  undated arm's own failure message says must not be possible. Two artifacts
  the standard also asks for are named as outstanding rather than claimed: the
  weekly rollup, which is produced at the portfolio level rather than here, and
  the quarterly seven-capability self-assessment, which is the maintainer
  answering about her own practice. Regression tests: nine in
  `tests/test_conformance.py`, including
  `::test_ai_dev_measurement_is_silent_against_the_real_committed_roadmap` and
  `::test_every_baseline_row_in_the_real_roadmap_will_fail_once_its_date_passes`,
  which reads the real ledger on 2026-10-12 so "this gate can fail" is a claim
  about the document rather than about a fixture.
- Issue 94: the first real, non-synthetic run of the small-cell suppression
  engine, over HUD's own published 2024 CoC Point-in-Time subpopulation
  counts (363 CoCs, 10,890 real cells; `eval/hud/`). No HUD-published
  numeric small-cell rule exists to validate the shipped CMS-modeled default
  (threshold 11) against -- confirming a gap `docs/ROADMAP.md` already
  named -- but applied to subpopulation-shaped data, the default withholds a
  majority of granular cells (60.7%, vs. ~1% for whole-CoC totals) and
  complementary suppression is empirically necessary on 95% of CoCs, not a
  theoretical edge case. Findings, data card, and a test that recomputes
  every headline number from the committed extract:
  `docs/audits/hud-coc-suppression-calibration-2026-08-21.md`,
  `docs/data/hud-coc-pit-subpopulations.md`,
  `tests/test_hud_suppression_calibration.py`.

### Changed
- The Lighthouse performance score is no longer a merge gate; the bytes it is a
  proxy for are. `categories:performance` is a simulated-throttling timing score
  of whatever machine ran Lighthouse, and both halves of the old gate — the 0.90
  floor in `lighthouserc.cjs` and the 10% band around a 1.00 baseline, which also
  lands on 0.90 — sat inside the runner's observed spread, so `main` and four
  pull requests went red for a reason no diff had caused and no diff could fix.
  What is scored in its place is what the artifact *is*: `total_kb_gzip`
  (2469 transferred bytes), the script/stylesheet/third-party budgets, and a new
  `<script>`-element count in `scripts/a11y.mjs`. That last one closed a real
  hole rather than merely replacing coverage: `resource-summary:script:size`
  budgets script *requests*, so 1216 bytes of inline JavaScript injected into the
  trace left it reading 0 and moved the compressed document by 26 bytes, passing
  both the old Lighthouse assertion and the 10% band. The score is still measured
  and printed every run, and its exclusion is declared in
  `check_perf_baseline.py`'s `OBSERVED_NOT_GATED` with its reason, so a reader
  can tell a number nobody scores from a number nobody noticed had stopped being
  scored. This changes a declared conformance position — PERF-02's floor — and
  `perf/README.md` records why. Shipped as #146; this entry is the changelog
  record it went in without.
- The container base image moves to the current `python:3.13-alpine` rebuild
  (`sha256:7415fbc3…`), which retires the CVE-2026-14456 workaround the
  Dockerfile had been carrying. That workaround pinned libcrypto3/libssl3
  3.5.8-r0 into the final stage and recorded its own exit condition: "Drop both
  pins, and this comment, once the base image itself ships 3.5.8-r0 or later."
  The rebuild does, so they are dropped. Leaving them would not have been free:
  a pinned `apk add` of an exact version fails the build the day Alpine v3.24
  main rotates that version out, which is useful as a reminder while the pin is
  load-bearing and is a scheduled outage once it is not. The libuuid 2.42.3-r1
  pin added on 2026-09-06 stays, and the reason it cannot be retired the same
  way is now recorded beside it: libuuid lives in the Alpine layer, and every
  `python:3.13-alpine` rebuild published so far shares that layer byte for byte
  (`sha256:55afa1ec…`, verified against the amd64 manifests of both the previous
  and the current digest), so no digest bump reaches it. The layer above it is
  the one a bump does reach, and that is where the openssl fix arrived. Verified
  with `make container-verify` on the rebuilt image: 0 findings in both the
  Alpine and python-pkg targets.
- `tests/test_conformance.py` no longer describes its frozen `controls.yml`
  snapshot as coming from "the version this repository pins in
  `.standards-version`". It does not. The pin is `v1.0.1`, and `controls.yml`
  did not exist at `v1.0.1`; it arrived with FIX-01 on 2026-07-11. The
  consequence is now stated where a reader meets the snapshot: the "portfolio
  standards" CI job checks the pinned ref out and runs
  `check_conformance.py --standards-dir .standards` against it, that checkout
  carries no `controls.yml`, and `standards_index` warns and falls back to the
  vendored literal. The job passes in a few seconds having compared the README
  against the same hardcoded list DOC-11 set out to stop trusting, so nothing is
  currently checking either copy against a live registry. The remedy is a
  `.standards-version` bump, which is a deliberate portfolio-pin decision with
  repository-wide scope and is not made here. `check_conformance.py` and its
  behavior are unchanged.
- `tests/test_conformance.py::test_the_standards_pin_is_named_the_same_way_in_all_three_places`
  pins the three places the standards version is written: `.standards-version`,
  the `ref:` the CI job checks the standards repository out at, and that job's
  own `test "$(cat .standards-version)" = "..."` line. Two of the three live in
  a workflow file no test read. Bumping `.standards-version` alone turns the job
  red on its assertion, which is loud; moving the `ref:` alone is the quiet one,
  and left the job checking out a version nobody declared while reporting green.
- The export ledger no longer claims to detect "any edit, insertion, deletion,
  or reordering". Deletion from the tail, a full rewrite with recomputed
  hashes, and an export never appended all leave no trace, and the module
  docstring, the ADR, and the README row now say so. `verify-ledger` prints
  the entry count and three "not proven" lines beside PASS, and its `--json`
  output carries `entries` and `not_proven`, so a clean chain can no longer
  read as proof of completeness or authorship. `verify-ledger` also now fails
  closed on a missing file: an absent ledger used to verify as an empty chain
  and report PASS, so a mistyped `--ledger` path was a green check that had
  read nothing.
- `.semgrep-waivers.yml`: both waivers re-reviewed on 2026-08-28 by deleting
  each suppression and re-running the pinned scanner against the file. Both
  rules still fire, so neither waiver can be retired and issue 53 stays open.
  The `sqlalchemy-execute-raw-query` entry also now records
  `python.lang.security.audit.formatted-sql-query`, which fires on the same line
  at WARNING severity and so sits outside the ERROR floor
  `make security-semgrep` blocks on.
- Every `uv sync --frozen` is now `uv sync --locked`: the `make install` step,
  the Dockerfile's builder stage, and the setup commands in `README.md`,
  `AGENTS.md`, and `docs/drafting.md`. `uv lock --check` was already the drift
  gate in `make install` and still runs first, but the sync itself could pass
  on a stale lock whenever it was invoked outside that target, and the image
  build had no drift check at all. `test_container_contract.py` now asserts
  `--locked` and asserts `--frozen` is absent from the Dockerfile.
- The README standards-conformance table declares Performance and AI
  Development Measurement. Both were missing from the table entirely, so
  neither was recorded as met, as exempt, or as a gap. Both are declared as
  applying with no committed artifact yet, which is an open gap.
- `scripts/check_conformance.py` no longer validates the README's
  standards-conformance table against a hardcoded literal that duplicated
  the table it was checking (DOC-11): given `--standards-dir`, it now derives
  the required-standards list from that checkout's `controls.yml` and fails
  loudly if the checkout is missing, rather than silently trusting its own
  copy. The "portfolio standards" CI job now passes `--standards-dir
  .standards`. Two row names move to match the pinned index's actual
  titles, which the table's own gate had never been able to check against:
  "Internationalization" becomes "Internationalization & Localization", and
  "AI Development Measurement" becomes "AI-Development Measurement".
  `make verify` keeps a vendored fallback list so the gate stays
  self-contained without the private standards checkout.
- All fourteen of this repository's `Last verified:` currency stamps used a
  `Recheck:` label the portfolio staleness parser's `Recheck cadence:` regex
  cannot match (DOC-15), so every one silently fell through to that parser's
  180-day default in any tooling that looked. Relabeled to the literal the
  parser expects; eight cadences that named only an event trigger ("after
  any incident", "on any HTML change") gained an explicit "and at least
  quarterly" day-based backstop, since a pure event trigger has no ceiling a
  mechanical check can enforce. `scripts/check_conformance.py` gains
  `doc_staleness_failures`, wired into `make hygiene`: it runs the same
  cadence math as the portfolio's own `check_staleness.py` against this
  repository's own docs (which nothing checked before -- the portfolio
  parser only scans the vendored `.standards` checkout), but fails closed on
  an unparseable cadence instead of defaulting to 180 days.
- `docs/a11y/ACR.md` and `docs/data/synthetic-fixtures.md` were re-verified
  against the current trace/chart markup and the current eval/compat fixture
  set (both were overdue against their own stated triggers) and re-stamped;
  no substantive claim in either needed to change.
- `tests/test_release_workflow.py` pins the release workflow's split-authority
  shape (dispatch-only trigger, least-privilege default token, `authorize`
  pinned to the reusable release-authorize workflow by a full commit SHA,
  exactly one `contents: write` job that never checks out code, `pypi-publish`
  re-comparing the live tag object before publishing) after nothing asserted
  it and a draft PR that once did (#66) was superseded without carrying the
  test over. `docs/RELEASING.md` documents the maintainer release procedure
  for the first time; `.github/allowed_signers` gained a comment header
  recording its key fingerprint.
- `scripts/check_conformance.py`'s `waiver_failures` no longer misreads a
  folded `reason: >-` block scalar as the non-empty string `">-"` -- every
  entry in the live registry folds its reason, so "missing or empty reason"
  was unenforceable against any of them. Also now rejects an unregistered
  waiver `kind`, a malformed `WVR-NNN` id, and (given `--standards-dir`) a
  `control` ID absent from the pinned `controls.yml`. `security_declaration_failures`
  cross-checks `docs/RESPONSIBLE-TECH-AUDITS.md` §F's VEX line against
  `waivers.yml`, so a live dependency-advisory waiver and an "N/A" VEX
  declaration can no longer silently coexist the way they did for about
  seven hours around 2026-08-15.
- SEC-38: re-ran the Scorecard measurement (`docs/audits/openssf-scorecard-2026-08-21.md`,
  aggregate 7.1, up from 6.8 on 2026-07-12 -- entirely from SAST, which the
  July report could not measure yet). WVR-006 is re-justified against the
  fresh number and its expiry is shortened, not extended, to 2026-09-25 (when
  the Maintained-score's under-90-days premise stops applying) instead of the
  original 2026-10-15. The `scorecard` workflow's enforced floor ratchets
  from `>= 6.8` to `>= 7.0`.

### Fixed
- `receipts verify` reported more receipts re-derived than the manifest contained,
  and blamed the data when the manifest's declared version was the only thing
  wrong. `schema_version` and `hash` are descriptors of the manifest document —
  compared against a constant, re-derived from nothing — but they were built as
  the same `Check` type as a receipt and counted alongside them, with `metric_id`
  as their only label. So the housing demo's **four**-receipt manifest printed
  `receipts checked: 6 (re-derived 6, drift 0)`, the `--json` payload's `n_ok`
  and `drift` carried the same inflation, and a manifest relabelled to a schema
  major nothing implements failed with `verify: FAIL — a receipt does not match
  the data` and `drift 1` while every one of its receipts re-derived cleanly.
  In a repository whose premise is that every reported number carries a receipt,
  the count of re-derived receipts was a reported number that did not.
  `Check` now records a `kind` of `receipt` or `manifest`; the human output
  reports the two counts on separate lines, each naming what it counted; the FAIL
  headline is built from the checks that actually failed and names them; and the
  `--json` payload gains `receipts_checked`, `receipts_ok`, `receipts_drift`,
  `manifest_checks`, `manifest_checks_failed`, and a `kind` on every entry in
  `checks`. `n_ok` and `drift` are unchanged and still span both kinds, so
  existing scripts keep working — they were never wrong as totals, only as the
  receipt counts they were printed as. `tests/test_verify.py` asserted
  `n_ok == len(figures) + 2`, which pinned the conflation as intended behaviour;
  it now also asserts the receipt-only counts against the manifest's own receipt
  list. Two docstrings corrected in the same pass, including `verify_manifest`'s
  claim that an unsupported schema fails "before any per-receipt re-derivation is
  attempted" — it does not, and reporting both is what makes a refusal
  attributable to the version rather than to the data.
- The `scorecard` job's three consecutive failures on `main` are two npm
  advisories no gate in this repository could see. `qs` 6.15.3 picked up
  GHSA-4mjr-xmp4-gh2g and GHSA-x5fp-wj9c-mxmx, both published 2026-09-02 at
  14:45 UTC — after the last green `scorecard` run on `main` that morning
  (04:32 UTC) and before the first red one on 2026-09-06. Nothing in the
  repository changed; the advisory database did, for the second time this week
  and in a second scanner. `scorecard.yml` asserts `Vulnerabilities == 10`,
  which counts OSV findings at every severity, while the two gates that run on
  a pull request cannot reach these: `npm audit`'s floor is HIGH and both are
  6.3 MEDIUM, and `security-osv` scans `uv.lock`, the Python half, only. So the
  finding could only ever surface after a merge, in a workflow that does not run
  on pull requests.
  `qs` arrives transitively through `express`/`body-parser` under `@lhci/cli` at
  `~6.15.1`, which cannot reach 6.16.0, so the fix is an `overrides` pin —
  `"qs": "6.16.0"` — beside the four already there. The lockfile change is three
  lines: one version, one `resolved`, one `integrity`.
  It took two attempts, and the first one is the part worth recording. Running
  `npm install` on the local toolchain (npm 11.19.0, Node 26.8.1) produced a
  lock that changed `qs` **and silently pruned 24 nested entries** under
  `puppeteer` and `puppeteer-core` — the proxy-agent chain. Local `npm ci` and a
  full `make a11y` both passed against it, so it looked correct; CI rejected it
  outright with `npm ci can only install packages when your package.json and
  package-lock.json are in sync`, naming every one of those 24 as `Missing … from
  lock file`. CI runs Node 22 with **npm 10.9.8**, and npm 10's resolver still
  requires what npm 11's prunes. Regenerating the lock inside a `node:22`
  container produced the three-line diff instead, npm 10 installs it, and npm 11
  installs it too — so the lock this repository commits has to be written by the
  npm that CI runs, not the one that happens to be on the machine. Verified:
  `npm ci` under both npm versions, `osv-scanner --lockfile package-lock.json`
  reporting no issues where it previously reported two, and the full local
  `make verify`.
- Issue 139, the environment half: `perf/baseline.json` and `perf/README.md`
  described a runner distribution tighter than the one that exists, and then
  described the replacement decision from three observations of it. Both now rest
  on the whole record. Every Lighthouse performance score this repository has
  logged between 2026-08-28, when the gate landed, and 2026-09-06 was read back
  out of the job logs — `make perf` prints one on every run, so the `verify` job
  is complete, and Lighthouse-CI prints one in the `accessibility` job only when
  it fails, so that job contributes its failures. Thirty-four observations, 0.77
  to 1.00 on byte-identical input: 26 at 1.00, three at 0.99, and one each at
  0.94, 0.89, 0.87, 0.81 and 0.77. Four are below the 0.90 floor and the same
  four are more than 10% below the baseline. Two of them were previously
  unrecorded here: the 0.81 and 0.77 came from the `accessibility` job, whose
  `verify` counterpart in the same run scored 1.00 both times — two audits of one
  artifact in one workflow run, 0.19 apart — and 0.89 was recorded on 2026-09-06
  on a pull request that touched only the `Dockerfile` and this file, with the
  next run of the same branch nine minutes later scoring 1.00. The scores
  themselves are unchanged, no assertion moves, and the earlier attempt of a
  re-run run is where three of the four failures live: `gh run view --log` serves
  only the latest attempt, so they are reachable at
  `/actions/runs/<id>/attempts/1/jobs` and nowhere else.
- The release workflow's five negative controls now fail as "the mutation did
  not apply" instead of as the property they were checking. Each builds its input
  by mutating the shipped `release.yml` text, which keeps the fixture anchored to
  what is actually deployed but makes every one a literal string match. Adding
  `timeout-minutes:` to the `verify` job in this same change broke one of those
  anchors: the anchor spanned `needs:`, `runs-on:` and `steps:` as one block, so
  `str.replace` returned the file unchanged and
  `test_widening_write_scope_onto_another_job_is_caught` reported
  `['github-release'] != ['github-release', 'verify']` — which reads as the
  permission checker having regressed, when in fact the sabotage never ran and
  the control proved nothing. A sabotage that silently no-ops is the failure mode
  a negative control exists to rule out, so `_assert_mutated` now asserts the
  mutation changed the text before the property is checked, on all five, and the
  broken anchor is narrowed to the job's `name:` line. Verified by renaming that
  line in `release.yml`: the guard fires with "the mutation did not apply: its
  anchor no longer matches .github/workflows/release.yml", and the file was
  restored.
- The three workflows #147 did not reach can still lose a commit its verdict, and
  two of them did, hours after #147 merged. A concurrency group holds one running
  run and one *pending* run, and a third run joining evicts the pending one before
  a single job dispatches: it ends `cancelled`, with no failure and no verdict.
  #147 keyed `ci.yml`'s group on the commit; `standards.yml`, `scorecard.yml` and
  `codeql.yml` were still keyed on `github.ref` alone. On 2026-09-06 two merges
  landed six seconds apart, `ci` kept both of its runs, and commit `abde41c` lost
  `portfolio standards` (run 34035866790) and `scorecard` (run 34035866788), each
  `cancelled` with zero jobs — and `portfolio standards conformance` is a
  *required* status check on `main`, so a required check has no result on that
  commit. `cancel-in-progress: false` is not protection: it governs the running
  run, and `scorecard.yml` had it set and was cancelled anyway. All three now use
  the same key `ci.yml` does. `codeql.yml` has never lost a run — §11e dropped its
  `push` trigger — and is changed for one idiom rather than two, which its comment
  says rather than implying a loss it did not have.
  `tests/test_workflow_concurrency.py` makes the rule mechanical: every workflow
  declaring a concurrency group must key non-pull-request events on the commit,
  `release.yml`'s single global group is a declared exemption with its reason
  rather than a file quietly not checked, and the count of workflows actually
  examined is asserted so the test cannot pass by finding none. Proven by
  reverting `scorecard.yml` to the ref-only key: the suite fails naming the file
  and the group.
- Issue 118: `receipts eval` now scores every narrative the run would export,
  and refuses to report a pass over nothing. It drafted through
  `draft(spec.report, ...)`, which fills only the legacy single
  `[report] template`. A spec that names funder formats under
  `[[report.templates]]` leaves that field empty, so eval drafted the empty
  string, found zero numeric spans, and reported `gate_pass: true` with exit 0.
  That is the shape of `examples/multi-funder/report.toml`, which ships in this
  repository: both funder narratives carry real figures, and eval had never
  looked at either. It now drafts through the same `_draft_templates` the
  export path uses and aggregates the spans across formats, which takes the
  shipped example from 0 numbers scored to 6. A figure written into two funder
  narratives counts twice on purpose: `run` exports one document per format, so
  each occurrence is its own chance for an ungrounded number to reach a reader,
  and the eval report's "What was scored" section now says so.
- `receipts eval` exits non-zero when it scored no numeric span at all.
  `EvalReport.gate_pass` still reports the grounding gate's own verdict, which
  is a truthful pass over an empty denominator and is what `run` would do with
  such a spec, but a command whose job is to measure the gate must not hand CI
  a green from a run that never exercised it. That silent green is how the
  multi-template hole above stayed invisible. `EvalReport.scored` is the new
  distinction, `--json` carries it as `scored`, and the committed eval report
  says in words that an unscored run is not a measurement. Regression tests:
  `tests/test_cli.py::test_eval_scores_every_funder_template_not_only_the_legacy_field`,
  `::test_eval_refuses_to_report_a_pass_when_it_scored_no_numbers`, a passing
  control on the legacy single-template path beside them, and
  `tests/test_eval_report_markdown.py::test_zero_numeric_spans_says_the_run_is_not_a_measurement`.
- Issue 117: a chart naming a metric whose value is negative now refuses to
  render instead of drawing the decrease as a zero. A comparison or
  reconciliation delta figure carries the signed change in `Figure.value`, and
  nothing stopped a `[[charts]]` block from naming one. `_bar_svg_body` took its
  `else` branch for any value not above zero and emitted `height="0.0"`, flush
  on the axis baseline, with the magnitude printed directly above it: a bar
  claiming "no change" beside a receipt reading minus twelve and a label reading
  12. `_line_svg_body` plotted the same point at `y=668.0` on a canvas 360 high,
  off the image entirely, and `_scale_max` fell back to an axis maximum of 1.0
  over a set of decreases. `_points` now raises `ValueError` naming the chart,
  the metric and the value, before any geometry is computed, so both the bar and
  the line path are covered from one place. Drawing the magnitude was rejected
  as a fix and is recorded as such: it makes a decrease of 12 and an increase of
  12 produce byte-identical geometry and an identical `<title>`. A signed bar
  from a zero baseline was also rejected for now, because the only text a chart
  may put on the page is `figure.display`, a delta display is the unsigned
  magnitude by design, and signed geometry with no signed text equivalent leaves
  a screen-reader user reading the same "12" for a rise and a fall. Rationale
  and the path to charting a change properly:
  `docs/adr/0006-refuse-a-negative-valued-chart-metric.md`. A true zero is
  unaffected and still draws a zero-height bar. Regression tests:
  `tests/test_charts.py::test_a_negative_bar_value_is_refused_instead_of_drawn_as_a_zero`,
  `::test_a_negative_line_value_is_refused_too`,
  `::test_the_refusal_names_the_value_and_says_what_to_do`, and a passing zero
  control beside them.
- Issue 116: a decimal written without its leading zero no longer loses its
  separator and binds an unrelated receipt. Every alternative in the grounding
  gate's `_NUMBER` pattern required the match to start on a digit, so `.75`
  matched one character late and came back as the span `75`. That span was
  then looked up like any integer, so a narrative stating a retention rate of
  `.75` bound a receipted count of 75 and the gate reported the report fully
  grounded: a number two orders of magnitude from anything in the data,
  carrying a receipt for something else. `$.99`, `-.5` and the Spanish-
  convention `,75` had the same shape. The pattern now consumes a leading
  `.`/`,` that is not itself preceded by a digit, so `_span_key` sees the whole
  number and a leading-separator decimal binds only a display written the same
  way. No display is written that way, because `engine._format` always writes
  the integer part, so such a span is unbound and blocks export. Ordinary
  decimals, thousands groups, NBSP grouping, currency, percent and duration
  spans are unchanged. Regression tests:
  `tests/test_grounding_gate.py::test_leading_dot_decimal_does_not_bind_the_integer_with_the_same_digits`,
  `::test_leading_separator_decimals_keep_their_separator_in_the_span`, a
  passing control beside them, and two new bilingual benchmark shapes
  (`leading-separator-decimal-for-count`, `sub-one-rate-with-leading-zero`).
- `make container-verify` failed on two upstream findings, not repo code: the
  pinned `python:3.13-alpine` base ships libcrypto3/libssl3 3.5.7-r0, which
  trivy flags for CVE-2026-14456 (HIGH, fixed in Alpine 3.24 main as
  3.5.8-r0), and even the newest base rebuild still carries the old build.
  The final stage now installs the fixed packages version-pinned, and removes
  pip entirely: the runtime is the copied venv, pip exists only for installs
  this offline image never performs, and pip's vendored msgpack and
  setuptools copies were the next findings the scanner surfaced. The base
  digest is refreshed to the current multi-arch index. All 11 verify gates
  pass again, with the scan reporting zero findings rather than any waiver.
- The README, the `docs/ROADMAP.md` metrics ledger, and
  `docs/RESPONSIBLE-TECH-AUDITS.md` all stated the committed grounding benchmark
  was 100 cases, the ROADMAP adding "50 EN, 50 ES; 50 planted unbound failures".
  It has held 132 cases, 66 EN, 66 ES and 66 planted failures since PR 89 added
  the 32-case formatting family on 2026-08-15, and none of the three was
  updated. The numbers were wrong in the three places a reader checks the
  evidence, in the direction of understating it, and nothing could catch that: a
  count written in prose is exactly the kind of claim no gate reads. All three
  are corrected, and `scripts/check_conformance.py` gains
  `benchmark_claim_failures`, wired into `make hygiene`, which reads the
  committed `eval/grounding-benchmark.jsonl` and compares the totals against the
  numbers the documents state. It fails closed on a claim it cannot parse as
  well as on one that is wrong, because a sentence that no longer matches the
  expected shape is not evidence the count is right, and it matches `[0-9]`
  rather than `\d` so a count written in fullwidth digits fails closed instead of
  parsing. Regression tests:
  `tests/test_conformance.py::test_benchmark_claim_failures_catches_the_stale_count`,
  `::test_benchmark_claim_failures_fails_closed_on_an_unreadable_claim`,
  `::test_benchmark_claim_failures_rejects_a_count_written_in_exotic_digits`,
  `::test_benchmark_claim_failures_is_silent_when_the_claims_are_true`, and
  `::test_benchmark_claim_is_true_of_the_real_committed_repository`.
- "Every number is a receipt" promised more than the gate delivers, and the
  project's own exports falsified it. Running the shipped gate over the
  artifacts `make build-html` writes gives `out/a11y/report.md` 3 bound and 61
  unbound, and `out/a11y/trace.html` 4 bound and 124 unbound. Those unbound
  spans are export timestamps, row counts, slice hashes, and the numerals inside
  the printed queries and definitions. They were never in the gate's scope:
  `receipts run` grounds the drafted narrative and the chart, comparison, and
  reconciliation claims, which is what `verify.py::_report_narrative` already
  documented and what README line 289 already said. The headline said otherwise
  in the GitHub description, `README.md`, `DEFINITION_OF_DONE.md`,
  `docs/PROJECT-SCOPE.md`, `AGENTS.md`, `CITATION.cff`, `pyproject.toml`, and
  the shipped `provenance_statement` string that prints inside every export. All
  of them now state the scope the gate actually enforces, and the README and the
  provenance block name the exception rather than leaving a reader to discover
  it. `tests/test_provenance.py::test_the_gate_covers_the_claims_not_every_numeral_in_the_file`
  pins both halves: clean over the narrative region, not clean over the whole
  rendered file. The Spanish `provenance_statement` was rewritten alongside the
  English so no locale keeps asserting what the English no longer says. The
  msgid is a stable key rather than the source text, so gettext could not have
  marked it fuzzy and nothing would have caught the drift. Per
  `docs/I18N.md`'s translation review policy this Spanish is a draft and still
  needs the human review step before it is final copy. Changing the copy changes
  the bytes of an exported `report.md`, so the two bundle digests in
  `tests/fixtures/compat/v1/workflow-artifacts.json` are regenerated. No schema,
  receipt, or figure changed, and the frozen `v0.1.0` manifest still re-derives.
- `docs/ci-action.md` published the composite action's `version` input default
  as `v0.1.0` in its Inputs table and as "the first released tag" in the prose
  beneath it. `action.yml` sets `v0.2.0`, so a reader copying the table pinned
  the wrong CLI. Both are corrected against `action.yml`, and
  `action_default_failures` reads the default out of the action definition
  rather than restating it.
- Nothing compared the three public schema versions across their three homes:
  the constant the code writes, the `const` the published JSON Schema pins, and
  the sentence `docs/SPEC-STABILITY.md` states. All three agree today;
  `schema_version_failures` is what keeps them agreeing, and fails closed when
  the sentence stops being readable.
- `scripts/check_conformance.py` allowed no waiver kind that
  `scripts/check_npm_audit.py` could honour. The npm gate accepts a Node
  dependency advisory only from a waiver whose `kind` is `npm-audit`, and
  `VALID_KINDS` did not list that string, so granting one would make
  `make security-npm` accept the advisory while `make hygiene` rejected the
  registry in the same `make verify` run. The `npm-audit` arm of
  `DEPENDENCY_ADVISORY_KINDS`, which drives the issue-96 VEX cross-check, could
  therefore never fire against a registry this repository would accept, and the
  four tests written against that fixture described a state its sibling gate
  rejects. Nothing had exercised the combination: WVR-007, the only npm-audit
  waiver ever granted here, was retired on 2026-08-15, and `VALID_KINDS` arrived
  on 2026-08-21. `test_valid_kinds_contains_the_kind_the_npm_audit_gate_requires`
  reads the constant from `check_npm_audit` instead of restating it.
- `make lint` and `make type` now cover `scripts/`. Every merge-blocking gate
  except the test suite is implemented in that directory, and neither tool
  looked at it. An unused import, a shadowed name and a type error injected into
  `scripts/check_source_hygiene.py` passed `ruff check src tests` and the
  config-driven `mypy` with exit 0. Type checking runs as two invocations,
  because one combined run cannot resolve the same file as both
  `check_conformance` and `scripts.check_conformance`.
- `scripts/check_source_hygiene.py` read suppression directives out of string
  literals, so a test that exercises suppression handling was flagged for a
  suppression it does not have. Directives are now read from real comment
  tokens. The marker scan stays line-based, because a marker left in a docstring
  is still one left behind, and `scripts/` is in scope for both.
- **Five documents still described `main` as having no bypass actor.** The
  committed ruleset and `docs/rulesets/README.md` were corrected when the
  duplicate ruleset file was removed, but the claim survived in `AGENTS.md`
  ("No admin bypass on `main`"), WVR-005's rationale in `waivers.yml`, and
  three dated documents: `docs/CONFORMANCE-AUDIT-2026-07-12.md`,
  `docs/audits/openssf-scorecard-2026-07-12.md`, and ADR 0002 ("direct pushes
  are structurally blocked"). The live `protect-main` ruleset carries the
  repository owner's standing bypass, `RepositoryRole` 5 with
  `bypass_mode: always`, deliberately and permanently: an agent once applied a
  ruleset with no bypass and locked the owner out of their own repository, and
  restoring access took a sweep across eighteen repositories. An empty list is
  not a stricter gate, it is the lockout, so a reader who trusted any of these
  five and "restored" the empty list would be repeating the incident. `AGENTS.md`
  and `waivers.yml` are corrected outright, being live instructions rather than
  records. The three dated documents keep their original findings and gain a
  dated correction note, because a record of what was believed on 2026-07-12 is
  worth more than a silently amended one -- and the correction says why the
  Scorecard number is unaffected, since Branch-Protection is capped here on the
  solo-maintainer approval count (WVR-005), not on bypass actors.
- `tests/test_ruleset_lockout.py` now pins those five corrections, so the claim
  cannot drift back in the document a reader actually opens. It failed against
  each of the five as they stood.
- A metric whose `value_sql` returns SQL `NULL` now fails closed in
  `compute_figure` instead of becoming the number `0.0`. `AVG`/`SUM`/`MIN`/`MAX`
  over an empty filtered set, a division by a zero denominator, and a NULL join
  all produce `NULL`, and the old coercion turned each of them into a published
  measurement: `"0"`, `"0%"`, `"$0.00"` or `"0 days"` in the narrative, a
  zero-height bar in the chart, `"value": 0.0` in `receipts.json`, and `0` in
  the trace. Nothing downstream could recover the distinction, because
  suppression reads `value == 0` as a true zero and leaves it published while
  `verify` re-derives the same `0.0` and agrees. The engine now raises
  `ValueError` naming the metric, and the message points at `COALESCE(<expr>, 0)`
  for authors who do mean zero over an empty set. `COUNT(*)` still returns a
  genuine `0` and still publishes. Regression tests:
  `tests/test_engine.py::test_null_scalar_fails_closed_instead_of_becoming_zero`
  and the four cases beside it.
- `receipts diff` no longer prints the literal word `None` for a suppressed
  figure's before/after value. A schema-2.0 receipt that crossed the
  suppression threshold between two runs carries `value: null`,
  `row_count: null`; the reason text and the two-level Markdown fallback both
  interpolated that straight into an f-string, so an exported diff read
  `"value None -> 47.0"` next to a real number, and a foreign manifest (`diff`
  reads two arbitrary JSON files, not only ones this tool produced) missing
  `display` entirely fell through the same way, or to a silently blank cell
  when `value` was also absent. Both `diff.py` and `report.py` now route
  through the same `[SUPPRESSED]` redaction marker `report._withheld` and
  `trace._withheld` already use. Regression tests:
  `tests/test_diff.py::test_suppressed_prior_value_reports_marker_not_the_word_none`
  and the three cases beside it.
- A federated rollup receipt missing `slice_hash`, `value`, or `row_count`
  entirely used to default to `""`, `0.0`, and `0` in `_record_disjoint_slice`
  -- the exact shape of a genuine, verified empty slice -- so it silently
  passed as "verified empty," was never registered against another partner's
  slice hash, and its own unexamined count still entered the rollup sum,
  exempting the partner from the one disjointness check
  `receipts rollup` exists to run. The three fields now go through a
  `_required_number`/`_required_text` extractor that raises `WorkflowError`
  naming the field instead of defaulting. Regression tests:
  `tests/test_rollup_adversarial.py::test_disjoint_slice_check_fails_closed_on_a_receipt_missing_every_gate_field`
  and the three cases beside it.
- `receipts map` reported confidence `1.00` -- the maximum score on the
  scale -- for a candidate whose field mapping was never actually checked.
  An unfiltered `count_rows` requirement maps zero logical fields, so
  `_candidate`'s `min(match.confidence for match in matches, default=1.0)`
  fired its default on an empty sequence, hiding the one review-queue row
  with no verified evidence behind the highest-looking score. Defaults to
  `0.0` now, the same floor a `blocked` candidate already carries. Regression
  test:
  `tests/test_mapping.py::test_zero_field_matches_reports_minimum_not_maximum_confidence`.
- The committed `eval.md` wrote `Grounding gate (100% required): PASS
  (observed 100.0%).` for a narrative with zero numeric spans, indistinguishable
  from a report that scored real numbers and found all of them grounded. The
  rate is vacuously `1.0` when there is nothing to bind (`evaluate.py`), which
  is a legitimate reason for the gate to pass, but `render_eval_markdown` now
  labels that case honestly -- `N/A (no numeric spans)` and "passes vacuously,
  not on a measured rate" -- instead of letting the vacuous rate stand in for a
  measurement. A report that actually scores numbers is unaffected. Regression
  tests: `tests/test_eval_report_markdown.py` (new; `render_eval_markdown` had
  no direct test before this change).

## [0.2.0] - 2026-08-16

Pre-1.0, so a breaking change to the receipts-manifest contract lands in a
minor bump rather than a major one (see the versioning note above). The
contract change is described in full under **Changed** below.

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
- The dependency-install step could not fail on lockfile drift. `make install`
  ran `uv sync --frozen` under a comment claiming `--frozen` made "a lockfile
  drift a loud CI failure"; it does not. `--frozen` installs exactly what
  `uv.lock` records and never compares the lock against `pyproject.toml`, so
  bumping `project.version` without re-locking still exits 0 — proven by doing
  exactly that: `uv sync --frozen` returned 0 with `pyproject.toml` at `0.2.0`
  and `uv.lock` at `0.1.0`, while `uv lock --check` returned 1 on the same tree.
  The one change guaranteed to desynchronise the lock was the one change the
  gate could not see, and every release re-verified against a stale editable
  install. `make install` now runs `uv lock --check` first and fails closed,
  matching what `npm ci` (as opposed to `npm install`) already did for the
  JavaScript half of the toolchain.
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

[Unreleased]: https://github.com/ChelseaKR/outcome-receipts/compare/v0.2.1...HEAD
[0.2.1]: https://github.com/ChelseaKR/outcome-receipts/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/ChelseaKR/outcome-receipts/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/ChelseaKR/outcome-receipts/releases/tag/v0.1.0
