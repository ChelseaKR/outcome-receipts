"""Committed bilingual benchmark for the fail-closed numeric grounding gate."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from outcome_receipts.grounding import ground
from outcome_receipts.models import Figure, Receipt

# No-break space: a real thousands separator in localized number formatting, and
# one no English-convention case ever contains.
NBSP = "\u00a0"

BENCHMARK = Path(__file__).resolve().parents[1] / "eval" / "grounding-benchmark.jsonl"
CASES = [json.loads(line) for line in BENCHMARK.read_text(encoding="utf-8").splitlines()]


def _figure(display: str) -> Figure:
    """A figure whose display is the benchmark's, receipt fields aside.

    The gate compares display forms, so the receipt's own numerics do not affect
    binding; they are placeholders. In particular the display is not parseable as
    a float for most formatting cases (``"$12,345.67"``, ``"30 days"``), which is
    the point of those cases.
    """

    receipt = Receipt(
        metric_id="served",
        value_sql="SELECT COUNT(*) FROM data",
        row_count=1,
        slice_hash="benchmark",
        value=0.0,
        unit="count",
        computed_at="1970-01-01T00:00:00+00:00",
    )
    return Figure(metric_id="served", value=0.0, display=display, receipt=receipt)


def test_benchmark_shape_and_language_balance() -> None:
    english = [case for case in CASES if case["language"] == "en"]
    spanish = [case for case in CASES if case["language"] == "es"]

    assert len(english) == len(spanish) == len(CASES) // 2
    assert sum(bool(case["should_pass"]) for case in english) == sum(
        bool(case["should_pass"]) for case in spanish
    )
    assert len({case["id"] for case in CASES}) == len(CASES)


def test_benchmark_exercises_the_locale_handling_it_claims_to() -> None:
    """The benchmark must be able to fail for a locale-formatting reason.

    Before issue #80 it could not: all 100 cases used bare three-digit integers
    with the same integer as the display, so no case contained a decimal
    separator, a thousands separator, a percent, a currency symbol, or an NBSP
    group, and the fifty Spanish cases exercised the same code path as the fifty
    English ones. This asserts the formatting family is present and that its
    Spanish half is written in Spanish number convention rather than English
    formatting inside Spanish prose.
    """

    formatting = [case for case in CASES if case.get("family") == "formatting"]
    assert formatting, "the formatting family is missing"

    shapes = {str(case["shape"]) for case in formatting}
    for required in (
        "grouped-count-nbsp",
        "money-both-separators",
        "percent-marker",
        "duration-unit-suffix",
        "rate-comma-decimal",
        "ambiguous-dot-for-grouped-count",
        "ambiguous-comma-for-decimal-rate",
        "leading-separator-decimal-for-count",
        "sub-one-rate-with-leading-zero",
    ):
        assert required in shapes, f"benchmark no longer covers {required}"

    # At least one Spanish case must use a comma as the decimal separator and at
    # least one a dot as a thousands group; both are absent from English
    # convention, so their presence is what proves the halves differ.
    spanish = [str(case["narrative"]) for case in formatting if case["language"] == "es"]
    assert any("3,5" in narrative for narrative in spanish)
    assert any("12.345,67" in narrative for narrative in spanish)
    assert any(NBSP in narrative for narrative in spanish)

    # And the ambiguous shape must be recorded as failing closed in both
    # languages, since that is the case the gate now refuses.
    ambiguous = [case for case in formatting if str(case["shape"]).startswith("ambiguous-")]
    assert {str(case["language"]) for case in ambiguous} == {"en", "es"}
    assert all(case["should_pass"] is False for case in ambiguous)


@pytest.mark.parametrize("case", CASES, ids=lambda case: str(case["id"]))
def test_bilingual_grounding_benchmark(case: dict[str, object]) -> None:
    display = str(case["display"])
    result = ground(str(case["narrative"]), [_figure(display)])
    assert result.ok is bool(case["should_pass"])
    # The expected count of unbound spans is recorded per case, so a failing case
    # cannot start failing on a different span than the planted one and still
    # count as a pass for the benchmark.
    assert len(result.unbound) == int(str(case["unbound"]))
