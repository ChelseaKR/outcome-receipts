# How to put a language model near a grant report without letting it invent a number

Nonprofit outcome reports often begin with careful analysis and end with manual
copying. A program or data staff member computes a figure in a case-management
system, moves it into a spreadsheet, and then places it into a funder template.
The final document rarely carries enough information for another person to
reproduce the number.

A language model can make the prose faster to draft, but it also adds another
place where a plausible number can appear without evidence. Telling the model to
be accurate does not resolve that problem. The number needs a different source
and an enforceable boundary.

`outcome-receipts` uses a mechanical trust chain:

```text
service data → deterministic SQL → receipt → draft → grounding gate → approval
```

Every report figure is computed before prose is written. Its receipt records the
query, value, source-row count, data-slice hash, definition, and computation time.
The drafting step can arrange receipted figures into sentences, but it is not a
source of figures. A fail-closed gate parses every numeric span and requires an
exact binding to a publishable receipt.

Privacy controls run inside the same chain. Small cells are suppressed before a
publishable surface is built, complementary controls prevent straightforward
arithmetic recovery, and the redacted result passes the grounding gate again.
A named human approves what will actually be exported.

The project does not claim that receipts are a new verification primitive or
that one suppression policy establishes compliance. Its contribution is an
open, offline-first implementation that joins deterministic metric computation,
schema-aware mapping review, receipts, fail-closed numeric grounding, privacy
controls, human approval, and verifiable export.

The included synthetic housing example takes about five minutes to run. It
produces a readable report, a machine-readable receipt manifest, an offline
trace view, and a bundle whose members can be re-derived and checked later.

[Run the five-minute demo](../TRY_THE_DEMO.md). If the workflow resembles a
reporting problem in your organization, describe the metric definition and an
anonymized column inventory. Do not share client-level rows.
