"""Fail on source hygiene violations owned by the Code Quality standard."""

from __future__ import annotations

import re
import sys
import tokenize
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
#: `scripts/` is in scope with `src/` and `tests/`: it holds every
#: merge-blocking gate except the test suite, and an undocumented suppression
#: there matters at least as much as one in the library.
SOURCE_DIRS = ("src", "tests", "scripts")
ISSUE = re.compile(r"\(#[0-9]+\)|https?://\S+/issues/[0-9]+")
#: Assembled from fragments so this definition does not match itself. The
#: marker scan is deliberately line-based (a marker in a docstring is still
#: a marker), and `scripts/` is now in scope, so the pattern that defines the
#: rule would otherwise be the one line in the repository that violates it.
MARKER = re.compile(r"\b(?:TO" r"DO|FIX" r"ME|HA" r"CK)\b")
SUPPRESSION = re.compile(r"#\s*(?:noqa|type:\s*ignore|nosemgrep)\b")

FORBIDDEN_CONFIG = ("ruff.toml", "pytest.ini", "mypy.ini", "setup.py", "setup.cfg", "tox.ini")


def _comment_lines(path: Path) -> set[int] | None:
    """Line numbers carrying a real Python comment, or None if unparseable.

    A suppression directive only does anything in a comment. Read line by line,
    the same text inside a string literal counts too, so a test that exercises
    suppression handling (tests/test_semgrep_ledger.py) or a script that
    documents the syntax gets flagged for a suppression it does not have. None
    means the file could not be tokenized, and the caller then falls back to
    scanning every line, which over-reports rather than letting a real
    suppression through.
    """

    try:
        with path.open("rb") as stream:
            tokens = list(tokenize.tokenize(stream.readline))
    except (OSError, SyntaxError, UnicodeDecodeError, tokenize.TokenError):
        return None
    return {token.start[0] for token in tokens if token.type == tokenize.COMMENT}


def _file_failures(path: Path, root: Path) -> list[str]:
    """Every unreferenced marker or suppression in one Python file."""

    text = path.read_text(encoding="utf-8")
    comments = _comment_lines(path)
    failures: list[str] = []
    for number, line in enumerate(text.splitlines(), 1):
        in_comment = comments is None or number in comments
        flagged = MARKER.search(line) or (in_comment and SUPPRESSION.search(line))
        if flagged and not ISSUE.search(line):
            failures.append(f"{path.relative_to(root)}:{number}: missing issue reference")
    return failures


def hygiene_failures(root: Path) -> list[str]:
    """Marker, suppression, layout, and duplicate-tool-config failures."""

    failures: list[str] = []
    for name in SOURCE_DIRS:
        base = root / name
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            failures.extend(_file_failures(path, root))

    failures.extend(name for name in FORBIDDEN_CONFIG if (root / name).exists())
    if not (root / "src" / "outcome_receipts").is_dir():
        failures.append("src/outcome_receipts is missing")
    if not (root / "tests").is_dir():
        failures.append("tests is missing")
    return failures


def main() -> int:
    """Check markers, suppressions, layout, and duplicate tool config."""

    failures = hygiene_failures(ROOT)
    if failures:
        print("source hygiene failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print("source hygiene: pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
