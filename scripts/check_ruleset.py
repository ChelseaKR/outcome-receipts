"""Does every ruleset definition here still record the owner's standing bypass?

`bypass_actors` is the one field in a ruleset that a well-meaning edit can
empty and make look *stricter*. It is not stricter. The repository owner keeps
a standing `RepositoryRole` 5 / `always` bypass, deliberately and permanently,
because an agent once applied a ruleset with no bypass and locked the owner out
of their own repository, and restoring access took a sweep across eighteen
repositories. An empty list is not a stricter gate, it is the lockout.

Until 2026-08-28 both committed definitions here (`.github/rulesets/main.json`
and `docs/rulesets/main.json`) said `"bypass_actors": []` while the live
`protect-main` ruleset carried the owner's bypass, and `docs/rulesets/README.md`
published `gh api -X POST ... --input docs/rulesets/main.json` as the way to
apply a ruleset -- so following this repository's own documented procedure would
have produced an active ruleset on `main` that the owner could not bypass.
Nothing compared the files to the repository, and nothing checked either file
against the one actor that has to be in it.

**Each side is judged on its own, and the two are never compared to each
other.** That is the whole design, and the reason is concrete: if a future edit
put `"bypass_actors": []` back into a committed file on a day the owner had also
been locked out of the repository, the two sides would agree, and any check
built on equality would report conformance on exactly the incident it exists to
prevent. So for the live ruleset and for each committed file, independently:

1. the owner's standing bypass must be present, and
2. no other actor -- a team, a GitHub App, a second role -- may have one.

This program performs no network access. The caller fetches the live ruleset
and hands it over, so the thing that fetches and the thing that judges stay
separable, and the judging half stays testable offline:

    gh api repos/ChelseaKR/outcome-receipts/rulesets/18752852 |
      .venv/bin/python scripts/check_ruleset.py --live -

With no `--live` it checks the committed files alone, which is what
`tests/test_ruleset.py` does on every run of `make verify`.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

#: Both committed ruleset definitions. There are two, and they are not copies:
#: `.github/rulesets/main.json` describes the live `protect-main` ruleset, and
#: `docs/rulesets/main.json` is the earlier "intended" ruleset from the CICD-12
#: remediation. `docs/rulesets/README.md` records why both exist. Both are
#: checked, because a file that omits the owner's bypass is a lockout waiting
#: for whoever applies it, whichever of the two they reach for.
COMMITTED_FILES = (
    ROOT / ".github" / "rulesets" / "main.json",
    ROOT / "docs" / "rulesets" / "main.json",
)

#: The repository owner's standing bypass. `RepositoryRole` 5 with
#: `bypass_mode: "always"` is what GitHub returns for it. It is permanent by
#: the owner's explicit decision after a no-bypass ruleset locked them out of
#: their own repository, so it is written here as a constant and asserted
#: against each side independently, and neither "the owner was locked out
#: again" nor "somebody granted a second actor a bypass" can pass as
#: conformance. See docs/rulesets/README.md, "Why the owner can bypass".
OWNER_BYPASS: dict[str, Any] = {
    "actor_id": 5,
    "actor_type": "RepositoryRole",
    "bypass_mode": "always",
}

_LOCKOUT = (
    "An empty or owner-less bypass list is not a stricter gate, it is the "
    'lockout -- see docs/rulesets/README.md, "Why the owner can bypass".'
)


def _actors(ruleset: dict[str, Any]) -> list[Any] | None:
    """The `bypass_actors` list, or None when the field is absent.

    Absent is not empty, and the difference matters in both directions. A
    token without permission to read repository administration gets a reduced
    payload from the API with `bypass_actors` omitted entirely; a committed
    file can lose the key to an edit. `.get("bypass_actors", [])` would turn
    either into "no one bypasses", which is a verdict drawn from a field that
    was never read, in the one check written to refuse exactly that.
    """

    actors = ruleset.get("bypass_actors")
    if actors is None:
        return None
    return list(actors) if isinstance(actors, list) else []


def side_findings(label: str, ruleset: dict[str, Any]) -> list[str]:
    """Everything wrong with one side's bypass list, judged on its own.

    Never against the other side: two wrong values that agree with each other
    is the failure mode this check exists for.
    """

    actors = _actors(ruleset)
    if actors is None:
        return [
            f"{label}: no `bypass_actors` field to read. An absent field is not "
            "an empty one; reading the live ruleset's bypass actors needs a "
            "token with permission to read repository administration. Nothing "
            "about the owner's standing bypass has been verified here."
        ]

    findings: list[str] = []
    if OWNER_BYPASS not in actors:
        findings.append(
            f"{label}: the repository owner's standing bypass "
            f"({json.dumps(OWNER_BYPASS, sort_keys=True)}) is missing. {_LOCKOUT}"
        )
    findings.extend(
        f"{label}: unreviewed bypass actor {json.dumps(actor, sort_keys=True)} may "
        "skip these rules. Only the owner's own standing bypass is expected; a "
        "team, a GitHub App or a second role is not."
        for actor in actors
        if actor != OWNER_BYPASS
    )
    return findings


def bypass_findings(live: dict[str, Any], committed: dict[str, Any]) -> list[str]:
    """The live ruleset and one committed file, each judged on its own.

    An equality check between them would pass on the day both were emptied
    together, which is the lockout recurring with a green tick on it. This
    returns two findings for that case, never zero.
    """

    return side_findings("live ruleset", live) + side_findings("committed ruleset", committed)


def committed_findings(paths: tuple[Path, ...] = COMMITTED_FILES) -> list[str]:
    """Every committed definition that no longer records the owner's bypass.

    Checked on the files themselves, not only inside a comparison, because
    `docs/rulesets/README.md` documents applying a file to the repository: an
    omission here becomes a lockout the moment somebody follows it.
    """

    findings: list[str] = []
    for path in paths:
        rel = path.relative_to(ROOT) if path.is_relative_to(ROOT) else path
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            findings.append(f"{rel}: cannot be read as JSON ({error})")
            continue
        if not isinstance(data, dict):
            findings.append(f"{rel}: is not a ruleset object")
            continue
        findings.extend(side_findings(str(rel), data))
    return findings


def _live_rulesets(raw: str) -> list[dict[str, Any]]:
    """One ruleset, or the whole `GET /repos/{owner}/{repo}/rulesets` list."""

    data = json.loads(raw)
    items = data if isinstance(data, list) else [data]
    return [item for item in items if isinstance(item, dict)]


def report(live: list[dict[str, Any]], paths: tuple[Path, ...] = COMMITTED_FILES) -> list[str]:
    """Every finding, live side and committed side, with nothing compared."""

    findings = list(committed_findings(paths))
    for ruleset in live:
        name = ruleset.get("name", "?")
        identifier = ruleset.get("id", "?")
        findings.extend(side_findings(f"live ruleset {identifier} ({name})", ruleset))
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live",
        help=(
            "a file holding the JSON body of GET /repos/{owner}/{repo}/rulesets, "
            "or of one ruleset. '-' reads stdin. This program never reaches the "
            "network itself. Omit it to check the committed files alone."
        ),
    )
    arguments = parser.parse_args(argv)

    live: list[dict[str, Any]] = []
    if arguments.live is not None:
        raw = (
            sys.stdin.read()
            if arguments.live == "-"
            else Path(arguments.live).read_text(encoding="utf-8")
        )
        live = _live_rulesets(raw)
        if not live:
            print("no ruleset in the supplied live payload", file=sys.stderr)
            return 1

    findings = report(live)
    if findings:
        print("ruleset bypass check failed:", file=sys.stderr)
        for finding in findings:
            print(f"- {finding}", file=sys.stderr)
        return 1
    checked = "committed files" if not live else "committed files and the live ruleset"
    print(f"ruleset bypass check: pass ({checked})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
