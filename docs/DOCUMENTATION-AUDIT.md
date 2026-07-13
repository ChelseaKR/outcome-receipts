# Documentation audit

Reviewed 2026-07-12 against portfolio-standards v1.0.1.

## Result

The root entry, process, security, release, citation, license, conduct, Definition
of Done, standards pin, and contributor files are present. The documentation set
now includes a canonical `docs/adr/` log, operations and incident runbooks, source
and synthetic data cards, generated AI cards, accessibility artifacts, i18n policy
and review records, threat/DPIA findings, and AI governance artifacts.

The README declares all thirteen standards with an applicable tier or reason. The
roadmap records project values rather than restating generic gates. Currency-
sensitive docs carry a verification date and recheck condition.

## Known review dependency

The accessibility ACR correctly remains Partially Supports until a person records
the required VoiceOver/macOS and NVDA/Windows walkthroughs. No document represents
those unperformed human checks as passing.

## Validation

`scripts/check_conformance.py` checks required artifacts, the standards SemVer
pin, and all README rows. The source-hygiene and i18n checks cover issue-linked
suppressions, catalog extraction/parity, and authored UTF-8. Relative Markdown
links are checked during this remediation and `make verify` gates the executable
artifacts and generated cards.

*Last verified: 2026-07-12 · Recheck: quarterly, each release, and each standards bump.*
