# 0004 — Receipt canonicalization and a versioned manifest schema

Status: accepted (working tree, uncommitted)

## Context

A receipt is only worth trusting if it can be re-derived, and a `receipts.json`
manifest is only useful to another tool if that tool knows exactly what it is
reading and how each `slice_hash` was produced. v0.1 shipped the manifest with no
version marker and no description of the hash, and the slice hash was computed over
the row values alone. Two gaps follow. First, a renamed column with identical
values hashed identically: a slice of `[["permanent"], ["temporary"]]` under a
column named `dest` and the same values under a column named `outcome` were
indistinguishable, so a schema change that a funder should see could slip past
re-derivation. Second, when the canonicalization or hash algorithm changes, every
hash changes; without a version marker a consumer sees a wave of opaque drift and
cannot tell a deliberate schema bump from tampering.

This ADR formalizes and versions the manifest schema, makes the slice hash
schema-aware, and records the canonicalization rules so a second implementation
could reproduce a hash byte for byte. It stays within v0.1's constraint of zero
third-party runtime dependencies (`pyproject` `dependencies = []`).

## Decisions

### The slice hash is canonicalized, and canonicalization is versioned as `v1`

A slice is turned into hashed bytes by a fixed rule set, named `v1`:

- **Per-value stringification.** Every cell is rendered with `str(value)`, so the
  hash is stable regardless of SQLite's column typing (all columns load as text,
  but a `CAST` in the metric SQL can surface an integer or float).
- **Row sorting.** The stringified rows are sorted, so the hash does not depend on
  the query's row order. A metric with no `ORDER BY` still hashes deterministically.
- **Sorted column names.** The slice's column names are sorted and folded into the
  payload alongside the rows. This is the change from v0's rows-only payload: a
  rename of a column, with identical values, now changes the hash. Names are sorted
  for the same reason rows are — the hash attests to the *set* of columns present,
  not the incidental order a `SELECT *` returned them in.
- **Compact JSON.** The payload is `{"columns": [...], "rows": [[...]]}` serialized
  with `json.dumps(..., separators=(",", ":"), ensure_ascii=False)`, then encoded
  UTF-8. Separators are pinned so whitespace never enters the digest.

The digest is BLAKE2b with a 32-byte digest size, rendered as a lowercase hex
string. Both are recorded in the manifest (see below) so a consumer need not read
the engine to re-derive.

### `EMPTY_SLICE_HASH` semantics are preserved

A slice with **zero rows** returns the all-zero sentinel `EMPTY_SLICE_HASH`
regardless of its columns. This preserves the v0.1 invariant that an empty slice is
a single, visible value rather than being folded into a normal hash — an empty
result set is a fact a reviewer should see, not something that silently coincides
with other data. The alternative — folding column names in even for an empty slice,
producing a family of column-dependent empty hashes — was rejected because it trades
that visible invariant for a distinction (empty-under-these-columns) that carries no
figure. Columns are hashed only when there is at least one row.

### The manifest is versioned and self-describing about its hash

`receipts.json` gains two top-level keys, emitted before the `receipts` array with
`sort_keys=True` output kept stable:

- `schema_version` — the manifest schema version, `"1.0"`. Bumped when the shape of
  the manifest or the meaning of a field changes in a way a consumer or the
  re-derivation check must know about.
- `hash` — `{"algorithm": "blake2b", "digest_size": 32, "canonicalization": "v1"}`,
  describing exactly how every `slice_hash` was produced.

Each receipt also carries `column_names` (the slice's columns in query order), so a
receipt is self-describing about what was hashed and a renamed column is visible in
the manifest itself, not only in a changed hash.

`verify` checks `schema_version` and the `hash` descriptor against the current
constants **before** re-deriving any per-receipt field, and reports a mismatch as a
named failure (`schema_version: manifest '0.9' != expected '1.0'`) rather than as a
wave of slice-hash drift. A manifest that predates the schema (no `schema_version`,
no `hash`) is not flagged by that check and falls through to plain re-derivation, so
the check adds a reason without changing which manifests pass.

### The schema is published as JSON Schema, validated with the standard library

`docs/schema/receipts.schema.json` is a JSON Schema (draft 2020-12) describing the
manifest: the required `schema_version`, the `hash` object, and the `receipts` array
with its per-receipt required fields, plus the optional `provenance` object. The
schema is documentation and a machine contract.

To keep runtime dependencies empty, the test suite does **not** pull in `jsonschema`.
Instead a small structural validator in the tests asserts the required keys and
their types against an emitted manifest. Preferring the stdlib structural check over
an optional `jsonschema` extra keeps the zero-dependency posture whole; the published
schema remains the authoritative, tool-agnostic contract for external consumers.

## Consequences

- Renamed columns with identical values now produce different slice hashes, closing
  a silent schema-change gap. This is an intended breaking change to the hash
  payload, gated by `schema_version` "1.0"; committed example manifests and golden
  fixtures were regenerated.
- A consumer can validate `receipts.json` against a published schema and knows the
  hash algorithm, digest size, and canonicalization without reading the engine.
- `verify` names a version or hash-descriptor mismatch before attempting field
  re-derivation, so a deliberate schema bump reads differently from tampering.
- The versioning policy: `canonicalization` is bumped whenever the slice-to-bytes
  rules change (every such change changes every hash); `schema_version` is bumped
  whenever the manifest shape or a field's meaning changes. This is the keystone the
  spec/manifest semantic-versioning guarantees on the road toward 1.0 build on.
- The zero-dependency constraint holds: no runtime dependency was added, and the
  schema is validated in tests by a stdlib structural check.
