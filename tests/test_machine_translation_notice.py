"""The machine-translation notice (owner decision, 2026-09-18).

The Spanish fixed copy ships labeled machine-translated rather than waiting for the human
review docs/I18N.md asks for. These fail if a Spanish report, its Word export, its trace page
or a Spanish portfolio index can be produced without the notice near its top, in both
languages -- and if an English artifact ever carries it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from outcome_receipts.cli import EXIT_OK, main
from outcome_receipts.copy import (
    MACHINE_TRANSLATED_LOCALES,
    MACHINE_TRANSLATION_NOTICE,
    SUPPORTED_LOCALES,
    Locale,
    is_machine_translated,
    machine_translation_notice_html,
    machine_translation_notice_markdown,
)
from outcome_receipts.docx import DOCX_NAME, read_docx
from outcome_receipts.grounding import find_numbers
from outcome_receipts.portfolio import render_index_html

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
GRANT = EXAMPLES / "grant-report" / "report.toml"

ES_LEAD, _ = MACHINE_TRANSLATION_NOTICE["es"]
EN_LEAD, _ = MACHINE_TRANSLATION_NOTICE["en"]


def _run(out: Path, *extra: str) -> int:
    ledger = out.parent / f"{out.name}-ledger.jsonl"
    return main(
        [
            *("run", "--config", str(GRANT), "--out", str(out), "--ledger", str(ledger)),
            *("--reproducible", "--approved-by", "CI"),
            *extra,
        ]
    )


def test_every_non_english_locale_is_machine_translated_until_a_review_is_recorded() -> None:
    others = [locale for locale in SUPPORTED_LOCALES if locale != "en"]
    assert others, "no non-English locale, so this proved nothing"
    for locale in others:
        assert locale in MACHINE_TRANSLATED_LOCALES
    assert not is_machine_translated("en")
    assert machine_translation_notice_markdown("en") is None
    assert machine_translation_notice_html("en") is None


@pytest.mark.parametrize("lang", ["es", "en"])
def test_the_notice_holds_nothing_the_grounding_gate_would_refuse(lang: Locale) -> None:
    # It sits in the report's narrative region, which the gate reads: a digit or a
    # written-out numeral ("una", "one") there would be an unbound number in every Spanish report.
    lead, body = MACHINE_TRANSLATION_NOTICE[lang]
    assert find_numbers(f"{lead} {body}") == []


def test_a_spanish_report_says_so_under_its_title_and_an_english_one_does_not(
    tmp_path: Path,
) -> None:
    es_out, en_out = tmp_path / "es", tmp_path / "en"
    assert _run(es_out, "--locale", "es") == EXIT_OK
    assert _run(en_out) == EXIT_OK

    lines = (es_out / "report.md").read_text(encoding="utf-8").splitlines()
    assert lines[0].startswith("# ")
    assert lines[1] == ""
    assert lines[2].startswith(f"**{ES_LEAD}**")
    assert lines[3] == ""
    assert lines[4].startswith(f"**{EN_LEAD}**")

    english = (en_out / "report.md").read_text(encoding="utf-8")
    assert ES_LEAD not in english
    assert EN_LEAD not in english


def test_the_spanish_trace_page_carries_it_first_in_main(tmp_path: Path) -> None:
    out = tmp_path / "es"
    assert _run(out, "--locale", "es") == EXIT_OK
    html = (out / "trace.html").read_text(encoding="utf-8")
    assert html.count("data-machine-translation-notice") == 1
    after_main = html.split("<main>", 1)[1].lstrip()
    assert after_main.startswith(
        '<div class="mt-notice" role="note" data-machine-translation-notice>'
    )
    assert f'<p lang="es"><strong>{ES_LEAD}</strong>' in after_main
    assert f'<p lang="en"><strong>{EN_LEAD}</strong>' in after_main
    assert after_main.index("data-machine-translation-notice") < after_main.index("<h1>")


def test_the_english_trace_page_does_not(tmp_path: Path) -> None:
    out = tmp_path / "en"
    assert _run(out) == EXIT_OK
    assert "data-machine-translation-notice" not in (out / "trace.html").read_text("utf-8")


def test_the_spanish_word_export_carries_it_because_it_says_what_report_md_says(
    tmp_path: Path,
) -> None:
    out = tmp_path / "es"
    assert _run(out, "--format", "docx", "--locale", "es") == EXIT_OK
    text = read_docx((out / DOCX_NAME).read_bytes()).text
    assert ES_LEAD in text
    assert EN_LEAD in text
    assert text.index(ES_LEAD) < text.index("Gráfico no incrustado en este documento")


def test_the_spanish_portfolio_index_carries_it_first_in_main() -> None:
    es = render_index_html((), (), locale="es")
    after_main = es.split("<main>", 1)[1].lstrip()
    assert after_main.startswith(
        '<div class="mt-notice" role="note" data-machine-translation-notice>'
    )
    assert "data-machine-translation-notice" not in render_index_html((), (), locale="en")
