# Validate committed example manifests against the published schema, and warn on a 1.0 withheld figure

- Status: Proposed
- Date: 2026-09-13
- Deciders: Chelsea Kelly-Reif

## Context

`examples/housing-demo/receipts.json` is the manifest the `dogfood-action` job
verifies the reusable action against, and the sdist ships it. Manifest schema
2.0 writes a figure withheld by small-cell suppression as `suppressed: true`
with `null` for `value`, `row_count`, `slice_hash` and `column_names`, because
schema 1.0 wrote zeros there and a reader could not tell a withheld cell from a
true zero ([ADR 0009](../decisions/0009-withheld-cells-are-null-not-zero.md)).
The example was last written on 2026-07-11, under 1.0, and was not regenerated
when 2.0 shipped. It published three withheld figures as `value: 0.0` and
`row_count: 0`, failed `docs/schema/receipts.schema.json` with five errors, and
went out in the `0.2.2` sdist, while every required check stayed green (#198).

Two gaps let that happen. Nothing validated a committed manifest against the
published schema: `receipts verify` re-derives figures, and the structural
validator in `tests/test_manifest_schema.py` checks only manifests the tests
emit themselves. And `receipts verify` reported a 1.0 withheld receipt as
`[ok] re-derived, matches`, which is true of the placeholders and silent about
what they hide.

Two existing commitments bound the remedy.
[`docs/decisions/0005`](../decisions/0005-receipt-canonicalization-and-schema.md)
keeps `jsonschema` out of the project environment to hold the
zero-runtime-dependency posture. [`docs/SPEC-STABILITY.md`](../SPEC-STABILITY.md)
promises that `receipts verify` reads manifest schema 1.0.

## Decision

**A gate validates every committed example manifest.** `make example-manifests`
is a `VERIFY_GATES` entry, so it runs inside the existing `verify` job and adds
no status context. It runs `scripts/check_example_manifests.py` with a real
Draft 2020-12 validator: `jsonschema`, pinned to an exact version and supplied by
`uv run --isolated --no-project --with`, which is how the Semgrep and zizmor
gates already run tools that are not project dependencies. `uv.lock` and the
project environment are unchanged. The gate discovers manifests under
`examples/` instead of reading a list, prints how many it validated and how many
are committed, and fails when those differ or when it found none.

**`receipts verify` warns, and does not fail, on a 1.0 withheld figure that
carries numbers.** A receipt with no `suppressed` key, a display of
`[SUPPRESSED]`, and a number in `value` or `row_count` (or a `slice_hash`)
produces a `VerifyWarning`. Warnings print as `[warn]` lines and appear in
`--json` output as `warnings`. They never enter `VerifyResult.ok`, so the exit
code does not change for any input.

## Consequences

The gate adds a narrow dependency boundary. It fetches `jsonschema` and its
dependencies when it runs, so `make verify` needs network for it as it already
does for Semgrep, and those transitive dependencies are pinned by name and
version of the top-level package only. Nothing a user installs changes.

The frozen compatibility baselines under `tests/fixtures/compat/` are outside
the gate's scope and stay at 1.0. The gate covers manifests committed to this
repository. A downstream user's manifest is still not validated against the
schema by anything this project ships.

Every manifest written by `v0.1.0` or `v0.2.0` that withholds a cell now prints
warnings when verified with a CLI carrying this change. The reusable action's
default `version: v0.2.0` does not carry it. Whether the warning should become a
failure, behind an opt-in flag first or by default at 1.0.0, is left open.
Failing by default would turn existing green runs red with no change to their
data and would contradict `SPEC-STABILITY.md` and ADR 0009, so it needs its own
decision.

The 1.0 copy of the example inside the published `0.2.2` sdist cannot be
changed. Only a new release replaces it.
