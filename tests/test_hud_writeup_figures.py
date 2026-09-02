"""Every figure in the HUD calibration write-up, read out of the document and recomputed.

`tests/test_hud_suppression_calibration.py` recomputes the calibration from the committed
CSV and pins the result. Its module docstring says every number in
`docs/audits/hud-coc-suppression-calibration-2026-08-21.md` "is required to trace back to
`scripts/hud_suppression_calibration.calibrate()` ... not copied from a one-time notebook
run and pasted into prose."

It never opens the document. It compares `calibrate()` against integer and float literals
typed into the test, which were copied out of the same run that produced the prose. Two
independent hand-copies of one computation, with nothing comparing them to each other. The
engine was pinned; the write-up was not.

Demonstrated before this file existed: changing a headline row of the write-up's
suppression-rate table from `44.3%` to `4.3%` -- an order of magnitude, on the finding the
document calls "the finding worth taking seriously" -- left the whole suite green, including
the test named `test_calibration_matches_the_committed_write_up`.

So this file does what that name promised. It parses the document, and every number it finds
has to equal a value derived from `calibrate()` run fresh against the committed CSV. Nothing
is asserted against a literal.

**The rounding convention is derived too, not guessed.** `calibrate()` publishes each rate
already rounded to four decimal places, and the write-up rounds *that published value* to one
decimal place as a percentage, half away from zero. Ten of ten rate rows reproduce under that
rule, including `Veterans | 31.0%`, which comes from the published `0.3095` and not from the
unrounded 30.9458% -- a distinction a tolerance-based comparison would have papered over and a
naive re-derivation would have called drift.

The committed extract's SHA-256 is checked here too: three documents state it and nothing
recomputed it from the file.
"""

from __future__ import annotations

import hashlib
import re
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

from scripts.hud_suppression_calibration import CSV_PATH, calibrate

ROOT = Path(__file__).resolve().parents[1]
WRITEUP = ROOT / "docs" / "audits" / "hud-coc-suppression-calibration-2026-08-21.md"
SOURCE_RECORD = ROOT / "eval" / "hud" / "SOURCE.md"
DATA_CARD = ROOT / "docs" / "data" / "hud-coc-pit-subpopulations.md"

#: Every document that states the committed extract's digest. A digest repeated in three
#: places and recomputed in none is three chances to be wrong about one file.
DIGEST_DOCUMENTS = (WRITEUP, SOURCE_RECORD, DATA_CARD)

#: The write-up's row label for each subpopulation `calibrate()` reports. Both directions are
#: checked below, so a subpopulation added to the engine and not to the table fails here, and
#: so does a table row naming something the engine does not report.
RATE_ROW_LABELS = {
    "Overall Homeless (whole-CoC total)": "overall",
    "Chronically Homeless": "chronically_homeless",
    "Chronically Homeless Individuals": "chronically_homeless_individuals",
    "Chronically Homeless, People in Families": "chronically_homeless_in_families",
    "Unaccompanied Youth (Under 25)": "unaccompanied_youth_under25",
    "Unaccompanied Youth, Under 18": "unaccompanied_youth_under18",
    "Unaccompanied Youth, 18\u201324": "unaccompanied_youth_18to24",
    "Veterans": "veterans",
    "Parenting Youth (Under 25)": "parenting_youth_under25",
    "Children of Parenting Youth": "children_of_parenting_youth",
}


def _writeup() -> str:
    return WRITEUP.read_text(encoding="utf-8")


def _percent(value: float | Decimal) -> str:
    """A share, as the write-up writes it: one decimal place, half away from zero."""

    return str((Decimal(str(value)) * 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def _thousands(value: int) -> str:
    return f"{value:,}"


def _rows(text: str, header: str) -> dict[str, list[str]]:
    """The body rows of the one Markdown table whose header line is `header`.

    Emphasis is stripped from the cells: the write-up bolds its headline figures, and a gate
    that could be satisfied by removing the asterisks would be checking the wrong thing.
    """

    lines = text.splitlines()
    starts = [index for index, line in enumerate(lines) if line.strip() == header]
    assert len(starts) == 1, f"expected exactly one table headed {header!r}, found {len(starts)}"
    body: dict[str, list[str]] = {}
    for line in lines[starts[0] + 2 :]:
        if not line.startswith("|"):
            break
        cells = [cell.replace("**", "").strip() for cell in line.strip().strip("|").split("|")]
        body[cells[0]] = cells[1:]
    assert body, f"the table headed {header!r} has a header and no rows"
    return body


def _stated_once(text: str, phrase: str) -> None:
    """Assert a derived sentence fragment appears in the document exactly once."""

    count = text.count(phrase)
    assert count == 1, (
        f"the write-up states {phrase!r} {count} time(s), expected exactly once. Every number "
        f"in that document is derived from scripts/hud_suppression_calibration.calibrate(); "
        f"if the engine or the committed CSV changed, rewrite the prose to match rather than "
        f"relaxing this."
    )


def test_the_readers_find_the_figures_they_are_meant_to_police() -> None:
    """The guard against a green run that parsed nothing.

    Every assertion below rests on a parser locating a table or a sentence in a Markdown file.
    A regex that silently stops matching would turn all of them into checks that cannot fail,
    which is the exact defect this file was written to close.
    """
    rates = _rows(_writeup(), "| Subpopulation | Primary-suppression rate |")
    assert len(rates) == 10, f"parsed {len(rates)} rate rows out of the write-up, expected 10"
    assert all(value[0].endswith("%") for value in rates.values())

    cells = _rows(_writeup(), "| | Cells | Share of all 10,890 |")
    assert len(cells) == 3, f"parsed {len(cells)} rows out of the cells table, expected 3"

    example = _rows(_writeup(), "| Metric | Value | Suppressed? |")
    assert len(example) == 3, f"parsed {len(example)} rows out of the AK-500 table, expected 3"


def test_the_suppression_rate_table_states_the_rates_the_engine_produces() -> None:
    """THE GATE, on the write-up's central table.

    Ten rows, each recomputed. This is the table that carried `44.3%` for Parenting Youth
    while nothing in the repository would have noticed `4.3%`.
    """
    rates: dict[str, Any] = calibrate()["per_subpopulation_primary_suppression_rate"]
    stated = _rows(_writeup(), "| Subpopulation | Primary-suppression rate |")

    assert set(stated) == set(RATE_ROW_LABELS), (
        "the write-up's rate table and this gate's label map disagree: "
        f"unmapped rows {sorted(set(stated) - set(RATE_ROW_LABELS))}, "
        f"missing rows {sorted(set(RATE_ROW_LABELS) - set(stated))}"
    )
    assert set(RATE_ROW_LABELS.values()) == set(rates), (
        "the engine reports a different subpopulation set than the write-up tabulates: "
        f"untabulated {sorted(set(rates) - set(RATE_ROW_LABELS.values()))}"
    )

    wrong = {
        label: (stated[label][0], f"{_percent(rates[key])}%")
        for label, key in RATE_ROW_LABELS.items()
        if stated[label][0] != f"{_percent(rates[key])}%"
    }
    assert not wrong, (
        f"the write-up's rate table disagrees with a fresh calibration run "
        f"(row: stated, derived): {wrong}"
    )


def test_the_cells_table_states_the_counts_and_shares_the_engine_produces() -> None:
    result = calibrate()
    total = result["total_cells"]
    stated = _rows(_writeup(), "| | Cells | Share of all 10,890 |")

    derived = {
        "Primary-suppressed (magnitude 1\u201310)": (
            result["primary_suppressed_cells"],
            result["primary_suppressed_share"],
        ),
        "Complementary-suppressed (recoverable by arithmetic if left visible)": (
            result["complementary_suppressed_cells"],
            result["complementary_suppressed_cells"] / total,
        ),
        "Total withheld": (
            result["total_suppressed_cells"],
            result["total_suppressed_share"],
        ),
    }
    assert set(stated) == set(derived), (
        f"the cells table's rows are {sorted(stated)}, this gate derives {sorted(derived)}"
    )
    for label, (count, share) in derived.items():
        assert stated[label] == [_thousands(count), f"{_percent(share)}%"], (
            f"{label}: the write-up states {stated[label]}, a fresh run derives "
            f"[{_thousands(count)!r}, {_percent(share) + '%'!r}]"
        )

    # The header itself carries the denominator, so it cannot go stale unnoticed either.
    _stated_once(_writeup(), f"| | Cells | Share of all {_thousands(total)} |")


def test_the_worked_ak_500_example_states_the_values_the_committed_csv_holds() -> None:
    """The one named real example, read out of the write-up rather than out of memory."""

    from scripts.hud_suppression_calibration import load_rows

    ak_500 = {row["subpopulation"]: row for row in load_rows()["AK-500"]}
    stated = _rows(_writeup(), "| Metric | Value | Suppressed? |")
    derived = {
        "Unaccompanied youth, overall (under 25)": "unaccompanied_youth_under25",
        "Unaccompanied youth, 18\u201324 (overall)": "unaccompanied_youth_18to24",
        "Unaccompanied youth, under 18 (overall)": "unaccompanied_youth_under18",
    }
    assert set(stated) == set(derived), f"the AK-500 table's rows are {sorted(stated)}"
    for label, subpopulation in derived.items():
        expected = ak_500[subpopulation]["overall"]
        assert stated[label][0] == expected, (
            f"{label}: the write-up states {stated[label][0]}, the committed CSV holds {expected}"
        )

    # The arithmetic the example turns on, stated in the prose as well as the table.
    under25 = int(ak_500["unaccompanied_youth_under25"]["overall"])
    band = int(ak_500["unaccompanied_youth_18to24"]["overall"])
    _stated_once(_writeup(), f"`{under25} - {band} = {under25 - band}`")


def test_every_derived_sentence_in_the_prose_states_a_recomputed_number() -> None:
    """The figures that live in sentences rather than tables.

    Deliberately exhaustive over the load-bearing ones: the dataset's shape, the
    complementary-suppression finding, and the true-zero finding. Each is written out with
    every number it contains, so a single edited digit anywhere in the sentence fails.
    """
    result = calibrate()
    text = _writeup()
    cocs = result["cocs"]
    total = result["total_cells"]
    triples = result["total_triples"]
    with_any = result["cocs_with_any_suppression"]
    needing = result["cocs_needing_complementary_suppression"]

    for phrase in (
        # The data section: the shape of the extract.
        f"**{cocs} CoCs**, each with **{len(result['per_subpopulation_primary_suppression_rate'])}"
        " named subpopulation groups**",
        f"**{_thousands(total)} real,\npublished count cells**",
        f"unsheltered` for every one of the {_thousands(triples)} (CoC, subpopulation) rows",
        f"every one of the {cocs} CoCs",
        # The method section: the figure set each CoC is turned into.
        f"({total // cocs} count figures: "
        f"{len(result['per_subpopulation_primary_suppression_rate'])} subpopulations",
        # Finding 2: complementary suppression.
        f"{with_any} of {cocs} CoCs ({_percent(with_any / cocs)}%) have at least one cell",
        f"**{needing} ({_percent(result['cocs_needing_complementary_suppression_share'])}% of all"
        f" CoCs, {_percent(needing / with_any)}% of CoCs with any\nsuppressed cell)",
        # Finding 3: true zeros beside small cells.
        f"**{result['zero_adjacent_to_small_cell_triples']} of {_thousands(triples)} "
        f"(CoC, subpopulation) rows ({_percent(result['zero_adjacent_share'])}%)",
        f"{_thousands(result['true_zero_cells'])} of {_thousands(total)} cells "
        f"({_percent(result['true_zero_cells'] / total)}%) are true zeros",
        # The "we are stricter than HUD" misreading, which quotes the headline share back.
        f"we suppress {_percent(result['total_suppressed_share'])}%",
        # Scope discipline: the aggregate the document promises every figure is taken over.
        f"aggregate across all {cocs} CoCs",
    ):
        _stated_once(text, phrase)


def test_the_excluded_coc_count_is_arithmetic_the_document_can_be_held_to() -> None:
    """363 of the workbook's 390 rows are kept; 27 are excluded. Two of those three are
    facts about the uncommitted `.xlsb`, so only their relationship is checkable here --
    but it is checkable, and the three numbers appear in three different documents.
    """
    cocs = calibrate()["cocs"]
    for document in (WRITEUP, SOURCE_RECORD, DATA_CARD):
        text = document.read_text(encoding="utf-8")
        stated = {int(value) for value in re.findall(r"\b(\d+) of (?:the workbook's )?390\b", text)}
        stated |= {int(value) for value in re.findall(r"(\d+) of 390 CoC rows", text)}
        if not stated:
            continue
        for kept_or_dropped in stated:
            assert kept_or_dropped in {cocs, 390 - cocs}, (
                f"{document.name} says '{kept_or_dropped} of 390', but the committed extract "
                f"holds {cocs} CoCs, so the only consistent figures are {cocs} (kept) and "
                f"{390 - cocs} (excluded)"
            )


def test_every_document_stating_the_extracts_digest_states_the_files_digest() -> None:
    """Three documents assert the committed CSV's SHA-256. Nothing recomputed it.

    The digest is the extract's identity: `eval/hud/SOURCE.md` offers it as the thing a
    reader reproduces by re-running `extract.py` against a fresh copy of HUD's workbook. A
    digest nothing compares to the file is a claim about a file, made without looking at it.
    """
    digest = hashlib.sha256(CSV_PATH.read_bytes()).hexdigest()
    for document in DIGEST_DOCUMENTS:
        text = document.read_text(encoding="utf-8")
        stated = set(re.findall(r"\b([0-9a-f]{64})\b", text))
        assert digest in stated, (
            f"{document.name} states {sorted(stated)} but "
            f"{CSV_PATH.relative_to(ROOT)} hashes to {digest}"
        )


def test_the_two_records_of_the_source_workbooks_digest_agree_with_each_other() -> None:
    """The upstream `.xlsb` is not committed, so its digest cannot be recomputed here.

    What can be checked is that the two documents recording it record the same thing: it is
    one fact, hand-copied twice, and the copies are exactly as capable of disagreeing as the
    extract's digest was.
    """
    pattern = re.compile(r"Original file SHA-256:\*{0,2}\s*`([0-9a-f]{64})`")
    recorded = {
        document.name: pattern.search(document.read_text(encoding="utf-8"))
        for document in (WRITEUP, SOURCE_RECORD)
    }
    assert all(match is not None for match in recorded.values()), (
        f"a document stopped recording the source workbook's digest: "
        f"{[name for name, match in recorded.items() if match is None]}"
    )
    digests = {match.group(1) for match in recorded.values() if match is not None}
    assert len(digests) == 1, f"the two records of the source workbook's digest disagree: {digests}"
