# 0009 — A withheld cell serialises as null, not as zero

Status: accepted

## Context

Issue #77 demonstrated that a suppressed figure and a figure that is genuinely
zero were indistinguishable in every field the published manifest schema
constrains. `_redact` zeroed the receipt's numerics: `value: 0.0`,
`row_count: 0`, `slice_hash` set to the all-zero empty-slice sentinel, and
`column_names` emptied. A true zero produces exactly those values.

The only surviving signal was the string `[SUPPRESSED]` in `display`. That string
was not in the published contract: `docs/schema/receipts.schema.json` required
`value` and documented it as "the numeric value the figure asserts", and the
marker appeared nowhere in `docs/schema/`, `docs/SPEC-STABILITY.md`, or the
README — only in a historical ADR. A consumer that validated against the schema
and read the numeric field read zero.

The project ships several machine consumers: a reusable CI Action, `receipts
verify`, `receipts diff`, and six evidence workflows that read manifests
directly. The sharpest case is equity review, whose whole purpose is to look at
the small groups suppression hides: an artifact reported `value=0.0,
row_count=0` for two withheld destination groups whose real values were 3 and 2,
carried interpretation limits that said nothing about suppression, and passed
`receipts verify-workflow`. Anyone plotting or summing the `value` field
concluded that nobody exited to a temporary or unknown destination.

"We served no one in that category" is a worse answer to a funder than "we
cannot report that figure", and it was the answer the file gave.

## Decision

Three states get three renderings, all declared in the schema.

| State | `suppressed` | `value` | `row_count` | `slice_hash` | `column_names` |
|---|---|---|---|---|---|
| Published, including a genuine zero | `false` | number | integer | hex digest | array |
| Withheld by suppression | `true` | `null` | `null` | `null` | `null` |
| Absent | no entry in `receipts` for that `metric_id` | — | — | — | — |

This is the issue's option 2 together with option 1, which the issue itself
notes supersedes option 3. A boolean alone would have left a required numeric
field carrying a value the report explicitly refuses to assert, and a consumer
that reads `value` without knowing to branch would still have read `0`. `null`
makes that consumer fail loudly instead: summing the column raises rather than
returning a total that counts a protected group as nobody.

The row count is withheld rather than kept, even though it is the one honest
fact a redacted receipt could still carry — that a query ran and matched rows.
For an ordinary count metric the row count *is* the suppressed value: `exits`
counts the rows its slice query returns. `suppressed: true` already tells a
reader, under the documented policy, that a query ran; it deliberately does not
distinguish primary from complementary suppression, which would narrow the
hidden value further.

The slice hash is withheld rather than set to the empty-slice sentinel, so a
genuinely empty slice keeps a meaning of its own and a hash of a guessed row set
cannot be compared against a published one to confirm the guess.

The representation is carried to every surface the figures are written to, not
only the manifest: the report's receipts appendix and the trace view's row-count
and slice-hash fields render the same `[SUPPRESSED]` marker the figure shows, an
equity review containing a withheld group states suppression in its
`interpretation_limits`, and `receipts verify-workflow` fails an artifact in
which an object declaring `suppressed: true` still carries a number, or an
equity review that withholds a group without saying so.

## Consequences

- **Breaking manifest change, schema `1.0` to `2.0`.** `suppressed` is required
  and four fields widen to a union with `null`. Under the project's own
  compatibility rules that is a major schema release; the deterministic 1.0-to-2.0
  field mapping those rules require is in `docs/SPEC-STABILITY.md`.
- `receipts verify` reads both versions. Which rendering to compare against is
  read off the stored receipt (does it declare `suppressed`?) rather than off the
  manifest envelope, so a 2.0 manifest missing the key on one receipt is compared
  against the 1.0 rendering and reported as drift rather than waved through. The
  frozen `v0.1.0` baseline, which contains three 1.0-shaped suppressed receipts,
  still re-derives. Nothing writes `1.0` any more.
- The workflow-artifact schema version is unchanged at `1.0`. Its envelope did
  not change; what changed is inside the receipts it embeds, which are governed
  by the receipts-manifest contract. The workflow schema's description now says
  so and points at `receipts.schema.json`.
- `suppress_figures` refuses an already-redacted figure set. A second pass has no
  value to test and would list a withheld cell under `unsuppressed` — a false
  all-clear on the invariant the function exists to assert.
- `Figure.value` is deliberately still `0.0` at this point. That is the same
  defect one layer in, on the field the chart renderer reads for geometry; it is
  issue #78 and ADR 0010, which builds on this one. Nothing serialised here reads
  it: the manifest, the report appendix, and the trace view all read the receipt.
