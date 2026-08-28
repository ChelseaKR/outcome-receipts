# Performance budgets and the committed baseline

Last verified: 2026-08-27 · Recheck cadence: quarterly and on any change to the
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
| PERF-02, Lighthouse score and bundle budgets | Applies, enforced | `lighthouserc.cjs` asserts them on the generated trace during `make a11y`. |
| PERF-03, baseline regression check | Applies, enforced | `scripts/check_perf_baseline.py`, run by `make perf` inside `make verify`. |
| PERF-04, baseline currency | Applies, review | The ritual below, plus the pull-request checklist. |
| PERF-05, intentional-regression sign-off | Applies, review | Solo-maintainer disposition: the regression is named in the pull request that carries it, and `perf/baseline.json` moves in that same pull request. |

## The budgets

| Budget | Value | Whose value | Asserted by |
|---|---|---|---|
| Lighthouse performance score | at least 0.9 | the standard's | `lighthouserc.cjs`, `categories:performance` |
| Script bytes on the published trace | 0 | this project's | `lighthouserc.cjs`, `resource-summary:script:size` |
| Regression against `baseline.json` | at most 10% worse, per metric, in its declared direction | the standard's | `scripts/check_perf_baseline.py` |

The script budget is deliberately tighter than the standard's 204 800-byte
critical-path figure. That figure is sized for a frontend. The trace here is a
document a funder opens from a file or an attachment, and the project ships no
web application and no network ingress, so the honest budget for script bytes in
a published artifact is none at all. At 204 800 the assertion could not have
failed until someone had already shipped 200 KB of JavaScript into a funder's
browser; at 0 it fails on the first byte. A 1 KB script injected into the trace
takes the measurement to 0.411 KB, which fails both the Lighthouse assertion and
the regression check.

## The baseline

`baseline.json` carries `meta` (the commit, date, environment and tool versions
the numbers were measured at, so they can be re-verified), `metrics` (the
measured values, with an explicit `null` for each metric this project has no
route to measure, never a silent absence) and `direction` (so the comparison is
mechanical rather than a judgement each time).

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
