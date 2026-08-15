#!/usr/bin/env python3
"""Adjudicate the OpenSSF Scorecard floors against the committed waiver registry.

The scorecard workflow used to assert its floors as a run of `jq -e` one-liners,
one of which was `Vulnerabilities == 10`. That is the right target and the wrong
gate shape: OpenSSF derives that check from OSV, OSV data changes without this
repository changing, and a `== 10` assertion turns any newly published advisory
against a pinned transitive dependency into a red default branch with no way to
say "reviewed, accepted, here is the expiry" short of lowering the number for
everything.

`npm audit` had the identical problem and SEC-12 already solved it: the severity
floor stays where it is and `scripts/check_npm_audit.py` adjudicates advisory by
advisory against `waivers.yml`. This gate applies that same rule to the Scorecard
Vulnerabilities check, and nothing else about the floors moves. A deduction is
accepted only when a live waiver names that exact advisory id; a new advisory, an
expired waiver, a malformed registry, a deduction whose advisories Scorecard did
not name, or a report this gate cannot parse all still fail.

Scorecard's Vulnerabilities check reads OSV over the same lockfiles the npm-audit
gate adjudicates, so it consults the same waiver kind. An advisory from another
ecosystem carries no waiver of that kind and therefore fails closed here --
deliberately, because pip-audit and OSV-Scanner would already be failing
`make security` for the same finding.

Reads a Scorecard `results_format: json` report from `--report` (default
`results.json`) and never runs Scorecard itself, so the merge gate and
tests/test_scorecard_gate.py exercise exactly the same code path.

Run it as a module from the repository root so the sibling import resolves:

  python3 -m scripts.check_scorecard --report results.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any

from scripts.check_npm_audit import live_waivers

ROOT = Path(__file__).resolve().parents[1]
WAIVERS_PATH = ROOT / "waivers.yml"

#: The aggregate floor. WVR-006 ratchets the measured baseline while OpenSSF
#: assigns zero Maintained score to repositories under 90 days old.
AGGREGATE_FLOOR = 6.8

#: Named critical-check floors, unchanged from the jq assertions they replace.
#: Branch-Protection is capped at 4 by WVR-005, the solo-maintainer exception.
FLOORS: tuple[tuple[str, str, float], ...] = (
    ("Pinned-Dependencies", ">=", 9),
    ("Token-Permissions", "==", 10),
    ("Dangerous-Workflow", "==", 10),
    ("Branch-Protection", ">=", 4),
    ("Signed-Releases", "==", 10),
)

#: The check whose deductions are adjudicated rather than asserted.
ADJUDICATED = "Vulnerabilities"

#: Advisory identifiers OSV surfaces through Scorecard's Vulnerabilities detail
#: lines. GHSA is what this repository's ecosystems produce; the others are
#: matched so a non-npm advisory is named in the failure rather than swallowed.
_ADVISORY_RE = re.compile(
    r"\b(GHSA-[0-9a-z]{4}-[0-9a-z]{4}-[0-9a-z]{4}"
    r"|CVE-\d{4}-\d{4,}"
    r"|(?:PYSEC|OSV|GO|RUSTSEC|MAL)-\d{4}-\d+)\b",
    re.IGNORECASE,
)


def check_scores(report: dict[str, Any]) -> dict[str, float]:
    """Return every named check score in the report, keyed by check name."""

    scores: dict[str, float] = {}
    checks = report.get("checks")
    if not isinstance(checks, list):
        return scores
    for check in checks:
        if not isinstance(check, dict):
            continue
        name = check.get("name")
        score = check.get("score")
        if isinstance(name, str) and isinstance(score, int | float):
            scores[name] = float(score)
    return scores


def named_advisories(report: dict[str, Any]) -> list[str]:
    """Return the advisory ids the Vulnerabilities check names, uppercased."""

    checks = report.get("checks")
    if not isinstance(checks, list):
        return []
    found: list[str] = []
    for check in checks:
        if not isinstance(check, dict) or check.get("name") != ADJUDICATED:
            continue
        for detail in check.get("details") or []:
            for match in _ADVISORY_RE.finditer(str(detail)):
                advisory = match.group(1).upper()
                if advisory not in found:
                    found.append(advisory)
    return found


def _floor_failure(name: str, operator: str, target: float, scores: dict[str, float]) -> str | None:
    """Return the failure text for one named floor, or None when it holds."""

    if name not in scores:
        return f"{name}: the report carries no such check; refusing to pass an unmeasured floor"
    actual = scores[name]
    if operator == ">=" and actual >= target:
        return None
    if operator == "==" and actual == target:
        return None
    return f"{name}: {actual:g}, floor is {operator} {target:g}"


def adjudicate_vulnerabilities(
    report: dict[str, Any], waivers: dict[str, dict[str, str]]
) -> tuple[list[str], list[str]]:
    """Return (failures, accepted) for the Vulnerabilities check.

    A full score passes with nothing to accept. Anything less must be fully
    explained: Scorecard has to name at least as many advisories as it deducted
    points, and every one of those has to carry a live waiver.
    """

    failures: list[str] = []
    accepted: list[str] = []
    scores = check_scores(report)
    if ADJUDICATED not in scores:
        return [f"{ADJUDICATED}: the report carries no such check"], accepted

    score = scores[ADJUDICATED]
    if score >= 10:
        return failures, accepted

    advisories = named_advisories(report)
    deducted = 10 - score
    if len(advisories) < deducted:
        failures.append(
            f"{ADJUDICATED}: scored {score:g}, so {deducted:g} point(s) were deducted, but the "
            f"report names only {len(advisories)} advisory id(s) "
            f"({', '.join(advisories) or 'none'}); refusing to pass deductions this gate "
            "cannot attribute"
        )

    for advisory in advisories:
        waiver = waivers.get(advisory)
        if waiver is None:
            failures.append(f"{advisory}: no waiver. OpenSSF Scorecard counts it against SEC-37")
            continue
        accepted.append(
            f"{waiver['advisory']} in {waiver['package']}: accepted by {waiver['id']}, "
            f"expires {waiver['expires']}"
        )
    return failures, accepted


def load_report(path: Path) -> tuple[dict[str, Any] | None, str]:
    """Return the parsed Scorecard report, or the reason it cannot be used."""

    if not path.exists():
        return None, f"no Scorecard report at {path}; the analysis did not run"
    raw = path.read_text(encoding="utf-8")
    if not raw.strip():
        return None, f"the Scorecard report at {path} is empty; the analysis did not run"
    try:
        report = json.loads(raw)
    except json.JSONDecodeError:
        return None, f"the Scorecard report at {path} is not JSON:\n{raw[:2000]}"
    if not isinstance(report, dict) or not isinstance(report.get("checks"), list):
        return None, f"the Scorecard report at {path} carries no checks array"
    if not isinstance(report.get("score"), int | float):
        return None, f"the Scorecard report at {path} carries no aggregate score"
    return report, ""


def evaluate(
    report: dict[str, Any], waivers: dict[str, dict[str, str]]
) -> tuple[list[str], list[str]]:
    """Return (failures, evidence) for one Scorecard report."""

    scores = check_scores(report)
    failures: list[str] = []
    evidence: list[str] = []

    aggregate = float(report["score"])
    if aggregate < AGGREGATE_FLOOR:
        failures.append(f"aggregate: {aggregate:g}, floor is >= {AGGREGATE_FLOOR:g}")
    else:
        evidence.append(f"aggregate {aggregate:g} (floor >= {AGGREGATE_FLOOR:g})")

    for name, operator, target in FLOORS:
        failure = _floor_failure(name, operator, target, scores)
        if failure is None:
            evidence.append(f"{name} {scores[name]:g} (floor {operator} {target:g})")
        else:
            failures.append(failure)

    vuln_failures, accepted = adjudicate_vulnerabilities(report, waivers)
    failures.extend(vuln_failures)
    if not vuln_failures and not accepted:
        evidence.append(f"{ADJUDICATED} 10 (no advisories)")
    evidence.extend(accepted)
    return failures, evidence


def main(argv: list[str] | None = None) -> int:
    """Return nonzero when a floor is missed or a deduction is not waived."""

    parser = argparse.ArgumentParser(description="Enforce the OpenSSF Scorecard floors.")
    parser.add_argument("--report", type=Path, default=Path("results.json"))
    parser.add_argument("--waivers", type=Path, default=WAIVERS_PATH)
    parser.add_argument("--repo", default="outcome-receipts")
    parser.add_argument("--today", default=None)
    args = parser.parse_args(argv)

    try:
        today = date.fromisoformat(args.today) if args.today else date.today()
    except ValueError:
        print(f"--today is not an ISO date: {args.today}", file=sys.stderr)
        return 2
    if not args.waivers.exists():
        print(f"waiver registry not found: {args.waivers}", file=sys.stderr)
        return 1

    waivers, problems = live_waivers(args.waivers.read_text(encoding="utf-8"), args.repo, today)
    report, error = load_report(args.report)
    if report is None:
        problems.append(error)
        failures: list[str] = []
        evidence: list[str] = []
    else:
        failures, evidence = evaluate(report, waivers)

    for line in evidence:
        print(f"scorecard: {line}")
    if problems or failures:
        print("scorecard gate failed:", file=sys.stderr)
        for problem in problems + failures:
            print(f"- {problem}", file=sys.stderr)
        print(
            "\nFix the finding, or record a dated, narrowly scoped waiver in waivers.yml naming"
            "\nthe advisory, the package, the severity, an owner, and an expiry. Lowering a floor"
            "\nis a policy change and belongs in the standard, not in this gate.",
            file=sys.stderr,
        )
        return 1

    print("scorecard: every floor met")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
