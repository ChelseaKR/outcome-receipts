# Responsible-Tech Audits — outcome-receipts

Project-specific findings under the portfolio Responsible-Tech Framework. This
artifact is reviewed on release; generic thresholds remain in portfolio-standards.

## Applicability

- A Ethics: applies.
- B Bias: applies because metric definitions and denominators shape claims.
- C Privacy/DPIA: applies; client-level L3 data is processed ephemerally and L2
  aggregates are published.
- D Transparency: applies; figures, model boundary, cards, and eval are disclosed.
- E Accessibility: applies to generated trace HTML and chart SVG.
- F Security: applies; ASVS authentication level is N/A because the offline CLI
  has no auth, authorization, or network ingress. SAST, SCA, secret scanning, and
  supply-chain controls still apply.
- AI Evaluation: applies to the optional Bedrock drafting seam; RAG retrieval
  metrics are N/A because there is no retriever, corpus, or vector store.
- Internationalization: applies to public report and trace output in EN/ES.

## A. Ethics

The primary harm is a wrong or invented number reaching a funder, with funding
and credibility consequences for the organization and indirect effects on the
people it serves. The control is structural: SQL computes figures, immutable
receipts record derivation, both pre- and post-suppression narratives pass the
numeric-span gate, and a named person approves the final redacted artifact.

Review gate: changing the numeric origin, approval order, or export boundary
requires an ADR and explicit trust/privacy review in the pull request.

## B. Bias and fairness

A correct query can encode an unfair definition. Receipts therefore carry a
plain-language definition, denominator, unit, category assumptions, data source,
collection frequency, and caveat when provided. Mapping candidates never approve
themselves; ambiguity and missing columns enter a human review queue.

Known limits remain: receipts do not prove collection completeness, consent,
measurement validity, causal impact, or that a category scheme treats groups
fairly. EN/ES benchmark parity proves the same numeric grounding enforcement in
both languages, not cultural or narrative-quality parity.

## C. Privacy and data-protection impact assessment

### Data flow and classification

Organization CSV rows are L3 while held in process. The loader validates them and
creates an in-memory SQLite table. Compute emits scalar figures with exact query,
row count, column names, BLAKE2b slice hash, value, and timestamp. Drafting,
grounding, suppression, rendering, bundles, and ledgers operate on figures and
provenance, not source rows. Published reports and manifests are L2 aggregates.

The optional Bedrock request is the sole cloud boundary. It receives the filled
narrative and scalar display allowlist only, with no rows, identifiers, SQL,
hashes, or paths. It is disabled unless the config policy and per-run CLI flag
both opt in. Small aggregate displays can reach the provider before publication
suppression, so the adopting organization must authorize the transfer and review
its Bedrock logging and retention configuration.

### Minimization, suppression, retention, and recovery

The application does not copy or persist source rows. Counts 1 through 10 are
redacted under the CMS-modeled default; complementary, delta, and percentage
controls block direct arithmetic recovery, while true zero remains distinct.
HUD does not prescribe that numeric floor, so the report's controlling local or
funder policy remains the operator's decision.

Reports, receipts, bundles, and the export ledger contain aggregates and
provenance. They remain under operator retention. The application has no durable
client database; backup and restore are documented as copying the report inputs,
outputs, key, and ledger together, then running all verify commands before trust.

Data cards: `docs/data/organization-service-export.md`,
`docs/data/synthetic-fixtures.md`, and `docs/cards/data-card-reporting.md`.

## D. Transparency and explainability

Every figure carries the query, row count, slice hash, timestamp, unit, and
definition. The report and accessible trace render that evidence; manifests and
bundle hashes support machine verification. `receipts verify`, bundle verification,
and ledger verification fail closed on drift.

The generated model and data cards describe the Bedrock boundary, limitations,
out-of-scope uses, and bilingual gate evidence. The committed eval reports Wilson
confidence intervals, and the 100-case benchmark includes planted EN/ES failures.
No model judge ships, so judge calibration is explicitly N/A until one is added.

## E. Accessibility

The generated trace and charts target WCAG 2.2 AA. `make a11y` builds a real trace
and runs axe, pa11y, Lighthouse accessibility ≥0.90, 320px reflow, and reduced
motion checks. Charts have an SVG title and description plus equivalent data
tables. EN/ES pages set the document language.

Review artifacts: `docs/a11y/ACR.md`, `docs/a11y/STATEMENT.md`, and the dated
screen-reader walkthrough. The required macOS VoiceOver and Windows NVDA task
walkthroughs remain unexecuted; they are recorded as a release review blocker and
are not inferred from automated results.

## F. Security and supply chain

- ASVS: N/A for auth/authz/ingress because the product is an offline CLI. Input
  validation, SQL trust boundaries, output encoding, and all supply-chain controls
  still apply.
- Container scanning: N/A because the repository has no Dockerfile or image.
- SBOM/signing: CycloneDX 1.7 SBOM plus GitHub Sigstore-backed build and SBOM
  attestations on every signed-tag release; PyPI uses OIDC Trusted Publishing.
- Secret policy: credentials stay in environment/provider stores, never config;
  rotate and revoke first on exposure, then assess history and notification using
  `docs/OPERATIONS.md`. Review annually.
- SAST/SCA/secrets: Ruff security rules, Semgrep, CodeQL, pip-audit, OSV-Scanner,
  npm audit, gitleaks, zizmor, and OpenSSF Scorecard are blocking on their declared
  triggers. Dynamic SQL waivers are narrow, quoted/trusted, and tracked in issue
  52 plus `.semgrep-waivers.yml`. The Python 3.7 compatibility false positive
  remains tracked in issue 53; a no-suppression scan on 2026-07-12 confirmed the
  combined Semgrep profile still reports it against this Python 3.12-only package.
- VEX: N/A today because scans report no unfixable HIGH/CRITICAL dependency CVE.
  Any future exception requires a CycloneDX VEX and quarterly review.

Threat and governance artifacts: `docs/THREAT-MODEL.md`, the AI risk register,
impact assessment, ISO 42001 applicability map, red-team report, and residual-risk
register under `docs/audits/`.

## Gate checklist

| Control | Gate | Evidence |
|---|---|---|
| No unbound number survives export | AUTO | Grounding, property, benchmark, and CLI tests |
| Small-cell and complementary recovery blocked | AUTO | Suppression and exhaustive recovery tests |
| Aggregate-only output | AUTO | Renderer and manifest tests |
| EN/ES key and placeholder parity | AUTO | gettext extraction/compile/parity target |
| Generated HTML accessibility | AUTO | axe, pa11y, Lighthouse, reflow, reduced motion |
| Dependency, secret, SAST, workflow security | AUTO | `make security`, CodeQL, Scorecard |
| Model/data cards and eval current | AUTO | generated-card and eval diff checks |
| Metric/policy fairness review | REVIEW | Human approval and ADR/PR checklist |
| Manual assistive-technology review | REVIEW | Dated walkthrough; currently incomplete |
| Residual-risk acceptance | REVIEW | Dated residual-risk register |

Status: beta. *Last verified: 2026-07-12 · Recheck: quarterly and every release.*
