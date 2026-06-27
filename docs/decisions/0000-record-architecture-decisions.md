# 0000 — Record architecture decisions

Status: accepted

## Context

We need a durable record of the architectural decisions on this project: what was
decided, why, and what it commits us to. Without one, the reasoning lives only in
commit messages and memory, and gets relitigated.

## Decision

We keep an Architecture Decision Record log in `docs/decisions/`, in the MADR
style. Each record is a numbered Markdown file (`NNNN-kebab-title.md`), sequential
and immutable once accepted: a later decision that changes an earlier one is a new
record that supersedes it, not an edit. Each record states Status, Context,
Decision, and Consequences.

A new ADR is expected for a decision that changes a public surface, a dependency
of consequence, a data or privacy boundary, or the meaning of a core invariant.

## Consequences

- The log is the first place to look for why something is the way it is.
- Accepted records are not edited; they are superseded, so history stays honest.
