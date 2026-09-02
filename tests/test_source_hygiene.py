"""Regression tests for the source-hygiene gate.

`make hygiene` has run `scripts/check_source_hygiene.py` on every commit and
nothing tested it, so neither of the two things it can get wrong was pinned:
letting an unreferenced suppression through, and reporting one that is not
there. Both directions are exercised here against fixture trees.
"""

from __future__ import annotations

from pathlib import Path

from scripts.check_source_hygiene import hygiene_failures

ROOT = Path(__file__).resolve().parents[1]

_ISSUE = "https://github.com/ChelseaKR/outcome-receipts/issues/1"

# Assembled from fragments for the same reason the checker's own MARKER pattern
# is: the marker scan is deliberately line-based, so a fixture spelling the word
# out would make this file fail the very gate it tests.
_MARKER = "TO" + "DO"


def _tree(root: Path, module: str) -> Path:
    package = root / "src" / "outcome_receipts"
    package.mkdir(parents=True, exist_ok=True)
    (package / "module.py").write_text(module, encoding="utf-8")
    (root / "tests").mkdir(parents=True, exist_ok=True)
    return root


def test_an_unreferenced_suppression_comment_fails(tmp_path: Path) -> None:
    root = _tree(tmp_path, "value = int('1')  # noqa: S101\n")

    failures = hygiene_failures(root)

    assert any("module.py:1: missing issue reference" in failure for failure in failures)


def test_a_referenced_suppression_comment_passes(tmp_path: Path) -> None:
    root = _tree(tmp_path, f"value = int('1')  # noqa: S101  {_ISSUE}\n")

    assert hygiene_failures(root) == []


def test_an_unreferenced_type_ignore_fails(tmp_path: Path) -> None:
    root = _tree(tmp_path, "value = 1  # type: ignore[assignment]\n")

    assert any("missing issue reference" in failure for failure in hygiene_failures(root))


def test_a_suppression_inside_a_string_literal_is_not_a_suppression(tmp_path: Path) -> None:
    # A test that exercises suppression handling, or a script that documents
    # the syntax, holds the text without holding the suppression. Reading the
    # file line by line could not tell the two apart.
    root = _tree(tmp_path, 'PATTERN = "# noqa: S101"\nDOC = """# nosemgrep: some-rule"""\n')

    assert hygiene_failures(root) == []


def test_an_unreferenced_marker_still_fails_anywhere_in_the_file(tmp_path: Path) -> None:
    # Markers stay line-based on purpose: one left in a docstring is still one
    # left behind.
    root = _tree(tmp_path, f'"""Module.\n\n{_MARKER}: finish this.\n"""\n')

    assert any("missing issue reference" in failure for failure in hygiene_failures(root))


def test_a_referenced_marker_passes(tmp_path: Path) -> None:
    root = _tree(tmp_path, f"# {_MARKER}: finish this. {_ISSUE}\nvalue = 1\n")

    assert hygiene_failures(root) == []


def test_a_file_that_cannot_be_tokenized_is_scanned_line_by_line(tmp_path: Path) -> None:
    # The tokenizer fallback must over-report, never skip: a syntactically
    # broken file is not a place a suppression gets to hide.
    root = _tree(tmp_path, "def broken(  # noqa: S101\n")

    assert any("missing issue reference" in failure for failure in hygiene_failures(root))


def test_a_duplicate_tool_config_fails(tmp_path: Path) -> None:
    root = _tree(tmp_path, "value = 1\n")
    (root / "setup.cfg").write_text("[metadata]\n", encoding="utf-8")

    assert "setup.cfg" in hygiene_failures(root)


def test_a_missing_package_layout_fails(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()

    assert "src/outcome_receipts is missing" in hygiene_failures(tmp_path)


def test_the_committed_repository_is_clean() -> None:
    assert hygiene_failures(ROOT) == []


def test_scripts_are_in_scope(tmp_path: Path) -> None:
    # The gate scripts are subject to the rule they enforce.
    root = _tree(tmp_path, "value = 1\n")
    scripts = root / "scripts"
    scripts.mkdir()
    (scripts / "gate.py").write_text("value = 1  # noqa: S101\n", encoding="utf-8")

    assert any("scripts/gate.py:1" in failure for failure in hygiene_failures(root))
