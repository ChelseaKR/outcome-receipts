# ADR 0013: Requirement coverage is proven at export, and an unanswerable requirement carries two halves

**Status:** Accepted
**Date:** 2026-09-07
**Decider:** Chelsea Kelly-Reif

(0012 is taken by the draft in #176. The number is skipped rather than reused so
the two can land in either order.)

## Context

The project proves every published number traces to a receipt. It did not prove
every *required* number was published.

`receipts map` returned per-requirement candidates that can come back `blocked`.
`requirements-diff` compared two requirement documents by stable id.
`contract-check` refused a milestone whose metric was absent. **Nothing
connected a requirement set to an export.** A spec that simply omitted a
required metric ran, grounded, was approved, and exported a report that was
fully receipted and silently incomplete.

That is this portfolio's dominant defect shape, one level up from where the
project already refuses it. A requirement nobody could answer and a requirement
nobody was asked about rendered identically — as nothing on the page — which is
the same error as a suppressed cell rendering as a zero. ADR 0009 refuses that
inside a figure. The report as a whole had no equivalent.

## Decision

A spec may declare `[requirements] path = "..."`, and each metric may name the
`requirement_id` it answers. When a spec is bound, **export must account for
every requirement in the document** or it refuses, writes nothing, and names
the requirement. The exit code is **4**, distinct from the grounding gate's 2.

Four states, kept distinguishable:

| status | meaning |
|---|---|
| `answered` | a metric names it and its figure was published with a receipt |
| `withheld` | a metric names it, the figure exists, and suppression withheld the cell |
| `unanswerable` | no metric answers it, and the spec carries **both** a blocker `map` reproduces **and** a reason a person wrote |
| `unanswered` | anything else — the export is refused |

`withheld` is answered. A query exists, it ran, and it produced a receipt whose
cell the privacy policy hides. Reporting it as unanswered would tell a funder
the organization never measured something it did measure.

**An `unanswerable` declaration needs both halves and neither is sufficient.**
A blocker without a reason is a tool's excuse: it says only that the tool could
not do it, never that a person looked. A reason without a blocker is
unfalsifiable — an operator can write any sentence. So the declared `blocker` is
**re-derived at export** by running `mapping.build_mapping_queue` over the same
data and the same requirement document, and the declaration is refused unless
the mapper produces that exact string for that requirement. A requirement that
maps cleanly cannot be declared unanswerable at all, and the refusal says so in
those words.

The requirement document's sha256 rides in the receipts manifest beside the
coverage record, and `verify --bundle` re-derives both. Editing the requirement
document after export fails, naming the digest; doctoring the coverage record
itself fails too, because the record is re-derived rather than read back.

## Options considered

| Option | What an operator can do | What a funder learns |
|---|---|---|
| **Bind the set and refuse (chosen)** | declare a requirement unanswerable, with a blocker the tool confirms | which requirements were answered, withheld, and not answerable |
| Warn but export | ignore the warning | nothing; the warning is not in the report |
| Require every requirement to be answered | nothing — an unanswerable requirement blocks the report forever | nothing, because no report ships |
| Accept a free-text reason with no blocker | wave any requirement away | a sentence nothing can check |

## Consequences

- **The coverage table is in the publishable report**, in EN and ES, not only in
  the manifest and the trace view. That tells the funder what was not answered,
  which is the honest choice and the one an operator will resist. It is also
  reversible in one place (`render_report`) if it turns out to be the wrong
  call for a real funder relationship.
- A spec with no `[requirements]` binding is **unchanged in every byte**. Its
  manifest carries no `requirements` key — absent, not an empty record, because
  such a spec has not answered zero requirements, it has made no claim at all.
  `verify --bundle` reports `not checked` rather than `ok` for the same reason.
- The `unanswerable` blocker check couples export to `mapping`, so a change to
  the mapper's blocker strings will invalidate declarations written against the
  old ones. That is deliberate: a declaration is a claim about what the tool
  says, and if the tool stops saying it, the claim needs re-approving.
- The receipts manifest stays at schema `2.0` with `requirements` as an
  optional additive member. See `docs/SPEC-STABILITY.md` for what that does and
  does not promise.

## Deliberately left open

- **Whether an `unanswerable` reason needs its own approver role** under #162's
  policy. It is the one field in an export that asserts something the data
  cannot check, and today it is covered by the same single `--approved-by`
  sign-off as everything else. Splitting it is a product decision about who in
  an organization may say "we cannot answer this", not an implementation
  detail, and it is not made here.
- Authoring requirement documents for any funder, and judging whether a reason
  is adequate. Neither is a thing software should do.
- #158's definition packs. A pack says what a metric *means*; this says whether
  it was *answered*.
