# Contributing to outcome-receipts

Thanks for your interest. outcome-receipts is an independent personal open-source project
(Apache-2.0, unaffiliated with any employer or client). It is a reference implementation: the
bar is high on purpose, because the point of the repo is to show provenance rigor that is
mechanically enforced rather than asserted.

The cross-cutting rigor (the coverage bar, the merge-gate model, the security posture, the
release pipeline) lives once in the portfolio `STANDARDS/` set and is referenced here, not
restated. The [README "Standards conformance" table](README.md#standards-conformance) records
how each standard maps to this repo.

## The one command that proves it: `make verify`

```sh
make install        # complete locked Python, Node/browser, and security toolchain
make verify         # the local mirror of the CI gate
```

`make verify` runs format/lint, strict typing, tests and coverage, source and
documentation hygiene, gettext parity, dependency/SAST/secret/workflow scans,
generated-HTML accessibility checks, generated-card drift, and the committed
eval/benchmark drift check. CI invokes the same targets. The active main ruleset
blocks force-push/deletion, requires pull requests and strict status checks, and
requires signed linear history. Keep branch coverage at or above 90%, with 95%
on the declared integrity-critical modules.

Individual targets include `make lint`, `make type`, `make test`, `make security`,
`make i18n`, `make a11y`, `make eval`, `make run`, and `make clean`.

## Branch model

Work on a short-lived topic branch cut from `main`, one logical change per branch,
and open a pull request back into `main`. The active `protect-main` ruleset blocks
force-pushes and branch deletion and requires the `verify`, `security`, and
`accessibility` checks. It does not currently require a pull request because the
repository has one maintainer, so direct pushes remain prohibited by project
policy rather than by GitHub. Every gate must be green before merge.

## Commit messages

Every commit and PR title follows [Conventional Commits 1.0.0](https://www.conventionalcommits.org/):

```
<type>(<scope>): <imperative summary>

<body — what and why, not how>

Signed-off-by: Your Name <you@example.com>
```

Types: `feat`, `fix`, `docs`, `refactor`, `test`, `build`, `ci`, `chore`, `perf`, `revert`.
Scopes track the pipeline stages and modules: `engine`, `grounding`, `draft`, `charts`,
`comparison`, `provenance`, `trace`, `verify`, `eval`, `cli`, `docs`. Conventional Commits
drafts the changelog, but a human curates the released section; a commit dump is not a
changelog.

## DCO sign-off (required)

Contributions are accepted under the
[Developer Certificate of Origin 1.1](https://developercertificate.org/). Sign off every
commit so the certification is on record:

```sh
git commit -s -m "feat(grounding): bind comparison-change numbers to receipts"
```

`-s` appends the `Signed-off-by:` trailer matching your `git config user.name` /
`user.email`. If you forgot, `git commit --amend -s` (or `git rebase --signoff main` for a
series) fixes it. By signing off you certify you wrote the contribution or have the right to
submit it under the project's Apache-2.0 license.

## Pull requests

Before requesting review:

- [ ] `make verify` is green locally (`ruff`, `mypy --strict`, `pytest`).
- [ ] Tests are added or updated for the change.
- [ ] If behavior changed, the eval report is regenerated (`make eval`) and
      `eval/report.md` is committed, so CI's `git diff --exit-code` passes.
- [ ] `CHANGELOG.md` `[Unreleased]` is updated.
- [ ] If a load-bearing guardrail changed (see below), an ADR under
      [`docs/adr/`](docs/adr/) is linked and the change is called out.

Solo-maintainer note: the "at least one review" expectation from the portfolio Code Quality
standard is met by a recorded self-review pass plus every gate green. The point is that the
checks ran and were acknowledged, not headcount. New ADRs use MADR under `docs/adr/`;
`docs/decisions/` is the read-only historic log.

## The invariants (do not weaken these)

These are load-bearing. Changing one is deliberate, reviewed, and recorded in an ADR.

- **Numbers never come from a model.** Figures come from SQL queries; the drafter
  ([`src/outcome_receipts/draft.py`](src/outcome_receipts/draft.py)) fills a template's
  placeholders and writes no number of its own.
- **The grounding gate is fail-closed.** Every number in the narrative, and in any chart or
  comparison, must bind to a figure's receipt; an unbound number blocks export. This is the
  merge-blocking invariant in
  [`src/outcome_receipts/grounding.py`](src/outcome_receipts/grounding.py), covered by
  `tests/test_grounding_gate.py` and `tests/test_grounded_sections.py`. Do not add a path
  that exports around the gate.
- **Small-cell suppression is a privacy invariant (v0.2).** Aggregate outcome counts below
  the suppression threshold (default `n < 11`) are suppressed in every export, with
  complementary suppression so a suppressed cell cannot be recovered by subtraction. It is a
  configurable value, not a hard-coded one, and it is not a claim of statistical-disclosure
  compliance. When it lands it is merge-blocking; do not weaken it.
- **Determinism.** The v0.1 path is network-free and seeded (an injected clock) so a committed
  run and its eval report are reproducible for identical inputs. Anything needing a cloud
  account (the future drafting seam) goes behind a config switch and must not be required for
  `make verify`.

## Security issues

Do not open a public issue for a vulnerability. Follow [`SECURITY.md`](SECURITY.md) for
private, coordinated disclosure.

## Code of Conduct

This project follows the [Contributor Covenant](CODE_OF_CONDUCT.md). By participating you agree
to uphold it.

---

*Maintainer: Chelsea Kelly-Reif · License: Apache-2.0 · Not legal, accounting, or compliance advice.*
