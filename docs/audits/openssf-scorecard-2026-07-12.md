# OpenSSF Scorecard review — 2026-07-12

Scorecard CLI 5.5.0 against the private GitHub repository after hardening and
attaching the v0.1.0 `.intoto.jsonl` bundle: aggregate 6.8.

| Check | Score | Finding |
|---|---:|---|
| Pinned-Dependencies | 10 | All workflow dependencies are full SHAs. |
| Token-Permissions | 10 | Default read; writes are job-scoped. |
| Dangerous-Workflow | 10 | No dangerous workflow pattern detected. |
| Signed-Releases | 10 | The single release exposes a signed attestation bundle. |
| Vulnerabilities | 10 | No existing vulnerability detected. |
| Dependency-Update-Tool | 10 | Renovate with a 72-hour minimum release age. |
| Branch-Protection | 4 | Pull request, strict checks, signatures, linear history, deletion/force-push blocks, and no bypass; independent approval is zero under ADR 0002. |
| SAST | 0 | The new CodeQL/Semgrep workflow changes are not on `main` yet; remeasure after merge. |
| Code-Review | 0 | Historic changes have no independent approvals in a one-maintainer repo. |
| Maintained | 0 | OpenSSF assigns zero to a repository less than 90 days old. |
| Fuzzing / CII Best Practices | 0 / 0 | Not adopted; property/mutation tests cover the invariant core but are not Scorecard-recognized fuzzing. |

**Correction, 2026-08-28.** The Branch-Protection row above ends "and no
bypass". That is no longer a true description of this repository and must not
be read as a security property it holds: the live `protect-main` ruleset (id
`18752852`, last updated 2026-08-26) carries the repository owner's standing
bypass, `RepositoryRole` 5 with `bypass_mode: always`. It is kept deliberately
and permanently, because an agent once applied a ruleset with no bypass and
locked the owner out of their own repository, and restoring access took a
sweep across eighteen repositories. The finding is left as it was written
rather than edited, and the score is unaffected: Scorecard caps
Branch-Protection here on the solo-maintainer approval count (WVR-005), not on
bypass actors. See `docs/rulesets/README.md`, "Why the owner can bypass". The
same correction applies to the same claim in
`docs/CONFORMANCE-AUDIT-2026-07-12.md`.

WVR-005 covers the solo-maintainer Branch-Protection score. WVR-006 covers the
age/history-constrained aggregate and expires after the 90-day mark. The workflow
fails on any regression below 6.8 and keeps Pinned-Dependencies, Token-Permissions,
Dangerous-Workflow, Signed-Releases, and Vulnerabilities at their full targets.

Owner: Chelsea Kelly-Reif. Recheck monthly, after the hardening changes reach
main, and before either waiver expires.
