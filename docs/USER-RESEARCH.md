# User research — synthetic personas and simulated interviews

> [!WARNING]
> **These personas and interviews are synthetic.** They were generated as a
> structured brainstorming device, not conducted with real people. No real user
> said any of this. The panel exists to pressure-test `outcome-receipts` from
> every stakeholder angle at once. It is not evidence of demand and does not
> substitute for real discovery. Treat every "quote" as a hypothesis to validate,
> not a finding. This labelling matches how the repo labels its synthetic eval
> fixtures (see [`eval/report.md`](../eval/report.md): seeded synthetic data,
> zero real personal data).
>
> The honest next step is real interviews with at least five of these roles, with
> priority on a funder program officer and a privacy reviewer at a real
> human-services org. The triaged backlog is in
> [`docs/RESEARCH-ROADMAP.md`](RESEARCH-ROADMAP.md).
>
> **Last assembled: 2026-06-30.**

## Why do this at all

Role-playing the full cast around a verified-reporting tool surfaces gaps a
single author misses, and it forces the question "who is each feature for?" The
synthesis at the end is tagged so it does not drift into a wishlist. The roadmap
file carries the tags; this file carries the interviews.

A guardrail specific to this product: every "values today" line below maps to a
feature that exists in **v0.1**, which ships the receipted-figure path with **no
language model in any path**. The deterministic SQLite engine, the per-figure
receipt, the template drafter, and the fail-closed grounding gate are real now.
Small-cell suppression, the drafting seam, the metric-mapping agent, and
`receipts verify` are roadmap, not present tense, and the interviews keep that
line honest.

## Method

- **Sampling frame.** The people a verified funder report passes through: the
  nonprofit staff who author it (development director, program manager,
  executive director, board), the people who operate the underlying data
  (analyst, frontline case manager), the funders and evaluators who receive and
  check it (foundation program officer, MEL evaluator, government compliance
  officer), the people who assure it (independent auditor, privacy and compliance
  reviewer), and the owner who builds it.
- **Protocol.** Each persona gets a goal, a walkthrough of the v0.1 surfaces they
  would actually touch (`receipts run`, `receipts audit`, `receipts eval`, the
  TOML spec, `out/report.md`, `out/receipts.json`), where they would stall, what
  they would want next, and the one thing that makes them adopt or walk.
- **Synthesis.** Frictions become **R**emediations; wishes become
  **E**xpansions. Each item in [`RESEARCH-ROADMAP.md`](RESEARCH-ROADMAP.md)
  carries priority, effort, the personas who raised it, and a cited evidence tag.
- **Research basis.** The panel is grounded in published evidence, not invented
  needs. Sources, accessed 2026-06-30:
  - Funders are formalizing skepticism of "substantially AI-developed" content.
    NIH will not consider applications "substantially developed by AI" to be the
    applicant's original ideas, effective for the September 25, 2025 receipt date
    ([NOT-OD-25-132](https://grants.nih.gov/grants/guide/notice-files/NOT-OD-25-132.html);
    [NIH Extramural Nexus, "Apply Responsibly," July 2025](https://grants.nih.gov/news-events/nih-extramural-nexus-news/2025/07/apply-responsibly-policy-on-ai-use-in-nih-research-applications-and-limiting-submissions-per-pi)).
    On the foundation side, a Candid survey found 67% of funders undecided about
    accepting AI-generated applications, 23% will not, 10% will, and 57% do not
    know whether they have already received AI-generated proposals
    ([Candid blog, "Where do foundations stand on AI-generated grant proposals?"](https://blog.candid.org/post/funders-insights-on-ai-generated-grant-application-proposals/)).
  - Reporting is a measured burden, not a felt one only. PEAK Grantmaking's
    "Drowning in Paperwork, Distracted from Purpose" (Project Streamline)
    documents how reporting "outsources the burden" onto grantees, and PEAK's
    "Grant Reporting: The Current State of Practice" found 77% of funders require
    narrative reports and 75% of funders do not know how much time grantees spend
    on reporting compliance
    ([Drowning in Paperwork](https://www.peakgrantmaking.org/resource/drowning-in-paperwork-distracted-from-purpose/);
    [Current State of Practice](https://www.peakgrantmaking.org/insights/grant-reporting-the-current-state-of-practice/)).
    Reporting now sits near the top of nonprofit leaders' stressors alongside
    funding and staffing
    ([CEP, State of Nonprofits 2025](https://cep.org/report/state-of-nonprofits-2025-what-funders-need-to-know/);
    [Urban Institute, nonprofit leaders' concerns](https://www.urban.org/research/publication/nonprofit-leaders-concerns-about-finances-programming-and-workforce-challenges)).
  - Outcome practice runs on logic models, theory of change, and MEL, which pair
    each outcome with an indicator, a data source, and a collection frequency
    ([Bridgespan, A Practical Guide to MEL](https://www.bridgespan.org/insights/nonprofit-organizational-effectiveness/a-practical-guide-to-nonprofit-measurement-evaluation-and-learning);
    [W.K. Kellogg Logic Model Development Guide](https://www.naccho.org/uploads/downloadable-resources/Programs/Public-Health-Infrastructure/KelloggLogicModelGuide_161122_162808.pdf);
    [BetterEvaluation MEL toolkit](https://www.betterevaluation.org/tools-resources/monitoring-evaluation-learning-mel-toolkit-for-grantmakers-grantees)).
  - The verify-or-flag idea is published and not novel. Proof-Carrying Numbers
    places numeric verification in the renderer and defaults every number to
    unverified, failing closed, model-agnostic
    ([Solatorio, PCN, arXiv:2509.06902](https://arxiv.org/abs/2509.06902));
    VeriTrail traces provenance and detects hallucination across multi-step
    workflows
    ([Microsoft Research, VeriTrail](https://www.microsoft.com/en-us/research/blog/veritrail-detecting-hallucination-and-tracing-provenance-in-multi-step-ai-workflows/);
    [arXiv:2505.21786](https://arxiv.org/abs/2505.21786)).
  - Aggregate-privacy practice for human-services data has a primary source. The
    CMS Cell Size Suppression Policy suppresses cells of 1–10 (reported as "<11")
    and requires complementary suppression so a suppressed cell cannot be
    recovered by subtraction
    ([CMS Cell Size Suppression Policy, ResDAC](https://resdac.org/articles/cms-cell-size-suppression-policy);
    [HHS Guidance Portal](https://www.hhs.gov/guidance/document/cms-cell-suppression-policy)).
    HUD does not itself prescribe a de-identification rule; a Continuum of Care
    and its HMIS Lead decide masking, and eight universal data elements are
    treated as PII
    ([HUD Exchange, HMIS Data and Technical Standards](https://www.hudexchange.info/programs/hmis/hmis-data-and-technical-standards/)).
  - A commercial tool already markets record-cited reporting. Sopact describes
    "numbers and stories on the same record, cited to source" and reports that
    "generate from the data" rather than being reassembled each cycle, with
    persistent participant IDs as the join key
    ([Sopact, Nonprofit Reporting Software](https://www.sopact.com/use-case/nonprofit-reporting-software);
    [Sopact, Nonprofit Impact Measurement](https://www.sopact.com/use-case/nonprofit-impact-measurement)).
    This is why the repo claims an open offline chain plus metric-mapping plus a
    privacy posture, not a new primitive.
- **Effort scale (used in the roadmap).** S is about an afternoon, M a day or
  two, L a week or more.

## How to read a persona

Each card compresses the simulated interview to five lines: **Goal** · **Values
today** (mapped to real v0.1 features) · **Gets stuck** · **Wants next** ·
**Adopts / walks**.

## Persona roster

| # | Persona | Group | Primary goal | Top friction (maps to a roadmap gap) |
| --- | --- | --- | --- | --- |
| P1 | **Renée** — development director / lead grant writer | Draft & Report | Submit an outcome report no funder can call AI-invented | Can fill a template, but the prose caveats she must add by hand are not bound to anything |
| P2 | **Marcus** — program manager (owns the numbers) | Draft & Report | Make sure each figure means what the funder thinks it means | The receipt shows the query, not the human definition or the dedup window |
| P3 | **Diane** — executive director | Draft & Report | Sign off without fear of a wrong number in front of a funder | Trusts the gate, but has no one-line, non-technical proof to hand a skeptical board or funder |
| P4 | **Hal** — board treasurer | Draft & Report | Approve what the org reports, tie it to the audited books | No reconciliation view between report figures and the financials |
| P5 | **Wendy** — data and operations analyst | Operate the Data | Turn a messy case-system export into a clean figure set | Mapping the funder's required metric onto her real columns is still hand work (no mapper in v0.1) |
| P6 | **Tomás** — frontline case manager / SME | Operate the Data | Make sure a count matches what happened on the ground | He knows the edge cases (re-entries, transfers) but the spec is authored without him |
| P7 | **Patricia** — foundation program officer | Fund & Verify | Trust the numbers in a grantee's report without an audit | Receives `report.md` and `receipts.json`, but cannot trace a figure without reading SQL or running Python |
| P8 | **Dr. Okafor** — external evaluator / MEL specialist | Fund & Verify | Confirm the figures match the logic model's indicators | No link from a figure to the indicator, data source, or collection window it is supposed to measure |
| P9 | **Ray** — government / CoC grants compliance officer | Fund & Verify | Accept a report into a regulated, HMIS-backed program | No small-cell suppression yet (v0.2), and no aggregate-only assertion he can rely on |
| P10 | **Sofia** — independent auditor (Single Audit) | Assure & Audit | Re-derive a reported figure from source on demand | The slice hash proves the data did not change, but `receipts verify` (re-compute) is v0.5, not present |
| P11 | **Janet** — privacy and compliance reviewer | Assure & Audit | Confirm no client is re-identifiable from the export | Suppression is roadmap (v0.2); today she must trust that no small cell or client field ships |
| P12 | **Chelsea** — owner / maintainer | Build | Prove the differentiator before any model is wired in | Keeping novelty honest and the three invariants merge-blocking as scope grows |

---

## Group A — Draft & Report (the nonprofit authoring side)

### A1 — Renée, development director and lead grant writer (primary author)
- **Goal.** File an outcome report that a funder cannot dismiss as
  "substantially AI-developed," and do it in hours, not the multi-day scramble of
  copying numbers between the case system, a spreadsheet, and the funder template.
- **Values today.** `receipts run` fills the TOML template's `{metric_id}`
  placeholders with figures that came from queries, and the deterministic drafter
  writes no number of its own. The grounding gate's PASS line, with "numbers in
  narrative: 4 (bound 4, unbound 0)," is exactly the assurance she wants to put in
  front of a program officer.
- **Gets stuck.** Her real reports carry caveats in prose ("Q3 excludes two
  partial intakes pending verification"). Those sentences are not bound to a
  receipt, so they live outside the gate. She also wants the report itself to
  carry a short, plain statement of how it was produced, to pre-empt the
  AI-skepticism the Candid and NIH evidence describes.
- **Wants next.** A way to attach a caveat or footnote to a figure so it travels
  with the receipt; an auto-embedded "how this report was produced" provenance
  note (numbers from queries, gate passed, no model invented a figure); a
  one-funder-to-many "common report" export.
- **Adopts if.** The output is something she can defend line by line to a funder.
  **Walks if.** She still has to assemble half the report by hand anyway.

### A2 — Marcus, program manager who owns the numbers
- **Goal.** Make sure each reported figure means what the funder believes it
  means. He is the one who knows that "clients served" depends on a deduplication
  window and an exit-destination rule.
- **Values today.** The receipt records the exact query, the row count, and a
  BLAKE2b slice hash, so a definition is visible and contestable rather than
  buried. This matches the bias finding in
  [`docs/RESPONSIBLE-TECH-AUDITS.md`](RESPONSIBLE-TECH-AUDITS.md): the tool does
  not hide definitional choices.
- **Gets stuck.** The receipt shows the SQL, but a program officer or evaluator
  cannot read SQL. The human-readable definition (what window, who counts, why)
  is not a first-class field, and the dedup-window trap the audit doc flags as a
  TODO is not yet surfaced.
- **Wants next.** A `definition` field on a metric spec that rides in the
  receipt and renders in plain language; a documented list of common definitional
  traps (dedup windows, exit categories) with how the receipt exposes each.
- **Adopts if.** He can show a funder the definition without translating SQL.
  **Walks if.** A "clean" report still hides the choices that change the number.

### A3 — Diane, executive director
- **Goal.** Sign off on every figure and sleep at night, because a wrong number
  in front of a funder can cost the org its funding and its credibility.
- **Values today.** The gate is fail-closed and mechanical, so the protection
  does not depend on her catching an error on a Friday. The committed
  [`eval/report.md`](../eval/report.md) shows a gated 100% grounding rate with a
  Wilson confidence interval, not a single headline number.
- **Gets stuck.** She trusts the gate, but she has no short, non-technical line
  to hand a board member or a skeptical funder that explains why this report is
  different from one a chatbot wrote.
- **Wants next.** A one-paragraph, plain-language trust statement she can paste
  into a cover letter; a human approval step she actually signs (the
  compute → ground → suppress → approve → export order in
  [`docs/ROADMAP.md`](ROADMAP.md) names it, but there is no sign-off surface yet).
- **Adopts if.** It lowers the personal risk of putting her name on the numbers.
  **Walks if.** Approving means reading SQL she does not understand.

### A4 — Hal, board treasurer
- **Goal.** Approve what the organization reports to funders and reconcile it
  against the audited financials he is fiduciarily responsible for.
- **Values today.** Aggregate-only output and a receipts manifest mean the board
  is approving figures with provenance, not a roster and not a number someone
  typed.
- **Gets stuck.** There is no reconciliation view tying a reported outcome count
  to the financial statements, so he cannot see at a glance that the program
  serving "187 households" lines up with the grant's budget and the audit.
- **Wants next.** A board-report view that places the receipted outcome figures
  next to the relevant financial lines; a change log across periods so he can
  explain a swing.
- **Adopts if.** It survives the auditor's questions at the board meeting.
  **Walks if.** It is one more artifact the board cannot reconcile.

---

## Group B — Operate the Data

### B1 — Wendy, data and operations analyst
- **Goal.** Take the case-management or HMIS CSV export, with its quirks and
  renamed columns, and produce a clean, defensible figure set for the report.
- **Values today.** Service data loads into an in-memory SQLite database and each
  metric runs as a deterministic SQL query, so the same export reproduces the
  same figure and slice hash. No randomness, no network, no model.
- **Gets stuck.** The hard part is upstream of the engine: mapping the funder
  template's required metric ("unduplicated clients exiting to permanent
  housing") onto her specific export's columns. In v0.1 that mapping is hand
  work; the metric-mapping agent is v0.4.
- **Wants next.** The mapping helper with a review queue for low-confidence
  mappings (roadmap v0.4); recognizers for common HMIS CSV and funder shapes; a
  clear error when a query references a column the export does not have.
- **Adopts if.** It cuts the per-cycle remapping she does today. **Walks if.**
  She still rewrites every query by hand each quarter.

### B2 — Tomás, frontline case manager and subject-matter expert
- **Goal.** Make sure a reported count matches what actually happened with
  clients, including the messy cases that a query can quietly miscount.
- **Values today.** Because every figure carries its exact query in the receipt,
  he can ask "does this query count a client who re-entered in March?" and get a
  concrete, checkable answer instead of a vibe.
- **Gets stuck.** He is not consulted when the spec is authored, and he cannot
  read SQL, so the edge cases he knows (re-entries, transfers between programs,
  a family counted as one household or several) may be encoded wrong without
  anyone noticing until a funder asks.
- **Wants next.** A plain-language description of each metric he can review and
  flag; a lightweight "this count looks wrong because…" path that becomes a test
  case.
- **Adopts if.** His ground knowledge can correct a definition without code.
  **Walks if.** The numbers are authored over his head and he only sees them after
  they ship.

---

## Group C — Fund & Verify (funder, evaluator, regulator)

### C1 — Patricia, foundation program officer (receives the report)
- **Goal.** Trust the numbers in a grantee's outcome report without commissioning
  an audit, especially now that she cannot tell whether a polished report was
  written by a model. The Candid survey puts her squarely in the 67% who are
  undecided about AI-generated content.
- **Values today.** She receives `out/report.md` with a receipts section and
  `out/receipts.json`. In principle every figure traces to a query, a row count,
  and a slice hash, which is exactly the assurance she lacks from a normal PDF.
- **Gets stuck.** In practice she cannot open SQL or run Python. The receipts
  manifest is machine-readable, but she has no human-facing way to click a figure
  and see its provenance, so the proof exists but is not legible to her.
- **Wants next.** A funder-facing "trace this number" view (static HTML or a
  printable appendix) that renders each figure with its definition, count, and
  hash; a short standard statement that no number originated in a model.
- **Adopts if.** She can verify a figure in ten seconds without an engineer.
  **Walks if.** "Verifiable" requires tooling only the grantee's analyst can run.

### C2 — Dr. Okafor, external evaluator and MEL specialist
- **Goal.** Confirm the reported figures actually measure the program's intended
  outcomes, mapping each to the logic model or theory of change he helped build.
- **Values today.** Deterministic, reproducible figures with receipts are a
  better substrate than the usual hand-keyed spreadsheet, and the period
  comparison computes the change with a single SQL query rather than arithmetic
  on the page.
- **Gets stuck.** There is no link from a figure to the indicator it represents,
  the data source, or the collection frequency, which is the spine of MEL
  practice. He cannot see whether a number is an output count or a genuine
  outcome.
- **Wants next.** An optional `indicator` and `data_source` field per metric that
  ties a figure to a logic-model row; an outputs-versus-outcomes label so a
  reader is not misled.
- **Adopts if.** It slots into an existing MEL framework instead of replacing it.
  **Walks if.** It proves the number but not that the number measures the right
  thing.

### C3 — Ray, government and Continuum-of-Care grants compliance officer
- **Goal.** Accept a grantee report into a regulated, HMIS-backed program without
  importing a re-identification risk or an unverifiable count.
- **Values today.** Aggregate-only output and receipts that carry no client-level
  field values are the right posture for HMIS-derived reporting, where eight
  universal data elements are PII.
- **Gets stuck.** Small-cell suppression is v0.2, not present. Until it lands, a
  report could publish a count of three exits in a category and recreate a
  disclosure risk, and there is no machine assertion that suppression ran.
- **Wants next.** The CMS-modeled suppression (cells of 1–10 suppressed, with
  complementary suppression) shipped and asserted in the manifest; an
  aggregate-only export mode he can require by policy.
- **Adopts if.** Suppression is a tested invariant, sourced from primary
  guidance, not a setting. **Walks if.** A small cell can reach a published table.

---

## Group D — Assure & Audit

### D1 — Sofia, independent auditor (Single Audit / nonprofit compliance)
- **Goal.** Re-derive a reported figure from source data on demand, so a funder
  claim survives an independent test.
- **Values today.** The slice hash is a BLAKE2b digest of the canonicalized rows
  the figure was computed from, so a changed data slice is detectable, and the
  receipt pins the exact query. The committed eval shows failures rather than
  hiding them.
- **Gets stuck.** The hash proves the data did not change, but re-computing the
  figure from the cited slice and asserting it still matches is `receipts verify`,
  which is roadmap v0.5. Today she can detect tampering but not push-button
  re-derive.
- **Wants next.** `receipts verify` that re-runs each receipt against the cited
  data and asserts identity; a tamper-evident, signed audit bundle (this aligns
  with the supply-chain hardening toward 1.0).
- **Adopts if.** She can independently reproduce a claim with one command.
  **Walks if.** "Reproducible" means trusting a hash she cannot recompute herself.

### D2 — Janet, privacy and compliance reviewer (small-cell, client confidentiality)
- **Goal.** Confirm that nothing in the export lets a client be re-identified, and
  document it for a DPIA.
- **Values today.** The DPIA framing in
  [`docs/RESPONSIBLE-TECH-AUDITS.md`](RESPONSIBLE-TECH-AUDITS.md) is real: the
  report is aggregate figures, not a roster, and the receipts manifest records the
  query, the row count, and a hash, never the rows.
- **Gets stuck.** Small-cell suppression is v0.2. Until then, the protective
  invariant she most needs is a stated intention rather than a tested gate, and
  the complementary-suppression rule that prevents recovery-by-subtraction is not
  yet enforced.
- **Wants next.** Suppression as a merge-blocking test sourced from the CMS Cell
  Size Suppression Policy, with true zeros preserved; a data-flow map and
  retention model (the audit doc lists both as TODO).
- **Adopts if.** The privacy invariant is enforced and cites its source.
  **Walks if.** Suppression stays a configurable option a hurried user can disable.

---

## Group E — Build

### E1 — Chelsea, owner and maintainer
- **Goal.** Prove the differentiator (receipt plus fail-closed grounding gate)
  before any model is wired in, and keep the project honest about novelty as it
  grows.
- **Values today.** v0.1 ships the entire receipted-figure path with no model, so
  the contribution is provable now. The three merge-blocking tests
  (`test_grounding_gate.py`, plus the planned `test_suppression.py` and
  `test_no_model_numbers.py`) are the trust-and-privacy invariants.
- **Gets stuck.** The pull toward scope creep: a mapper, a model seam, a UI, each
  of which can quietly weaken an invariant. The README must keep saying plainly
  that the verify-or-flag primitive is published (PCN, VeriTrail) and that
  deterministic record-cited reporting is sold commercially (Sopact).
- **Wants next.** The sequencing already in [`docs/ROADMAP.md`](ROADMAP.md):
  suppression next (v0.2), then the policy-gated drafting seam (v0.3), then the
  hard metric-mapping agent (v0.4), then provenance verify (v0.5). The panel below
  sharpens that order; it does not overturn it.
- **Adopts if.** Each new seam ships with a passing and a failing fixture and
  does not touch the load-bearing invariant. **Walks if.** A feature makes a
  number able to originate outside a receipt.

---

## Cross-cutting themes (what the cast agrees on)

1. **The proof exists but is not legible to the people who need it.** P1, P3, P7,
   P8 all hold a receipts manifest that is machine-true and human-opaque. The
   single highest-leverage move is a funder-facing, plain-language "trace this
   number" surface plus a metric `definition` field. The engine is right; the
   *view* for non-engineers is thin. This is the same lesson the sibling
   personal-site panel reached: the components are there, the legibility is not.
2. **Definitions decide the number, so they belong in the receipt.** P2, P6, P8
   independently land on dedup windows, exit categories, and outputs-versus-
   outcomes. The receipt records the query; it should also record the human
   definition, which the bias audit already flags as a TODO.
3. **Privacy is the gate that is not built yet.** P9 and P11 cannot fully adopt
   until small-cell suppression (v0.2) is a tested invariant sourced from the CMS
   policy. This is the most-cited blocker among the verify-and-assure groups, and
   it is already next on the roadmap, which the evidence corroborates.
4. **Reproducibility is the most-valued property, and `verify` finishes it.** P7,
   P10 want push-button re-derivation. The slice hash gets halfway (tamper
   detection); `receipts verify` (v0.5) closes it. Reproducibility is also what
   the published primitives (PCN, VeriTrail) and the commercial tool (Sopact) all
   lean on, so it is the property to perfect.
5. **The AI-skepticism the tool was built for is an asset to name out loud.** P1,
   P3, P7 each want a short, standard statement that no number originated in a
   model. The repo's whole posture is the answer to the Candid and NIH evidence;
   it should be printed on the report, not left implicit.
6. **Outcome practice is MEL-shaped, and the tool should speak that language.**
   P8 and C-group personas want indicators, data sources, and the
   output/outcome distinction. Mapping a figure to a logic-model row is cheap and
   makes the tool legible to evaluators without becoming a measurement product.

## Honest limits of this exercise

This is simulated. It can generate plausible needs and obvious gaps, but it
cannot tell you which are real, how many funders would actually change a decision
because of a receipt, or whether a program officer would use a trace view. It
over-represents the author's mental model and will miss what only a real privacy
reviewer at a real Continuum of Care, or a real foundation program officer,
would surface. Two roles carry the most uncertainty and should be interviewed
first: the **funder program officer** (does machine-checkable provenance change
trust, or just add a file they ignore?) and the **privacy reviewer** (is the
CMS-modeled threshold the right one for the funder's report type, or is a HUD or
funder-specific rule binding instead?). Do not prioritize a roadmap off this
panel alone. Use it to design the real interviews and to reduce their cost.

The triaged backlog, sequenced roadmap, and traceability matrix are in
[`docs/RESEARCH-ROADMAP.md`](RESEARCH-ROADMAP.md).
