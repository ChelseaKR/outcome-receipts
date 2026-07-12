# Outreach kit

These drafts introduce the project without claiming a new verification
primitive or presenting the default privacy policy as compliance advice. Replace
bracketed details before sending.

## Direct practitioner invitation

Subject: A five-minute test for verifiable grant-report numbers

I built an open-source workflow for drafting funder outcome reports where every
number is computed by deterministic SQL and carries a receipt. A fail-closed gate
blocks any displayed number that cannot be traced back to one of those receipts.

The synthetic housing demo takes about five minutes and runs offline. I would
value your reaction to two questions: could a grant or program staff member
follow the trace, and where would mapping your actual metric definitions become
difficult?

Demo: https://github.com/ChelseaKR/outcome-receipts/blob/main/docs/TRY_THE_DEMO.md

Please do not send real service rows or client identifiers. An anonymized column
inventory and a written metric definition are enough for the mapping discussion.

## Community post for NTEN or TechSoup

Title: Testing an offline trust chain for grant-report numbers

I have been working on an open-source reporting workflow for a specific failure
mode: a correct outcome figure gets copied through several tools, or a drafting
model introduces a plausible number that has no source.

The workflow computes every figure with deterministic SQL, attaches a receipt,
applies small-cell controls, and blocks export unless every displayed number
binds to a publishable receipt. A named human still approves the result. The
language-model drafting seam is optional and off by default.

There is a five-minute synthetic housing demo here:
https://github.com/ChelseaKR/outcome-receipts/blob/main/docs/TRY_THE_DEMO.md

I am looking for practitioner feedback, especially on the difficult part:
mapping a funder's metric definition onto one organization's schema. What would
you need to see before trusting the trace, and which definitions are hardest to
translate into a reproducible query?

## LinkedIn post

Grant-report numbers should not become less trustworthy when prose gets easier
to draft.

I built `outcome-receipts`, an open-source, offline-first workflow that computes
each figure with deterministic SQL and attaches a receipt. A fail-closed gate
blocks export if any displayed number cannot be traced to a publishable receipt.
The optional model writes prose only; it never supplies figures.

The five-minute synthetic housing demo shows the report, receipt manifest,
privacy boundary, human approval, and re-derivation check:
https://github.com/ChelseaKR/outcome-receipts/blob/main/docs/TRY_THE_DEMO.md

I would especially like feedback from nonprofit grant, program, evaluation, and
data staff who translate funder definitions into reports.

## NHSDC session or lightning-talk abstract

Title: Every number is a receipt: a fail-closed trust chain for outcome reports

Outcome reporting often depends on metric definitions that must be translated
into one provider's HMIS or service-data schema. This session demonstrates an
open-source, offline-first workflow that maps explicit requirements to reviewed
SQL, computes aggregate figures with receipts, suppresses small cells, and
refuses export when a displayed number lacks evidence. Participants will inspect
a synthetic housing example from source schema through a funder-readable trace
and discuss where metric-mapping uncertainty must route back to a human. The
session does not present the tool as a reporting standard or compliance system;
it focuses on reproducibility, privacy boundaries, and reviewable decisions.

## Follow-up after a demo run

Thank you for trying the demo. I am tracking whether people can complete three
steps without assistance: produce the report, locate the definition behind a
figure, and run verification. If one of those steps was unclear, please tell me
the command or page where you stopped. If you reached the mapping question, an
anonymized column inventory and a plain-language metric definition are the most
useful next inputs.
