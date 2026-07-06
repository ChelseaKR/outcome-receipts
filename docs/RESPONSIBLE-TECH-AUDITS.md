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

TODO: complete the data-flow map and the retention model once the suppression and
export modes land.

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
multi-tenant or network surface. TODO: commit the threat model and the
supply-chain hardening (SBOM, signed releases, pinned actions) on the path to 1.0.

## Legal note

This is a reference implementation, not legal advice. An organization adopting it,
and the small-cell suppression in particular, needs its own review against its own
funder and statutory obligations.
