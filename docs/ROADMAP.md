# Roadmap

*Last verified: 2026-07-11 · Recheck: quarterly*

Planned direction for outcome-receipts. Dates are intentions, not promises;
items move earlier when users ask for them. Feedback is welcome as GitHub issues.

The sequencing rule: ship the differentiator first with the least-risky
subsystems, then grow outward. The differentiator is the receipt plus the
fail-closed grounding gate. The risky parts (an LLM in the drafting path, metric
mapping over messy real exports) come after the trust machinery has proven out.

## Architecture

A deterministic state machine: compute figures with receipts, draft and ground
against the raw receipted values, suppress every publishable surface, ground the
redacted result again, let a human approve, export.

```
compute -> draft -> ground -> suppress -> re-draft/re-ground -> approve -> export
(SQL +     (figures   (raw       (privacy     (publishable      (human     (bundle +
 receipt)   only)      gate)       gate)         gate)            sign-off)  manifest)
```

## v0.1.0 — Receipts, no LLM (released 2026-07-11)

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

## v0.2.0 — Small-cell suppression (completed)

* ✅ The privacy invariant: aggregate counts below a threshold suppressed, with
  complementary suppression and true zeros preserved, modeled on the U.S. CMS
  Cell Size Suppression Policy. CMS—not HUD—supplies the numeric default; HUD's
  HMIS publication guide leaves the numeric rule to the applicable local policy.
  Implementation: threshold = 11 (CMS policy: suppress 1–10), complementary
  suppression applied to totals, true zeros (0) preserved. Tested with
  comprehensive cases covering threshold behavior, complementary suppression, and
  aggregate-only export. Merge-blocking: `tests/test_suppression.py`.
* ✅ Aggregate-only export mode for figures shared externally. Provenance
  attestation includes `aggregate_only: true`; the artifact boundary accepts
  only scalar `Figure` objects and never receives the source client rows.

## v0.3.0 — The drafting seam

* ✅ An optional Claude-on-Bedrock drafter that writes the narrative prose around the
  receipted figures, guarded by the same grounding gate. Off by default and
  policy-gated by config plus `--allow-cloud-drafting`, so the deterministic
  drafter remains the zero-dependency default. The manifest records which
  narrative drafter was used; both raw and publishable drafts must pass the gate.
* If an LLM judge scores narrative faithfulness, calibrate against human labels
  with Cohen's kappa and fail closed on drift.
* ✅ Generated [model](cards/model-card.md) and [data](cards/data-card-reporting.md) cards describe the
  provider boundary, limitations, evaluation, privacy, and retention. Tagged
  release verification fails if committed cards drift from the generator.

## v0.4.0 — The metric-mapping agent

* ✅ Map a funder template's required metrics to deterministic queries over a
  schema-variant export (HMIS CSV and common funder shapes), with a review queue
  for mappings. `receipts map` recognizes canonical fields and documented HMIS
  aliases, emits candidate `MetricSpec` queries, blocks missing/ambiguous fields,
  and marks every candidate `pending`/`review_required`; it never executes or
  approves a guess. See [metric-mapping.md](metric-mapping.md).

## v0.5.0 — Provenance manifest and verify (completed)

* ✅ Each exported report carries a manifest of its receipts and slice hashes;
  `receipts verify` re-checks that the figures still compute from the cited data.
* **EXP-11 — Hash-chained export ledger (shipped).** `run` appends every
  successful export to an append-only, hash-chained ledger (report title, a
  BLAKE2b hash of the receipts manifest, recipient, timestamp), each entry linked
  to the prior by hash so tampering is detectable. `receipts verify-ledger`
  re-hashes the chain and fails closed on any break. The record of what was
  reported to whom is itself receipted. See ADR 0004.
* ✅ **Shipped:** `receipts verify` is packaged as a reusable composite GitHub Action
  (`action.yml`), so a downstream repo can gate CI on receipt drift with
  `uses: ChelseaKR/outcome-receipts@v1`. See [ci-action.md](ci-action.md).

## v1.0.0 — Future stability gates (not open implementation backlog)

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
* **FIX-11 — property-based and mutation testing on the invariant core (done).**
  The grounding gate is covered by Hypothesis property tests
  (`tests/test_grounding_properties.py`): over adversarial narratives that mix
  receipted figure displays with randomly injected numbers, every ungrounded
  number lands in `unbound`, `ok` is true iff `unbound` is empty, redaction is
  total, and grounding is idempotent after redaction. Mutation testing (mutmut,
  `make mutation`) is scoped to `grounding.py` and `engine.py`; the property
  tests kill every mutant in the grounding gate itself.

## Metrics ledger

| Attribute | Current value | Gate |
|-----------|---------------|------|
| AI-Evaluation-Standard | APPLIES — optional Bedrock prose drafter; numeric grounding, red-team, cards, and governance tiers; no RAG or judge | REVIEW scope declaration |
| Grounding rate | 100% of numeric spans bound on exported fixtures; any unbound span blocks | AUTO |
| Bilingual benchmark | 100 committed cases: 50 EN, 50 ES; 50 planted unbound failures all rejected | AUTO |
| Hallucinated-number rate | Reported with Wilson intervals in `eval/report.md` | AUTO artifact / REVIEW interpretation |
| LLM judge calibration | N/A — no model judge ships; calibration becomes blocking before one can gate | Declared N/A |
| Branch coverage | 90% repository floor; integrity-critical module group 95% | AUTO |
| Mutation quality | 0 surviving grounding-gate mutants in the last scoped run | REVIEW/nightly |
| Small-cell privacy | Counts 1–10 plus complementary, delta, and percentage recovery controls; zero is distinct | AUTO |
| Supply chain | CycloneDX 1.7, signed attestations, exact published bytes, OIDC, SHA-pinned Actions | AUTO |
| SAST/SCA/secrets | Ruff, Semgrep, CodeQL, pip-audit, npm audit, OSV, gitleaks, zizmor | AUTO |
| OpenSSF Scorecard | Aggregate and named critical-check floors enforced in scheduled/push workflow | AUTO |
| axe WCAG 2.2 AA | 0 critical, serious, or moderate violations on generated trace | AUTO |
| pa11y | 0 errors on generated trace | AUTO |
| Lighthouse accessibility | At least 0.90 on generated trace | AUTO |
| Keyboard/reflow/motion | Native-link path; no overflow at 320px; no residual motion | AUTO + REVIEW |
| Screen readers | VoiceOver/macOS and NVDA/Windows task reviews not yet executed | REVIEW blocker |
| i18n | 51 EN/ES gettext keys, zero missing/fuzzy entries, placeholder parity | AUTO |
| Data governance | Three current data cards; L3 input ephemeral, L2 output operator-retained | AUTO + REVIEW |
| Incident response | 0 recorded incidents; label/postmortem and secret runbook armed | REVIEW |

### DORA and quality-debt baseline

Portfolio collection on 2026-07-11 measured 2.1 deploy/merge proxies per week,
149.8 hours median lead time, 0.0 revert-based change-fail ratio, 27 merges, and
3.19 PRs per week over the 90-day window. These are observe-only proxies, not
release gates. The same run measured 0.074 churn ratio, 69% short-term churn,
100% unreviewed merges, and zero reverts. The unreviewed-merge value is a risk
signal for a solo-maintained, agent-assisted repo and motivates the required PR
acknowledgement and complete automated gates.

## Out of scope

* Becoming a data warehouse or BI tool. It computes the figures a report needs
  and proves them.
* Inventing a verification primitive. The verify-or-flag idea is published; the
  contribution is the open offline chain, the metric mapping, and the privacy
  posture.
