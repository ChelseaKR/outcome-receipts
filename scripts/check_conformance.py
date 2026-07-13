"""Check repository-local portfolio conformance declarations and artifacts."""

from __future__ import annotations

import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STANDARDS = {
    "Responsible-Tech Framework",
    "Code Quality",
    "Security & Supply-Chain",
    "CI/CD",
    "Release & Versioning",
    "Observability",
    "Accessibility",
    "Internationalization",
    "AI Evaluation",
    "Documentation",
    "Quality & Metrics",
    "Incident Response",
    "Data Governance",
}
REQUIRED = (
    "CHANGELOG.md",
    "CITATION.cff",
    "CONTRIBUTING.md",
    "DEFINITION_OF_DONE.md",
    "LICENSE",
    "SECURITY.md",
    ".standards-version",
    "waivers.yml",
    "docs/adr/0000-record-architecture-decisions.md",
    "docs/RESPONSIBLE-TECH-AUDITS.md",
    "docs/OPERATIONS.md",
    "docs/THREAT-MODEL.md",
    "docs/a11y/ACR.md",
    "docs/a11y/STATEMENT.md",
    "docs/audits/ai-risk-register.md",
    "docs/audits/ai-impact-assessment-drafting.md",
    "docs/audits/iso42001-soa.md",
    "docs/audits/residual-risk-register.md",
    "docs/cards/model-card.md",
    "docs/cards/data-card-reporting.md",
    "docs/data/organization-service-export.md",
    "docs/data/synthetic-fixtures.md",
    "docs/incidents/README.md",
)


def _readme_rows(text: str) -> dict[str, str]:
    rows: dict[str, str] = {}
    for name, state in re.findall(r"^\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|$", text, re.MULTILINE):
        rows[name.strip()] = state.strip()
    return rows


def _link_failures() -> list[str]:
    failures: list[str] = []
    link = re.compile(r"\[[^]]+\]\(([^)]+)\)")
    for path in sorted((*ROOT.glob("*.md"), *ROOT.joinpath("docs").rglob("*.md"))):
        for target in link.findall(path.read_text(encoding="utf-8")):
            clean = target.strip().strip("<>").split("#", 1)[0]
            if not clean or re.match(r"(?:https?|mailto):", clean):
                continue
            if not (path.parent / clean).resolve().exists():
                failures.append(f"broken link: {path.relative_to(ROOT)} -> {target}")
    return failures


def _card_failures() -> list[str]:
    model = (ROOT / "docs/cards/model-card.md").read_text(encoding="utf-8")
    data = (ROOT / "docs/cards/data-card-reporting.md").read_text(encoding="utf-8")
    failures = []
    for key in (
        "language:",
        "license:",
        "base_model:",
        "pipeline_tag:",
        "library_name:",
        "model-index:",
    ):
        if key not in model:
            failures.append(f"model card missing {key}")
    for heading in (
        "Motivation",
        "Composition",
        "Collection",
        "Preprocessing",
        "Uses",
        "Distribution",
        "Maintenance",
    ):
        if f"## {heading}" not in data:
            failures.append(f"data card missing {heading}")
    return failures


def _waiver_date(
    fields: dict[str, str], field: str, label: str, waiver_id: str, failures: list[str]
) -> date | None:
    try:
        return date.fromisoformat(fields.get(field, ""))
    except ValueError:
        failures.append(f"{waiver_id}: invalid {label}")
        return None


def waiver_failures(path: Path) -> list[str]:
    """Return schema and expiry failures from a repository waiver registry."""

    text = path.read_text(encoding="utf-8")
    failures: list[str] = []
    if not re.search(r"^version:\s*1\s*$", text, re.MULTILINE):
        failures.append("waiver registry must declare version: 1")
    if not re.search(r"^waivers:\s*(?:\[\])?\s*$", text, re.MULTILINE):
        failures.append("waiver registry must declare waivers")

    blocks = re.split(r"(?=^  - )", text, flags=re.MULTILINE)[1:]
    seen: set[str] = set()
    required = ("id", "control", "repo", "kind", "reason", "owner", "granted", "expires")
    for block in blocks:
        fields = dict(re.findall(r"^\s+(?:- )?([a-z_]+):\s*([^\n]*)", block, re.MULTILINE))
        waiver_id = fields.get("id", "<missing>").strip()
        if waiver_id in seen:
            failures.append(f"duplicate waiver id: {waiver_id}")
        seen.add(waiver_id)
        for field in required:
            if not fields.get(field, "").strip():
                failures.append(f"{waiver_id}: missing {field}")
        granted = _waiver_date(fields, "granted", "granted date", waiver_id, failures)
        expires = _waiver_date(fields, "expires", "expiry", waiver_id, failures)
        if expires is not None and expires < date.today():
            failures.append(f"{waiver_id}: expired")
        if granted is not None and expires is not None and expires < granted:
            failures.append(f"{waiver_id}: expiry precedes granted date")
    return failures


def main() -> int:
    """Return nonzero when a required declaration or artifact is missing."""

    failures = [path for path in REQUIRED if not (ROOT / path).exists()]
    version = (
        (ROOT / ".standards-version").read_text(encoding="utf-8").strip()
        if (ROOT / ".standards-version").exists()
        else ""
    )
    if not re.fullmatch(r"v\d+\.\d+\.\d+", version):
        failures.append(".standards-version must contain a SemVer tag")

    rows = _readme_rows((ROOT / "README.md").read_text(encoding="utf-8"))
    for standard in sorted(STANDARDS):
        state = rows.get(standard, "")
        if not state:
            failures.append(f"README conformance row missing: {standard}")
        elif state == "N/A" or "Open:" in state or "gap tracked" in state:
            failures.append(f"README conformance row is not closed: {standard}: {state}")

    failures.extend(_link_failures())
    failures.extend(_card_failures())
    failures.extend(waiver_failures(ROOT / "waivers.yml"))

    if failures:
        print("repository conformance failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print("repository declarations: pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
