# OpenSSF Scorecard review — 2026-08-21

Scorecard v5.3.0, run by the repository's own `scorecard` GitHub Actions
workflow against commit `ced739f61c70dd0aebda068d1a1bca6fc97ad334` on `main`
(run [32509036996](https://github.com/ChelseaKR/outcome-receipts/actions/runs/32509036996),
2026-08-21T17:36:34Z): **aggregate 7.1**, up from 6.8 in the
[2026-07-12 report](openssf-scorecard-2026-07-12.md).

| Check | Score | Finding |
|---|---:|---|
| Binary-Artifacts | 10 | No binaries found in the repo. |
| Branch-Protection | 4 | Pull request, strict checks, signatures, linear history, and deletion/force-push blocks are required; independent approval is zero under [ADR 0002](../adr/0002-solo-maintainer-review-count.md) (WVR-005). |
| CI-Tests | 10 | 30 of the last 30 merged PRs were checked by a CI test. |
| CII-Best-Practices | 0 | No OpenSSF Best Practices badge has been pursued. This is a decision, not a finding: applying for the badge is unstarted work, not a defect to fix silently. |
| Code-Review | 0 | 0 of 30 changesets carry an independent approval — a solo-maintainer repository has no second reviewer to provide one. |
| Contributors | 3 | One contributing organization. |
| Dangerous-Workflow | 10 | No dangerous workflow pattern detected. |
| Dependency-Update-Tool | 10 | Renovate detected (`renovate.json`). |
| Fuzzing | 0 | Not adopted. Property and mutation tests cover the invariant core (`grounding.py`, `engine.py`) but Scorecard does not recognize either as fuzzing. |
| License | 10 | License file detected. |
| Maintained | 0 | OpenSSF assigns zero to a repository under 90 days old. First commit 2026-06-27; this structurally clears on or about **2026-09-25**. |
| Packaging | 10 | Packaging workflow detected. |
| Pinned-Dependencies | 10 | All workflow dependencies are full SHAs. |
| SAST | 7 | SAST tool detected but not run on every commit. This is the check the 2026-07-12 report could not measure yet (its CodeQL/Semgrep changes were not on `main` at the time); it is now on `main` and measuring 7, not the placeholder 0 the July report recorded. |
| Security-Policy | 10 | `SECURITY.md` detected with disclosure, vulnerability, and timeline content. |
| Signed-Releases | 10 | 2 of the last 2 releases carry a total of 2 signed artifacts. |
| Token-Permissions | 10 | GitHub workflow tokens follow least privilege. |
| Vulnerabilities | 10 | 0 existing vulnerabilities detected. (The 2026-07-12 report's successor measurement recorded 9 here for the since-retired extract-zip advisory, WVR-007; that advisory's package was removed from the dependency graph in #99, which is why this is 10 again.) |

## What changed since 2026-07-12

- **SAST 0 → 7.** The July report couldn't measure this: "the new CodeQL/Semgrep
  workflow changes are not on `main` yet." They merged since, and this is the
  real measured score, not a re-run of the same placeholder.
- **Vulnerabilities: 10, clean.** The extract-zip advisory (GHSA-jmr9-qjv8-65gv,
  WVR-007) that would have scored this 9 on an intermediate measurement was
  resolved by removing the package from the dependency graph (#99); WVR-007 is
  retired.
- **Aggregate 6.8 → 7.1**, driven entirely by SAST — every other check is
  unchanged from July.

## Two zeros that are structural, not earned

- **Maintained (0):** purely a function of repository age. Scorecard assigns
  zero to any repository under 90 days old regardless of activity level. This
  clears on or about 2026-09-25 (90 days from the 2026-06-27 first commit) and
  requires no repository change to resolve.
- **CII-Best-Practices (0):** a decision not yet made, not a finding. Pursuing
  the OpenSSF Best Practices badge is unstarted, optional work; it is recorded
  here so the zero reads as "not pursued" rather than "failed."

Code-Review (0), Contributors (3), and Fuzzing (0) are the same solo-maintainer
and scope-appropriate reasons the July report gave, unchanged.

## Waivers

- **WVR-005** (Branch-Protection, capped at 4): unchanged, still governed by
  ADR 0002.
- **WVR-006** (SEC-37 aggregate floor, portfolio standard 8.0): re-justified
  against this report. The waived floor moves from 6.8 to 7.1 and the
  `scorecard` workflow's enforced floor (`.github/workflows/scorecard.yml`)
  ratchets from `>= 6.8` to `>= 7.0` — one tenth below the exact measurement,
  so routine Scorecard measurement noise doesn't fail the gate, while still
  disallowing a silent regression back toward the old floor. **Shortened, not
  extended**: expiry moves to 2026-09-25, the date the Maintained-score's
  stated premise (repository age) stops applying, rather than coasting to the
  original 2026-10-15 on numbers that will be stale before then. This is not
  expected to retire the waiver outright: Code-Review, CII-Best-Practices, and
  Fuzzing are structural to a solo-maintainer repository and will likely still
  hold the aggregate below the portfolio's 8.0 target after Maintained clears,
  so a fresh re-measurement and a re-justified (likely renewed, not removed)
  WVR-006 is the expected outcome at expiry, not an assumption that the
  aggregate reaches 8.0 unassisted.

## Recheck

Owner: Chelsea Kelly-Reif. Recheck monthly (SEC-38), and specifically on or
after 2026-09-25 when WVR-006 expires and the Maintained-score premise
changes.
