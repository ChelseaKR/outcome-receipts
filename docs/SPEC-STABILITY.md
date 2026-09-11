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

The reasoning is recorded in
[ADR 0009](decisions/0009-withheld-cells-are-null-not-zero.md).

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
[issue 65](https://github.com/ChelseaKR/outcome-receipts/issues/65). Two tags now
exist, `v0.1.0` and `v0.2.0`, and both are frozen and exercised; what they do not
yet establish is stated under the matrix below rather than left as "pending".

## Compatibility evidence

| Producer | Contract | Current consumer | Result |
|---|---|---|---|
| Signed `v0.1.0` tag, commit `51d18fc4cdd9f9dcd91dd4588ededc80a6b6bb7d` | Unversioned beta report spec, interpreted as report-spec `1.0` | Current loader | PASS |
| Signed `v0.1.0` tag, same commit | Receipts manifest `1.0` | Current re-derivation verifier (reads `1.0`, writes `2.0`) | PASS |
| Current implementation package | Workflow artifact `1.0`, all six kinds | `receipts verify-workflow` | PASS |
| Signed `v0.2.0` tag, commit `b8f5a27e48283e6b97add1841d1f8a110f760265` | Report spec `1.0`, declared explicitly | Current loader | PASS |
| Signed `v0.2.0` tag, same commit | Receipts manifest `1.0` | Current re-derivation verifier (reads `1.0`, writes `2.0`) | PASS |
| Signed `v0.1.0` tag, manifest relabelled `schema_version: "3.0"` | A manifest major nothing implements | Current re-derivation verifier | REFUSED by name; every receipt in it still re-derives, so the refusal is the declared version and nothing else |
| Signed `v0.1.0` tag, manifest with one figure edited by hand | Receipts manifest `1.0`, altered after release | Current re-derivation verifier | REFUSED as drift, on the edited metric by name |
| Signed `v0.2.0` tag, spec relabelled `schema_version: "2.0"` | A report-spec major nothing implements | Current loader | REFUSED before computation; no output written |
| Next tagged release | A contract that actually moves across the boundary | Next tagged verifier | Not yet observed — see below |

The signed-release files are preserved byte-for-byte under
`tests/fixtures/compat/v0.1.0/` and `tests/fixtures/compat/v0.2.0/`; each
directory records its source commit and paths. `tests/test_release_compatibility.py`
recomputes each tagged manifest with current code.

The last three rows are the same released artifacts with one field changed, and
they are in the table for a reason a PASS row cannot supply on its own. A
verifier that accepts every document also accepts a released one, so "the
`v0.1.0` manifest re-derives" is only evidence if some neighbouring document does
not. Each refusal names what it refused: the relabelled manifest fails on
`schema_version` while all four of its receipts still re-derive, so the failure
is attributable to the declared version rather than to the data; the edited
manifest fails on the single metric whose figure moved; and the relabelled spec
is refused by the loader before any figure is computed, which is asserted by
pointing that spec's `[data] path` at a CSV that does not exist — if refusal ever
moved to after the read, the missing file would raise first and the test would
say so. The refused run leaves its `--out` directory empty. A half-written bundle
from a rejected spec would be a receipt set with nothing behind it.

What the second tag established, and what it did not. `v0.2.0`'s
`services.csv` and `receipts.json` are byte-identical to `v0.1.0`'s: the second
released implementation produced exactly the artifact the first one did. The only
difference between the two frozen specs is that `v0.2.0`'s declares
`schema_version = "1.0"` where `v0.1.0`'s carried no `schema_version` key and was
interpreted as `1.0` by default. So the evidence across this boundary is real but
narrow — a spec that names its contract and a spec that omits it are read
identically, and a released implementation's manifest still re-derives
field-for-field.

It is not evidence that a *changed* contract survives a release boundary, because
no contract changed across it. That is what issue 65's remaining criteria need,
and it cannot be written before a release moves one; recording the gap here is
the honest alternative to reading two identical artifacts as a compatibility
result.

## Report spec 1.0: `[requirements]` is an additive, optional binding

The reasoning is recorded in
[ADR 0013](decisions/0013-requirement-coverage-is-proven-at-export.md).

`[requirements] path = "..."` binds a spec to a funder's requirement document,
and each metric may carry `requirement_id`. Both are optional at spec `1.0`, in
exactly the way `[[data_checks]]` is: a spec that declares neither loads,
computes, grounds, approves, and exports precisely what it did before, and the
version does not move.

The receipts manifest stays at `2.0` and gains one optional member,
`requirements`, present only for a bound spec. Three things follow, and the
third is a real limitation rather than a footnote:

- **A manifest from an unbound spec is byte-identical to what it was.** The key
  is absent, not an empty record — such a spec has not answered zero
  requirements, it has made no coverage claim at all. `verify --bundle` reports
  `not checked` rather than `ok` for the same reason.
- **A `2.0` consumer that ignores unknown members reads a bound manifest
  unchanged.** The coverage record is beside the receipts, never inside one, so
  nothing a `2.0` reader already parses has moved.
- **A consumer validating against a copy of the `2.0` schema taken before this
  change will reject a bound manifest**, because that schema sets
  `additionalProperties: false`. The published schema now describes
  `requirements`; a pinned older copy does not. The alternative — a `2.1` —
  would have moved the version on every manifest including those from unbound
  specs, breaking the byte-identity above for every consumer in order to
  describe a member none of them would receive. That trade was chosen this way
  deliberately and is the one thing here worth revisiting if a real consumer
  turns out to validate against a pinned copy.

`verify --bundle` re-derives the coverage record and the requirement document's
sha256 rather than reading either back from the manifest, so editing the
requirement document after export fails naming the digest, and editing the
coverage record itself fails as a mismatch against what the spec and data
actually produce.

## Report spec 1.0: `[approval]` is an additive, optional sign-off policy

`[approval] required = ["program", "finance"]` names the roles an export must
record before it may be written. It is optional at spec `1.0`, in exactly the
way `[requirements]` and `[[data_checks]]` are: a spec that omits the section
loads, computes, grounds, approves and exports precisely what it did before, and
the version does not move.

One shape is refused rather than accepted as a policy. An `[approval]` table
that names no role would be a declared sign-off gate that demands nobody, and it
would read in the manifest exactly like a satisfied one. The loader rejects it
naming the key. Absent means "no policy"; present means "these roles".

The receipts manifest stays at `2.0` and its `provenance` block gains one
optional member, `approvals`, present only for a spec that declares a policy.
Each entry carries `role`, `approved_by` and `approved_at`. Three consequences:

- **A manifest from a spec with no policy is byte-identical to what it was.**
  The key is absent, not an empty list. Such a spec has not satisfied zero
  roles, it has declared none, and `verify --bundle` reports `not checked`
  rather than `ok` for the same reason it does for an unbound requirement set.
- **`approved_by` keeps naming a person and is not replaced.** For a role-based
  export it carries every approver, in the policy's order, as
  `A. Lee (program), B. Cruz (finance)`. Everything that already reads it —
  `verify-workflow`, the rollup composition's "bundle has no named human
  approval" refusal, the provenance paragraph in the report body — keeps working
  without learning a new field, and reads a complete answer rather than one of
  two names.
- **A consumer validating against a pinned older copy of the `2.0` schema still
  accepts a manifest carrying approvals.** `provenance` is declared with
  `additionalProperties: true`, so this addition costs nothing that the
  `requirements` member cost. That is the difference between adding a member
  inside an open object and adding one beside a closed one.

`verify --bundle` reads the policy from the spec, never from the manifest. Both
directions fail. A manifest recording no approvals against a spec that requires
them was exported before the policy existed, so its report proves nothing about
the policy now in force. A manifest recording approvals against a spec that
declares none records a gate nothing now defines. A manifest whose `approvals`
member is present but unreadable fails the comparison rather than taking the
"nothing to compare" path, because that path reports `not checked` and passes.

The policy governs the evidence-workflow commands that run from one spec —
`restate`, `contract-check` and `equity-review` — for the reason the section
exists: a requirement that travels with the report definition must not be
satisfiable by a different invocation. `migrate-check` and `rollup` are not
covered. `migrate-check` reads two specs and there is no settled answer to which
one's policy governs a comparison between them; `rollup` reads a plan rather
than a spec and has no policy to read. Both still take `--approved-by`.

## Receipts manifest 2.0: `artifacts` may name `report.docx`

`run --format docx` records `report.docx` in `artifacts` beside `report.md`,
`trace.html` and each chart. This is **compatible** and needs no version change:
`artifacts` was already a map from any bundle-relative path to a digest, so a
consumer validating against the published `2.0` schema accepts it, and a run
without the flag writes the map exactly as before.

What an older verifier does with it is worth stating, because it is less than
the current one. A verifier from before this change checks the document's
sha256 like any other artifact and stops there: it does not read the document,
compare it with `report.md`, or ground its narrative. The current verifier does
all three, and it also fails a `report.docx` the manifest does not attest.
