# Optional Bedrock narrative drafting

The deterministic template drafter is the default and makes no network calls.
Claude on Amazon Bedrock is an optional prose-rewrite seam. Until the first
package release, install the locked optional dependency from a repository clone:

```console
uv sync --frozen --python 3.12 --group dev --extra bedrock
source .venv/bin/activate
```

After a package is published, the equivalent package install will be
`pip install 'outcome-receipts[bedrock]'`.

Opt in in the report spec:

```toml
[report.drafting]
provider = "bedrock"
enabled = true
model_id = "anthropic.claude-3-5-sonnet-20241022-v2:0"
max_tokens = 1200
```

Each run also requires explicit authorization:

```console
receipts run --config report.toml --out out --allow-cloud-drafting --approved-by REVIEWER
```

Without the CLI flag, the command fails before drafting. The Bedrock request
contains the filled baseline narrative and scalar display allowlist—not source
rows, identifiers, SQL, hashes, or paths. The model is called once against raw
receipted figures and again after suppression. Both drafts pass the same exact,
fail-closed numeric grounding gate; any invented, altered, rounded, signed,
ranged, or written-out number blocks export. A named human still approves the
redacted final artifact.

The first request can contain small aggregate displays. Enabling cloud drafting
therefore requires an organization-level data-transfer decision even though the
published report later suppresses those cells. Bedrock account logging and
retention settings remain the operator's responsibility. See the generated
[model card](cards/model-card.md) and [data card](cards/data-card-reporting.md).
