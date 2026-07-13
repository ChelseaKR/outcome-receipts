"""Committed bilingual benchmark for the fail-closed numeric grounding gate."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from outcome_receipts.grounding import ground
from outcome_receipts.models import Figure, Receipt

BENCHMARK = Path(__file__).resolve().parents[1] / "eval" / "grounding-benchmark.jsonl"
CASES = [json.loads(line) for line in BENCHMARK.read_text(encoding="utf-8").splitlines()]


def _figure(display: str) -> Figure:
    value = float(display)
    receipt = Receipt(
        metric_id="served",
        value_sql="SELECT COUNT(*) FROM data",
        row_count=int(value),
        slice_hash="benchmark",
        value=value,
        unit="count",
        computed_at="1970-01-01T00:00:00+00:00",
    )
    return Figure(metric_id="served", value=value, display=display, receipt=receipt)


def test_benchmark_shape_and_language_balance() -> None:
    assert len(CASES) == 100
    assert sum(case["language"] == "en" for case in CASES) == 50
    assert sum(case["language"] == "es" for case in CASES) == 50
    assert sum(bool(case["should_pass"]) for case in CASES) == 50


@pytest.mark.parametrize("case", CASES, ids=lambda case: str(case["id"]))
def test_bilingual_grounding_benchmark(case: dict[str, object]) -> None:
    display = str(case["display"])
    result = ground(str(case["narrative"]), [_figure(display)])
    assert result.ok is bool(case["should_pass"])
    if not bool(case["should_pass"]):
        assert len(result.unbound) == 1
