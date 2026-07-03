# Roadmap

*Last verified: 2026-07-05 · Recheck: quarterly*

Planned direction for outcome-receipts. Dates are intentions, not promises;
items move earlier when users ask for them. Feedback is welcome as GitHub issues.

The sequencing rule: ship the differentiator first with the least-risky
subsystems, then grow outward. The differentiator is the receipt plus the
fail-closed grounding gate. The risky parts (an LLM in the drafting path, metric
mapping over messy real exports) come after the trust machinery has proven out.

## Architecture

A deterministic state machine: compute figures with receipts, draft a narrative,
run the grounding gate, suppress small cells, let a human approve, export.

```
compute  ->  draft  ->  ground  ->  suppress  ->  approve  ->  export
(SQL,        (fill      (every     (small-cell   (human      (report +
 receipt)     template)  number     redaction)    sign-off)   manifest)
              binds to a
              receipt)
```

## v0.1.0 — Receipts, no LLM (scope complete on `main`; not yet tagged/released)

* Service-data CSV in, a TOML metric spec, the deterministic SQLite engine,
  receipts, the deterministic template drafter, and the grounding gate.
* Committed eval (`eval/report.md`) on seeded synthetic fixtures; the gate is a
  merge-blocking test.
* Definition of done: a messy figure set resolves to a receipted report, every
  number in the narrative binds to a receipt, and an injected unverifiable number
  is caught. Met.

### Expansions

* **EXP-02 author-declared data checks (pre-compute quality gate) — done.**
  Spec authors declare `[[data_checks]]` data-quality assertions (each an
  `assert_sql` returning a single scalar) that run before any figure is computed
  and fail closed: a violated precondition raises before a receipt is produced and
  blocks the whole run/export, extending the "fail closed everywhere" invariant to
  the data the figures rest on.

## v0.2.0 — Small-cell suppression

* The privacy invariant: aggregate counts below a threshold suppressed, with
  complementary suppression and true zeros preserved, modeled on the U.S. CMS
  Cell Size Suppression Policy. Sourced from primary guidance, expressed as tests.
* Aggregate-only export mode for figures shared externally.

## v0.3.0 — The drafting seam

* An optional Claude-on-Bedrock drafter that writes the narrative prose around the
  receipted figures, guarded by the same grounding gate. Off by default and
  policy-gated, so the deterministic drafter remains the zero-dependency default.
* If an LLM judge scores narrative faithfulness, calibrate against human labels
  with Cohen's kappa and fail closed on drift.

## v0.4.0 — The metric-mapping agent

* Map a funder template's required metrics to deterministic queries over a
  schema-variant export (HMIS CSV and common funder shapes), with a review queue
  for low-confidence mappings. This is the hard, unserved part; it lands after the
  trust machinery is proven.

## v0.5.0 — Provenance manifest and verify

* Each exported report carries a manifest of its receipts and slice hashes;
  `receipts verify` re-checks that the figures still compute from the cited data.
* **EXP-11 — Hash-chained export ledger (shipped).** `run` appends every
  successful export to an append-only, hash-chained ledger (report title, a
  BLAKE2b hash of the receipts manifest, recipient, timestamp), each entry linked
  to the prior by hash so tampering is detectable. `receipts verify-ledger`
  re-hashes the chain and fails closed on any break. The record of what was
  reported to whom is itself receipted. See ADR 0004.
* **Shipped:** `receipts verify` is packaged as a reusable composite GitHub Action
  (`action.yml`), so a downstream repo can gate CI on receipt drift with
  `uses: ChelseaKR/outcome-receipts@v1`. See [ci-action.md](ci-action.md).

## v1.0.0 — Stability commitments

Gated on the pipeline proving out against more than one real organization and on
a stable spec and report schema for two consecutive releases. Adds a second
template format, one-command Docker self-host, committed responsible-tech audits,
and semantic-versioning guarantees on the spec and the receipts manifest schema.

## Eval and quality plan

* The gated metric is the **grounding rate**: the share of numbers in the
  narrative that bind to a receipt, fail-closed at 100%. The hallucinated-number
  rate is reported with Wilson confidence intervals.
* Fixtures are seeded synthetic with planted ground-truth figures and a planted
  unverifiable number; zero real personal data.

## Metrics ledger

| Attribute | Target | Gate |
|-----------|--------|------|
| Grounding rate (eval) | 100%, fail-closed | AUTO |
| Test coverage (logic) | per CODE-QUALITY-STANDARD | AUTO |
| Hallucinated-number rate | reported with Wilson CIs | REVIEW |
| Small-cell suppression invariants | from primary CMS guidance, as tests | AUTO (v0.2) |
| LLM judge calibration (Cohen's kappa) | fail-closed on drift | AUTO (v0.3) |
| Supply chain | SBOM, signed releases, SHA-pinned actions | AUTO — landed in `release.yml` and `ci.yml`'s `security` job (pip-audit, osv-scanner, gitleaks, zizmor) |
| Accessibility (trace.html) | zero pa11y WCAG2AA errors | AUTO — `ci.yml`'s `accessibility` job |

## Out of scope

* Becoming a data warehouse or BI tool. It computes the figures a report needs
  and proves them.
* Inventing a verification primitive. The verify-or-flag idea is published; the
  contribution is the open offline chain, the metric mapping, and the privacy
  posture.
