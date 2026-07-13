# Portfolio standards conformance audit — 2026-07-12

Authority: local `portfolio-standards` tag v1.0.1. Scope: code, tests, local gates,
GitHub workflows and settings, releases, docs, generated report surfaces, optional
Bedrock seam, and project-specific review artifacts.

| Area | Initial finding | Remediation |
|---|---|---|
| Tier-1 automation | 26/30; old ruff/mypy floors, missing canonical ADR path, i18n declaration mismatch | Canonical tool floors, `docs/adr/`, explicit applies declaration; local Tier-1 structural controls pass except its N/A-only i18n heuristic. |
| Local/CI parity | Security, accessibility, i18n, cards, and eval lived outside `make verify` | One full `make verify`; focused CI jobs call the same targets. |
| Code quality | No minimum pytest setting, no critical-module floor, unowned suppressions | Canonical config, 95% critical group, issue-linked narrow suppressions, hygiene gate. |
| Security | CodeQL/Scorecard absent; private vulnerability reporting disabled | Automatic CodeQL and Scorecard workflows, live private reporting enabled, full local scanner chain. |
| Supply chain/release | CycloneDX defaulted to 1.6; no published-artifact smoke verification | Explicit CycloneDX 1.7 and post-publish attestation/PyPI verification. |
| CI governance | Main ruleset lacked PR, signature, linear-history, and strict checks | Live ruleset hardened; standards checkout uses a read-only deploy key pinned to v1.0.1. |
| Documentation | 11/13 conformance rows; no Definition of Done, incident/data/operations artifacts; stale roadmap claims | Complete declaration and current project artifacts; canonical ADR migration record. |
| Accessibility | pa11y only; no axe/Lighthouse/reflow/motion or ACR/walkthrough | Full browser gate plus ACR, statement, and dated walkthrough. Manual NVDA/VoiceOver rows remain honestly pending. |
| Internationalization | Bespoke Python dictionaries and English-only trace | Packaged gettext EN/ES catalogs, complete localized trace, extraction/compile/parity/BCP47 gates and review artifacts. |
| AI evaluation/governance | Generated cards incomplete and noncanonical; no benchmark/risk/impact/SoA/red-team records | Canonical generated cards, 100-case bilingual benchmark, risk register, impact assessment, SoA, red-team and residual-risk records. |
| Data governance | DPIA prose but no per-source cards or recovery procedure | L3 input/L2 output cards, retention and verified recovery runbook. |
| Responsible tech | Stale future-tense findings after features shipped | Current six-audit artifact and explicit gate checklist. |

## Remaining human review gate

One control cannot be executed by this coding session: the required task
walkthrough with VoiceOver + Safari on macOS and NVDA + Firefox/Chrome on Windows.
The ACR remains Partially Supports and the dated walkthrough names the exact
evidence a human must record. This is not waived or silently marked green.

## External-state evidence

The live main ruleset blocks deletion and force-push, requires signed linear
history and pull requests, and requires strict status checks without bypass
actors. Default workflow permissions are read-only. Private vulnerability
reporting is enabled. Release v0.1.0 carries an SBOM and attested build artifacts;
the next release workflow adds the explicit 1.7 and published-verification gates.

*Audited: 2026-07-12 · Recheck: next standards bump or quarterly.*
