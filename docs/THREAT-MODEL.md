# Threat model

STRIDE/LINDDUN review of the offline CLI, generated artifacts, optional Bedrock
drafting seam, and CI/release supply chain.

## Assets and trust boundaries

Assets are figure integrity, fail-closed grounding, small-cell confidentiality,
aggregate-only exports, human approval, bundle/ledger integrity, and installable
release provenance. Trust boundaries are the author-controlled TOML and SQL, the
organization's L3 service export, the optional Bedrock provider, filesystem keys
and outputs, and GitHub/PyPI build infrastructure.

Author-supplied report SQL is trusted code, not an untrusted multi-tenant request.
Dynamic identifiers are quoted, the database is in memory, and scanner waivers
are narrow and tracked in issue 52. Source CSV content is untrusted data and is
validated before use.

## Threats and controls

| Threat | Control | Residual status |
|---|---|---|
| Unbacked or changed figure reaches prose, chart, comparison, or trace | Deterministic queries, immutable receipts, raw and post-suppression span grounding, export refusal | Low; merge-blocking tests |
| Model invents, rounds, signs, ranges, or spells out a number | Scalar allowlist and same mechanical gate; model cannot compute or approve | Low for numeric invention; nonnumeric drift remains Medium |
| Client row or identifier reaches an export/model request | Typed artifact boundary accepts figures; request excludes rows, identifiers, SQL, hashes, paths | Low; structural tests |
| Small cell recovered from total, delta, rate, or complementary cells | Primary plus exhaustive complementary/delta/percentage suppression before final drafting | Medium because operator policy may differ from CMS default |
| Source/spec path traversal or malformed CSV causes unintended read | Paths resolve from explicit operator config; loader fails on malformed shape; operator runs trusted specs | Low in single-user local boundary |
| Report/bundle/ledger is altered after approval | Artifact digests, optional keyed bundle signature, whole-bundle verification, hash-chained ledger | Low when key and ledger are retained together |
| A forged aggregate or edited composed query enters a restatement or partner rollup | Complete source-bundle verification, typed `receipt_composed` provenance, canonical input digests, fixed composition queries, `verify-workflow` | Low for structural tamper; source re-derivation still requires the cited bundles |
| One partner's rows are submitted twice and summed under a `disjoint` rollup declaration | Rollup rejects two partner receipts sharing a non-empty slice hash and refuses a receipt whose non-zero count carries the empty-slice hash; a true zero is exempt and a `not_deduplicated` plan keeps its label (ADR 0004) | Medium: only byte-identical slices are falsifiable, so the same people counted twice under different client identifiers, column names, or any recorded-row difference still passes, as does every partial overlap; `disjoint` remains an operator declaration in each of those cases |
| Workflow artifact carries client-level rows | Allowlisted aggregate structures plus recursive rejection of row/client container fields | Low; compatibility and adversarial tests |
| Signing key is disclosed | Key path supplied explicitly; key not embedded in artifacts; gitleaks plus incident runbook | Medium because local key storage is operator-owned |
| CI dependency or workflow is compromised | SHA-pinned actions, least privilege, no persisted checkout credentials, lock scans, SAST, Scorecard, OIDC release, no release caches | Low; monthly evidence review still required |
| Bedrock retains aggregate prompt/response | Two explicit opt-ins, documented provider boundary, organization-owned logging/retention review | Medium; outside local process control |
| Denial of service from pathological local input | Failure affects the invoking operator only; no listener or shared service | Accepted low availability risk |

## Abuse cases

- A spec author embeds prompt instructions in narrative text. The model may follow
  them, but any new numeric span blocks and the human reviews nonnumeric meaning.
- A malicious CSV header attempts SQL injection. Identifier quoting doubles quotes;
  values use bound parameters; spec SQL itself remains explicitly trusted.
- An operator tries to publish raw rows through a renderer. Renderers accept
  `Figure` values and provenance, not loaded tables.
- An attacker edits one artifact but not the bundle. Whole-bundle verification
  fails on the digest mismatch; changing the ledger also breaks the chain.

## Review and incident interface

The AI risk, impact, red-team, residual-risk, DPIA, and data-card artifacts live
under `docs/audits/`, `docs/cards/`, and `docs/data/`. An integrity bypass,
recoverable suppressed cell, secret exposure, or L2/L3 data disclosure uses the
private channel and postmortem process in `SECURITY.md` and `docs/OPERATIONS.md`.

Status: current beta architecture. *Last verified: 2026-07-22 · Recheck cadence: every release, threat-boundary change, or disclosed supply-chain compromise, and at least quarterly.*
