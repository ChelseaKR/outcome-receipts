"""Report-spec loading.

A report is configured by a TOML file: the data source, the report title and
template, the metric definitions, and four optional sections. ``[[charts]]`` draws
a chart from named figures, ``[comparison]`` compares a set of metrics across two
periods, ``[reconciliation]`` pairs each outcome figure with a financial line over
the same two periods, and ``[[data_checks]]`` declares data-quality preconditions
asserted before any figure is computed, and ``[[report.templates]]`` names several funder formats
that render the same shared figures. Every number a chart or comparison renders is
still a figure with a receipt; nothing here introduces an ungrounded path to a
number. A metric may also carry optional logic-model mapping keys (``indicator``,
``data_source``, ``collection_frequency``). File paths resolve relative to the
spec's own directory so a spec and its data move together.
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
    DraftingSpec,
    MetricSpec,
    PeriodSpec,
    ReconciliationRow,
    ReconciliationSpec,
    ReportSpec,
    TemplateSpec,
)

_VALID_UNITS = frozenset({"count", "percent", "money", "duration", "rate"})
_VALID_KINDS = frozenset({"output", "outcome"})
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
    if not str(body.get("value_sql", "")).strip() or not str(body.get("slice_sql", "")).strip():
        raise ValueError(f"metric {metric_id!r} must set value_sql and slice_sql")
    unit = str(body.get("unit", "count"))
    if unit not in _VALID_UNITS:
        raise ValueError(
            f"metric {metric_id!r} unit {unit!r} must be one of {sorted(_VALID_UNITS)}"
        )
    kind = str(body.get("kind", "output"))
    if kind not in _VALID_KINDS:
        raise ValueError(
            f"metric {metric_id!r} kind {kind!r} must be one of {sorted(_VALID_KINDS)}"
        )
    return MetricSpec(
        metric_id=str(metric_id),
        description=str(body.get("description", "")),
        value_sql=str(body["value_sql"]),
        slice_sql=str(body["slice_sql"]),
        unit=unit,
        decimals=int(body.get("decimals", 0)),
        definition=str(body.get("definition", "")),
        kind=kind,
        indicator=str(body.get("indicator", "")),
        data_source=str(body.get("data_source", "")),
        collection_frequency=str(body.get("collection_frequency", "")),
        caveat=str(body.get("caveat", "")),
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


def _parse_templates(raw: object, *, default_title: str) -> tuple[TemplateSpec, ...]:
    """Parse the optional ``[[report.templates]]`` array of funder formats.

    Each entry names one funder template over the shared metrics. ``id`` and
    ``template`` are required; ``title`` defaults to the report title, so a terse
    and a fuller format can render the same figures without repeating the heading.
    """

    if not raw:
        return ()
    if not isinstance(raw, list):
        raise ValueError("[[report.templates]] must be an array of tables")
    templates: list[TemplateSpec] = []
    for entry in raw:
        if "id" not in entry or "template" not in entry:
            raise ValueError("each [[report.templates]] entry must set 'id' and 'template'")
        templates.append(
            TemplateSpec(
                template_id=str(entry["id"]),
                title=str(entry.get("title", default_title)),
                template=str(entry["template"]),
            )
        )
    return tuple(templates)


def _parse_periods(raw: object, *, section: str) -> tuple[PeriodSpec, ...]:
    """Parse the ``[[<section>.periods]]`` array of tables shared by both sections."""

    if not isinstance(raw, list) or not raw:
        raise ValueError(f"[{section}] must define [[{section}.periods]]")
    periods: list[PeriodSpec] = []
    for entry in raw:
        if "id" not in entry or "predicate" not in entry:
            raise ValueError(f"each [[{section}.periods]] entry must set 'id' and 'predicate'")
        period_id = str(entry["id"])
        periods.append(
            PeriodSpec(
                period_id=period_id,
                label=str(entry.get("label", period_id)),
                predicate=str(entry["predicate"]),
            )
        )
    return tuple(periods)


def _resolve_period_refs(
    raw: dict[str, Any], periods: tuple[PeriodSpec, ...], *, section: str
) -> tuple[str, str]:
    """Validate that the table's ``current``/``prior`` name defined periods."""

    if "current" not in raw or "prior" not in raw:
        raise ValueError(f"[{section}] must set 'current' and 'prior'")
    current = str(raw["current"])
    prior = str(raw["prior"])
    known = {period.period_id for period in periods}
    for name in (current, prior):
        if name not in known:
            raise ValueError(f"[{section}] references unknown period {name!r}")
    return current, prior


def _parse_comparison(raw: object) -> ComparisonSpec | None:
    if not raw:
        return None
    if not isinstance(raw, dict):
        raise ValueError("[comparison] must be a table")
    periods = _parse_periods(raw.get("periods"), section="comparison")
    current, prior = _resolve_period_refs(raw, periods, section="comparison")
    metric_section = raw.get("metrics", {})
    if not metric_section:
        raise ValueError("[comparison] must define at least one [comparison.metrics.<id>]")
    metrics = tuple(_parse_metric(metric_id, body) for metric_id, body in metric_section.items())
    return ComparisonSpec(current=current, prior=prior, periods=periods, metrics=metrics)


def _slug(text: str) -> str:
    """A stable metric-id-safe token derived from a row label."""

    token = "".join(ch if ch.isalnum() else "_" for ch in text.lower()).strip("_")
    while "__" in token:
        token = token.replace("__", "_")
    return token or "row"


def _parse_reconciliation(raw: object) -> ReconciliationSpec | None:
    if not raw:
        return None
    if not isinstance(raw, dict):
        raise ValueError("[reconciliation] must be a table")
    periods = _parse_periods(raw.get("periods"), section="reconciliation")
    current, prior = _resolve_period_refs(raw, periods, section="reconciliation")
    rows_raw = raw.get("rows", [])
    if not isinstance(rows_raw, list) or not rows_raw:
        raise ValueError("[reconciliation] must define at least one [[reconciliation.rows]]")
    rows: list[ReconciliationRow] = []
    for entry in rows_raw:
        if "label" not in entry:
            raise ValueError("each [[reconciliation.rows]] entry must set 'label'")
        label = str(entry["label"])
        row_id = str(entry.get("id", _slug(label)))
        if "outcome" not in entry:
            raise ValueError(
                f"reconciliation row {label!r} must set an [reconciliation.rows.outcome] metric"
            )
        if "financial" not in entry:
            raise ValueError(
                f"reconciliation row {label!r} must set an [reconciliation.rows.financial] metric"
            )
        rows.append(
            ReconciliationRow(
                label=label,
                outcome=_parse_metric(f"{row_id}_outcome", entry["outcome"]),
                financial=_parse_metric(f"{row_id}_financial", entry["financial"]),
            )
        )
    return ReconciliationSpec(current=current, prior=prior, periods=periods, rows=tuple(rows))


def load_spec(path: str | Path) -> Spec:
    spec_path = Path(path)
    base = spec_path.parent
    with spec_path.open("rb") as handle:
        data = tomllib.load(handle)

    data_section = data.get("data", {})
    report_section = data.get("report", {})
    metric_section = data.get("metrics", {})

    title = str(report_section.get("title", "Outcome report"))
    templates = _parse_templates(report_section.get("templates"), default_title=title)

    if "path" not in data_section:
        raise ValueError("spec [data] must set 'path'")
    if "template" not in report_section and not templates:
        raise ValueError("spec [report] must set 'template' or define [[report.templates]]")
    if not metric_section:
        raise ValueError("spec must define at least one [metrics.<id>]")

    metrics = tuple(_parse_metric(metric_id, body) for metric_id, body in metric_section.items())
    charts = _parse_charts(data.get("charts"))
    comparison = _parse_comparison(data.get("comparison"))
    data_checks = _parse_data_checks(data.get("data_checks"))
    reconciliation = _parse_reconciliation(data.get("reconciliation"))
    drafting_raw = report_section.get("drafting", {})
    if not isinstance(drafting_raw, dict):
        raise ValueError("[report.drafting] must be a table")
    drafting = DraftingSpec(
        provider=str(drafting_raw.get("provider", "deterministic")),
        enabled=bool(drafting_raw.get("enabled", False)),
        model_id=str(drafting_raw.get("model_id", "")),
        max_tokens=int(drafting_raw.get("max_tokens", 1200)),
    )
    if drafting.provider not in {"deterministic", "bedrock"}:
        raise ValueError("report.drafting.provider must be 'deterministic' or 'bedrock'")
    if drafting.enabled and drafting.provider == "bedrock" and not drafting.model_id:
        raise ValueError("enabled Bedrock drafting requires report.drafting.model_id")

    report = ReportSpec(
        title=title,
        template=str(report_section.get("template", "")),
        metrics=metrics,
        charts=charts,
        comparison=comparison,
        data_checks=data_checks,
        reconciliation=reconciliation,
        templates=templates,
        drafting=drafting,
    )
    return Spec(data_path=_resolve(base, str(data_section["path"])), report=report)
