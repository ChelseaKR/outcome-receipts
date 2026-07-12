"""Property-based tests over the grounding gate invariants.

The example tests in ``test_grounding_gate.py`` pin specific narratives. These use
Hypothesis to generate adversarial narratives — real, receipted figure displays
interleaved with randomly injected numbers — and assert the gate's load-bearing
invariants hold for *every* generated case, not just the hand-written examples:

  * the gate never misses an ungrounded number — every injected number that is
    not backed by a figure lands in ``result.unbound``;
  * ``result.ok`` is True iff ``result.unbound`` is empty (consistency);
  * ``redact_unbound`` is total — no ungrounded numeric literal survives it, and
    grounded figures do survive;
  * grounding is idempotent — after redaction the narrative grounds clean.

The figures are the same realistic ones the example tests use (``load_spec`` +
``compute_figures`` over the housing demo), so the "allowed" number set is the
one a real report would produce. Hypothesis then layers the number-injection.

Runs are derandomized so CI is stable: the same seed every time, no flaky
example that passes locally and fails on a rerun.
"""

from __future__ import annotations

from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from outcome_receipts.clock import FixedClock
from outcome_receipts.config import load_spec
from outcome_receipts.engine import compute_figures, read_csv
from outcome_receipts.grounding import find_numbers, ground, redact_unbound
from outcome_receipts.models import Figure, MetricSpec

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "housing-demo"


def _example_figures() -> list[Figure]:
    """The realistic, receipted figure set the example gate tests also use."""

    spec = load_spec(EXAMPLES / "report.toml")
    rows = read_csv(spec.data_path)
    return compute_figures(rows, spec.report.metrics, clock=FixedClock())


def _thousands_figure() -> Figure:
    """A receipted figure whose display carries a thousands separator (``1,234``).

    The housing-demo figures are all under 1,000, so nothing exercises the gate's
    separator normalization. This one does, so the tests below can pin it.
    """

    spec = MetricSpec(
        metric_id="big",
        description="a four-digit figure",
        value_sql="SELECT 1234",
        slice_sql="SELECT 1",
    )
    return compute_figures([{"x": "1"}], (spec,), clock=FixedClock())[0]


def _normalize(token: str) -> str:
    """Mirror the gate's own normalization: drop thousands separators."""

    return token.replace(",", "")


FIGURES: list[Figure] = _example_figures()
# The number set the gate binds against, normalized the way the gate does.
ALLOWED: frozenset[str] = frozenset(_normalize(figure.display) for figure in FIGURES)
GROUNDED_DISPLAYS: list[str] = [figure.display for figure in FIGURES]
assert GROUNDED_DISPLAYS, "the demo spec must produce at least one figure to sample from"


# --- strategies ------------------------------------------------------------

# Numeric literals the gate's regex captures as a single span. Kept simple —
# integers and two-place decimals — so each is one whole token, never a
# fragment that would merge with a neighbor.
_int_tokens: st.SearchStrategy[str] = st.integers(min_value=0, max_value=1_000_000).map(str)
_decimal_tokens: st.SearchStrategy[str] = st.builds(
    lambda whole, frac: f"{whole}.{frac:02d}",
    st.integers(min_value=0, max_value=9_999),
    st.integers(min_value=0, max_value=99),
)

# Injected numbers are, by construction, *not* a figure display: filtered so the
# invariant "unbound == exactly the injected numbers" is unambiguous.
_ungrounded_numbers: st.SearchStrategy[str] = st.one_of(_int_tokens, _decimal_tokens).filter(
    lambda token: _normalize(token) not in ALLOWED
)

# A tagged token: either a genuine grounded figure display, or an injected
# ungrounded number. Tests read the tag to know what the gate *should* do.
_token: st.SearchStrategy[tuple[str, str]] = st.one_of(
    _ungrounded_numbers.map(lambda token: ("inj", token)),
    st.sampled_from(GROUNDED_DISPLAYS).map(lambda display: ("bound", display)),
)
_tokens: st.SearchStrategy[list[tuple[str, str]]] = st.lists(_token, max_size=12)


def _narrative(tokens: list[tuple[str, str]]) -> str:
    """Weave tokens into prose. The `` . `` separator has no digit, so every

    numeric token stays a distinct span and none accidentally merges with its
    neighbor — the same shape a drafted sentence has.
    """

    return " . ".join(text for _tag, text in tokens)


# --- properties ------------------------------------------------------------


@settings(derandomize=True, max_examples=300)
@given(text=st.text())
def test_gate_partitions_every_number_by_the_allowed_set(text: str) -> None:
    """Over arbitrary text: every numeric span is bound iff it is an allowed

    figure display, and unbound otherwise. This is the gate's core promise — no
    ungrounded number is ever silently kept — stated as a universal property.
    """

    result = ground(text, FIGURES)
    for span in find_numbers(text):
        if _normalize(span.text) in ALLOWED:
            assert span in result.bound
        else:
            assert span in result.unbound
    # Consistency: ok is exactly "nothing unbound", and the partition is total.
    assert result.ok == (len(result.unbound) == 0)
    assert result.total == len(find_numbers(text))


@settings(derandomize=True, max_examples=300)
@given(tokens=_tokens)
def test_every_injected_number_is_flagged(tokens: list[tuple[str, str]]) -> None:
    """Every injected (ungrounded) number appears in ``unbound``; every grounded

    figure display appears in ``bound``. The gate neither misses an invented
    number nor falsely accuses a real one.
    """

    narrative = _narrative(tokens)
    result = ground(narrative, FIGURES)

    unbound = {_normalize(span.text) for span in result.unbound}
    bound = {_normalize(span.text) for span in result.bound}
    injected = {_normalize(text) for tag, text in tokens if tag == "inj"}
    grounded = {_normalize(text) for tag, text in tokens if tag == "bound"}

    assert injected <= unbound
    assert grounded <= bound
    assert result.ok == (len(injected) == 0)


@settings(derandomize=True, max_examples=300)
@given(tokens=_tokens)
def test_redaction_is_total(tokens: list[tuple[str, str]]) -> None:
    """After ``redact_unbound`` no ungrounded number remains as a token, and the

    grounded figures are left untouched.
    """

    narrative = _narrative(tokens)
    result = ground(narrative, FIGURES)
    cleaned = redact_unbound(narrative, result)

    remaining = {_normalize(span.text) for span in find_numbers(cleaned)}
    injected = {_normalize(text) for tag, text in tokens if tag == "inj"}
    grounded = {_normalize(text) for tag, text in tokens if tag == "bound"}

    assert injected.isdisjoint(remaining)
    assert grounded <= remaining


@settings(derandomize=True, max_examples=300)
@given(tokens=_tokens)
def test_grounding_is_idempotent_after_redaction(tokens: list[tuple[str, str]]) -> None:
    """Redaction reaches a fixed point in one pass: whatever the narrative, the

    redacted text grounds clean, so re-running the gate never finds more to strip.
    """

    narrative = _narrative(tokens)
    result = ground(narrative, FIGURES)
    cleaned = redact_unbound(narrative, result)

    assert ground(cleaned, FIGURES).ok


# --- separator normalization and exact redaction ---------------------------
#
# These are example-based, not generated, but they pin two behaviors the
# property strategies above cannot reach: the housing-demo figures never carry a
# thousands separator, and the property tests deliberately avoid asserting the
# redaction marker's exact spelling. Both are load-bearing to the gate.


def test_thousands_separator_is_normalized_both_ways() -> None:
    """The gate compares numbers by value, not spelling: a figure displayed as

    ``1,234`` binds whether the narrative writes it with the separator or without.
    A different four-digit number still fails closed.
    """

    figures = [_thousands_figure()]  # display == "1,234"

    assert ground("we served 1,234 people", figures).ok
    assert ground("we served 1234 people", figures).ok

    other = ground("we served 5678 people", figures)
    assert not other.ok
    assert any(span.text == "5678" for span in other.unbound)


def test_default_redaction_marker_is_exact() -> None:
    """Redaction replaces an ungrounded number with exactly ``[UNVERIFIED]`` — no

    more, no less — so a reader can trust the marker's shape, not just that it
    contains that word.
    """

    figures = [_thousands_figure()]
    text = "we served 5678 people"
    result = ground(text, figures)

    assert redact_unbound(text, result) == "we served [UNVERIFIED] people"
