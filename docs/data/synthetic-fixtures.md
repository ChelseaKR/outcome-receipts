# Data card: committed synthetic fixtures and eval cases

- Source and publisher: authored in this repository by Chelsea Kelly-Reif.
- License: Apache-2.0.
- Tier: L1 synthetic, non-sensitive; no record represents a real person.
- Refresh cadence: updated with the behavior or eval change that needs a new case.
- Fetch timestamp: N/A, generated and versioned in git rather than fetched.
- Retention: indefinite as test and release evidence.
- Dataset version: repository release tag and commit SHA.

## Coverage and limitations

Fixtures cover housing-service examples, planted receipt-backed values, planted
unbound numbers, suppression recovery paths, mapping ambiguity, English/Spanish
numeric spans, bundle tampering, and all six version-1.0 evidence-workflow
artifacts. They are deliberately small and do not represent the distribution or
data quality of any real organization's records.

The compatibility directory also preserves the signed `v0.1.0` housing fixture
byte-for-byte, with its immutable source commit recorded in `SOURCE.md`. It is
synthetic L1 data, not an organization export.

*Last verified: 2026-08-21 · Recheck cadence: with each eval or fixture change, and at least quarterly.*
