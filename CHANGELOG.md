# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project aims
for [Semantic Versioning](https://semver.org/spec/v2.0.0.html) from 1.0.

Version `0.1.0` is the first beta release. It includes the deterministic core
and the privacy, verification, mapping, localization, optional drafting, and
release-hardening work completed before the first public tag.

## [Unreleased]

### Added
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

[Unreleased]: https://github.com/ChelseaKR/outcome-receipts/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/ChelseaKR/outcome-receipts/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/ChelseaKR/outcome-receipts/releases/tag/v0.1.0
