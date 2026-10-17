# Accept the v0.2.0 and v0.2.1 release gaps as history, and exempt only them

- Status: Accepted
- Date: 2026-10-17
- Deciders: Chelsea Kelly-Reif

## Context

`.github/workflows/release-reality.yml` runs `scripts/check_release_reality.py`
weekly and follows each release across three links: a dated changelog section
has a tag, a stable tag has a published GitHub release, and a published
release's version is on PyPI. It has been red on every scheduled run since it
landed (the most recent on 2026-10-12, at `63c660a`). Measured against the live
GitHub and PyPI APIs on 2026-10-17, two breaks keep it red, and neither can be
repaired:

| Version | Link it fails | What happened |
|---|---|---|
| `0.2.0` | a published release is on the index | Release run 31955281617 (2026-08-16) passed `authorize`, `verify`, `build` and `github-release`, so `v0.2.0` is a published GitHub release with five assets. `pypi-publish` then waited at the `pypi` environment's required review and was canceled on 2026-08-29, with `verify-published`. The PyPI simple API and `https://pypi.org/pypi/outcome-receipts/json` list `0.1.0` and `0.2.2` and no `0.2.0`. |
| `0.2.1` | a stable tag has a published release | The signed `v0.2.1` tag names `dae3e8e`, where `pyproject.toml` reads `0.2.0` and `CHANGELOG.md` has no `[0.2.1]` section. No release run for it got past its gates, so no GitHub release exists for it and it is not on PyPI. |

`0.2.0` cannot be republished: its tagged tree pins a base image whose own
`verify` job now refuses it, and the fix for that is a new version, which
`0.2.2` was. `0.2.1` could only be made coherent by moving a published tag onto
a tree it was not cut from, which `docs/RELEASING.md` forbids. Both are already
recorded as history in the `CHANGELOG.md` preamble and the README status note.

A check that is red for a reason nobody can act on stops being read, and the
next real stall would arrive into a job that has been failing for months.

## Decision

`scripts/check_release_reality.py` carries a committed, dated exemption list,
`EXEMPTIONS`, with exactly two entries:

- `0.2.0`, exempt from the link "a published release is on the index" only.
- `0.2.1`, exempt from the link "a stable tag has a published release" only.

Each entry names its version, the one link it is exempt from, the date of this
decision, and this ADR. An exemption matches on the version and the link
together. The same version breaking a different link still fails, and any
other version breaking the same link still fails. An exempted break is not
counted as a link that held: each link still prints `N of M` over everything it
examined, and the exempted versions are named on that line, so the run says
what it is excusing every time it runs.

The list is closed. Adding an entry needs a new ADR that names the version, the
link, and why the gap cannot be repaired; a release that stalls today gets
repaired by cutting a new version, not exempted.

## Consequences

The weekly run can go green with the live state as it is on 2026-10-17, and a
new stall at any link is reported as before.

It will be red between a release PR merging and that release reaching PyPI,
because the dated changelog section exists before its tag does. That is the
check doing its job; it stays red until the tag, the dispatch and the PyPI
approval in `docs/RELEASING.md` are all done.

If either gap is ever repaired (a `0.2.0` upload, a `v0.2.1` release), its
exemption stops matching anything and does no harm, but it should be removed in
a later change that cites this record. Nothing enforces that removal.
