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


def test_every_gate_script_is_inside_the_directory_the_gates_now_cover() -> None:
    # The scope above is expressed as a directory, so this is what makes it a
    # guarantee about files rather than about a path string: nothing that
    # implements a gate may sit outside scripts/ and escape both tools again.
    stray = sorted(
        path.relative_to(ROOT).as_posix()
        for path in ROOT.glob("*.py")
        if path.name not in {"conftest.py"}
    )
    assert stray == [], f"gate code outside src/, tests/ and scripts/: {stray}"
