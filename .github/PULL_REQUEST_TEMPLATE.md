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
- [ ] `make eval` leaves `eval/report.md` unchanged, or the updated report is committed.
- [ ] Documentation links and examples were checked.
- [ ] `CHANGELOG.md` is updated when the change is user-visible.

## Contribution

- [ ] Every commit includes the required DCO sign-off.
