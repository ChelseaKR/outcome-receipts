#!/usr/bin/env python3
"""Adjudicate `npm audit` findings against the committed waiver registry.

The Node dependency audit (SEC-12) is merge-blocking: any HIGH or CRITICAL
advisory in the accessibility toolchain fails it. `npm audit` cannot accept a
single reviewed advisory -- the only lever it offers is `--audit-level`, and
raising that hides every finding at that severity rather than the one that was
actually reviewed.

So the severity floor stays where it is and this gate adjudicates advisory by
advisory against waivers.yml, the registry scripts/check_waivers.py already
validates for schema and expiry. An advisory passes only when a live waiver
names that exact advisory id, that exact package, and that exact severity.
Everything else fails: a new advisory, a second advisory in the same package,
the waived advisory on a different package or escalated in severity, an expired
or malformed waiver, or a report this gate cannot parse.

Reads the report from stdin (`npm audit --json | ... check_npm_audit.py`) or
from `--report`, and never runs npm itself, so the merge gate and
tests/test_npm_audit_gate.py exercise exactly the same code path.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
WAIVERS_PATH = ROOT / "waivers.yml"

#: The `npm audit --audit-level=high` floor this gate replaces, unchanged.
BLOCKING = frozenset({"high", "critical"})

#: Only this waiver kind can accept a dependency advisory, so a semgrep waiver
#: can never accidentally cover one.
KIND = "npm-audit"

REQUIRED_FIELDS = (
    "id",
    "control",
    "repo",
    "kind",
    "reason",
    "owner",
    "granted",
    "expires",
    "advisory",
    "package",
    "severity",
)

# `  - key: value` opens a waiver, `    key: value` adds a field, anything
# indented further continues the field above it -- so folded prose inside
# `reason:` is never mistaken for a field, whatever it says.
_ENTRY_RE = re.compile(r"^  - ([a-z_]+):[ \t]*(.*)$")
_FIELD_RE = re.compile(r"^    ([a-z_]+):[ \t]*(.*)$")
_FOLD_RE = re.compile(r"^ {6,}(\S.*)$")
_BLOCK_INDICATORS = frozenset({">", ">-", ">+", "|", "|-", "|+"})
_ADVISORY_RE = re.compile(r"(GHSA-[0-9a-z]{4}-[0-9a-z]{4}-[0-9a-z]{4})", re.IGNORECASE)


def parse_waivers(text: str) -> list[dict[str, str]]:
    """Return every waiver entry in the registry as a field mapping."""

    waivers: list[dict[str, str]] = []
    field_name = ""
    for line in text.splitlines():
        entry = _ENTRY_RE.match(line)
        field = entry or _FIELD_RE.match(line)
        if field is not None:
            if entry is not None:
                waivers.append({})
            field_name = field.group(1)
            value = field.group(2).strip()
            waivers[-1][field_name] = "" if value in _BLOCK_INDICATORS else value
            continue
        folded = _FOLD_RE.match(line)
        if folded is not None and waivers and field_name:
            existing = waivers[-1].get(field_name, "")
            waivers[-1][field_name] = f"{existing} {folded.group(1).strip()}".strip()
            continue
        if line.strip():
            field_name = ""
    return waivers


def _parse_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def live_waivers(text: str, repo: str, today: date) -> tuple[dict[str, dict[str, str]], list[str]]:
    """Return usable npm-audit waivers by advisory id, plus every problem found.

    An invalid or expired waiver is not returned, so it accepts nothing: this
    gate fails closed on a rotten registry rather than passing on one.
    """

    problems: list[str] = []
    usable: dict[str, dict[str, str]] = {}
    for waiver in parse_waivers(text):
        if waiver.get("kind") != KIND:
            continue
        waiver_id = waiver.get("id") or "<missing id>"
        missing = [field for field in REQUIRED_FIELDS if not waiver.get(field)]
        if missing:
            problems.append(f"{waiver_id}: missing required field(s): {', '.join(missing)}")
            continue
        if waiver["repo"] != repo:
            problems.append(f"{waiver_id}: repo is {waiver['repo']}, not {repo}")
            continue
        granted = _parse_date(waiver["granted"])
        expires = _parse_date(waiver["expires"])
        if granted is None or expires is None:
            problems.append(f"{waiver_id}: granted and expires must be ISO dates")
            continue
        if expires < granted:
            problems.append(f"{waiver_id}: expiry precedes granted date")
            continue
        if expires < today:
            problems.append(f"{waiver_id}: expired on {waiver['expires']}; re-review it")
            continue
        if waiver["severity"] not in BLOCKING:
            problems.append(
                f"{waiver_id}: severity {waiver['severity']!r} is not one this gate blocks on"
            )
            continue
        advisory = waiver["advisory"].upper()
        if advisory in usable:
            problems.append(f"{waiver_id}: duplicate waiver for {advisory}")
            continue
        usable[advisory] = waiver
    return usable, problems


def advisory_id(via: dict[str, Any]) -> str:
    """Return the GHSA id an npm advisory object carries, or its numeric source."""

    match = _ADVISORY_RE.search(str(via.get("url", "")))
    if match is not None:
        return match.group(1).upper()
    return f"npm-source-{via.get('source', 'unknown')}"


def report_advisories(report: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the distinct advisories an `npm audit --json` report names.

    npm lists one entry per affected package. The packages carrying the
    advisory have object-shaped `via` entries; everything downstream just names
    the package it inherited the problem from, so adjudicating the advisory
    objects covers the whole propagated set.
    """

    seen: dict[tuple[str, str, str], dict[str, Any]] = {}
    vulnerabilities = report.get("vulnerabilities")
    if not isinstance(vulnerabilities, dict):
        return []
    for entry in vulnerabilities.values():
        if not isinstance(entry, dict):
            continue
        for via in entry.get("via", []):
            if not isinstance(via, dict):
                continue
            key = (advisory_id(via), str(via.get("name", "")), str(via.get("severity", "")).lower())
            seen.setdefault(key, via)
    return [
        {"id": key[0], "package": key[1], "severity": key[2], "via": via}
        for key, via in seen.items()
    ]


def blocking_total(report: dict[str, Any]) -> int:
    """Return the HIGH + CRITICAL count npm itself reports."""

    metadata = report.get("metadata")
    counts = metadata.get("vulnerabilities") if isinstance(metadata, dict) else None
    if not isinstance(counts, dict):
        return 0
    total = 0
    for severity in sorted(BLOCKING):
        try:
            total += int(counts.get(severity, 0))
        except (TypeError, ValueError):
            return 0
    return total


def adjudicate(
    report: dict[str, Any], waivers: dict[str, dict[str, str]]
) -> tuple[list[str], list[str]]:
    """Return (failures, accepted) for one npm audit report."""

    failures: list[str] = []
    accepted: list[str] = []
    blocking = [item for item in report_advisories(report) if item["severity"] in BLOCKING]

    if blocking_total(report) > 0 and not blocking:
        failures.append(
            "npm reports HIGH/CRITICAL findings but no advisory objects could be read from the "
            "report; refusing to pass a report this gate does not understand"
        )

    for item in blocking:
        waiver = waivers.get(str(item["id"]))
        if waiver is None:
            title = item["via"].get("title", "no title")
            failures.append(
                f"{item['id']} ({item['severity']}) in {item['package']}: no waiver. {title}"
            )
            continue
        if waiver["package"] != item["package"]:
            failures.append(
                f"{item['id']}: waiver {waiver['id']} covers {waiver['package']}, but the "
                f"advisory is reported against {item['package']}"
            )
            continue
        if waiver["severity"] != item["severity"]:
            failures.append(
                f"{item['id']}: waiver {waiver['id']} accepts severity {waiver['severity']}, "
                f"but npm now reports {item['severity']}"
            )
            continue
        accepted.append(
            f"{item['id']} ({item['severity']}) in {item['package']}: accepted by "
            f"{waiver['id']}, expires {waiver['expires']}"
        )
    return failures, accepted


def load_report(path: Path | None) -> tuple[dict[str, Any] | None, str]:
    """Return the parsed npm audit report, or the reason it cannot be used."""

    raw = path.read_text(encoding="utf-8") if path is not None else sys.stdin.read()
    source = str(path) if path is not None else "stdin"
    if not raw.strip():
        return None, f"no npm audit report on {source}; the audit did not run"
    try:
        report = json.loads(raw)
    except json.JSONDecodeError:
        return None, f"the npm audit report on {source} is not JSON:\n{raw[:2000]}"
    if not isinstance(report, dict) or "vulnerabilities" not in report:
        return None, f"the npm audit report on {source} carries no vulnerability section"
    if report.get("error"):
        return None, f"npm audit reported an error: {report['error']}"
    return report, ""


def main(argv: list[str] | None = None) -> int:
    """Return nonzero when an unwaived HIGH/CRITICAL advisory is present."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=None)
    parser.add_argument("--waivers", type=Path, default=WAIVERS_PATH)
    parser.add_argument("--repo", default="outcome-receipts")
    parser.add_argument("--today", default=None)
    args = parser.parse_args(argv)

    today = _parse_date(args.today) if args.today else date.today()
    if today is None:
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
        accepted: list[str] = []
    else:
        failures, accepted = adjudicate(report, waivers)

    for line in accepted:
        print(f"npm audit: {line}")
    if problems or failures:
        print("npm audit gate failed:", file=sys.stderr)
        for problem in problems + failures:
            print(f"- {problem}", file=sys.stderr)
        print(
            "\nA HIGH or CRITICAL advisory blocks merge. Fix it, or record a dated, narrowly"
            "\nscoped waiver in waivers.yml naming the advisory, the package, the severity, an"
            "\nowner, and an expiry.",
            file=sys.stderr,
        )
        return 1

    print(f"npm audit: no unwaived HIGH/CRITICAL advisories ({len(accepted)} waived)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
