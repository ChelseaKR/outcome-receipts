# Performance budgets and the committed baseline

Last verified: 2026-09-06 · Recheck cadence: quarterly and on any change to the
generated trace markup or the Lighthouse toolchain

This directory holds the portfolio Performance standard's artifacts for this
repository: the budgets it is held to, the measured baseline those budgets are
compared against, and the reasons for every value that differs from the
standard's default.

## What this project is, for the purpose of this standard

`outcome-receipts` is an offline CLI. It has no hosted route, no preview
environment, and no running service. It does generate and ship HTML: the trace
view a funder opens (`receipts trace`, rendered into `out/a11y/trace.html` by
`make build-html`), which is a single static document with no JavaScript, no
stylesheets, and no third-party requests.

So the standard applies in part, and the part that does not apply is declared
rather than skipped.

| Control | State here | Reason |
|---|---|---|
| PERF-01, k6 latency thresholds | N/A | There is no hosted route and no preview environment to measure. The standard's own rule is that a perf job with no real URL is declared N/A until the environment exists, not wired in advisory mode. |
| PERF-02, Lighthouse score and bundle budgets | Applies, enforced, with one deliberate substitution | `lighthouserc.cjs` asserts the bundle budgets and the accessibility score on the generated trace during `make a11y`. The standard's `categories:performance` floor is **not** asserted; see "Why the performance score is not a gate" below. |
| PERF-03, baseline regression check | Applies, enforced | `scripts/check_perf_baseline.py`, run by `make perf` inside `make verify`. |
| PERF-04, baseline currency | Applies, review | The ritual below, plus the pull-request checklist. |
| PERF-05, intentional-regression sign-off | Applies, review | Solo-maintainer disposition: the regression is named in the pull request that carries it, and `perf/baseline.json` moves in that same pull request. |

## The budgets

| Budget | Value | Whose value | Asserted by |
|---|---|---|---|
| JavaScript on the published trace | none, inline or external | this project's | `scripts/a11y.mjs`, a `<script>` element count; and `lighthouserc.cjs`, `resource-summary:script:size` |
| Stylesheet and third-party bytes | 0 | this project's | `lighthouserc.cjs`, `resource-summary:{stylesheet,third-party}:size` |
| Total transfer weight of the trace | at most 51 200 bytes | this project's | `lighthouserc.cjs`, `resource-summary:total:size` |
| Regression against `baseline.json` | at most 10% worse, per metric, in its declared direction | the standard's | `scripts/check_perf_baseline.py` |
| Lighthouse performance score | recorded, not gated | — | measured every run, printed by `make perf`, fails nothing |

## Why the performance score is not a gate

It was one, and it was the wrong kind of number to gate on.

`categories:performance` is a simulated-throttling timing score of whatever
machine ran Lighthouse. This section first stated that spread from three
observations. Every score the repository has recorded is below, so that the claim
about the distribution rests on the distribution.

`make perf` prints the score on every run, pass or fail, so the `verify` job is a
complete record; Lighthouse-CI in the `accessibility` job prints one only when its
assertion fails, so that job contributes its failures and nothing else. Both were
read from the job logs of every `ci` run between 2026-08-28, when the gate landed,
and 2026-09-06, including the first attempt of each re-run run.

| Score | Observations | Against the old gate |
|---|---|---|
| 1.00 | 26 | passes |
| 0.99 | 3 | passes |
| 0.94 | 1 | passes |
| 0.89 | 1 | below the 0.90 floor, and 11% below the baseline |
| 0.87 | 1 | below the 0.90 floor, and 13% below the baseline |
| 0.81 | 1 | below the 0.90 floor, and 19% below the baseline |
| 0.77 | 1 | below the 0.90 floor, and 23% below the baseline |

Thirty-four observations, 0.77 to 1.00, four of them below the floor. Both halves
of the old gate — Lighthouse-CI's 0.90 floor and the 10% band around a 1.00
baseline, which also lands on 0.90 — sit inside that spread.

The spread is not only between commits. Each `ci` run audits the same generated
page twice, once in `verify` and once in `accessibility`, minutes apart on the
same runner image, and the two disagree:

| CI run | Commit's `verify` audit | Commit's `accessibility` audit |
|---|---|---|
| 33581078870 | 1.00 | **0.81**, failed |
| 33582650956 | 1.00 | **0.77**, failed |
| 33591194873 | **0.87**, failed | passed |
| 34034962101 | **0.89**, failed | passed |

Two audits of one artifact in one workflow run, 0.19 apart. And the last of those
is after the fact: 34034962101 is a pull request opened on 2026-09-06 whose diff
touched only the `Dockerfile` and this repository's changelog, nothing the trace
loads, and it scored 0.89 — while the next run of the same branch nine minutes
later scored 1.00.

So `main` went red for a reason no diff had caused and no diff could fix, and
re-baselining to 0.87 would only have rescheduled the same failure at a lower
number — as 0.81 and 0.77 already show, both of them below anything a re-baseline
would plausibly have chosen.

What replaces it is a set of budgets on what the artifact *is* rather than on how
fast a contended runner painted it: its transferred bytes, its subresource
counts, and the absence of JavaScript. Those measured 2469 total bytes and zero
of everything else on every run on every machine tried. For a static document
with no scripts, no stylesheets and no third-party requests, that *is* what "fast
for a funder" reduces to; the timing score was only ever a proxy for it.

The score is still collected every run, still recorded in `baseline.json`, and
still printed by `make perf` — labelled "observed, not scored", with the reason.
`scripts/check_perf_baseline.py` declares the exclusion in `OBSERVED_NOT_GATED`
rather than achieving it by quietly not measuring the metric, so a reader can
tell the difference between a number nobody scores and a number nobody noticed
had stopped being scored.

One thing this cost, and how it was paid back. `resource-summary:script:size` is
a budget on script *requests*, so it never sees an inline `<script>`: injecting
1216 bytes of inline JavaScript into the trace left that row reading 0 and moved
the compressed document by 26 bytes, passing both the Lighthouse assertion and
the 10% band. The budget this directory publishes is "the trace ships no
JavaScript", so `scripts/a11y.mjs` now counts `<script>` elements and fails on
any, inline or external. That check catches the injection both byte budgets
missed.

## The other budgets

The script budget is deliberately tighter than the standard's 204 800-byte
critical-path figure. That figure is sized for a frontend. The trace here is a
document a funder opens from a file or an attachment, and the project ships no
web application and no network ingress, so the honest budget for script bytes in
a published artifact is none at all. At 204 800 the assertion could not have
failed until someone had already shipped 200 KB of JavaScript into a funder's
browser; at 0 it fails on the first byte of an external script, and the
`<script>`-element check in `scripts/a11y.mjs` fails on the first byte of an
inline one.

## The baseline

`baseline.json` carries `meta` (the commit, date, environment and tool versions
the numbers were measured at, so they can be re-verified), `metrics` (the
measured values, with an explicit `null` for each metric this project has no
route to measure, never a silent absence) and `direction` (so the comparison is
mechanical rather than a judgement each time).

`total_kb_gzip` is 2.4111328125 — the 2469 transferred bytes of the generated
trace, which reproduced exactly on every run and every machine tried. It is the
metric that carries the weight the performance score used to: 10% above it is
2.652 KB, so a real content regression fails. Injecting 1500 incompressible bytes
into the trace takes it to 3.958 KB and `make perf` exits 1.

`lighthouse_performance` is recorded at 1.00, the best the page has been observed
to do, and is deliberately *not* scored — see "Why the performance score is not a
gate" above. It stays in the file because `docs/ROADMAP.md` publishes it and
`scripts/check_conformance.py` cross-checks the two, so the published figure
still cannot drift from the receipted one.

`p95_ms`, `llm_first_token_ms` and `llm_full_response_ms` are `null`: there is no
hosted route and no model in the default path. They are declared N/A here, and
the check skips a `null` metric while failing on a metric it measures that the
baseline never declared, because an undeclared metric is one nobody decided
about.

## Running it

```sh
make a11y     # generates the trace and runs Lighthouse, asserting the budgets
make perf     # compares that run's report against baseline.json
```

`make verify` runs both, in that order. `make perf` reads the report `make a11y`
produced rather than taking a second measurement, because the standard requires
one Lighthouse configuration per repository and two runs would be two numbers.
It refuses a report older than the trace it would be scored against, and refuses
when there is no report at all, so a Lighthouse run that failed cannot leave a
stale green behind it.

## Updating the baseline

| Case | Who | How |
|---|---|---|
| The numbers got better | the author | Update `baseline.json` in the same pull request. Ratchet forward. No sign-off. |
| An intentional regression | the author, with owner sign-off | The pull request names the regression and moves `baseline.json` in the same change. The diff is the audit trail. |
| An unintentional regression | nobody | Not an update case. Fix the code. The baseline does not move to make red turn green. |
| The environment or a tool changed | the author | Re-measure, update `meta.tools`/`meta.environment` and the metrics together, in one pull request titled as a re-baseline, with the before and after numbers in its description. |
