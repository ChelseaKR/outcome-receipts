"""Regression tests for the Semgrep waiver ledger cross-check.

`.semgrep-waivers.yml` asserted its own invariant in a header comment and
nothing enforced it. These tests drive `scripts/check_semgrep_waivers.py` over
fixture trees, in both directions: a ledger row with no suppression behind it,
and a suppression with no ledger row in front of it. A gate that only ever ran
against a consistent repository would report green in both of those states,
which is the failure mode this file exists to rule out.
"""

from __future__ import annotations

from pathlib import Path

from scripts.check_semgrep_waivers import (
    find_suppressions,
    ledger_failures,
    main,
    parse_ledger,
)

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / ".semgrep-waivers.yml"

_LEDGER_TEXT = """\
# A header comment, which is not a waiver.
waivers:
  - rule_id: some-rule
    locations:
      - src/pkg/module.py (a note in parentheses)
    added: 2026-07-12
    last_reviewed: 2026-07-22
    tracking_issue: https://example.invalid/issues/1
    reason: >
      A folded reason whose first sentence contains a colon: the parser must not
      read that as a new field name, which is exactly what an earlier draft did.
"""


def _tree(root: Path, ledger: str, module: str) -> tuple[Path, Path]:
    source = root / "src" / "pkg" / "module.py"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(module, encoding="utf-8")
    ledger_path = root / ".semgrep-waivers.yml"
    ledger_path.write_text(ledger, encoding="utf-8")
    return root, ledger_path


_SUPPRESSED = "# nosemgrep: some-rule\nvalue = 1\n"


def test_a_consistent_tree_reports_nothing(tmp_path: Path) -> None:
    root, ledger = _tree(tmp_path, _LEDGER_TEXT, _SUPPRESSED)
    assert ledger_failures(root, ledger) == []


def test_a_ledger_row_with_no_suppression_behind_it_fails(tmp_path: Path) -> None:
    root, ledger = _tree(tmp_path, _LEDGER_TEXT, "value = 1\n")

    failures = ledger_failures(root, ledger)

    assert any("no inline suppression naming it" in failure for failure in failures)


def test_a_suppression_with_no_ledger_row_in_front_of_it_fails(tmp_path: Path) -> None:
    root, ledger = _tree(
        tmp_path, _LEDGER_TEXT, _SUPPRESSED + "# nosemgrep: undocumented-rule\nother = 2\n"
    )

    failures = ledger_failures(root, ledger)

    assert any("'undocumented-rule' is suppressed here" in failure for failure in failures)


def test_a_row_naming_a_file_that_does_not_carry_the_suppression_fails(tmp_path: Path) -> None:
    # The suppression exists, but somewhere other than where the ledger says.
    root, ledger = _tree(tmp_path, _LEDGER_TEXT, "value = 1\n")
    elsewhere = root / "src" / "pkg" / "other.py"
    elsewhere.write_text(_SUPPRESSED, encoding="utf-8")

    failures = ledger_failures(root, ledger)

    assert any("carries no suppression for this rule" in failure for failure in failures)


def test_an_unqualified_suppression_is_refused(tmp_path: Path) -> None:
    root, ledger = _tree(tmp_path, _LEDGER_TEXT, _SUPPRESSED + "# nosemgrep\nother = 2\n")

    failures = ledger_failures(root, ledger)

    assert any("names no rule" in failure for failure in failures)


def test_a_row_missing_a_required_field_fails(tmp_path: Path) -> None:
    root, ledger = _tree(
        tmp_path,
        _LEDGER_TEXT.replace("    tracking_issue: https://example.invalid/issues/1\n", ""),
        _SUPPRESSED,
    )

    failures = ledger_failures(root, ledger)

    assert "some-rule: missing tracking_issue" in failures


def test_a_row_with_an_unparseable_date_fails(tmp_path: Path) -> None:
    root, ledger = _tree(
        tmp_path,
        _LEDGER_TEXT.replace("last_reviewed: 2026-07-22", "last_reviewed: soon"),
        _SUPPRESSED,
    )

    failures = ledger_failures(root, ledger)

    assert any("last_reviewed 'soon' is not an ISO date" in failure for failure in failures)


def test_a_missing_ledger_fails_rather_than_passing_vacuously(tmp_path: Path) -> None:
    failures = ledger_failures(tmp_path, tmp_path / ".semgrep-waivers.yml")

    assert failures and "does not exist" in failures[0]


def test_a_directive_quoted_in_a_docstring_is_not_a_suppression(tmp_path: Path) -> None:
    # Python files are tokenized, so prose and test fixtures that quote the
    # syntax do not register. Without this, this very test file would fail the
    # gate it is testing.
    root, ledger = _tree(
        tmp_path, _LEDGER_TEXT, _SUPPRESSED + '\nDOC = """# nosemgrep: quoted-only"""\n'
    )

    assert ledger_failures(root, ledger) == []


def test_the_committed_ledger_and_the_committed_tree_agree() -> None:
    assert ledger_failures(ROOT, LEDGER) == []


def test_the_real_ledger_parses_into_complete_rows() -> None:
    # A parser that silently produced empty rows would make every coverage
    # check above pass over nothing.
    entries = parse_ledger(LEDGER.read_text(encoding="utf-8"))

    assert len(entries) == 2
    for entry in entries:
        assert entry.rule_id
        assert entry.locations
        assert entry.fields["reason"].strip()


def test_the_real_tree_actually_contains_the_suppressions_being_checked() -> None:
    # Guards the other direction of vacuity: if the scan found nothing, every
    # "no undocumented suppression" assertion would be trivially satisfied.
    found = find_suppressions(ROOT)

    assert {rule for item in found for rule in item.rule_ids} == {
        "python37-compatibility-importlib2",
        "sqlalchemy-execute-raw-query",
    }


def test_main_returns_nonzero_on_a_broken_tree(tmp_path: Path) -> None:
    root, ledger = _tree(tmp_path, _LEDGER_TEXT, "value = 1\n")

    assert main(["--root", str(root), "--ledger", str(ledger)]) == 1


def test_main_returns_zero_on_the_committed_repository() -> None:
    assert main(["--root", str(ROOT), "--ledger", str(LEDGER)]) == 0
