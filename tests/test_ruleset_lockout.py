"""No committed ruleset file may lock the repository owner out when it is applied.

A ruleset file in this tree is not a description. It is an instrument: `docs/rulesets/`
carries the command that posts one, and `gh api -X POST .../rulesets --input <file>` sends
the file exactly as it stands. GitHub answers 201 whether or not a bypass actor survived.
With none, and with this profile requiring a pull request, six contexts, a strict
up-to-date policy, signed commits and linear history, the sole maintainer cannot merge
past a wedged check, cannot push, and cannot delete the ruleset that is blocking them.
That is not hypothetical: an agent applied a no-bypass ruleset elsewhere in this portfolio
and restoring access took a sweep across eighteen repositories.

Both committed rulesets here carried `"bypass_actors": []`, and the documented apply
command pointed at the staler of the two. Nothing read either file:
`grep -rln 'bypass_actors' tests/ src/ scripts/` returned nothing, so correcting the value
once would have left the regression path open.

Two design choices, both answering a defect this repository actually had.

**Files are discovered, not named.** The stale second ruleset existed for five months
without anything noticing, because a guard written against one hardcoded path is blind to
the file next to it. This module globs, so a ruleset file that reappears anywhere is
covered the day it lands, and finding none at all is a failure rather than a quiet pass.

**The document is parsed, not searched.** A truncated JSON file still contains the literal
string `bypass_actors`, so a grep-based check vouches for a file it cannot read. The parse
is what catches that, and an unparseable or missing file fails here rather than defaulting
to something the assertions would read as "nothing wrong".

`lockout_risk` is a pure function of a parsed document, so it is run against the documents
it must reject as well as against the ones in the tree, with a positive control so it
cannot pass by refusing everything.

What this does not check is whether a committed export still matches the live ruleset.
That needs a network call, which these gates do not make. See `docs/rulesets/README.md`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]

OWNER_BYPASS = {
    "actor_id": 5,
    "actor_type": "RepositoryRole",
    "bypass_mode": "always",
}
"""The repository owner's standing bypass, and the only entry a committed file may carry.

`RepositoryRole` 5 is admin. `bypass_mode: "always"` rather than `"pull_request"`, because
a bypass that only works inside a pull request is no use when the thing that is wedged is
the pull request itself.
"""


def ruleset_files() -> list[Path]:
    """Every committed ruleset document, found by shape rather than by name.

    Anything named `*.json` under a directory called `rulesets`. Deliberately broader than
    the one path that matters today: the defect this module exists to catch is a second
    ruleset file drifting unnoticed beside the first.
    """
    return sorted(
        path
        for path in ROOT.glob("**/rulesets/*.json")
        if ".git" not in path.parts and "node_modules" not in path.parts
    )


def load_ruleset(path: Path) -> dict[str, Any]:
    """One ruleset document, or a failure. Never a silently empty document."""
    if not path.is_file():
        pytest.fail(f"{path} is missing; the committed ruleset is what this checks")
    # Bound before the try, so the parse failing cannot leave the name unset. `pytest.fail`
    # raises, so the `isinstance` below is not reached after a JSONDecodeError; binding
    # `None` first means that even if it somehow were, the next check refuses rather than
    # reading an unset name. CodeQL's py/uninitialized-local-variable found the earlier
    # shape, which is the kind of "cannot happen" this module exists to distrust.
    loaded: Any = None
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        pytest.fail(f"{path} is not parseable JSON, so nothing can vouch for it: {exc}")
    if not isinstance(loaded, dict):
        pytest.fail(f"{path} is not a JSON object, so nothing can vouch for it: {loaded!r}")
    return loaded


def lockout_risk(ruleset: dict[str, Any]) -> str | None:
    """Why applying this document would lock the owner out, or ``None`` if it would not."""
    if "bypass_actors" not in ruleset:
        return "no bypass_actors key at all, which GitHub reads as an empty list"
    actors = ruleset["bypass_actors"]
    if not isinstance(actors, list):
        return f"bypass_actors is {type(actors).__name__}, not a list"
    if not actors:
        return (
            "bypass_actors is empty, so applying this leaves no break-glass path and the "
            "owner cannot merge, push or delete the ruleset that is blocking them"
        )
    if OWNER_BYPASS not in actors:
        return (
            f"bypass_actors does not carry the owner's standing bypass {OWNER_BYPASS}; "
            f"it carries {actors}"
        )
    return None


def test_at_least_one_ruleset_file_is_committed() -> None:
    """The vacuous pass this module must not have.

    Every assertion below is parametrized over the files found. If none are found, every
    one of them is skipped and the module reports success while checking nothing.
    """
    found = ruleset_files()
    assert found, (
        f"no ruleset file found under {ROOT}; this module would then pass by checking "
        "nothing, which is the shape of gate it exists to prevent"
    )


@pytest.mark.parametrize("path", ruleset_files(), ids=lambda p: str(p.relative_to(ROOT)))
def test_applying_a_committed_ruleset_would_not_lock_the_owner_out(path: Path) -> None:
    """The assertion the empty list has to fail, for every committed ruleset."""
    risk = lockout_risk(load_ruleset(path))
    assert risk is None, (
        f"applying {path.relative_to(ROOT)} as committed would lock the repository owner "
        f"out: {risk}. See docs/rulesets/README.md."
    )


@pytest.mark.parametrize("path", ruleset_files(), ids=lambda p: str(p.relative_to(ROOT)))
def test_the_owner_is_the_only_bypass_actor(path: Path) -> None:
    """One actor. A team, an app or a second role would be a real widening; this is not."""
    actors = load_ruleset(path)["bypass_actors"]
    assert actors == [OWNER_BYPASS], (
        f"{path.relative_to(ROOT)}: the owner's standing bypass is the only entry a "
        f"committed ruleset may carry, and a second one widens who can skip every "
        f"required check: {actors}"
    )


@pytest.mark.parametrize(
    ("document", "expected"),
    [
        ({"bypass_actors": []}, "empty"),
        ({}, "no bypass_actors key"),
        ({"bypass_actors": {}}, "not a list"),
        (
            {
                "bypass_actors": [
                    {"actor_id": 1, "actor_type": "Integration", "bypass_mode": "always"}
                ]
            },
            "does not carry the owner",
        ),
        (
            {"bypass_actors": [dict(OWNER_BYPASS, bypass_mode="pull_request")]},
            "does not carry the owner",
        ),
    ],
    ids=["empty", "absent", "wrong-type", "wrong-actor", "wrong-mode"],
)
def test_the_lockout_check_rejects_the_documents_it_must_reject(
    document: dict[str, Any], expected: str
) -> None:
    """Five ways to lose the bypass, each of which GitHub answers with a 201.

    The empty list is the one that was committed, twice. `pull_request` mode is the one
    the portfolio's CI-CD standard actually asks for, and it is the subtle one: it looks
    like a bypass and is not one when the pull request is what has wedged.
    """
    risk = lockout_risk(document)
    assert risk is not None, f"{document} should be refused"
    assert expected in risk


def test_the_lockout_check_accepts_the_shape_it_should() -> None:
    """A positive control, so the check above is not passing by refusing everything."""
    assert lockout_risk({"bypass_actors": [OWNER_BYPASS]}) is None


def test_the_ruleset_readme_names_the_bypass_the_files_carry() -> None:
    """The README is what a person reads before posting. It must name the same actor."""
    doc = (ROOT / "docs" / "rulesets" / "README.md").read_text(encoding="utf-8")
    for fragment in ('"actor_id": 5', "RepositoryRole", "always"):
        assert fragment in doc, f"docs/rulesets/README.md does not name {fragment!r}"
