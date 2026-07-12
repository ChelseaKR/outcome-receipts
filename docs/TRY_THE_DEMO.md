# Try the five-minute demo

This walkthrough produces a human-approved housing outcome report, inspects the
receipt behind its publishable figure, and independently re-derives the result.
It uses synthetic data and makes no network calls.

## Prerequisites

- Python 3.12 or newer
- [uv](https://docs.astral.sh/uv/)
- GNU Make

## Run and verify

```sh
git clone https://github.com/ChelseaKR/outcome-receipts.git
cd outcome-receipts
make install
.venv/bin/receipts run \
  --config examples/housing-demo/report.toml \
  --out out/demo \
  --approved-by "Demo reviewer"
.venv/bin/receipts verify \
  --config examples/housing-demo/report.toml \
  --receipts out/demo/receipts.json
```

A successful run prints `grounding gate: PASS`. Verification then reports that
all receipts match. Open these files to follow the trust chain:

- `out/demo/report.md` is the drafted, grounded, suppressed, approved report.
- `out/demo/trace.html` explains every publishable figure without requiring SQL.
- `out/demo/receipts.json` is the machine-readable receipt manifest.
- `out/demo/bundle.json` records the exported artifacts and their digests.

The example intentionally contains small cells. The default CMS-modeled policy
suppresses counts from 1 through 10 and applies complementary controls so the
hidden values are not exposed by straightforward subtraction. This is a
demonstration policy, not a compliance determination for a specific report.

## See the gate fail closed

Audit a short narrative that contains the receipted total and an invented
additional number:

```sh
printf 'We served 12 clients and 999 additional clients.\n' > /tmp/outcome-receipts-draft.md
.venv/bin/receipts audit \
  --config examples/housing-demo/report.toml \
  --narrative /tmp/outcome-receipts-draft.md
```

The audit exits non-zero and identifies the unbound number. The normal export
path applies the same rule and refuses to write a report with an unbound numeric
span.

## Tell us what happened

- [Report a successful or blocked demo run](https://github.com/ChelseaKR/outcome-receipts/issues/new?template=demo-run.yml)
- [Bring an anonymized schema for mapping help](https://github.com/ChelseaKR/outcome-receipts/issues/new?template=schema-mapping.yml)
- [Ask a question in Discussions](https://github.com/ChelseaKR/outcome-receipts/discussions)

Do not attach client-level data, identifiers, credentials, or a real service
export to an issue or discussion.
