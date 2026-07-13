# Record architecture decisions

- Status: Accepted
- Date: 2026-07-12
- Deciders: Chelsea Kelly-Reif

## Context

Architectural and guardrail decisions were originally recorded under
`docs/decisions/`. The portfolio documentation standard now names `docs/adr/` as
the canonical append-only log and requires sequential MADR records.

## Decision

New decisions use `docs/adr/NNNN-kebab-title.md`, starting with this meta-ADR.
Each record states Status, Date, Deciders, Context, Decision, and Consequences.
Accepted records are superseded by a later record and are not silently rewritten.
The files under `docs/decisions/` remain as the read-only pre-migration history.

## Consequences

Reviewers have one canonical location for new decisions. Historic links remain
valid, and the migration does not rewrite prior reasoning.
