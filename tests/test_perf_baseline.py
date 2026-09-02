"""Tests for the committed performance baseline and its regression check.

The check implements the portfolio Performance standard's PERF-03 control: a run
fails when any metric is more than 10% worse than `perf/baseline.json` in that
metric's declared direction. The point of these tests is that the check can
fail, in each of the ways it is supposed to. A performance gate that cannot go
red is the same defect as a grounding gate that cannot, and it is easier to miss
because a passing perf job looks identical either way.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from scripts.check_perf_baseline import (
    BASELINE,
    Measurement,
    PerfCheckError,
    latest_report,
    read_measurement,
    regression_failures,
)

ROOT = Path(__file__).resolve().parents[1]


def _baseline() -> dict[str, dict[str, object]]:
    loaded: dict[str, dict[str, object]] = json.loads(BASELINE.read_text(encoding="utf-8"))
    return loaded


def _report(tmp_path: Path, *, score: float | None, script_bytes: int | None) -> Path:
    audits: dict[str, object] = {}
    if script_bytes is not None:
        audits["resource-summary"] = {
            "details": {
                "items": [
                    {"resourceType": "document", "transferSize": 2469},
                    {"resourceType": "script", "transferSize": script_bytes},
                ]
            }
        }
    else:
        audits["resource-summary"] = {"details": {"items": []}}
    path = tmp_path / "lhr-1000.json"
    path.write_text(
        json.dumps({"categories": {"performance": {"score": score}}, "audits": audits}),
        encoding="utf-8",
    )
    return path


def test_the_committed_baseline_has_the_schema_the_standard_requires() -> None:
    baseline = _baseline()
    assert set(baseline) == {"meta", "metrics", "direction"}
    assert set(baseline["meta"]) == {"commit", "date", "environment", "tools"}
    # Every metric the standard names is present. An inapplicable one is an
    # explicit null, never silently absent, so a declared N/A is visible.
    assert set(baseline["metrics"]) == {
        "p95_ms",
        "llm_first_token_ms",
        "llm_full_response_ms",
        "lighthouse_performance",
        "js_kb_gzip",
    }
    assert set(baseline["direction"]) == set(baseline["metrics"])
    assert set(baseline["direction"].values()) <= {"lower_is_better", "higher_is_better"}


def test_a_script_byte_in_the_trace_fails_the_budget() -> None:
    # The regression this repository's budget exists for. The published trace is a
    # static document with no scripts, so the baseline is zero and any script at
    # all is more than 10% worse. Proven against the real gate as well: injecting a
    # 1 KB script into out/a11y/trace.html makes `lhci autorun` fail its
    # resource-summary assertion and this check report js_kb_gzip 0.411133.
    failures = regression_failures(
        {"lighthouse_performance": 1.0, "js_kb_gzip": 0.411133}, _baseline()
    )

    assert len(failures) == 1
    assert "js_kb_gzip regressed" in failures[0]
    assert "baseline of 0" in failures[0]


def test_a_dropped_lighthouse_score_fails_in_the_other_direction() -> None:
    failures = regression_failures({"lighthouse_performance": 0.85, "js_kb_gzip": 0.0}, _baseline())

    assert len(failures) == 1
    assert "lighthouse_performance regressed" in failures[0]
    assert "higher_is_better" in failures[0]


def test_a_score_inside_the_ten_percent_band_passes() -> None:
    # The control. 0.91 against a baseline of 1.0 is worse but not by more than
    # 10%, so the regression half stays silent; the absolute floor of 0.9 is
    # Lighthouse-CI's own assertion, asserted in the same run from the same config.
    assert (
        regression_failures({"lighthouse_performance": 0.91, "js_kb_gzip": 0.0}, _baseline()) == []
    )


def test_a_metric_the_baseline_never_declared_fails_rather_than_passing() -> None:
    # An undeclared metric is one nobody decided about, so it is not silently
    # skipped. A baseline that quietly ignores what it does not recognize is a
    # gate that stops covering whatever gets added next.
    failures = regression_failures({"invented_metric": 1.0}, _baseline())

    assert failures == [
        "invented_metric is measured but perf/baseline.json declares no value for it"
    ]


def test_a_null_metric_is_a_declared_na_and_is_skipped() -> None:
    # p95_ms is null: this project has no hosted route to measure. That is a
    # declaration, not an omission, and it does not fail.
    assert regression_failures({"p95_ms": 9999.0}, _baseline()) == []


def test_an_unusable_direction_fails_rather_than_guessing() -> None:
    baseline = _baseline()
    baseline["direction"]["js_kb_gzip"] = "sideways"

    failures = regression_failures({"js_kb_gzip": 0.0}, baseline)

    assert len(failures) == 1
    assert "no usable direction" in failures[0]


def test_no_report_is_a_failure_not_a_pass(tmp_path: Path) -> None:
    with pytest.raises(PerfCheckError, match="no Lighthouse report"):
        latest_report(tmp_path)


def test_the_newest_report_is_chosen_by_its_own_timestamp(tmp_path: Path) -> None:
    # By the epoch milliseconds in the name, not by filesystem mtime, which a
    # checkout or a copy rewrites.
    for name in ("lhr-100.json", "lhr-2000.json", "lhr-30.json", "not-a-report.json"):
        (tmp_path / name).write_text("{}", encoding="utf-8")

    run_ms, path = latest_report(tmp_path)

    assert (run_ms, path.name) == (2000, "lhr-2000.json")


def test_a_report_without_a_performance_score_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(PerfCheckError, match="null performance score"):
        read_measurement(_report(tmp_path, score=None, script_bytes=0))


def test_a_report_without_a_script_row_fails_closed(tmp_path: Path) -> None:
    # No script row means the budget was not measured. Reading that as zero bytes
    # would turn a broken measurement into a passing one.
    with pytest.raises(PerfCheckError, match="no script row"):
        read_measurement(_report(tmp_path, score=1.0, script_bytes=None))


def test_a_real_shaped_report_reads_as_the_baseline_names_it(tmp_path: Path) -> None:
    measurement = read_measurement(_report(tmp_path, score=1.0, script_bytes=2048))

    assert measurement == Measurement(lighthouse_performance=1.0, js_kb_gzip=2.0)
