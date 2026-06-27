"""Report-spec loading.

A report is configured by a TOML file: the data source, the report title and
template, and the metric definitions. File paths resolve relative to the spec's
own directory so a spec and its data move together.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from outcome_receipts.models import MetricSpec, ReportSpec

_VALID_UNITS = frozenset({"count", "percent"})


@dataclass(frozen=True)
class Spec:
    """A loaded report spec plus the resolved path to its data."""

    data_path: Path
    report: ReportSpec


def _resolve(base: Path, value: str) -> Path:
    candidate = Path(value)
    return candidate if candidate.is_absolute() else (base / candidate)


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

    metrics: list[MetricSpec] = []
    for metric_id, body in metric_section.items():
        if "value_sql" not in body or "slice_sql" not in body:
            raise ValueError(f"metric {metric_id!r} must set value_sql and slice_sql")
        unit = str(body.get("unit", "count"))
        if unit not in _VALID_UNITS:
            raise ValueError(
                f"metric {metric_id!r} unit {unit!r} must be one of {sorted(_VALID_UNITS)}"
            )
        metrics.append(
            MetricSpec(
                metric_id=str(metric_id),
                description=str(body.get("description", "")),
                value_sql=str(body["value_sql"]),
                slice_sql=str(body["slice_sql"]),
                unit=unit,
                decimals=int(body.get("decimals", 0)),
            )
        )

    report = ReportSpec(
        title=str(report_section.get("title", "Outcome report")),
        template=str(report_section["template"]),
        metrics=tuple(metrics),
    )
    return Spec(data_path=_resolve(base, str(data_section["path"])), report=report)
