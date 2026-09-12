# Adopt the shared portfolio release authorization workflow

- Status: Accepted
- Date: 2026-08-07
- Deciders: Chelsea Kelly-Reif

## Context

`release.yml` previously combined tag verification and GitHub release
publication: the tag was checked through the GitHub API (annotated, carries a
signature, points at the verified commit), and the job that created the GitHub
release also checked out and executed repository code while holding
`contents: write`. The portfolio Release & Versioning standard (§4, §4.1) now
prescribes a trusted-main, split-authority shape: release authority comes from
the reviewed workflow on `main` via `workflow_dispatch`, the tag signature is
verified locally against a committed allowed-signers file, the tagged commit is
proven reachable from `origin/main`, and the write-authorized publication job
never checks out repository code and re-compares the live tag object
immediately before publishing. The portfolio publishes a reusable
`release-authorize.yml` workflow that centralizes that trust step and returns
immutable identifiers.

## Decision

- The release trigger is `workflow_dispatch` with the signed tag as an input.
  The tag-push trigger is removed because a tag-push run executes the workflow
  definition stored at the tagged ref rather than the reviewed one on `main`.
- An `authorize` job calls
  `ChelseaKR/portfolio-standards/.github/workflows/release-authorize.yml`,
  pinned to a full 40-character commit SHA. The committed
  `.github/allowed_signers` names the maintainer's SSH signing key, the same
  key that signed `v0.1.0`.
- Verification and build execute the authorized release commit with
  `contents: read`. GitHub release publication moves to a checkout-free
  `contents: write` job that re-checks the live tag object SHA against the
  authorizer output; the PyPI job performs the same recheck before Trusted
  Publishing.
- The GitHub release notes are the tag's own CHANGELOG section (REL-10),
  extracted in the build job because the publication job holds no checkout.

## Consequences

- A release is started with `git tag -s vX.Y.Z && git push origin vX.Y.Z`
  followed by `gh workflow run release.yml --ref main -f tag=vX.Y.Z`. Pushing
  a tag alone no longer starts a release run.
- A tag moved or re-pointed between authorization and publication fails closed
  in both publication jobs.
- Build, Sigstore attestation, SBOM generation, exact-byte artifact hand-off,
  and post-publication verification are unchanged. PyPI Trusted Publishing
  still binds to `release.yml` and the `pypi` environment, so no publisher
  reconfiguration is needed.
- Residual risk: tag immutability rests on signed-tag discipline and the
  registry's no-re-publish rule. A hosted tag-protection ruleset
  (`protect-release-tags` over `refs/tags/v*`, REL §3.1) is not yet configured
  on the repository; creating it is a hosted-settings change outside this
  repository's files and is recorded here rather than claimed.

## Note, 2026-09-08: where the reusable workflow is read from

The Decision above names
`ChelseaKR/portfolio-standards/.github/workflows/release-authorize.yml`. That
repository is **private**, and a public repository cannot call a reusable
workflow that lives in a private one — GitHub refuses at parse time and words
the refusal `workflow was not found`, which reads as a deleted file rather than
as a visibility rule. `release.yml` has called the public mirror
`ChelseaKR/.github/.github/workflows/release-authorize.yml` since 2026-08-08;
the Decision line was not updated with it, and `docs/RELEASING.md` was.

The decision itself is unchanged: authorization is still delegated to one
reviewed, centrally-owned workflow pinned by a full 40-character commit SHA.
Only the repository the bytes are read from moved, and the two copies are
byte-identical as of the pin below.

The pin is now `7be4c3e44e2acf20e8a98eeea4351c1e5d2789bc`, which is what the
signed tag `v1.0.0` of `ChelseaKR/.github` dereferences to. It replaces
`315a513ff3b4e7c5c0628428909052d947f4f1ab`, the commit that first hosted the
file publicly. Measured rather than assumed: the two blobs differ by exactly
one line, `timeout-minutes: 30` on the `authorize` job (3,014 bytes against
3,038). That job is the trust boundary — it resolves the release tag and
verifies its SSH signature — and without the line it inherits the six-hour
default, so this is a tightening. The earlier pin was also not a tag, which
pin-identity checks elsewhere in the portfolio reject.

This changes nothing about whether the workflow parses: the old pin was already
public, so this repository's release path was never blocked by the visibility
rule that blocked others. It bounds a job that was unbounded, and moves the pin
onto a tagged commit.
