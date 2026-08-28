"""Regression tests for repository-local conformance validation."""

from __future__ import annotations

import json
import re
import shutil
import tempfile
from datetime import date
from pathlib import Path

import pytest
from scripts.check_conformance import (
    FALLBACK_STANDARDS,
    StandardsIndexError,
    _readme_standards_rows,
    _standards_table_failures,
    action_default_failures,
    benchmark_claim_failures,
    doc_staleness_failures,
    schema_version_failures,
    security_declaration_failures,
    standards_index,
    waiver_failures,
)

# A frozen, verbatim copy of the 15 standard-registry lines from the portfolio
# standards repo's controls.yml. This is what a real `--standards-dir` checkout
# looks like; the test below proves the vendored FALLBACK_STANDARDS literal
# (used by the self-contained `make verify`) agrees with it.
#
# It is not a snapshot of the version this repository pins, and saying so would
# be worse than saying nothing. `.standards-version` pins v1.0.1, and
# controls.yml did not exist yet at v1.0.1; it arrived with FIX-01 on
# 2026-07-11. So this snapshot is of a later registry than the pin names, and
# the consequence is worth stating where a reader will meet it: the "portfolio
# standards" CI job checks the pinned ref out and runs
# `check_conformance.py --standards-dir .standards` against it, that checkout
# has no controls.yml, and `standards_index` therefore warns and falls back to
# the vendored literal. The job passes in a few seconds having compared the
# README against the same hardcoded list DOC-11 set out to stop trusting.
#
# Nothing is currently checking either copy against a live registry. This test
# compares two copies in this repository, which catches an edit to one of them
# and nothing else, and that is all it can claim. The live cross-check starts
# working when `.standards-version` moves to a version that carries
# controls.yml, which is a deliberate portfolio-pin decision with repository-wide
# scope, recorded in `standards_index`'s own warning text rather than made here.
# `test_the_standards_pin_is_named_the_same_way_in_all_three_places` below keeps
# the pin's three copies from drifting in the meantime.
_CONTROLS_YML_STANDARDS_SNAPSHOT = """
standards:
  CQ:   { file: CODE-QUALITY-STANDARD.md,            title: "Code Quality Standard" }
  SEC:  { file: SECURITY-AND-SUPPLY-CHAIN-STANDARD.md, title: "Security & Supply-Chain Standard" }
  CICD: { file: CI-CD-STANDARD.md,                   title: "CI/CD Standard" }
  OBS:  { file: OBSERVABILITY-STANDARD.md,           title: "Observability Standard" }
  A11Y: { file: ACCESSIBILITY-STANDARD.md,           title: "Accessibility Standard" }
  I18N: { file: INTERNATIONALIZATION-STANDARD.md,    title: "Internationalization & Localization Standard" }
  AIEV: { file: AI-EVALUATION-STANDARD.md,           title: "AI Evaluation Standard" }
  QM:   { file: QUALITY-AND-METRICS-STANDARD.md,     title: "Quality & Metrics Standard" }
  DOC:  { file: DOCUMENTATION-STANDARD.md,           title: "Documentation Standard" }
  REL:  { file: RELEASE-AND-VERSIONING-STANDARD.md,  title: "Release & Versioning Standard" }
  RTF:  { file: RESPONSIBLE-TECH-FRAMEWORK.md,       title: "Responsible-Tech Framework" }
  PERF: { file: PERFORMANCE-STANDARD.md,             title: "Performance Standard" }
  IR:   { file: INCIDENT-RESPONSE-STANDARD.md,       title: "Incident Response Standard" }
  DG:   { file: DATA-GOVERNANCE-STANDARD.md,         title: "Data Governance Standard" }
  ADM:  { file: AI-DEVELOPMENT-MEASUREMENT-STANDARD.md, title: "AI-Development Measurement Standard" }
"""


def test_waiver_registry_accepts_a_current_complete_entry(tmp_path: Path) -> None:
    registry = tmp_path / "waivers.yml"
    registry.write_text(
        """version: 1

waivers:
  - id: WVR-950
    control: SEC-10
    repo: outcome-receipts
    kind: other
    reason: deterministic test fixture
    owner: maintainer
    granted: 2099-01-01
    expires: 2099-02-01
""",
        encoding="utf-8",
    )

    assert waiver_failures(registry) == []


def test_waiver_registry_reports_a_wrong_top_level_key(tmp_path: Path) -> None:
    # `waiverz` (not `waivers`) is a schema violation on its own: the whole
    # document declares no waivers as far as the schema is concerned, so
    # nothing under the misspelled key is read as an entry at all -- that is
    # a second, independent way this document is wrong, not a reason to
    # expect per-entry checks below to somehow still run on it.
    registry = tmp_path / "waivers.yml"
    registry.write_text(
        """version: 2

waiverz:
  - id: WVR-951
    control: SEC-10
    repo: outcome-receipts
    kind: other
    reason: seeded fixture
    owner: maintainer
    granted: 2099-01-01
    expires: 2099-02-01
""",
        encoding="utf-8",
    )

    failures = waiver_failures(registry)
    assert failures == [
        "waiver registry must declare version: 1",
        "waiver registry must declare waivers",
    ]


def test_waiver_registry_reports_dates_and_duplicates(tmp_path: Path) -> None:
    registry = tmp_path / "waivers.yml"
    registry.write_text(
        """version: 1

waivers:
  - id: WVR-952
    control: SEC-10
    repo: outcome-receipts
    kind: other
    reason: first fixture
    owner: maintainer
    granted: not-a-date
    expires: 2000-01-01
  - id: WVR-952
    control: SEC-10
    repo: outcome-receipts
    kind: other
    reason: second fixture
    owner: maintainer
    granted: 2099-02-01
    expires: 2099-01-01
""",
        encoding="utf-8",
    )

    failures = waiver_failures(registry)
    assert "WVR-952: invalid granted date" in failures
    assert "WVR-952: expired" in failures
    assert "duplicate waiver id: WVR-952" in failures
    assert "WVR-952: expiry precedes granted date" in failures


# ---------------------------------------------------------------------------
# DOC-11: the standards index must be derived, not duplicated (issue 98).
# ---------------------------------------------------------------------------


def test_standards_index_defaults_to_the_vendored_fallback_when_unpinned() -> None:
    assert standards_index(None) == FALLBACK_STANDARDS
    # Not a tautology by construction: the fallback set only matches the
    # pinned portfolio index because the next test proves it against a frozen
    # copy of the real registry, not because this test invented its own copy.


def test_standards_index_derives_from_a_pinned_checkouts_controls_yml(tmp_path: Path) -> None:
    (tmp_path / "controls.yml").write_text(_CONTROLS_YML_STANDARDS_SNAPSHOT, encoding="utf-8")

    assert standards_index(tmp_path) == FALLBACK_STANDARDS


def test_fallback_standards_literal_matches_a_frozen_snapshot_of_the_pinned_index() -> None:
    # Restates the above from the other direction: the vendored fallback list
    # is not free-standing prose, it is required to equal what a real
    # controls.yml derives to. If the portfolio index ever adds, renames, or
    # retires a standard, this snapshot (and FALLBACK_STANDARDS) need a
    # deliberate update.
    #
    # Both copies live in this repository, so this catches an edit to one of
    # them and cannot catch the portfolio registry moving underneath both. See
    # the note on _CONTROLS_YML_STANDARDS_SNAPSHOT: the job that was meant to
    # make that comparison live runs against a pinned checkout with no
    # controls.yml.
    assert len(FALLBACK_STANDARDS) == 15
    assert {
        "Code Quality",
        "Security & Supply-Chain",
        "CI/CD",
        "Observability",
        "Accessibility",
        "Internationalization & Localization",
        "AI Evaluation",
        "Quality & Metrics",
        "Documentation",
        "Release & Versioning",
        "Responsible-Tech Framework",
        "Performance",
        "Incident Response",
        "Data Governance",
        "AI-Development Measurement",
    } == FALLBACK_STANDARDS


def test_standards_index_fails_loudly_when_the_pinned_checkout_is_missing(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist"

    with pytest.raises(StandardsIndexError, match="does not exist"):
        standards_index(missing)


def test_standards_index_fails_loudly_when_controls_yml_has_no_standards(
    tmp_path: Path,
) -> None:
    (tmp_path / "controls.yml").write_text("version: 1\nsomething: else\n", encoding="utf-8")

    with pytest.raises(StandardsIndexError, match="no standard entries"):
        standards_index(tmp_path)


def test_standards_index_falls_back_with_a_warning_when_checkout_predates_controls_yml(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # This is this repository's actual live state: `.standards-version` is
    # pinned to v1.0.1, and controls.yml was not added to the standards repo
    # until FIX-01, after that tag. A present-but-older checkout is not the
    # same failure as a missing one -- it should not turn CI red for a
    # pin-staleness gap this change did not set out to fix, but it must not
    # be silent about it either.
    empty_checkout = tmp_path / "standards-checkout-without-controls-yml"
    empty_checkout.mkdir()
    (empty_checkout / "SECURITY-AND-SUPPLY-CHAIN-STANDARD.md").write_text("stub", encoding="utf-8")

    result = standards_index(empty_checkout)

    assert result == FALLBACK_STANDARDS
    warning = capsys.readouterr().err
    assert "predates FIX-01" in warning
    assert "Falling back to the vendored standards list" in warning


def test_readme_standards_rows_ignores_unrelated_tables_in_the_document() -> None:
    readme = """\
## Usage

| Code | Meaning |
| ---- | ------- |
| 0 | Success |
| 1 | Failure |

## Standards conformance

| Standard | State |
|----------|-------|
| Code Quality | Applies |
| Security & Supply-Chain | Applies |

## License
"""
    rows = _readme_standards_rows(readme)

    assert rows == {"Code Quality": "Applies", "Security & Supply-Chain": "Applies"}
    assert "0" not in rows and "1" not in rows and "Standard" not in rows


def test_standards_table_failures_flags_a_missing_row() -> None:
    failures = _standards_table_failures(
        {"Code Quality": "Applies"}, {"Code Quality", "Observability"}
    )

    assert "README conformance row missing: Observability" in failures


def test_standards_table_failures_flags_an_open_or_na_row() -> None:
    rows = {"Code Quality": "N/A", "Observability": "Open: pending decision"}
    failures = _standards_table_failures(rows, {"Code Quality", "Observability"})

    assert "README conformance row is not closed: Code Quality: N/A" in failures
    assert "README conformance row is not closed: Observability: Open: pending decision" in failures


def test_standards_table_failures_flags_a_row_not_in_the_index() -> None:
    rows = {"Code Quality": "Applies", "Retired Standard": "Applies"}
    failures = _standards_table_failures(rows, {"Code Quality"})

    assert any("Retired Standard" in failure for failure in failures)


def test_standards_table_failures_flags_a_row_count_mismatch() -> None:
    # Two rows recorded, but the index only names one standard: a duplicate
    # or stray row would otherwise slip past the per-standard checks above,
    # which only ever look up names the index already expects.
    rows = {"Code Quality": "Applies", "Code Quality ": "Applies"}
    failures = _standards_table_failures(rows, {"Code Quality"})

    assert any("2 row(s)" in failure and "1 standard(s)" in failure for failure in failures)


def test_standards_table_failures_is_silent_when_everything_matches() -> None:
    rows = {"Code Quality": "Applies", "Observability": "Applies"}
    assert _standards_table_failures(rows, {"Code Quality", "Observability"}) == []


# ---------------------------------------------------------------------------
# Issue 97: the waiver lint could not see an empty folded reason, an
# invented kind, or an invented control. Each rotten shape below is seeded
# on its own (so a failing assertion names exactly which rule broke) and
# then together in one registry, mirroring tests/test_npm_audit_gate.py's
# style of proving both what the gate accepts and what it refuses.
# ---------------------------------------------------------------------------


def _registry(tmp_path: Path, body: str) -> Path:
    registry = tmp_path / "waivers.yml"
    registry.write_text(f"version: 1\n\nwaivers:\n{body}", encoding="utf-8")
    return registry


def test_waiver_registry_accepts_a_real_folded_reason(tmp_path: Path) -> None:
    # Every entry in the live waivers.yml folds its reason across several
    # lines with `>-`. This is the shape the previous single-line-regex
    # parser could not read correctly (see the next test); this one proves
    # a *real*, non-empty folded reason is captured and accepted, not just
    # that an empty one is rejected.
    registry = _registry(
        tmp_path,
        """  - id: WVR-100
    control: SEC-10
    repo: outcome-receipts
    kind: other
    reason: >-
      This reason spans multiple folded lines, exactly like every entry in
      the committed registry, and should be read as one non-empty string.
    owner: maintainer
    granted: 2099-01-01
    expires: 2099-02-01
""",
    )

    assert waiver_failures(registry) == []


def test_waiver_registry_rejects_an_empty_folded_reason() -> None:
    # The bug this fixes directly: the old single-line regex captured the
    # `>-` folded-scalar indicator itself as the field's "value", so
    # `reason: >-` (immediately followed by nothing, or by non-indented
    # content) registered as a non-empty string and the "missing or empty
    # reason" rule was unenforceable against the shape every real entry uses.
    from scripts.check_conformance import _parse_waiver_entries

    entries = _parse_waiver_entries(
        """version: 1

waivers:
  - id: WVR-101
    control: SEC-10
    repo: outcome-receipts
    kind: other
    reason: >-
    owner: maintainer
    granted: 2099-01-01
    expires: 2099-02-01
"""
    )
    assert entries[0]["reason"] == ""


def test_waiver_registry_rejects_an_invented_kind(tmp_path: Path) -> None:
    registry = _registry(
        tmp_path,
        """  - id: WVR-102
    control: SEC-10
    repo: outcome-receipts
    kind: totally-made-up
    reason: seeded fixture
    owner: maintainer
    granted: 2099-01-01
    expires: 2099-02-01
""",
    )

    failures = waiver_failures(registry)
    assert any("unknown kind 'totally-made-up'" in f for f in failures)


def test_waiver_registry_rejects_an_invented_control_by_format(tmp_path: Path) -> None:
    # No control_ids given: format-only fallback (mirrors the portfolio
    # lint's own controls.yml-absent behavior).
    registry = _registry(
        tmp_path,
        """  - id: WVR-103
    control: not-a-real-control-id
    repo: outcome-receipts
    kind: other
    reason: seeded fixture
    owner: maintainer
    granted: 2099-01-01
    expires: 2099-02-01
""",
    )

    failures = waiver_failures(registry)
    assert any("not a valid PREFIX-NN control ID" in f for f in failures)


def test_waiver_registry_rejects_a_control_absent_from_a_pinned_registry(tmp_path: Path) -> None:
    # control_ids given (as if a pinned controls.yml were checked out):
    # membership is checked, not just shape -- SEC-99 is well-formed but does
    # not exist in the (fixture) registry.
    registry = _registry(
        tmp_path,
        """  - id: WVR-104
    control: SEC-99
    repo: outcome-receipts
    kind: other
    reason: seeded fixture
    owner: maintainer
    granted: 2099-01-01
    expires: 2099-02-01
""",
    )

    failures = waiver_failures(registry, control_ids={"SEC-10", "CQ-35"})
    assert any("unknown control ID 'SEC-99'" in f for f in failures)


def test_waiver_registry_accepts_a_control_present_in_a_pinned_registry(tmp_path: Path) -> None:
    registry = _registry(
        tmp_path,
        """  - id: WVR-105
    control: SEC-10
    repo: outcome-receipts
    kind: other
    reason: seeded fixture
    owner: maintainer
    granted: 2099-01-01
    expires: 2099-02-01
""",
    )

    assert waiver_failures(registry, control_ids={"SEC-10", "CQ-35"}) == []


def test_waiver_registry_rejects_a_malformed_id(tmp_path: Path) -> None:
    registry = _registry(
        tmp_path,
        """  - id: nope
    control: SEC-10
    repo: outcome-receipts
    kind: other
    reason: seeded fixture
    owner: maintainer
    granted: 2099-01-01
    expires: 2099-02-01
""",
    )

    failures = waiver_failures(registry)
    assert any("id does not match WVR-NNN" in f for f in failures)


def test_waiver_registry_rejects_all_three_rotten_shapes_together(tmp_path: Path) -> None:
    # The exact scenario issue 97 describes: "an empty reason, an invented
    # waiver kind, or an invented control" -- fed together, each still caught.
    registry = _registry(
        tmp_path,
        """  - id: WVR-106
    control: SEC-99
    repo: outcome-receipts
    kind: made-up-kind
    reason: >-
    owner: maintainer
    granted: 2099-01-01
    expires: 2099-02-01
""",
    )

    failures = waiver_failures(registry, control_ids={"SEC-10"})
    assert "WVR-106: missing reason" in failures
    assert any("unknown kind 'made-up-kind'" in f for f in failures)
    assert any("unknown control ID 'SEC-99'" in f for f in failures)


def test_the_committed_registry_and_gate_still_agree(tmp_path: Path) -> None:
    # Confirms the hardened gate doesn't regress the real, live registry --
    # it should report zero failures against waivers.yml as committed.
    del tmp_path  # unused; keeps the fixture list symmetric with its neighbors
    root = Path(__file__).resolve().parents[1]
    assert waiver_failures(root / "waivers.yml") == []


# ---------------------------------------------------------------------------
# Issue 96: nothing compared docs/RESPONSIBLE-TECH-AUDITS.md §F's VEX
# declaration against the waiver registry, so they silently contradicted
# each other for about seven hours around 2026-08-15. This seeds that exact
# historical contradiction and proves the check now catches it.
# ---------------------------------------------------------------------------

_AUDITS_WITH_NA_VEX = """\
## F. Security and supply chain

- ASVS: N/A for auth/authz/ingress because the product is an offline CLI.
- VEX: N/A today because scans report no unfixable HIGH/CRITICAL dependency CVE.
  Any future exception requires a CycloneDX VEX and quarterly review.

## G. Something else
"""

_AUDITS_WITH_VEX_DECLARED = """\
## F. Security and supply chain

- ASVS: N/A for auth/authz/ingress because the product is an offline CLI.
- VEX: Tracked in vex.json; see the linked CycloneDX VEX document.

## G. Something else
"""


def _waivers_with_live_npm_audit_waiver(expires: str = "2099-01-01") -> str:
    return f"""version: 1

waivers:
  - id: WVR-107
    control: SEC-12
    repo: outcome-receipts
    kind: npm-audit
    advisory: GHSA-jmr9-qjv8-65gv
    reason: >-
      Historical contradiction fixture: a live dependency-advisory waiver
      while the audits doc's VEX line still says N/A.
    owner: maintainer
    granted: 2026-08-15
    expires: {expires}
"""


def test_security_declaration_is_consistent_when_nothing_is_waived() -> None:
    # Today's actual state: no live dependency-advisory waiver, §F says N/A.
    assert (
        security_declaration_failures(
            _AUDITS_WITH_NA_VEX, "version: 1\n\nwaivers: []\n", Path("vex.json")
        )
        == []
    )


def test_security_declaration_catches_the_2026_08_15_contradiction(tmp_path: Path) -> None:
    # The exact shape issue 96 describes: a live waiver, but §F still N/A,
    # and no vex.json on disk at all.
    missing_vex = tmp_path / "vex.json"
    failures = security_declaration_failures(
        _AUDITS_WITH_NA_VEX, _waivers_with_live_npm_audit_waiver(), missing_vex
    )

    assert any("still says N/A" in f for f in failures)
    assert any("does not exist" in f for f in failures)


def test_security_declaration_still_fails_if_vex_json_exists_but_lacks_the_advisory(
    tmp_path: Path,
) -> None:
    vex_path = tmp_path / "vex.json"
    vex_path.write_text(
        '{"vulnerabilities": [{"id": "GHSA-unrelated-0000-0000"}]}', encoding="utf-8"
    )

    failures = security_declaration_failures(
        _AUDITS_WITH_VEX_DECLARED, _waivers_with_live_npm_audit_waiver(), vex_path
    )

    assert any("no VEX statement for waived advisory GHSA-jmr9-qjv8-65gv" in f for f in failures)


def test_security_declaration_passes_when_vex_json_covers_the_live_waiver(tmp_path: Path) -> None:
    vex_path = tmp_path / "vex.json"
    vex_path.write_text(
        '{"vulnerabilities": [{"id": "GHSA-jmr9-qjv8-65gv", "analysis": {"state": "exploitable"}}]}',
        encoding="utf-8",
    )

    failures = security_declaration_failures(
        _AUDITS_WITH_VEX_DECLARED, _waivers_with_live_npm_audit_waiver(), vex_path
    )

    assert failures == []


def test_security_declaration_catches_a_stale_vex_statement(tmp_path: Path) -> None:
    # The opposite direction: vex.json still claims a statement for an
    # advisory that is no longer waived (e.g. the waiver was retired but the
    # VEX document was not cleaned up).
    vex_path = tmp_path / "vex.json"
    vex_path.write_text('{"vulnerabilities": [{"id": "GHSA-jmr9-qjv8-65gv"}]}', encoding="utf-8")

    failures = security_declaration_failures(
        _AUDITS_WITH_NA_VEX, "version: 1\n\nwaivers: []\n", vex_path
    )

    assert any("stale VEX statement" in f for f in failures)


def test_security_declaration_ignores_an_expired_dependency_waiver() -> None:
    # An expired waiver is not "live" -- it should not force a VEX document
    # to exist, and §F may still say N/A.
    failures = security_declaration_failures(
        _AUDITS_WITH_NA_VEX,
        _waivers_with_live_npm_audit_waiver(expires="2020-01-01"),
        Path("vex.json"),
    )

    assert failures == []


# ---------------------------------------------------------------------------
# Issue 93/DOC-15: this repository's own `Last verified:` stamps were never
# mechanically checked -- the portfolio's own staleness parser only scans the
# vendored `.standards` checkout -- and all fourteen used a `Recheck:` label
# the parser's `Recheck cadence:` regex cannot match, so every one silently
# fell through to that parser's 180-day default in any tooling that looked.
# ---------------------------------------------------------------------------


def _doc(root: Path, relpath: str, stamp: str) -> None:
    path = root / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# Doc\n\nBody text.\n\n{stamp}\n", encoding="utf-8")


def test_doc_staleness_ignores_docs_with_no_stamp(tmp_path: Path) -> None:
    _doc(tmp_path, "README.md", "No stamp here at all.")

    assert doc_staleness_failures(tmp_path, date(2026, 8, 21)) == []


def test_doc_staleness_accepts_a_fresh_quarterly_stamp(tmp_path: Path) -> None:
    _doc(
        tmp_path,
        "docs/fresh.md",
        "*Last verified: 2026-07-01 · Recheck cadence: quarterly*",
    )

    assert doc_staleness_failures(tmp_path, date(2026, 8, 21)) == []


def test_doc_staleness_flags_a_stamp_older_than_its_cadence(tmp_path: Path) -> None:
    _doc(
        tmp_path,
        "docs/stale.md",
        "*Last verified: 2026-01-01 · Recheck cadence: monthly*",
    )

    failures = doc_staleness_failures(tmp_path, date(2026, 8, 21))
    assert any("docs/stale.md" in f and "stale" in f for f in failures)


def test_doc_staleness_fails_closed_on_a_missing_cadence_line(tmp_path: Path) -> None:
    _doc(tmp_path, "docs/no-cadence.md", "*Last verified: 2026-08-01*")

    failures = doc_staleness_failures(tmp_path, date(2026, 8, 21))
    assert any("no 'Recheck cadence:' line" in f for f in failures)


def test_doc_staleness_fails_closed_on_an_unparseable_cadence(tmp_path: Path) -> None:
    # The exact bug this issue names: a portfolio-style parser would default
    # an unrecognized cadence to 180 days and report this fresh. This one
    # fails instead, even though 2026-08-21 is only 20 days after the stamp.
    _doc(
        tmp_path,
        "docs/vague.md",
        "*Last verified: 2026-08-01 · Recheck cadence: whenever it feels due*",
    )

    failures = doc_staleness_failures(tmp_path, date(2026, 8, 21))
    assert any("names no recognized interval" in f for f in failures)


def test_doc_staleness_reads_a_keyword_on_the_first_wrapped_line(tmp_path: Path) -> None:
    # Regression guard: an earlier draft of this fix wrapped a cadence
    # sentence across two Markdown source lines with the recognizable
    # keyword ("quarterly") on the *second* line, past where the single-line
    # CADENCE_RE regex stops -- which silently misclassified two real
    # documents (docs/THREAT-MODEL.md, docs/a11y/ACR.md) as unparseable
    # before the wrap was fixed. Confirms a keyword within the regex's own
    # single line is read even when the human-authored sentence continues
    # past it (the wrap fix pairs with this, not a substitute for it).
    _doc(
        tmp_path,
        "docs/wrapped.md",
        "*Last verified: 2026-07-01 · Recheck cadence: quarterly, and also\non any related change.*",
    )

    assert doc_staleness_failures(tmp_path, date(2026, 8, 21)) == []


def test_doc_staleness_ignores_files_outside_root_md_and_docs(tmp_path: Path) -> None:
    (tmp_path / "node_modules" / "somepkg").mkdir(parents=True)
    _doc(
        tmp_path,
        "node_modules/somepkg/README.md",
        "*Last verified: 2020-01-01 · Recheck cadence: monthly*",
    )

    assert doc_staleness_failures(tmp_path, date(2026, 8, 21)) == []


def test_doc_staleness_is_silent_against_the_real_committed_docs() -> None:
    # The fourteen real stamps this issue named, checked as of today: every
    # one now uses the parseable `Recheck cadence:` label and a recognized
    # interval keyword.
    root = Path(__file__).resolve().parents[1]
    assert doc_staleness_failures(root, date.today()) == []


# --- The documented benchmark size, checked against the benchmark that ships. ---


def _benchmark_fixture(root: Path, *, cases: int, spanish_from: int, failures: int) -> None:
    """Write a benchmark file with a known shape, plus the docs the check reads."""

    (root / "eval").mkdir(parents=True, exist_ok=True)
    (root / "docs").mkdir(parents=True, exist_ok=True)
    (root / "docs" / "RESPONSIBLE-TECH-AUDITS.md").write_text(
        f"the {cases}-case benchmark includes planted EN/ES failures.\n", encoding="utf-8"
    )
    lines = []
    for index in range(cases):
        lines.append(
            json.dumps(
                {
                    "id": f"case-{index}",
                    "language": "es" if index >= spanish_from else "en",
                    "should_pass": index >= failures,
                }
            )
        )
    (root / "eval" / "grounding-benchmark.jsonl").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def test_benchmark_claim_failures_catches_the_stale_count() -> None:
    # The real drift this check exists for. Both documents said "100 cases,
    # 50 EN, 50 ES, 50 planted failures" for two months after PR #89 added the
    # 32-case formatting family, because a prose count is exactly the kind of
    # claim no gate reads.
    root = Path(tempfile.mkdtemp())
    _benchmark_fixture(root, cases=132, spanish_from=66, failures=66)
    (root / "README.md").write_text("a 100-case bilingual grounding benchmark\n", encoding="utf-8")
    (root / "docs" / "RESPONSIBLE-TECH-AUDITS.md").write_text(
        "the 100-case benchmark includes planted EN/ES failures.\n", encoding="utf-8"
    )
    (root / "docs" / "ROADMAP.md").write_text(
        "| Bilingual benchmark | 100 committed cases: 50 EN, 50 ES; 50 planted unbound "
        "failures all rejected | AUTO |\n",
        encoding="utf-8",
    )

    failures = benchmark_claim_failures(root)

    assert len(failures) == 3
    assert "README.md claims a 100-case" in failures[0]
    assert "holds 132" in failures[0]
    assert "docs/RESPONSIBLE-TECH-AUDITS.md claims a 100-case" in failures[1]
    assert "holds 132" in failures[1]
    assert "100 cases / 50 EN / 50 ES / 50 planted failures" in failures[2]
    assert "132 / 66 / 66 / 66" in failures[2]


def test_benchmark_claim_failures_fails_closed_on_an_unreadable_claim() -> None:
    # A sentence that no longer matches the shape is not evidence that the count
    # is right. It is a claim the check can no longer read, which is how the
    # stale one survived, so it fails rather than passing silently.
    root = Path(tempfile.mkdtemp())
    _benchmark_fixture(root, cases=4, spanish_from=2, failures=2)
    (root / "README.md").write_text("a bilingual grounding benchmark of some size\n", "utf-8")
    (root / "docs" / "RESPONSIBLE-TECH-AUDITS.md").write_text("the benchmark has cases\n", "utf-8")
    (root / "docs" / "ROADMAP.md").write_text("| Bilingual benchmark | lots | AUTO |\n", "utf-8")

    failures = benchmark_claim_failures(root)

    assert len(failures) == 3
    assert all("cannot be checked" in failure for failure in failures)


def test_benchmark_claim_failures_rejects_a_count_written_in_exotic_digits() -> None:
    # `\d` matches every Unicode decimal digit and `int()` converts them, so a
    # count written in fullwidth digits would have parsed and compared equal.
    # `[0-9]` makes it unreadable instead, which fails closed.
    root = Path(tempfile.mkdtemp())
    _benchmark_fixture(root, cases=4, spanish_from=2, failures=2)
    (root / "README.md").write_text("a \uff14-case bilingual grounding benchmark\n", "utf-8")
    (root / "docs" / "ROADMAP.md").write_text(
        "| Bilingual benchmark | 4 committed cases: 2 EN, 2 ES; 2 planted unbound failures "
        "all rejected | AUTO |\n",
        encoding="utf-8",
    )

    failures = benchmark_claim_failures(root)

    assert failures == [
        "README.md states no benchmark size in the form '<n>-case bilingual grounding "
        "benchmark', so the claim cannot be checked against eval/grounding-benchmark.jsonl"
    ]


def test_benchmark_claim_failures_is_silent_when_the_claims_are_true() -> None:
    root = Path(tempfile.mkdtemp())
    # The fixture writes a matching docs/RESPONSIBLE-TECH-AUDITS.md.
    _benchmark_fixture(root, cases=4, spanish_from=2, failures=2)
    (root / "README.md").write_text("a 4-case bilingual grounding benchmark\n", encoding="utf-8")
    (root / "docs" / "ROADMAP.md").write_text(
        "| Bilingual benchmark | 4 committed cases: 2 EN, 2 ES; 2 planted unbound failures "
        "all rejected | AUTO |\n",
        encoding="utf-8",
    )

    assert benchmark_claim_failures(root) == []


def test_benchmark_claim_is_true_of_the_real_committed_repository() -> None:
    # The one that would have been red on main: the committed README and ROADMAP
    # against the committed benchmark file.
    root = Path(__file__).resolve().parents[1]
    assert benchmark_claim_failures(root) == []


# --- The published action default, and the three schema versions. ---


def _action_fixture(root: Path, *, actual: str, table: str, prose: str) -> None:
    (root / "docs").mkdir(parents=True, exist_ok=True)
    (root / "action.yml").write_text(
        "inputs:\n"
        "  config:\n"
        "    required: true\n"
        "  version:\n"
        "    description: >-\n"
        "      Package version to install.\n"
        "    required: false\n"
        f'    default: "{actual}"\n',
        encoding="utf-8",
    )
    (root / "docs" / "ci-action.md").write_text(
        f"| `version`  | no       | `{table}` | Git ref to install. |\n"
        f"\n- **The `version` input** defaults to `{prose}`, the tag named in "
        "[`action.yml`](../action.yml).\n",
        encoding="utf-8",
    )


def test_action_default_failures_catches_documentation_left_on_the_old_tag() -> None:
    # The real drift: action.yml moved to v0.2.0 and docs/ci-action.md kept
    # publishing v0.1.0 in its Inputs table and "the first released tag" in the
    # prose, so a reader copying the table installed the wrong CLI.
    root = Path(tempfile.mkdtemp())
    _action_fixture(root, actual="v0.2.0", table="v0.1.0", prose="v0.1.0")

    failures = action_default_failures(root)

    assert len(failures) == 2
    assert "its Inputs table" in failures[0]
    assert "defaults to v0.1.0; action.yml sets v0.2.0" in failures[0]
    assert "the prose under Pinning" in failures[1]


def test_action_default_failures_fails_closed_on_an_unreadable_action() -> None:
    # Two defaults inside the version block, or none, means the check cannot tell
    # which one ships. That is not evidence the documented default is right.
    root = Path(tempfile.mkdtemp())
    _action_fixture(root, actual="v0.2.0", table="v0.2.0", prose="v0.2.0")
    (root / "action.yml").write_text("inputs:\n  config:\n    required: true\n", encoding="utf-8")

    failures = action_default_failures(root)

    assert failures == [
        "action.yml no longer states one unambiguous default for its `version` input, "
        "so the default docs/ci-action.md publishes cannot be checked against it"
    ]


def test_action_default_failures_is_silent_when_the_documentation_agrees() -> None:
    root = Path(tempfile.mkdtemp())
    _action_fixture(root, actual="v0.2.0", table="v0.2.0", prose="v0.2.0")

    assert action_default_failures(root) == []


def test_action_default_is_true_of_the_real_committed_repository() -> None:
    root = Path(__file__).resolve().parents[1]
    assert action_default_failures(root) == []


def test_schema_versions_are_true_of_the_real_committed_repository() -> None:
    # Three homes per contract: the constant the code writes, the `const` the
    # published JSON Schema pins, and the sentence docs/SPEC-STABILITY.md states.
    # Nothing compared them before.
    root = Path(__file__).resolve().parents[1]
    assert schema_version_failures(root) == []


def test_schema_version_failures_catches_a_bumped_constant(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    shutil.copytree(root / "src", tmp_path / "src")
    shutil.copytree(root / "docs" / "schema", tmp_path / "docs" / "schema")
    (tmp_path / "docs" / "SPEC-STABILITY.md").write_text(
        (root / "docs" / "SPEC-STABILITY.md").read_text(encoding="utf-8"), encoding="utf-8"
    )
    models = tmp_path / "src" / "outcome_receipts" / "models.py"
    models.write_text(
        models.read_text(encoding="utf-8").replace(
            'SCHEMA_VERSION = "2.0"', 'SCHEMA_VERSION = "3.0"'
        ),
        encoding="utf-8",
    )

    failures = schema_version_failures(tmp_path)

    assert any("receipts.schema.json pins schema_version const '2.0'" in f for f in failures)
    assert any("receipts manifest is at 2.0" in f for f in failures)


def test_schema_version_failures_fails_closed_on_an_unreadable_sentence(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    shutil.copytree(root / "src", tmp_path / "src")
    shutil.copytree(root / "docs" / "schema", tmp_path / "docs" / "schema")
    (tmp_path / "docs" / "SPEC-STABILITY.md").write_text(
        "The contracts are versioned somewhere else now.\n", encoding="utf-8"
    )

    failures = schema_version_failures(tmp_path)

    assert failures == [
        "docs/SPEC-STABILITY.md no longer names the three contract versions in the form "
        "'The report spec is at `X`, the receipts manifest at `Y`, and the workflow "
        "artifact at `Z`.', so the claim cannot be checked against the code"
    ]


def test_the_standards_pin_is_named_the_same_way_in_all_three_places() -> None:
    """`.standards-version`, the CI checkout ref, and the CI assertion must agree.

    The pin is written three times: once in `.standards-version`, once as the
    `ref:` the "portfolio standards" job checks the standards repository out at,
    and once in that job's own `test "$(cat .standards-version)" = "..."` line.
    Two of those three are inside a workflow file, which no test read.

    Bumping `.standards-version` alone turns the job red on its assertion, which
    is loud and fine. Bumping the assertion literal alone, or the `ref:` alone,
    is the quiet one: the job would go on checking out a version nobody declared
    and reporting green about it. Whichever copy moves, all three move.
    """

    root = Path(__file__).resolve().parents[1]
    pinned = (root / ".standards-version").read_text(encoding="utf-8").strip()
    workflow = (root / ".github" / "workflows" / "standards.yml").read_text(encoding="utf-8")

    checkout_refs = re.findall(r"^\s+ref:\s*(\S+)\s*$", workflow, re.MULTILINE)
    asserted = re.findall(r'test\s+"\$\(cat \.standards-version\)"\s*=\s*"([^"]+)"', workflow)

    assert checkout_refs == [pinned], (checkout_refs, pinned)
    assert asserted == [pinned], (asserted, pinned)
