# AGENTS.md — outcome-receipts

> Source of truth for project intent, scope, conventions, and the build plan.
> Read it fully before writing any code.

## What this is

`outcome-receipts` drafts a funder outcome report in which **every number is a
receipt**. It connects to a nonprofit's own service data, computes each required
figure with a deterministic query, and attaches to that figure a receipt: the
exact query, the row count, a content hash of the data slice it was computed
from, and a timestamp. A drafting step writes narrative prose around the
receipted figures. A fail-closed grounding gate then strips or flags any number
in the prose that does not trace to a receipt, before a human approves each
figure and exports the report.

The contribution is not a new verification primitive (those are published) and
not a new reporting product (commercial ones exist). It is the open-source,
offline-first chain — compute-with-receipt, draft, fail-closed grounding audit,
human approval, provenance-stamped export — with a privacy posture (small-cell
suppression, aggregate-only output) a human-services org can defend to its
clients and its funder at the same time.

## Why it exists (strategic context — read this, it shapes decisions)

This is a portfolio and contribution project by Chelsea Kelly-Reif. It is the
second pillar of a nonprofit-data pair: `constituent-reconciler` gets messy
intake *into* the system of record; `outcome-receipts` gets verified outcome
numbers *out* of it and into a funder report. Build it so the two read as
siblings: same engineering bar, same fail-closed instinct, same honesty about
what is solved art versus what is the actual contribution.

The research that motivated it found three things. Funders are beginning to
reject reports that are "substantially AI-developed," because an LLM that writes
plausible outcome numbers is a liability, not a help. The per-figure
verify-or-flag idea is already published (Proof-Carrying Numbers, VeriTrail) and
a commercial tool (Sopact) already markets deterministic record-cited reporting,
so **do not claim a new primitive**. The genuinely hard, genuinely unserved part
is metric-mapping over schema-variant exports: turning "unduplicated clients
exiting to permanent housing" into a correct deterministic query over one
specific org's messy HMIS or CSV export. That mapping, plus the receipts and the
fail-closed grounding gate, is where the work is.

Two audiences:

1. **Grant and program staff** at small-to-mid human-services nonprofits who
   assemble outcome reports by hand each cycle, copying numbers between a case
   system, a spreadsheet, and a funder template, and who cannot afford a wrong
   number in front of a funder.
2. **The nonprofit-tech and responsible-AI community** who will judge the repo
   as a work sample and as a reference for "how to put an LLM near reporting
   without letting it invent the figures."

Do not frame this repo anywhere in its docs as a job-search artifact. The README
speaks only to nonprofit practitioners.

## Ground rules for Codex

* **Numbers never come from the model. Ever.** Every figure in a report is
  computed by a deterministic query over the org's data and carries a receipt.
  The LLM drafts prose *around* already-computed, already-receipted figures. A
  number that originates in the model is a defect, and the grounding gate exists
  to catch it. This is the single load-bearing invariant; it is a merge-blocking
  test (`tests/test_grounding_gate.py`).
* **Fail closed, everywhere.** A figure with no receipt, a query that errors, a
  metric the mapper is unsure about, a cell too small to publish safely, a
  consent or suppression rule that is ambiguous: all route to a human or block
  the export. Never silent-pass, never publish an unverifiable number.
* **The grounding gate is the product.** Given a drafted narrative and the set
  of receipts, every numeric span in the narrative must bind to a receipt whose
  value matches. Unbound or mismatched numbers are stripped and surfaced for
  review. A report cannot be exported while any numeric span is unbound.
* **Small-cell suppression is a privacy invariant, not a setting.** Aggregate
  outcome counts below the suppression threshold (default n < 11, the common
  HUD/HMIS floor — confirm the exact rule from primary HUD guidance before
  hard-coding it) are suppressed in every export, and complementary suppression
  is applied so a suppressed cell cannot be recovered by subtraction. This will
  be a merge-blocking test (`tests/test_suppression.py`, planned for v0.2 — not
  yet present in the tree). Do not invent the threshold or the complementary
  rule; cite the source.
* **Aggregate-only by default.** A report is aggregate statistics, not a client
  roster. The export path emits counts, rates, and the narrative; it never emits
  client-level rows. Emitting a client identifier in a report is a defect.
* **Deterministic by default; the LLM is an optional seam.** Metric computation,
  receipt generation, the grounding gate, and suppression all run with zero
  cloud calls. The drafting seam (Codex on Bedrock) writes narrative only, and
  only when enabled. v0.1 ships the entire receipted-figure path with no LLM at
  all, so the differentiator is provable before any model is wired in.
* **Be honest about novelty.** The README says plainly: the verify-or-flag
  primitive is published, deterministic record-cited reporting is sold
  commercially, and the contribution is the open chain plus the metric-mapping
  plus the privacy posture. No "first-ever," no "new primitive."
* **Never invent compliance or statistical-disclosure facts.** Suppression
  thresholds, complementary-suppression rules, and any funder-specific
  definition come from primary sources (HUD HMIS reporting guidance, the
  funder's own data dictionary), read at build time, not from memory. Where a
  rule is ambiguous, implement the more protective interpretation and record the
  question.
* Python 3.12+. Keep the dependency surface small. The metric engine runs on
  the standard library plus a dataframe/SQL layer (DuckDB is the likely choice;
  record the decision in an ADR). `tomllib` for specs, `argparse` for the CLI.
  The LLM client appears only inside the drafting seam, nowhere else. License:
  Apache-2.0, matching the portfolio default.

## Conformance to the portfolio STANDARDS

This repo holds itself to the portfolio's shared engineering standards. Per the
"reference, don't repeat" rule, the rigor is defined once in the STANDARDS set;
this repo records only its own values and findings (in README, `docs/ROADMAP.md`
metrics ledger, and `docs/RESPONSIBLE-TECH-AUDITS.md`). The concrete bars this
repo commits to:

* **Code quality.** `ruff` (full select set: `E,W,F,I,UP,B,SIM,S,C90,RUF`,
  `max-complexity = 10`), `mypy --strict`, `pytest` with branch coverage
  **≥ 90%** (treat the metric engine as a library; correctness is the product),
  all merge-blocking. `uv` with a committed `uv.lock`; `uv sync --frozen` in CI.
  PyPA src layout, `pyproject.toml` as the single config root.
* **AI evaluation.** This is an AI repo: the drafting seam puts a model in the
  path, so the AI-Evaluation standard applies in full. Committed eval on seeded
  synthetic fixtures with planted ground truth. The gated metrics: a
  **fail-closed grounding rate** (zero unbound numeric spans may survive to an
  exported report), a hallucinated-number rate reported with Wilson confidence
  intervals, and judge calibration (Cohen's kappa **≥ 0.60**, recalibrated
  within 30 days) if an LLM judge scores narrative faithfulness. No
  cherry-picking; failures are shown. Model card and data card committed and
  regenerated on release.
* **Security and supply chain.** OWASP ASVS-aligned. SHA-pinned Actions,
  least-privilege `GITHUB_TOKEN` (`contents: read` default), `pip-audit` and
  secret scanning with no `|| true`. SBOM (CycloneDX) and Sigstore-signed,
  SLSA-provenanced releases via OIDC Trusted Publishing as the release path
  lands.
* **CI/CD.** `make verify` reproduces the full AUTO-GATE set byte-for-byte with
  CI. No admin bypass on `main`.
* **Documentation.** README with a Standards Conformance table (every standard
  marked Applies or N/A-with-reason). MADR-format ADRs in `docs/decisions/`.
  Keep a Changelog. `CITATION.cff`, `SECURITY.md`, `CONTRIBUTING.md`.
* **Accessibility.** N/A for the CLI core (headless, no HTML). When the review
  surface gains an HTML view, WCAG 2.2 AA applies to it.
* **Internationalization.** Report output and any reviewer-facing copy are
  externalized; EN and ES at parity for public-facing strings.
* **Responsible tech.** `docs/RESPONSIBLE-TECH-AUDITS.md` carries all six audits
  (ethics, bias, privacy/DPIA, transparency, accessibility, security) as
  committed findings. Privacy gets a DPIA: the tool reads client-level data to
  compute aggregates, so the data-minimization and suppression posture is the
  central finding.

Project-specific values live in `docs/ROADMAP.md` (metrics ledger) and
`docs/RESPONSIBLE-TECH-AUDITS.md`, never restated from the shared standard. When
publishing as a standalone public repo, keep it self-contained: do not add
relative links to the private STANDARDS repo; state the bar inline as above.

## Architecture

```
outcome-receipts/
├── AGENTS.md                      # this file
├── README.md                      # practitioner-facing
├── pyproject.toml                 # PEP 621, console_scripts entry: receipts
├── Makefile                       # install / lint / type / test / eval / verify
├── src/outcome_receipts/          # flat module layout — no sub-packages yet
│   ├── __init__.py                # package entry; the supported surface is the receipts CLI
│   ├── cli.py                     # receipts run | audit | verify | eval
│   ├── config.py                  # report-spec + metric-spec + policy loading from TOML
│   ├── models.py                  # core data types: Receipt, Figure, MetricSpec, Report
│   ├── clock.py                   # time source for receipts (injectable, deterministic in tests)
│   ├── engine.py                  # the deterministic metric engine: run a MetricSpec, emit a Figure + receipt
│   ├── grounding.py               # the fail-closed gate: every numeric span binds to a receipt
│   ├── draft.py                   # the deterministic drafter: template-fill narrative, no LLM
│   ├── comparison.py              # period-over-period comparison, every number SQL-grounded
│   ├── charts.py                  # charts from grounded figures, with an accessible data table
│   ├── provenance.py              # the provenance statement that travels with every export
│   ├── trace.py                   # funder-facing trace view: static, accessible HTML of the receipts
│   ├── verify.py                  # re-derivation check for a committed receipts manifest
│   ├── evaluate.py                # eval scoring: grounding rate, hallucinated-number rate, Wilson CIs, kappa
│   └── report.py                  # rendering for the report, the receipts manifest, and the eval
│   # PLANNED (v0.2, no source file yet): small-cell suppression, data-loading,
│   # and the funder-template mapping/review surface — see the Roadmap below.
├── tests/                         # one module per source module, plus grounded-section tests
│   ├── test_grounding_gate.py     # MERGE-BLOCKING: no unbound number survives the gate
│   └── test_*.py                  # engine, draft, comparison, charts, provenance, trace, verify, eval, config, definition
│   # PLANNED merge-blocking tests (v0.2): test_suppression.py, test_no_model_numbers.py
├── eval/                          # committed eval report (report.md)
├── examples/                      # runnable example configs: board-report, grant-report, housing-demo
├── docs/
│   ├── ROADMAP.md
│   ├── RESEARCH-ROADMAP.md
│   ├── RESPONSIBLE-TECH-AUDITS.md
│   ├── USER-RESEARCH.md
│   └── decisions/                 # MADR ADRs, 0000 meta-ADR first
└── .github/workflows/             # ci.yml, release.yml
```

Decisions made now so they are not relitigated:

* **A Receipt is the unit of trust.** `Receipt = {metric_id, query, row_count,
  slice_hash, value, unit, computed_at}`. The `slice_hash` is a BLAKE2b hash of
  the canonicalized rows the figure was computed from, so the same data
  reproduces the same receipt and a changed slice is detectable. Receipts are
  immutable values.
* **The metric engine is deterministic and pure.** A `MetricSpec` is a query or
  expression plus a unit and a suppression rule. Running it over a dataset
  returns a `Figure` (a value plus its receipt). No randomness, no model, no
  network. The same data and spec always produce the same figure and receipt.
* **The grounding gate operates on spans, not vibes.** It parses numeric spans
  out of the drafted narrative and binds each to a receipt by value and metric.
  Unbound or value-mismatched spans block export. It is mechanical and testable;
  it does not ask a model whether the narrative "looks faithful."
* **The drafting seam writes words, never numbers.** Its prompt is given the
  receipted figures and instructed to write prose that references them; the
  grounding gate is the enforcement that it complied. Under any policy pack that
  forbids cloud calls, the seam is fused off and the deterministic template
  drafter is used.
* **Suppression runs before export, after grounding.** Order: compute → receipt
  → draft → ground → suppress → human-approve → export. Suppression is the last
  transform before a human sees the report, so what they approve is what ships.

## Build plan

Ship the differentiator first with the least-risky subsystems, then grow the
chain outward. Phases are tracked in `docs/ROADMAP.md`.

* **v0.1 — Receipts, no LLM.** Service-data CSV in, a TOML metric spec, the
  deterministic engine, receipts, the deterministic template drafter, and the
  grounding gate. Committed eval with planted figures and planted bad numbers
  showing the gate catches every unbound span. Ships the differentiator with no
  model risk.
* **v0.2 — Small-cell suppression.** The privacy invariant: threshold +
  complementary suppression, sourced from primary HUD guidance, expressed as
  tests. Aggregate-only export hardening.
* **v0.3 — The drafting seam.** Optional Bedrock narrative drafting, policy
  gated. The grounding gate now guards a model's output. Judge calibration with
  Cohen's kappa if an LLM scores faithfulness. Model and data cards.
* **v0.4 — The metric-mapping agent.** Map a funder template's required metrics
  to `MetricSpec`s over a schema-variant export, with a review queue for
  low-confidence mappings. This is the hard, unserved part; it comes after the
  trust machinery is proven.
* **v0.5 — Provenance manifest + verify.** Each exported report carries a
  manifest of its receipts and slice hashes; `receipts verify` re-checks that the
  figures still compute from the cited data. Reuses the portfolio hash-chain
  pattern.
* **v1.0 — A second funder template, Docker self-host, committed audits, schema
  stability guarantees.**

## Quality bar

* Every step has a passing and a failing fixture. The privacy-and-trust
  invariants ride on merge-blocking tests: `test_grounding_gate.py` (present and
  green on `main`); `test_suppression.py` and `test_no_model_numbers.py` are
  planned for v0.2, when suppression and the model-drafting seam land.
* `ruff check`, `mypy --strict`, and `pytest` (branch coverage ≥ 90%) pass in CI
  before any feature work continues. No skipped tests on `main`. No bare
  `# type: ignore` or `# noqa` without an issue reference.
* The eval report is committed and regenerated on release, with the grounding
  rate (fail-closed), the hallucinated-number rate with Wilson CIs, and judge
  calibration if used. Failures are shown, not hidden.
* Conformance to the STANDARDS is declared in the README table, values in
  `docs/ROADMAP.md`, findings in `docs/RESPONSIBLE-TECH-AUDITS.md`.
* Conventional commits; PR-sized changes even when working solo; MADR ADRs for
  every architectural decision (engine backend, receipt hash construction,
  suppression threshold source, the drafting-seam boundary).

## Writing style for docs and messages

Plain, concrete prose. At most one em dash per document, prefer zero. No
rule-of-three rhetorical constructions. No "simply," "just," "powerful,"
"seamless." Vary paragraph openings. A finding or a reviewer-facing label says
what is true, where, and what the reviewer should do, in language a grant
manager can act on. Write like a careful engineer, not a launch tweet.

## Open questions to resolve early (do not guess)

1. The metric engine backend: DuckDB versus pure-pandas versus stdlib `sqlite3`,
   judged on determinism, packaging weight in a CI install, and how cleanly a
   `MetricSpec` query expresses an "unduplicated count over a date window."
2. The exact small-cell suppression threshold and complementary-suppression
   rule, from primary HUD HMIS reporting guidance, expressed as tests. Do not
   hard-code n < 11 without confirming it against the source for the report type.
3. How a numeric span is parsed from narrative for the grounding gate
   (percentages, ranges, money, written-out numbers) and how strict the
   value-match is (exact, rounded, tolerance), recorded in an ADR.
4. The report-spec and metric-spec shape, and how far to map toward HMIS CSV and
   common funder templates without overreaching into being a reporting product.
5. Whether the figure-approval and mapping-review surface is a CLI flow or a
   local web UI for the first cut, judged on what a non-technical grant manager
   can actually run.
