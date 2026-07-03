# 0004 — Whole-bundle verification

Status: accepted

## Context

`receipts verify` (ADR 0003) re-derives every receipt from the spec and data and
checks it against the manifest. That proves the figures still hold, but it says
nothing about the rest of the bundle `run` exports. Nothing checks that the
adjacent `report.md` still binds every number to a receipt, that `trace.html`
matches, or that a chart SVG was not swapped for a different image after export.
The three artifacts are not linked; the provenance record is a self-asserted JSON
field. Signing a bundle (a later step) is only meaningful once its internal
cross-references exist, so this precedes it.

## Decision

### The manifest records a digest of each sibling artifact

At export, `receipts_manifest` gains an optional `artifacts` key: a mapping of
bundle-relative path to the sha256 hex digest of that file's UTF-8 bytes. `run`
records `report.md`, `trace.html`, and each chart SVG (`charts/{id}.svg`). The map
is written sorted for determinism, alongside the existing `sort_keys`/`indent`
settings, so a reproducible run yields a byte-identical manifest.

### The hash relation is one-directional; the manifest never hashes itself

The report embeds the receipts section but not the artifact digests, and the
manifest hashes the report but not itself. So the dependency runs one way —
report and trace and charts are inputs to the manifest, and the manifest is an
input to nothing it also hashes — and there is no circularity to resolve. A
consumer verifies the report, trace, and charts against the manifest; the manifest
itself is trusted as the root, exactly as with any digest list.

### Write order: charts, then report, then trace, then the manifest

`_cmd_run` builds the report, trace, and each chart SVG as strings in memory,
computes their digests, then writes charts, `report.md`, `trace.html`, and finally
`receipts.json`. The manifest is written last so it can hash its siblings; because
nothing hashes the manifest, its own content need not exist when the others are
hashed.

### `verify --bundle` checks the whole bundle, fail-closed

`receipts verify --bundle <dir>` re-runs the per-receipt re-derivation, then reads
each file named under `artifacts`, recomputes its sha256, and reports a failure
naming the file when a digest differs or the file is missing. It also re-runs the
grounding gate over the exported narrative (the region of `report.md` after the
title, up to the first `##` section), so a number that no longer binds to a
receipt fails the check. A manifest with no `artifacts` key is an error, not a
pass. `--receipts` and `--bundle` are mutually exclusive; editing one character of
any exported artifact makes `verify --bundle` exit non-zero naming the file.

## Consequences

- Verification covers the exported bundle, not just the figures: a swapped SVG, a
  hand-edited `report.md`, or an ungrounded number in the narrative is caught.
- `receipts_manifest` takes an optional `artifacts` argument and omits the key
  when it is absent, so existing callers and tests are unaffected.
- The grounding gate is now enforced twice — once at export, once at verify — over
  the same narrative region, so drift between the exported prose and its receipts
  cannot pass silently.
- Signing a bundle (a later ADR) can sign the manifest alone, since the manifest
  already commits to every other artifact by digest.
