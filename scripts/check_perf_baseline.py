"""Compare the latest Lighthouse run against the committed performance baseline.

This is the portfolio Performance standard's PERF-03 control: for every metric
the baseline declares, a run fails when the measurement is more than 10% worse in
that metric's declared direction. `perf/baseline.json` is the comparand, and it
is a committed file rather than a dashboard or the previous CI run, so the number
a failure is measured against is in the diff and can be re-verified.

Two things this deliberately does not do.

It does not re-run Lighthouse. `make a11y` already runs `lhci autorun` against
the generated trace, and the standard requires one Lighthouse config per
repository rather than two with drifting numbers, so this reads that run's own
report. The absolute budgets (performance >= 0.9, script transfer 0 bytes) are
asserted there, by Lighthouse-CI itself; this file adds the regression half.

It does not accept a report it cannot prove is current. Reading whatever
`.lighthouseci` happens to hold would turn every red Lighthouse run into a green
performance check scored against a stale report, which is the failure mode this
whole gate exists to prevent. A report older than the trace it claims to
describe, or no report at all, fails.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "perf" / "baseline.json"
LHCI_DIR = ROOT / ".lighthouseci"
TRACE = ROOT / "out" / "a11y" / "trace.html"

# lhci writes one report per run as `.lighthouseci/lhr-<epoch-milliseconds>.json`.
# The timestamp is in the name, so the newest run is identified without trusting
# filesystem mtimes, which a checkout or a copy rewrites.
_LHR_RE = re.compile(r"^lhr-([0-9]+)\.json$")

# The 10% rule from the standard, one place.
_REGRESSION_TOLERANCE = 0.10


class PerfCheckError(Exception):
    """The check could not be performed, which is never a pass."""


@dataclass(frozen=True)
class Measurement:
    """The metrics one Lighthouse report carries, in baseline.json's names."""

    lighthouse_performance: float
    js_kb_gzip: float

    def as_dict(self) -> dict[str, float]:
        return {
            "lighthouse_performance": self.lighthouse_performance,
            "js_kb_gzip": self.js_kb_gzip,
        }


def latest_report(lhci_dir: Path) -> tuple[int, Path]:
    """The newest `lhr-*.json` in ``lhci_dir`` as ``(run epoch ms, path)``, or raise."""

    reports = [
        (int(match.group(1)), path)
        for path in lhci_dir.glob("lhr-*.json")
        if (match := _LHR_RE.match(path.name)) is not None
    ]
    if not reports:
        raise PerfCheckError(
            f"no Lighthouse report in {lhci_dir.name}; run `make a11y` first, and treat its "
            "failure as this gate's failure rather than scoring an older run"
        )
    return max(reports)


def read_measurement(report_path: Path) -> Measurement:
    """Pull the baseline's metrics out of one Lighthouse report."""

    report = json.loads(report_path.read_text(encoding="utf-8"))
    try:
        score = report["categories"]["performance"]["score"]
    except (KeyError, TypeError) as exc:
        raise PerfCheckError(f"{report_path.name} carries no performance category score") from exc
    if score is None:
        raise PerfCheckError(f"{report_path.name} reports a null performance score")

    items = report.get("audits", {}).get("resource-summary", {}).get("details", {}).get("items", [])
    script = next((item for item in items if item.get("resourceType") == "script"), None)
    if script is None:
        raise PerfCheckError(
            f"{report_path.name} carries no script row in its resource summary, so the "
            "JavaScript budget cannot be measured"
        )
    return Measurement(
        lighthouse_performance=float(score),
        js_kb_gzip=float(script["transferSize"]) / 1024.0,
    )


def regression_failures(
    measured: dict[str, float],
    baseline: dict[str, dict[str, object]],
) -> list[str]:
    """Every metric more than 10% worse than the baseline, in its own direction.

    A metric the baseline declares `null` is a declared N/A and is skipped; a
    metric the baseline does not mention at all is not, and fails, because an
    undeclared metric is one nobody decided about.
    """

    metrics = baseline["metrics"]
    directions = baseline["direction"]
    failures: list[str] = []
    for name, current in sorted(measured.items()):
        if name not in metrics:
            failures.append(f"{name} is measured but perf/baseline.json declares no value for it")
            continue
        expected = metrics[name]
        if expected is None:
            continue
        expected_value = float(str(expected))
        direction = directions.get(name)
        if direction == "lower_is_better":
            limit = expected_value * (1 + _REGRESSION_TOLERANCE)
            worse = current > limit
        elif direction == "higher_is_better":
            limit = expected_value * (1 - _REGRESSION_TOLERANCE)
            worse = current < limit
        else:
            failures.append(f"{name} has no usable direction in perf/baseline.json: {direction!r}")
            continue
        if worse:
            failures.append(
                f"{name} regressed: {current:g} against a baseline of {expected_value:g} "
                f"({direction}, limit {limit:g}). Fix the regression, or update "
                "perf/baseline.json in the same pull request with the reason, per the "
                "baseline update ritual in perf/README.md"
            )
    return failures


def main() -> int:
    """Return nonzero when the check fails or cannot be performed."""

    try:
        baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
        report_ms, report_path = latest_report(LHCI_DIR)
        if not TRACE.exists():
            raise PerfCheckError(
                "out/a11y/trace.html does not exist, so no Lighthouse report can be current; "
                "run `make a11y`"
            )
        if report_ms < int(TRACE.stat().st_mtime * 1000):
            raise PerfCheckError(
                f"{report_path.name} predates the trace it would be scored against; the "
                "Lighthouse run did not complete for this build. Run `make a11y`"
            )
        measurement = read_measurement(report_path)
    except (OSError, ValueError, PerfCheckError) as exc:
        print(f"performance baseline: FAIL - {exc}", file=sys.stderr)
        return 1

    failures = regression_failures(measurement.as_dict(), baseline)
    if failures:
        print("performance baseline failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print(
        "performance baseline: pass "
        f"(lighthouse_performance {measurement.lighthouse_performance:g}, "
        f"js_kb_gzip {measurement.js_kb_gzip:g})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
