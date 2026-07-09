# Project Scope

Last reviewed: 2026-07-08. Base branch: `main`.

This file is a plain-language map of the project as it exists on `main`. It does not replace the README, roadmap, audit docs, or source comments. It points to them so a reviewer can see the whole shape without reading every file first.

## What This Project Is

Outcome Receipts creates grounded reports from service data. It connects narrative claims, charts, definitions, comparisons, and provenance so readers can trace where each number came from.

Package metadata checked in this pass:

- Python package `outcome-receipts` for Python `>=3.12`.

## Who It Serves

- Nonprofits writing grant, board, or impact reports from service CSVs.
- Funders and reviewers who want numbers tied back to definitions and source data.
- Maintainers building no-model reporting workflows with verifiable outputs.

## What It Covers

- A Python library and CLI for report config, drafting, charts, comparisons, provenance, trace, and verification.
- Examples for board, grant, and housing reports.
- Docs for roadmap, user research, decisions, audits, and I18N.
- Evaluation reports and tests for definitions, grounding, traces, reports, and verification.
- Config-driven receipts that can be checked after generation.

## How It Is Put Together

- src/outcome_receipts/ contains engine, config, charts, draft, provenance, trace, report, and verify code.
- examples/ contains small report inputs.
- docs/decisions/ records grounding, templates, comparison, and trace choices.
- eval/ contains report material.
- tests/ checks the report and verification behavior.

Observed source and operations surfaces:

- `Makefile`
- `eval/`
- `pyproject.toml`
- `src/`

GitHub workflow files checked:

- `.github/workflows/ci.yml`
- `.github/workflows/release.yml`

## Trust Boundaries

- Claims should be tied to source rows, definitions, and transformations.
- The project is careful about saying when a number comes from data rather than a model.
- Verification is part of the output contract, so reports can be checked later.

## Outside This Scope

- It does not decide whether a program worked.
- It cannot fix bad source data or missing definitions.
- Human sign-off is still needed before sending a report to funders or a board.

## Docs And Evidence Checked

This pass checked 21 hand-authored doc or metadata files, 18 test files, and 2 workflow files on `main`. The count excludes vendored provider licenses, dependency folders, generated cache files, and large generated artifact history.

Primary docs checked:

- `CHANGELOG.md`
- `CITATION.cff`
- `CLAUDE.md`
- `CODE_OF_CONDUCT.md`
- `CONTRIBUTING.md`
- `LICENSE`
- `NOTICE`
- `README.md`
- `SECURITY.md`
- `docs/I18N.md`
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

Representative test files checked:

- `tests/test_charts.py`
- `tests/test_comparison.py`
- `tests/test_config_sections.py`
- `tests/test_data_checks.py`
- `tests/test_definition.py`
- `tests/test_draft_and_config.py`
- `tests/test_engine.py`
- `tests/test_evaluate.py`
- `tests/test_grounded_sections.py`
- `tests/test_grounding_gate.py`
- `tests/test_grounding_locale.py`
- `tests/test_kind.py`
- `tests/test_ledger.py`
- `tests/test_provenance.py`
- `tests/test_report_sections.py`
- `tests/test_scaffold.py`
- `tests/test_trace.py`
- `tests/test_verify.py`

## Validation Notes

For this docs PR, validation means the scope file was generated from the clean `origin/main` worktree, reviewed against repo metadata and docs inventory, and checked with `git diff --check`. Project test suites are still the authority for code behavior, because this PR changes documentation only.
