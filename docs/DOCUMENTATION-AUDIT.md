# Documentation Audit

Last reviewed: 2026-07-08. Base branch: `main`.

This audit records the documentation sweep and remediation loop for this repository. It checks the docs as a system: entry points, root-level process and legal files, project scope, setup and validation notes, safety and privacy posture, architecture and planning docs, local links, and the places where code, tests, workflows, and docs meet.

## Audit Results

| Area | Result | Evidence |
| --- | --- | --- |
| Entry docs | pass | `README.md` present |
| Security/process docs | pass | CONTRIBUTING.md, SECURITY.md, CHANGELOG.md |
| Architecture/planning docs | pass | 1 architecture/interface docs; 3 planning/research docs |
| Safety/privacy/audit docs | pass | 3 safety/privacy/accessibility/audit docs |
| Validation surface | pass | 18 test files; 2 workflow files |
| Local doc links | pass | 106 authored-doc links checked; 0 unresolved |

## Root-Level Documentation Audit

This section covers hand-authored documentation at the repository root and root-adjacent GitHub templates. It is separate from the `docs/` inventory so README, process, legal, release, and project-specific root files do not get hidden inside the larger docs tree.

| Surface | Result | Evidence |
| --- | --- | --- |
| Root README | pass | Present: `README.md` |
| Root process docs | pass | Present: `CONTRIBUTING.md`, `SECURITY.md`, `CHANGELOG.md` |
| Root legal, citation, and conduct docs | pass | Present: `LICENSE`, `NOTICE`, `CITATION.cff`, `CODE_OF_CONDUCT.md` |
| Other root project docs | info | `CLAUDE.md` |
| Root-adjacent GitHub templates | pass | `.github/CODEOWNERS` |
| Root/template doc links | pass | 26 root-level/template links checked; 0 unresolved |

Root-level files checked:

- `CHANGELOG.md`
- `CITATION.cff`
- `CLAUDE.md`
- `CODE_OF_CONDUCT.md`
- `CONTRIBUTING.md`
- `LICENSE`
- `NOTICE`
- `README.md`
- `SECURITY.md`

Root-adjacent template files checked:

- `.github/CODEOWNERS`

## Remediation In This PR

- No missing root-level docs were found (README, process, legal, citation, and conduct files are all present), so none were added.
- Added `docs/PROJECT-SCOPE.md` as the plain-language project and boundary map.
- Added this audit record so future doc changes have a dated baseline.
- Added or refreshed the docs index so scope, audit, and primary docs are easy to find.

## Repo Surfaces Checked

Package and workspace metadata:

- Python package `outcome-receipts` (>=3.12).

Source and operations surfaces seen at the repo root:

- `eval/`
- `Makefile`
- `pyproject.toml`
- `src/`
- `tests/`
- `uv.lock`

Workflow files checked:

- `.github/workflows/ci.yml`
- `.github/workflows/release.yml`

## Documentation Inventory

| Category | Count | Representative files |
| --- | ---: | --- |
| architecture and interfaces | 1 | `docs/decisions/0000-record-architecture-decisions.md` |
| entry points and repo process | 9 | `.github/CODEOWNERS`, `CHANGELOG.md`, `CITATION.cff`, `CODE_OF_CONDUCT.md`, `CONTRIBUTING.md`, `LICENSE`, `NOTICE`, `README.md`, plus 1 more |
| other docs | 9 | `CLAUDE.md`, `docs/I18N.md`, `docs/PROJECT-SCOPE.md`, `docs/README.md`, `docs/decisions/0001-engine-receipts-grounding.md`, `docs/decisions/0002-templates-charts-comparison.md`, `docs/decisions/0003-definitions-provenance-trace-verify.md`, `docs/decisions/0004-hash-chained-export-ledger.md`, plus 1 more |
| planning and research | 3 | `docs/RESEARCH-ROADMAP.md`, `docs/ROADMAP.md`, `docs/USER-RESEARCH.md` |
| safety, privacy, accessibility, and audits | 3 | `docs/DOCUMENTATION-AUDIT.md`, `docs/RESPONSIBLE-TECH-AUDITS.md`, `docs/THREAT-MODEL.md` |

Full hand-authored doc inventory checked by this pass:

- `.github/CODEOWNERS`
- `CHANGELOG.md`
- `CITATION.cff`
- `CLAUDE.md`
- `CODE_OF_CONDUCT.md`
- `CONTRIBUTING.md`
- `LICENSE`
- `NOTICE`
- `README.md`
- `SECURITY.md`
- `docs/DOCUMENTATION-AUDIT.md`
- `docs/I18N.md`
- `docs/PROJECT-SCOPE.md`
- `docs/README.md`
- `docs/RESEARCH-ROADMAP.md`
- `docs/RESPONSIBLE-TECH-AUDITS.md`
- `docs/ROADMAP.md`
- `docs/THREAT-MODEL.md`
- `docs/USER-RESEARCH.md`
- `docs/decisions/0000-record-architecture-decisions.md`
- `docs/decisions/0001-engine-receipts-grounding.md`
- `docs/decisions/0002-templates-charts-comparison.md`
- `docs/decisions/0003-definitions-provenance-trace-verify.md`
- `docs/decisions/0004-hash-chained-export-ledger.md`
- `eval/report.md`

## Link Check

- Checked 106 local links in authored Markdown and MDX docs.
- Unresolved authored-doc links after remediation: 0.
- Root-level/template unresolved links after remediation: 0.

## Validation Notes

- The audit was generated from a clean worktree based on `origin/main` for this PR branch.
- Ran a local relative-link check over hand-authored Markdown and MDX docs.
- Ran an explicit root-level documentation presence and link check for README, process, legal, project, and template docs.
- Ran `git diff --check` across the PR worktrees after remediation.
- Product test suites remain the authority for runtime behavior; this PR changes documentation only.
