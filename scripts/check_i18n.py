"""Validate gettext catalog completeness, placeholders, locales, and encoding."""

from __future__ import annotations

import re
import sys
from pathlib import Path

from babel import Locale
from babel.messages import pofile

ROOT = Path(__file__).resolve().parents[1]
LOCALES = ROOT / "src" / "outcome_receipts" / "locales"
PLACEHOLDER = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


def _messages(locale: str) -> dict[str, str]:
    path = LOCALES / locale / "LC_MESSAGES" / "messages.po"
    with path.open(encoding="utf-8") as stream:
        catalog = pofile.read_po(stream, locale=locale)
    messages: dict[str, str] = {}
    for message in catalog:
        if not message.id or not isinstance(message.id, str):
            continue
        if "fuzzy" in message.flags or not message.string:
            raise ValueError(f"{path}: untranslated or fuzzy message {message.id!r}")
        if not isinstance(message.string, str):
            raise TypeError(f"{path}: plural message is not supported for {message.id!r}")
        messages[message.id] = message.string
    return messages


def _template_keys() -> set[str]:
    path = LOCALES / "messages.pot"
    with path.open(encoding="utf-8") as stream:
        catalog = pofile.read_po(stream)
    return {message.id for message in catalog if message.id and isinstance(message.id, str)}


def _encoding_failures() -> list[str]:
    failures: list[str] = []
    excluded = {
        ".git",
        ".venv",
        "node_modules",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".hypothesis",
        ".tools",
        "dist",
        "out",
    }
    for path in ROOT.rglob("*"):
        if excluded.intersection(path.parts) or not path.is_file():
            continue
        if path.name in {".coverage", ".DS_Store"} or path.suffix in {".png", ".mo", ".pyc"}:
            continue
        try:
            path.read_bytes().decode("utf-8")
        except UnicodeDecodeError:
            failures.append(f"non-UTF-8 tracked file: {path.relative_to(ROOT)}")
    return failures


def _catalog_failures(catalogs: dict[str, dict[str, str]], template_keys: set[str]) -> list[str]:
    failures: list[str] = []
    if not template_keys:
        failures.append("gettext extraction template is empty")
    for locale, messages in catalogs.items():
        if template_keys != messages.keys():
            failures.append(f"POT/{locale.upper()} gettext keys differ")
    if catalogs["en"].keys() != catalogs["es"].keys():
        failures.append("EN/ES gettext keys differ")
    for key, english in catalogs["en"].items():
        spanish = catalogs["es"].get(key)
        if spanish is not None and PLACEHOLDER.findall(english) != PLACEHOLDER.findall(spanish):
            failures.append(f"placeholder mismatch for {key}")
    return failures


def main() -> int:
    """Fail if catalogs or authored file encodings diverge."""

    failures: list[str] = []
    catalogs = {locale: _messages(locale) for locale in ("en", "es")}
    template_keys = _template_keys()
    failures.extend(_catalog_failures(catalogs, template_keys))
    for tag in catalogs:
        Locale.parse(tag, sep="-")

    failures.extend(_encoding_failures())

    if failures:
        print("i18n validation failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print(f"i18n catalogs: {len(template_keys)} extracted POT/EN/ES messages at parity")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
