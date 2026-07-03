# CI action: gate on receipt drift

`outcome-receipts` ships a reusable [composite GitHub Action](../action.yml) so a
downstream repository can gate its CI on receipt drift. The action installs the
`receipts` CLI and runs `receipts verify`, which re-derives every figure in a
receipts manifest from its spec and data. If any receipt no longer matches — the
data changed, the spec changed, or the manifest was tampered with — the CLI exits
non-zero and the job fails. The gate fails closed; there is no "warn only" mode.

## Usage

Add a workflow to the repository that stores your report spec, data, and the
committed `receipts.json` manifest:

```yaml
# .github/workflows/receipts.yml
name: receipts

on:
  push:
    branches: [main]
  pull_request:

# Least-privilege token: verification only reads the checked-out tree.
permissions:
  contents: read

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          persist-credentials: false
      - name: Verify receipts
        uses: ChelseaKR/outcome-receipts@v1
        with:
          config: reports/housing/report.toml
          receipts: reports/housing/receipts.json
```

The manifest is produced by `receipts run --config <spec> --out <dir>` (it writes
`receipts.json` into the output directory); commit it next to the spec and data it
was derived from. On every push and pull request the action re-derives the figures
and fails the job if the committed manifest has drifted.

## Inputs

| Input      | Required | Default  | Description |
|------------|----------|----------|-------------|
| `config`   | yes      | —        | Path to the report spec TOML. Mirrors the CLI's `--config`. |
| `receipts` | yes      | —        | Path to the `receipts.json` manifest to verify. Mirrors the CLI's `--receipts`. |
| `version`  | no       | `main`   | Git ref (branch, tag, or commit SHA) of `ChelseaKR/outcome-receipts` to install. |

## Pinning for supply-chain hardening

Two independent references are worth pinning, and they harden different things:

- **The action reference** (`uses: ChelseaKR/outcome-receipts@...`) selects which
  `action.yml` and step definitions run. For reproducible, tamper-evident runs,
  pin it to a full commit SHA with a version comment rather than a moving tag:

  ```yaml
  - uses: ChelseaKR/outcome-receipts@<commit-sha> # v1
  ```

- **The `version` input** selects which CLI package the action installs. It
  defaults to `main` for convenience; pin it to a released tag or a commit SHA so
  the verifier that runs in CI is itself reproducible:

  ```yaml
  with:
    config: reports/housing/report.toml
    receipts: reports/housing/receipts.json
    version: v0.1.0
  ```

This mirrors the convention used inside this repository, where third-party
actions in [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) are pinned to
commit SHAs with a trailing `# vN` comment.

## Permissions

The action only reads the checked-out tree, so grant it the least-privilege token:

```yaml
permissions:
  contents: read
```
