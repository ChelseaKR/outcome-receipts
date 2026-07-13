# Operations runbook

This is an offline CLI, not a hosted service. Operational work is therefore about
protecting local source data, verifying exports, and responding to integrity or
secret incidents.

## Failed report or verification

1. Preserve the input CSV, TOML spec, output bundle, and command output. Do not
   paste client rows into an issue or chat.
2. Run `receipts verify --config REPORT.toml --receipts receipts.json` and
   `receipts verify-bundle --bundle bundle.json` against copies in a scratch
   directory.
3. If a numeric span is unbound, a cell is recoverable, or a bundle digest drifts,
   stop distribution. Recompute from the authoritative source and require a new
   human approval. Never edit a receipt to make it match prose.
4. For a product defect, open a minimal synthetic reproduction. For a grounding,
   suppression, or integrity bypass, use the private channel in `SECURITY.md`.

## Backup and recovery

The application creates no durable client database. The organization's system of
record remains authoritative. Back up the report spec, source export under the
organization's retention policy, report directory, signing key if used, and
export ledger together. Recovery is a copy into a scratch directory followed by
`receipts verify`, `receipts verify-bundle`, and `receipts verify-ledger` before
the restored artifact is trusted.

## Secret exposure

1. Stop the affected workflow or local process and preserve timestamps.
2. Rotate and revoke the credential at its provider before investigating cause.
3. Search the full git history and release assets with gitleaks. Treat a deleted
   working-tree value as exposed until history and caches are assessed.
4. Decide whether to history-scrub based on whether the secret itself or protected
   client data remains retrievable. Rotation is mandatory even if history is
   rewritten.
5. Open a private advisory, label the tracking issue `incident` plus severity, and
   document any L2/L3 data exposure, retention impact, and notification decision.
6. Commit the postmortem under `docs/incidents/` before the next release.

## Release recovery

A released version is immutable. Yank a defective PyPI version when necessary,
record the reason in CHANGELOG, and ship a new patch. Never move or reuse a tag.

*Last verified: 2026-07-12 · Recheck: after any incident or release-process change.*
