# outcome-receipts

[![CI](https://github.com/ChelseaKR/outcome-receipts/actions/workflows/ci.yml/badge.svg)](https://github.com/ChelseaKR/outcome-receipts/actions/workflows/ci.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-3776AB.svg)](https://www.python.org/downloads/)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-4c1.svg)](LICENSE)

![Outcome Receipts: deterministic SQL to receipt to grounding gate to verified report](docs/assets/social-preview.png)

**New here?** [Run the five-minute demo](docs/TRY_THE_DEMO.md). It uses
synthetic data, makes no network calls, and ends with the grounding gate
refusing an invented number.

Draft funder outcome reports where **every reported figure is a receipt**. The
tool reads a nonprofit's own service data, computes each required figure with a
deterministic query, and attaches to that figure a receipt: the exact query, the
count of rows it drew from, a content hash of that data slice, and a timestamp.
It then drafts a narrative around the receipted figures and runs fail-closed
grounding gates before and after suppression. Export is refused if any number in
the drafted narrative, or in a chart, comparison, or reconciliation claim, does
not trace to a receipt.

The gate reads those narrative and structured claims. It does not read every
numeral in an exported file: the receipts section, the provenance block, and the
trace page also print timestamps, row counts, slice hashes, and the text of each
query, and those are receipt metadata rather than reported figures. Running the
gate over a whole exported `report.md` reports them as unbound, which is the
scope working as specified and not a gate failure.

> **Status: Beta.** This tree declares `0.2.1`, and `0.2.1` is not published
> yet: its tag and its CHANGELOG section exist, and the newest release anyone
> can obtain is `v0.2.0` (`v0.1.0` was the first). What remains is the
> maintainer's alone and is recorded in
> [docs/RELEASING.md](docs/RELEASING.md). The default path is
> deterministic, offline, and tested end to end. The release includes the completed privacy,
> verification, mapping, localization, multi-template, reconciliation, and
> optional Bedrock-drafting roadmap work. The v1 implementation package adds
> container self-hosting, stable report and artifact contracts, and six bounded
> evidence workflows; the v1 tag remains gated on real-organization,
> cross-release, and manual assistive-technology evidence. Bedrock is off by
> default and requires two explicit opt-ins. A
> committed eval ([eval/report.md](eval/report.md)) scores the grounding gate.
> See [CHANGELOG.md](CHANGELOG.md) and
> [SECURITY.md](SECURITY.md#supported-versions).
>
> *Last verified: 2026-09-07 · Recheck cadence: quarterly*

**Start here:** [run the five-minute synthetic demo](docs/TRY_THE_DEMO.md),
[inspect the current evaluation](eval/report.md), or
[bring an anonymized schema-mapping question](https://github.com/ChelseaKR/outcome-receipts/issues/new?template=schema-mapping.yml).

## Quickstart

Prerequisites: Python 3.12+, [uv](https://docs.astral.sh/uv/), GNU Make. This
runs on synthetic data and makes no network calls:

```sh
git clone https://github.com/ChelseaKR/outcome-receipts.git
cd outcome-receipts
make install
.venv/bin/receipts run \
  --config examples/housing-demo/report.toml \
  --out out/demo \
  --approved-by "Demo reviewer"
```

A successful run prints `grounding gate: PASS` and writes the approved report,
its receipts manifest, and a funder-facing trace view under `out/demo/`. The
[five-minute demo walkthrough](docs/TRY_THE_DEMO.md) continues from here —
verifying the receipts and watching the gate fail closed on an invented number —
and [Usage](#usage) covers the full CLI.

## Try it, review it, or contribute

- **Try it:** complete the synthetic demo and
  [report where it passed or stopped](https://github.com/ChelseaKR/outcome-receipts/issues/new?template=demo-run.yml).
- **Review it:** inspect the trace view, suppression behavior, and verification
  command, then ask a
  [question in Discussions](https://github.com/ChelseaKR/outcome-receipts/discussions).
- **Contribute:** choose a
  [bounded open issue](https://github.com/ChelseaKR/outcome-receipts/issues?q=is%3Aissue+is%3Aopen+label%3A%22help+wanted%22)
  or follow [CONTRIBUTING.md](CONTRIBUTING.md). Documentation, accessibility
  review, and practitioner feedback are useful contributions.

## The problem

Funders are starting to reject reports that are "substantially AI-developed,"
because a language model that writes plausible outcome numbers is a liability, not
a help. The fix is not to ban the model; it is to make the numbers come from the
data and prove it. The verify-or-flag idea is published, and one commercial tool
markets deterministic record-cited reporting. The contribution here is the open,
offline chain — compute with a receipt, draft, fail-closed grounding gate, export
with a receipts manifest — plus a fail-closed review queue for mapping explicit
requirements onto schema-variant exports, and a privacy posture (aggregate,
small-cell-aware) a human-services org can defend.

## How it works

```text
compute → draft → ground → suppress → re-draft/re-ground → approve → export
```

1. **Compute with receipts.** Author-declared data checks run first. Service data
   is then loaded into an in-memory SQLite database and every metric is computed
   by SQL. Each figure carries the query, row count, slice hash, value, definition,
   and timestamp that produced it.
2. **Draft and ground the raw result.** The deterministic drafter fills
   `{metric_id}` placeholders. If the optional Bedrock drafter is enabled, it may
   rewrite the prose but receives no source rows, identifiers, SQL, hashes, or
   paths. Every numeric span must match a receipted display exactly.
3. **Apply the privacy boundary.** Counts from 1 through 10 are suppressed under
   the CMS-modeled default. Complementary, delta, and percentage controls prevent
   straightforward arithmetic recovery; true zeros remain visible. Every
   publishable surface is rebuilt from the redacted figures.
4. **Ground again and approve.** The redacted narrative, charts, comparison, and
   reconciliation views pass the same fail-closed gate. A named human then signs
   off on the final artifact.
5. **Export and seal.** The report, receipts manifest, trace view, charts, bundle
   manifest, and hash-chained ledger entry are written. Optional keyed signing
   seals the bundle; verification commands detect later drift or tampering.

The load-bearing invariant is unchanged: **numbers never come from a model.** A
model may write prose only when explicitly enabled, and any numeric invention or
alteration blocks export.

## Usage

Prerequisites: Python 3.12, [uv](https://docs.astral.sh/uv/), GNU Make, and a
clone of this repository. Docker with a running daemon is also required for the
full contributor verification gate and container path, but not for ordinary
Python CLI use. Install the locked development environment and activate it:

```sh
make install
source .venv/bin/activate
```

`make install` creates `.venv`, installs the locked Node/browser dependencies,
and installs the checksum-verified security scanners consumed by `make verify`.
It does not modify the parent shell's `PATH`; you can use
`.venv/bin/receipts` instead of activating it. `make install-smoke` runs the
same install and then asserts that the complete verification toolchain exists.

Run the bundled demo:

```sh
receipts run --config examples/housing-demo/report.toml --out out --approved-by "A. Reviewer"
```

Or run the same deterministic demo in the locked-down container:

```sh
make container-demo
```

See [container self-hosting](docs/SELF-HOSTING.md) for an organization-owned
spec and the mount, identity, and backup boundaries.

```text
loaded examples/housing-demo/services.csv: 12 rows, 5 columns, digest b8b5e05adefaa26f
figures computed: 4
chart and comparison numbers: 0 (bound 0, unbound 0)
numbers in 'report' narrative: 1 (bound 1, unbound 0)
suppression policy: applied (threshold 11; hidden 3)

grounding gate: PASS
  approved: A. Reviewer
  report:   out/report.md
  receipts: out/receipts.json
  trace:    out/trace.html
  bundle:   out/bundle.json (digests-only)
  ledger:   export-ledger.jsonl (entry 0, hash …)
```

It writes `out/report.md` (the narrative, provenance, and receipts appendix),
`out/receipts.json` (machine-readable receipts and provenance), `out/trace.html`
(a funder-facing trace view), and `out/bundle.json` (digests for the complete
export). Runs also append to `export-ledger.jsonl` by default. Specs with charts
add accessible SVG files under `out/charts/`.

A spec may also bind the funder's requirement document. Then the export must
account for every requirement in it — answered by a metric, withheld because
small-cell suppression hid the cell, or declared unanswerable with a blocker
`receipts map` actually reproduces and a reason a person wrote — or it names the
requirement, writes nothing, and exits 4. See
[Proving the report answered the requirement set](#proving-the-report-answered-the-requirement-set).

An export also needs a named human sign-off. `--approved-by NAME` records the
approver non-interactively; without it, an interactive run prompts you to type
your name after the grounding gate passes, and a non-interactive run aborts with
exit code 3 and writes nothing. The approver and the approval time are recorded
in the provenance statement of the report and in the receipts manifest
(`provenance.approved_by`, `provenance.approved_at`; `approved_by` is `null`
when nothing was approved, which no export should ever carry).

#### Requiring more than one signature

Boards and contracts often require two people, a program lead and a finance
lead. A spec can say so, and then the requirement travels with the report
definition rather than with the flag whoever ran the export happened to type:

```toml
[approval]
required = ["program", "finance"]
```

```
receipts run --config report.toml --out out \
  --approve program:"A. Lee" --approve finance:"B. Cruz"
```

A run missing a required role writes nothing and exits 3 naming the role. The
same person cannot fill two roles; the comparison folds case and internal
whitespace, so `A. Lee` and `a.  lee` are one person. `--approved-by` is refused
against a role policy, because a policy a different flag can satisfy is not a
policy. An interactive run prompts once per unfilled role.

Each approval is recorded in the manifest under `provenance.approvals` with its
role, approver and timestamp, and `provenance.approved_by` names every approver
so a reader that only knows that field still reads a complete answer.
`receipts verify --bundle` re-reads the policy from the spec, so a bundle stops
verifying if the policy later gains a role or an approval is edited out of the
manifest. `restate`, `contract-check` and `equity-review` honour the same
policy. A spec with no `[approval]` section behaves exactly as it did before.

### Minimal report specification

A report spec identifies the CSV, narrative template, and deterministic query for
each placeholder. Paths resolve relative to the TOML file.

```toml
schema_version = "1.0"

[data]
path = "services.csv"

[report]
title = "Housing outcome report"
template = "We served {clients_served} clients."

[metrics.clients_served]
description = "Unduplicated clients served"
definition = "Distinct clients with an enrollment in the reporting export."
kind = "output"
unit = "count"
value_sql = "SELECT COUNT(DISTINCT client_id) FROM data"
slice_sql = "SELECT client_id FROM data"
```

See [examples/housing-demo/report.toml](examples/housing-demo/report.toml) for a
complete spec and `receipts init --data services.csv --out report.toml` for a
fail-loud starter containing the source-column inventory. The public spec and
manifest compatibility rules are in
[Specification and manifest stability](docs/SPEC-STABILITY.md).

### Privacy defaults

Exports are structurally aggregate-only: source client rows never enter a report
renderer. The default suppression policy is modeled on CMS guidance: count cells
from 1 through 10 are redacted, true zeros are preserved, and complementary
suppression closes arithmetic recovery paths through totals, deltas, and
percentages. HUD requires anonymous aggregate publication but does not prescribe
this numeric floor, so the policy governing a particular report remains the
operator's responsibility. See the [data card](docs/cards/data-card-reporting.md),
the [DPIA findings](docs/RESPONSIBLE-TECH-AUDITS.md), and the historic suppression
ADRs in [docs/decisions](docs/decisions/). The default is calibrated against
real, non-synthetic data: running the engine over HUD's own 2024 CoC
Point-in-Time subpopulation counts is
[findings, gated by a recomputation test](docs/audits/hud-coc-suppression-calibration-2026-08-21.md).

A withheld cell is never a zero. In `receipts.json` its receipt carries
`suppressed: true` and `null` for `value`, `row_count`, `slice_hash`, and
`column_names`; a figure that is genuinely zero carries `suppressed: false` and a
real `0`; a figure that does not exist has no receipt at all. Three states, three
distinguishable renderings, so a consumer reading the manifest cannot mistake "we
cannot report this figure" for "we served nobody". The report appendix and the
trace view show `[SUPPRESSED]` in place of the row count and slice hash for the
same reason. See
[ADR 0009](docs/decisions/0009-withheld-cells-are-null-not-zero.md) for the
reasoning and
[Specification and manifest stability](docs/SPEC-STABILITY.md) for the manifest
schema `2.0` change and the field mapping from `1.0`.

Check a narrative against the receipts at any time:

```sh
receipts audit --config examples/housing-demo/report.toml --narrative some-draft.md
```

`audit` grounds against the figures the report may actually **publish** — the set
`run` exports, after suppression — not against the raw computed figures. So it
reports two distinct failures, and exits non-zero on either:

* a number that no figure backs (unbound); and
* a number that is the withheld value of a suppressed cell. That number does
  trace to a real receipt, which is exactly why grounding against the raw figures
  used to pass it. Writing it into a report publishes a protected count, so
  `audit` names the metric it discloses rather than calling it unbound.

A sentence carrying no numeral is invisible to all of that, so `audit` and `run`
also check the narrative's **comparative claims** against the directions the
comparison actually computed. "Placements rose" binds only when some declared
comparison row's own `direction` is an increase; a claim every row contradicts is
refused and named beside what the receipts say; a claim that agrees only with a row
suppression withheld is reported as a disclosure, because writing it publishes a
direction the comparison table itself redacts. Four families are detected and can
never bind, for the reason a written-out numeral never binds: an evaluative word
("improved") needs a metric polarity no spec declares, a magnitude word ("doubled")
needs a ratio nothing here computes, a quantifier ("most") needs a proportion of a
total no figure states, and a superlative ("highest") needs a ranking the tool does
not model. See
[ADR 0012](docs/decisions/0012-comparative-claims-bind-to-receipted-directions.md),
which also records what it deliberately leaves open.

`--explain` says *why* each of those numbers missed: which receipted displays are
nearest and by how much, whether the miss is a rounding, a magnitude slip, a
percentage written as a count, or the thousands/decimal ambiguity
[ADR 0011](docs/decisions/0011-canonicalization-preserves-magnitude.md)
deliberately refuses to resolve. It is advice; the verdict and the exit code are
the same with and without it, and `run --explain` likewise explains a refusal
without softening it.

`--fixes-out` writes that diagnosis as a reviewable JSON plan, and
`--apply-fixes` applies a plan you have read, to a new file:

```sh
receipts audit --config report.toml --narrative draft.md --fixes-out fixes.json
receipts audit --config report.toml --narrative draft.md \
  --apply-fixes fixes.json --fixed-out draft.fixed.md
```

The applier substitutes only exact receipted displays, re-checked against the
figure set at the moment it runs, and then re-runs the gate over the bytes it
wrote. It refuses the plan whole — never in part — if the narrative has changed
since the plan was built, if a replacement is not the current display of a
publishable figure, or if a replacement would state a suppressed cell. A span two
displays are equally near gets no fix at all: nothing in the text says which, so
nothing is chosen for you.

`run` refuses to export in either case.

### Templates, charts, comparison, and reconciliation

A report type is defined entirely by its TOML spec, so adding a report shape means
adding a spec. Two more ship alongside the housing demo: a grant report and a
board report.

```sh
receipts run --config examples/grant-report/report.toml --out out/grant --approved-by "A. Reviewer"
receipts run --config examples/board-report/report.toml --out out/board --approved-by "A. Reviewer"
```

The same receipted figure set can render into several `[[report.templates]]`
formats for different funders. Optional charts, comparisons, and board
reconciliations are held to the same gate as every narrative:

* **Charts.** A `[[charts]]` entry names the figures it draws. The chart's bars or
  points are those figures' values, so a chart has no data of its own; it is a
  rendering of numbers that already carry receipts. Each chart is written as a
  standalone SVG and paired with an accessible data table that carries the same
  numbers as text, so a chart is readable without the image and every number in it
  traces to a receipt. The SVG is built with the standard library, so no
  dependency is added. A withheld figure has no value to draw: its bar becomes a
  hatched, dashed full-height slot rather than a bar of height zero, a line chart
  breaks rather than interpolating through it, and it takes no part in the axis
  scale. A bar height is a claim, and the chart does not make one the text
  refuses to make. See
  [ADR 0010](docs/decisions/0010-withheld-cells-are-drawn-as-an-absence.md).
* **Period comparison.** A `[comparison]` section runs one set of metrics across
  two periods (for example two quarters) and reports the change. The two period
  values and the change are each a figure with a receipt; the change is computed
  by a single SQL query that subtracts one period from the other, not by
  arithmetic on the page. Direction is reported as a word, so no ungrounded number
  is shown.
* **Board reconciliation.** A `[reconciliation]` section pairs receipted outcome
  figures with receipted financial lines over the same periods, including a
  grounded change log. No displayed ratio or delta is computed only on the page.
* **Multi-funder output.** Each `[[report.templates]]` entry gets its own output
  directory, report, manifest, trace, bundle, and ledger entry while reusing the
  same byte-identical figure set.

`receipts run` grounds all narrative and structured claims before and after
suppression and refuses to export if any number is unbound.

Score the gate on the committed fixtures:

```sh
receipts eval --config examples/housing-demo/report.toml
```

The committed result is in [eval/report.md](eval/report.md). It scores the
**exported** narrative — drafted and grounded after suppression, so it measures
the artifact the pipeline actually writes rather than a pre-suppression draft it
would never produce. That narrative grounds 100% of its numbers, so the gate
passes. Because suppressed cells render as `[SUPPRESSED]` and carry no number,
the denominator is the count of numbers that survive suppression, which the
report states. That the gate catches an injected unverifiable number is shown by
the merge-blocking test `tests/test_grounding_gate.py`.

The authoritative product roadmap has no remaining repository-side
implementation items. Evidence gates for a v1 tag and the implemented bounded
applications are in [the roadmap](docs/ROADMAP.md) and
[evidence use cases](docs/NOVEL-USE-CASES.md).

### English and Spanish report output

Public report copy, approval language, reconciliation labels, chart alternative
text, receipt metadata labels, and trace-view content are available in English
and Spanish. Figures, SQL, hashes, and source data do not change across locales:
a figure display is written the same way in every locale, with `,` grouping
thousands and `.` marking the decimal, so a Spanish-reading funder sees `1,234`
for one thousand two hundred and thirty-four.

The grounding gate reads prose in either convention, and its canonicalization
preserves magnitude. `12.345,67` and `12,345.67` both bind a display of
`$12,345.67`; `3,5` binds `3.5`; NBSP-grouped `1 234` binds `1,234`. One shape
cannot be resolved from the text and is therefore refused rather than guessed
at: a single separator with 1–3 digits before it and exactly 3 after (`1.234`)
is a thousands group under one convention and a decimal point under the other,
and the two readings are a factor of a thousand apart. A span in that shape
binds only a display written the same way, so a narrative cannot state a number
1,000x its receipt and bind. See
[ADR 0011](docs/decisions/0011-canonicalization-preserves-magnitude.md).

```sh
receipts run --config examples/housing-demo/report.toml --out out/es \
  --locale es --approved-by "A. Reviewer"
```

The CLI's operational messages remain English. See [docs/I18N.md](docs/I18N.md).

### Optional Claude-on-Bedrock drafting

The deterministic drafter remains the zero-cloud default. Bedrock drafting needs
the optional dependency, an enabled `[report.drafting]` policy with a model ID,
and `--allow-cloud-drafting` on every run:

```sh
uv sync --locked --python 3.12 --group dev --extra bedrock
receipts run --config report.toml --out out --allow-cloud-drafting \
  --approved-by "A. Reviewer"
```

The first model request may contain small aggregate displays even though the
published artifact is subsequently suppressed. Organizations must explicitly
authorize that transfer and configure their Bedrock logging and retention policy.
See [docs/drafting.md](docs/drafting.md), the
[model card](docs/cards/model-card.md), and the
[data card](docs/cards/data-card-reporting.md).

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
  that each figure was computed by a deterministic query, that no figure was
  written by a model, and that the grounding gate bound every number in the
  report's claims before export.
  The same attestation goes into the manifest as a machine-readable record, which
  separately names the deterministic or Bedrock narrative drafter used.

Re-derive a committed report to confirm it still holds:

```sh
receipts run --config examples/grant-report/report.toml --out out/grant --approved-by "A. Reviewer"
receipts verify --config examples/grant-report/report.toml --receipts out/grant/receipts.json
```

`receipts verify` recomputes every figure from the spec and the cited data and
checks each value, slice hash, row count, and query against the manifest. A
mismatch is drift (the data changed, the spec changed, or the manifest was edited);
verify reports each drifted receipt and exits non-zero, so a silent divergence
cannot pass.

The same check is packaged as a reusable composite GitHub Action so a downstream
repo can gate CI on receipt drift with a commit-pinned action ref. See
[docs/ci-action.md](docs/ci-action.md) for the workflow snippet and supply-chain
pinning guidance.

### Command guide

| Command | Purpose |
| --- | --- |
| `receipts init` | Inspect a CSV header and create an empty, fail-loud starter spec. |
| `receipts map` | Map explicit funder requirements to candidate SQL and emit a mandatory human review queue; see [metric mapping](docs/metric-mapping.md). |
| `receipts run` | Compute, ground, suppress, approve, export, seal, and append to the ledger. |
| `receipts audit` | Check an existing narrative against the publishable figures: report spans that bind to no receipt, and spans that state a suppressed cell. `--explain` diagnoses each miss; `--fixes-out` / `--apply-fixes` round-trip a reviewable fix plan. |
| `receipts mcp` | Serve `audit`, `verify`, `trace` and the publishable figure list to a drafting tool over stdio, read-only. No export tool, no approval tool, no network, no new dependency; a withheld cell answers as the redaction marker. See [drafting](docs/drafting.md). |
| `receipts eval` | Score grounding behavior on a configured fixture. |
| `receipts verify` | Recompute receipt values and hashes, or verify an entire exported bundle with `--bundle`. |
| `receipts verify-bundle` | Recompute `bundle.json` member digests and an optional keyed signature. |
| `receipts verify-ledger` | Re-hash the append-only export ledger and detect an entry edited, inserted, reordered, or removed mid-chain. It cannot detect entries deleted from the end, a rewrite that recomputes every hash, or an export never appended; its PASS output lists exactly that. |
| `receipts diff` | Explain added, removed, or changed figures between two manifests. |
| `receipts restate` | Link a verified prior bundle to a receipted restatement and named approval. |
| `receipts migrate-check` | Compare reviewed metrics across two schema-variant exports. Each metric is `equivalent`, `changed`, or `indeterminate` (withheld by suppression on one side, so no comparison is possible). |
| `receipts requirements-diff` | Classify funder requirement changes by stable ID and text digest. |
| `receipts contract-check` | Package receipted milestone, threshold, and financial evidence without making a legal determination. |
| `receipts suppress-preview` | Preview what one or more suppression policies would withhold from a report, before anything is exported. Writes nothing. The shareable output never prints a withheld value; `--local` opts into them. |
| `receipts rollup` | Compose an aggregate count from verified, unsuppressed partner bundles. |
| `receipts equity-review` | Package allowlisted subgroup receipts after whole-report suppression, with required policy and consent context. |
| `receipts verify-workflow` | Validate an evidence artifact's schema version, typed relationship, digests, aggregate-only boundary, and composed-receipt lineage. |
| `receipts portfolio` | Export several report specs as one batch through the ordinary gate, into one directory and one shared ledger. The first spec that fails stops the batch and no portfolio record is written. |
| `receipts portfolio-verify` | Re-verify every bundle in a portfolio from its own spec and render `index.html`: per report the gate result, who signed off, the bundle digest and its ledger entry, plus the figures more than one report states. |
| `receipts cards` | Generate or drift-check the model and data cards. |

Run `receipts <command> --help` for the complete option reference. Every command
supports `--json` before or after the subcommand.

The six evidence workflows are documented in
[implemented use cases](docs/NOVEL-USE-CASES.md). Their artifacts share the
versioned [workflow artifact schema](docs/schema/workflow-artifact.schema.json).
Rollup and equity review are experimental for real organizational data until
their documented privacy and user-validation gates are complete.

### CLI output and exit codes

Every command prints human-readable lines by default. Pass `--json` to any command
to get a single machine-readable JSON object on stdout instead, with the prose
suppressed. The JSON is purely presentational; it never changes the exit code.

```sh
receipts run --config examples/housing-demo/report.toml --out out --reproducible --approved-by CI --json
receipts verify --config examples/grant-report/report.toml --receipts out/grant/receipts.json --json
receipts map --data examples/housing-demo/services.csv --requirements examples/mapping/requirements.json --out mapping-review.json --json
```

The `run` object reports the gate result, figure and narrative tallies, any
unbound numbers, the paths it wrote, the export-ledger entry it appended, and the
recorded approval. Under `--json` there is no interactive sign-off prompt, so
`run` needs `--approved-by`; without it the export aborts with exit code 3 and a
`null` approval in the payload. The `audit`, `verify`, `verify-bundle`,
`verify-ledger`, `eval`, `diff`, and `cards` objects report their own results and
details; `map` reports pending or blocked candidates without executing them;
`init` carries the scaffolded spec and where it was written.

`verify` reports its counts twice over, because two different things are checked
and only one of them is a receipt. `receipts_checked`, `receipts_ok` and
`receipts_drift` count receipts re-derived from the data. `n_ok` and `drift` are
totals that also include the manifest's own descriptors — its declared
`schema_version` and its `hash` block — which are compared against a constant and
re-derived from nothing. Each entry in `checks` carries a `kind` of `receipt` or
`manifest` saying which it is, so a script need not guess from the `metric_id`.
`verify-workflow` reports every artifact-contract check, and each workflow
command returns the artifact it wrote. The `--json` flag is accepted before or
after the subcommand, so `receipts --json run ...` and `receipts run ... --json`
are equivalent.

The exit code is the contract a script should read. It is stable across the human
and JSON forms.

| Code | Meaning |
| ---- | ------- |
| 0 | Success. The command ran and the grounding gate, where one applies, passed. |
| 1 | A check failed closed: mapping was blocked, grounding/eval failed, receipts or a bundle drifted, a ledger chain broke, or generated cards were stale. |
| 2 | The grounding gate refused to export. `run` found an unbound number and wrote nothing. |
| 3 | The export was not approved. The grounding gate passed but no named human signed off (no `--approved-by`, and no interactive sign-off), or the sign-off did not satisfy the spec's `[approval]` policy, so `run` wrote nothing. |
| 4 | The export did not answer its bound requirement set. A requirement was neither answered by a metric, withheld as a suppressed cell, nor declared unanswerable with a blocker `map` reproduces and a reason a person wrote — so `run` named it and wrote nothing. Only a spec with a `[requirements]` binding can return this. |

### Publishing more than one report

An organization rarely publishes one report. It publishes a grant report, a
board report, and a template per funder, each from its own spec. The receipts
prove every figure in each one and prove nothing about the set, and an auditor
holding five output directories has no page saying which reports exist, which
still verify, and whether two of them state the same metric differently.

```sh
receipts portfolio \
  --specs examples/grant-report/report.toml examples/board-report/report.toml \
  --out out/portfolio --approved-by "A. Reviewer"
receipts portfolio-verify --dir out/portfolio
```

The batch takes no shortcut: each spec is exported by `run` itself, so the
grounding gate, the requirement-coverage refusal, suppression and the human
sign-off apply exactly as they do to a single report, and a spec's `[approval]`
policy applies too. Every export appends to one shared ledger. The first spec
that fails stops the batch, names itself, and returns its own exit code, and no
portfolio record is written. Specs run in path order, so the batch is the same
whichever order the arguments arrived in.

`portfolio-verify` re-verifies every bundle from its own spec and writes
`index.html`: per report the gate result, who signed off, the bundle signature
and digest, and the ledger entry, followed by the figures more than one report
states. That table computes nothing. It compares what each report already
published, and it keeps four outcomes apart:

| Outcome | What it means |
| --- | --- |
| Same definition, same value | The reports agree. |
| Same definition, different values | The reports contradict each other. This is the only one of the four that says so. |
| Definitions differ | The reports count different things, so their values are not comparable at all and no comparison was made. |
| Withheld in at least one report | Small-cell suppression withheld the cell. An absence, never a disagreement and never a zero. |

The index is one static, script-free HTML file in EN or ES, held to the same
WCAG 2.2 AA gate as the trace view.

### Proving the report answered the requirement set

The project proves every published number traces to a receipt. That is one half
of the claim. The other is that every *required* number was published, and it is
the half an auditor checks first: a spec that simply omitted a required metric
used to run, ground, be approved, and export a report that was fully receipted
and silently incomplete.

Bind the spec to the requirement document `receipts map` already reads, and name
the requirement each metric answers:

```toml
[requirements]
path = "requirements.json"

[[requirements.unanswerable]]
requirement_id = "R-4"
blocker = "no source column matches logical field 'return_within_180_days'"
reason = "The HMIS export carries no re-entry field. Returns are tracked in the continuum's separate quarterly reconciliation."

[metrics.clients_served]
requirement_id = "R-1"
# ...
```

Every requirement then lands in one of four states, and only three of them may
be exported:

| status | meaning |
| ------ | ------- |
| `answered` | a metric names it and its figure was published with a receipt |
| `withheld` | a metric names it, the figure exists, and suppression withheld the cell — **answered**, and it reads as unanswered nowhere |
| `unanswerable` | no metric answers it, and the spec carries both a blocker and a reason |
| `unanswered` | anything else: the export is refused, exit 4, nothing written |

An `unanswerable` declaration needs **both** halves and neither is enough alone.
A blocker without a reason is a tool's excuse; a reason without a blocker is
unfalsifiable. So the declared `blocker` is re-derived at export by running the
mapper over the same data and the same requirement document, and the declaration
is refused unless the mapper produces that exact string. A requirement that maps
cleanly cannot be declared unanswerable at all.

The coverage table renders in the report appendix in both locales, the
requirement document's sha256 rides in `receipts.json`, and `verify --bundle`
re-derives both — so editing the requirement document after export fails naming
the digest, and doctoring the coverage record fails as a mismatch. A spec with no
`[requirements]` binding is unchanged in every byte and its manifest carries no
coverage key at all; `verify --bundle` says `not checked`, not `ok`.

```sh
receipts run --config examples/requirement-coverage/report.toml --out out --approved-by "Program director"
```

See [ADR 0013](docs/decisions/0013-requirement-coverage-is-proven-at-export.md)
for the reasoning and for the one question it deliberately leaves to the owner.

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
| Responsible-Tech Framework | Applies — dated ethics, bias, DPIA, transparency, accessibility, security, AI-risk, and residual-risk artifacts |
| Code Quality | Applies — Python 3.12, current canonical ruff/mypy floors, strict typing, 90% branch coverage and 95% on integrity-critical modules |
| Security & Supply-Chain | Applies — Semgrep, CodeQL, dependency and secret scans, Scorecard, SHA-pinned Actions, CycloneDX 1.7, Sigstore-backed attestations, and OIDC publishing |
| CI/CD | Applies — `make verify` is the full local gate and CI invokes the same targets; main is ruleset-protected and releases run the trusted-main dispatch pipeline |
| Release & Versioning | Applies — SemVer, signed tags verified against committed allowed signers, trusted-main dispatch with checkout-free publication, CHANGELOG, exact-version build, PyPI Trusted Publishing, provenance, SBOM, and published-artifact verification; maintainer procedure in [docs/RELEASING.md](docs/RELEASING.md) |
| Observability | Applies — Tier C local CLI; no service telemetry or SLO surface, with explicit operational and incident runbooks |
| Accessibility | Applies — axe, pa11y, Lighthouse, reflow, and reduced-motion gates cover generated HTML; the ACR records manual VoiceOver/NVDA evidence status |
| Internationalization & Localization | Applies — packaged gettext catalogs with EN/ES key and placeholder parity; operational CLI messages remain English |
| AI Evaluation | Applies to optional Bedrock drafting — 136-case bilingual grounding benchmark, generated cards, red-team and governance artifacts; no judge ships |
| Documentation | Applies — pinned standards, current root docs, canonical ADR log, data/incident/operations artifacts, and conformance checks |
| Quality & Metrics | Applies — Definition of Done, committed eval with Wilson intervals, fail-closed gates, and project metrics ledger |
| Incident Response | Applies — severity/label convention, private disclosure, secret-leak runbook, and committed-postmortem requirement |
| Data Governance | Applies — L3 ephemeral input and L2 aggregate-output cards, retention boundary, lineage, and verified recovery procedure |
| Performance | Applies — Lighthouse performance score and a zero-byte script budget on the generated trace, asserted from the one repository Lighthouse config, plus a committed `perf/baseline.json` and a direction-aware 10% regression gate (`make perf`); k6 latency is N/A with reason, there being no hosted route, and the reason is recorded in [perf/README.md](perf/README.md) rather than skipped |
| AI-Development Measurement | Applies — declared in the [ROADMAP](docs/ROADMAP.md) metrics ledger, with the delivery and quality-debt metrics recorded as dated BASELINE rows that each name the date their graduation decision is due; diagnostic counters are tracked nowhere and gate nothing. The portfolio-level weekly rollup and the quarterly seven-capability self-assessment are named as outstanding in the same section rather than claimed |

## License

Apache-2.0.

## Project discussion

Use [GitHub Discussions](https://github.com/ChelseaKR/outcome-receipts/discussions)
for setup and design questions. Use the structured issue forms to
[report a demo run](https://github.com/ChelseaKR/outcome-receipts/issues/new?template=demo-run.yml)
or [describe a mapping question](https://github.com/ChelseaKR/outcome-receipts/issues/new?template=schema-mapping.yml).
Never post client-level rows, identifiers, credentials, or real service exports.

## Support

This is independent work, published so it can be read and checked rather than taken on
trust. If your organization wants help making its outcome reporting traceable,
[get in touch](https://chelseakr.com/contact).
