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

import hashlib
import itertools
import re
from collections.abc import Sequence

from outcome_receipts.models import (
    AuditResult,
    Explanation,
    Figure,
    GroundingResult,
    NumericSpan,
    SpanCandidate,
    SuppressedSpan,
)

# A number as it appears in prose, tolerant of locale formatting, in four forms,
# each with an optional leading currency symbol. Form 4 is tried first and the
# rest in the order listed, for the reason form 4 records:
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
#   4. A decimal written without its leading zero: a '.'/',' that is not itself
#      preceded by a digit, then a digit run (".75", "$.99", "-.5", ",75"). This
#      alternative is tried first, because the three above all require the match
#      to *start* on a digit and so match a leading-separator decimal one
#      character late: ".75" came back as the span "75", the dot silently outside
#      the match, and that span then bound a receipted count of 75. A rate
#      written the ordinary English way ("a retention rate of .75") therefore
#      carried a receipt for a number two orders of magnitude away from it. The
#      separator is inside the span now, so _span_key reads ".75" as its own
#      value and it binds only a display written the same way. No display is
#      written that way -- every display comes out of engine._format, which
#      always writes the integer part -- so a leading-separator decimal is
#      unbound, which is the fail-closed direction and is visible to the author.
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
    r"(?<!\d)\$?[+-]?[.,]\d+%?"
    r"|(?<!\d)\$?[+-]?\d{1,3}(?:[\u00a0\u202f]\d{3})+(?:[.,]\d+)?%?"
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


# --------------------------------------------------------------------------
# Diagnosis: why a span did not bind, and what receipted display it may have meant
#
# Everything below is advice. It reads the same canonicalization the gate reads
# (`_figure_keys`, `_span_key`, `_is_ambiguous`), so it cannot contradict a
# verdict, and it is never consulted when a verdict is formed: `ground` and
# `audit_narrative` above are untouched by it. `explain_audit` returns a *copy*
# of an AuditResult with the diagnoses attached; `ok` and `total` do not read
# them, so the gate's exit code is the same whether or not a caller asks.
# --------------------------------------------------------------------------

#: Reason classes, most specific first. The order is the ranking `_rank` uses:
#: a candidate whose *form* explains the miss outranks one that is merely
#: numerically close, because the former names a mistake and the latter only
#: measures a gap.
_REASON_ORDER = (
    "separator_ambiguity",
    "percent_as_count",
    "magnitude",
    "rounding",
    "nearest",
)

#: How close two same-shaped numbers must be before the nearer is worth naming.
#: A relative gap wider than this is a different figure, not a typo, and
#: offering it as "the display you probably meant" would be a guess dressed as a
#: measurement. 1,234 against a receipted 1,235 is 8e-4 and is named; 1,234
#: against a receipted 4,001 is 0.69 and is not.
_NEAREST_RELATIVE_TOLERANCE = 0.05

#: ...but a gap of one is always worth naming, whatever the magnitude. A
#: relative window alone is blind exactly where hand-typed numbers go wrong most
#: often: 11 against a receipted 10 is a relative gap of 0.09 and would fall
#: outside a 5% window, while being the commonest miss there is. The floor is
#: absolute so an off-by-one is diagnosed at every scale.
_NEAREST_ABSOLUTE_FLOOR = 1.0

_NON_DIGIT = re.compile(r"\D")


def _rank(reason: str) -> int:
    return _REASON_ORDER.index(reason)


def _as_number(key: str) -> tuple[float, bool] | None:
    """``(value, is_percent)`` for a canonicalized key, or ``None``.

    The key must already have come through ``_display_value`` or
    ``_prose_value``, which leave '.' as the only separator, so ``float`` is
    exact here. ``None`` is returned for anything that does not parse -- an
    ambiguous prose token reduced to its presentational form, for instance --
    and every caller treats ``None`` as "no numeric comparison is available",
    never as zero.
    """

    body, percent = _split_percent(key)
    try:
        return float(body), bool(percent)
    except ValueError:
        return None


def _decimals(key: str) -> int:
    """Decimal places carried by a canonicalized key."""

    body, _ = _split_percent(key)
    _, _, fraction = body.partition(".")
    return len(fraction)


def _digit_run(token: str) -> str:
    """Just the digits of a token, separators and decoration discarded.

    Used only to recognize a magnitude slip: "12.34" and "1,234" carry the same
    digits in the same order and differ by a factor of a hundred, which is the
    error ADR 0011 is about. Two numbers whose digit runs differ are not that
    error, however close they are numerically.
    """

    return _NON_DIGIT.sub("", token)


def _ambiguous_readings(token: str) -> tuple[str, str]:
    """The two value keys an ambiguous prose token could denote.

    ``("1234", "1.234")`` for "1,234": the thousands reading and the decimal
    reading. Only called for tokens ``_is_ambiguous`` accepted, so exactly one
    separator is present and it splits 1-3 digits from exactly 3.
    """

    body, percent = _split_percent(_presentational(token))
    separator = "." if "." in body else ","
    return (
        body.replace(separator, "") + percent,
        body.replace(separator, ".") + percent,
    )


def _candidates_for_ambiguous(token: str, by_key: dict[str, list[Figure]]) -> list[SpanCandidate]:
    """Displays an ADR 0011 ambiguous span would have bound, written their way.

    The span was refused a value reading on purpose (see ``_span_key``), so the
    remedy is never "we resolved it for you": it is "the report writes this
    figure exactly like this, so write it exactly like this". The candidate's
    display is the receipt's own string, character for character.
    """

    out: list[SpanCandidate] = []
    for reading in _ambiguous_readings(token):
        for figure in by_key.get(reading, ()):
            if _presentational(figure.display) == _presentational(token):
                # It would have bound; it is not an ambiguity failure.
                continue
            out.append(
                SpanCandidate(
                    metric_id=figure.metric_id,
                    display=figure.display,
                    reason="separator_ambiguity",
                    detail=(
                        f"{figure.metric_id} is {figure.display}; "
                        f"{token!r} could mean either of two values a thousand apart, "
                        f"so it binds only when written exactly as the receipt writes it"
                    ),
                )
            )
    return out


def _candidates_for_value(
    token: str, span_key: str, figures: Sequence[Figure]
) -> list[SpanCandidate]:
    """Near-miss diagnoses for a span whose value is not in question."""

    parsed = _as_number(span_key)
    if parsed is None:
        return []
    span_value, span_percent = parsed
    span_digits = _digit_run(_presentational(token))
    span_decimals = _decimals(span_key)

    out: list[SpanCandidate] = []
    for figure in figures:
        key = _display_value(figure.display)
        if key == span_key:
            # It bound; there is nothing to explain.
            continue
        other = _as_number(key)
        if other is None:
            continue
        value, percent = other
        difference = abs(span_value - value)

        if percent != span_percent and value == span_value:
            stated, meant = ("a count", "a percentage") if percent else ("a percentage", "a count")
            out.append(
                SpanCandidate(
                    metric_id=figure.metric_id,
                    display=figure.display,
                    reason="percent_as_count",
                    detail=(
                        f"{figure.metric_id} is {figure.display}; the narrative states "
                        f"the same digits as {stated} where the receipt is {meant}"
                    ),
                )
            )
            continue
        if percent != span_percent:
            continue

        if span_digits and span_digits == _digit_run(_presentational(figure.display)):
            factor = value / span_value if span_value else 0.0
            out.append(
                SpanCandidate(
                    metric_id=figure.metric_id,
                    display=figure.display,
                    reason="magnitude",
                    detail=(
                        f"{figure.metric_id} is {figure.display}, the same digits as "
                        f"{token!r} at {factor:g}x its magnitude -- check the "
                        f"thousands separator or the decimal point"
                    ),
                    distance=difference,
                )
            )
            continue

        rounds_together = (
            round(span_value, _decimals(key)) == value or round(value, span_decimals) == span_value
        )
        scale = max(abs(span_value), abs(value), 1.0)
        if rounds_together:
            out.append(
                SpanCandidate(
                    metric_id=figure.metric_id,
                    display=figure.display,
                    reason="rounding",
                    detail=(
                        f"{figure.metric_id} is {figure.display}; {token!r} is the same "
                        f"number rounded differently, and a display is matched exactly"
                    ),
                    distance=difference,
                )
            )
        elif difference <= max(_NEAREST_ABSOLUTE_FLOOR, _NEAREST_RELATIVE_TOLERANCE * scale):
            out.append(
                SpanCandidate(
                    metric_id=figure.metric_id,
                    display=figure.display,
                    reason="nearest",
                    detail=(
                        f"nearest: {figure.metric_id} {figure.display} (off by {difference:g})"
                    ),
                    distance=difference,
                )
            )
    return out


def _deduplicate(candidates: Sequence[SpanCandidate]) -> list[SpanCandidate]:
    """One candidate per (metric, reason), keeping the nearest.

    An ambiguous span is measured against both of its readings, so the same
    figure can be reached twice by the same reason class. Reporting it twice
    would also make it look like a tie to ``_tied_at_front`` and turn a clean
    single suggestion into a refusal.
    """

    nearest_first = sorted(
        candidates,
        key=lambda candidate: (
            candidate.distance is None,
            candidate.distance if candidate.distance is not None else 0.0,
        ),
    )
    best: dict[tuple[str, str], SpanCandidate] = {}
    for candidate in nearest_first:
        best.setdefault((candidate.metric_id, candidate.reason), candidate)
    return list(best.values())


def _ordered(candidates: Sequence[SpanCandidate]) -> tuple[SpanCandidate, ...]:
    """Candidates in a total, data-independent order.

    Sorted by reason rank, then numeric distance, then metric id. The metric id
    is the final key so the order does not depend on the order figures happened
    to be computed in: two runs over the same data produce the same fix plan,
    which is what makes ``apply_fixes`` reproducible.
    """

    return tuple(
        sorted(
            candidates,
            key=lambda candidate: (
                _rank(candidate.reason),
                candidate.distance if candidate.distance is not None else 0.0,
                candidate.metric_id,
            ),
        )
    )


def _tied_at_front(candidates: Sequence[SpanCandidate]) -> bool:
    """True when nothing distinguishes the first candidate from the second.

    Two candidates of the same reason class at the same distance are equally
    near, and there is nothing in the text to choose between them. That is the
    case ``apply_fixes`` refuses.
    """

    if len(candidates) < 2:
        return False
    first, second = candidates[0], candidates[1]
    return first.reason == second.reason and first.distance == second.distance


def explain_span(span: NumericSpan, publishable: Sequence[Figure]) -> Explanation:
    """Diagnose one unbound span against the publishable figure set."""

    if _NUMBER_WORD.fullmatch(span.text):
        return Explanation(
            span=span,
            remedy="none",
            detail=(
                f"{span.text!r} is a written-out numeral. The gate never converts a word "
                f"into a value, so it can never bind: write the digits of a receipted "
                f"figure, or remove the number"
            ),
        )

    token = _presentational(span.text)
    by_key: dict[str, list[Figure]] = {}
    for figure in publishable:
        for key in _figure_keys(figure.display):
            by_key.setdefault(key, []).append(figure)

    if _is_ambiguous(token):
        # Two passes, and the second is the one the issue's own example needs.
        # An ambiguous span is refused a value reading by the *gate* (ADR 0011)
        # and must stay refused there. Diagnosis is not binding, though, and
        # saying nothing about "1,234" when the report publishes 1,235 is a
        # diagnosis that fails exactly where it is most wanted. So: name any
        # display the span would have bound had it been written the report's
        # way (rank 0, an exact form match), and then measure both readings
        # against the figure set for near-misses. Both readings, because
        # neither is privileged -- the span genuinely could be either, which is
        # why it did not bind.
        found = _candidates_for_ambiguous(span.text, by_key)
        for reading in _ambiguous_readings(span.text):
            found.extend(_candidates_for_value(span.text, reading, publishable))
        candidates = _ordered(_deduplicate(found))
    else:
        candidates = _ordered(_candidates_for_value(span.text, _span_key(span.text), publishable))

    if not candidates:
        return Explanation(
            span=span,
            remedy="none",
            detail=(
                f"no receipted display is near {span.text!r}. Remove it, or add a metric "
                f"whose receipt produces it"
            ),
        )
    if _tied_at_front(candidates):
        names = ", ".join(candidate.metric_id for candidate in candidates)
        return Explanation(
            span=span,
            remedy="review",
            detail=(
                f"{span.text!r} is equally near {names}; nothing in the text says which, "
                f"so no substitution is offered"
            ),
            candidates=candidates,
        )
    return Explanation(
        span=span,
        remedy="replace",
        detail=candidates[0].detail,
        candidates=candidates,
    )


def explain_disclosure(disclosure: SuppressedSpan, suppressed: Sequence[Figure]) -> Explanation:
    """Diagnose a span that states a cell the report withholds.

    The remedy is removal and only removal. Every candidate here carries
    ``substitutable=False``, because the candidate's display *is* the protected
    value: offering it as a replacement would be the tool proposing the
    disclosure it just refused.
    """

    displays = {figure.metric_id: figure.display for figure in suppressed}
    candidates = tuple(
        SpanCandidate(
            metric_id=metric_id,
            display=displays.get(metric_id, ""),
            reason="suppressed_disclosure",
            detail=(
                f"{metric_id} is withheld by small-cell suppression; this report does not "
                f"publish its value"
            ),
            substitutable=False,
        )
        for metric_id in disclosure.metric_ids
    )
    also = ""
    if disclosure.ambiguous:
        names = ", ".join(disclosure.publishable_metric_ids)
        also = (
            f" It is also the published value of {names}, so rephrase until the two numbers differ."
        )
    return Explanation(
        span=disclosure.span,
        remedy="remove",
        detail=(
            f"{disclosure.span.text!r} is the withheld value of "
            f"{', '.join(disclosure.metric_ids)}. Remove it; no receipted display may "
            f"stand in for a protected cell.{also}"
        ),
        candidates=candidates,
    )


def explain_audit(
    result: AuditResult,
    publishable: Sequence[Figure],
    suppressed: Sequence[Figure],
) -> AuditResult:
    """Return ``result`` with a diagnosis attached to each failing span.

    A copy: the verdict fields are carried over unchanged and ``ok`` does not
    read ``explanations``, so asking for a diagnosis cannot alter the gate.
    """

    explanations = tuple(
        [explain_disclosure(item, suppressed) for item in result.suppressed]
        + [explain_span(span, publishable) for span in result.unbound]
    )
    return AuditResult(
        bound=result.bound,
        suppressed=result.suppressed,
        unbound=result.unbound,
        explanations=explanations,
    )


def explain_unbound(
    spans: Sequence[NumericSpan], publishable: Sequence[Figure]
) -> tuple[Explanation, ...]:
    """Diagnose the unbound spans of a plain ``GroundingResult``.

    ``run`` grounds against the publishable set with ``ground``, which has no
    disclosure category, so its failures are all of the one kind.
    """

    return tuple(explain_span(span, publishable) for span in spans)


# --------------------------------------------------------------------------
# Fix plans
#
# A plan is a proposal a human reads and edits. Applying one is therefore not
# "trust the plan": every field in it is re-checked against the narrative and
# the figure set as they are *now*, and a plan that no longer describes them is
# refused whole rather than applied in part. The substituted text is always a
# receipted display copied character for character out of a Figure; the applier
# never formats a number.
# --------------------------------------------------------------------------

#: Version of the fix-plan document. A plan written by a future version is
#: refused rather than read on a guess about which fields moved.
FIX_PLAN_SCHEMA_VERSION = 1


class FixPlanRefused(Exception):
    """A fix plan cannot be applied, with the reason a human needs.

    Raised rather than returned so no caller can fall through to writing a
    narrative it failed to validate.
    """


def narrative_digest(text: str) -> str:
    """The digest a fix plan carries so it cannot be applied to a changed file.

    Every offset in a plan indexes the narrative it was computed from. Applying
    it to an edited narrative would splice a receipted display into whatever now
    sits at those offsets -- a corruption that would then be gated as if it were
    the author's own sentence. The digest makes that mismatch loud.
    """

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_fix_plan(text: str, explanations: Sequence[Explanation]) -> dict[str, object]:
    """A machine-readable, human-editable plan built from the diagnoses.

    Only ``replace`` explanations become fixes. Everything else is listed under
    ``unfixable`` with its reason, present so the plan is a complete account of
    the failure rather than only the convenient part of it: a plan that silently
    omitted the disclosures would read as "four problems, four fixes" when one
    of them is a protected cell no substitution can address.
    """

    fixes = []
    unfixable = []
    for explanation in explanations:
        span = explanation.span
        if explanation.remedy == "replace":
            # `candidates[0]` and not `.replacement`: the property is typed
            # optional for callers who do not know the remedy, and this branch
            # does. `Explanation.__post_init__` refuses to build a `replace`
            # with an empty or non-substitutable candidate list, so the index is
            # safe by construction rather than by a runtime assertion.
            candidate = explanation.candidates[0]
            fixes.append(
                {
                    "start": span.start,
                    "end": span.end,
                    "was": span.text,
                    "replace_with": candidate.display,
                    "metric_id": candidate.metric_id,
                    "reason": candidate.reason,
                }
            )
        else:
            unfixable.append(
                {
                    "start": span.start,
                    "end": span.end,
                    "was": span.text,
                    "remedy": explanation.remedy,
                    "why": explanation.detail,
                }
            )
    return {
        "schema_version": FIX_PLAN_SCHEMA_VERSION,
        "narrative_sha256": narrative_digest(text),
        "fixes": fixes,
        "unfixable": unfixable,
    }


def _read_plan(plan: object) -> tuple[object, list[dict[str, object]]]:
    """The digest and the fix list of a plan whose shape has been checked.

    Returns both so the caller never re-reads the raw object: everything the
    applier needs comes back narrowed, and there is no second place where an
    unvalidated field could be picked up.
    """

    if not isinstance(plan, dict):
        raise FixPlanRefused("fix plan is not an object")
    version = plan.get("schema_version")
    if version != FIX_PLAN_SCHEMA_VERSION:
        raise FixPlanRefused(
            f"fix plan schema_version is {version!r}, expected {FIX_PLAN_SCHEMA_VERSION}"
        )
    fixes = plan.get("fixes")
    if not isinstance(fixes, list):
        raise FixPlanRefused("fix plan has no 'fixes' list")
    out: list[dict[str, object]] = []
    for entry in fixes:
        if not isinstance(entry, dict):
            raise FixPlanRefused("a fix entry is not an object")
        out.append(entry)
    return plan.get("narrative_sha256"), out


def _checked_fix(
    entry: dict[str, object],
    text: str,
    *,
    allowed: set[str],
    withheld: set[str],
) -> tuple[int, int, str]:
    """One plan entry validated against the narrative and figures as they are now.

    Every branch raises. There is no repair path and no "closest acceptable
    display" fallback: a plan that no longer describes the text or the figure
    set is refused, because the alternative is a substitution nobody proposed
    landing in a narrative that then passes the gate.
    """

    start, end = entry.get("start"), entry.get("end")
    was, replacement = entry.get("was"), entry.get("replace_with")
    if isinstance(start, bool) or isinstance(end, bool):
        raise FixPlanRefused(f"fix {entry!r} has boolean offsets")
    if not isinstance(start, int) or not isinstance(end, int):
        raise FixPlanRefused(f"fix {entry!r} has no integer offsets")
    if not isinstance(was, str) or not isinstance(replacement, str):
        raise FixPlanRefused(f"fix {entry!r} has no 'was'/'replace_with' strings")
    if not 0 <= start < end <= len(text):
        raise FixPlanRefused(f"fix at {start}:{end} is outside the narrative")
    if text[start:end] != was:
        raise FixPlanRefused(
            f"fix at {start}:{end} expected {was!r} but the narrative has {text[start:end]!r}"
        )
    if replacement in withheld:
        raise FixPlanRefused(
            f"fix at {start}:{end} would write {replacement!r}, the withheld value of a "
            f"suppressed cell"
        )
    if replacement not in allowed:
        raise FixPlanRefused(
            f"fix at {start}:{end} would write {replacement!r}, which is not the display "
            f"of any publishable figure"
        )
    return (start, end, replacement)


def apply_fix_plan(
    text: str,
    plan: object,
    publishable: Sequence[Figure],
    suppressed: Sequence[Figure],
) -> str:
    """Apply a fix plan to ``text``, or refuse it whole.

    Every check below has cost someone an afternoon somewhere, and each refuses
    rather than repairs:

    - the plan's schema version must be the one this code reads;
    - the plan's digest must be the digest of ``text``, so the offsets still
      index the sentences they were computed from;
    - each ``was`` must be exactly the text at its offsets;
    - fixes must not overlap, so no substitution lands inside another;
    - each ``replace_with`` must be, character for character, the current
      display of a *publishable* figure. A display that is merely close, or one
      belonging to a withheld figure, is refused;
    - a ``replace_with`` that would state a suppressed cell's raw display is
      refused by name, whatever the plan calls it.

    The last two are the ones that matter most: they are what makes "substitutes
    only exact receipted displays" a property of the applier rather than a
    property of whoever wrote the plan.
    """

    digest, fixes = _read_plan(plan)
    actual = narrative_digest(text)
    if digest != actual:
        raise FixPlanRefused(
            f"fix plan was built for a different narrative "
            f"(plan {digest!r}, file {actual!r}); re-run audit --explain"
        )

    allowed = {figure.display for figure in publishable}
    withheld = {figure.display for figure in suppressed}

    normalized = sorted(
        _checked_fix(entry, text, allowed=allowed, withheld=withheld) for entry in fixes
    )
    for (_, previous_end, _), (next_start, _, _) in itertools.pairwise(normalized):
        if next_start < previous_end:
            raise FixPlanRefused("two fixes overlap; the plan cannot be applied")

    out = text
    for start, end, replacement in reversed(normalized):
        out = out[:start] + replacement + out[end:]
    return out
