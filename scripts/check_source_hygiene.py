"""Fail on source hygiene violations owned by the Code Quality standard."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIRS = (ROOT / "src", ROOT / "tests")
ISSUE = re.compile(r"\(#[0-9]+\)|https?://\S+/issues/[0-9]+")
MARKER = re.compile(r"\b(?:TODO|FIXME|HACK)\b")
SUPPRESSION = re.compile(r"#\s*(?:noqa|type:\s*ignore|nosemgrep)\b")


def main() -> int:
    """Check markers, suppressions, layout, and duplicate tool config."""

    failures: list[str] = []
    for base in SOURCE_DIRS:
        for path in sorted(base.rglob("*.py")):
            for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if (MARKER.search(line) or SUPPRESSION.search(line)) and not ISSUE.search(line):
                    failures.append(
                        f"{path.relative_to(ROOT)}:{line_number}: missing issue reference"
                    )

    forbidden = ("ruff.toml", "pytest.ini", "mypy.ini", "setup.py", "setup.cfg", "tox.ini")
    failures.extend(name for name in forbidden if (ROOT / name).exists())
    if not (ROOT / "src" / "outcome_receipts").is_dir():
        failures.append("src/outcome_receipts is missing")
    if not (ROOT / "tests").is_dir():
        failures.append("tests is missing")

    if failures:
        print("source hygiene failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print("source hygiene: pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
