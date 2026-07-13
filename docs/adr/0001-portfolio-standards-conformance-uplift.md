# Adopt the portfolio standards as executable gates

- Status: Accepted
- Date: 2026-07-12
- Deciders: Chelsea Kelly-Reif

## Context

The repo's original gates proved the receipt and grounding core but left security,
accessibility, i18n, documentation, and AI-governance checks split between CI and
prose. Tool version floors and the standards applicability entry had also drifted.

## Decision

`make verify` is the executable local gate. It includes the applicable code,
security, i18n, accessibility, AI-eval, generated-card, and documentation checks.
CI calls the same targets. Reviewer-facing copy moves from Python dictionaries to
packaged gettext catalogs. The repo consumes portfolio-standards v1.0.1 through a
read-only deploy key and records the pin in `.standards-version`.

The offline deterministic path remains the default. The Node dependency set is
development-only and exists solely to scan generated HTML; shipped Python runtime
dependencies remain empty unless the Bedrock extra is explicitly installed.

## Consequences

Local verification now needs Node 22 and downloads browser/security tooling during
installation. The stronger gate costs more time but detects drift before merge.
Manual NVDA and VoiceOver review remains a human review artifact and cannot be
truthfully replaced by automation.
