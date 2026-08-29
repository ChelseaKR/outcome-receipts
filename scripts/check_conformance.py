"""Check repository-local portfolio conformance declarations and artifacts."""

from __future__ import annotations

import argparse
import json
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


#: Mirrors automation/check_staleness.py's LAST_VERIFIED_RE/CADENCE_RE exactly
#: (accepting both the plain footer and `**Bold:**`-emphasized labels), so a
#: doc using either label reads the same way in the portfolio parser and here.
LAST_VERIFIED_RE = re.compile(r"Last verified:\s*\*{0,2}\s*(\d{4}-\d{2}-\d{2})")
CADENCE_RE = re.compile(r"Recheck cadence:\s*\*{0,2}\s*(.+)")

#: Mirrors automation/check_staleness.py's CADENCE_DAYS keyword -> max-age
#: mapping exactly, so a cadence sentence means the same number of days in
#: both places.
CADENCE_DAYS = (
    (re.compile(r"\bmonthly\b", re.IGNORECASE), 31),
    (re.compile(r"\bquarter", re.IGNORECASE), 92),
    (re.compile(r"\bsemi-?annual", re.IGNORECASE), 183),
    (re.compile(r"\bannual|\byearly\b", re.IGNORECASE), 365),
)


def _cadence_to_days(cadence: str) -> int | None:
    """The strictest recognized interval named in a cadence sentence, or None.

    Unlike the portfolio parser's `cadence_to_days` (which defaults an
    unrecognized cadence to 180 days), this returns None when nothing
    matches, so the caller can fail closed instead of silently granting a
    six-month grace period to a sentence nothing has actually parsed.
    """

    best: int | None = None
    for pattern, days in CADENCE_DAYS:
        if pattern.search(cadence):
            best = days if best is None else min(best, days)
    return best


def doc_staleness_failures(root: Path, today: date) -> list[str]:
    """Every root-level or docs/ Markdown file whose currency stamp is stale,
    unreadable, or missing a cadence -- issue 93/DOC-15.

    Nothing checked this repository's own `Last verified:` stamps before:
    `automation/check_staleness.py` only globs `*-STANDARD.md`/`*-FRAMEWORK.md`
    inside the vendored `.standards` checkout, never this repository's own
    docs. All fourteen of this repository's stamps also used a `Recheck:`
    label the portfolio parser's `CADENCE_RE` cannot match (it requires the
    literal `Recheck cadence:`), so every one of them silently fell through
    to that 180-day default even in tooling that did look -- which never
    happened to be this repository's own gates, only the portfolio-wide
    parser if it were ever pointed here.

    Scoped to `_stamped_markdown_files`: root `*.md`, everything under `docs/`,
    and the other directories in this repository that carry authored prose with
    a currency stamp. Not every Markdown file in the tree -- `node_modules` and
    `.venv` carry vendored READMEs this check has no business grading.

    `perf/README.md` is why this is a wider set than `_link_failures` walks. It
    shipped a `Last verified:` line and a `Recheck cadence:` line that no gate
    read, so the stamp was decorative: it could go years stale and stay green.
    A stamp nothing reads is a claim nothing checks.
    """

    failures: list[str] = []
    for path in _stamped_markdown_files(root):
        text = path.read_text(encoding="utf-8")
        verified_match = LAST_VERIFIED_RE.search(text)
        if verified_match is None:
            continue
        rel = path.relative_to(root)
        cadence_match = CADENCE_RE.search(text)
        if cadence_match is None:
            failures.append(f"{rel}: has 'Last verified:' but no 'Recheck cadence:' line")
            continue
        cadence_text = cadence_match.group(1).strip()
        max_days = _cadence_to_days(cadence_text)
        if max_days is None:
            failures.append(
                f"{rel}: 'Recheck cadence: {cadence_text}' names no recognized interval "
                "(monthly/quarterly/semi-annual/annual) -- add one so staleness is "
                "mechanically checkable instead of unverifiable prose"
            )
            continue
        verified = date.fromisoformat(verified_match.group(1))
        age = (today - verified).days
        if age > max_days:
            failures.append(
                f"{rel}: stale -- last verified {verified.isoformat()} ({age}d ago), "
                f"cadence allows {max_days}d"
            )
    return failures


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
    "perf/baseline.json",
    "perf/README.md",
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


def _repo_markdown_files(root: Path) -> list[Path]:
    """Root-level `*.md` plus everything under `docs/` -- this repo's own docs,
    not vendored trees like `node_modules` or `.venv`."""

    return sorted((*root.glob("*.md"), *root.joinpath("docs").rglob("*.md")))


# Directories beyond root and `docs/` that hold this repository's own authored
# prose. A currency stamp in one of them is a claim, and this is the list that
# makes it a checked one.
_STAMPED_DIRS = ("perf",)


def _stamped_markdown_files(root: Path) -> list[Path]:
    """`_repo_markdown_files` plus the other directories carrying authored prose."""

    extra: list[Path] = []
    for name in _STAMPED_DIRS:
        extra.extend(root.joinpath(name).rglob("*.md"))
    return sorted({*_repo_markdown_files(root), *extra})


def _link_failures() -> list[str]:
    failures: list[str] = []
    link = re.compile(r"\[[^]]+\]\(([^)]+)\)")
    for path in _repo_markdown_files(ROOT):
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


#: The portfolio waiver schema's allowed `kind` values (WAIVERS-SCHEMA.md),
#: mirrored from the portfolio-wide lint's VALID_KINDS so the two cannot
#: silently diverge on what a waiver is allowed to claim to be.
VALID_KINDS = ("semgrep", "vex", "pa11y", "na-in-flight", "other")

#: WAIVERS-SCHEMA.md's waiver-id shape.
WAIVER_ID_RE = re.compile(r"^WVR-\d{3,}$")

#: Fallback control-id format check when no controls.yml is available to
#: validate membership against -- mirrors the portfolio lint's own fallback.
CONTROL_ID_RE = re.compile(r"^[A-Z][A-Z0-9]{1,5}-\d{1,3}$")


_BLOCK_SCALAR_INDICATORS = (">-", ">", "|", "|-")


def _fold_scalars(lines: list[str]) -> list[tuple[int, str]]:
    """Collapse `>-`/`>`/`|`/`|-` block scalars into single logical lines.

    Returns `(indent, "key: value")` pairs for every non-blank logical line
    in `lines`, with a folded scalar's continuation lines already joined
    into the one line that opened it. Isolating this from
    `_parse_waiver_entries` keeps each function's branching simple enough to
    read at a glance (and under the repository's complexity floor).
    """

    out: list[tuple[int, str]] = []
    index = 0
    while index < len(lines):
        raw = lines[index]
        stripped = raw.strip()
        if not stripped:
            index += 1
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        key, sep, value = stripped.partition(":")
        value = value.strip()
        index += 1
        if not (sep and value in _BLOCK_SCALAR_INDICATORS):
            out.append((indent, stripped))
            continue
        body_indent = indent + 1
        parts: list[str] = []
        while index < len(lines) and lines[index].strip():
            line_indent = len(lines[index]) - len(lines[index].lstrip(" "))
            if line_indent < body_indent:
                break
            parts.append(lines[index].strip())
            index += 1
        out.append((indent, f"{key.strip()}: {' '.join(parts)}"))
    return out


def _parse_waiver_entries(text: str) -> list[dict[str, str]]:
    """Parse the `waivers:` sequence, folded (`>-`) reason scalars included.

    A small, purpose-built parser for exactly the shape WAIVERS-SCHEMA.md
    documents (a top-level `waivers:` sequence of two-space-indented
    `- key: value` mappings, where a value may be a folded block scalar),
    not a general YAML parser. The previous implementation read each field
    with a single-line regex, which captured a folded scalar's own `>-`
    indicator as if it were the field's literal value -- so `reason: >-`
    registered as the non-empty string `">-"`, and the schema's "missing or
    empty reason" rule was unenforceable against every entry in this
    repository's own registry, all of which fold their `reason`. This
    mirrors the block-aware parser in the portfolio's own
    `automation/check_waivers.py`, so the two cannot read the same file two
    different ways.
    """

    entries: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    in_waivers = False

    for indent, line in _fold_scalars(text.splitlines()):
        if indent == 0:
            in_waivers = line == "waivers:"
            current = None
            continue
        if not in_waivers:
            continue
        if line.startswith("- "):
            current = {}
            entries.append(current)
            line = line[2:].strip()
        if current is None:
            continue
        key, sep, value = line.partition(":")
        if sep:
            current[key.strip()] = value.strip()

    return entries


def _entry_failures(
    fields: dict[str, str], control_ids: set[str] | None, seen: set[str]
) -> list[str]:
    """Every schema, format, and expiry failure for one parsed waiver entry."""

    failures: list[str] = []
    waiver_id = fields.get("id", "<missing>").strip()
    if waiver_id in seen:
        failures.append(f"duplicate waiver id: {waiver_id}")
    seen.add(waiver_id)

    for field in ("id", "control", "repo", "kind", "reason", "owner", "granted", "expires"):
        if not fields.get(field, "").strip():
            failures.append(f"{waiver_id}: missing {field}")

    if waiver_id not in ("", "<missing>") and not WAIVER_ID_RE.match(waiver_id):
        failures.append(f"{waiver_id}: id does not match WVR-NNN")

    kind = fields.get("kind", "").strip()
    if kind and kind not in VALID_KINDS:
        failures.append(
            f"{waiver_id}: unknown kind {kind!r} (must be one of {', '.join(VALID_KINDS)})"
        )

    failures.extend(_control_id_failures(waiver_id, fields.get("control", "").strip(), control_ids))

    granted = _waiver_date(fields, "granted", "granted date", waiver_id, failures)
    expires = _waiver_date(fields, "expires", "expiry", waiver_id, failures)
    if expires is not None and expires < date.today():
        failures.append(f"{waiver_id}: expired")
    if granted is not None and expires is not None and expires < granted:
        failures.append(f"{waiver_id}: expiry precedes granted date")
    return failures


def _control_id_failures(waiver_id: str, control: str, control_ids: set[str] | None) -> list[str]:
    if not control:
        return []
    if control_ids is not None:
        if control not in control_ids:
            return [f"{waiver_id}: unknown control ID {control!r} (not in controls.yml)"]
        return []
    if not CONTROL_ID_RE.match(control):
        return [f"{waiver_id}: control {control!r} is not a valid PREFIX-NN control ID"]
    return []


def waiver_failures(path: Path, control_ids: set[str] | None = None) -> list[str]:
    """Return schema and expiry failures from a repository waiver registry.

    `control_ids`, when given, is the set of valid control IDs from a pinned
    `controls.yml`; an entry's `control` must be a member. When omitted (no
    pinned checkout available), a control ID is only format-checked against
    `CONTROL_ID_RE`, matching the portfolio lint's own controls.yml-absent
    fallback.
    """

    text = path.read_text(encoding="utf-8")
    failures: list[str] = []
    if not re.search(r"^version:\s*1\s*$", text, re.MULTILINE):
        failures.append("waiver registry must declare version: 1")
    if not re.search(r"^waivers:\s*(?:\[\])?\s*$", text, re.MULTILINE):
        failures.append("waiver registry must declare waivers")

    seen: set[str] = set()
    for fields in _parse_waiver_entries(text):
        failures.extend(_entry_failures(fields, control_ids, seen))
    return failures


def _load_control_ids(standards_dir: Path) -> set[str] | None:
    """Control IDs from a pinned checkout's controls.yml, or None if unavailable.

    Mirrors `standards_index`'s own non-fatal handling of a checkout that
    predates `controls.yml` (issue 98/DOC-11): a missing file here degrades
    waiver control-ID checking to the format-only fallback rather than
    failing the whole conformance run over the same pin-staleness gap.
    """

    controls_path = standards_dir / "controls.yml"
    if not standards_dir.exists() or not controls_path.exists():
        return None
    text = controls_path.read_text(encoding="utf-8")
    ids = set(re.findall(r"id:\s*([A-Z][A-Z0-9]{1,5}-\d{1,3})\s*,", text))
    return ids or None


#: Waiver kinds that can accept a dependency-advisory exception (issue 96).
#: `npm-audit` is this repository's own local mechanism (scripts/check_npm_audit.py);
#: `vex` is the portfolio schema's registered kind for the same purpose. Both
#: are dependency-advisory kinds for the purpose of the §F cross-check below,
#: regardless of which one the portfolio-wide kind question eventually settles on.
DEPENDENCY_ADVISORY_KINDS = ("npm-audit", "vex")


def _section(text: str, heading: str) -> str:
    """The body of a `## <heading>` Markdown section, up to the next `## `."""

    match = re.search(re.escape(heading) + r"\n(.*?)(?=\n## |\Z)", text, re.DOTALL)
    return match.group(1) if match else ""


def _bullet(section: str, label: str) -> str | None:
    """A `- <label>: ...` bullet's text, continuation lines joined in."""

    match = re.search(rf"^- {re.escape(label)}:\s*(.+(?:\n  .+)*)", section, re.MULTILINE)
    if match is None:
        return None
    return " ".join(line.strip() for line in match.group(1).splitlines())


def _vex_statement_ids(vex_path: Path) -> set[str]:
    try:
        data = json.loads(vex_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    if not isinstance(data, dict):
        return set()
    return {
        entry["id"]
        for entry in data.get("vulnerabilities", [])
        if isinstance(entry, dict) and entry.get("id")
    }


def _as_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _live_dependency_advisory_waivers(waivers_text: str) -> list[dict[str, str]]:
    """Unexpired waivers.yml entries whose `kind` accepts a dependency advisory."""

    today = date.today()
    live = []
    for entry in _parse_waiver_entries(waivers_text):
        if entry.get("kind") not in DEPENDENCY_ADVISORY_KINDS:
            continue
        expires = _as_date(entry.get("expires", ""))
        if expires is not None and expires >= today:
            live.append(entry)
    return live


def security_declaration_failures(audits_text: str, waivers_text: str, vex_path: Path) -> list[str]:
    """Cross-check docs/RESPONSIBLE-TECH-AUDITS.md §F's VEX line against waivers.yml.

    On 2026-08-15 the registry held a live, accepted HIGH dependency waiver
    (WVR-007) while §F's VEX line still read "N/A today because scans report
    no unfixable HIGH/CRITICAL dependency CVE" -- both true when the
    sentence was written, both no longer consistent with each other once
    WVR-007 was granted, and nothing compared them (issue 96). This is that
    comparison:

    * If `waivers.yml` holds any live (unexpired) waiver whose `kind` is a
      dependency-advisory kind (`npm-audit` or `vex`), then `vex.json` must
      exist, must contain a statement for every such waived advisory id, and
      the §F VEX line must not say "N/A".
    * If it holds none, the §F line may say N/A (or may not -- either is
      consistent with "nothing is currently waived"), and `vex.json`, if
      present, must not carry a statement for an advisory that is not
      currently waived: a stale `not_affected` claim for a waiver that has
      since been retired is its own false claim, the same shape of defect in
      the other direction.
    """

    failures: list[str] = []
    section = _section(audits_text, "## F. Security and supply chain")
    vex_line = _bullet(section, "VEX")
    if vex_line is None:
        return ["docs/RESPONSIBLE-TECH-AUDITS.md §F has no 'VEX:' declaration line"]

    declares_na = bool(re.search(r"\bN/A\b", vex_line))
    live = _live_dependency_advisory_waivers(waivers_text)
    live_advisories = sorted({entry["advisory"] for entry in live if entry.get("advisory")})

    if live:
        ids = ", ".join(entry.get("id", "?") for entry in live)
        if declares_na:
            failures.append(
                f"waivers.yml holds a live dependency-advisory waiver ({ids}) but "
                f"docs/RESPONSIBLE-TECH-AUDITS.md §F's VEX line still says N/A: {vex_line!r}"
            )
        if not vex_path.exists():
            failures.append(
                f"waivers.yml holds a live dependency-advisory waiver ({ids}) but "
                f"{vex_path.name} does not exist"
            )
        else:
            vex_ids = _vex_statement_ids(vex_path)
            for advisory in live_advisories:
                if advisory not in vex_ids:
                    failures.append(
                        f"{vex_path.name} has no VEX statement for waived advisory {advisory}"
                    )
    elif vex_path.exists():
        stale = _vex_statement_ids(vex_path)
        if stale:
            failures.append(
                f"{vex_path.name} carries statement(s) for {', '.join(sorted(stale))} but "
                "waivers.yml holds no live dependency-advisory waiver -- a stale VEX "
                "statement for an advisory that is no longer waived is its own false claim"
            )
    return failures


# Three documents state the committed grounding benchmark's size. All three went
# stale the moment PR #89 added the formatting family (32 cases on top of the
# original 100), and nothing noticed for two months, because a prose count is
# exactly the kind of claim no gate reads. These regexes pin the sentence shape so
# the numbers stay machine-readable, and `benchmark_claim_failures` compares them
# against the committed file.
#
# The digit class is `[0-9]` rather than `\d`. `\d` matches every Unicode decimal
# digit and `int()` converts them, so a claim written with fullwidth digits would
# parse and compare equal while reading as an unreadable number on the page. With
# `[0-9]` such a claim stops matching and the check fails closed instead.
_README_BENCHMARK_RE = re.compile(r"([0-9]+)-case bilingual grounding benchmark")
_AUDITS_BENCHMARK_RE = re.compile(r"([0-9]+)-case benchmark includes planted EN/ES failures")
_ROADMAP_BENCHMARK_RE = re.compile(
    r"([0-9]+) committed cases: ([0-9]+) EN, ([0-9]+) ES; ([0-9]+) planted unbound failures"
)


def _benchmark_counts(path: Path) -> tuple[int, int, int, int]:
    """``(total, english, spanish, planted failures)`` from the committed file."""

    cases = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    return (
        len(cases),
        sum(1 for case in cases if case["language"] == "en"),
        sum(1 for case in cases if case["language"] == "es"),
        sum(1 for case in cases if not case["should_pass"]),
    )


def benchmark_claim_failures(root: Path) -> list[str]:
    """Check the benchmark size the docs state against the benchmark that ships.

    Fails closed on a missing claim as well as a wrong one. A sentence that no
    longer matches the expected shape is not evidence that the count is right; it
    is a claim this check can no longer read, which is how the stale one survived.
    """

    benchmark = root / "eval" / "grounding-benchmark.jsonl"
    if not benchmark.exists():
        return [f"{benchmark.name} is missing, so the documented benchmark size cannot be checked"]
    total, english, spanish, planted = _benchmark_counts(benchmark)

    failures: list[str] = []
    for name, pattern, shape in (
        ("README.md", _README_BENCHMARK_RE, "<n>-case bilingual grounding benchmark"),
        (
            "docs/RESPONSIBLE-TECH-AUDITS.md",
            _AUDITS_BENCHMARK_RE,
            "<n>-case benchmark includes planted EN/ES failures",
        ),
    ):
        text = (root / name).read_text(encoding="utf-8")
        match = pattern.search(text)
        if match is None:
            failures.append(
                f"{name} states no benchmark size in the form '{shape}', so the claim "
                "cannot be checked against eval/grounding-benchmark.jsonl"
            )
        elif int(match.group(1)) != total:
            failures.append(
                f"{name} claims a {match.group(1)}-case benchmark; "
                f"eval/grounding-benchmark.jsonl holds {total}"
            )

    roadmap = (root / "docs" / "ROADMAP.md").read_text(encoding="utf-8")
    roadmap_match = _ROADMAP_BENCHMARK_RE.search(roadmap)
    if roadmap_match is None:
        failures.append(
            "docs/ROADMAP.md states no benchmark size in the form '<n> committed cases: <n> EN, "
            "<n> ES; <n> planted unbound failures', so the claim cannot be checked against "
            "eval/grounding-benchmark.jsonl"
        )
    else:
        claimed = tuple(int(group) for group in roadmap_match.groups())
        actual = (total, english, spanish, planted)
        if claimed != actual:
            failures.append(
                "docs/ROADMAP.md claims the benchmark is "
                f"{claimed[0]} cases / {claimed[1]} EN / {claimed[2]} ES / {claimed[3]} planted "
                f"failures; eval/grounding-benchmark.jsonl holds "
                f"{actual[0]} / {actual[1]} / {actual[2]} / {actual[3]}"
            )
    return failures


# `docs/ci-action.md` publishes the composite action's `version` input default in
# its Inputs table and again in the prose beneath it. `action.yml` bumped that
# default to v0.2.0 and the documentation kept saying v0.1.0, so a reader copying
# the table got the wrong CLI. The default lives in exactly one place; these read
# it from there rather than restating it.
_ACTION_DEFAULT_RE = re.compile(r'^ {4}default: "([^"]+)"$', re.MULTILINE)
_DOC_ACTION_DEFAULT_RE = re.compile(r"^\| `version` +\| no +\| `([^`]+)` +\|", re.MULTILINE)
_DOC_ACTION_PROSE_RE = re.compile(r"defaults to `([^`]+)`, the tag named in")


def _action_version_default(action_yml: str) -> str | None:
    """The `version` input's default, read out of the action's own definition.

    Returns ``None`` when the block cannot be located unambiguously, which the
    caller reports as a failure. A default this check cannot find is not evidence
    that the documented one is right.
    """

    lines = action_yml.splitlines()
    try:
        start = lines.index("  version:")
    except ValueError:
        return None
    body: list[str] = []
    for line in lines[start + 1 :]:
        if line and not line.startswith("   "):
            break
        body.append(line)
    matches = _ACTION_DEFAULT_RE.findall("\n".join(body))
    return matches[0] if len(matches) == 1 else None


# The ROADMAP publishes the two live performance numbers in prose, beside an AUTO
# label that asserts a gate checks them. `perf/baseline.json` is where they are
# actually receipted, and nothing compared the two: the row could say 0.42 while
# the baseline said 1.0 and every gate stayed green. `[0-9]` rather than `\d`, for
# the reason `benchmark_claim_failures` states.
_ROADMAP_LIGHTHOUSE_RE = re.compile(
    r"\| Lighthouse performance \| ([0-9]+(?:\.[0-9]+)?) on the generated trace"
)
_ROADMAP_JS_BYTES_RE = re.compile(r"\| Script bytes on a published artifact \| ([0-9]+);")


def perf_claim_failures(root: Path) -> list[str]:
    """Check the performance figures docs/ROADMAP.md publishes against perf/baseline.json.

    Fails closed on a claim it cannot read as well as on one that is wrong. A row
    labelled AUTO states that something checks it; before this, nothing did.
    """

    baseline_path = root / "perf" / "baseline.json"
    if not baseline_path.exists():
        return [
            "perf/baseline.json is missing, so the performance figures docs/ROADMAP.md "
            "publishes cannot be checked"
        ]
    try:
        metrics = json.loads(baseline_path.read_text(encoding="utf-8"))["metrics"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        return [f"perf/baseline.json cannot be read as a metrics object ({exc}), so the "
                "performance figures docs/ROADMAP.md publishes cannot be checked"]

    roadmap = (root / "docs" / "ROADMAP.md").read_text(encoding="utf-8")
    failures: list[str] = []
    for label, pattern, key, shape in (
        (
            "Lighthouse performance",
            _ROADMAP_LIGHTHOUSE_RE,
            "lighthouse_performance",
            "<n> on the generated trace",
        ),
        (
            "Script bytes on a published artifact",
            _ROADMAP_JS_BYTES_RE,
            "js_kb_gzip",
            "<n>;",
        ),
    ):
        match = pattern.search(roadmap)
        if match is None:
            failures.append(
                f"docs/ROADMAP.md states no {label!r} figure in the form '{shape}', so the "
                "claim cannot be checked against perf/baseline.json"
            )
            continue
        recorded = metrics.get(key)
        if recorded is None:
            failures.append(
                f"perf/baseline.json records no {key!r}, so the {label!r} figure "
                "docs/ROADMAP.md publishes cannot be checked"
            )
        elif float(match.group(1)) != float(recorded):
            failures.append(
                f"docs/ROADMAP.md publishes {label!r} as {match.group(1)}; "
                f"perf/baseline.json records {recorded}"
            )
    return failures


def action_default_failures(root: Path) -> list[str]:
    """Check the action default `docs/ci-action.md` publishes against `action.yml`."""

    action = root / "action.yml"
    doc = root / "docs" / "ci-action.md"
    if not action.exists() or not doc.exists():
        return [
            "action.yml or docs/ci-action.md is missing, so the published default cannot be checked"
        ]

    actual = _action_version_default(action.read_text(encoding="utf-8"))
    if actual is None:
        return [
            "action.yml no longer states one unambiguous default for its `version` input, "
            "so the default docs/ci-action.md publishes cannot be checked against it"
        ]

    text = doc.read_text(encoding="utf-8")
    failures: list[str] = []
    for label, pattern in (
        ("its Inputs table", _DOC_ACTION_DEFAULT_RE),
        ("the prose under Pinning", _DOC_ACTION_PROSE_RE),
    ):
        match = pattern.search(text)
        if match is None:
            failures.append(
                f"docs/ci-action.md states no `version` default in {label}, so the claim "
                "cannot be checked against action.yml"
            )
        elif match.group(1) != actual:
            failures.append(
                f"docs/ci-action.md says in {label} that the action's `version` input "
                f"defaults to {match.group(1)}; action.yml sets {actual}"
            )
    return failures


# `docs/SPEC-STABILITY.md` names the current version of all three public
# contracts in one sentence. Each version has two other homes that ship: the
# constant the code writes, and the `const` the published JSON Schema pins. All
# three must agree, and nothing compared them.
_SCHEMA_CONTRACTS = (
    ("report spec", "src/outcome_receipts/config.py", "SPEC_SCHEMA_VERSION", "report-spec"),
    ("receipts manifest", "src/outcome_receipts/models.py", "SCHEMA_VERSION", "receipts"),
    (
        "workflow artifact",
        "src/outcome_receipts/workflows.py",
        "WORKFLOW_SCHEMA_VERSION",
        "workflow-artifact",
    ),
)
_SPEC_STABILITY_RE = re.compile(
    r"The report spec is at `([0-9.]+)`, the receipts manifest at `([0-9.]+)`, and the\n"
    r"workflow artifact at `([0-9.]+)`\."
)


def _module_constant(path: Path, name: str) -> str | None:
    match = re.search(rf'^{name} = "([^"]+)"$', path.read_text(encoding="utf-8"), re.MULTILINE)
    return match.group(1) if match else None


def schema_version_failures(root: Path) -> list[str]:
    """Check the schema versions `docs/SPEC-STABILITY.md` names against code and schemas."""

    failures: list[str] = []
    actual: list[str | None] = []
    for label, module, constant, schema_name in _SCHEMA_CONTRACTS:
        value = _module_constant(root / module, constant)
        if value is None:
            failures.append(
                f"{module} no longer defines {constant}, so the {label} version cannot be checked"
            )
        actual.append(value)
        schema_path = root / "docs" / "schema" / f"{schema_name}.schema.json"
        pinned = json.loads(schema_path.read_text(encoding="utf-8"))["properties"][
            "schema_version"
        ].get("const")
        if value is not None and pinned != value:
            failures.append(
                f"{module} sets {constant} to {value!r} but "
                f"docs/schema/{schema_name}.schema.json pins schema_version const {pinned!r}"
            )

    text = (root / "docs" / "SPEC-STABILITY.md").read_text(encoding="utf-8")
    match = _SPEC_STABILITY_RE.search(text)
    if match is None:
        failures.append(
            "docs/SPEC-STABILITY.md no longer names the three contract versions in the form "
            "'The report spec is at `X`, the receipts manifest at `Y`, and the workflow "
            "artifact at `Z`.', so the claim cannot be checked against the code"
        )
    else:
        for (label, module, constant, _schema), claimed, value in zip(
            _SCHEMA_CONTRACTS, match.groups(), actual, strict=True
        ):
            if value is not None and claimed != value:
                failures.append(
                    f"docs/SPEC-STABILITY.md says the {label} is at {claimed}; "
                    f"{module} sets {constant} to {value}"
                )
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
            "derived from its controls.yml instead of the vendored fallback (a missing "
            "checkout is a hard failure; one that exists but predates controls.yml warns "
            "and falls back), and waiver control IDs are validated against the same "
            "controls.yml instead of format-checked only"
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

    waivers_text = (ROOT / "waivers.yml").read_text(encoding="utf-8")
    control_ids = _load_control_ids(args.standards_dir) if args.standards_dir is not None else None
    failures.extend(waiver_failures(ROOT / "waivers.yml", control_ids=control_ids))

    audits_text = (ROOT / "docs" / "RESPONSIBLE-TECH-AUDITS.md").read_text(encoding="utf-8")
    failures.extend(security_declaration_failures(audits_text, waivers_text, ROOT / "vex.json"))
    failures.extend(doc_staleness_failures(ROOT, date.today()))
    failures.extend(benchmark_claim_failures(ROOT))
    failures.extend(perf_claim_failures(ROOT))
    failures.extend(action_default_failures(ROOT))
    failures.extend(schema_version_failures(ROOT))

    if failures:
        print("repository conformance failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print("repository declarations: pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
