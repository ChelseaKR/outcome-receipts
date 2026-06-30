"""Period-over-period comparison, every number SQL-grounded.

A comparison takes one set of metrics, each written with a ``{period}`` placeholder
in its SQL, and computes each metric for a prior period and a current period, then
the change between them. The two period figures are ordinary Figures: the engine
runs the metric's query with the period's predicate substituted, so each carries a
receipt. The change is a Figure too, and it is not Python arithmetic over the other
two: its value comes from a single deterministic query that subtracts the prior
period's scalar from the current period's scalar inside SQLite, with a slice that
is the union of both periods' rows. So the delta traces to a receipt exactly as the
period figures do, and the grounding gate can verify it.

The delta Figure carries the signed change in its value and receipt (an honest
record of current minus prior), but its display is the magnitude, because the
grounding gate matches the bare number a reader sees. Direction is reported as a
word, not a number.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace

from outcome_receipts.clock import Clock, SystemClock
from outcome_receipts.engine import _format, compute_figure, load_table
from outcome_receipts.models import ComparisonSpec, Figure, MetricSpec, PeriodSpec

_PLACEHOLDER = "{period}"


def _require_placeholder(spec: MetricSpec) -> None:
    if _PLACEHOLDER not in spec.value_sql or _PLACEHOLDER not in spec.slice_sql:
        raise ValueError(
            f"comparison metric {spec.metric_id!r} must use the {_PLACEHOLDER} "
            "placeholder in both value_sql and slice_sql"
        )


def _for_period(spec: MetricSpec, period: PeriodSpec) -> MetricSpec:
    """A concrete metric spec for one period: substitute its predicate."""

    return replace(
        spec,
        metric_id=f"{spec.metric_id}__{period.period_id}",
        value_sql=spec.value_sql.replace(_PLACEHOLDER, period.predicate),
        slice_sql=spec.slice_sql.replace(_PLACEHOLDER, period.predicate),
    )


def _delta_spec(spec: MetricSpec, current: PeriodSpec, prior: PeriodSpec) -> MetricSpec:
    """A metric spec whose query is the SQL difference current minus prior.

    The value is a single scalar query: the current period's value query and the
    prior period's value query each become a scalar subquery, and SQLite subtracts
    them. The slice is the union of both periods' rows, so the receipt's row count
    and slice hash cover every record that fed the delta.
    """

    current_value = spec.value_sql.replace(_PLACEHOLDER, current.predicate)
    prior_value = spec.value_sql.replace(_PLACEHOLDER, prior.predicate)
    current_slice = spec.slice_sql.replace(_PLACEHOLDER, current.predicate)
    prior_slice = spec.slice_sql.replace(_PLACEHOLDER, prior.predicate)
    return replace(
        spec,
        metric_id=f"{spec.metric_id}__delta",
        value_sql=f"SELECT ({current_value}) - ({prior_value})",
        slice_sql=f"SELECT * FROM ({current_slice}) UNION ALL SELECT * FROM ({prior_slice})",
    )


def _magnitude_display(value: float, decimals: int) -> str:
    """Format the absolute change as a bare number the grounding gate can bind.

    A percentage metric's change is in percentage points, so it is shown without a
    percent sign; the column header names the unit. This keeps the displayed token
    a plain number that the gate matches, while the receipt keeps the signed value.
    """

    return _format(abs(value), "count", decimals)


@dataclass(frozen=True)
class ComparisonRow:
    """One metric compared across the two periods.

    ``prior`` and ``current`` are the period figures; ``delta`` is the change
    figure. ``direction`` is ``"increase"``, ``"decrease"``, or ``"no change"``,
    derived from the sign of the delta value, not from any number in prose.
    """

    base_metric_id: str
    description: str
    prior: Figure
    current: Figure
    delta: Figure
    direction: str

    @property
    def arrow(self) -> str:
        return {"increase": "up", "decrease": "down", "no change": "flat"}[self.direction]


@dataclass(frozen=True)
class ComparisonResult:
    """The computed comparison: its rows and the flat list of figures it produced.

    ``figures`` is every period and delta figure, so callers add them to the report
    figure set the grounding gate and the receipts manifest draw from.
    """

    current_label: str
    prior_label: str
    rows: tuple[ComparisonRow, ...]
    figures: tuple[Figure, ...]


def _direction(value: float) -> str:
    if value > 0:
        return "increase"
    if value < 0:
        return "decrease"
    return "no change"


def compute_comparison(
    rows: Sequence[dict[str, str]],
    comparison: ComparisonSpec,
    *,
    clock: Clock | None = None,
    table: str = "data",
) -> ComparisonResult:
    """Compute every period and delta figure for a comparison.

    One in-memory table is loaded and reused for every period and delta query, so
    the periods are compared over the same data slice the rest of the report uses.
    """

    clock = clock or SystemClock()
    current = comparison.period(comparison.current)
    prior = comparison.period(comparison.prior)

    conn = load_table(rows, table=table)
    try:
        result_rows: list[ComparisonRow] = []
        figures: list[Figure] = []
        for spec in comparison.metrics:
            _require_placeholder(spec)
            prior_fig = compute_figure(conn, _for_period(spec, prior), clock=clock)
            current_fig = compute_figure(conn, _for_period(spec, current), clock=clock)
            raw_delta = compute_figure(conn, _delta_spec(spec, current, prior), clock=clock)
            delta_fig = replace(
                raw_delta, display=_magnitude_display(raw_delta.value, spec.decimals)
            )
            result_rows.append(
                ComparisonRow(
                    base_metric_id=spec.metric_id,
                    description=spec.description,
                    prior=prior_fig,
                    current=current_fig,
                    delta=delta_fig,
                    direction=_direction(raw_delta.value),
                )
            )
            figures.extend((prior_fig, current_fig, delta_fig))
        return ComparisonResult(
            current_label=current.label,
            prior_label=prior.label,
            rows=tuple(result_rows),
            figures=tuple(figures),
        )
    finally:
        conn.close()
