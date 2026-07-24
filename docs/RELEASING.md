# Releasing Outcome Receipts

Releases are a manual promotion of an already-reviewed commit on `main`. The
workflow never treats a tag push as authority to publish.

## Trust model

The release workflow has three distinct authorities:

1. `verify-build` has read-only repository access. It starts from the exact
   hosted `main` commit selected by `workflow_dispatch`, validates a stable
   SemVer tag, requires an annotated SSH signature from
   `.github/allowed_signers`, proves the tag is on reviewed `main` history,
   reruns `make verify`, and builds the distributions and SBOM.
2. `publish-release` has release and attestation write access but never checks
   out repository code. It downloads only the verified artifacts and rechecks
   that the hosted tag object still has the SHA observed by the read-only job.
3. `pypi-publish` receives only the verified wheel and source distribution and
   uses PyPI Trusted Publishing. It has no repository checkout or build tools.

This separation prevents a write-capable job from rebuilding or executing
repository source after the verification boundary.

## Prepare a release

1. Update `pyproject.toml`, `CHANGELOG.md`, generated cards, and any dated
   release evidence in one pull request.
2. Merge only after the complete `make verify` gate passes.
3. On current `main`, create an SSH-signed annotated tag:

   ```sh
   git switch main
   git pull --ff-only
   git tag -s vX.Y.Z -m "outcome-receipts vX.Y.Z"
   git verify-tag vX.Y.Z
   git push origin vX.Y.Z
   ```

4. In GitHub Actions, run the `release` workflow from `main` and supply the
   existing tag. Do not select a feature branch.
5. Confirm the GitHub release, attestation bundle, CycloneDX SBOM, and PyPI
   files all correspond to the same version and artifact digests.

The PyPI project must have a Trusted Publisher bound to repository
`ChelseaKR/outcome-receipts`, workflow `release.yml`, and environment `pypi`.
No long-lived PyPI token belongs in repository secrets.

## Failure and recovery

A failed run is safe to rerun with the same unchanged tag. Never move or reuse a
published tag. If verification fails, correct the source and version in a new
pull request and create a new version tag. If publication partially succeeds,
rerun only after confirming the tag object is unchanged; the workflow replaces
GitHub release assets with the same verified bytes and PyPI rejects an already
published filename.
