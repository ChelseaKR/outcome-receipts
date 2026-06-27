# 0001 — Engine, receipts, and the grounding gate

Status: accepted (v0.1)

## Context

The project's promise is that every number in a report traces to the data, and an
invented number is caught before export. v0.1 has to make that promise real with
the least-risky parts: no language model, a deterministic engine, and a gate that
is mechanical rather than judgmental. Three decisions set the shape.

## Decisions

### The engine is SQLite over the standard library

A metric is a SQL query; the value comes from running it. v0.1 loads the service
data into an in-memory SQLite database, which is in the Python standard library,
so the deterministic core has zero third-party dependencies. SQL is the honest
form of "a deterministic query," it is auditable in the receipt, and SQLite is
deterministic and ubiquitous. DuckDB or pandas would add capability and weight;
the open question of moving to DuckDB for larger or columnar data is recorded in
CLAUDE.md and deferred until a real dataset needs it. All columns load as text and
the metric SQL casts where it needs a number, which keeps loading deterministic.

### A receipt is the unit of trust

Each figure carries a `Receipt`: the exact value query, the count of rows in its
slice, a BLAKE2b hash of those rows, the value, the unit, and a timestamp. The
slice hash is computed over the canonicalized, sorted rows, so the same data
reproduces the same receipt regardless of row order, and a changed slice is
detectable. The timestamp comes from an injected clock (a fixed clock for the
committed eval) so a run is reproducible and CI can regenerate-and-diff the eval,
the same discipline the sibling constituent-reconciler project uses for its
provenance timestamps.

### The grounding gate operates on numeric spans, not on judgment

The gate finds every number in the narrative with a regex and binds each to a
figure whose display string matches (after normalizing thousands separators). A
span that matches no figure is unbound and blocks export. The gate does not ask a
model whether the narrative "looks faithful"; it checks that each number traces to
a receipt. This is what lets a model draft the prose in a later version without
being trusted to invent figures: whatever it writes, the gate is the enforcement.

The gate is deliberately strict. A number that is not a figure — a stray year, a
list marker — is unbound and must be removed or made into a figure. The cost is
that prose cannot contain incidental numbers; the benefit is that there is no
gray area in which an invented number could pass.

## Consequences

- The deterministic core has no third-party runtime dependency.
- Figures are reproducible and auditable; a receipts manifest ships with every
  export.
- Display formatting is part of the figure, because the gate matches on the
  display string; a figure has one canonical rendering, set by its unit and
  decimals.
- The strict gate means report templates avoid incidental numbers; this is a
  documented constraint, not a bug.
- Moving the engine to DuckDB later is possible behind the same `MetricSpec`
  surface; it would be a new ADR.
