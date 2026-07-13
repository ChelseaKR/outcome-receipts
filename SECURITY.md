# Security Policy

outcome-receipts is an independent personal open-source project (Apache-2.0).
The default path is offline, with no network listener, authentication, or durable
client database and zero required runtime dependencies. An optional Bedrock extra
adds one explicitly authorized model request for prose only. The security posture
and current values are in [`docs/RESPONSIBLE-TECH-AUDITS.md`](docs/RESPONSIBLE-TECH-AUDITS.md).

## Supported versions

outcome-receipts is pre-1.0, so only the latest minor on the latest major receives security
fixes. A fix ships forward in a new patch release rather than a re-publish of an existing
version.

| Version | Supported | Notes                                      |
|---------|-----------|--------------------------------------------|
| 0.1.x   | Yes       | Current pre-1.0 security-support line.     |
| < 0.1.0 | No        | Pre-release snapshots are not supported.  |

When a `0.2.0` ships, `0.1.x` security support ends and this table is updated in the same
release.

## Reporting a vulnerability

**Please do not open a public GitHub issue, pull request, or discussion for a security
report.**

Report privately, by either:

1. **GitHub Security Advisory** via *Security -> Report a vulnerability* on the repository
   (preferred; it keeps the report, fix, and GHSA linked), or
2. **Email** to `ckellyreif@gmail.com` with subject `SECURITY: outcome-receipts`.

Please include, as far as you can:

- the affected version or commit,
- a minimal reproduction or proof-of-concept,
- the impact you believe it has, and
- any suggested remediation.

If you want an encrypted channel, say so in a first low-detail email and we will arrange one.

## Our commitments

| Stage                    | Target                                                            |
|--------------------------|-------------------------------------------------------------------|
| Acknowledgement & triage | within **72 hours** of receipt                                    |
| Severity assessment      | CVSS-based, shared with you in the triage reply                   |
| Fix or mitigation plan   | communicated after triage, prioritized by severity               |
| Coordinated disclosure   | by mutual agreement; default embargo up to 90 days               |
| Credit                   | named in the advisory and the `CHANGELOG.md` `Security` entry, unless you prefer to stay anonymous |

## Scope

In scope: the `outcome_receipts` package and CLI, the eval harness, the report/build/release
workflows, and the dependency supply chain. Because the value of the tool is that a number
cannot reach an export unless it traces to a receipt, an **integrity bypass is in scope**: a
demonstrated way to export a number that binds to no receipt (defeating the fail-closed
grounding gate), or a way to recover a suppressed cell, is a security report,
not a normal issue.

Out of scope: the seeded synthetic example data contains no secrets or PII by construction.
The *correctness* of a computed figure, a metric definition, or a report template is an eval,
spec, or data issue rather than a vulnerability; file those as normal issues.

## Supply chain

Release actions are pinned to commit SHAs, release artifacts carry a Sigstore build-provenance
attestation and a CycloneDX SBOM, and publishing to PyPI uses Trusted Publishing (OIDC, no
long-lived token). The CI token is least-privilege and does not persist credentials.
`make security` and CI run pip-audit, npm audit, OSV-Scanner, gitleaks,
Semgrep, and zizmor. CodeQL covers Python and Actions; OpenSSF Scorecard enforces
the portfolio score floors on its automatic triggers. `release.yml` re-runs the
full `make verify` gate at the tagged commit before signing or publishing.

## Hardening notes for operators

- Keep the default **offline** run; it has no network, auth, or persistence.
- Treat a report spec as trusted input. A metric is a SQL expression run over your loaded
  data slice, so run only specs you or a colleague wrote, the same way you would with any
  query file.
- Provide any future provider credentials by environment only; secrets are never committed.
