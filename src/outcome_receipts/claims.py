"""The comparative-claim gate: prose that asserts a direction without a digit.

``grounding`` finds numbers. A sentence carrying no numeral is invisible to it, and
"placements rose this quarter" is a quantitative claim. The invariant this project
sells is that numbers never come from a model; a drafter forbidden to invent a
digit was not forbidden to invent a direction, and a funder reading "rose" does not
read it as prose.

So this module does for direction words what ``grounding`` does for numbers, and it
draws the same line in the same place. ``comparison.ComparisonRow.direction`` is
already computed from a receipted delta -- ``increase``, ``decrease`` or
``no change``, derived from the sign of a value a single SQL statement produced.
That is the only receipted direction in the system, so it is the only thing a
comparative claim may bind to. A claim that agrees with one binds. A claim that
agrees with none, where comparisons exist, is **contradicted** and blocks export. A
claim made where the spec declares no comparison at all is **unbound** and blocks
export. A claim that agrees only with a comparison suppression withheld is a
**disclosure**, and is reported as one for the reason ``grounding.audit_narrative``
reports a number that states a redacted cell: the two need different remedies, and
issue #75 was exactly this leak -- the comparison table's direction word recovering
both hidden periods.

**Four families of claim are detected and can never bind.** This is the
``_NUMBER_WORD`` precedent, not an oversight: a written-out numeral is detected and
always left unbound so a drafter cannot evade the gate by spelling one, and each of
these asserts something no receipt in this system carries.

``evaluative``   "improved", "worsened", "better". A direction word only becomes a
                 valuation once you know whether up is good, and **a spec declares
                 no polarity for a metric.** "Improved" over a length-of-stay metric
                 means a decrease; over a placements metric it means an increase.
                 Binding it to either would be the gate inventing the very thing it
                 exists to check.
``magnitude``    "doubled", "halved", "twice". These assert a ratio, and there is no
                 receipted ratio: ``compute_reconciliation`` deliberately refuses to
                 compute cost-per-outcome for exactly this reason -- the receipt's
                 slice cannot be a well-formed union of two differently shaped row
                 sets. A ratio the system will not compute is not a ratio it can
                 check.
``proportion``   "most", "nearly all", "few". A share of a whole. Figures are counts,
                 rates and money; none of them is a proportion-of-total that a
                 quantifier could be checked against.
``rank``         "highest", "lowest", "record". A position in an ordering over a set
                 the gate does not model. Two periods do not make a ranking.

Each is reported with its own reason so the author is told *why* the words cannot be
checked rather than being left to guess, and none of them is silently passed --
which is what happens today.

**Known collisions, accepted.** "Declined" means both *fell* and *refused*, and
"12 clients declined services" is ordinary prose in this domain. It is detected as a
decrease claim and must be rephrased. That is the fail-closed direction and it
matches the rest of the gate, which already blocks a stray "2024": the author is
told the exact word and offset, and rewording is cheap where a false negative is a
published claim nobody checked.

**What this deliberately does not do.** It does not tie a claim to the particular
metric its own sentence is about. Report-wide binding means "placements fell" binds
whenever *some* declared comparison decreased, which is weaker than a per-sentence
rule and is what issue #174 specifies ("bind to a receipted comparison whose own
direction agrees with it"). Every disagreeing row is named in the explanation so the
gap is visible rather than hidden. It also judges no tone, no sentiment, and no
sentence that carries none of these forms.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from outcome_receipts.models import REDACTED_DISPLAY, Figure

INCREASE = "increase"
DECREASE = "decrease"
NO_CHANGE = "no change"

#: The three words ``comparison._direction`` can produce. Anything else in a row's
#: ``direction`` field is a redaction sentinel, never a fourth direction.
RECEIPTED_DIRECTIONS = (INCREASE, DECREASE, NO_CHANGE)

KIND_DIRECTION = "direction"
KIND_EVALUATIVE = "evaluative"
KIND_MAGNITUDE = "magnitude"
KIND_PROPORTION = "proportion"
KIND_RANK = "rank"

#: Kinds that assert something no receipt in this system carries. Detected, reported,
#: and never bound -- exactly as ``grounding._NUMBER_WORD`` spans are.
UNBINDABLE_KINDS = (KIND_EVALUATIVE, KIND_MAGNITUDE, KIND_PROPORTION, KIND_RANK)

STATUS_BOUND = "bound"
STATUS_UNBOUND = "unbound"
STATUS_CONTRADICTED = "contradicted"
STATUS_DISCLOSED = "disclosed"

# --------------------------------------------------------------------------
# The closed vocabulary.
#
# One place, two languages, every entry carrying its kind and (for a direction
# claim) the direction it asserts. `test_claims.py` asserts that the compiled
# detector and this catalog cannot drift apart: every entry must be findable and
# nothing may be findable that is not an entry.
#
# Entries are matched case-insensitively on word boundaries. Multi-word entries are
# matched with flexible internal whitespace so a line-wrapped narrative is not a
# hole in the gate.
# --------------------------------------------------------------------------

_VOCABULARY: tuple[tuple[str, str, str | None], ...] = (
    # -- English, bindable directions -------------------------------------
    ("rose", KIND_DIRECTION, INCREASE),
    ("risen", KIND_DIRECTION, INCREASE),
    ("increased", KIND_DIRECTION, INCREASE),
    ("an increase", KIND_DIRECTION, INCREASE),
    ("grew", KIND_DIRECTION, INCREASE),
    ("climbed", KIND_DIRECTION, INCREASE),
    ("went up", KIND_DIRECTION, INCREASE),
    ("up from", KIND_DIRECTION, INCREASE),
    ("fell", KIND_DIRECTION, DECREASE),
    ("fallen", KIND_DIRECTION, DECREASE),
    ("decreased", KIND_DIRECTION, DECREASE),
    ("a decrease", KIND_DIRECTION, DECREASE),
    ("declined", KIND_DIRECTION, DECREASE),
    ("a decline", KIND_DIRECTION, DECREASE),
    ("dropped", KIND_DIRECTION, DECREASE),
    ("shrank", KIND_DIRECTION, DECREASE),
    ("went down", KIND_DIRECTION, DECREASE),
    ("down from", KIND_DIRECTION, DECREASE),
    ("unchanged", KIND_DIRECTION, NO_CHANGE),
    ("no change", KIND_DIRECTION, NO_CHANGE),
    ("held steady", KIND_DIRECTION, NO_CHANGE),
    ("stayed the same", KIND_DIRECTION, NO_CHANGE),
    ("remained the same", KIND_DIRECTION, NO_CHANGE),
    # -- Spanish, bindable directions -------------------------------------
    ("aumentó", KIND_DIRECTION, INCREASE),
    ("aumentaron", KIND_DIRECTION, INCREASE),
    ("subió", KIND_DIRECTION, INCREASE),
    ("subieron", KIND_DIRECTION, INCREASE),
    ("creció", KIND_DIRECTION, INCREASE),
    ("crecieron", KIND_DIRECTION, INCREASE),
    ("un aumento", KIND_DIRECTION, INCREASE),
    ("bajó", KIND_DIRECTION, DECREASE),
    ("bajaron", KIND_DIRECTION, DECREASE),
    ("disminuyó", KIND_DIRECTION, DECREASE),
    ("disminuyeron", KIND_DIRECTION, DECREASE),
    ("cayó", KIND_DIRECTION, DECREASE),
    ("cayeron", KIND_DIRECTION, DECREASE),
    ("descendió", KIND_DIRECTION, DECREASE),
    ("una disminución", KIND_DIRECTION, DECREASE),
    ("sin cambios", KIND_DIRECTION, NO_CHANGE),
    ("se mantuvo", KIND_DIRECTION, NO_CHANGE),
    ("se mantuvieron", KIND_DIRECTION, NO_CHANGE),
    ("permaneció igual", KIND_DIRECTION, NO_CHANGE),
    # -- Evaluative: a direction whose sign depends on undeclared polarity --
    ("improved", KIND_EVALUATIVE, None),
    ("improvement", KIND_EVALUATIVE, None),
    ("worsened", KIND_EVALUATIVE, None),
    ("deteriorated", KIND_EVALUATIVE, None),
    ("mejoró", KIND_EVALUATIVE, None),
    ("mejoraron", KIND_EVALUATIVE, None),
    ("empeoró", KIND_EVALUATIVE, None),
    ("empeoraron", KIND_EVALUATIVE, None),
    # -- Magnitude: a ratio no receipt carries ------------------------------
    ("doubled", KIND_MAGNITUDE, None),
    ("tripled", KIND_MAGNITUDE, None),
    ("quadrupled", KIND_MAGNITUDE, None),
    ("halved", KIND_MAGNITUDE, None),
    ("twice as many", KIND_MAGNITUDE, None),
    ("half as many", KIND_MAGNITUDE, None),
    ("threefold", KIND_MAGNITUDE, None),
    ("tenfold", KIND_MAGNITUDE, None),
    ("se duplicó", KIND_MAGNITUDE, None),
    ("se duplicaron", KIND_MAGNITUDE, None),
    ("se triplicó", KIND_MAGNITUDE, None),
    ("se redujo a la mitad", KIND_MAGNITUDE, None),
    ("el doble", KIND_MAGNITUDE, None),
    ("el triple", KIND_MAGNITUDE, None),
    # -- Proportion: a share of a whole no figure states --------------------
    ("most", KIND_PROPORTION, None),
    ("a majority", KIND_PROPORTION, None),
    ("the majority", KIND_PROPORTION, None),
    ("nearly all", KIND_PROPORTION, None),
    ("almost all", KIND_PROPORTION, None),
    ("virtually all", KIND_PROPORTION, None),
    ("almost none", KIND_PROPORTION, None),
    ("hardly any", KIND_PROPORTION, None),
    ("la mayoría", KIND_PROPORTION, None),
    ("casi todos", KIND_PROPORTION, None),
    ("casi todas", KIND_PROPORTION, None),
    ("casi ninguno", KIND_PROPORTION, None),
    ("casi ninguna", KIND_PROPORTION, None),
    # -- Rank: a position in an ordering the gate does not model ------------
    ("highest", KIND_RANK, None),
    ("lowest", KIND_RANK, None),
    ("largest", KIND_RANK, None),
    ("smallest", KIND_RANK, None),
    ("the best", KIND_RANK, None),
    ("the worst", KIND_RANK, None),
    ("a record number", KIND_RANK, None),
    ("el más alto", KIND_RANK, None),
    ("la más alta", KIND_RANK, None),
    ("el más bajo", KIND_RANK, None),
    ("la más baja", KIND_RANK, None),
    ("un número récord", KIND_RANK, None),
)


def _entry_pattern(phrase: str) -> str:
    """One vocabulary entry as a regex: word-bounded, whitespace-flexible."""

    return r"\s+".join(re.escape(word) for word in phrase.split())


# Longest first, so "a decline" wins over nothing and "twice as many" is not split.
# `finditer` over one alternation also guarantees non-overlapping matches, which is
# what makes the span offsets a caller reports meaningful.
_ORDERED = sorted(_VOCABULARY, key=lambda entry: (-len(entry[0]), entry[0]))
_DETECTOR = re.compile(
    r"(?<!\w)(?:" + "|".join(_entry_pattern(phrase) for phrase, _k, _d in _ORDERED) + r")(?!\w)",
    re.IGNORECASE,
)

_BY_PHRASE = {phrase.casefold(): (kind, direction) for phrase, kind, direction in _VOCABULARY}

_WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True)
class ClaimSpan:
    """A comparative or quantifying phrase found in drafted text, and where."""

    text: str
    start: int
    end: int
    kind: str
    #: The direction this phrase asserts, for a ``direction`` claim; ``None`` for
    #: every kind that can never bind. Never inferred -- it is the catalog's value.
    direction: str | None


@dataclass(frozen=True)
class DirectionEvidence:
    """One receipted comparison row, reduced to what a claim can be checked against.

    ``direction`` is the row's *real* direction, taken before suppression redacts it.
    ``withheld`` says whether suppression redacted any of the row's three figures, so
    a claim that agrees with this row can be reported as a disclosure rather than as
    a binding. Reading the redacted row instead would lose the direction entirely and
    turn a disclosure into an unbound claim, which is the wrong remedy.
    """

    base_metric_id: str
    direction: str
    withheld: bool = False


@dataclass(frozen=True)
class ClaimVerdict:
    """One detected claim and what the gate decided about it."""

    span: ClaimSpan
    status: str
    detail: str
    #: The comparison rows this verdict was formed against, whatever the status.
    metric_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.status not in (
            STATUS_BOUND,
            STATUS_UNBOUND,
            STATUS_CONTRADICTED,
            STATUS_DISCLOSED,
        ):
            raise ValueError(f"unknown claim status {self.status!r}")


@dataclass(frozen=True)
class ClaimAudit:
    """The outcome of the comparative-claim gate over a narrative.

    ``ok`` is true only when nothing is unbound, contradicted or disclosed -- the
    same shape as ``GroundingResult.ok`` and for the same reason. A narrative
    containing no vocabulary entry at all produces an empty audit that is ``ok``,
    so a spec whose prose carries no comparative form gates exactly as before this
    module existed.
    """

    bound: tuple[ClaimVerdict, ...] = ()
    unbound: tuple[ClaimVerdict, ...] = ()
    contradicted: tuple[ClaimVerdict, ...] = ()
    disclosed: tuple[ClaimVerdict, ...] = ()

    @property
    def ok(self) -> bool:
        return not (self.unbound or self.contradicted or self.disclosed)

    @property
    def total(self) -> int:
        return len(self.bound) + len(self.unbound) + len(self.contradicted) + len(self.disclosed)

    @property
    def verdicts(self) -> tuple[ClaimVerdict, ...]:
        """Every verdict in the order the claims appear in the text."""

        everything = self.bound + self.unbound + self.contradicted + self.disclosed
        return tuple(sorted(everything, key=lambda verdict: verdict.span.start))


def vocabulary() -> tuple[tuple[str, str, str | None], ...]:
    """The closed catalog, for tests and for anything that documents the gate."""

    return _VOCABULARY


def find_claims(text: str) -> list[ClaimSpan]:
    """Every vocabulary phrase in ``text``, in order, non-overlapping."""

    spans = []
    for match in _DETECTOR.finditer(text):
        phrase = _WHITESPACE.sub(" ", match.group(0)).casefold()
        kind, direction = _BY_PHRASE[phrase]
        spans.append(
            ClaimSpan(
                text=match.group(0),
                start=match.start(),
                end=match.end(),
                kind=kind,
                direction=direction,
            )
        )
    return spans


_UNBINDABLE_DETAIL = {
    KIND_EVALUATIVE: (
        "states a direction whose sign depends on whether up is good for the metric, "
        "and a spec declares no polarity, so no receipt can settle it"
    ),
    KIND_MAGNITUDE: (
        "states a ratio between two periods, and no figure in this report is a ratio; "
        "state the two receipted figures instead"
    ),
    KIND_PROPORTION: (
        "states a share of a whole, and no figure in this report is a proportion of a "
        "total; state the receipted count or rate instead"
    ),
    KIND_RANK: (
        "states a position in an ordering, and this report ranks nothing; two periods "
        "are not a ranking"
    ),
}


def evidence_from_rows(
    rows: Iterable[object], withheld_metric_ids: Sequence[str] = ()
) -> tuple[DirectionEvidence, ...]:
    """Reduce comparison and reconciliation rows to what a claim can be checked against.

    Accepts anything carrying ``base_metric_id``, ``direction``, ``prior``, ``current``
    and ``delta`` -- which is ``comparison.ComparisonRow`` -- and is written against
    those attributes rather than the class so this module does not import the compute
    layer to read four fields off it.

    A row whose ``direction`` is not one of the three receipted words is dropped: that
    is a row suppression already redacted, and its real direction is gone. Callers pass
    the *pre*-suppression rows together with the set of withheld metric ids, exactly as
    ``grounding.audit_narrative`` is given the pre-suppression figures.
    """

    hidden = set(withheld_metric_ids)
    evidence = []
    for row in rows:
        direction = getattr(row, "direction", None)
        base = getattr(row, "base_metric_id", None)
        if direction not in RECEIPTED_DIRECTIONS or not isinstance(base, str):
            continue
        figures = [getattr(row, name, None) for name in ("prior", "current", "delta")]
        withheld = any(
            isinstance(figure, Figure)
            and (
                figure.metric_id in hidden
                or figure.receipt.suppressed
                or figure.display == REDACTED_DISPLAY
            )
            for figure in figures
        )
        evidence.append(
            DirectionEvidence(base_metric_id=base, direction=direction, withheld=withheld)
        )
    return tuple(evidence)


def _names(evidence: Iterable[DirectionEvidence]) -> str:
    return ", ".join(sorted({item.base_metric_id for item in evidence}))


def _declared(evidence: Sequence[DirectionEvidence]) -> str:
    return "; ".join(f"{item.base_metric_id} {item.direction}" for item in evidence)


def audit_claims(text: str, evidence: Sequence[DirectionEvidence] = ()) -> ClaimAudit:
    """Check every comparative claim in ``text`` against the receipted directions.

    Order of resolution, and it is the fail-closed order for the reason
    ``grounding.audit_narrative`` tests the suppressed set first: a claim that agrees
    with a *withheld* row is a disclosure whatever else it also agrees with, because
    writing it publishes the direction of a comparison the report declines to publish
    -- the #75 leak, arriving through prose instead of through the table.
    """

    bound: list[ClaimVerdict] = []
    unbound: list[ClaimVerdict] = []
    contradicted: list[ClaimVerdict] = []
    disclosed: list[ClaimVerdict] = []

    for span in find_claims(text):
        if span.kind in UNBINDABLE_KINDS:
            unbound.append(
                ClaimVerdict(
                    span=span,
                    status=STATUS_UNBOUND,
                    detail=f"{span.text!r} {_UNBINDABLE_DETAIL[span.kind]}",
                )
            )
            continue
        if not evidence:
            unbound.append(
                ClaimVerdict(
                    span=span,
                    status=STATUS_UNBOUND,
                    detail=(
                        f"{span.text!r} states a {span.direction}, and this spec declares no "
                        "comparison or reconciliation, so there is no receipted direction to "
                        "check it against"
                    ),
                )
            )
            continue
        agreeing = [item for item in evidence if item.direction == span.direction]
        hidden = [item for item in agreeing if item.withheld]
        if hidden:
            disclosed.append(
                ClaimVerdict(
                    span=span,
                    status=STATUS_DISCLOSED,
                    detail=(
                        f"{span.text!r} states the direction of {_names(hidden)}, whose figures "
                        "suppression withholds; this report does not publish which way it moved"
                    ),
                    metric_ids=tuple(sorted(item.base_metric_id for item in hidden)),
                )
            )
            continue
        if agreeing:
            bound.append(
                ClaimVerdict(
                    span=span,
                    status=STATUS_BOUND,
                    detail=f"{span.text!r} agrees with the receipted {span.direction} "
                    f"in {_names(agreeing)}",
                    metric_ids=tuple(sorted(item.base_metric_id for item in agreeing)),
                )
            )
            continue
        contradicted.append(
            ClaimVerdict(
                span=span,
                status=STATUS_CONTRADICTED,
                detail=(
                    f"{span.text!r} states a {span.direction}, and every receipted comparison "
                    f"says otherwise: {_declared(evidence)}"
                ),
                metric_ids=tuple(sorted(item.base_metric_id for item in evidence)),
            )
        )

    return ClaimAudit(
        bound=tuple(bound),
        unbound=tuple(unbound),
        contradicted=tuple(contradicted),
        disclosed=tuple(disclosed),
    )


@dataclass(frozen=True)
class ClaimSummary:
    """Counts for the run summary, one line per class."""

    total: int = 0
    bound: int = 0
    unbound: int = 0
    contradicted: int = 0
    disclosed: int = 0
    by_kind: dict[str, int] = field(default_factory=dict)


def summarize(audit: ClaimAudit) -> ClaimSummary:
    """Counts by class and by kind, computed from the verdicts rather than typed."""

    by_kind: dict[str, int] = {}
    for verdict in audit.verdicts:
        by_kind[verdict.span.kind] = by_kind.get(verdict.span.kind, 0) + 1
    return ClaimSummary(
        total=audit.total,
        bound=len(audit.bound),
        unbound=len(audit.unbound),
        contradicted=len(audit.contradicted),
        disclosed=len(audit.disclosed),
        by_kind=by_kind,
    )


def verdict_payload(verdict: ClaimVerdict) -> dict[str, object]:
    """One verdict as JSON."""

    return {
        "text": verdict.span.text,
        "start": verdict.span.start,
        "end": verdict.span.end,
        "kind": verdict.span.kind,
        "direction": verdict.span.direction,
        "status": verdict.status,
        "detail": verdict.detail,
        "metric_ids": list(verdict.metric_ids),
    }


def audit_payload(audit: ClaimAudit) -> dict[str, object]:
    """The audit as JSON, in the one shape both the CLI and the MCP server emit.

    It lives here rather than in either caller because ``tests/test_mcp_server.py``
    requires the two to be byte-identical for the same inputs: a drafting tool told
    over MCP that a narrative is clean, while the CLI would refuse to export it, is
    the drift that test exists to prevent.

    Only the blocking verdicts are listed. A bound claim is reported as a count,
    because listing every one would bury the ones an author has to act on.
    """

    summary = summarize(audit)
    return {
        "ok": audit.ok,
        "total": summary.total,
        "bound": summary.bound,
        "unbound": summary.unbound,
        "contradicted": summary.contradicted,
        "disclosed": summary.disclosed,
        "by_kind": dict(sorted(summary.by_kind.items())),
        "blocking": [
            verdict_payload(verdict) for verdict in audit.verdicts if verdict.status != STATUS_BOUND
        ],
    }
