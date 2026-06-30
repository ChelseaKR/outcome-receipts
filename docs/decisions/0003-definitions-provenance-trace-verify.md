# 0003 — Definitions, provenance, a trace view, and re-derivation

Status: accepted (working tree, uncommitted)

## Context

v0.1 ships the differentiator: a figure with a receipt and a fail-closed grounding
gate. A synthetic persona panel (`docs/USER-RESEARCH.md`) and a research-backed
triage (`docs/RESEARCH-ROADMAP.md`) surfaced one consistent gap. The proof exists,
but it is illegible and unverified for the people who receive the report: the
receipts manifest is JSON, a figure's definition lives only in its SQL, and nothing
on the page tells a skeptical funder that no number came from a model or lets an
auditor re-derive a committed figure. None of the fixes needs a model, so all fit
v0.1's no-LLM constraint. This ADR records four that ride alongside the v0.2 work.

## Decisions

### A definition rides in the receipt

A `MetricSpec` gains an optional `definition`: a plain-language statement of the
window, who is in scope, and the deduplication rule. It flows into the `Receipt`
at compute time and renders next to the figure in the report, the manifest, and the
trace view. `description` stays a short label; `definition` is the precise statement
a reviewer can contest. This closes the bias-audit TODO on definitional traps
(deduplication windows, exit-destination categories): the choice a query encodes is
stated in words rather than inferred from SQL. The field defaults to empty, so it
is additive and no existing spec breaks.

### A provenance statement is embedded in every export

The product is the answer to a funder rejecting model-written numbers, so the
export says so. A standard block is written into the report body and a
machine-readable record into the manifest: every number came from a deterministic
query, no figure was written by a model, and the grounding gate bound every number
before export, with the count. The block is assembled from the gate's own counts;
it is not generated prose. It pairs with the PASS summary the CLI already prints.

### A trace view renders the receipts for a non-engineer

The receipts manifest is machine-readable, which makes it unreadable to a grant
manager or program officer. `run` now also writes `trace.html`: one self-contained
page with a summary table of every figure (value, definition, row count) and a
receipt detail per figure (query, slice hash, timestamp). It is built as text with
the standard library, carries no script and no external asset, and is semantic and
high-contrast, so it opens offline and meets WCAG 2.2 AA the way the chart output
does. It reads the same figures the report and manifest use, so it adds no second
path to a number and no client-level surface.

### `receipts verify` re-derives a committed manifest

A receipt is only worth trusting if it can be re-derived. `receipts verify`
recomputes every figure from the spec and the cited data, then checks each value,
slice hash, row count, query, unit, and display against the manifest. The timestamp
is excluded on purpose: it differs run to run by design, so comparing it would flag
every re-run as drift. Verify fails closed, reporting every drifted receipt and any
receipt with no matching figure (or figure with no receipt) and exiting non-zero.
This is a thin, deterministic forward cut of the v0.5 provenance-and-verify line.

## Consequences

- The differentiator is legible and reproducible to the report's recipient, with no
  model anywhere near a number. The grounding gate, the aggregate-only posture, and
  the no-LLM constraint are unchanged.
- `render_report` and `receipts_manifest` take an optional provenance argument and
  omit the block when it is absent, so existing callers and tests are unaffected.
- The Accessibility standard now covers the trace view as well as the chart output.
- New tests cover each item, including the failing fixtures: a tampered manifest is
  drift, an ungrounded export is blocked, and HTML data is escaped.
- Small-cell suppression (R3) is deliberately not in this set. The research panel's
  own validation note asks for confirming the binding threshold from primary source
  per report type before it ships, which cannot be done here; it stays v0.2.
