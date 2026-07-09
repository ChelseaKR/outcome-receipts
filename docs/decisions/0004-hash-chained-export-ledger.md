# 0004 — A hash-chained export ledger

Status: accepted (working tree, uncommitted)

## Context

A receipt proves how a number was produced, and `receipts verify` proves a
committed manifest still re-derives from the data. Neither records that an export
happened at all. A funder rejecting "substantially AI-developed" reports wants to
know what was sent, to whom, and when, and to trust that the record has not been
edited after the fact. Without such a record, a report can be quietly re-sent, a
recipient swapped, or an entry backdated, and nothing detects it. This is the
export-side counterpart to the receipt: the act of reporting should itself carry
evidence.

The portfolio already uses a hash-chain pattern (the sibling
`constituent-reconciler` and the v0.5 provenance line both call for it), so the
choice is which construction to adopt, not whether to chain.

## Decision

`run` appends one line to an append-only JSONL ledger (default
`<out>/../export-ledger.jsonl`, or `--ledger`) after a successful export, and
only after the grounding gate passes and the report, manifest, and trace are
written. A blocked export writes nothing, so the ledger records exports that
actually shipped.

### The entry-hash construction

Each `LedgerEntry` holds `index`, `timestamp`, `report_title`, `manifest_hash`,
`recipient`, `prev_hash`, and `entry_hash`. The hash is built like the receipt
slice hash in `engine.py`: `blake2b` with a 32-byte digest, over a canonical JSON
payload. Canonicalization sorts keys and fixes separators so the same fields
always serialize to the same bytes and therefore the same hash.

- `manifest_hash` is the BLAKE2b hash of the receipts manifest that shipped, so
  the entry pins the exact numbers exported, not just the fact of an export.
- `prev_hash` is the previous entry's `entry_hash`; the genesis entry links to a
  fixed all-zero hash (`"0" * 64`), matching the `EMPTY_SLICE_HASH` convention in
  `models.py`.
- `entry_hash` is `blake2b` over every field except itself. Excluding
  `entry_hash` from its own preimage is what makes it well defined; including
  `prev_hash` in the preimage is what chains the entries, so editing any earlier
  entry changes its hash and breaks the `prev_hash` link of the next one.

The timestamp comes from the injected `Clock`, the same seam receipts use, so a
`--reproducible` run is byte-for-byte stable and CI can diff it.

### Verification

`verify-ledger` (and `verify_chain`) recomputes each entry's hash and checks it
against the stored value, checks each `prev_hash` against the previous entry's
`entry_hash`, and checks that indices are contiguous from zero. It reports every
problem with the index where it was found and exits non-zero on any break, so an
edited, inserted, dropped, or reordered entry is located and fails closed, the
same UX as `receipts verify`.

## Consequences

- What was reported to whom is itself receipted and tamper-evident, with no model
  anywhere near it. The ledger is deterministic, standard-library only, and holds
  to the offline-first posture.
- The ledger is aggregate metadata (a report title, a manifest hash, a recipient
  label, a timestamp). It carries no client-level data, so the aggregate-only and
  privacy invariants are unchanged. A recipient string is caller-supplied and
  optional; it is not derived from service data.
- The entry schema is now load-bearing for the chain. A new field must be added to
  the hashed payload, or old entries stop re-hashing; the payload field list is
  kept in one place in `ledger.py` so the JSON line and the hash preimage cannot
  drift apart.
- This is a forward cut of the v0.5 provenance-and-verify line, sitting alongside
  the existing manifest re-derivation rather than replacing it.
