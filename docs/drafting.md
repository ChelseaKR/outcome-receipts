# Optional Bedrock narrative drafting

The deterministic template drafter is the default and makes no network calls.
Claude on Amazon Bedrock is an optional prose-rewrite seam. Until the first
package release, install the locked optional dependency from a repository clone:

```console
uv sync --locked --python 3.12 --group dev --extra bedrock
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

## Drafting in your own assistant: the local MCP server

Bedrock is one integration. Organizations draft in whatever assistant they
already use, and the risk is the same everywhere: a fluent number nobody
checked. `receipts mcp` puts the gate where the drafting happens.

```console
receipts mcp
```

It speaks JSON-RPC 2.0 over standard input and output — the MCP stdio
transport — and nothing else. No socket, no port, no network of its own, and no
new dependency: the transport is newline-delimited JSON over two file objects,
so this ships in the default install rather than behind an extra. Configure it
in your client the way any stdio MCP server is configured, with `receipts` as
the command and `mcp` as its argument.

### The tools

Four, all read-only. This is the whole surface; a name outside it is refused
before any handler runs.

| Tool | Arguments | Returns |
|---|---|---|
| `list_publishable_figures` | `config` | Every figure the report may publish: `display`, `value`, `unit`, `kind`, `definition`, `indicator`, `caveat`, `suppressed`. A withheld cell carries the redaction marker and a null value. |
| `audit_narrative` | `config`, `text` | The same object `receipts audit --json` prints: `ok`, `total`, `bound`, `suppressed` spans, `unbound` spans. |
| `verify_receipts` | `config`, `receipts` | The same object `receipts verify --json` prints. |
| `trace_figure` | `config`, `metric_id` | One publishable figure's receipt: definition, unit, query, row count, slice hash, columns, timestamp. |

### The pattern: draft, then audit

1. The assistant asks for `list_publishable_figures` and writes prose using
   those display strings verbatim.
2. It calls `audit_narrative` on its own draft *before* showing it to anyone.
3. Every span in `unbound` is a number that binds to no receipt: it must be
   removed or rewritten as the receipt writes it. Every span in `suppressed` is
   worse — it states a cell the report withholds, and must be removed.
4. When the audit passes, a human runs `receipts run` and signs off. That is
   still the only path to an export.

### What it cannot do

- **It cannot export.** There is no `run` tool, no write tool, and no approval
  tool. Sign-off stays a human at a terminal.
- **It cannot disclose a withheld cell.** Every tool answers from the
  post-suppression figure set. `trace_figure` on a suppressed metric returns
  the marker, a null value, a null row count and a null slice hash, alongside
  the definition — enough to tell "withheld" from "does not exist", and nothing
  more. `tests/test_mcp_server.py` drives every tool against a figure set whose
  withheld member carries a value found nowhere else in the project, then
  searches every byte of every response for it.
- **It cannot log your draft.** A tool's arguments are the author's text, so
  the error path names the method and the exception class and nothing else.
  There is no log level that turns the text back on.
- **It declares no `sampling` capability.** A server that could ask the client's
  model a question would be a second path to a number, which is the one thing
  this project does not have.

The MCP revision declared at `initialize` is recorded once, as
`PROTOCOL_VERSION` in `src/outcome_receipts/mcp.py`.
