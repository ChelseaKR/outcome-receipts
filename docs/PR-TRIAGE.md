# Open pull-request triage

Triage of the eight open pull requests as of 2026-08-28, against `origin/main`
at `80ee14d` ("docs(changelog): record the three fail-closed fixes merged as
\#112-\#114 (#115)").

Read-only triage. Nothing here was merged, closed, commented on, relabelled or
re-run. Every claim below is marked VERIFIED or ON TRUST in the last section.

## Method

* `git fetch origin --prune`, then `git log`, `git cherry` and two-dot
  `git diff` per head to establish topology and staleness.
* `gh pr diff` and `gh pr checks` for all eight, then the raw job logs
  (`gh api .../actions/jobs/<id>/logs`) for every red check. No verdict below
  rests on a check's colour alone.
* `git merge-tree --write-tree` against `main` for each head, and pairwise
  across all 28 head pairs. Because every head's merge base is `main` itself,
  a pairwise `merge-tree` is exactly the sequential-merge test.
* Merged trees were materialised into a scratch directory with `git archive`
  and the repository's own `.venv` ruff, mypy and conformance code was run
  over them. The working tree was not touched.

## The shared red: what BLOCKED actually means

Every one of the eight shows two failing checks, `verify` and
`container (build - smoke - trivy)`, and five passing ones. The logs are
unambiguous and identical in kind across all eight:

```
== container-verify: FAIL ==
FAILED 1 of 11 gates: container-verify
make: *** [Makefile:136: verify] Error 1
```

(`1 of 12` on #127, which adds a `perf` gate; that gate reports
`== perf: PASS ==`.)

The single failing gate is `container-scan`, and its cause is one Trivy
finding in the pinned Alpine base:

| Library | Vulnerability | Severity | Status | Installed | Fixed |
|---|---|---|---|---|---|
| libcrypto3 | CVE-2026-14456 | HIGH | fixed | 3.5.7-r0 | 3.5.8-r0 |
| libssl3 | CVE-2026-14456 | HIGH | fixed | 3.5.7-r0 | 3.5.8-r0 |

The base is pinned by digest in the `Dockerfile`:
`python:3.13-alpine@sha256:399babc8b49529dabfd9c922f2b5eea81d611e4512e3ed250d75bd2e7683f4b0`,
and `container-scan` runs Trivy with `--severity HIGH,CRITICAL --exit-code 1
--ignore-unfixed=false`.

**No pull request in this queue is red for a reason of its own.** On every one
of the eight, all ten other `verify` gates pass: lint, type, test, hygiene,
i18n, the six security gates, a11y, cards, eval-check and compat. The
`container` job is the same scan failing standalone.

Two refinements to the standing description of this failure:

1. It is **libcrypto3 as well as libssl3**. Both packages carry the CVE.
2. Trivy reports `Status: fixed` and names **3.5.8-r0**, so the fix exists at
   the Alpine package level. The remediation is a base-image digest bump to a
   `python:3.13-alpine` rebuild that carries openssl 3.5.8-r0, not an
   open-ended wait. Whether such a rebuild has been published yet was not
   checked here (see ON TRUST).

## Per pull request

### #130 Repair four gates that could not report what they exist to report

* Base `main`. Head `fix/gates-that-could-not-fail`, 7 commits, merge base is
  `main`'s tip. Not stale. Merges clean against `main`.
* CI: inherited Trivy failure only.
* Changes: puts `scripts/` under `ruff check`, `ruff format --check` and a
  second `mypy --strict scripts` invocation; ships `src/outcome_receipts/py.typed`;
  adds `npm-audit` to `VALID_KINDS` in `scripts/check_conformance.py`; teaches
  `check_source_hygiene.py` to read suppression directives from real comments
  via `tokenize` and to cover `scripts/`; adds `scripts/check_semgrep_waivers.py`
  (325 lines) enforcing the Semgrep ledger against the tree in both directions;
  re-reviews both Semgrep waivers and re-dates them.
* Correctness: the central claims hold. `scripts/check_npm_audit.py` really does
  define `KIND = "npm-audit"` while `main`'s `VALID_KINDS` omitted it, and
  `DEPENDENCY_ADVISORY_KINDS` really does contain `"npm-audit"`, so the only
  kind the npm gate could honour was a kind the waiver lint rejected. That arm
  could not fire. The fix is real. `check_semgrep_waivers.py` is careful work:
  it refuses an unqualified `nosemgrep`, tokenizes Python so a directive quoted
  in a docstring is not counted, and over-reports rather than under-reports on
  an unparseable file.
* One weak test. `tests/test_gate_scope.py::test_every_gate_script_is_inside_the_directory_the_gates_now_cover`
  claims that "nothing that implements a gate may sit outside `scripts/` and
  escape both tools again", but it scans `ROOT.glob("*.py")`, which is the
  repository root only and is not recursive. There are zero `.py` files at the
  repository root, so the assertion is vacuously true today and would stay true
  if gate code were added under any subdirectory. There is already one tracked
  Python file outside the covered set, `eval/hud/extract.py`, which this test
  does not see and which `make lint` and `mypy` still do not cover after this
  change. The other two tests in that file are sound and do fail if the scope is
  narrowed. This is a narrower guarantee than advertised, not a false claim.
* **Recommendation: merge after rebase.** Merge it last (see order of
  operations). It is the only head that edits all three `[Unreleased]`
  subsections, so it conflicts with all seven others on `CHANGELOG.md`
  wherever it is placed; going last costs one rebase instead of seven.

### #129 test(conformance): say what the frozen standards snapshot is, and pin the version's three copies

* Base `main`. Head `docs/standards-pin-cross-check`, 1 commit. Not stale.
  Merges clean against `main`.
* CI: inherited Trivy failure only.
* Changes: rewrites a comment in `tests/test_conformance.py` that falsely
  described `_CONTROLS_YML_STANDARDS_SNAPSHOT` as a snapshot "of the version
  this repository pins", and adds
  `test_the_standards_pin_is_named_the_same_way_in_all_three_places`.
* Correctness: this is the highest-value truth-telling change in the queue, and
  its central claim was verified against a live CI log rather than taken from
  the diff. `.standards-version` pins `v1.0.1`; `controls.yml` did not exist at
  `v1.0.1`. The green "portfolio standards conformance" check on every one of
  these eight pull requests emits, in its own log:

  > `WARNING: .standards exists but has no controls.yml -- the pinned standards
  > checkout (see .standards-version) predates FIX-01 (controls.yml was added
  > 2026-07-11). Falling back to the vendored standards list...`

  So that green check compares the README against the repository's own
  hardcoded literal, which is the thing DOC-11 exists to stop trusting. The
  comment on `main` asserted the opposite. Correcting it is worth more than the
  new test.
* The new test is sound but brittle in one respect: it asserts
  `checkout_refs == [pinned]`, which requires `standards.yml` to contain exactly
  one `ref:` line. It contains exactly one today. A second checkout step with a
  `ref:` would turn it red for an unrelated reason.
* **Recommendation: merge.**

### #128 docs(conformance): declare AI-Development Measurement scope and date every BASELINE row

* Base `main`. Head `docs/ai-dev-measurement-declaration`, 1 commit. Not stale.
  Merges clean against `main`.
* CI: inherited Trivy failure only.
* Changes: adds an `AI-DEV-MEASUREMENT: APPLIES` scope row and converts the
  DORA and quality-debt prose in `docs/ROADMAP.md` into a seven-row table where
  each row carries `BASELINE until 2026-10-11`; updates the README conformance
  row; adds `ai_dev_measurement_failures()` to `scripts/check_conformance.py`
  and five tests.
* Correctness: the prose is honest and the two unbuilt artifacts are named as
  outstanding rather than claimed, which is right. The defect is in the gate.
  `ai_dev_measurement_failures` finds every table row containing `BASELINE`
  and then runs `_ISO_DATE_RE.search(row)` over **the entire row**, not over
  the BASELINE cell, and never compares the date to today. Two consequences,
  both reproduced by running the merged function directly:

  * A row parked in BASELINE **with no graduation date at all** passes, as long
    as any ISO date appears anywhere else in the row. Probed:
    `| Change lead time | 149.8 hours, measured 2026-07-11 | BASELINE |`
    returns no failures. The table this pull request adds is headed
    `| Metric | Measured 2026-07-11 | Gate |`, so putting a measurement date in
    a data cell is the natural next edit, and it silently disables the check
    for that row.
  * An **elapsed** graduation date passes. Probed:
    `| Change lead time | x | BASELINE until 1999-01-01 |` returns no failures.
    Every row this pull request adds says `BASELINE until 2026-10-11`. From
    2026-10-12 onward the gate reports green forever, while the rule it states
    in its own failure message is "a metric may not sit there indefinitely".
    That is the precise condition the check exists to catch, and it cannot
    detect it.

  The pattern for the fix already exists eleven lines away in the same file:
  `doc_staleness_failures(root, date.today())` takes the current date and
  enforces recency.
* **Recommendation: needs work.** Specifically: parse the graduation date out
  of the cell that contains the `BASELINE` token rather than searching the
  whole row, and take a `today: date` parameter and fail when the graduation
  date has passed, mirroring `doc_staleness_failures`. Add a test that a
  BASELINE row whose date has elapsed fails, and a test that a measurement date
  elsewhere in the row does not satisfy the requirement. Everything else in the
  pull request is fine and can stay.

### #127 feat(perf): commit the Performance standard's budgets, baseline and regression gate

* Base `main`. Head `feat/performance-budget-and-baseline`, 2 commits. Not
  stale. Merges clean against `main`.
* CI: inherited Trivy failure only. Its new `perf` gate ran and passed in CI
  (`== perf: PASS ==`), and the gate list grew from 11 to 12.
* Changes: adds `categories:performance` and a zero-byte
  `resource-summary:script:size` assertion to the single `lighthouserc.cjs`;
  commits `perf/baseline.json` and `perf/README.md`; adds
  `scripts/check_perf_baseline.py` and `tests/test_perf_baseline.py`; wires
  `perf` into `VERIFY_GATES` after `a11y`; registers the two new files in the
  conformance `REQUIRED` list.
* Correctness: the script is good and the tests are real. They drive
  `regression_failures` with synthetic measurements against the actual
  committed baseline and assert both directions, the declared-N/A skip, the
  undeclared-metric failure and the unusable-direction failure; `latest_report`
  and `read_measurement` are tested to fail closed on a missing report, a null
  score and a missing script row. The staleness refusal (a report older than
  the trace it would be scored against is rejected) is the genuinely new
  protection here, and it is the right one: it stops a failed Lighthouse run
  leaving a green performance check.
* One thing a reader should not misread. For both metrics that are actually
  live, the regression threshold coincides exactly with the absolute assertion
  Lighthouse-CI already makes in `a11y`. `lighthouse_performance` has baseline
  1.0 and `higher_is_better`, so the 10% band floor is 0.90, which is the same
  number as the `minScore: 0.9` assertion. `js_kb_gzip` has baseline 0 and
  `lower_is_better`, so a multiplicative 10% band around zero is zero, which is
  the same as `maxNumericValue: 0`. Neither regression arm can fire in a state
  where the `a11y` gate passes. The mechanism is correct and unit-tested, and
  the three null metrics will use it once they have values, but as configured
  today the "direction-aware 10% regression gate" adds no detection power over
  the absolute budgets. Worth a sentence in `perf/README.md`; not a blocker.
* **Recommendation: merge.**

### #125 docs(conformance): the documented benchmark size is now checked against the benchmark

* Base `main`. Head `docs/benchmark-size-claims-are-checked`, 1 commit. Not
  stale. Merges clean against `main`.
* CI: inherited Trivy failure only.
* Changes: corrects the README from "100-case" to "132-case" and the ROADMAP
  from "100 committed cases: 50 EN, 50 ES; 50 planted unbound failures" to
  "132 committed cases: 66 EN, 66 ES; 66 planted unbound failures"; adds
  `benchmark_claim_failures()` to `scripts/check_conformance.py` so the
  documented size is compared against `eval/grounding-benchmark.jsonl`; adds
  four tests.
* Correctness: correct as of `main`. The committed benchmark on `main` really
  does hold 132 cases / 66 EN / 66 ES / 66 planted failures, and both documents
  really did still say 100 / 50 / 50 / 50. The check fails closed on an
  unreadable claim as well as a wrong one, which is the right call, and
  `test_benchmark_claim_is_true_of_the_real_committed_repository` binds it to
  the real files.
* **This pull request and #122 merge cleanly into a broken `main`.** See the
  hazard section below. It is the reason for the recommendation.
* **Recommendation: merge after rebase.** Rebase after #122 lands and
  regenerate the two documented counts to 136 / 68 / 68 / 68 in the same
  commit. Also expect to resolve `tests/test_conformance.py` against #129 and
  both conformance files against #128.

### #124 fix(charts): refuse a negative-valued chart metric instead of drawing it as zero (#117)

* Base `main`. Head `fix/charts-refuse-negative-value-117`, 1 commit. Not
  stale. Merges clean against `main`.
* CI: inherited Trivy failure only.
* Changes: `_points` now raises `ValueError` when a drawable point's value is
  negative, naming the chart, the metric and the value; adds ADR 0006; adds
  four tests.
* Correctness: a genuine fail-closed defect, genuinely fixed. A comparison or
  reconciliation delta figure carries a signed `Figure.value` while its
  `display` is the unsigned magnitude, so a decrease of 12 rendered as
  `height="0.0"` on the baseline with the label `12` above it, and on the line
  path at `y=668` on a 360-high canvas. Refusing is the correct resolution
  rather than drawing the magnitude, and the reasoning for that (a chart may
  only print `figure.display`, so signed geometry would have no signed text
  equivalent for a screen-reader user) is recorded in the module docstring and
  the ADR. The tests use `pytest.raises`, so they fail in the pre-fix state;
  the zero-value control is explicitly labelled as passing in both states.
* **Recommendation: merge.**

### #123 fix(eval): score every exported narrative, and refuse a pass over nothing (#118)

* Base `main`. Head `fix/eval-scores-every-template-118`, 1 commit. Not stale.
  Merges clean against `main`.
* CI: inherited Trivy failure only.
* Changes: `_cmd_eval` now drafts through `_draft_templates` over
  `spec.report.effective_templates` instead of `draft(spec.report, ...)`; adds
  `EvalReport.scored`; makes `receipts eval` exit non-zero when it scored no
  numeric span; makes `render_eval_markdown` say so; updates `eval/report.md`.
* Correctness: a genuine fail-closed defect. A spec using `[[report.templates]]`
  leaves the legacy single `[report] template` empty, so eval drafted the empty
  string, found no numbers and reported a pass over nothing. That spec ships in
  this repository at `examples/multi-funder/report.toml`. Separating
  "the gate passed" from "this run is evidence the gate works" is the right
  model, and the exit code now agrees with what the markdown already refused to
  claim. The three new CLI tests cover the multi-template case, a
  single-template control that is unchanged, and a spec with no figures at all
  that must exit non-zero while still reporting `gate_pass: true`.
* Note: the new stderr message contains an em dash. That is consistent with
  this repository (`main`'s README carries 23 of them) and nothing here
  enforces the portfolio's no-dash rule, so it is not a defect against this
  repository. It is flagged only because the portfolio convention says
  otherwise. Same applies to #125, #127 and #128.
* **Recommendation: merge.**

### #122 fix(grounding): a leading-separator decimal must keep its separator (#116)

* Base `main`. Head `fix/grounding-leading-dot-116`, 1 commit. Not stale.
  Merges clean against `main`.
* CI: inherited Trivy failure only.
* Changes: adds a fourth alternative to `_NUMBER`, tried first, matching a
  decimal written without its leading zero; adds two benchmark shapes (four
  cases, two EN and two ES) to `eval/grounding-benchmark.jsonl` and its
  generator; adds three tests.
* Correctness: a genuine defect in the repository's load-bearing invariant, and
  the most serious of the three. All three prior alternatives require the match
  to start on a digit, so `.75` matched one character late and came back as the
  span `75`, which then **bound a receipted count of 75**. A rate written the
  ordinary English way therefore carried a receipt for a number two orders of
  magnitude away from it, which is precisely the "a number that is not a
  figure" failure the gate exists to prevent. Placing the new alternative first
  is necessary and does not disturb the others: they are only reachable at a
  position starting with a digit, and the new one requires a separator there.
  The tests assert the span text is `.75`, so they fail in the pre-fix state
  where it was `75`; the `0.75` positive control is labelled as passing in
  both states.
* **Recommendation: merge.** Merge it first.

## Stack and overlap

There is **no stack**. All eight heads have the same merge base, `80ee14d`,
which is the current tip of `main`. `git cherry origin/main origin/<head>`
marks every commit on every head as `+` (not upstream), and every two-dot
`git diff origin/main..origin/<head>` is non-empty. No branch contains another
branch's commits. The cumulative-snapshot antipattern is not present here, and
no pull request in this queue has an empty diff or would be silently delivered
by merging another.

```
                         origin/main  80ee14d
                              |
   +------+------+------+-----+-----+------+------+------+
   |      |      |      |           |      |      |      |
 #122   #123   #124   #125        #127   #128   #129   #130
  1c     1c     1c     1c          2c     1c     1c     7c

 File overlap (all eight are independent commits off the same base):

 CHANGELOG.md              #122 #123 #124 #125 #127 #128 #129 #130   (all 8)
   [Unreleased] > Added                        #127 #128      #130
   [Unreleased] > Changed                                #129 #130
   [Unreleased] > Fixed    #122 #123 #124 #125                #130

 scripts/check_conformance.py              #125 #127 #128      #130
 tests/test_conformance.py                 #125      #128 #129 #130
 README.md                                 #125 #127 #128
 docs/ROADMAP.md                           #125 #127 #128
 Makefile                                            #127      #130
 eval/grounding-benchmark.jsonl       #122            (pinned by #125's gate)
```

## Pairwise collisions

All 28 pairs were tested with `git merge-tree`. Twenty conflict. Because each
pair's merge base is `main`, this is exactly what happens on sequential merge.

| Pair | Conflicts on |
|---|---|
| #130 with each of #129 #128 #127 #125 #124 #123 #122 | `CHANGELOG.md` (7 pairs) |
| #128 with #127 | `CHANGELOG.md`, `README.md` |
| #128 with #125 | `scripts/check_conformance.py`, `tests/test_conformance.py` |
| #129 with #128 | `tests/test_conformance.py` |
| #129 with #125 | `tests/test_conformance.py` |
| #125 with #124, #125 with #123, #125 with #122 | `CHANGELOG.md` |
| #124 with #123, #124 with #122 | `CHANGELOG.md` |
| #123 with #122 | `CHANGELOG.md` |

Clean pairs: #129 with #127, #124, #123, #122; #128 with #124, #123, #122;
#127 with #125, #124, #123, #122.

The `CHANGELOG.md` pattern is fully explained by which `[Unreleased]`
subsection each head inserts into. `main`'s subsections begin at lines 13
(Added), 28 (Changed) and 96 (Fixed). Heads inserting into the same subsection
collide; heads in different subsections do not. #130 inserts into all three.

The `README.md` collision between #127 and #128 is line adjacency: #127 rewrites
the Performance row at line 490 and #128 rewrites the AI-Development Measurement
row at line 491.

## Non-diff hazards

### The changelog-into-a-released-section hazard does not occur

Checked and cleared. `main`'s `CHANGELOG.md` has `## [Unreleased]` at line 11,
`## [0.2.0] - 2026-08-16` at line 155 and `## [0.1.0] - 2026-07-11` at line 388.
Every hunk in all eight heads lands at line 11, 26 or 94, all comfortably inside
`[Unreleased]`. No head writes at or past line 155. As earlier merges push the
`[0.2.0]` boundary down, git's content-based three-way merge re-anchors later
hunks by context, so the observed outcome is a conflict inside `[Unreleased]`,
never a silent landing inside a released section.

### The real hazard: #122 and #125 merge cleanly into a red `main`

This is the one to plan around. It was reproduced, not inferred.

* `main` holds 132 benchmark cases (66 EN, 66 ES, 66 planted failures), and
  both `README.md` and `docs/ROADMAP.md` still claim 100 / 50 / 50 / 50.
* **#125** corrects both documents to 132 / 66 / 66 / 66 and adds
  `benchmark_claim_failures()`, which asserts the documented counts equal the
  committed file's counts. Correct against `main`.
* **#122** adds four cases to `eval/grounding-benchmark.jsonl`, taking it to
  136 / 68 / 68 / 68, and does not touch `README.md` or `docs/ROADMAP.md`,
  because on `main` no gate reads those numbers.
* The two conflict only on `CHANGELOG.md`. Nothing else about them collides,
  so a routine changelog resolution produces a tree where the new gate fails.

Running #125's own gate over the merged tree:

```
README.md claims a 132-case bilingual grounding benchmark;
  eval/grounding-benchmark.jsonl holds 136
docs/ROADMAP.md claims the benchmark is 132 cases / 66 EN / 66 ES /
  66 planted failures; eval/grounding-benchmark.jsonl holds 136 / 68 / 68 / 68
```

That failure surfaces twice: in the `hygiene` gate of `make verify`, and in the
`portfolio standards conformance` job, which runs `check_conformance.py`
directly. #125's own
`test_benchmark_claim_is_true_of_the_real_committed_repository` also goes red.

Mitigation: whichever of the two merges second must carry the documented count.
The order below merges #122 first and treats the count bump as a required
regeneration step on #125.

### Two heads appending to one Python file, merging cleanly into breakage

Checked and cleared for the code gates. `tests/test_conformance.py` is appended
to by #130, #129, #128 and #125, and `scripts/check_conformance.py` by #130,
#128, #127 and #125. No two heads introduce a colliding function or constant
name, and the pairs that would merge silently do not produce duplicate
definitions. To confirm rather than assume, merged trees of #130 with each of
#127, #128, #125 and #122 were materialised and the repository's own tooling
was run over them:

```
ruff check src tests scripts        All checks passed!   (all four)
ruff format --check src tests scripts  formatted         (all four)
mypy --strict scripts              Success               (all four)
```

This matters specifically because #130 puts `scripts/` under ruff and
`mypy --strict` for the first time, and #127 adds a brand new 182-line script
there that has never been linted or type-checked. It passes. That result is
what makes it safe to merge #130 last. Also checked: none of the other heads
adds a `nosemgrep`, `noqa`, `type: ignore` or a TODO/FIXME/HACK marker under
`scripts/`, so #130's widened hygiene and its new Semgrep ledger check do not
trip on any of them.

Not verified: the full eight-way merged tree was never built, because several
pairs conflict and a resolution would have to be invented. The lint, type and
conformance results above are pairwise.

## Order of operations

Two rules shape this order. #130 touches all three changelog subsections, so it
conflicts with everything wherever it goes; putting it last costs one rebase
instead of seven. Within a changelog subsection, the second and later merges
always need a rebase. Across subsections they do not.

**Wave 1: three merges, no conflicts, no rebases.** These three pairs were all
verified clean.

1. **#122** (`Fixed`). Merge as-is. First, because it is a correctness fix in
   the load-bearing grounding gate and because it changes the benchmark file
   #125 pins.
2. **#129** (`Changed`). Merge as-is. Clean against `main` plus #122.
3. **#127** (`Added`). Merge as-is. Clean against `main` plus #122 and #129.

**Wave 2: rebases required.**

4. **#124** (`Fixed`). Rebase: the `Fixed` subsection moved when #122 landed.
   No other collision.
5. **#123** (`Fixed`). Rebase for the same reason. No other collision.
6. **#125** (`Fixed`). Rebase, **and a required regeneration step**: change
   `README.md` to "136-case" and `docs/ROADMAP.md` to
   "136 committed cases: 68 EN, 68 ES; 68 planted unbound failures" in the same
   commit, because #122 grew the benchmark by four cases. Without this the gate
   this pull request introduces goes red on `main` immediately. Also resolve
   `tests/test_conformance.py` against #129's changes to the same file.

**Wave 3: after #128 is fixed.**

7. **#128**, once the graduation-date check is corrected. Rebase, then resolve
   three collisions: `README.md` line adjacency with #127's Performance row,
   and `scripts/check_conformance.py` plus `tests/test_conformance.py` against
   #125.

**Wave 4.**

8. **#130**. Rebase last. Resolve `CHANGELOG.md` across all three subsections.
   No other file needs resolution, and its widened lint, type, hygiene and
   Semgrep-ledger gates were verified to pass against every other head.

Merges needing a regeneration or reposition step, in one list:

* **#125: regeneration required.** Documented benchmark counts must be
  recomputed from the post-#122 benchmark file. This is the only step in the
  queue whose omission produces a red `main` from two green pull requests.
* **#124, #123, #125: changelog reposition** into the `Fixed` subsection as it
  stands after #122.
* **#128: changelog reposition** into `Added` as it stands after #127, plus the
  adjacent README row.
* **#130: changelog reposition** in all three subsections.

Nothing in this queue needs retargeting: all eight already base on `main`.
Nothing is superseded or duplicated.

## Two green checks that cannot fail

Outside the scope of any single pull request, but found while verifying them,
and both worth an issue:

1. **`portfolio standards conformance`** passes on all eight and is comparing
   the README against the repository's own vendored literal, not against the
   pinned registry, because `.standards-version` pins `v1.0.1` and
   `controls.yml` did not exist until 2026-07-11. The job's own log says so.
   #129 documents this accurately; it does not fix it, and says it does not.
2. **#128's BASELINE graduation-date check**, as written, goes permanently
   green on 2026-10-12. Covered above.

## Verified versus taken on trust

### Verified

* All eight base on `main` and have merge base `80ee14d`, the current tip. No
  branch is stale, none contains another's commits, none has an empty two-dot
  diff, and `git cherry` marks every commit unmerged. No stack, no cumulative
  snapshot.
* Every one of the eight fails exactly and only `container-verify`, on Trivy
  CVE-2026-14456. Read from each `verify` job's full gate list in the raw log,
  not from check status.
* The CVE hits `libcrypto3` and `libssl3`, installed 3.5.7-r0, and Trivy
  reports a fixed version 3.5.8-r0 exists.
* The 28-pair conflict matrix, by `git merge-tree --write-tree`.
* Every changelog hunk in all eight lands inside `[Unreleased]`; section
  boundaries read from `origin/main:CHANGELOG.md`.
* #122 plus #125 produces a failing conformance gate. Reproduced by
  materialising the merged tree and running `benchmark_claim_failures` over it.
* Benchmark counts: 132/66/66/66 on `main` and on #125, 136/68/68/68 on #122.
  Computed from the files.
* `ruff check`, `ruff format --check` and `mypy --strict scripts` all pass on
  merged trees of #130 with each of #127, #128, #125 and #122.
* #128's date check passes a BASELINE row carrying no graduation date when any
  ISO date appears elsewhere in the row, and passes an already-elapsed date.
  Both probed against the merged function.
* #130's stray-script assertion scans the repository root only and is vacuously
  true; `eval/hud/extract.py` is a tracked Python file outside every covered
  directory.
* #129's claim about the vacuous standards job, against the live CI log
  warning text.
* #130's npm-audit claim: `check_npm_audit.KIND == "npm-audit"`,
  `DEPENDENCY_ADVISORY_KINDS` contains it, `main`'s `VALID_KINDS` did not.
* `standards.yml` contains exactly one `ref:`, so #129's new test holds today.
* All eight modify `CHANGELOG.md`.

### Taken on trust

* That no rebuilt `python:3.13-alpine` digest carrying openssl 3.5.8-r0 has
  been published. No registry was queried. Trivy's `Status: fixed` says only
  that Alpine has shipped the package fix.
* The repository's branch protection and required-check configuration. Settings
  were not read. That `BLOCKED` follows from the two failing required checks is
  an inference, supported by all eight showing an identical pattern and
  `mergeable: MERGEABLE`.
* That `make verify` reproduces CI byte for byte. The Makefile says so; only
  ruff, mypy and two conformance functions were run locally.
* Pull request titles and descriptions. Correctness verdicts come from reading
  the diffs and the test bodies.
* That `examples/multi-funder/report.toml` yields exactly six scored spans, as
  #123's test asserts. The test passed in CI; it was not re-run here.
* The eight-way merged state. All conflict, lint and type results are pairwise.

## Outcome, recorded 2026-09-01

The triage above is a snapshot of 2026-08-28 and is kept as written. What
followed is recorded here rather than folded into it, so the report can still be
read against the state it was made in.

| PR | Recommended | What happened |
|---|---|---|
| #122 | merge (first) | merged as `4ee481e` |
| #123 | merge | merged as `7c9970e` |
| #124 | merge | merged as `c7f6d0f` |
| #125 | merge after rebase | **closed**, superseded by #136 |
| #127 | merge | merged as `d449088` |
| #128 | needs work | **merged after the defect was fixed** |
| #129 | merge | merged as `b724433` |
| #130 | merge (last) | merged as `27809cd` |

Three of the report's findings decided an outcome:

**The #122 + #125 collision was real, and #125 lost the race.** #136 landed the
same `benchmark_claim_failures` gate on 2026-08-29 with the regenerated
136/68/68/68 counts and a third document (`docs/RESPONSIBLE-TECH-AUDITS.md`) in
scope. #125's branch still carried `132`, so merging it after #122 would have
turned the gate it adds red against its own repository — exactly the breakage
this report reproduced. It was closed as superseded rather than rebased.

**#128's graduation-date check was fixed before merge, and the report
understated it by one.** Both defects named here were reproduced against the
as-submitted function: with a measurement date anywhere else in the row, an
undated BASELINE row reported nothing, and the real ledger reported nothing on
2099-01-01. The date is now read out of the gate cell alone and compared against
today. A third case the report did not name was found while fixing it: a
date-shaped string that is not a date (`2026-13-40`) parsed as "a date is
present" and passed. It now fails closed.

**The shared red belonged to nobody, and is gone.** #133 cleared
CVE-2026-14456 on 2026-08-29 by installing the fixed `libcrypto3`/`libssl3`
3.5.8-r0 into the final stage, version-pinned, and deleting pip from the runtime.
`container (build · smoke · trivy)` has been green on every run since. The
report's one "taken on trust" item on this point — that no rebuilt
`python:3.13-alpine` digest carries the fix — held: the remedy was not a digest
bump.

The two green checks that cannot fail, from the section above:

1. **`portfolio standards conformance` compares the README against the vendored
   literal.** Still true. It needs a `.standards-version` bump, which is a
   portfolio-pin decision with repository-wide scope and is not made here.
2. **#128's BASELINE check.** Fixed, with four regression tests, one of which
   reads the real ledger on 2026-10-12 and requires every row parked in BASELINE
   to come back overdue.
