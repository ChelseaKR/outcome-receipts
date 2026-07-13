# Keep the enforced pull-request approval count at zero for one maintainer

- Status: Accepted
- Date: 2026-07-12
- Deciders: Chelsea Kelly-Reif

## Context

The portfolio standard calls for an approving review on main. This repository has
one active maintainer, and GitHub does not count an author's approval of their own
pull request. Setting the ruleset count to one would make every maintainer-authored
change unmergeable rather than create an independent review.

## Decision

The ruleset requires a pull request, resolved review threads, signed linear
history, an up-to-date branch, and every applicable automated check, but records
`required_approving_review_count: 0` and no code-owner approval. The maintainer
records the self-review with the pull-request Definition of Done checklist.

When a second active maintainer is available, a new ADR must supersede this one
and raise the live and committed review count to one before that maintainer's
changes are relied on as an independent review.

## Consequences

Direct pushes are structurally blocked and review evidence is explicit, but the
independence objective remains unmet for maintainer-authored work. The portfolio
unreviewed-merge metric remains an honest risk signal rather than being disguised
as an approval that GitHub cannot enforce.
