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

# What a reader sees in place of a figure small-cell suppression withheld. It is
# a redaction marker, not narrative copy, so it is never translated. Single
# sourced here because suppression writes it, the report and trace views render
# it, and the evidence workflows branch on it; three copies of the literal is
# three chances for one of them to drift out of agreement with the others.
REDACTED_DISPLAY = "[SUPPRESSED]"

# The schema version of the receipts manifest. Bumped when the shape of
# receipts.json or the meaning of a receipt field changes in a way that a
# consumer or the re-derivation check must know about. ``verify`` names a
# version mismatch before it tries to re-derive fields, so a manifest written
# under an older schema fails with a clear reason rather than as opaque drift.
#
# 2.0 is a breaking change: a suppressed receipt's withheld numerics are ``null``
# and it carries ``suppressed: true``. Under 1.0 they were zeros, so a consumer
# reading the numeric field could not tell a withheld cell from a true zero. See
# docs/SPEC-STABILITY.md for the field mapping.
SCHEMA_VERSION = "2.0"

# Manifest schema versions ``verify`` can still re-derive. Reading an older
# manifest is supported (the 1.0 rendering of a suppressed receipt is
# reconstructable from the current figures); writing one is not.
SUPPORTED_SCHEMA_VERSIONS = ("1.0", "2.0")

# The hash descriptor. It rides in the manifest so a consumer knows exactly how
# every ``slice_hash`` was produced without reading the engine. ``canonicalization``
# names the rule set that turns a slice into the hashed bytes (see the ADR); it is
# bumped whenever those rules change, because a changed canonicalization changes
# every hash. ``v1`` folds the sorted column names into the payload, so a slice of
# identical values under renamed columns hashes differently.
HASH_ALGORITHM = "blake2b"
HASH_DIGEST_SIZE = 32
HASH_CANONICALIZATION = "v1"


@dataclass(frozen=True)
class MetricSpec:
    """How to compute one figure, deterministically.

    ``value_sql`` is a query returning a single scalar (the figure's value).
    ``slice_sql`` returns the rows the figure is computed over; it is used for the
    row count and the slice hash, the evidence that the value came from a specific
    set of records. ``unit`` selects formatting: ``count``, ``percent``, ``money``
    (a ``$``-prefixed amount), ``duration`` (a number of ``days``), or ``rate`` (a
    bare fixed-decimal number). ``decimals`` sets the fixed-decimal places; ``money``
    typically uses 2. Each unit has one canonical display form (see ADR 0004), the
    single string the grounding gate binds.

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

    ``indicator``, ``data_source``, and ``collection_frequency`` are the optional
    logic-model mapping. They tie the figure to a row in a theory of change: the
    named indicator it measures, the system the data comes from, and how often that
    data is collected. Each defaults to empty, which means the figure is not mapped;
    when set they ride into the receipt so the mapping travels with the number.

    ``caveat`` is an optional qualifying note (e.g. a data-quality limitation)
    that travels with the receipt, so a limitation on the figure rides inside the
    receipt chain and renders next to the figure instead of living as loose prose.

    ``requirement_id`` names the requirement in the bound requirement document
    that this metric answers. It is empty for a metric that answers no declared
    requirement, and it is the only link between a funder's requirement set and
    the figures an export publishes. See ``coverage.py`` and ADR 0012.
    """

    metric_id: str
    description: str
    value_sql: str
    slice_sql: str
    unit: str = "count"
    decimals: int = 0
    definition: str = ""
    kind: str = "output"
    indicator: str = ""
    data_source: str = ""
    collection_frequency: str = ""
    caveat: str = ""
    requirement_id: str = ""


@dataclass(frozen=True)
class UnanswerableRequirement:
    """An operator's declaration that a required figure cannot be produced.

    Both halves are mandatory and neither is sufficient alone. ``blocker`` is a
    machine-readable string that ``mapping.build_mapping_queue`` must actually
    produce for this requirement against this data -- a blocker the tool does
    not produce is refused, so the field cannot be used to wave a requirement
    away. ``reason`` is a sentence a person wrote. A blocker without a reason is
    a tool's excuse; a reason without a blocker is unfalsifiable.
    """

    requirement_id: str
    blocker: str
    reason: str


@dataclass(frozen=True)
class RequirementsSpec:
    """The requirement document an export must prove it answered.

    ``path`` is the requirement JSON the spec is bound to -- the same document
    ``receipts map`` and ``receipts requirements-diff`` read. ``unanswerable``
    carries the operator's declarations for requirements no metric answers.
    """

    path: str
    unanswerable: tuple[UnanswerableRequirement, ...] = field(default_factory=tuple)


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
    slice is detectable. ``column_names`` records the slice's columns (in query
    order), so the receipt is self-describing about what was hashed and a renamed
    column is visible rather than silent; those names are folded into the hash
    payload, so two slices with identical values under different column names
    hash differently. ``computed_at`` comes from an injected clock so a committed
    eval is reproducible. ``unit`` is the metric's unit (``count``, ``percent``,
    ``money``, ``duration``, or ``rate``), carried so a consumer can re-derive the
    display. ``definition`` carries the figure's plain-language
    definition forward from its ``MetricSpec`` so the receipt is self-describing
    without the spec on hand. ``kind`` carries the same forward label
    distinguishing an activity count (``output``) from a change in condition
    (``outcome``), so a reader of the receipt alone does not misread an output as
    an outcome. ``indicator``, ``data_source``, and ``collection_frequency`` carry
    the logic-model mapping forward the same way, so a receipt states which
    theory-of-change indicator its number belongs to.
    ``caveat`` carries the figure's optional qualifying note (e.g. a
    data-quality limitation) forward the same way, so the limitation rides inside
    the receipt chain rather than as loose prose.

    ``suppressed`` says whether small-cell suppression withheld this figure. It
    is the field a machine consumer branches on, and it is why the withheld
    numerics are typed ``| None``: a suppressed receipt carries ``None`` for
    ``value``, ``row_count``, ``slice_hash``, and ``column_names``, never a zero.
    Three states have to stay three states. A figure that is genuinely zero
    carries ``suppressed=False`` with ``value=0.0``, ``row_count=0``, and the
    all-zero ``EMPTY_SLICE_HASH``; a figure that is withheld carries
    ``suppressed=True`` and nothing numeric at all; a figure that does not exist
    has no ``Receipt``. Writing a zero for a withheld cell told every downstream
    reader "we served nobody", which is a worse answer to a funder than "we
    cannot report that figure" and is not the answer the report makes in prose.
    """

    metric_id: str
    value_sql: str
    row_count: int | None
    slice_hash: str | None
    value: float | None
    unit: str
    computed_at: str
    definition: str = ""
    kind: str = "output"
    indicator: str = ""
    data_source: str = ""
    collection_frequency: str = ""
    caveat: str = ""
    column_names: tuple[str, ...] | None = ()
    suppressed: bool = False


@dataclass(frozen=True)
class Figure:
    """A computed value, its display string, and the receipt that backs it.

    ``value`` is ``None`` when small-cell suppression withheld the figure, for
    the same reason its receipt's numerics are: it is the field renderers read
    for geometry, and a suppressed figure carrying ``0.0`` drew a bar of height
    zero and a line straight through the axis floor. There is no value here to
    draw. A renderer must check ``receipt.suppressed`` (or ``value is None``)
    and draw an absence, not a quantity.
    """

    metric_id: str
    value: float | None
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
class ReconciliationRow:
    """One board line: a receipted outcome figure paired with its financial line.

    ``outcome`` and ``financial`` are period metrics written with the same
    ``{period}`` placeholder as comparison metrics, so each is computed once for the
    prior period and once for the current period, then differenced by a single
    query. Placing them on one row lets the board read an outcome figure next to
    the money it took to produce it, with both numbers grounded. ``label`` names
    the pairing; it carries no number.
    """

    label: str
    outcome: MetricSpec
    financial: MetricSpec


@dataclass(frozen=True)
class ReconciliationSpec:
    """A board reconciliation: outcome figures beside financial lines, over two periods.

    Each row pairs an outcome metric with a financial metric, both using the
    ``{period}`` placeholder exactly like a ``ComparisonSpec``. The reconciliation
    computes every metric for ``prior`` and ``current`` and the delta between them,
    each as a Figure with its own receipt, so a board can see how an outcome and its
    financial line each moved period over period. ``current`` and ``prior`` name two
    entries in ``periods``.
    """

    current: str
    prior: str
    periods: tuple[PeriodSpec, ...] = field(default_factory=tuple)
    rows: tuple[ReconciliationRow, ...] = field(default_factory=tuple)

    def period(self, period_id: str) -> PeriodSpec:
        for spec in self.periods:
            if spec.period_id == period_id:
                return spec
        raise KeyError(f"reconciliation references unknown period {period_id!r}")


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
class DraftingSpec:
    """Optional narrative provider policy; deterministic and disabled by default."""

    provider: str = "deterministic"
    enabled: bool = False
    model_id: str = ""
    max_tokens: int = 1200


@dataclass(frozen=True)
class ReportSpec:
    """A report template plus the metrics it needs.

    ``template`` is plain text with ``{metric_id}`` placeholders. ``metrics`` are
    the specs whose figures fill those placeholders. ``title`` heads the rendered
    report. ``charts``, ``comparison``, and ``reconciliation`` are optional
    sections; their numbers are figures too, held to the same grounding gate.
    ``data_checks`` are author-declared data-quality preconditions that assert
    before any figure is computed and fail closed, so a bad export is refused
    before a single number is produced.

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
    reconciliation: ReconciliationSpec | None = None
    templates: tuple[TemplateSpec, ...] = field(default_factory=tuple)
    drafting: DraftingSpec = field(default_factory=DraftingSpec)
    requirements: RequirementsSpec | None = None

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


@dataclass(frozen=True)
class SuppressedSpan:
    """A number in prose that states a cell the report refuses to publish.

    This is not an unbound span, and reporting it as one would send the author
    looking for a missing metric. The number is real and fully receipted; it is
    the raw value of a figure small-cell suppression redacted, so writing it into
    a narrative discloses a protected cell. ``metric_ids`` names every suppressed
    figure whose pre-suppression display canonicalizes to this number.

    ``publishable_metric_ids`` names any *publishable* figure that canonicalizes
    to the same number. When it is non-empty the span is genuinely ambiguous: the
    prose could be stating either figure, and nothing in the text says which. The
    span is still classified as a disclosure -- resolving the ambiguity toward
    "they must have meant the publishable one" is the unsafe direction -- but the
    ambiguity is reported rather than hidden, so the author can see that the
    number they wrote is also the exact value of a cell the report withholds.
    """

    span: NumericSpan
    metric_ids: tuple[str, ...]
    publishable_metric_ids: tuple[str, ...] = ()

    @property
    def ambiguous(self) -> bool:
        return bool(self.publishable_metric_ids)


@dataclass(frozen=True)
class SpanCandidate:
    """One receipted display an unresolved numeric span may have been meant to state.

    A candidate is a *diagnosis*, never a verdict. It is derived from the same
    canonicalization the gate uses (see ``grounding``), so it can never disagree
    with the gate about what binds; it says only what the gate found nearby and
    why the two did not match.

    ``reason`` is the machine-readable class of near-miss and ``detail`` is the
    sentence a human reads. ``distance`` is the absolute difference between the
    span's value and the candidate display's value where both resolve to a
    number, and ``None`` where the near-miss is not a numeric one (a separator
    ambiguity, a percent stated as a count). It orders candidates within a
    reason class and nothing else.

    ``substitutable`` is the field ``apply_fixes`` branches on, and it is false
    for every candidate drawn from the suppressed set. A withheld cell's raw
    display is a real, receipted string; writing it into the narrative would be
    the disclosure the gate exists to stop, so a disclosure is offered removal
    and never a replacement.
    """

    metric_id: str
    display: str
    reason: str
    detail: str
    distance: float | None = None
    substitutable: bool = True


@dataclass(frozen=True)
class Explanation:
    """Why one numeric span did not bind, and what a human may do about it.

    ``remedy`` is one of four words and each means something different:

    ``replace``  exactly one substitutable candidate is nearest, so a fix plan
                 may offer its display.
    ``remove``   the span states a cell the report withholds. Removal is the
                 only remedy; no substitution is ever offered.
    ``review``   two or more candidates tie for nearest, so nothing can be
                 chosen mechanically. ``apply_fixes`` refuses a span in this
                 state rather than picking one.
    ``none``     no receipted display is near this number at all. That is not a
                 failure of the diagnosis; it is the diagnosis, and it says the
                 number has to be removed or made into a metric.

    ``candidates`` may be empty only when ``remedy`` is ``none``. An explanation
    with a remedy of ``replace`` and no candidate would be an empty suggestion
    rendered as a real one, so the invariant is asserted rather than assumed.
    """

    span: NumericSpan
    remedy: str
    detail: str
    candidates: tuple[SpanCandidate, ...] = ()

    def __post_init__(self) -> None:
        if self.remedy not in ("replace", "remove", "review", "none"):
            raise ValueError(f"unknown remedy {self.remedy!r}")
        if self.remedy == "none" and self.candidates:
            raise ValueError("remedy 'none' cannot carry candidates")
        if self.remedy != "none" and not self.candidates:
            raise ValueError(f"remedy {self.remedy!r} requires at least one candidate")
        if self.remedy == "replace" and not self.candidates[0].substitutable:
            raise ValueError("remedy 'replace' requires a substitutable candidate")

    @property
    def replacement(self) -> SpanCandidate | None:
        """The one display a fix plan may offer, or ``None``.

        Only a ``replace`` remedy has one. ``review`` deliberately returns
        ``None`` even though it carries candidates: a tie is exactly the case a
        machine must not resolve.
        """

        return self.candidates[0] if self.remedy == "replace" else None


@dataclass(frozen=True)
class AuditResult:
    """The outcome of auditing a narrative against the publishable figure set.

    Three outcomes, not two. ``bound`` spans match a figure the report will
    actually publish. ``suppressed`` spans match a figure suppression redacted,
    so the narrative would publish a protected cell. ``unbound`` spans match
    nothing at all. ``ok`` requires both failing categories to be empty, so a
    narrative that discloses a protected cell fails exactly as hard as one that
    invents a number.
    """

    bound: tuple[NumericSpan, ...]
    suppressed: tuple[SuppressedSpan, ...]
    unbound: tuple[NumericSpan, ...]
    #: Diagnoses for the failing spans, empty unless a caller asked for them.
    #: ``ok`` and ``total`` do not read this field and never will: an
    #: explanation is advice about a verdict already reached, so adding one
    #: cannot change the verdict or the exit code derived from it.
    explanations: tuple[Explanation, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.suppressed and not self.unbound

    @property
    def total(self) -> int:
        return len(self.bound) + len(self.suppressed) + len(self.unbound)
