# outcome-receipts

Draft funder outcome reports where **every number is a receipt**. The tool reads
a nonprofit's own service data, computes each required figure with a deterministic
query, and attaches to that figure a receipt: the exact query, the count of rows
it drew from, a content hash of that data slice, and a timestamp. It then drafts
a narrative around the receipted figures and runs a fail-closed grounding gate
that refuses to export if any number in the narrative does not trace to a receipt.

> **Status: v0.1, early but working.** The deterministic path runs end to end and
> is tested: service-data CSV in, receipted figures out, a drafted narrative, and
> a grounding gate that blocks export on any unverifiable number. No language
> model is involved in v0.1. A committed eval ([eval/report.md](eval/report.md))
> scores the gate. Track progress in [docs/ROADMAP.md](docs/ROADMAP.md); the build
> is specified in [CLAUDE.md](CLAUDE.md).

## The problem

Funders are starting to reject reports that are "substantially AI-developed,"
because a language model that writes plausible outcome numbers is a liability, not
a help. The fix is not to ban the model; it is to make the numbers come from the
data and prove it. The verify-or-flag idea is published, and one commercial tool
markets deterministic record-cited reporting. The contribution here is the open,
offline chain — compute with a receipt, draft, fail-closed grounding gate, export
with a receipts manifest — plus the metric-mapping over messy real exports, and a
privacy posture (aggregate, small-cell-aware) a human-services org can defend.

## How it works

1. **Compute.** Service data is loaded into an in-memory SQLite database, and each
   metric is run as a SQL query. The value comes from the query, never from
   generated text. Every figure carries a receipt.
2. **Draft.** A report template's `{metric_id}` placeholders are filled with the
   figures' display strings. v0.1's drafter writes no number of its own.
3. **Ground.** The grounding gate finds every number in the narrative and binds
   each to a figure whose display matches. A number that matches no figure is
   unbound, and an unbound number blocks export. The gate is mechanical: it checks
   that each number traces to a receipt, it does not ask a model whether the text
   "looks faithful."
4. **Export.** When the gate passes, the report and a JSON receipts manifest are
   written, so a funder or auditor can trace every figure to the query and data
   slice that produced it.

The load-bearing invariant: **numbers never come from a model.** In a later
version a model drafts the prose, but the grounding gate is the enforcement that
every number in it still came from a receipt.

## Usage

Install (Python 3.11+):

```sh
make install
```

Run the bundled demo:

```sh
receipts run --config examples/housing-demo/report.toml --out out
```

```text
figures computed: 4
numbers in narrative: 4 (bound 4, unbound 0)
chart and comparison numbers: 0 (bound 0, unbound 0)

grounding gate: PASS
  report:   out/report.md
  receipts: out/receipts.json
  trace:    out/trace.html
```

It writes `out/report.md` (the narrative, a provenance statement, and a receipts
manifest), `out/receipts.json` (the machine-readable receipts and provenance
record), and `out/trace.html` (a funder-facing view of the receipts, described
below). Check a narrative against the receipts at any time:

```sh
receipts audit --config examples/housing-demo/report.toml --narrative some-draft.md
```

If the narrative contains a number that no figure backs, `audit` reports it and
exits non-zero, and `run` refuses to export.

### Report templates, charts, and a period comparison

A report type is defined entirely by its TOML spec, so adding a report shape means
adding a spec. Two more ship alongside the housing demo: a grant report and a
board report.

```sh
receipts run --config examples/grant-report/report.toml --out out/grant
receipts run --config examples/board-report/report.toml --out out/board
```

Each can add two optional sections, and the numbers in both are held to the same
gate as the narrative:

* **Charts.** A `[[charts]]` entry names the figures it draws. The chart's bars or
  points are those figures' values, so a chart has no data of its own; it is a
  rendering of numbers that already carry receipts. Each chart is written as a
  standalone SVG and paired with an accessible data table that carries the same
  numbers as text, so a chart is readable without the image and every number in it
  traces to a receipt. The SVG is built with the standard library, so no
  dependency is added.
* **Period comparison.** A `[comparison]` section runs one set of metrics across
  two periods (for example two quarters) and reports the change. The two period
  values and the change are each a figure with a receipt; the change is computed
  by a single SQL query that subtracts one period from the other, not by
  arithmetic on the page. Direction is reported as a word, so no ungrounded number
  is shown.

`receipts run` grounds the narrative and the chart-and-comparison numbers, and
refuses to export if any number in any of them is unbound.

Score the gate on the committed fixtures:

```sh
receipts eval --config examples/housing-demo/report.toml
```

The committed result is in [eval/report.md](eval/report.md): the drafted
narrative grounds 100% of its numbers, so the gate passes. That the gate catches
an injected unverifiable number is shown by the merge-blocking test
`tests/test_grounding_gate.py`.

### The trace view, the provenance statement, and re-derivation

Three things make the proof legible and checkable for the people who receive a
report, none of which puts a model near a number.

* **A definition on every metric.** A figure is only as fair as its definition, so
  a metric can carry a plain-language `definition` (what window, who counts, the
  deduplication rule). It rides in the receipt and renders next to the figure, so a
  reviewer can see and contest the choice a query encodes without reading SQL.
* **A trace view** (`out/trace.html`). The receipts manifest is JSON, which a grant
  manager or program officer cannot read. The trace view renders the same receipts
  as one self-contained, accessible HTML page: a summary table of every figure with
  its value and definition, then the receipt behind each (the query, the row count,
  the slice hash, the timestamp). It opens offline and needs no SQL or Python.
* **A provenance statement.** Every export embeds a short, standard block stating
  that each number was computed by a deterministic query, that no figure was
  written by a model, and that the grounding gate bound every number before export.
  The same attestation goes into the manifest as a machine-readable record.

Re-derive a committed report to confirm it still holds:

```sh
receipts run --config examples/grant-report/report.toml --out out/grant
receipts verify --config examples/grant-report/report.toml --receipts out/grant/receipts.json
```

`receipts verify` recomputes every figure from the spec and the cited data and
checks each value, slice hash, row count, and query against the manifest. A
mismatch is drift (the data changed, the spec changed, or the manifest was edited);
verify reports each drifted receipt and exits non-zero, so a silent divergence
cannot pass.

### CLI output and exit codes

Every command prints human-readable lines by default. Pass `--json` to any command
to get a single machine-readable JSON object on stdout instead, with the prose
suppressed. The JSON is purely presentational; it never changes the exit code.

```sh
receipts run --config examples/housing-demo/report.toml --out out --reproducible --json
receipts verify --config examples/grant-report/report.toml --receipts out/grant/receipts.json --json
```

The `run` object reports the gate result, the figure and narrative tallies, any
unbound numbers, and the paths it wrote. The `audit`, `verify`, and `eval` objects
report their own pass or fail and the details behind it. The `--json` flag is
accepted before or after the subcommand, so `receipts --json run ...` and
`receipts run ... --json` are equivalent.

The exit code is the contract a script should read. It is stable across the human
and JSON forms.

| Code | Meaning |
| ---- | ------- |
| 0 | Success. The command ran and the grounding gate, where one applies, passed. |
| 1 | A verification or eval check failed closed: `audit` found an unbound number, `verify` found receipt drift, or the `eval` gate did not pass. |
| 2 | The grounding gate refused to export. `run` found an unbound number and wrote nothing. |

## What it does not do

* It does **not let a model invent numbers.** Figures come from queries; the gate
  enforces it.
* It is **not a data warehouse or a BI tool.** It computes the figures a report
  needs and proves them, then gets out of the way.
* It does **not claim a new verification primitive.** The verify-or-flag idea is
  published; the contribution is the open offline chain, the metric-mapping, and
  the privacy posture.

## Standards conformance

This repo holds itself to the portfolio's shared engineering standards. The
project-specific values live in [docs/ROADMAP.md](docs/ROADMAP.md) and
[docs/RESPONSIBLE-TECH-AUDITS.md](docs/RESPONSIBLE-TECH-AUDITS.md).

| Standard | State |
|----------|-------|
| Responsible-Tech Framework | Applies — see docs/RESPONSIBLE-TECH-AUDITS.md |
| Code Quality | Applies — ruff, mypy --strict, pytest, merge-blocking |
| Documentation | Applies |
| Quality & Metrics | Applies — committed eval with Wilson CIs, fail-closed gate |
| AI Evaluation | Applies when the drafting seam lands (v0.3); v0.1 has no model in any path |
| Security & Supply-Chain | Applies — hardening (SBOM, signed releases, pinned actions) lands toward 1.0 |
| CI/CD | Applies — `make verify` mirrors CI |
| Accessibility | Applies to the chart output and the trace view — every chart ships an SVG with `role="img"`, `<title>`, and `<desc>` paired with an equivalent data table, and the trace-view HTML is semantic and high-contrast (one `<h1>`, `lang` set, table headers with `scope`, a `<caption>`); the CLI core stays headless |
| Internationalization | N/A — English-only at v0.1; report copy is externalizable in the spec |
| Observability | N/A — library/CLI, no long-running service |

## For Claude Code

Read [CLAUDE.md](CLAUDE.md) first. It is the source of truth for scope,
conventions, and the build plan, and it states the hard guardrails: numbers never
come from the model, the grounding gate is fail-closed, small-cell suppression is
a privacy invariant, and the honest framing of what is solved art versus the
contribution. Then read [docs/ROADMAP.md](docs/ROADMAP.md) and build phase by
phase.

## License

Apache-2.0.
