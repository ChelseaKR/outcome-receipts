# Specification and manifest stability

Outcome Receipts has three public data contracts:

- a TOML report specification, described by
  [`schema/report-spec.schema.json`](schema/report-spec.schema.json);
- the exported receipts manifest, described by
  [`schema/receipts.schema.json`](schema/receipts.schema.json);
- evidence-workflow artifacts, described by
  [`schema/workflow-artifact.schema.json`](schema/workflow-artifact.schema.json).

Each contract uses a `MAJOR.MINOR` schema version independent of the package
version. The report spec is at `1.0`, the receipts manifest at `2.0`, and the
workflow artifact at `1.0`.

## Receipts manifest 2.0: a withheld cell is not a zero

Manifest `1.0` wrote a suppressed figure's numeric fields as zeros: `value:
0.0`, `row_count: 0`, and the all-zero `slice_hash` sentinel. A figure that is
genuinely zero produces the same three values, so nothing in the schema
distinguished "we withhold this count to protect the people in it" from "we
served nobody". The only surviving signal was the human-readable string
`[SUPPRESSED]` in `display`, which the schema did not describe, and which no
machine consumer reads.

`2.0` makes the three states three distinct renderings:

| State | `suppressed` | `value` | `row_count` | `slice_hash` | `column_names` |
|---|---|---|---|---|---|
| Published, including a genuine zero | `false` | number (`0` when zero) | integer (`0` when the slice is empty) | hex digest (all-zero sentinel when empty) | array |
| Withheld by suppression | `true` | `null` | `null` | `null` | `null` |
| Absent | no entry in `receipts` for that `metric_id` | — | — | — | — |

This is a **breaking** change: `value`, `row_count`, `slice_hash`, and
`column_names` widen to a union with `null`, and the new `suppressed` field is
required. A consumer that reads the numeric field without branching on
`suppressed` now sees `null` and fails, which is the intended direction — it
used to see `0` and silently believe it.

**Field mapping, 1.0 to 2.0.** For a receipt with `display` equal to
`[SUPPRESSED]`, set `suppressed: true` and replace `value`, `row_count`,
`slice_hash`, and `column_names` with `null`. For every other receipt, set
`suppressed: false` and leave the fields as they are. The mapping is
deterministic and needs no data access, because `1.0` wrote a fixed rendering
for every suppressed receipt.

`receipts verify` reads both `1.0` and `2.0`. For a `1.0` manifest it
reconstructs that manifest's rendering from the current figures before
comparing, so the schema change is not reported as data drift and the frozen
`v0.1.0` baseline still re-derives. Nothing writes `1.0` any more.

The workflow artifact version is unchanged at `1.0`. Its envelope did not
change; what changed is inside the receipts it embeds, and those are governed by
the receipts-manifest contract. `receipts verify-workflow` gained a check that
fails any artifact in which an object declaring `suppressed: true` still carries
a number in `value`, `row_count`, or `slice_hash`, and a check that an equity
review with a withheld group states suppression in its interpretation limits.

## Compatibility rules

A patch release may clarify documentation or validation without changing a
valid document's meaning. A minor schema release may add optional fields. A
major schema release is required to remove or rename a field, make an optional
field required, change a field's type or meaning, or change receipt
canonicalization in a way that changes hashes.

The loader accepts a report spec only when its declared `schema_version` is
supported. Unversioned specs from the beta period are interpreted as `1.0` so
existing users are not stranded, but `receipts init` and all maintained examples
write the version explicitly. The verifier checks a manifest's
`schema_version` before re-derivation and names a version mismatch directly.
`receipts verify-workflow` checks the workflow version, typed relationship,
digest syntax, aggregate-only boundary, and receipt-composed input digest before
a consumer interprets the artifact.

Support for a schema major lasts for the full package major that introduced it.
When a later package major drops that schema, the changelog must identify the
last compatible package and provide a deterministic migration command or field
mapping. No migration may recompute a figure, weaken suppression, or alter a
receipt silently.

## Release gate

Before a release can claim a stable contract:

1. every maintained example declares the current report-spec version;
2. generated manifests conform to the published receipts schema;
3. the previous two tagged releases' example specs and manifests still pass, or
   the package major and schema major both change with migration guidance;
4. `receipts verify` still fails closed on unsupported manifest versions;
5. `receipts verify-workflow` accepts every frozen artifact for supported
   workflow versions and rejects unsupported versions;
6. the changelog labels every contract change as compatible or breaking.

The repository freezes generated version-1.0 examples for all six workflow
artifact kinds under `tests/fixtures/compat/v1/` and regenerates them in
`make verify` to catch drift. Cross-release execution evidence is tracked in
[issue 65](https://github.com/ChelseaKR/outcome-receipts/issues/65) and begins
with the next two tags; it cannot be manufactured from a single release.

## Compatibility evidence

| Producer | Contract | Current consumer | Result |
|---|---|---|---|
| Signed `v0.1.0` tag, commit `51d18fc4cdd9f9dcd91dd4588ededc80a6b6bb7d` | Unversioned beta report spec, interpreted as report-spec `1.0` | Current loader | PASS |
| Signed `v0.1.0` tag, same commit | Receipts manifest `1.0` | Current re-derivation verifier (reads `1.0`, writes `2.0`) | PASS |
| Current implementation package | Workflow artifact `1.0`, all six kinds | `receipts verify-workflow` | PASS |
| Next tagged release | All supported contracts | Next tagged verifier | Pending issue 65 |

The signed-release files are preserved byte-for-byte under
`tests/fixtures/compat/v0.1.0/`; the source commit and paths are recorded in that
directory. `tests/test_release_compatibility.py` recomputes the tagged manifest
with current code. This establishes a real prior-release baseline, but the v1
gate still needs evidence across the next two consecutive tags.
