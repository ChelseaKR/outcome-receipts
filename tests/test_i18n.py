"""Regression tests for source extraction and committed gettext catalogs."""

from __future__ import annotations

from collections.abc import Callable
from io import BytesIO
from pathlib import Path
from typing import IO, Any, cast

from babel.messages import mofile, pofile
from babel.messages.extract import extract_from_dir
from babel.messages.frontend import parse_mapping_cfg

ROOT = Path(__file__).resolve().parents[1]
LOCALES = ROOT / "src" / "outcome_receipts" / "locales"


def _catalog_keys(path: Path) -> set[str]:
    with path.open(encoding="utf-8") as stream:
        catalog = pofile.read_po(stream)
    return {message.id for message in catalog if message.id and isinstance(message.id, str)}


def test_source_extraction_is_nonempty_and_matches_every_catalog() -> None:
    parse_mapping = cast(
        Callable[
            [IO[str], str],
            tuple[list[tuple[str, str]], dict[str, dict[str, Any]]],
        ],
        parse_mapping_cfg,
    )
    with (ROOT / "babel.cfg").open(encoding="utf-8") as mapping_file:
        method_map, options_map = parse_mapping(mapping_file, "babel.cfg")
    extracted = {
        message
        for _filename, _line, message, _comments, _context in extract_from_dir(
            ROOT / "src", method_map, options_map
        )
        if isinstance(message, str)
    }

    assert extracted
    assert extracted == _catalog_keys(LOCALES / "messages.pot")
    assert extracted == _catalog_keys(LOCALES / "en" / "LC_MESSAGES" / "messages.po")
    assert extracted == _catalog_keys(LOCALES / "es" / "LC_MESSAGES" / "messages.po")


def _compile_catalog(path: Path) -> bytes:
    with path.open(encoding="utf-8") as stream:
        catalog = pofile.read_po(stream)
    output = BytesIO()
    mofile.write_mo(output, catalog)
    return output.getvalue()


def test_compiled_catalogs_are_byte_reproducible() -> None:
    """PO metadata must be explicit so Babel cannot inject the current time."""

    for language in ("en", "es"):
        messages = LOCALES / language / "LC_MESSAGES"
        compiled = _compile_catalog(messages / "messages.po")
        assert compiled == _compile_catalog(messages / "messages.po")
        assert compiled == (messages / "messages.mo").read_bytes()
