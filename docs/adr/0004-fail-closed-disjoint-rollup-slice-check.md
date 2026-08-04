# Refuse a disjoint rollup the partner slice hashes contradict or cannot support

- Status: Accepted
- Date: 2026-08-04
- Deciders: Chelsea Kelly-Reif

## Context

`receipts rollup` composes count receipts from independently verified partner
bundles. The plan declares `population_overlap` as either `disjoint`, meaning no
person appears in two partners' rows, or `not_deduplicated`, meaning the combined
figure counts some people more than once and says so on its face. ADR 0003 left
that declaration to the operator: the rollup checked definitions, periods,
suppression policies, and bundle digests, and accepted the overlap label as
written.

The wave 3 adversarial fixture set for UC-5 found a plan the tool would publish.
Two partners submitted the same rows under a `disjoint` declaration. Each bundle
verified. The bundle digests differed, because each partner's report carries its
own title and narrative, so the duplicate-digest check did not fire. The rollup
summed both and published a combined count larger than the number of people
actually served, in an artifact whose `population_overlap` field asserted no
overlap.

A receipt's `slice_hash` is a content hash of the exact rows a figure was
computed from. Two partner receipts carrying the same non-empty slice hash
counted the same rows, which a disjoint population cannot produce. The lead
agency reaches that conclusion from hashes the partners already publish, without
ever holding a client row.

One hash value carries no such evidence. `EMPTY_SLICE_HASH` is the single
sentinel every zero-row slice hashes to, whoever produced it
(`docs/decisions/0005-receipt-canonicalization-and-schema.md`). Two partners who
both report a true zero share it and are not a collision. But a receipt also
carries that sentinel when its value was computed over rows its slice query does
not return: a non-zero count whose published hash matches every other empty slice
and identifies no rows. Such a receipt still contributes to the sum.

## Decision

Under a `disjoint` declaration, `build_rollup` refuses to produce an artifact
when either condition holds:

- two inputs carry the same non-empty slice hash. The error names both. When one
  partner appears twice under two bundles, which is a legitimate shape for one
  organization with two programs, the bundle digest distinguishes them;
- an input carries the empty-slice sentinel, or no slice hash, while its receipt
  reports a non-zero count or a non-zero row count. The empty-slice exemption is
  keyed on the receipt reporting nothing counted, never on the hash value alone.

A plan declaring `not_deduplicated` is unaffected. It has already told the reader
the combined figure counts some people more than once, so there is no claim for
these checks to falsify.

The compose path refuses rather than warns because the artifact, not the
terminal, is what travels. A warning is not carried in the JSON: the published
`population_overlap: disjoint` field would still assert to every downstream
reader something the tool has evidence against, or has no way to check, and the
tool's whole claim is that its numbers are checkable. This matches the existing
rule that a suppressed partner cell blocks a rollup rather than being read as
zero. The cost of refusing falls on the operator, who can restate the plan as
`not_deduplicated` or correct the partner spec, and who is present. The cost of
warning would fall on a reader who is not.

## Consequences

The one duplicate-client case the tool can decide on its own is now decided, and
a receipt that cannot be checked at all no longer passes silently. Nothing about
the data flow changes: only hashes are compared, and no client row crosses an
organizational boundary.

The residual risk is that equal hashes are a narrow test. Only a byte-identical
slice is falsifiable. Two partners serving exactly the same people under
different client identifiers, different column names, or any difference in the
recorded rows hash differently and still pass, as does every partial overlap. A
complete overlap is therefore caught only in the identical-export case, and
`disjoint` remains an operator declaration everywhere else, which is why the
`docs/THREAT-MODEL.md` row for duplicate submission keeps a Medium residual risk.
Hashes are also compared only within a single rollup run, so overlap across
separate rollups or periods is not detected.

A partner whose spec computes a count over a slice query that returns no rows can
no longer be included in a disjoint rollup. That is a real cost and the intended
one: the fix is a slice query that returns the rows being counted, which restores
the evidence, or a `not_deduplicated` plan, which drops the claim.

Superseding this record requires a later ADR. Deduplicating clients across
organizations, which would decide the general case, remains out of scope for the
reasons ADR 0003 gives.
