"""The public report-spec schema and loader version policy stay aligned."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path
from typing import Any, cast

from outcome_receipts.config import SPEC_SCHEMA_VERSION

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "docs" / "schema" / "report-spec.schema.json"


def _schema() -> dict[str, Any]:
    raw: object = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    return cast(dict[str, Any], raw)


def test_report_spec_schema_pins_the_loader_version() -> None:
    schema = _schema()
    assert schema["properties"]["schema_version"]["const"] == SPEC_SCHEMA_VERSION
    assert set(schema["required"]) == {"schema_version", "data", "report", "metrics"}
    assert schema["additionalProperties"] is False


def test_report_spec_schema_declares_every_loader_section() -> None:
    properties = _schema()["properties"]
    assert set(properties) == {
        "schema_version",
        "data",
        "report",
        "metrics",
        "data_checks",
        "charts",
        "comparison",
        "reconciliation",
    }


def test_maintained_examples_declare_the_current_schema() -> None:
    schema = _schema()
    root_properties = set(schema["properties"])
    report_properties = set(schema["properties"]["report"]["properties"])
    metric_properties = set(schema["$defs"]["metric"]["properties"])
    chart_properties = set(schema["$defs"]["chart"]["properties"])
    comparison_properties = set(schema["$defs"]["comparison"]["properties"])
    period_properties = set(schema["$defs"]["period"]["properties"])
    reconciliation_properties = set(schema["$defs"]["reconciliation"]["properties"])
    row_properties = set(schema["$defs"]["reconciliation_metric_pair"]["properties"])

    specs = sorted((ROOT / "examples").glob("*/report.toml"))
    assert specs
    for path in specs:
        with path.open("rb") as handle:
            parsed = tomllib.load(handle)
        assert parsed["schema_version"] == SPEC_SCHEMA_VERSION, path
        assert set(parsed) <= root_properties, path
        assert set(parsed["report"]) <= report_properties, path
        for metric in parsed["metrics"].values():
            assert set(metric) <= metric_properties, path
        for chart in parsed.get("charts", []):
            assert set(chart) <= chart_properties, path
        if comparison := parsed.get("comparison"):
            assert set(comparison) <= comparison_properties, path
            for period in comparison["periods"]:
                assert set(period) <= period_properties, path
            for metric in comparison["metrics"].values():
                assert set(metric) <= metric_properties, path
        if reconciliation := parsed.get("reconciliation"):
            assert set(reconciliation) <= reconciliation_properties, path
            for period in reconciliation["periods"]:
                assert set(period) <= period_properties, path
            for row in reconciliation["rows"]:
                assert set(row) <= row_properties, path
                assert set(row["outcome"]) <= metric_properties, path
                assert set(row["financial"]) <= metric_properties, path
