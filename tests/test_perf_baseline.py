"""Tests for the committed performance baseline and its regression check.

The check implements the portfolio Performance standard's PERF-03 control: a run
fails when any metric is more than 10% worse than `perf/baseline.json` in that
metric's declared direction. The point of these tests is that the check can
fail, in each of the ways it is supposed to. A performance gate that cannot go
red is the same defect as a grounding gate that cannot, and it is easier to miss
because a passing perf job looks identical either way.

The second point is that it can only fail for a reason the repository controls.
The gate used to score Lighthouse's `categories:performance`, which is a
simulated-throttling timing score of the machine that ran it. On byte-identical
input it was observed at 1.00 locally, 0.99 and 0.87 on GitHub-hosted runners --
0.87 and a pass in two jobs of a single workflow run, commit 5e5c7aa. Both the
0.90 floor and the 10% band around a 1.00 baseline sit inside that spread, so the
gate failed on runner contention. What is scored now is what the artifact is:
its bytes. Those measured 2469 every run, on every machine tried.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from scripts.check_perf_baseline import (
    BASELINE,
    OBSERVED_NOT_GATED,
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


def _report(
    tmp_path: Path,
    *,
    score: float | None,
    script_bytes: int | None,
    total_bytes: int | None = 2469,
) -> Path:
    audits: dict[str, object] = {}
    items: list[dict[str, object]] = [{"resourceType": "document", "transferSize": 2469}]
    if total_bytes is not None:
        items.append({"resourceType": "total", "transferSize": total_bytes})
    if script_bytes is not None:
        items.append({"resourceType": "script", "transferSize": script_bytes})
    if script_bytes is None and total_bytes is None:
        items = []
    audits["resource-summary"] = {"details": {"items": items}}
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
        # This repository's addition: the whole published artifact's transfer
        # weight, which is what "is the trace fast" reduces to for a static
        # document with no scripts, no stylesheets and no third-party requests.
        # It replaces the timing score as the thing actually scored.
        "total_kb_gzip",
    }
    assert set(baseline["direction"]) == set(baseline["metrics"])
    assert set(baseline["direction"].values()) <= {"lower_is_better", "higher_is_better"}


def test_a_script_byte_in_the_trace_fails_the_budget() -> None:
    # The regression this repository's budget exists for. The published trace is a
    # static document with no scripts, so the baseline is zero and any script at
    # all is more than 10% worse. Proven against the real gate as well: injecting a
    # 1 KB script into out/a11y/trace.html makes `lhci autorun` fail its
    # resource-summary assertion and this check report js_kb_gzip 0.411133.
    failures = regression_failures({"total_kb_gzip": 2.41, "js_kb_gzip": 0.411133}, _baseline())

    assert len(failures) == 1
    assert "js_kb_gzip regressed" in failures[0]
    assert "baseline of 0" in failures[0]


def test_a_slow_runner_is_not_a_regression(tmp_path: Path) -> None:
    # The bug this gate had. Run 33591194873 on commit 5e5c7aa scored 0.87 in the
    # `verify` job and passed in the `accessibility` job -- same commit, same
    # command, same workflow run -- and a re-run of that identical commit four
    # days later scored a pass with no code change at all. The artifact was
    # byte-identical in every case. A timing score of a contended runner is not
    # evidence about this repository, so it is measured and reported but not
    # scored.
    measurement = read_measurement(_report(tmp_path, score=0.87, script_bytes=0))

    assert measurement.lighthouse_performance == 0.87
    assert regression_failures(measurement.gated(), _baseline()) == []


def test_the_score_is_excluded_on_purpose_and_says_why() -> None:
    # Not scored, and not by accident: the exclusion is declared, with its reason,
    # so that "the gate stopped covering this" cannot happen silently the way a
    # metric quietly dropped from the measurement would.
    assert "lighthouse_performance" in OBSERVED_NOT_GATED
    assert OBSERVED_NOT_GATED["lighthouse_performance"]
    assert (
        "lighthouse_performance"
        not in Measurement(js_kb_gzip=0.0, total_kb_gzip=2.41, lighthouse_performance=1.0).gated()
    )


def test_a_size_inside_the_ten_percent_band_passes() -> None:
    # The control. The committed baseline is 2.4111328125 KB, so 2.5 KB is worse
    # but not by more than 10% and the regression half stays silent. The absolute
    # ceiling is Lighthouse-CI's own `resource-summary:total:size` assertion,
    # made in the same run from the same config.
    assert regression_failures({"total_kb_gzip": 2.5, "js_kb_gzip": 0.0}, _baseline()) == []


def test_a_trace_that_grew_past_the_band_fails() -> None:
    # The teeth the byte budget has in place of the timing score. 2.4111328125 KB
    # plus 10% is 2.65 KB; 4 KB of newly embedded content is a real regression in
    # the weight of the artifact a funder downloads, and it is one this repository
    # actually controls.
    failures = regression_failures({"total_kb_gzip": 4.0, "js_kb_gzip": 0.0}, _baseline())

    assert len(failures) == 1
    assert "total_kb_gzip regressed" in failures[0]
    assert "lower_is_better" in failures[0]


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
        read_measurement(_report(tmp_path, score=1.0, script_bytes=None, total_bytes=None))


def test_a_report_without_a_total_row_fails_closed(tmp_path: Path) -> None:
    # Same rule for the metric that replaced the timing score. An absent total row
    # is an unmeasured budget, not an empty page.
    with pytest.raises(PerfCheckError, match="no total row"):
        read_measurement(_report(tmp_path, score=1.0, script_bytes=0, total_bytes=None))


def test_a_real_shaped_report_reads_as_the_baseline_names_it(tmp_path: Path) -> None:
    measurement = read_measurement(
        _report(tmp_path, score=1.0, script_bytes=2048, total_bytes=4096)
    )

    assert measurement == Measurement(js_kb_gzip=2.0, total_kb_gzip=4.0, lighthouse_performance=1.0)


def test_every_gated_metric_is_declared_in_the_committed_baseline() -> None:
    # The failure mode the exclusion above could otherwise introduce: a metric
    # that is measured, is not scored, and is not declared anywhere either, so
    # nothing covers it and nothing says so. Every name the check scores has to
    # exist in the file it is scored against.
    gated = Measurement(js_kb_gzip=0.0, total_kb_gzip=2.41, lighthouse_performance=1.0).gated()

    assert gated
    assert set(gated) <= set(_baseline()["metrics"])
