# 0014 — The Word export is gated on its own bytes

Status: accepted (2026-09-11)

## Context

Funder portals accept Word or PDF, so staff paste `report.md` into Word by hand.
That was the one step after the grounding gate where a number could change: the
gate ran over `report.md`, and the file a funder opened was produced outside it.
Issue 159 asked for the document to be exported, and for the gate to run over the
document rather than over the Markdown it came from.

## Decision

### `report.docx` is rendered from `report.md`, not from what built it

`run --format docx` renders the finished report text into `report.docx`, beside
`report.md` and never instead of it. `render_report` stays the one place that
decides what a report says; the document is a conversion of its output, so there
is no second layout that could drift from the first. The document therefore
carries everything `report.md` does, in the same order: the narrative, the
comparison and reconciliation tables, each chart's data table, requirement
coverage, the provenance statement verbatim, and the receipts appendix.

### The gate reads the document back out of its bytes

A renderer checked against itself cannot fail. `check_document` reads the written
bytes back with a reader that shares nothing with the writer except the block
model, and makes four comparisons:

1. the blocks read back equal the blocks `report.md` renders to, character for
   character and style for style;
2. the document's digits equal the digits in `report.md`'s raw text;
3. the redaction marker appears as many times as in `report.md`'s raw text;
4. the narrative read back -- after the title, up to the first section heading,
   the same region `verify` grounds in `report.md` -- grounds against the
   publishable figures.

The second and third exist because the first trusts the renderer: a renderer that
lost a number would expect the loss and agree with itself. They read
`report.md`'s raw text, which the renderer never touches. The same function runs
at export, before anything is written, and again in `verify --bundle`.

### The reader accepts only what the writer writes

Eight parts, all stored, none repeated, none encrypted; the six constant parts
byte-identical to the ones this version writes; `word/document.xml` through a
closed vocabulary of 26 elements, each allowed only under the parents and with
the attributes it is written with; no document type declaration, entity,
comment, processing instruction, CDATA section, or text outside a text run.

That is deliberate. The gate has to see every character Word would render, and
the only way to be sure of that is to accept nothing the reader does not
understand. A document someone opened in Word and saved again is a different
document, and `verify` says so.

The XML is read with the standard library's expat parser, driven directly with
the refusals `defusedxml` installs, because the package has no runtime
dependencies.

### Charts are not embedded

Rasterizing the SVG needs a native dependency this package does not take, and
Word's SVG extension still requires a raster fallback. Each chart's image line
becomes one sentence naming the chart's file in the export -- sealed in the same
bundle -- followed by the data table `report.md` already carries. The issue names
this as the fallback, "stated in the document". The sentence adds no number of
its own in either locale, which a test holds.

### Reproducible by construction

Nothing in the document reads a clock: one 1980-01-01 timestamp on every entry,
every entry stored, the creating system and file attributes pinned, and the parts
in a fixed order. Two `--reproducible` runs write byte-identical documents, and so
does any pair of runs whose `report.md` is byte-identical.

### What changes in the contracts

`receipts.json`'s `artifacts` map gains a `report.docx` key when the flag is
given. The map was already open, so receipts manifest `2.0` is unchanged. A
verifier older than this change checks the document's sha256 and nothing else --
it does not read the document, compare it with `report.md`, or ground it. Without
the flag, every artifact is byte-identical to what the previous commit wrote.

## Consequences

- An edited document fails `verify --bundle`, even when the editor also rewrote
  every digest in `receipts.json` and resealed `bundle.json`.
- The document gate can refuse a narrative the Markdown gate passes, because
  inline markup changes how a number reads. Measured: a template reading
  `served **{clients_served}**% of its clients` passes `run`, whose gate binds
  `12`, while `report.md` in any Markdown viewer -- and the document -- says
  `12%`, which no receipt supports. `--format docx` refuses that export,
  naming `12%`. The document is what the funder reads, so its reading is the
  one gated. The Markdown gate is not changed here; issue
  [191](https://github.com/ChelseaKR/outcome-receipts/issues/191) records
  the gap, which a drafting model can reach as easily as an author.
- A change to any constant part is a change to what `verify` accepts. When one is
  needed, the previous version's parts have to stay readable, or every earlier
  document stops verifying.

## Not decided here

- **PDF.** It needs a renderer decision of its own.
- **`export --from out/ --format docx`.** Adding a document to a bundle that is
  already sealed means rewriting `receipts.json`, whose hash is what the export
  ledger recorded for that export. It would either break the ledger's link to
  its manifest or need a second ledger entry for one export. That is a decision
  about the ledger, not about the document, and it is left open. Running
  `run --format docx` again is the path today.
