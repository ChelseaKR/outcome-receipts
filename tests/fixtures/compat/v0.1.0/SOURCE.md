# v0.1.0 compatibility baseline

- Tag: `v0.1.0`
- Commit: `51d18fc4cdd9f9dcd91dd4588ededc80a6b6bb7d`
- Release date: 2026-07-11
- Frozen paths:
  - `examples/housing-demo/report.toml`
  - `examples/housing-demo/services.csv`
  - `examples/housing-demo/receipts.json`

These files are byte-for-byte copies from the signed tag. They contain only the
repository's synthetic housing fixture. Current tests load the unversioned beta
spec, recompute and suppress its figures, and verify the tagged receipt manifest.
Do not regenerate this directory from `main`.
