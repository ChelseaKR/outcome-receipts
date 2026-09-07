# 0012 — A comparative claim binds to a receipted direction, or it blocks

Status: accepted. Extends ADR 0007, which sets the matching policy for numbers,
to the class of quantitative claim that carries no number at all.

## Context

The grounding gate finds numbers. ADR 0007 fixes how a numeric span is matched,
and `grounding._NUMBER_WORD` closes the spelling evasion by detecting a written-out
numeral and always leaving it unbound. A sentence containing no numeral is invisible
to all of it.

"Placements rose this quarter", "outcomes improved", "most clients exited to
permanent housing" are quantitative claims. Before this decision they blocked
nothing. The invariant the project sells is that numbers never come from a model,
and the optional Bedrock drafter ships behind two explicit opt-ins: a drafter
forbidden to invent a digit was not forbidden to invent a direction, and a funder
reading "rose" does not read it as prose.

The tool already treats direction as load-bearing everywhere else.
`comparison.ComparisonRow.direction` is `increase` / `decrease` / `no change`,
derived from the sign of a delta a single SQL statement produced. Issue #75 was the
suppression leak in which the comparison table's direction word recovered both
hidden periods, and `suppression._redact_row_direction` exists because of it. The
narrative was the one surface where the same words were unread.

## Decision

A closed, bilingual vocabulary of comparative and quantifying forms is detected in
the drafted narrative. Each detected claim resolves to one of four states, and three
of them block export exactly as an unbound number does.

**`bound`** — the claim asserts a direction, and some declared comparison or
reconciliation row's own `direction` agrees with it.

**`contradicted`** — the claim asserts a direction and every declared row says
otherwise. The message names both the claim and what the receipts say, because
"unbound" alone would send the author looking for a missing metric rather than at a
sentence that is false.

**`unbound`** — either the spec declares no comparison at all, or the claim is of a
kind that can never bind (below).

**`disclosed`** — the claim agrees with a row suppression withheld. Reported as a
disclosure and not as unbound, for the reason `grounding.audit_narrative` separates a
number that states a redacted cell: the two need different remedies, and this one is
a privacy finding. The withheld set is tested first, which is the fail-closed
ordering `audit_narrative` already uses.

### Four kinds are detected and can never bind

This is the `_NUMBER_WORD` precedent rather than an omission. Each asserts something
no receipt in this system carries.

`evaluative` — "improved", "worsened". A direction word becomes a valuation only once
you know whether up is good for the metric, and **a spec declares no polarity.**
"Improved" over a length-of-stay metric means a decrease; over a placements metric it
means an increase. Binding it to either would be the gate inventing the thing it
exists to check.

`magnitude` — "doubled", "halved". These assert a ratio, and there is no receipted
ratio. `compute_reconciliation` deliberately refuses to compute cost-per-outcome for
exactly this reason: the receipt's slice cannot be a well-formed union of two
differently shaped row sets. A ratio the system will not compute is not one it can
check.

`proportion` — "most", "nearly all", "few". A share of a whole. Figures are counts,
rates and money; none of them is a proportion-of-total.

`rank` — "highest", "lowest". A position in an ordering over a set the gate does not
model. Two periods are not a ranking.

### Scope

The gate runs over the drafted narratives — the one surface a model writes. A
metric's author-written `caveat` is not drafted and is not gated here; the committed
examples all use the word "dropped" in a caveat, and gating that string would refuse
every example on prose nobody generated.

The CLI (`receipts run`, `receipts audit`) and the MCP `audit_narrative` tool answer
from the same computation and emit the same payload. A drafting tool told over MCP
that a narrative is clean while the CLI would refuse to export it is the drift
`tests/test_mcp_server.py` exists to prevent, and that test caught this change
before the payloads could diverge.

## Consequences

**A false positive is a rephrase, and it is the accepted direction.** "Declined"
means both *fell* and *refused*, and "12 clients declined services" is ordinary prose
in this domain. It is detected as a decrease claim and must be reworded. That matches
a gate which already blocks a stray "2024": the author is told the exact word and
offset, and rewording is cheap where a false negative is a published claim nobody
checked.

**Every comparison row in the committed grant-report example is withheld**, because
each delta is smaller than the suppression threshold and complementary suppression
takes a period figure with it. `_redact_row_direction` therefore renders the whole
direction column as the sentinel, so the report already declines to say which way
anything moved — and until now a sentence could have said it anyway. Under this
decision such a sentence is a disclosure. This is the #75 leak arriving through
prose, and it is measured rather than hypothetical.

**Binding is report-wide, not per sentence.** A claim binds when *some* declared row
agrees, which is what issue #174 specifies. Tying a claim to the metric its own
sentence is about would be a stronger gate; it needs to know which sentence is about
which metric, and every disagreeing row is named in the explanation so the gap is
visible rather than hidden.

**A narrative with no vocabulary entry gates exactly as before.** The compat
fixtures and every committed example are unaffected, which is asserted rather than
assumed.

## What this does not decide

Issue #174 asks whether an unrecognized evaluative sentence — "outcomes were
encouraging" — should block, warn, or pass. It passes, as it does today, because a
vocabulary that cannot be complete makes an unpredictable gate and this decision
does not widen the refusal surface beyond forms that are enumerated. The third
answer in that issue, where the gate lists such sentences and the named approver
acknowledges them before export, is a product judgement and remains open.
