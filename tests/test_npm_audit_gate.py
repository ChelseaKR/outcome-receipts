"""The npm-audit waiver is bounded to one advisory, and provably so.

waivers.yml WVR-007 accepts GHSA-jmr9-qjv8-65gv, an unpatched symlink
path-traversal issue in extract-zip that reaches this repository only as a
transitive development dependency of the accessibility toolchain. An exception
mechanism nobody has tested is worse than no exception at all, so these pin
what it will *not* accept: a different advisory, a second advisory in the same
package, the waived advisory on another package or at a higher severity, and an
expired or malformed waiver all still fail the gate.

The reports below are recorded `npm audit --json` shapes, so none of this needs
a network call or an installed node_modules tree.
"""

from __future__ import annotations

import json
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from scripts.check_npm_audit import live_waivers, main

ROOT = Path(__file__).resolve().parents[1]
WAIVERS = ROOT / "waivers.yml"
MAKEFILE = ROOT / "Makefile"

WAIVED_ADVISORY = "GHSA-jmr9-qjv8-65gv"
WAIVED_PACKAGE = "extract-zip"


def _advisory(
    advisory: str, package: str, severity: str = "high", source: int = 1139346
) -> dict[str, Any]:
    return {
        "source": source,
        "name": package,
        "dependency": package,
        "title": f"{package} test advisory",
        "url": f"https://github.com/advisories/{advisory}",
        "severity": severity,
        "range": "*",
    }


def _report(*advisories: dict[str, Any]) -> dict[str, Any]:
    """Build an `npm audit --json` report carrying the given advisories.

    Mirrors npm's real shape: the package carrying the advisory has an
    object-shaped `via`, and a downstream package just names its parent.
    """

    vulnerabilities: dict[str, Any] = {}
    counts = {"info": 0, "low": 0, "moderate": 0, "high": 0, "critical": 0}
    for via in advisories:
        package = str(via["name"])
        vulnerabilities[package] = {
            "name": package,
            "severity": via["severity"],
            "via": [via],
            "effects": [f"depends-on-{package}"],
            "range": "*",
            "nodes": [f"node_modules/{package}"],
        }
        vulnerabilities[f"depends-on-{package}"] = {
            "name": f"depends-on-{package}",
            "severity": via["severity"],
            "via": [package],
            "effects": [],
            "range": "*",
            "nodes": [f"node_modules/depends-on-{package}"],
        }
        counts[str(via["severity"])] += 2
    return {
        "auditReportVersion": 2,
        "vulnerabilities": vulnerabilities,
        "metadata": {"vulnerabilities": {**counts, "total": sum(counts.values())}},
    }


def _gate(tmp_path: Path, report: dict[str, Any], waivers: Path = WAIVERS) -> int:
    path = tmp_path / "audit.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    return main(["--report", str(path), "--waivers", str(waivers)])


def test_the_committed_waiver_accepts_the_advisory_it_names(tmp_path: Path) -> None:
    assert _gate(tmp_path, _report(_advisory(WAIVED_ADVISORY, WAIVED_PACKAGE))) == 0


def test_a_different_high_advisory_still_fails(tmp_path: Path) -> None:
    """The point of the whole exercise: the waiver is not an allowlist."""

    assert _gate(tmp_path, _report(_advisory("GHSA-aaaa-bbbb-cccc", "tar-fs"))) == 1


def test_a_different_advisory_alongside_the_waived_one_still_fails(tmp_path: Path) -> None:
    report = _report(
        _advisory(WAIVED_ADVISORY, WAIVED_PACKAGE),
        _advisory("GHSA-aaaa-bbbb-cccc", "tar-fs", source=222222),
    )
    assert _gate(tmp_path, report) == 1


def test_a_second_advisory_in_the_same_package_still_fails(tmp_path: Path) -> None:
    """Scoped to the advisory, not to extract-zip."""

    assert _gate(tmp_path, _report(_advisory("GHSA-dddd-eeee-ffff", WAIVED_PACKAGE))) == 1


def test_the_waived_advisory_on_another_package_still_fails(tmp_path: Path) -> None:
    assert _gate(tmp_path, _report(_advisory(WAIVED_ADVISORY, "some-other-package"))) == 1


def test_the_waived_advisory_escalated_to_critical_still_fails(tmp_path: Path) -> None:
    report = _report(_advisory(WAIVED_ADVISORY, WAIVED_PACKAGE, severity="critical"))
    assert _gate(tmp_path, report) == 1


def test_a_moderate_advisory_does_not_fail_the_high_floor(tmp_path: Path) -> None:
    report = _report(_advisory("GHSA-aaaa-bbbb-cccc", "tar-fs", severity="moderate"))
    assert _gate(tmp_path, report) == 0


def test_an_expired_waiver_accepts_nothing(tmp_path: Path) -> None:
    stale = tmp_path / "waivers.yml"
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    stale.write_text(
        WAIVERS.read_text(encoding="utf-8").replace("expires: 2026-11-15", f"expires: {yesterday}"),
        encoding="utf-8",
    )
    assert _gate(tmp_path, _report(_advisory(WAIVED_ADVISORY, WAIVED_PACKAGE)), stale) == 1


def test_a_waiver_missing_a_required_field_accepts_nothing(tmp_path: Path) -> None:
    broken = tmp_path / "waivers.yml"
    text = WAIVERS.read_text(encoding="utf-8")
    broken.write_text(text.replace("    advisory: GHSA-jmr9-qjv8-65gv\n", ""), encoding="utf-8")
    assert _gate(tmp_path, _report(_advisory(WAIVED_ADVISORY, WAIVED_PACKAGE)), broken) == 1


def test_an_empty_audit_report_fails_closed(tmp_path: Path) -> None:
    """An audit that produced no report is not an audit that passed."""

    empty = tmp_path / "audit.json"
    empty.write_text("", encoding="utf-8")
    assert main(["--report", str(empty), "--waivers", str(WAIVERS)]) == 1


def test_a_report_shape_the_gate_cannot_read_fails_closed(tmp_path: Path) -> None:
    report = _report(_advisory(WAIVED_ADVISORY, WAIVED_PACKAGE))
    report["vulnerabilities"] = {"opaque": {"severity": "high", "via": ["something"]}}
    assert _gate(tmp_path, report) == 1


def test_a_semgrep_waiver_cannot_accept_a_dependency_advisory(tmp_path: Path) -> None:
    """Waiver kinds are not interchangeable."""

    mislabelled = tmp_path / "waivers.yml"
    mislabelled.write_text(
        WAIVERS.read_text(encoding="utf-8").replace("    kind: npm-audit\n", "    kind: semgrep\n"),
        encoding="utf-8",
    )
    assert _gate(tmp_path, _report(_advisory(WAIVED_ADVISORY, WAIVED_PACKAGE)), mislabelled) == 1


def test_every_security_scanner_is_its_own_gate() -> None:
    """The defect this gate came from: six scanners in one recipe, four skipped.

    `make security` ran pip-audit, then npm audit, then osv-scanner, gitleaks,
    semgrep and zizmor as six lines of a single recipe. make stops a recipe at
    its first failing line, so an unfixable npm advisory on line two meant the
    last four never ran while the job reported red for a reason that had
    nothing to do with them.
    """

    text = MAKEFILE.read_text(encoding="utf-8")
    match = re.search(r"^SECURITY_GATES :=((?:[^\n\\]*\\\n)*[^\n]*)", text, re.MULTILINE)
    assert match is not None
    assert match.group(1).replace("\\\n", " ").split() == [
        "security-pip",
        "security-npm",
        "security-osv",
        "security-secrets",
        "security-semgrep",
        "security-workflows",
    ]
    # Each one is a target of its own, not a line inside another recipe.
    for gate in ("security-pip", "security-npm", "security-osv", "security-secrets"):
        assert re.search(rf"^{gate}:$", text, re.MULTILINE)


def test_the_committed_registry_is_well_formed() -> None:
    waivers, problems = live_waivers(
        WAIVERS.read_text(encoding="utf-8"), "outcome-receipts", date.today()
    )
    assert problems == []
    assert set(waivers) == {WAIVED_ADVISORY.upper()}
    waiver = waivers[WAIVED_ADVISORY.upper()]
    assert waiver["package"] == WAIVED_PACKAGE
    assert waiver["severity"] == "high"
    # The record has to carry the facts the acceptance rests on, not just an id.
    evidence = waiver["reason"] + waiver["version"] + waiver["dependency_path"]
    for claim in ("2.0.1", "pa11y", "2026-08-15", "devDependency"):
        assert claim in evidence
