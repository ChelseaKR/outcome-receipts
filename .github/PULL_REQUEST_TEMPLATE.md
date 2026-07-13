## What changed

<!-- Describe the behavior or documentation change and why it is needed. -->

## Trust and privacy review

- [ ] No model path can create or alter a report figure.
- [ ] Unbound numbers and uncertain mappings still fail closed.
- [ ] No publishable artifact exposes suppressed or client-level data.
- [ ] Any changed definition or policy cites its authoritative source.
- [ ] Not applicable; this change does not touch those invariants.

## Validation

- [ ] `make verify`
- [ ] Generated cards, catalogs, benchmark, and eval artifacts are unchanged or their updates are committed.
- [ ] Documentation links, examples, and currency stamps were checked.
- [ ] `CHANGELOG.md` is updated when the change is user-visible.

## Definition of Done review

- [ ] Applicable AUTO-GATE and REVIEW-GATE rows in `DEFINITION_OF_DONE.md` are complete.
- [ ] Any guardrail, permissions, dependency-boundary, public-API, or threshold change links a new accepted ADR under `docs/adr/`.
- [ ] Accessibility, i18n, data-governance, AI-risk, threat-model, and residual-risk artifacts are updated when their boundary changes.
- [ ] Security changes name the advisory/waiver owner and do not silence a blocking gate.

## Contribution

- [ ] Every commit includes the required DCO sign-off.
