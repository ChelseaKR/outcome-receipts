# 0004 — A self-contained, tamper-evident signed audit bundle

Status: accepted

## Context

`receipts run` writes a report, a receipts manifest, a trace view, and any charts,
and `receipts verify` (ADR 0003, R6) re-derives every receipt from the data. An
auditor (persona P10) and a compliance reviewer (P9) want one more assurance: that
the bundle of files they hold is exactly what was exported — no member quietly
swapped, dropped, or added after the fact — and, when a key is shared, that the
bundle was sealed by someone who held it.

The obvious supply-chain answer is Sigstore/cosign keyless signing. But cosign's
keyless flow needs an OIDC identity and network calls to Fulcio and Rekor. That is
the right tool for a published release artifact, and CLAUDE.md already commits the
release path to "SBOM (CycloneDX) and Sigstore-signed, SLSA-provenanced releases
via OIDC Trusted Publishing." It is the wrong tool for the local core: `receipts
run` must work offline, deterministically, and with no runtime dependency beyond
the standard library (the CLAUDE.md small-dependency rule), the same posture the
metric engine already holds.

## Decision

Ship a `bundle.py` module, stdlib only, that seals an export directory with a JSON
bundle manifest: each member file's name and BLAKE2b-256 content digest, sorted by
name, plus a `bundle_digest` that is a BLAKE2b hash over the canonicalized
`(name, digest)` list. The digests alone are tamper-evident — changing any byte, or
adding or dropping a member, breaks re-hashing. When a key is supplied (`run
--sign-key-file PATH`), a keyed-BLAKE2b `signature` over the same canonical bytes is
added: a self-contained seal that proves possession of the key with no service,
network, or OIDC. `verify_bundle` (and `receipts verify-bundle --dir`) recompute
everything and fail closed, reporting every tampered, missing, or extra member,
exactly like `receipts verify`.

This reuses the portfolio hash-chain pattern already in `engine._slice_hash`
(BLAKE2b-256 over compact, sorted, canonical JSON), so re-bundling identical files
reproduces identical digests, and it introduces no new dependency. Keyed BLAKE2b is
a standard, well-understood MAC available directly in `hashlib`; the signature
comparison uses `hmac.compare_digest` for constant time.

## Consequences

- The local core stays offline, deterministic, and stdlib-only; `run` gains a
  `bundle.json` and a `verify-bundle` subcommand, both additive.
- The seal is symmetric: a keyed-BLAKE2b signature proves possession of a shared
  secret, not a public identity. It is a tamper-evident MAC, not a public-key
  attestation, and does not establish non-repudiation to a third party who lacks
  the key. That property, and transparency-log inclusion, are exactly what the
  Sigstore release path provides.
- Real Sigstore/cosign signing is therefore deliberately **not** implemented here.
  It is deferred to the release workflow (SBOM signing), where OIDC and network are
  available and the artifact is a published release rather than a local run.
- Default runs are unsigned (digests-only) and still tamper-evident, so the common
  path needs no key management.
- New tests cover the passing case, a mutated member, missing and extra members, a
  wrong and a tampered signature, a keyed round-trip, and the CLI run/verify path,
  keeping branch coverage on the new module above the repo's ≥ 90% bar.
