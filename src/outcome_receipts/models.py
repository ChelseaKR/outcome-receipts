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

    ``description`` is a short label. ``definition`` is the precise, plain-language
    statement of what the figure counts: the time window, who is in scope, and the
    deduplication rule. The definition rides in the receipt and renders next to the
    figure, so a reviewer can see and contest the choices a query encodes (a count
    of "clients served" is only as fair as its definition) instead of inferring
    them from the SQL.

    ``kind`` distinguishes an ``output`` (an activity count, such as clients
    served) from an ``outcome`` (a change in condition, such as a housing-retention
    rate). It rides in the receipt so a reader does not misread a busy output as
    the outcome it is meant to produce.
    """

    metric_id: str
    description: str
    value_sql: str
    slice_sql: str
    unit: str = "count"
    decimals: int = 0
    definition: str = ""
    kind: str = "output"


@dataclass(frozen=True)
class DataCheck:
    """An author-declared data-quality precondition, asserted before compute.

    ``assert_sql`` is a query returning a single scalar; a nonzero/true value
    passes and a falsy value (None, 0, "0", "", "false") fails. Checks state the
    preconditions a report's figures rely on -- no null client ids, dates inside
    the reporting window, no duplicate keys -- and run before any figure is
    computed, so a violated precondition fails closed and blocks the whole run
    rather than producing a receipted-but-wrong number. ``message`` is an optional
    author note appended to the failure so the person fixing the data knows what
    the check was defending.
    """

    check_id: str
    description: str
    assert_sql: str
    message: str = ""


@dataclass(frozen=True)
class Receipt:
    """The record of how a figure was produced.

    ``slice_hash`` is a BLAKE2b hash of the canonicalized rows the figure was
    computed over, so the same data reproduces the same receipt and a changed
    slice is detectable. ``computed_at`` comes from an injected clock so a
    committed eval is reproducible. ``definition`` carries the figure's
    plain-language definition forward from its ``MetricSpec`` so the receipt is
    self-describing without the spec on hand. ``kind`` carries the same forward
    label distinguishing an activity count (``output``) from a change in condition
    (``outcome``), so a reader of the receipt alone does not misread an output as
    an outcome.
    """

    metric_id: str
    value_sql: str
    row_count: int
    slice_hash: str
    value: float
    unit: str
    computed_at: str
    definition: str = ""
    kind: str = "output"


@dataclass(frozen=True)
class Figure:
    """A computed value, its display string, and the receipt that backs it."""

    metric_id: str
    value: float
    display: str
    receipt: Receipt


@dataclass(frozen=True)
class PeriodSpec:
    """One reporting period in a multi-period comparison.

    ``predicate`` is a SQL boolean over the data table that selects the period's
    rows (for example a date window). It is substituted into a comparison metric's
    ``{period}`` placeholder, so each period's figure is computed by the same
    deterministic query restricted to that period. ``label`` is the human name
    shown in tables and charts; it carries no number.
    """

    period_id: str
    label: str
    predicate: str


@dataclass(frozen=True)
class ComparisonSpec:
    """A period-over-period comparison of a shared set of metrics.

    Each metric in ``metrics`` uses a ``{period}`` placeholder in its SQL. The
    comparison computes that metric once for ``prior`` and once for ``current``,
    then a delta, each as a Figure with its own receipt. ``current`` and ``prior``
    name two entries in ``periods``.
    """

    current: str
    prior: str
    periods: tuple[PeriodSpec, ...] = field(default_factory=tuple)
    metrics: tuple[MetricSpec, ...] = field(default_factory=tuple)

    def period(self, period_id: str) -> PeriodSpec:
        for spec in self.periods:
            if spec.period_id == period_id:
                return spec
        raise KeyError(f"comparison references unknown period {period_id!r}")


@dataclass(frozen=True)
class ChartSpec:
    """A chart drawn from already-computed, receipted figures.

    ``metric_ids`` names the figures whose values become the chart's data points,
    so a chart has no data path of its own: its bars and points are the grounded
    figures. ``kind`` is ``bar`` or ``line``. Every number the chart renders (its
    value labels and its accessible data table) is a figure display, so the
    grounding gate verifies a chart exactly as it verifies prose.
    """

    chart_id: str
    title: str
    kind: str
    metric_ids: tuple[str, ...]
    labels: tuple[str, ...] = field(default_factory=tuple)

    def label_for(self, index: int) -> str:
        """The bar/point label for the figure at ``index``.

        Falls back to the metric id when no explicit label is given, so a chart
        is renderable without a parallel labels list.
        """

        if index < len(self.labels):
            return self.labels[index]
        return self.metric_ids[index]


@dataclass(frozen=True)
class TemplateSpec:
    """One named funder template format for a report.

    ``template_id`` identifies the funder format and names the output subdirectory
    the report renders into. ``title`` heads that funder's rendered report.
    ``template`` is plain text with ``{metric_id}`` placeholders, filled with the
    same shared, receipted figures. Several ``TemplateSpec``s over one metric set
    let a single run render the same figures into more than one funder format, each
    held to the same grounding gate.
    """

    template_id: str
    title: str
    template: str


@dataclass(frozen=True)
class ReportSpec:
    """A report template plus the metrics it needs.

    ``template`` is plain text with ``{metric_id}`` placeholders. ``metrics`` are
    the specs whose figures fill those placeholders. ``title`` heads the rendered
    report. ``charts`` and ``comparison`` are optional sections; their numbers are
    figures too, held to the same grounding gate. ``data_checks`` are author-declared
    data-quality preconditions that assert before any figure is computed and fail
    closed, so a bad export is refused before a single number is produced.

    ``templates`` optionally names several funder formats over the same metrics. It
    is empty for a legacy single-template spec; when empty, the legacy
    ``title``/``template`` pair is the sole default format (see
    ``effective_templates``), so existing specs keep rendering into the flat output
    directory unchanged.
    """

    title: str
    template: str
    metrics: tuple[MetricSpec, ...] = field(default_factory=tuple)
    charts: tuple[ChartSpec, ...] = field(default_factory=tuple)
    comparison: ComparisonSpec | None = None
    data_checks: tuple[DataCheck, ...] = field(default_factory=tuple)
    templates: tuple[TemplateSpec, ...] = field(default_factory=tuple)

    @property
    def effective_templates(self) -> tuple[TemplateSpec, ...]:
        """The funder formats to render, one per output.

        When ``templates`` is set the run renders each named format. Otherwise the
        legacy single template is synthesized into one ``TemplateSpec`` with id
        ``"report"``, so callers iterate the same shape either way while the
        legacy spec still describes exactly one report.
        """

        if self.templates:
            return self.templates
        return (TemplateSpec(template_id="report", title=self.title, template=self.template),)


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
