"""The code-quality gates must cover the code that implements the other gates.

Every merge-blocking check in this repository except the test suite lives under
``scripts/``: the conformance checker, the waiver lints, the npm-audit
adjudicator, the i18n checker, the source-hygiene checker. For a long time
``make lint`` read ``ruff check src tests`` and ``[tool.mypy] files`` read
``["src", "tests"]``, so that directory was the one place neither tool looked.
A deliberate break confirmed the consequence: an unused import, a shadowed
name and a type error injected into ``scripts/check_source_hygiene.py`` passed
both gates with exit 0.

These tests fail if the scope is narrowed back.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAKEFILE = ROOT / "Makefile"
PYPROJECT = ROOT / "pyproject.toml"


def _recipe(text: str, target: str) -> list[str]:
    """The tab-indented command lines of one Makefile target, continuations joined."""

    match = re.search(rf"^{re.escape(target)}:[^\n]*\n((?:\t[^\n]*\n)*)", text, re.MULTILINE)
    assert match is not None, f"no recipe found for `{target}` in the Makefile"
    body = match.group(1).replace("\\\n", " ")
    return [line.strip() for line in body.splitlines() if line.strip()]


def test_lint_covers_the_scripts_that_implement_the_other_gates() -> None:
    commands = _recipe(MAKEFILE.read_text(encoding="utf-8"), "lint")
    checked = [command for command in commands if "ruff check" in command]
    formatted = [command for command in commands if "ruff format" in command]

    assert checked, "make lint runs no `ruff check`"
    assert formatted, "make lint runs no `ruff format --check`"
    for command in checked + formatted:
        for directory in ("src", "tests", "scripts"):
            assert re.search(rf"\b{directory}\b", command), (
                f"`{command}` does not cover {directory}/; a gate that skips the "
                "directory holding the other gates cannot report a defect in them"
            )


def test_type_checking_covers_scripts_as_well_as_src_and_tests() -> None:
    commands = _recipe(MAKEFILE.read_text(encoding="utf-8"), "type")
    mypy_commands = [command for command in commands if "mypy" in command]

    assert mypy_commands, "make type runs no mypy"
    # One invocation reads `files` from pyproject; a second names scripts/
    # explicitly, because a single combined run cannot resolve the same file
    # as both `check_conformance` and `scripts.check_conformance`.
    assert any(re.search(r"\bscripts\b", command) for command in mypy_commands), (
        "no mypy invocation in `make type` names scripts/"
    )

    files = re.search(r"^files\s*=\s*\[([^\]]*)\]", PYPROJECT.read_text(encoding="utf-8"), re.M)
    assert files is not None, "pyproject.toml declares no [tool.mypy] files"
    for directory in ("src", "tests"):
        assert f'"{directory}"' in files.group(1), (
            f"[tool.mypy] files no longer covers {directory}/"
        )


# The one tracked Python file outside the covered directories. It self-documents
# as a one-time, human-run data-preparation script that is deliberately not part
# of `make verify`, and it cannot join the covered set as it stands: `ruff check`
# reports an error on it and `mypy --strict` wants pandas stubs. It is named here
# rather than skipped silently, so the exception is a decision on the record and
# any *other* stray file fails.
KNOWN_UNCOVERED = {"eval/hud/extract.py"}
COVERED_DIRS = ("src", "tests", "scripts")
VENDORED = (".venv", "node_modules", ".git", ".ruff_cache", ".mypy_cache", ".pytest_cache")


def test_every_gate_script_is_inside_the_directory_the_gates_now_cover() -> None:
    # The scope above is expressed as a directory, so this is what makes it a
    # guarantee about files rather than about a path string: nothing that
    # implements a gate may sit outside scripts/ and escape both tools again.
    #
    # This walks the tree. It used to be `ROOT.glob("*.py")`, which reads the
    # repository root only and non-recursively; there are no `.py` files at the
    # root, so the assertion was true no matter what was added under any
    # subdirectory, and `eval/hud/extract.py` was already sitting outside every
    # covered directory while this test reported green.
    stray = sorted(
        path.relative_to(ROOT).as_posix()
        for path in ROOT.rglob("*.py")
        if not any(part in VENDORED for part in path.parts)
        and path.relative_to(ROOT).parts[0] not in COVERED_DIRS
        and path.name != "conftest.py"
        and path.relative_to(ROOT).as_posix() not in KNOWN_UNCOVERED
    )
    assert stray == [], f"gate code outside src/, tests/ and scripts/: {stray}"


def test_the_known_uncovered_file_still_exists_so_the_exception_stays_honest() -> None:
    # An allowlist entry for a file that has been deleted or moved is an
    # exception nobody is reviewing. If this fails, remove the entry.
    for relative in KNOWN_UNCOVERED:
        assert (ROOT / relative).exists(), (
            f"{relative} is in KNOWN_UNCOVERED but no longer exists; remove the entry"
        )
