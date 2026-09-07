# Releasing Outcome Receipts

Releases are a manual promotion of an already-reviewed commit on `main`. The
workflow never treats a tag push as authority to publish.

## Trust model

`.github/workflows/release.yml` splits release authority across six jobs so
that no single write-capable step both executes repository code and holds
publication credentials:

1. **`authorize`** calls the standards-owned reusable workflow
   `ChelseaKR/.github/.github/workflows/release-authorize.yml`, pinned to a
   full 40-character commit SHA. It validates a stable SemVer tag, verifies
   an SSH signature against the committed `.github/allowed_signers`, proves
   the tagged commit is reachable from current `origin/main`, and returns
   immutable identifiers (the authorized commit and the tag object SHA).
2. **`verify`** and **`build`** run with `contents: read` at the exact commit
   `authorize` returned. `verify` reruns `make verify` and the cards check;
   `build` produces the wheel/sdist, Sigstore build-provenance and SBOM
   attestations, and the CHANGELOG-derived release notes.
3. **`github-release`** is the only job with `contents: write`. It never
   checks out or executes repository code — it downloads the artifacts
   `build` uploaded, re-compares the live tag object SHA against
   `authorize`'s output, and publishes the GitHub release.
4. **`pypi-publish`** downloads only the attested `dist/` artifacts,
   re-verifies their digests against the manifest `build` recorded, repeats
   the tag-object recheck, and publishes to PyPI via Trusted Publishing (OIDC,
   no long-lived token).
5. **`verify-published`** confirms the published wheel's Sigstore attestation
   and smoke-tests the package pulled fresh from PyPI.

This separation means a job that can rebuild or execute repository source
never holds `contents: write`, and a job that holds `contents: write` never
rebuilds or executes repository source. `tests/test_release_workflow.py`
pins the shape described above so a future restructuring cannot regress it
silently — see ADR
[0005](adr/0005-adopt-shared-release-authorization.md) for the fuller
rationale and history.

## Prepare a release

1. Update **every place that carries the version**, in one pull request. This
   list is exhaustive as of `0.2.1`, and it is written out because a shorter
   version of this step is what produced the `0.2.1` drift: the promotion to
   `0.2.1` moved `CHANGELOG.md` alone, and `pyproject.toml` sat at `0.2.0`
   through a green `make verify`, a green `ci`, and a `release.yml` whose only
   version check was satisfied by that tree.

   | File | What moves |
   |---|---|
   | `CHANGELOG.md` | `## [Unreleased]` becomes `## [X.Y.Z] - <date>`, and a fresh empty `## [Unreleased]` opens above it |
   | `pyproject.toml` | `project.version` — this is what `uv build` stamps on the wheel |
   | `uv.lock` | the `outcome-receipts` editable-root entry's `version`; `make install` runs `uv lock --check`, which fails closed on the drift a bump creates |
   | `CITATION.cff` | `version` **and** `date-released` |
   | `README.md` | the status note, and its `Last verified:` stamp |
   | `docs/cards/` | regenerate: `uv run receipts cards --out docs/cards` |

   Three of those six are now checked against each other by
   `make release-version` (`CHANGELOG.md`, `pyproject.toml`, `CITATION.cff`),
   and `uv.lock` is caught by the `uv lock --check` that `make install` runs.
   The README prose and the cards are not machine-checked and are still read by
   a person.

   **After** the release is published, `action.yml`'s `version` input default
   and the places `docs/ci-action.md` restates it move to the new tag —
   separately, because that default names the newest tag a downstream consumer
   can install, which is not true until the release exists.
   `scripts/check_conformance.py` already fails when the action's default and
   the documentation disagree, so they move together or not at all.
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
   existing tag:

   ```sh
   gh workflow run release.yml --ref main -f tag=vX.Y.Z
   ```

   Do not select a feature branch — `workflow_dispatch` on `main` is the only
   trigger; pushing the tag alone starts nothing.
5. Confirm the GitHub release, attestation bundle, CycloneDX SBOM, and PyPI
   files all correspond to the same version and artifact digests.

The PyPI project must have a Trusted Publisher bound to repository
`ChelseaKR/outcome-receipts`, workflow `release.yml`, and environment `pypi`.
No long-lived PyPI token belongs in repository secrets.

## Failure and recovery

A failed run is safe to rerun with the same unchanged tag. Never move or
reuse a published tag. If verification fails, correct the source and version
in a new pull request and create a new version tag. If publication partially
succeeds, rerun only after confirming the tag object is unchanged; the
workflow replaces GitHub release assets with the same verified bytes, and
PyPI rejects an already-published filename outright.
