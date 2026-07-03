"""Report-spec loading.

A report is configured by a TOML file: the data source, the report title and
template, the metric definitions, and three optional sections. ``[[charts]]`` draws
a chart from named figures, ``[comparison]`` compares a set of metrics across two
periods, and ``[[data_checks]]`` declares data-quality preconditions asserted before
any figure is computed. Every number a chart or comparison renders is still a figure
with a receipt; nothing here introduces an ungrounded path to a number. File paths
resolve relative to the spec's own directory so a spec and its data move together.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from outcome_receipts.models import (
    ChartSpec,
    ComparisonSpec,
    DataCheck,
    MetricSpec,
    PeriodSpec,
    ReportSpec,
)

_VALID_UNITS = frozenset({"count", "percent"})
_VALID_CHART_KINDS = frozenset({"bar", "line"})


@dataclass(frozen=True)
class Spec:
    """A loaded report spec plus the resolved path to its data."""

    data_path: Path
    report: ReportSpec


def _resolve(base: Path, value: str) -> Path:
    candidate = Path(value)
    return candidate if candidate.is_absolute() else (base / candidate)


def _parse_metric(metric_id: str, body: dict[str, Any]) -> MetricSpec:
    if "value_sql" not in body or "slice_sql" not in body:
        raise ValueError(f"metric {metric_id!r} must set value_sql and slice_sql")
    unit = str(body.get("unit", "count"))
    if unit not in _VALID_UNITS:
        raise ValueError(
            f"metric {metric_id!r} unit {unit!r} must be one of {sorted(_VALID_UNITS)}"
        )
    return MetricSpec(
        metric_id=str(metric_id),
        description=str(body.get("description", "")),
        value_sql=str(body["value_sql"]),
        slice_sql=str(body["slice_sql"]),
        unit=unit,
        decimals=int(body.get("decimals", 0)),
        definition=str(body.get("definition", "")),
    )


def _parse_charts(raw: object) -> tuple[ChartSpec, ...]:
    if not raw:
        return ()
    if not isinstance(raw, list):
        raise ValueError("[[charts]] must be an array of tables")
    charts: list[ChartSpec] = []
    for entry in raw:
        if "id" not in entry:
            raise ValueError("each [[charts]] entry must set 'id'")
        chart_id = str(entry["id"])
        kind = str(entry.get("kind", "bar"))
        if kind not in _VALID_CHART_KINDS:
            raise ValueError(
                f"chart {chart_id!r} kind {kind!r} must be one of {sorted(_VALID_CHART_KINDS)}"
            )
        metric_ids = tuple(str(m) for m in entry.get("metrics", ()))
        if not metric_ids:
            raise ValueError(f"chart {chart_id!r} must name at least one metric")
        labels = tuple(str(label) for label in entry.get("labels", ()))
        charts.append(
            ChartSpec(
                chart_id=chart_id,
                title=str(entry.get("title", chart_id)),
                kind=kind,
                metric_ids=metric_ids,
                labels=labels,
            )
        )
    return tuple(charts)


def _parse_data_checks(raw: object) -> tuple[DataCheck, ...]:
    if not raw:
        return ()
    if not isinstance(raw, list):
        raise ValueError("[[data_checks]] must be an array of tables")
    checks: list[DataCheck] = []
    for entry in raw:
        if "id" not in entry or "assert_sql" not in entry:
            raise ValueError("each [[data_checks]] entry must set 'id' and 'assert_sql'")
        checks.append(
            DataCheck(
                check_id=str(entry["id"]),
                description=str(entry.get("description", "")),
                assert_sql=str(entry["assert_sql"]),
                message=str(entry.get("message", "")),
            )
        )
    return tuple(checks)


def _parse_comparison(raw: object) -> ComparisonSpec | None:
    if not raw:
        return None
    if not isinstance(raw, dict):
        raise ValueError("[comparison] must be a table")
    if "current" not in raw or "prior" not in raw:
        raise ValueError("[comparison] must set 'current' and 'prior'")
    periods_raw = raw.get("periods", [])
    if not isinstance(periods_raw, list) or not periods_raw:
        raise ValueError("[comparison] must define [[comparison.periods]]")
    periods: list[PeriodSpec] = []
    for entry in periods_raw:
        if "id" not in entry or "predicate" not in entry:
            raise ValueError("each [[comparison.periods]] entry must set 'id' and 'predicate'")
        period_id = str(entry["id"])
        periods.append(
            PeriodSpec(
                period_id=period_id,
                label=str(entry.get("label", period_id)),
                predicate=str(entry["predicate"]),
            )
        )
    metric_section = raw.get("metrics", {})
    if not metric_section:
        raise ValueError("[comparison] must define at least one [comparison.metrics.<id>]")
    metrics = tuple(
        _parse_metric(metric_id, body) for metric_id, body in metric_section.items()
    )
    current = str(raw["current"])
    prior = str(raw["prior"])
    known = {period.period_id for period in periods}
    for name in (current, prior):
        if name not in known:
            raise ValueError(f"[comparison] references unknown period {name!r}")
    return ComparisonSpec(
        current=current, prior=prior, periods=tuple(periods), metrics=metrics
    )


def load_spec(path: str | Path) -> Spec:
    spec_path = Path(path)
    base = spec_path.parent
    with spec_path.open("rb") as handle:
        data = tomllib.load(handle)

    data_section = data.get("data", {})
    report_section = data.get("report", {})
    metric_section = data.get("metrics", {})

    if "path" not in data_section:
        raise ValueError("spec [data] must set 'path'")
    if "template" not in report_section:
        raise ValueError("spec [report] must set 'template'")
    if not metric_section:
        raise ValueError("spec must define at least one [metrics.<id>]")

    metrics = tuple(_parse_metric(metric_id, body) for metric_id, body in metric_section.items())
    charts = _parse_charts(data.get("charts"))
    comparison = _parse_comparison(data.get("comparison"))
    data_checks = _parse_data_checks(data.get("data_checks"))

    report = ReportSpec(
        title=str(report_section.get("title", "Outcome report")),
        template=str(report_section["template"]),
        metrics=metrics,
        charts=charts,
        comparison=comparison,
        data_checks=data_checks,
    )
    return Spec(data_path=_resolve(base, str(data_section["path"])), report=report)
