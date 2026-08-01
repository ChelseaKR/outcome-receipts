# Compose only verified aggregate receipts

- Status: Accepted
- Date: 2026-07-22
- Deciders: Chelsea Kelly-Reif

## Context

Restatements, migration checks, contract milestones, and partner rollups need
figures derived from other figures. Treating those values as ordinary
row-backed receipts would hide a material provenance difference. Accepting an
unverified manifest would also let an edited aggregate enter a new evidence
package with the appearance of trust.

Equity slices have a related boundary. They need stricter disclosure review, but
they must not create a free-form query surface or bypass the report-wide
suppression pass.

## Decision

A derived number is computed by SQLite over values from verified receipts. Its
record uses `provenance_type = "receipt_composed"`, stores the deterministic
query, and hashes an ordered list of input receipt digests. It is not a
row-backed `Receipt`.

Restatements and federated rollups verify the complete source bundle before
using a receipt. A rollup accepts unsuppressed count receipts only, requires
matching definitions and operator-supplied period, suppression-policy, and
population-overlap declarations, and sorts inputs before computing its digest.
A suppressed partner cell blocks the rollup; it is never treated as zero.

Migration comparisons run reviewed source-specific report specs and require
identical metric IDs, definitions, units, and kinds. Contract thresholds and
financial values are metrics in the report spec, not numeric fields interpreted
from prose. Requirement changes match stable IDs exactly and route changed text
to review. Equity review packages only allowlisted metric IDs after the existing
whole-report suppression pass and does not rank groups or infer causality.

All artifacts use the versioned envelope in
`docs/schema/workflow-artifact.schema.json`. Builders validate their complete
input and return an artifact in memory. The CLI writes only after successful
validation.

## Consequences

An auditor can distinguish evidence computed from source rows from evidence
composed from approved aggregates. Partner data can remain local, but each
partner must provide a verifiable export bundle. A definition mismatch,
suppressed input, missing approval, absent consent basis, or incomplete
controlling text blocks output.

This first release intentionally does not deduplicate clients across
organizations, interpret contract law, approve requirement mappings, or make an
equity conclusion. Real-world privacy, accessibility, and multi-organization
compatibility evidence remain release gates rather than claims supplied by the
software.
