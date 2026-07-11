# Threat model

The security posture for outcome-receipts, written as a committed, dated
artifact and regenerated on release. It records what the tool protects, the
boundaries it trusts, and the threats it defends against, so a reviewer can see
the reasoning rather than take the claim on faith. The shared engineering bar
lives in the portfolio Security & Supply-Chain standard; this document states
only what is specific to this repo and cross-references
[`SECURITY.md`](../SECURITY.md) and
[`RESPONSIBLE-TECH-AUDITS.md`](RESPONSIBLE-TECH-AUDITS.md) rather than restating
the standard.

Status: v0.1, dated 2026-07-02, regenerated on release.

## Scope and assumptions

At v0.1 the tool runs offline. There is no network path, no authentication, no
persisted user data, and no language model in any code path. The deterministic
core has zero runtime dependencies. The attack surface is therefore small, and
this model reasons about that small surface rather than a hypothetical
cloud-hosted service.

Four trust boundaries frame the analysis:

* **(a) The author-supplied report and metric spec, including its SQL.** A
  metric is a query expression a person on the org's side wrote. The tool runs
  it; it does not sandbox it. The spec is trusted input.
* **(b) The org's own service data, loaded into the in-memory engine.** The data
  is single-tenant and the org's own. It is read to compute aggregates, and it
  never leaves the local process.
* **(c) The CI and release supply chain.** The build, test, and release
  workflows and the dependency surface they draw on.
* **(d) The future optional Bedrock drafting seam.** This lands in v0.3 and is
  out of scope at v0.1. It is noted here so the boundary is named before the
  code exists.

## Assets to protect

The value of the tool is that a number cannot reach an export unless it traces
to a receipt. Protecting that property is the point of the analysis. The assets,
in the order they matter:

* **Integrity of exported figures.** The load-bearing invariant is that no
  number reaches an export without a receipt binding it to a deterministic query
  over a named data slice.
* **The fail-closed grounding gate.** The gate strips or flags any numeric span
  in the narrative that does not bind to a receipt, and it blocks export while
  any span is unbound. Its fail-closed behavior is itself an asset.
* **Small-cell suppression (v0.2).** Once suppression lands, a suppressed cell
  must not be recoverable, including by subtraction from complementary cells.
* **Aggregate-only output.** A report is counts, rates, and narrative. No
  client-level row leaves the process.
* **The supply chain.** The integrity of what a downstream user installs and
  runs.

## Method

This model uses STRIDE as its frame for the integrity and disclosure threats,
with a LINDDUN lens on the privacy angle where the two overlap (the suppression
and aggregate-only assets). The table below maps each threat to its mitigation
and status. Rows are drawn from the invariants recorded in
[`CLAUDE.md`](../CLAUDE.md) and [`SECURITY.md`](../SECURITY.md), not invented for
this document.

| Threat (STRIDE / LINDDUN) | Mitigation | Status |
|---|---|---|
| Spoofing or tampering of a figure so an unbacked number ships | Each figure carries a receipt with a BLAKE2b `slice_hash` over the canonicalized rows; the fail-closed grounding gate binds every numeric span to a receipt before export. `tests/test_grounding_gate.py`, merge-blocking. | In place (v0.1) |
| Tampering via a model-invented number entering the narrative | Numbers never originate in the model; the drafting seam writes prose around already-receipted figures, and the gate is the enforcement. `tests/test_no_model_numbers.py`, merge-blocking. | In place (v0.1) |
| Information disclosure of client-level data | Aggregate-only export path emits counts, rates, and narrative, never client-level rows; the DPIA posture in `RESPONSIBLE-TECH-AUDITS.md` records the data-minimization finding. | In place (v0.1) |
| Information disclosure by recovering a suppressed cell | Small-cell suppression with complementary suppression, so a suppressed cell cannot be recovered by subtraction. `tests/test_suppression.py`. | Planned (v0.2) |
| Tampering via malicious or erroneous spec SQL | Documented as trusted input; the query runs against an in-memory, single-tenant database loaded only with the org's own data, with no network surface to reach. Operators run only specs they or a colleague wrote. | Accepted (trusted input) |
| Supply-chain tampering with build or release artifacts | SHA-pinned GitHub Actions, least-privilege `GITHUB_TOKEN`, Sigstore build-provenance attestation, PyPI Trusted Publishing over OIDC, and a CycloneDX SBOM on release (commits 201d716, 42c33b5). | In place |
| Denial of service | Out of scope for an offline CLI with no network listener; a user who supplies a pathological spec affects only their own local run. | Out of scope |

## Out of scope

Correctness of a figure, a metric definition, or a report template is an eval,
spec, or data issue rather than a vulnerability, and `SECURITY.md` files it as a
normal issue. The seeded synthetic fixtures carry no secrets and no PII by
construction, so they hold nothing to disclose. Denial of service against an
offline CLI is not modeled, as noted in the table.

## Residual risks and roadmap toward 1.0

Some of the posture is still forward-dated, and this document names the gaps
rather than papering over them. The retention and data-flow map completes once
the suppression and export modes land, which fills out the DPIA's remaining TODO.
Suppression itself, with its complementary rule and the recovery-resistance it
buys, arrives in v0.2. When the optional Bedrock drafting seam lands in v0.3, a
model card for it ships alongside, and this threat model gains the boundary-(d)
analysis that is only named today. Each of these is tracked in
[`ROADMAP.md`](ROADMAP.md) and reflected back into
[`RESPONSIBLE-TECH-AUDITS.md`](RESPONSIBLE-TECH-AUDITS.md) as it lands.
