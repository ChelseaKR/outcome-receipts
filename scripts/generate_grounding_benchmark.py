"""Regenerate the committed bilingual grounding benchmark.

Two families of cases.

The *volume* family is 100 cases of a bare three-digit integer, half English and
half Spanish, half of them with an invented number planted beside the receipted
one. They exercise detection and the fail-closed rule at volume.

The *formatting* family is the part that exercises what the module docstring
calls the hard bit: thousands and decimal separators in both conventions, NBSP
grouping, percent markers, currency symbols, unit suffixes, and the ambiguous
1-3 + 3 shape where a single separator could be either. Before issue #80 the
benchmark could not fail for any reason relating to locale handling at all: all
100 cases used bare integers with the same integer as the display, so the fifty
Spanish cases exercised precisely the same code path as the fifty English ones.
The Spanish half here writes numbers in Spanish convention rather than English
formatting inside Spanish prose, which is what makes it a different path.

``unbound`` is recorded per case, not just ``should_pass``, so a case cannot
start passing for the wrong reason: a failing case that begins failing on a
different span than the planted one is a drift the benchmark should catch.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "eval" / "grounding-benchmark.jsonl"

NBSP = "\u00a0"

# (shape, display, English prose, Spanish prose, should_pass, unbound)
#
# ``display`` is a figure display as the engine writes one: ',' groups thousands
# and '.' marks the decimal, in every locale. The prose is what a person writes.
_FORMATTING: tuple[tuple[str, str, str, str, bool, int], ...] = (
    (
        "grouped-count-own-convention",
        "1,234",
        "We served 1,234 people.",
        "Atendimos a 1,234 personas.",
        True,
        0,
    ),
    (
        "grouped-count-nbsp",
        "1,234",
        f"We served 1{NBSP}234 people.",
        f"Atendimos a 1{NBSP}234 personas.",
        True,
        0,
    ),
    (
        "grouped-count-repeated-separator",
        "1,234,567",
        "We reached 1.234.567 in total.",
        "Alcanzamos 1.234.567 en total.",
        True,
        0,
    ),
    (
        "money-both-separators",
        "$12,345.67",
        "Revenue was $12,345.67 for the period.",
        "Los ingresos fueron de 12.345,67 en el periodo.",
        True,
        0,
    ),
    (
        "rate-comma-decimal",
        "3.5",
        "The average rate was 3.5 per household.",
        "La tasa media fue de 3,5 por hogar.",
        True,
        0,
    ),
    (
        "percent-marker",
        "42%",
        "That is 42% of the cohort.",
        "Eso es el 42% del grupo.",
        True,
        0,
    ),
    (
        "duration-unit-suffix",
        "30 days",
        "The median stay was 30 days.",
        "La estancia media fue de 30 días.",
        True,
        0,
    ),
    (
        "rate-three-decimals-own-convention",
        "1.234",
        "The cost per outcome ratio is 1.234.",
        "La razón de coste por resultado es 1.234.",
        True,
        0,
    ),
    # The ambiguous shape. Each of these states a number a thousand times the
    # receipt, or a thousandth of it, and each of them used to bind.
    (
        "ambiguous-dot-for-grouped-count",
        "1,234",
        "The cost per outcome ratio is 1.234.",
        "La razón de coste por resultado es 1.234.",
        False,
        1,
    ),
    (
        "ambiguous-comma-for-decimal-rate",
        "1.234",
        "The cost ratio moved to 1,234 this quarter.",
        "La razón de coste subió a 1,234 este trimestre.",
        False,
        1,
    ),
    (
        "ambiguous-percent",
        "12.345%",
        "The rate was 12,345%.",
        "La tasa fue del 12,345%.",
        False,
        1,
    ),
    (
        "ambiguous-money",
        "$1.234",
        "We spent $1,234 on the program.",
        "Gastamos $1,234 en el programa.",
        False,
        1,
    ),
    (
        "ambiguous-duration",
        "1.234 days",
        "The average stay was 1,234 days.",
        "La estancia media fue de 1,234 días.",
        False,
        1,
    ),
    (
        "off-by-one",
        "1,234",
        "We served 1,235 people.",
        "Atendimos a 1,235 personas.",
        False,
        1,
    ),
    (
        "stray-year",
        "1,234",
        "In 2024 we served 1,234 people.",
        "En 2024 atendimos a 1,234 personas.",
        False,
        1,
    ),
    (
        "written-numeral",
        "12",
        "We served twelve families.",
        "Atendimos a doce familias.",
        False,
        1,
    ),
)


def _volume_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for language in ("en", "es"):
        for offset in range(25):
            value = 100 + offset
            served = (
                f"We served {value} people."
                if language == "en"
                else f"Atendimos a {value} personas."
            )
            rows.append(
                {
                    "id": f"{language}-grounded-{offset:02d}",
                    "language": language,
                    "family": "volume",
                    "display": str(value),
                    "narrative": served,
                    "should_pass": True,
                    "unbound": 0,
                }
            )
            invented = (
                f"We served {value} people and invented {900 + offset}."
                if language == "en"
                else f"Atendimos a {value} personas e inventamos {900 + offset}."
            )
            rows.append(
                {
                    "id": f"{language}-injected-{offset:02d}",
                    "language": language,
                    "family": "volume",
                    "display": str(value),
                    "narrative": invented,
                    "should_pass": False,
                    "unbound": 1,
                }
            )
    return rows


def _formatting_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for shape, display, english, spanish, should_pass, unbound in _FORMATTING:
        for language, narrative in (("en", english), ("es", spanish)):
            rows.append(
                {
                    "id": f"{language}-format-{shape}",
                    "language": language,
                    "family": "formatting",
                    "shape": shape,
                    "display": display,
                    "narrative": narrative,
                    "should_pass": should_pass,
                    "unbound": unbound,
                }
            )
    return rows


def main() -> None:
    """Write stable EN/ES pass and planted-failure cases."""

    rows = [*_volume_rows(), *_formatting_rows()]
    OUT.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
