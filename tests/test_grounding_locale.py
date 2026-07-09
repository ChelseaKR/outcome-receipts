"""Locale-aware number canonicalization in the grounding gate (FIX-13).

A figure display and a prose span that denote the same value must bind even when
they use different locale number formatting (thousands and decimal separators),
so localized (E9) report output can render the same receipted figure in either
language. The fail-closed invariant is preserved: a different value, a stray
number, or a written-out numeral stays unbound.

These are unit cases: they build ``Figure`` objects directly rather than running
the full compute pipeline, mirroring the style of ``test_grounding_gate.py``.
"""

from __future__ import annotations

from outcome_receipts.grounding import ground
from outcome_receipts.models import Figure, Receipt

# Narrow no-break space (U+202F) and no-break space (U+00A0): both are used as
# thousands separators in localized number formatting.
NNBSP = " "
NBSP = " "


def _figure(display: str, *, value: float = 0.0, metric_id: str = "m") -> Figure:
    """A Figure with the given display and a throwaway receipt.

    The gate compares canonicalized display strings, so the receipt fields other
    than presence do not affect binding; they are filled with stable placeholders.
    """

    receipt = Receipt(
        metric_id=metric_id,
        value_sql="SELECT 1",
        row_count=1,
        slice_hash="0" * 16,
        value=value,
        unit="count",
        computed_at="2026-01-01T00:00:00Z",
    )
    return Figure(metric_id=metric_id, value=value, display=display, receipt=receipt)


def test_thousands_grouped_figure_binds_across_locale_separators() -> None:
    # US comma grouping, European dot grouping, and the two no-break-space forms
    # real localized output uses for thousands all denote the same 1234 and bind.
    figures = [_figure("1,234", value=1234.0)]
    for prose in ("1,234", "1.234", f"1{NBSP}234", f"1{NNBSP}234"):
        result = ground(f"We served {prose} people.", figures)
        assert result.ok, f"{prose!r} should bind to figure display '1,234'"
        assert len(result.bound) == 1
        assert not result.unbound


def test_ascii_space_is_a_delimiter_not_a_thousands_separator() -> None:
    # Plain ASCII space separates distinct figures in the report (chart accessible
    # tables), so it must not group thousands: "1 234" is two spans, not one 1234.
    figures = [_figure("1,234", value=1234.0)]
    result = ground("We served 1 234 people.", figures)
    assert not result.ok
    assert [span.text for span in result.unbound] == ["1", "234"]


def test_full_form_binds_across_us_and_european_grouping() -> None:
    # US "12,345.67" and European "12.345,67" both denote 12345.67. With both a
    # '.' and a ',' present, the right-most separator is the decimal and the other
    # groups thousands, so the two spellings canonicalize identically and bind.
    figures = [_figure("12,345.67", value=12345.67)]
    for prose in ("12,345.67", "12.345,67"):
        result = ground(f"Revenue was {prose} dollars.", figures)
        assert result.ok, f"{prose!r} should bind to figure display '12,345.67'"
        assert len(result.bound) == 1
        assert not result.unbound


def test_repeated_separator_reads_as_thousands_groups() -> None:
    # A separator that appears more than once can only be grouping thousands, so
    # "1,234,567" and "1.234.567" (and the NBSP form) all denote 1234567 and bind.
    figures = [_figure("1,234,567", value=1234567.0)]
    for prose in ("1,234,567", "1.234.567", f"1{NBSP}234{NBSP}567"):
        result = ground(f"We reached {prose} in total.", figures)
        assert result.ok, f"{prose!r} should bind to figure display '1,234,567'"
        assert len(result.bound) == 1


def test_decimal_figure_binds_comma_decimal() -> None:
    figures = [_figure("3.5", value=3.5)]
    result = ground("The rate was 3,5 on average.", figures)
    assert result.ok
    assert len(result.bound) == 1


def test_percent_figure_binds_percent_span() -> None:
    figures = [_figure("42%", value=42.0)]
    result = ground("That is 42% of the cohort.", figures)
    assert result.ok
    assert [span.text for span in result.bound] == ["42%"]


def test_stray_year_stays_unbound() -> None:
    figures = [_figure("1,234", value=1234.0)]
    result = ground("In 2024 we served 1.234 people.", figures)
    assert not result.ok
    assert [span.text for span in result.unbound] == ["2024"]
    assert any(span.text == "1.234" for span in result.bound)


def test_different_value_stays_unbound() -> None:
    figures = [_figure("1,234", value=1234.0)]
    result = ground("We served 1,235 people.", figures)
    assert not result.ok
    assert [span.text for span in result.unbound] == ["1,235"]


def test_written_out_numeral_is_not_a_span_and_never_binds() -> None:
    # A written-out numeral carries no digits, so it is never parsed as a numeric
    # span and therefore never binds; the gate stays fail-closed on it.
    figures = [_figure("12", value=12.0)]
    result = ground("We served twelve families.", figures)
    assert result.total == 0
    assert not result.bound
    assert not result.unbound
