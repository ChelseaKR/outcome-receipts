# Definition of Done

Reviewed quarterly. The CODEOWNER protects changes to this file.

## AUTO-GATE

- [ ] `make verify` passes: formatting, lint, strict typing, tests, branch coverage,
      source hygiene, gettext parity, dependency/SAST/secret/workflow scans,
      WCAG 2.2 AA browser checks, generated cards, and the committed eval.
- [ ] The grounding, suppression, bundle, and re-derivation critical modules each
      retain at least 95% branch coverage; repository branch coverage stays at 90%.
- [ ] Every numeric span in every publishable surface binds to a receipt after
      suppression; client-level rows and identifiers never reach an export.
- [ ] All GitHub Actions references are full commit SHAs, tokens are least
      privilege, and release jobs use OIDC without build caches.
- [ ] CodeQL, OpenSSF Scorecard, the reusable-action dogfood check, and the pinned
      portfolio-standards check pass on their configured triggers.

## REVIEW-GATE

- [ ] A human reviews changed metric definitions, suppression behavior, cloud
      boundaries, and reviewer-facing copy for concrete harm and ambiguity.
- [ ] A new or changed guardrail, permission, dependency boundary, or quality
      threshold has an accepted ADR under `docs/adr/`.
- [ ] Accessibility, translation, threat-model, DPIA, AI-risk, and residual-risk
      artifacts are current for the release; manual assistive-technology rows are
      signed by the person who performed them.
- [ ] The CHANGELOG describes user impact, security changes name their advisory,
      and the public API is changed according to the pre-1.0 SemVer policy.
- [ ] The final redacted report requires a named human approver; review never
      bypasses grounding, suppression, or verification.

*Last reviewed: 2026-07-12 · Recheck: quarterly and before each release.*
