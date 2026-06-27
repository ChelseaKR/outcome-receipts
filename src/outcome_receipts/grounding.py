"""The fail-closed grounding gate.

Given a drafted narrative and the figures computed for it, the gate finds every
number in the narrative and binds each to a figure whose display matches. A number
that matches no figure is unbound, and an unbound number blocks export. The gate
is mechanical: it does not ask a model whether the text "looks faithful", it
checks that each number traces to a receipt.

This is what lets a model draft the prose in a later version without being trusted
to invent the figures: whatever the drafter writes, the gate is the enforcement
that every number in it came from a receipt.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from outcome_receipts.models import Figure, GroundingResult, NumericSpan

# A number as it appears in prose: an integer or decimal, optional thousands
# separators, optional trailing percent sign. Years and list markers are numbers
# too; the gate treats every numeric span the same way, so a number that is not a
# figure (a stray "2024") is unbound and must be removed or made a figure. That
# strictness is the point.
_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?%?")


def _normalize(token: str) -> str:
    """Canonicalize a numeric token for comparison: drop thousands separators."""

    return token.replace(",", "")


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
