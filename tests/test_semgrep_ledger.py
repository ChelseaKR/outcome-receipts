"""Regression tests for the Semgrep waiver ledger cross-check.

`.semgrep-waivers.yml` asserted its own invariant in a header comment and
nothing enforced it. These tests drive `scripts/check_semgrep_waivers.py` over
fixture trees, in both directions: a ledger row with no suppression behind it,
and a suppression with no ledger row in front of it. A gate that only ever ran
against a consistent repository would report green in both of those states,
which is the failure mode this file exists to rule out.

The same question is asked of the ledger's own dates. `last_reviewed` was
validated as an ISO date and then ignored, so the quarterly cadence issues 52
and 53 promise had nothing enforcing it: these drive the clock, not the tree,
and one of them runs the real ledger forward past its own quarter so "the
cadence is enforced" is a claim about the committed document.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from scripts.check_semgrep_waivers import (
    REVIEW_INTERVAL_DAYS,
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


#: The day the fixture ledger's `last_reviewed: 2026-07-22` is one day old. Every
#: test below that is not about review currency is pinned to it, so none of them
#: starts failing on a calendar date rather than on the state it set up.
_TODAY = date(2026, 7, 23)

_AUDITS = "docs/RESPONSIBLE-TECH-AUDITS.md"


def _tree(
    root: Path, ledger: str, module: str, *, audits: str | None = "2026-07-22"
) -> tuple[Path, Path]:
    source = root / "src" / "pkg" / "module.py"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(module, encoding="utf-8")
    ledger_path = root / ".semgrep-waivers.yml"
    ledger_path.write_text(ledger, encoding="utf-8")
    if audits is not None:
        audits_path = root / _AUDITS
        audits_path.parent.mkdir(parents=True, exist_ok=True)
        audits_path.write_text(f"Waiver review recorded {audits}.\n", encoding="utf-8")
    return root, ledger_path


_SUPPRESSED = "# nosemgrep: some-rule\nvalue = 1\n"


def test_a_consistent_tree_reports_nothing(tmp_path: Path) -> None:
    root, ledger = _tree(tmp_path, _LEDGER_TEXT, _SUPPRESSED)
    assert ledger_failures(root, ledger, _TODAY) == []


def test_a_ledger_row_with_no_suppression_behind_it_fails(tmp_path: Path) -> None:
    root, ledger = _tree(tmp_path, _LEDGER_TEXT, "value = 1\n")

    failures = ledger_failures(root, ledger, _TODAY)

    assert any("no inline suppression naming it" in failure for failure in failures)


def test_a_suppression_with_no_ledger_row_in_front_of_it_fails(tmp_path: Path) -> None:
    root, ledger = _tree(
        tmp_path, _LEDGER_TEXT, _SUPPRESSED + "# nosemgrep: undocumented-rule\nother = 2\n"
    )

    failures = ledger_failures(root, ledger, _TODAY)

    assert any("'undocumented-rule' is suppressed here" in failure for failure in failures)


def test_a_row_naming_a_file_that_does_not_carry_the_suppression_fails(tmp_path: Path) -> None:
    # The suppression exists, but somewhere other than where the ledger says.
    root, ledger = _tree(tmp_path, _LEDGER_TEXT, "value = 1\n")
    elsewhere = root / "src" / "pkg" / "other.py"
    elsewhere.write_text(_SUPPRESSED, encoding="utf-8")

    failures = ledger_failures(root, ledger, _TODAY)

    assert any("carries no suppression for this rule" in failure for failure in failures)


def test_an_unqualified_suppression_is_refused(tmp_path: Path) -> None:
    root, ledger = _tree(tmp_path, _LEDGER_TEXT, _SUPPRESSED + "# nosemgrep\nother = 2\n")

    failures = ledger_failures(root, ledger, _TODAY)

    assert any("names no rule" in failure for failure in failures)


def test_a_row_missing_a_required_field_fails(tmp_path: Path) -> None:
    root, ledger = _tree(
        tmp_path,
        _LEDGER_TEXT.replace("    tracking_issue: https://example.invalid/issues/1\n", ""),
        _SUPPRESSED,
    )

    failures = ledger_failures(root, ledger, _TODAY)

    assert "some-rule: missing tracking_issue" in failures


def test_a_row_with_an_unparseable_date_fails(tmp_path: Path) -> None:
    root, ledger = _tree(
        tmp_path,
        _LEDGER_TEXT.replace("last_reviewed: 2026-07-22", "last_reviewed: soon"),
        _SUPPRESSED,
    )

    failures = ledger_failures(root, ledger, _TODAY)

    assert any("last_reviewed 'soon' is not an ISO date" in failure for failure in failures)


def test_a_missing_ledger_fails_rather_than_passing_vacuously(tmp_path: Path) -> None:
    failures = ledger_failures(tmp_path, tmp_path / ".semgrep-waivers.yml", _TODAY)

    assert failures and "does not exist" in failures[0]


def test_a_directive_quoted_in_a_docstring_is_not_a_suppression(tmp_path: Path) -> None:
    # Python files are tokenized, so prose and test fixtures that quote the
    # syntax do not register. Without this, this very test file would fail the
    # gate it is testing.
    root, ledger = _tree(
        tmp_path, _LEDGER_TEXT, _SUPPRESSED + '\nDOC = """# nosemgrep: quoted-only"""\n'
    )

    assert ledger_failures(root, ledger, _TODAY) == []


def test_the_committed_ledger_and_the_committed_tree_agree() -> None:
    assert ledger_failures(ROOT, LEDGER, date.today()) == []


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

    assert main(["--root", str(root), "--ledger", str(ledger), "--today", _TODAY.isoformat()]) == 1


def test_main_returns_zero_on_the_committed_repository() -> None:
    assert main(["--root", str(ROOT), "--ledger", str(LEDGER)]) == 0


# --- The quarterly review the two tracking issues promise, and its two records. ---
#
# `last_reviewed` was parsed as a date and then never looked at again, so the
# quarterly cadence issues 52 and 53 exist to enforce was a sentence in two
# issue bodies with nothing behind it: a waiver reviewed once in July passed
# identically forever. These drive the clock rather than the tree.


def test_a_review_inside_the_quarter_is_not_a_failure(tmp_path: Path) -> None:
    root, ledger = _tree(tmp_path, _LEDGER_TEXT, _SUPPRESSED)
    last_day = date(2026, 7, 22) + timedelta(days=REVIEW_INTERVAL_DAYS)

    # The boundary belongs to the reviewer, not to the gate: the review is good
    # through the last day of the quarter and lapses the day after.
    assert ledger_failures(root, ledger, last_day) == []


def test_a_lapsed_review_fails_and_names_its_owner(tmp_path: Path) -> None:
    root, ledger = _tree(tmp_path, _LEDGER_TEXT, _SUPPRESSED)
    overdue_by_one = date(2026, 7, 22) + timedelta(days=REVIEW_INTERVAL_DAYS + 1)

    failures = ledger_failures(root, ledger, overdue_by_one)

    assert len(failures) == 1
    assert "some-rule: last reviewed 2026-07-22" in failures[0]
    assert "1 day(s) overdue" in failures[0]
    # The failure has to be actionable by whoever reads it, so it names the
    # tracking issue rather than only the rule.
    assert "https://example.invalid/issues/1" in failures[0]


def test_a_review_dated_in_the_future_is_refused(tmp_path: Path) -> None:
    # The one value that would make this check permanently silent: a date ahead
    # of today can never go stale, so "reviewed 2099-01-01" would buy a waiver
    # 73 years of green. A review that has not happened is not a review.
    root, ledger = _tree(
        tmp_path,
        _LEDGER_TEXT.replace("last_reviewed: 2026-07-22", "last_reviewed: 2099-01-01"),
        _SUPPRESSED,
        audits="2099-01-01",
    )

    failures = ledger_failures(root, ledger, _TODAY)

    assert len(failures) == 1
    assert "after today" in failures[0]


def test_an_unreadable_review_date_is_reported_once_not_twice(tmp_path: Path) -> None:
    # An unparseable date is a schema failure. Reporting it a second time as
    # "overdue" would be the gate guessing at a value it just said it cannot
    # read.
    root, ledger = _tree(
        tmp_path,
        _LEDGER_TEXT.replace("last_reviewed: 2026-07-22", "last_reviewed: soon"),
        _SUPPRESSED,
        audits="soon",
    )

    failures = ledger_failures(root, ledger, date(2099, 1, 1))

    assert failures == ["some-rule: last_reviewed 'soon' is not an ISO date"]


def test_a_review_recorded_in_only_one_of_the_two_places_fails(tmp_path: Path) -> None:
    # Issue 52's acceptance criteria name the ledger and the audits document.
    # Nothing compared them, so the ledger could carry a fresh date while the
    # section a reader opens still described the previous review.
    root, ledger = _tree(tmp_path, _LEDGER_TEXT, _SUPPRESSED, audits="2026-01-01")

    failures = ledger_failures(root, ledger, _TODAY)

    assert len(failures) == 1
    assert "does not mention that date" in failures[0]


def test_a_missing_audits_document_is_reported_as_unread_not_as_disagreement(
    tmp_path: Path,
) -> None:
    # "There is no second record" and "the two records disagree" are different
    # statements. Reporting the first as the second would be a finding about a
    # document that does not exist, once per row.
    root, ledger = _tree(tmp_path, _LEDGER_TEXT, _SUPPRESSED, audits=None)

    failures = ledger_failures(root, ledger, _TODAY)

    assert len(failures) == 1
    assert "is missing, so the second record" in failures[0]


def test_the_committed_ledger_lapses_on_a_knowable_date() -> None:
    # The real ledger read through the real check. Without this, "the cadence is
    # enforced" would be a claim about a fixture: every committed waiver is
    # required to fail once its own quarter has run out.
    entries = parse_ledger(LEDGER.read_text(encoding="utf-8"))
    assert entries, "the committed ledger holds no rows, so this test proves nothing"
    latest = max(date.fromisoformat(entry.fields["last_reviewed"]) for entry in entries)

    overdue = ledger_failures(ROOT, LEDGER, latest + timedelta(days=REVIEW_INTERVAL_DAYS + 1))

    assert len(overdue) == len(entries)
    assert all("overdue" in failure for failure in overdue)


def test_the_committed_review_dates_appear_in_the_audits_document() -> None:
    audits = (ROOT / _AUDITS).read_text(encoding="utf-8")
    for entry in parse_ledger(LEDGER.read_text(encoding="utf-8")):
        assert entry.fields["last_reviewed"] in audits, (
            f"{entry.rule_id}: the ledger records a review on "
            f"{entry.fields['last_reviewed']} that {_AUDITS} does not mention"
        )
