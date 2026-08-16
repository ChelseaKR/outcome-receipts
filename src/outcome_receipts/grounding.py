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
bind even when they use different thousands or decimal separators (US
"12,345.67", European "12.345,67", or NBSP-grouped "1\u00a0234"). Written-out
English and Spanish numerals ("twelve", "doce") are detected but never
canonicalized or bound: they are always unbound so a model cannot evade the gate
by spelling a number. Localized (E9) report output relies on this
canonicalization so the same receipted figure binds in either language's number
formatting.

Canonicalization preserves magnitude. That is not free, because one shape is
genuinely ambiguous: a single '.' or ',' splitting 1-3 digits from exactly 3
("1,234", "1.234") is a thousands group under one convention and a decimal point
under the other, and the two readings differ by a factor of a thousand. Reducing
both to the same token, which is what the gate used to do, let a narrative state
a cost per outcome of 1.234 and bind a receipt of 1,234 -- three orders of
magnitude, carrying a receipt that appeared to back it. So the two sides are no
longer symmetric. A *figure display* is never ambiguous: the engine writes every
display one way, so it is read that way. A *prose span* in that one shape is
refused a value reading and must instead match a display character for
character. Every other shape resolves on its own and still binds across
conventions. See ``_is_ambiguous``, ``_figure_keys``, ``_span_key``, and ADR
0011.

``ground`` answers "does this number trace to a receipt". That is the right
question for the export path, which grounds against the already-suppressed
figures. It is the wrong question on its own for a hand-written draft, where a
number can trace to a perfectly real receipt for a cell small-cell suppression
redacted -- fully receipted and still a disclosure. ``audit_narrative`` is the
gate for that path: it binds against the publishable set and reports a span that
states a redacted figure as its own category. See ``suppression``.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from outcome_receipts.models import (
    AuditResult,
    Figure,
    GroundingResult,
    NumericSpan,
    SuppressedSpan,
)

# A number as it appears in prose, tolerant of locale formatting, in three forms
# tried in order, each with an optional leading currency symbol:
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
# The ``$`` is captured so a money display (``$1,234.50``) is one span that
# normalizes to its figure. A trailing unit word (the ``days`` in a duration
# display) is not captured here on purpose: capturing an arbitrary following word
# would swallow the next prose word after any bare number and change what an
# unbound span reports; the suffix is instead stripped from the figure display in
# ``_presentational``, so a ``30 days`` display still binds the ``30`` a reader
# sees. Either '.' or ',' may be the decimal; ``_canonical`` resolves which for a
# figure display and ``_span_key`` refuses to guess for prose. Years and list
# markers are numbers as well; the gate treats every numeric span the same way,
# so a number that is not a figure (a stray "2024") is unbound and must be removed
# or made a figure. That strictness is the point.
_NUMBER = re.compile(
    r"(?<!\d)\$?[+-]?\d{1,3}(?:[\u00a0\u202f]\d{3})+(?:[.,]\d+)?%?"
    r"|(?<!\d)\$?[+-]?\d[\d.,]*\d%?"
    r"|(?<!\d)\$?[+-]?\d%?"
)

_NUMBER_WORD = re.compile(
    r"\b(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
    r"thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|"
    r"thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand|million|"
    r"billion|trillion|first|second|third|fourth|fifth|sixth|seventh|eighth|"
    r"ninth|tenth|cero|un[oa]?|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|"
    r"once|doce|trece|catorce|quince|dieciséis|dieciseis|veinte|treinta|cuarenta|"
    r"cincuenta|sesenta|setenta|ochenta|noventa|cien|ciento|mil|millón|millon|"
    r"millones|primero|primera|segundo|segunda|tercero|tercera)\b",
    re.IGNORECASE,
)

# Separators that only ever group thousands, never mark a decimal: they are
# stripped outright during canonicalization.
_GROUP_SPACES = ("\u00a0", "\u202f", " ")

# A trailing unit word on a figure display, e.g. the "days" in "30 days".
_UNIT_SUFFIX = re.compile(r"\s*[A-Za-z]+$")


def _single_separator_is_thousands(body: str, sep: str) -> bool:
    """Decide whether a lone '.'/',' groups thousands rather than marks a decimal.

    A single kind of separator is read as a thousands group when it occurs more
    than once (e.g. "1.234.567"), or when its one occurrence splits the digits
    into a leading run of 1-3 and a trailing run of exactly 3 ("1,234" / "1.234").
    Otherwise it is the decimal point ("3,5" / "3.5"). The rule only chooses which
    character is the radix point; it never adds or drops a digit.

    This is the *producer's* rule, and it is exact for a figure display: the
    engine writes every display in one format, with ',' grouping thousands and
    '.' marking the decimal, so a display's separators are never in question. It
    is not exact for prose, which is why ``_is_ambiguous`` exists.
    """

    if body.count(sep) > 1:
        return True
    left, _, right = body.partition(sep)
    return 1 <= len(left) <= 3 and len(right) == 3


def _presentational(token: str) -> str:
    """A numeric token stripped of decoration but with its separators intact.

    Removes a trailing unit word (the ``days`` of a duration display), a leading
    ``$``, and surrounding whitespace, and nothing else: the separators are what
    this form exists to preserve. Two tokens with this form equal are the same
    number written the same way, whatever convention the writer had in mind.
    """

    return _UNIT_SUFFIX.sub("", token.strip()).replace("$", "")


def _is_ambiguous(token: str) -> bool:
    """True when a prose token's one separator could be either radix or grouping.

    Exactly the shape 1-3 digits, one '.' or ',', then exactly 3 digits: "1,234"
    and "1.234" and "12,345%" and "$1.234". Under a thousands reading that is one
    thousand two hundred and thirty-four; under a decimal reading it is one and a
    bit. Nothing in the token says which, and the two differ by a factor of a
    thousand.

    Every other shape resolves on its own and is not ambiguous: two or more
    separators of one kind can only be grouping ("1.234.567"); both kinds
    together fix the right-most as the radix ("12.345,67"); a group that is not
    exactly three digits long cannot be a thousands group ("3,5", "0.30",
    "1.23456"); and the NBSP-style separators only ever group.
    """

    percent = token.endswith("%")
    body = token[:-1] if percent else token
    for space in _GROUP_SPACES:
        if space in body:
            return False
    if ("." in body) == ("," in body):
        # Neither separator, or both: nothing left to guess.
        return False
    sep = "." if "." in body else ","
    if body.count(sep) > 1:
        return False
    left, _, right = body.lstrip("+-").partition(sep)
    return 1 <= len(left) <= 3 and len(right) == 3


def _split_percent(token: str) -> tuple[str, str]:
    """``(body, "%" or "")``. The percent marker stays part of every compared
    form, so a bare number never binds a percent figure."""

    return (token[:-1], "%") if token.endswith("%") else (token, "")


def _display_value(display: str) -> str:
    """The value a *figure display* denotes, read the way the engine writes one.

    There is no ambiguity on this side and none is guessed at. Every display is
    produced by one formatter: ``,`` groups thousands and ``.`` marks the
    decimal, in every locale (figure displays do not change across ``--locale``).
    So ``12.345%`` is twelve point three four five percent, and reading it by the
    digit-shape heuristic below -- which would call it a thousands group and
    return twelve thousand -- is exactly the thousandfold error this function
    exists to avoid.
    """

    body, percent = _split_percent(_presentational(display))
    for space in _GROUP_SPACES:
        body = body.replace(space, "")
    return body.replace(",", "") + percent


def _prose_value(span: str) -> str:
    """The value an *unambiguous* prose span denotes, whatever convention it uses.

    Space-style separators only ever group and are removed. Both separators
    present fixes the right-most as the radix ("12.345,67" and "12,345.67" both
    reduce to "12345.67"). A single separator is resolved by shape, which is
    sound here because ``_span_key`` only calls this for spans whose shape
    resolves: a repeated separator can only group, and a group that is not
    exactly three digits long cannot be one ("3,5" is three and a half).

    The digits are not renormalized beyond that: "0.30" and "0.3" stay distinct,
    because a figure has one canonical display (ADR 0004) and matching is exact.
    """

    body, percent = _split_percent(_presentational(span))
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


def _figure_keys(display: str) -> set[str]:
    """The forms a figure display may be matched on.

    Two, and they are not interchangeable. ``_display_value`` is the value the
    display denotes; an unambiguous prose span binds against it whatever
    convention the writer used, which is what makes localized prose work.
    ``_presentational`` is the display exactly as written, separators and all;
    an *ambiguous* prose span binds only against this, so it has to have been
    written the way the receipt writes it.
    """

    return {_display_value(display), _presentational(display)}


def _span_key(text: str) -> str:
    """The single form a prose span is allowed to match on.

    An unambiguous span reduces to its value, so it binds a receipt written in
    any convention. An ambiguous one reduces to itself, so it binds only a
    receipt that writes the number the same way -- which is the whole fix. A
    receipted count of 1,234 and a receipted rate of 1.234 are a thousandfold
    apart and used to canonicalize to the same token, so a narrative could state
    either one and bind the other. Now "1.234" in prose reaches a count of 1,234
    only if the report actually displays it as "1.234", which it does not.

    The cost is a span written in a convention the report does not use, in that
    one shape, going unbound: a Spanish-convention "1.234" for a receipted
    "1,234" is refused rather than guessed at. That is the fail-closed direction
    and it is visible to the author, who is told the number does not bind and can
    write it as the receipt does.
    """

    presentational = _presentational(text)
    return presentational if _is_ambiguous(presentational) else _prose_value(text)


def find_numbers(text: str) -> list[NumericSpan]:
    """Return every numeric span in the text, in order."""

    spans = [
        NumericSpan(text=match.group(0), start=match.start(), end=match.end())
        for pattern in (_NUMBER, _NUMBER_WORD)
        for match in pattern.finditer(text)
    ]
    return sorted(spans, key=lambda span: span.start)


def ground(text: str, figures: Sequence[Figure]) -> GroundingResult:
    """Bind every number in ``text`` to a figure display, fail-closed.

    A span is bound when its key (see ``_span_key``) is one of the keys some
    figure display offers (see ``_figure_keys``). Anything else is unbound. The
    result is ``ok`` only when nothing is unbound.
    """

    allowed = {key for figure in figures for key in _figure_keys(figure.display)}
    bound: list[NumericSpan] = []
    unbound: list[NumericSpan] = []
    for span in find_numbers(text):
        if _NUMBER_WORD.fullmatch(span.text):
            unbound.append(span)
        elif _span_key(span.text) in allowed:
            bound.append(span)
        else:
            unbound.append(span)
    return GroundingResult(bound=tuple(bound), unbound=tuple(unbound))


def audit_narrative(
    text: str,
    publishable: Sequence[Figure],
    suppressed: Sequence[Figure],
) -> AuditResult:
    """Ground ``text`` against what the report may publish, not against raw figures.

    ``publishable`` is the post-suppression figure set -- exactly what
    ``receipts run`` exports. ``suppressed`` is the *pre*-suppression form of the
    figures suppression redacted, carrying their raw displays; it is the only
    thing here that knows what a protected cell actually says, and it exists so a
    number matching one can be named as a disclosure instead of silently binding.

    Grounding against ``publishable`` alone would report a protected cell as
    merely "unbound", which reads as a missing metric and sends the author
    looking for a spec change rather than telling them they are about to publish
    a count of six people. So a span is tested against the suppressed set first:
    if it states a redacted figure it is a disclosure, whatever else it also
    matches. That ordering is deliberate and is the fail-closed direction -- a
    number that is simultaneously a publishable figure and a protected cell's raw
    value cannot be resolved from the text, so it is reported as a disclosure and
    flagged ambiguous rather than quietly counted as bound.

    Written-out numerals are unbound here exactly as in ``ground``; the gate
    never converts a word into a value, so "six" cannot be checked against a
    suppressed cell either. It blocks export on its own account.
    """

    allowed: dict[str, list[str]] = {}
    for figure in publishable:
        for key in _figure_keys(figure.display):
            allowed.setdefault(key, []).append(figure.metric_id)
    hidden: dict[str, list[str]] = {}
    for figure in suppressed:
        for key in _figure_keys(figure.display):
            hidden.setdefault(key, []).append(figure.metric_id)

    bound: list[NumericSpan] = []
    disclosed: list[SuppressedSpan] = []
    unbound: list[NumericSpan] = []
    for span in find_numbers(text):
        if _NUMBER_WORD.fullmatch(span.text):
            unbound.append(span)
            continue
        token = _span_key(span.text)
        if token in hidden:
            disclosed.append(
                SuppressedSpan(
                    span=span,
                    metric_ids=tuple(sorted(hidden[token])),
                    publishable_metric_ids=tuple(sorted(allowed.get(token, ()))),
                )
            )
        elif token in allowed:
            bound.append(span)
        else:
            unbound.append(span)
    return AuditResult(
        bound=tuple(bound),
        suppressed=tuple(disclosed),
        unbound=tuple(unbound),
    )


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
