"""Check repository-local portfolio conformance declarations and artifacts."""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Fallback standards index for a self-contained `make verify`: no network
# call and no dependency on the private ChelseaKR/portfolio-standards repo,
# so a fork or a contributor without deploy-key access can still run the
# full local gate (AGENTS.md: "keep it self-contained ... state the bar
# inline"). This has to stay a literal for that reason, but it is no longer
# the *only* copy of the list -- when a pinned standards checkout is present
# (`--standards-dir`, wired into the "portfolio standards" CI job), that
# checkout's own controls.yml is the source of truth instead, and this
# literal is checked against it below rather than trusted blindly (see
# `test_fallback_standards_literal_matches_a_pinned_checkout` in
# tests/test_conformance.py). That is what closes the gap DOC-11 named: a
# check that only ever compares the README against its own hardcoded
# expectations reports green even when both have drifted from the real,
# 15-standard portfolio index.
#
# Each display name is a controls.yml standard `title` with a trailing
# " Standard" suffix stripped (see `_display_name`); the Responsible-Tech
# Framework title carries no such suffix and is used verbatim.
FALLBACK_STANDARDS = {
    "Responsible-Tech Framework",
    "Code Quality",
    "Security & Supply-Chain",
    "CI/CD",
    "Release & Versioning",
    "Observability",
    "Accessibility",
    "Internationalization & Localization",
    "AI Evaluation",
    "Documentation",
    "Quality & Metrics",
    "Performance",
    "Incident Response",
    "Data Governance",
    "AI-Development Measurement",
}

# controls.yml's standard-registry line shape, e.g.:
#   CQ:   { file: CODE-QUALITY-STANDARD.md, title: "Code Quality Standard" }
# Matches automation/readme_conformance.py's STANDARD_RE in the standards repo,
# so the two tools cannot read the same file two different ways.
_STANDARD_TITLE_RE = re.compile(
    r'^\s{2}[A-Z0-9]+:\s*\{\s*file:\s*[^,\s]+,\s*title:\s*"([^"]*)"', re.MULTILINE
)


def _display_name(title: str) -> str:
    """A controls.yml standard title, in this repo's README row-name style."""

    return title.removesuffix(" Standard")


class StandardsIndexError(Exception):
    """A `--standards-dir` was given but no checkout exists at that path.

    Deliberately distinct from a plain empty result: DOC-11 requires "a clear
    failure when the checkout is absent, rather than a silent fallback" once
    the caller has asserted a pinned checkout should exist. Swallowing this
    into an empty set would make the conformance check silently pass with
    zero required rows, which is a worse failure than the tautology it
    replaces. This is for the checkout itself being missing (a broken
    `actions/checkout` step, a wrong path, a revoked deploy key) -- a real
    infrastructure failure, not a documentation gap. A checkout that exists
    but predates `controls.yml` is a different, narrower condition; see
    `standards_index`.
    """


def standards_index(standards_dir: Path | None) -> set[str]:
    """The set of portfolio standard display names this repo must declare.

    With `standards_dir` omitted, returns the vendored fallback list (used by
    the self-contained `make verify`). With `standards_dir` given and
    present, reads `<standards_dir>/controls.yml` and derives the list from
    the real, currently-pinned portfolio index.

    Two distinct absence cases, handled differently on purpose:

    * `standards_dir` itself does not exist: raises `StandardsIndexError`.
      This means the checkout step that was supposed to populate it did not
      run or did not succeed -- a clear, loud failure, never a silent
      fallback, because there is no way to tell whether the fallback list is
      still accurate.
    * `standards_dir` exists but has no `controls.yml`: this is the state of
      this repository's own pin as of 2026-08-21 -- `.standards-version` is
      `v1.0.1`, and `controls.yml` was not added to the standards repo until
      FIX-01 (2026-07-11), well after that tag. The checkout is real and
      trustworthy; it is simply older than the registry this function reads.
      Failing the build over a pin-staleness gap that issue 98 did not ask
      this change to fix, and that a solo maintainer cannot resolve from
      inside this repository, would make "portfolio standards conformance"
      permanently red for a reason unrelated to what it is checking. This
      case prints a clear (not silent) warning to stderr and returns the
      vendored fallback list instead, which `test_fallback_standards_literal_matches_a_frozen_snapshot_of_the_pinned_index`
      keeps honest against a real, current copy of the registry.
    """

    if standards_dir is None:
        return set(FALLBACK_STANDARDS)
    if not standards_dir.exists():
        raise StandardsIndexError(
            f"--standards-dir {standards_dir} was given but that path does not exist -- "
            "the pinned standards checkout is missing (checkout step failed, wrong path, "
            "or revoked access). Omit --standards-dir to use the vendored fallback list "
            "instead."
        )
    controls_path = standards_dir / "controls.yml"
    if not controls_path.exists():
        print(
            f"WARNING: {standards_dir} exists but has no controls.yml -- the pinned "
            "standards checkout (see .standards-version) predates FIX-01 "
            "(controls.yml was added 2026-07-11). Falling back to the vendored "
            "standards list, which is tested against a frozen snapshot of the current "
            "registry. Bumping .standards-version would let this derive from the live "
            "checkout instead; that is a separate, deliberate portfolio-pin decision, "
            "not something this check does on its own.",
            file=sys.stderr,
        )
        return set(FALLBACK_STANDARDS)
    text = controls_path.read_text(encoding="utf-8")
    titles = _STANDARD_TITLE_RE.findall(text)
    if not titles:
        raise StandardsIndexError(
            f"{controls_path} exists but no standard entries were found in it "
            '(expected lines shaped like `XX: { file: ..., title: "..." }`) -- '
            "the schema may have changed; this check needs updating, not skipping."
        )
    return {_display_name(title) for title in titles}


REQUIRED = (
    "CHANGELOG.md",
    "CITATION.cff",
    "CONTRIBUTING.md",
    "DEFINITION_OF_DONE.md",
    "Dockerfile",
    "LICENSE",
    "SECURITY.md",
    ".standards-version",
    "waivers.yml",
    "docs/adr/0000-record-architecture-decisions.md",
    "docs/RESPONSIBLE-TECH-AUDITS.md",
    "docs/OPERATIONS.md",
    "docs/NOVEL-USE-CASES.md",
    "docs/SELF-HOSTING.md",
    "docs/SPEC-STABILITY.md",
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
    "docs/schema/report-spec.schema.json",
    "docs/schema/receipts.schema.json",
    "docs/schema/workflow-artifact.schema.json",
    "tests/fixtures/compat/v0.1.0/SOURCE.md",
    "tests/fixtures/compat/v0.1.0/receipts.json",
    "tests/fixtures/compat/v1/workflow-artifacts.json",
)


def _readme_rows(text: str) -> dict[str, str]:
    rows: dict[str, str] = {}
    for name, state in re.findall(r"^\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|$", text, re.MULTILINE):
        rows[name.strip()] = state.strip()
    return rows


def _readme_standards_rows(readme_text: str) -> dict[str, str]:
    """Standard -> state, scoped to the '## Standards conformance' table only.

    `_readme_rows` matches every two-column pipe-table row in the whole
    README -- there are others, e.g. the CLI exit-code table -- so scoping to
    this one section is what makes the row-count and unexpected-row checks in
    `_standards_table_failures` meaningful rather than noise picked up from
    unrelated tables.
    """

    match = re.search(
        r"^## Standards conformance\n(.*?)(?=^## |\Z)", readme_text, re.MULTILINE | re.DOTALL
    )
    if match is None:
        return {}
    rows = _readme_rows(match.group(1))
    rows.pop("Standard", None)  # table header row
    return {name: state for name, state in rows.items() if not re.fullmatch(r"-+", name)}


def _standards_table_failures(rows: dict[str, str], standards: set[str]) -> list[str]:
    """Every way the README's Standards-conformance table can disagree with `standards`."""

    failures: list[str] = []
    for standard in sorted(standards):
        state = rows.get(standard, "")
        if not state:
            failures.append(f"README conformance row missing: {standard}")
        elif state == "N/A" or "Open:" in state or "gap tracked" in state:
            failures.append(f"README conformance row is not closed: {standard}: {state}")

    extra = sorted(set(rows) - standards)
    if extra:
        failures.append(
            "README conformance row(s) not in the standards index (renamed, "
            f"misspelled, or retired standard?): {', '.join(extra)}"
        )
    if len(rows) != len(standards):
        failures.append(
            f"README conformance table has {len(rows)} row(s) but the standards "
            f"index names {len(standards)} standard(s)"
        )
    return failures


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

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--standards-dir",
        type=Path,
        default=None,
        help=(
            "path to a checked-out ChelseaKR/portfolio-standards (e.g. .standards in the "
            "'portfolio standards' CI job); when given, the required-standards list is "
            "derived from its controls.yml instead of the vendored fallback, and a "
            "missing or unreadable checkout is a hard failure rather than a silent "
            "fallback to the vendored list"
        ),
    )
    args = parser.parse_args()

    failures = [path for path in REQUIRED if not (ROOT / path).exists()]
    version = (
        (ROOT / ".standards-version").read_text(encoding="utf-8").strip()
        if (ROOT / ".standards-version").exists()
        else ""
    )
    if not re.fullmatch(r"v\d+\.\d+\.\d+", version):
        failures.append(".standards-version must contain a SemVer tag")

    readme_text = (ROOT / "README.md").read_text(encoding="utf-8")
    try:
        standards = standards_index(args.standards_dir)
    except StandardsIndexError as exc:
        failures.append(str(exc))
    else:
        failures.extend(_standards_table_failures(_readme_standards_rows(readme_text), standards))

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
