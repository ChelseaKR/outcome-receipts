"""The fail-closed grounding gate.

Given a drafted narrative and the figures computed for it, the gate finds every
number in the narrative and binds each to a figure whose display matches. A number
that matches no figure is unbound, and an unbound number blocks export. The gate
is mechanical: it does not ask a model whether the text "looks faithful", it
checks that each number traces to a receipt.

This is what lets a model draft the prose in a later version without being trusted
to invent the figures: whatever the drafter writes, the gate is the enforcement
that every number in it came from a receipt.

Numbers are canonicalized before comparison so that locale formatting does not
defeat the gate: a figure display and a prose span that denote the same value
bind even when they use different thousands or decimal separators (US "1,234",
European "1.234", or NBSP-grouped "1 234"). Written-out numerals ("twelve",
"doce") are NOT yet canonicalized; they carry no digits, are never parsed as a
numeric span, and therefore remain unbound (fail-closed) rather than binding by
accident. Localized (E9) report output relies on this canonicalization so the
same receipted figure binds in either language's number formatting.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from outcome_receipts.models import Figure, GroundingResult, NumericSpan

# A number as it appears in prose, tolerant of locale formatting, in three forms
# tried in order:
#   1. NBSP-grouped thousands: 1-3 leading digits then one or more groups of
#      exactly 3 digits separated by NBSP (U+00A0) or narrow NBSP (U+202F), with
#      an optional '.'/',' decimal tail and optional '%'. These are the space
#      characters real localized number formatting (e.g. French) uses for
#      thousands. Plain ASCII space is deliberately NOT a grouping separator: the
#      report renders space-separated lists of distinct figures (chart accessible
#      tables, "13 3 2 999"), and treating ASCII space as a thousands separator
#      would merge "2 999" into one span and hide an ungrounded number. Localized
#      output never uses ASCII space to group, so nothing binds worse for it.
#   2. Dot/comma-grouped or decimal: a digit run carrying '.'/',' as thousands
#      and/or decimal ("1,234", "1.234", "12,345.67", "3.5", "3,5").
#   3. A lone digit, with optional '%'.
# Either '.' or ',' may be the decimal; _normalize resolves which. Years and list
# markers are numbers as well; the gate treats every numeric span the same way,
# so a number that is not a figure (a stray "2024") is unbound and must be removed
# or made a figure. That strictness is the point.
_NUMBER = re.compile(
    r"\d{1,3}(?:[  ]\d{3})+(?:[.,]\d+)?%?"  # 1: NBSP-grouped thousands
    r"|\d[\d.,]*\d%?"  # 2: dot/comma-grouped or decimal
    r"|\d%?"  # 3: lone digit
)

# Separators that only ever group thousands, never mark a decimal: they are
# stripped outright during canonicalization.
_GROUP_SPACES = (" ", " ", " ")


def _single_separator_is_thousands(body: str, sep: str) -> bool:
    """Decide whether a lone '.'/',' groups thousands rather than marks a decimal.

    A single kind of separator is read as a thousands group when it occurs more
    than once (e.g. "1.234.567"), or when its one occurrence splits the digits
    into a leading run of 1-3 and a trailing run of exactly 3 ("1,234" / "1.234").
    Otherwise it is the decimal point ("3,5" / "3.5"). The rule only chooses which
    character is the radix point; it never adds or drops a digit. When the split
    is ambiguous it favors the thousands reading only for the canonical 1-3 + 3
    shape, so a legitimately-receipted grouped figure can still bind.
    """

    if body.count(sep) > 1:
        return True
    left, _, right = body.partition(sep)
    return 1 <= len(left) <= 3 and len(right) == 3


def _normalize(token: str) -> str:
    """Canonicalize a numeric token so locale formatting does not defeat the gate.

    Both a figure's display and a prose span are passed through this function, so
    the goal is that any two spellings of the same value transform to the same
    string. A trailing '%' is preserved (kept part of the compared form, matching
    the gate's existing semantics). Space-style thousands separators are removed;
    then '.'/',' are resolved to a single '.' decimal point using the rule above.
    """

    percent = "%" if token.endswith("%") else ""
    body = token[:-1] if percent else token
    for space in _GROUP_SPACES:
        body = body.replace(space, "")

    has_dot = "." in body
    has_comma = "," in body
    if has_dot and has_comma:
        # The right-most of the two is the decimal; the other groups thousands.
        decimal = "." if body.rfind(".") > body.rfind(",") else ","
        thousands = "," if decimal == "." else "."
        body = body.replace(thousands, "").replace(decimal, ".")
    elif has_dot or has_comma:
        sep = "." if has_dot else ","
        if _single_separator_is_thousands(body, sep):
            body = body.replace(sep, "")
        else:
            body = body.replace(sep, ".")

    return body + percent


def find_numbers(text: str) -> list[NumericSpan]:
    """Return every numeric span in the text, in order."""

    return [
        NumericSpan(text=match.group(0), start=match.start(), end=match.end())
        for match in _NUMBER.finditer(text)
    ]


def ground(text: str, figures: Sequence[Figure]) -> GroundingResult:
    """Bind every number in ``text`` to a figure display, fail-closed.

    A span is bound when its normalized form equals the normalized display of some
    figure. Anything else is unbound. The result is ``ok`` only when nothing is
    unbound.
    """

    allowed = {_normalize(figure.display) for figure in figures}
    bound: list[NumericSpan] = []
    unbound: list[NumericSpan] = []
    for span in find_numbers(text):
        if _normalize(span.text) in allowed:
            bound.append(span)
        else:
            unbound.append(span)
    return GroundingResult(bound=tuple(bound), unbound=tuple(unbound))


def redact_unbound(text: str, result: GroundingResult, *, marker: str = "[UNVERIFIED]") -> str:
    """Replace every unbound numeric span with a marker.

    Used when a caller wants the narrative with ungrounded numbers stripped rather
    than the whole export blocked. Spans are replaced from the end so earlier
    offsets stay valid.
    """

    out = text
    for span in sorted(result.unbound, key=lambda s: s.start, reverse=True):
        out = out[: span.start] + marker + out[span.end :]
    return out
