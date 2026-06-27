# Responsible-tech audits

Project-specific findings for outcome-receipts, following a standard
responsible-tech audit method: ethics, bias, privacy and a DPIA, transparency,
accessibility, and security. This is a committed, dated artifact, regenerated on
release. Sections marked TODO are scoped but not yet measured.

Status: v0.1.

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
receipt, so a reviewer can see and contest the definition. TODO: document common
definitional traps (deduplication windows, exit-destination categories) and how
the receipt surfaces them.

## Privacy and data minimization (DPIA)

The tool reads client-level service data to compute aggregates, and the output is
a report of aggregate figures, not a client roster.

* The receipts manifest carries no client-level field values: it records the
  query, the row count, and a hash of the slice, not the rows themselves.
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
single headline number. TODO: publish the model card for the optional drafting
seam when it lands (v0.3).

## Accessibility

N/A at v0.1: the tool is a headless CLI with no HTML or UI surface. When a review
or approval UI lands, WCAG 2.2 AA applies to it.

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
