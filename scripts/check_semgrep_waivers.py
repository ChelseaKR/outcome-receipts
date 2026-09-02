#!/usr/bin/env python3
"""Cross-check `.semgrep-waivers.yml` against the suppressions actually in the tree.

The ledger states its own invariant in its header: every entry there must have a
matching inline suppression comment in the code. Nothing enforced it, in either
direction. A row could outlive the suppression it documents, and an inline
suppression could be added with no row at all, and `make verify` stayed green
either way, so SEC-10 waiver hygiene was a promise in a comment rather than a
gate.

This is the same comparison `scripts/check_conformance.py` already makes between
`waivers.yml` and section F of the audits document (issue 96), applied to the
Semgrep ledger:

* every ledger row's rule id must be suppressed somewhere in the tree;
* every path a row names must itself carry that suppression;
* every inline suppression must have a ledger row for the rule it names;
* an unqualified suppression naming no rule is refused, because it silences
  every rule at that line and no ledger row can describe what it accepted.

Then the same question about the ledger's own dates, because a row can be
perfectly consistent with the tree and still be a waiver nobody has looked at
since it was granted:

* `last_reviewed` more than `REVIEW_INTERVAL_DAYS` old fails, naming the
  tracking issue that owns the re-review. Issues 52 and 53 promise a quarterly
  review; the field recording it was parsed as a date and then never read, so
  the promise had no clock on it and a waiver reviewed once could stay green
  forever;
* `last_reviewed` in the future is refused, since a date ahead of today can
  never lapse and would buy the row unlimited green;
* the review date has to appear in `docs/RESPONSIBLE-TECH-AUDITS.md` too. Issue
  52's acceptance criteria name both records; nothing compared them, so one
  could be updated and the other forgotten.

Python files are read through `tokenize`, so a directive quoted inside a
docstring or a test fixture is not mistaken for a live suppression. Reads the
repository by default; `--root` and `--ledger` exist so
tests/test_semgrep_ledger.py drives the identical code path over fixtures.
"""

from __future__ import annotations

import argparse
import re
import sys
import tokenize
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: Where a suppression can legitimately live: every directory of this
#: repository's own authored code, and the file suffixes Semgrep's default and
#: Python profiles parse.
SCAN_DIRS = ("src", "tests", "scripts", ".github")
SCAN_SUFFIXES = frozenset({".py", ".mjs", ".js", ".sh", ".yml", ".yaml", ".toml"})

#: Semgrep's suppression syntax, anchored to the start of a comment: bare
#: silences every rule on the line, and a colon-separated list silences only
#: those rules. Anchoring is what keeps prose that merely mentions the syntax
#: (this file included) from registering as a suppression. Digit classes are
#: spelled out rather than `\d`, which also matches non-ASCII decimal digits.
_DIRECTIVE_RE = re.compile(
    r"^(?:#|//)[ \t]*nosemgrep(?::[ \t]*([A-Za-z0-9_.\-]+(?:[ \t]*,[ \t]*[A-Za-z0-9_.\-]+)*))?"
)
_COMMENT_START_RE = re.compile(r"(?:#|//)")

REQUIRED_FIELDS = ("rule_id", "locations", "added", "last_reviewed", "tracking_issue", "reason")

#: How long a `last_reviewed` date stays good. Issues 52 and 53 are the audit
#: owners CQ-35 and SEC-10 require, and both commit to a *quarterly* re-review;
#: 92 days is the same number `check_conformance.CADENCE_DAYS` maps "quarter" to,
#: so a quarter means the same span in both gates.
#:
#: Until this, that commitment was a sentence in two issues and a field nothing
#: read. `last_reviewed` was validated as an ISO date and then ignored, so a
#: waiver whose review had lapsed by a year passed exactly like one reviewed
#: yesterday, and the two issues could stay open indefinitely with nothing able
#: to say the promise in them had been broken. A recurring review with no clock
#: on it is not a control.
REVIEW_INTERVAL_DAYS = 92

#: The second place each review has to be recorded. Issue 52's acceptance
#: criteria name both this ledger and the audits document, and nothing compared
#: them: the ledger could carry a fresh review date while the audit section a
#: reader actually opens still described the previous one. The check is
#: deliberately weak -- the date string has to appear somewhere in the document
#: -- because a stricter shape would be a second thing to keep in sync. It
#: catches the failure that has actually happened here, which is one record
#: being updated and the other forgotten.
AUDITS_DOC = Path("docs") / "RESPONSIBLE-TECH-AUDITS.md"

_BLOCK_INDICATORS = frozenset({">", ">-", ">+", "|", "|-", "|+"})


@dataclass(frozen=True)
class Suppression:
    """One inline suppression: where it is and which rules it names."""

    path: str
    line: int
    rule_ids: tuple[str, ...]


@dataclass(frozen=True)
class LedgerEntry:
    """One parsed ledger row."""

    rule_id: str
    locations: tuple[str, ...]
    fields: dict[str, str]


def _indent(raw: str) -> int:
    return len(raw) - len(raw.lstrip(" "))


def parse_ledger(text: str) -> list[LedgerEntry]:
    """Parse the ledger's `waivers:` sequence.

    A small parser for exactly the shape the ledger documents, matching the
    no-YAML-dependency choice `scripts/check_conformance.py` already made for
    `waivers.yml`. Folded `reason:` scalars are collected by indentation rather
    than by looking for a colon, because a reason sentence contains colons and
    reading one as a field name silently emptied the `reason` of the second
    entry when this parser was first written.
    """

    raw_entries: list[dict[str, list[str]]] = []
    current: dict[str, list[str]] | None = None
    key = ""
    block_indent: int | None = None
    in_waivers = False

    for raw in text.splitlines():
        stripped = raw.strip()
        indent = _indent(raw)
        if block_indent is not None and current is not None:
            if stripped and indent >= block_indent:
                current.setdefault(key, []).append(stripped)
                continue
            block_indent = None
        if not stripped or stripped.startswith("#"):
            continue
        if indent == 0:
            in_waivers = stripped == "waivers:"
            current = None
            continue
        if not in_waivers:
            continue
        if indent == 2 and stripped.startswith("- "):
            current = {}
            raw_entries.append(current)
            stripped, indent = stripped[2:].strip(), 4
        if current is None:
            continue
        key, block_indent = _absorb(current, key, indent, stripped)

    return [_entry(fields) for fields in raw_entries]


def _absorb(
    current: dict[str, list[str]], key: str, indent: int, line: str
) -> tuple[str, int | None]:
    """Fold one ledger line into `current`; return the open key and block indent."""

    if line.startswith("- "):
        current.setdefault(key, []).append(line[2:].strip())
        return key, None
    name, sep, value = line.partition(":")
    if not sep:
        current.setdefault(key, []).append(line)
        return key, None
    name, value = name.strip(), value.strip()
    if value and value not in _BLOCK_INDICATORS:
        current[name] = [value]
        return name, None
    current.setdefault(name, [])
    return name, indent + 2 if value in _BLOCK_INDICATORS else None


def _entry(fields: dict[str, list[str]]) -> LedgerEntry:
    flat = {name: " ".join(values).strip() for name, values in fields.items()}
    return LedgerEntry(
        rule_id=flat.get("rule_id", ""),
        locations=tuple(fields.get("locations", ())),
        fields=flat,
    )


def _location_path(location: str) -> str:
    """The repository-relative path a `locations:` item names, note stripped."""

    return location.split(" (", 1)[0].strip()


def _python_comments(path: Path) -> list[tuple[int, str]] | None:
    """(line, comment text) for every Python comment, or None if unparseable."""

    try:
        with path.open("rb") as stream:
            tokens = list(tokenize.tokenize(stream.readline))
    except (OSError, SyntaxError, UnicodeDecodeError, tokenize.TokenError):
        return None
    return [(token.start[0], token.string) for token in tokens if token.type == tokenize.COMMENT]


def _comment_candidates(path: Path, text: str) -> list[tuple[int, str]]:
    """Every comment in a file, or, where it cannot be tokenized, every line
    from its first comment marker onward. The fallback over-reports rather than
    under-reports: an unreadable file must not become a place a suppression can
    hide."""

    if path.suffix == ".py":
        comments = _python_comments(path)
        if comments is not None:
            return comments
    candidates: list[tuple[int, str]] = []
    for number, line in enumerate(text.splitlines(), 1):
        match = _COMMENT_START_RE.search(line)
        if match is not None:
            candidates.append((number, line[match.start() :]))
    return candidates


def _suppressions_in(path: Path, root: Path) -> list[Suppression]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    found: list[Suppression] = []
    for number, comment in _comment_candidates(path, text):
        match = _DIRECTIVE_RE.match(comment.strip())
        if match is None:
            continue
        named = match.group(1)
        rules = tuple(part.strip() for part in named.split(",")) if named else ()
        found.append(Suppression(path.relative_to(root).as_posix(), number, rules))
    return found


def find_suppressions(root: Path) -> list[Suppression]:
    """Every inline Semgrep suppression in this repository's own authored code."""

    found: list[Suppression] = []
    for directory in SCAN_DIRS:
        base = root / directory
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if path.is_file() and path.suffix in SCAN_SUFFIXES:
                found.extend(_suppressions_in(path, root))
    return found


def _schema_failures(entry: LedgerEntry, label: str) -> list[str]:
    failures = [
        f"{label}: missing {field}" for field in REQUIRED_FIELDS if not entry.fields.get(field)
    ]
    for field in ("added", "last_reviewed"):
        value = entry.fields.get(field, "")
        if not value:
            continue
        try:
            date.fromisoformat(value)
        except ValueError:
            failures.append(f"{label}: {field} {value!r} is not an ISO date")
    return failures


def _review_failures(entry: LedgerEntry, label: str, today: date, audits: str | None) -> list[str]:
    """Has this waiver's quarterly review happened, and is it recorded twice?

    Runs only on a row whose `last_reviewed` already parsed, so an unreadable
    date is reported once as a schema failure rather than again here as a lapse.
    """

    value = entry.fields.get("last_reviewed", "")
    try:
        reviewed = date.fromisoformat(value)
    except ValueError:
        return []

    issue = entry.fields.get("tracking_issue", "") or "the waiver's tracking issue"
    failures: list[str] = []
    if reviewed > today:
        # Not pedantry: a future date is the one value that would make this
        # check permanently silent, because it can never go stale. A review
        # dated ahead of today has not happened.
        failures.append(
            f"{label}: last_reviewed is {value}, which is after today ({today.isoformat()}); "
            "a review that has not happened yet cannot be recorded as done"
        )
    elif (today - reviewed).days > REVIEW_INTERVAL_DAYS:
        overdue = (today - reviewed).days - REVIEW_INTERVAL_DAYS
        failures.append(
            f"{label}: last reviewed {value}, {(today - reviewed).days} days ago, and this "
            f"waiver is reviewed quarterly ({REVIEW_INTERVAL_DAYS} days) -- {overdue} day(s) "
            f"overdue. Re-run the pinned scanner with the suppression deleted, then record "
            f"the result in the ledger and in {AUDITS_DOC.as_posix()}, or retire the waiver. "
            f"Owner: {issue}"
        )

    if audits is not None and value not in audits:
        failures.append(
            f"{label}: the ledger records a review on {value} but {AUDITS_DOC.as_posix()} "
            "does not mention that date, so the two records of the same review disagree"
        )
    return failures


def _entry_failures(
    entry: LedgerEntry,
    suppressions: list[Suppression],
    today: date,
    audits: str | None,
) -> list[str]:
    """Schema, review-currency and coverage failures for one ledger row."""

    label = entry.rule_id or "<missing rule_id>"
    failures = _schema_failures(entry, label)
    if not entry.rule_id:
        return failures
    failures.extend(_review_failures(entry, label, today, audits))

    covering = [item for item in suppressions if entry.rule_id in item.rule_ids]
    if not covering:
        failures.append(
            f"{label}: the ledger records this waiver but no inline suppression naming "
            "it exists anywhere in the tree; delete the row or restore the suppression"
        )
        return failures

    covered = {item.path for item in covering}
    failures.extend(
        f"{label}: the ledger names {_location_path(location)} but that file carries no "
        f"suppression for this rule"
        for location in entry.locations
        if _location_path(location) not in covered
    )
    return failures


def _undocumented_failures(
    suppressions: list[Suppression], known: set[str], name: str
) -> list[str]:
    failures: list[str] = []
    for item in suppressions:
        if not item.rule_ids:
            failures.append(
                f"{item.path}:{item.line}: this suppression names no rule, so it silences "
                "every rule at that line and no ledger row can record what was accepted"
            )
            continue
        failures.extend(
            f"{item.path}:{item.line}: rule {rule_id!r} is suppressed here but has no row "
            f"in {name}; add one or remove the suppression"
            for rule_id in item.rule_ids
            if rule_id not in known
        )
    return failures


def ledger_failures(root: Path, ledger_path: Path, today: date) -> list[str]:
    """Every disagreement between the ledger, the tree, the calendar and the audits doc."""

    if not ledger_path.exists():
        return [f"{ledger_path} does not exist; the Semgrep waiver ledger is required"]

    entries = parse_ledger(ledger_path.read_text(encoding="utf-8"))
    suppressions = find_suppressions(root)

    audits_path = root / AUDITS_DOC
    # `None` means "there is no second record to compare against", which is a
    # different statement from "the two records disagree" and must not be
    # reported as one. It is still a failure, reported once for the document
    # rather than once per row.
    audits: str | None = None
    failures: list[str] = []
    if audits_path.exists():
        audits = audits_path.read_text(encoding="utf-8")
    elif entries:
        failures.append(
            f"{AUDITS_DOC.as_posix()} is missing, so the second record of each waiver "
            "review cannot be read; the ledger's dates cannot be corroborated"
        )

    known: set[str] = set()
    for entry in entries:
        if entry.rule_id and entry.rule_id in known:
            failures.append(f"{entry.rule_id}: duplicate ledger row")
        known.add(entry.rule_id)
        failures.extend(_entry_failures(entry, suppressions, today, audits))

    failures.extend(_undocumented_failures(suppressions, known, ledger_path.name))
    return failures


def main(argv: list[str] | None = None) -> int:
    """Return nonzero when the ledger and the tree disagree."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--ledger", type=Path, default=None)
    parser.add_argument(
        "--today",
        type=date.fromisoformat,
        default=None,
        help="the date to judge review currency against (default: today)",
    )
    args = parser.parse_args(argv)

    today = args.today if args.today is not None else date.today()
    ledger = args.ledger if args.ledger is not None else args.root / ".semgrep-waivers.yml"
    failures = ledger_failures(args.root, ledger, today)
    if failures:
        print("semgrep waiver ledger failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1

    entries = parse_ledger(ledger.read_text(encoding="utf-8"))
    inline = len(find_suppressions(args.root))
    # Print the nearest review deadline rather than only a row count, so a green
    # run says when this stops being green instead of implying it never will.
    due = min(
        (date.fromisoformat(entry.fields["last_reviewed"]) for entry in entries),
        default=None,
    )
    horizon = (
        f", next review due {(due + timedelta(days=REVIEW_INTERVAL_DAYS)).isoformat()}"
        if due is not None
        else ""
    )
    print(
        f"semgrep waiver ledger: {len(entries)} row(s) matched against "
        f"{inline} inline suppression(s){horizon}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
