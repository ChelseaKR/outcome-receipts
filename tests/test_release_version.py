"""The version declarations in the tree, and the release tag, must agree.

`tests/test_version.py` covers the wheel and the CLI. This covers the third
term of the sentence that file opens with -- the tag -- and the two files that
carry the number by hand, `CITATION.cff` and `CHANGELOG.md`.

Every fixture below writes literal version strings. None is computed from
`outcome_receipts.__version__`, from `pyproject.toml`, or from the tag under
test: a fixture derived from the value it checks moves with that value and can
never catch a wrong one.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from scripts.check_release_version import main, version_failures

ROOT = Path(__file__).resolve().parents[1]


def _tree(
    root: Path,
    *,
    pyproject: str = "0.2.1",
    citation: str = "0.2.1",
    citation_date: str = "2026-09-07",
    changelog: str = "## [Unreleased]\n\n## [0.2.1] - 2026-09-07\n\n### Added\n- A thing.\n",
) -> Path:
    (root / "pyproject.toml").write_text(
        f'[project]\nname = "outcome-receipts"\nversion = "{pyproject}"\n',
        encoding="utf-8",
    )
    (root / "CITATION.cff").write_text(
        "cff-version: 1.2.0\n"
        'title: "outcome-receipts"\n'
        f'version: "{citation}"\n'
        f"date-released: {citation_date}\n",
        encoding="utf-8",
    )
    (root / "CHANGELOG.md").write_text(f"# Changelog\n\n{changelog}", encoding="utf-8")
    return root


def test_an_agreeing_tree_passes(tmp_path: Path) -> None:
    assert version_failures(_tree(tmp_path)) == []


def test_an_agreeing_tree_passes_with_its_own_tag(tmp_path: Path) -> None:
    assert version_failures(_tree(tmp_path), tag="v0.2.1") == []


def test_a_changelog_promotion_without_the_bump_fails(tmp_path: Path) -> None:
    """The defect this gate was written for: `main` on 2026-09-07.

    `CHANGELOG.md` said `0.2.1` was released; `pyproject.toml` still said
    `0.2.0`; `make verify` and `ci` were both green.
    """

    failures = version_failures(
        _tree(tmp_path, pyproject="0.2.0", citation="0.2.0", citation_date="2026-08-16")
    )
    assert any("pyproject.toml declares version 0.2.0" in f for f in failures)
    assert any("CITATION.cff declares version 0.2.0" in f for f in failures)
    assert any("date-released is 2026-08-16" in f for f in failures)


def test_a_bump_without_the_changelog_fails(tmp_path: Path) -> None:
    """The same drift in the other direction, which is just as publishable."""

    failures = version_failures(
        _tree(
            tmp_path,
            pyproject="0.3.0",
            citation="0.3.0",
            citation_date="2026-09-07",
        )
    )
    assert any("pyproject.toml declares version 0.3.0" in f and "is 0.2.1" in f for f in failures)


def test_a_tag_that_names_a_version_the_tree_does_not_declare_fails(tmp_path: Path) -> None:
    """The comparison `release.yml` had no step for.

    `uv build` reads `pyproject.toml`, so a `v0.3.0` dispatch over this tree
    would build, attest and upload a `0.2.1` wheel, and only `verify-published`
    -- after the PyPI upload -- would notice.
    """

    failures = version_failures(_tree(tmp_path), tag="v0.3.0")
    assert failures == [
        "the release tag is v0.3.0, but pyproject.toml declares version 0.2.1. "
        "`uv build` reads pyproject.toml, so this run would publish 0.2.1 under "
        "the name v0.3.0."
    ]


@pytest.mark.parametrize("tag", ["0.2.1", "v0.2", "v0.2.1-rc1", "release-0.2.1", ""])
def test_a_tag_that_is_not_a_stable_release_tag_fails(tmp_path: Path, tag: str) -> None:
    failures = version_failures(_tree(tmp_path), tag=tag)
    assert any("is not a stable vX.Y.Z release tag" in f for f in failures)


# --- unmeasurable is a failure, not a pass -------------------------------


def test_a_changelog_with_no_released_section_fails(tmp_path: Path) -> None:
    failures = version_failures(_tree(tmp_path, changelog="## [Unreleased]\n\n- Nothing yet.\n"))
    assert failures == ["CHANGELOG.md declares no dated release section"]


def test_a_release_heading_with_no_date_fails_rather_than_skipping_it(tmp_path: Path) -> None:
    """A botched promotion must not pass by matching the release below it.

    `## [0.2.1]` with the date dropped is the shape a hand-edited promotion
    produces. If the scan skipped it and kept looking, it would compare against
    `## [0.2.0] - 2026-08-16` and agree with a `pyproject.toml` that had never
    been bumped -- reporting a match it reached by ignoring the newest release.
    """

    failures = version_failures(
        _tree(
            tmp_path,
            pyproject="0.2.0",
            citation="0.2.0",
            citation_date="2026-08-16",
            changelog="## [Unreleased]\n\n## [0.2.1]\n\n## [0.2.0] - 2026-08-16\n",
        )
    )
    assert failures == ["CHANGELOG.md's newest release heading is malformed: '## [0.2.1]'"]


def test_a_release_heading_with_an_unparseable_date_fails(tmp_path: Path) -> None:
    failures = version_failures(
        _tree(tmp_path, changelog="## [Unreleased]\n\n## [0.2.1] - 2026-13-99\n")
    )
    assert failures == ["CHANGELOG.md's 0.2.1 section has an unparseable date: '2026-13-99'"]


def test_a_pyproject_with_no_version_fails(tmp_path: Path) -> None:
    tree = _tree(tmp_path)
    (tree / "pyproject.toml").write_text('[project]\nname = "outcome-receipts"\n', encoding="utf-8")
    failures = version_failures(tree)
    assert failures == ["pyproject.toml declares no project.version"]


def test_a_citation_with_no_version_is_not_compared_as_if_it_were_one(tmp_path: Path) -> None:
    """An unreadable declaration is reported once, not also compared."""

    tree = _tree(tmp_path)
    (tree / "CITATION.cff").write_text(
        "cff-version: 1.2.0\ndate-released: 2026-09-07\n", encoding="utf-8"
    )
    failures = version_failures(tree)
    assert failures == ["CITATION.cff declares no version"]


@pytest.mark.parametrize("missing", ["pyproject.toml", "CITATION.cff", "CHANGELOG.md"])
def test_a_missing_declaration_file_fails(tmp_path: Path, missing: str) -> None:
    tree = _tree(tmp_path)
    (tree / missing).unlink()
    assert version_failures(tree) == [f"{missing} is missing"]


# --- the repository itself -----------------------------------------------


def test_this_repository_agrees_with_itself() -> None:
    assert version_failures(ROOT) == []


def test_main_reports_the_repository_as_passing(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--root", str(ROOT)]) == 0
    assert "release version parity" in capsys.readouterr().out


def test_main_returns_nonzero_and_names_each_failure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    tree = _tree(tmp_path, pyproject="0.2.0", citation="0.2.0", citation_date="2026-08-16")
    assert main(["--root", str(tree)]) == 1
    err = capsys.readouterr().err
    assert "release version parity failed:" in err
    assert err.count("\n- ") == 3
