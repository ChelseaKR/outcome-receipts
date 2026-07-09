# Research-backed roadmap

> [!NOTE]
> This roadmap is **research-backed and persona-driven**, and it **complements,
> does not replace,** [`docs/ROADMAP.md`](ROADMAP.md). The shipped/versioned plan
> (v0.1 → v1.0) is authoritative for sequencing the core chain. This file triages
> what the synthetic persona panel in
> [`docs/USER-RESEARCH.md`](USER-RESEARCH.md) surfaced, scores it against
> published evidence, and tags each item so it never becomes a wishlist:
>
> - **[corroborates ROADMAP vX]** — the panel independently re-derived an item the
>   existing roadmap already plans. Triangulation is signal, not noise; it raises
>   confidence in the existing sequence.
> - **[NET-NEW]** — surfaced only by the panel and not in
>   [`docs/ROADMAP.md`](ROADMAP.md). Most are small, legibility-focused additions,
>   not new pillars.
>
> Nothing here overturns the core sequencing rule: ship the differentiator (receipt
> plus fail-closed grounding gate, both live in v0.1) first, then privacy, then the
> model seam, then the hard metric-mapping, then verify. The panel sharpens the
> order and adds a thin layer of funder-facing legibility the existing roadmap
> underweights.
>
> **Assembled: 2026-06-30.** Personas are synthetic (see the warning in
> [`docs/USER-RESEARCH.md`](USER-RESEARCH.md)).

## Research basis (evidence behind the priorities)

All accessed 2026-06-30. Load-bearing claims are cross-checked against at least
two sources.

| # | Evidence | Source(s) | What it drives |
| --- | --- | --- | --- |
| EV1 | Funders are formalizing rejection of "substantially AI-developed" content. NIH will not treat AI-substantially-developed applications as original ideas (effective Sept 25, 2025). A Candid survey found 67% of funders undecided on accepting AI-generated applications, 23% will not, 10% will. | [NIH NOT-OD-25-132](https://grants.nih.gov/grants/guide/notice-files/NOT-OD-25-132.html); [NIH Extramural Nexus](https://grants.nih.gov/news-events/nih-extramural-nexus-news/2025/07/apply-responsibly-policy-on-ai-use-in-nih-research-applications-and-limiting-submissions-per-pi); [Candid](https://blog.candid.org/post/funders-insights-on-ai-generated-grant-application-proposals/) | The product's reason to exist; R5 (provenance/no-model-number statement) |
| EV2 | Reporting is a measured burden: it "outsources the burden" onto grantees; 77% of funders require narrative reports; 75% of funders do not know how much time grantees spend reporting; only ~1/3 accept a common report submitted to multiple funders. | [PEAK, Drowning in Paperwork](https://www.peakgrantmaking.org/resource/drowning-in-paperwork-distracted-from-purpose/); [PEAK, Current State of Practice](https://www.peakgrantmaking.org/insights/grant-reporting-the-current-state-of-practice/) | E2 (common-report reuse); the core time-savings value prop |
| EV3 | Reporting sits near the top of nonprofit leaders' stressors alongside funding and staffing; data is scattered across systems. | [CEP, State of Nonprofits 2025](https://cep.org/report/state-of-nonprofits-2025-what-funders-need-to-know/); [Urban Institute](https://www.urban.org/research/publication/nonprofit-leaders-concerns-about-finances-programming-and-workforce-challenges) | Confirms demand pressure; E4 (mapper) |
| EV4 | Outcome practice runs on logic models / theory of change / MEL, pairing each outcome with an indicator, a data source, and a collection frequency; outputs are distinct from outcomes. | [Bridgespan MEL guide](https://www.bridgespan.org/insights/nonprofit-organizational-effectiveness/a-practical-guide-to-nonprofit-measurement-evaluation-and-learning); [Kellogg Logic Model guide](https://www.naccho.org/uploads/downloadable-resources/Programs/Public-Health-Infrastructure/KelloggLogicModelGuide_161122_162808.pdf); [BetterEvaluation MEL toolkit](https://www.betterevaluation.org/tools-resources/monitoring-evaluation-learning-mel-toolkit-for-grantmakers-grantees) | R2 (definition field); E3 (indicator mapping) |
| EV5 | Verify-or-flag is published, not novel: numeric verification belongs in the renderer, defaults to unverified, fails closed, model-agnostic (PCN); provenance tracing detects hallucination across multi-step workflows (VeriTrail). | [PCN, arXiv:2509.06902](https://arxiv.org/abs/2509.06902); [Microsoft VeriTrail](https://www.microsoft.com/en-us/research/blog/veritrail-detecting-hallucination-and-tracing-provenance-in-multi-step-ai-workflows/); [arXiv:2505.21786](https://arxiv.org/abs/2505.21786) | Keeps novelty honest; validates the gate design; R6 (verify) |
| EV6 | Aggregate-privacy has a primary source: CMS suppresses cells of 1–10 ("<11") and requires complementary suppression. HUD does not prescribe de-identification; the CoC/HMIS Lead decides masking; 8 universal data elements are PII. | [CMS Cell Size Suppression Policy (ResDAC)](https://resdac.org/articles/cms-cell-size-suppression-policy); [HHS Guidance Portal](https://www.hhs.gov/guidance/document/cms-cell-suppression-policy); [HUD Exchange HMIS standards](https://www.hudexchange.info/programs/hmis/hmis-data-and-technical-standards/) | R3 (suppression source); R4 (aggregate-only assertion) |
| EV7 | A commercial tool markets record-cited, reproducible reporting: "numbers and stories on the same record, cited to source"; reports "generate from the data"; persistent participant IDs as the join key. | [Sopact, Reporting Software](https://www.sopact.com/use-case/nonprofit-reporting-software); [Sopact, Impact Measurement](https://www.sopact.com/use-case/nonprofit-impact-measurement) | Confirms "open offline chain + privacy posture," not a new primitive; R1 (trace view) |

## Remediation backlog (close gaps in what v0.1 already does)

Priority: **P0** now · **P1** next · **P2** soon · **P3** opportunistic. Effort:
S afternoon · M day or two · L week or more.

| ID | Remediation | Personas | Pri | Effort | Evidence / notes |
| --- | --- | --- | --- | --- | --- |
| R1 | **Funder-facing "trace this number" view** — render `receipts.json` as static HTML or a printable report appendix: each figure with its plain-language definition, row count, slice hash, timestamp, clickable from the narrative. No SQL, no Python to read it. | P1,P3,P7,P8,P10 | P0 | M | The proof exists but is illegible to non-engineers (theme 1). EV7: record-cited reporting is the bar. **[NET-NEW]** (the manifest exists at v0.1; a human view does not) ✅ Implemented, committed 5d7cd57..42c33b5 |
| R2 | **`definition` field on a `MetricSpec`** that rides in the receipt and renders in plain language (what window, who counts, dedup rule). Document common definitional traps. | P2,P6,P8 | P0 | S | Directly closes the bias-audit TODO in [`RESPONSIBLE-TECH-AUDITS.md`](RESPONSIBLE-TECH-AUDITS.md) (dedup windows, exit categories). EV4. **[NET-NEW]** ✅ Implemented, committed 5d7cd57..42c33b5 |
| R3 | **Small-cell suppression as a merge-blocking, sourced invariant** — cells of 1–10 suppressed, complementary suppression, true zeros preserved, modeled on the CMS policy; assert "suppression applied" in the manifest. | P9,P11 | P0 | M | **[corroborates ROADMAP v0.2]**. EV6 fixes the exact threshold and complementary rule from primary guidance. Already `test_suppression.py` in the plan. |
| R4 | **Machine-readable aggregate-only assertion** in the manifest (no client-level field shipped; export mode = aggregate). | P9,P11 | P1 | S | **[corroborates ROADMAP v0.2]** (aggregate-only export). EV6. Makes the DPIA posture checkable, not just stated. |
| R5 | **Auto-embedded provenance statement in every export** — a short, standard block: numbers from deterministic queries, gate passed at 100%, no figure originated in a model; gate result and counts printed. | P1,P3,P7 | P1 | S | EV1: the product is the answer to AI-skepticism; print it. Pairs with the existing PASS summary. **[NET-NEW]** ✅ Implemented, committed 5d7cd57..42c33b5 |
| R6 | **`receipts verify`** — re-run each receipt's query against the cited data slice and assert the value still matches; exit non-zero on drift. | P7,P10 | P1 | M | **[corroborates ROADMAP v0.5]** (provenance manifest + verify). EV5: re-derivation is the property auditors most want. ✅ Implemented, committed 5d7cd57..42c33b5 |
| R7 | **Numeric-span match precision in the gate** — settle exact vs rounded vs tolerance match for percentages, ranges, money, written-out numbers; record in an ADR. | P2,P10,E1 | P1 | S | [`CLAUDE.md`](../CLAUDE.md) open question #3. A loose match could bind a wrong number; a strict one could false-flag. **[NET-NEW]** (refines the existing gate) |
| R8 | **Human approval / sign-off step** before export (CLI confirm or a signed approval line in the manifest naming the approver). | P3,P4 | P2 | M | **[corroborates ROADMAP]** (the architecture names `approve` between suppress and export; no surface yet). |
| R9 | **Clear, fail-closed error when a query references a missing column** in the export, naming the column. | P5 | P2 | S | Fail-closed everywhere ([`CLAUDE.md`](../CLAUDE.md)). Today a bad spec against a messy export is the most common stumble. **[NET-NEW]** ✅ Implemented 2026-07-02 |
| R10 | **Period-comparison legibility** — label direction and magnitude in the trace view, and bind the change figure's receipt to both period receipts. | P4,P8 | P2 | S | Extends the shipped `[comparison]` feature; the change is already one SQL query. **[NET-NEW]** |
| R11 | **Outputs-vs-outcomes label** on each metric so a reader is not misled (an activity count is not an outcome). | P8 | P3 | S | EV4: the output/outcome distinction is core to MEL. **[NET-NEW]** ✅ Implemented 2026-07-02 |

## Expansion backlog (new capability)

| ID | Expansion | Personas | Pri | Effort | Evidence / notes |
| --- | --- | --- | --- | --- | --- |
| E1 | **Caveat / footnote binding** — attach a qualifying note to a figure so it travels with the receipt and the narrative, inside the gate rather than as loose prose. | P1,P2 | P1 | M | Real reports carry caveats; today they live outside the gate (theme 2). **[NET-NEW]** |
| E2 | **Common-report / multi-funder reuse export** — generate the same receipted figure set into more than one funder template format. | P1,P3 | P1 | M | EV2: only ~1/3 of funders accept a common report and reporting outsources burden; reuse is the time win. Parallels the v1.0 "second template format." **[corroborates ROADMAP v1.0]** (partial) · **[NET-NEW]** framing |
| E3 | **Logic-model / indicator mapping** — optional `indicator` and `data_source` fields per metric tying a figure to a theory-of-change row, with collection frequency. | P8,C-group | P2 | M | EV4. Makes the tool legible to evaluators without becoming a measurement product. **[NET-NEW]** |
| E4 | **Metric-mapping agent** — map a funder template's required metrics to `MetricSpec`s over a schema-variant export (HMIS CSV and common funder shapes), with a review queue for low-confidence mappings. | P5 | P2 | L | **[corroborates ROADMAP v0.4]** — the hard, unserved part. EV3 (scattered data) confirms the need. Lands after trust machinery. |
| E5 | **Policy-gated drafting seam** — optional Claude-on-Bedrock narrative drafter writing prose around receipted figures, guarded by the same gate; off by default. | P1,E1 | P2 | L | **[corroborates ROADMAP v0.3]**. EV5: the gate is the enforcement that a model wrote no number. Judge calibration (Cohen's κ ≥ 0.60) if an LLM scores faithfulness. |
| E6 | **Tamper-evident, signed audit bundle** — package report, receipts, slice hashes, and a `verify` manifest as a signed artifact. | P10,P9 | P3 | M | Builds on R6 and the toward-1.0 supply-chain hardening (SBOM, Sigstore). EV5. **[corroborates ROADMAP]** (toward 1.0) |
| E7 | **Board / financial reconciliation view** — place receipted outcome figures next to the relevant financial lines and a cross-period change log. | P4,P3 | P3 | M | Extends the shipped board-report template. **[NET-NEW]** |
| E8 | **Model and data cards** for the drafting seam, regenerated on release. | P11,E1 | P3 | S | **[corroborates ROADMAP v0.3]** / [`CLAUDE.md`](../CLAUDE.md) quality bar. Lands with E5. |
| E9 | **EN/ES report-output parity** — externalize report copy so the same receipted figures render bilingually. | P7,(LEP communities) | P3 | M | [`CLAUDE.md`](../CLAUDE.md) i18n bar (EN/ES parity); not in [`docs/ROADMAP.md`](ROADMAP.md). **[NET-NEW]** vs roadmap. **Prerequisite FIX-13 (locale-aware number canonicalization in the gate) — DONE:** the gate now binds a figure display and a prose span that denote the same value across locale thousands/decimal separators (US `1,234`, European `1.234`, NBSP-grouped `1 234`), so localized output cannot desync a number from its receipt. Written-out numerals stay unbound (fail-closed). See `src/outcome_receipts/grounding.py`, `tests/test_grounding_locale.py`. |
| E10 | **Data-flow map + retention model** documented in the DPIA. | P11 | P3 | S | Closes the explicit TODO in [`RESPONSIBLE-TECH-AUDITS.md`](RESPONSIBLE-TECH-AUDITS.md). EV6. **[NET-NEW]** (doc, not code) |

## Sequenced roadmap (how the panel layers onto `docs/ROADMAP.md`)

The existing version sequence stays. The panel adds a thin legibility-and-trust
layer, mostly small, that rides alongside each release.

- **Now, alongside v0.2 (suppression).** R3 and R4 are v0.2 already and the panel
  ranks them P0/P1 from the privacy and regulator personas. Bundle the
  afternoon-sized legibility wins that do not depend on a model: **R1** (trace
  view), **R2** (definition field), **R5** (provenance statement). These three are
  the highest-leverage, lowest-risk additions and they make the v0.1
  differentiator legible to the funder who receives it.
- **With v0.3 (drafting seam).** R7 (span-match precision) should be settled
  before a model writes prose, since the gate is the enforcement. E5 is the seam
  itself; E8 (cards) ships with it. R8 (approval step) fits here so a human signs
  what a model drafted.
- **With v0.4 (metric-mapping agent).** E4 is the agent; R9 (missing-column error)
  is its fail-closed companion. E3 (indicator mapping) is cheap to add while the
  spec is being extended for mapping.
- **With v0.5 (provenance + verify).** R6 (`verify`) is the headline. E6 (signed
  bundle) and E7 (reconciliation) follow.
- **Toward v1.0.** E2 (multi-funder reuse) pairs with the planned second template
  format. E9 (EN/ES), E10 (data-flow map), R10/R11 (comparison and
  output/outcome legibility) round out the docs-and-polish set.

## Recommended first sprint (highest-leverage, lowest-risk)

The triage and the existing roadmap converge on the same starting line: finish
making the **already-shipped v0.1 differentiator legible and verifiable to the
non-engineers who receive the report**, while landing the privacy invariant that
the regulated personas block on. None of these put a model anywhere near a number.

1. **R3 + R4 — small-cell suppression as a sourced, merge-blocking invariant**
   (the CMS threshold and complementary rule), plus a machine-readable
   aggregate-only assertion. This is v0.2 already; it is the one hard blocker for
   Ray (P9) and Janet (P11) and is grounded in primary guidance (EV6).
2. **R1 — the funder-facing "trace this number" view.** The single
   highest-leverage move for adoption: it makes the receipts manifest legible to
   Patricia (P7), Diane (P3), Renée (P1), and Sofia (P10) without an engineer. The
   proof already exists in `receipts.json`; this is a rendering of it (EV7).
3. **R2 — the `definition` field in the receipt.** Closes the bias-audit TODO,
   answers Marcus (P2), Tomás (P6), and Dr. Okafor (P8), and is an afternoon of
   work (EV4).
4. **R5 — the auto-embedded provenance statement.** Cheap, and it turns the whole
   reason the tool exists into something printed on the report a skeptical funder
   reads (EV1).
5. **R6 — `receipts verify` (or its first cut).** Reproducibility is the
   most-valued property across the assure-and-verify groups, and re-derivation is
   what the published primitives lean on (EV5). v0.5 on the roadmap; worth pulling
   a thin version forward if the trace view lands first.

Bundle the afternoon-sized wins alongside: **R7** (span-match ADR, before any
model), **R9** (missing-column error), **R11** (output/outcome label).

## Traceability matrix (persona → findings)

| Persona | Remediations | Expansions |
| --- | --- | --- |
| P1 Development director | R1, R5 | E1, E2 |
| P2 Program manager | R2, R7 | E1 |
| P3 Executive director | R1, R5, R8 | E2, E7 |
| P4 Board treasurer | R8, R10 | E7 |
| P5 Data/ops analyst | R9 | E4 |
| P6 Frontline SME | R2 | — |
| P7 Program officer (funder) | R1, R5, R6 | E2, E9 |
| P8 MEL evaluator | R1, R2, R10, R11 | E3 |
| P9 Gov/CoC compliance | R3, R4 | E6 |
| P10 Auditor | R1, R6, R7 | E6 |
| P11 Privacy reviewer | R3, R4 | E8, E10 |
| P12 Owner/maintainer | R7 | E5, E8 |

## Validate with real users (and the risks if we do not)

This roadmap is built on a synthetic panel and published evidence, not on real
discovery. Two interviews would change it most, and both carry real risk if
skipped:

- **A foundation program officer (P7).** The whole bet of R1 and R5 is that
  machine-checkable provenance changes a funder's trust. If the real answer is "I
  glance at the narrative and never open an appendix," then the trace view is
  effort spent on a file no one reads, and the value is the time-savings (EV2),
  not the verification. Test this before building R1 at full fidelity.
- **A privacy reviewer at a real Continuum of Care (P11).** The CMS threshold of
  11 is the modeled default, but the binding rule for a given report may be a HUD,
  state, or funder-specific one. Hard-coding 11 without confirming the rule for
  the report type is exactly the failure [`CLAUDE.md`](../CLAUDE.md) warns
  against. Confirm the source per report type before R3 ships.

Lower-risk but worth checking: whether evaluators (P8) actually want the
indicator mapping (E3) or find it redundant with their own MEL tooling; whether
analysts (P5) would trust an automated mapper (E4) or insist on authoring every
query by hand.

## Honest limits of this exercise

The panel is simulated. It surfaces plausible needs and obvious gaps, but it
cannot tell you which are real, how many funders or orgs exist who would change a
decision because of a receipt, or what any of them would pay. It over-represents
the author's mental model and will miss what only real users surprise you with.
Priorities here are a demand-times-leverage read from synthetic interviews, not a
commitment. The existing [`docs/ROADMAP.md`](ROADMAP.md) sequence remains
authoritative; this file is a research-grounded argument for what to add at the
margins and which of the existing items the evidence most strongly supports. Do
not ship a roadmap off this document alone. Use it to design the real interviews
named above and to reduce their cost.
