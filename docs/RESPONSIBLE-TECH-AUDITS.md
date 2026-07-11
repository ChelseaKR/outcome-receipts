# Responsible-tech audits

Project-specific findings for outcome-receipts, following a standard
responsible-tech audit method: ethics, bias, privacy and a DPIA, transparency,
accessibility, and security. This is a committed, dated artifact, regenerated on
release. Sections marked TODO are scoped but not yet measured.

Status: v0.1. *Last verified: 2026-07-05 · Recheck: quarterly*

## Ethics

The harm this tool guards against is a wrong or invented number in a funder
report, which can cost an organization its funding and its credibility. The
design answer is structural: numbers come from queries, not from generated text,
and the grounding gate refuses to export any number that does not trace to a
receipt. The gate is fail-closed and mechanical, so the protection does not depend
on a reviewer noticing.

## Bias

A metric is only as fair as its definition. A query that counts "clients served"
encodes choices (who counts, over what window) that can over- or under-represent
groups. The tool does not hide those choices; it records the exact query in the
receipt, so a reviewer can see and contest the definition.

Each metric also carries a plain-language `definition` field that rides in the
receipt and renders next to the figure, in the report, the trace view, and the
manifest, so the choice is legible without reading SQL. The definitions in the
bundled examples name the common traps directly:

* **Deduplication window and unit.** "Clients served" is counted once per person
  by `client_id`, so the unit is the person, not the enrollment; "exits" is counted
  per enrollment, so one client who exited two enrollments counts twice. Stating
  the unit keeps a person-count and an enrollment-count from being read as the same
  thing.
* **Exit-destination categories.** Destinations are taken as recorded. An
  unrecorded destination is its own category, not folded into "permanent" or
  dropped, so the destination categories sum to total exits and a missing outcome
  is visible rather than silently favorable.
* **Denominator scope.** A rate names its denominator. The permanent-housing rate
  divides by exits, not by all enrolled clients, so a client still enrolled is not
  counted against the outcome.

## Privacy and data minimization (DPIA)

The tool reads client-level service data to compute aggregates, and the output is
a report of aggregate figures, not a client roster.

* The receipts manifest carries no client-level field values: it records the
  query, the row count, and a hash of the slice, not the rows themselves. The trace
  view (`trace.html`) and `receipts verify` read the same receipts, so neither adds
  a client-level surface: the trace view renders counts, definitions, and slice
  hashes, and verify re-derives values without emitting any slice rows.
* Small-cell suppression (v0.2) will suppress aggregate counts below a threshold,
  with complementary suppression and true zeros preserved, modeled on the U.S. CMS
  Cell Size Suppression Policy and grounded in primary guidance, expressed as
  tests. This is the same posture and the same honest attribution as the sibling
  constituent-reconciler project's DV pack.

### Data-flow map

The chain runs compute, receipt, draft, ground, suppress, human-approve, export,
in that order. Each stage below names what data crosses into it and what it
carries forward.

* **Ingest.** The org's client-level service data (a CSV) is read locally into
  the deterministic engine (the data and engine layer). Client-level rows stay in
  the local process; they are not sent anywhere and are not written back out by
  the tool.
* **Compute.** `engine.py` runs each `MetricSpec` and emits a `Figure`: a value
  plus a `Receipt` of `{metric_id, value_sql, row_count, slice_hash, value, unit,
  computed_at, definition, kind}`, where `slice_hash` is a BLAKE2b hash of the
  canonicalized slice the figure was computed from. From this point on, only the
  aggregates and the slice hash move forward. Raw rows are not carried into the
  receipt.
* **Draft.** The deterministic template drafter (or the optional policy-gated
  Bedrock seam) writes prose around figures that already carry receipts. The
  drafter receives figures, never raw rows.
* **Ground.** `grounding.py` binds every numeric span in the narrative to a
  receipt and fails closed: an unbound or mismatched number blocks the export
  rather than passing silently.
* **Suppress (v0.2, planned).** Small-cell and complementary suppression run over
  the aggregate counts before export, consistent with the suppression posture
  described above. This module has not landed yet.
* **Human approve.** The operator reviews the grounded draft before exporting;
  everything they see is already aggregate-only. A recorded sign-off (named
  approver, timestamp, hash of the approved content in the manifest) is planned
  (R8) and has not landed yet; today the approval is the operator's decision to
  run the export.
* **Export.** `report.py` and `provenance.py` emit the aggregate report together
  with a manifest of receipts and slice hashes, and `ledger.py` appends one
  hash-chained line per successful export (report title, manifest hash, optional
  recipient, timestamp). No client-level field value and no client identifier is
  emitted. This is the aggregate-only invariant: what leaves the tool is counts,
  rates, narrative, and provenance metadata.
* **Verify.** `verify.py` re-derives the figures from the spec and the cited data
  and checks them against the manifest. It reads the same data and emits no slice
  rows.

One external boundary exists in the whole chain: the optional drafting seam
(Claude on Bedrock). It receives only receipted aggregate figures and narrative
instructions, never client-level rows, and it is fused off entirely under any
no-cloud policy pack.

### Retention model

Retention is bounded by what each artifact is allowed to contain.

* **Input service data.** Not copied or retained by the tool beyond the compute
  run. It is read from the org's own store and stays owned and retained by the
  org under the org's own policy.
* **Receipts and manifest.** Retain aggregates, queries, row counts, slice
  hashes, and timestamps, with no client-level values, so a report stays
  reproducible. Slice hashes are one-way BLAKE2b digests and are not reversible
  to the underlying rows.
* **Drafting-seam prompts and responses (when the seam is enabled).** Contain
  only aggregate figures and narrative, no client-level data. Their retention
  follows the org's own Bedrock configuration, outside this tool.
* **Export ledger (`export-ledger.jsonl`).** Append-only and retained
  indefinitely by design (its tamper evidence depends on the chain staying
  intact). Each entry holds a report title, a manifest hash, an optional
  recipient, a timestamp, and chain hashes — aggregates' provenance metadata
  only, no client-level data.
* **Exported report.** Aggregate-only, retained by the org and its funder.

Because no client-level PII is retained in any artifact the tool produces, the
retention obligation on tool-produced artifacts is bounded to aggregates and
provenance metadata. The obligation over client-level data stays with the org's
system of record, where it already lived.

## Transparency

Every figure in a report ships with its receipt: the query, the row count, the
slice hash, and the timestamp. The committed eval shows the gated grounding rate
with a Wilson confidence interval, and the gate's PASS or FAIL, rather than a
single headline number.

Two transparency surfaces ship for the report's recipient. Every export embeds a
provenance statement, in the report body and as a machine-readable record in the
manifest, stating that each number was computed by a deterministic query, that no
figure was written by a model, and that the gate bound every number before export.
And `receipts verify` re-derives every figure from the spec and the cited data and
checks it against the manifest, so the claim is reproducible and not only asserted;
it fails closed on any drift. TODO: publish the model card for the optional drafting
seam when it lands (v0.3).

## Accessibility

The CLI core stays headless. The HTML the tool emits is held to WCAG 2.2 AA. The
chart output ships an SVG with `role="img"`, a `<title>`, and a `<desc>`, paired
with an equivalent data table. The trace view (`trace.html`) is a single semantic,
high-contrast page: one `<h1>`, a document `lang`, a summary table with a
`<caption>` and `scope`-marked headers, dark text on white, and every number as
text. It carries no script and no external asset, so it opens offline. When a
review or approval UI lands, the same bar applies to it.

## Security

The deterministic core has no third-party runtime dependency, which keeps the
supply-chain surface small. The SQL in a spec is author-supplied and runs against
an in-memory database loaded only with the org's own data; it is not a
multi-tenant or network surface. The threat model now ships at
[`THREAT-MODEL.md`](THREAT-MODEL.md), and the supply-chain hardening it names is
in place: SHA-pinned Actions, a least-privilege `GITHUB_TOKEN`, Sigstore-signed
releases, PyPI Trusted Publishing over OIDC, and a CycloneDX SBOM on release.
The remaining 1.0 security work is the retention and data-flow map, which
completes with the suppression and export modes, and the drafting-seam model card
that lands with v0.3.

## Legal note

This is a reference implementation, not legal advice. An organization adopting it,
and the small-cell suppression in particular, needs its own review against its own
funder and statutory obligations.
