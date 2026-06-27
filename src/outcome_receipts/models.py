"""Core data types.

A Receipt is the unit of trust: it records exactly how a number was produced, so
the number can be reproduced and audited. A Figure is a value plus its receipt. A
MetricSpec defines how to compute a figure deterministically. Nothing here calls
a model; figures come from queries, never from generated text.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# The hash that stands in for "no data slice", used when a metric is computed
# over an empty result set. Distinct from a real slice hash so an empty slice is
# visible rather than silently indistinguishable.
EMPTY_SLICE_HASH = "0" * 64


@dataclass(frozen=True)
class MetricSpec:
    """How to compute one figure, deterministically.

    ``value_sql`` is a query returning a single scalar (the figure's value).
    ``slice_sql`` returns the rows the figure is computed over; it is used for the
    row count and the slice hash, the evidence that the value came from a specific
    set of records. ``unit`` selects formatting: ``count`` or ``percent``.
    ``format`` is an optional override of the default formatting for the unit.
    """

    metric_id: str
    description: str
    value_sql: str
    slice_sql: str
    unit: str = "count"
    decimals: int = 0


@dataclass(frozen=True)
class Receipt:
    """The record of how a figure was produced.

    ``slice_hash`` is a BLAKE2b hash of the canonicalized rows the figure was
    computed over, so the same data reproduces the same receipt and a changed
    slice is detectable. ``computed_at`` comes from an injected clock so a
    committed eval is reproducible.
    """

    metric_id: str
    value_sql: str
    row_count: int
    slice_hash: str
    value: float
    unit: str
    computed_at: str


@dataclass(frozen=True)
class Figure:
    """A computed value, its display string, and the receipt that backs it."""

    metric_id: str
    value: float
    display: str
    receipt: Receipt


@dataclass(frozen=True)
class ReportSpec:
    """A report template plus the metrics it needs.

    ``template`` is plain text with ``{metric_id}`` placeholders. ``metrics`` are
    the specs whose figures fill those placeholders. ``title`` heads the rendered
    report.
    """

    title: str
    template: str
    metrics: tuple[MetricSpec, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class NumericSpan:
    """A number found in drafted text, with where it was found."""

    text: str
    start: int
    end: int


@dataclass(frozen=True)
class GroundingResult:
    """The outcome of the grounding gate over a narrative.

    ``bound`` are numeric spans that matched a figure's display; ``unbound`` are
    spans that matched no figure and therefore block export. ``ok`` is true only
    when nothing is unbound.
    """

    bound: tuple[NumericSpan, ...]
    unbound: tuple[NumericSpan, ...]

    @property
    def ok(self) -> bool:
        return not self.unbound

    @property
    def total(self) -> int:
        return len(self.bound) + len(self.unbound)
