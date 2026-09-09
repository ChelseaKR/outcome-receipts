"""Every workflow's concurrency key must not cost a commit its verdict.

A GitHub concurrency group holds one running run and one *pending* run. A third
run joining the group evicts the pending one, which then ends `cancelled` having
dispatched zero jobs -- no failure, no verdict, and a green-looking checks list
with a hole in it. Keyed only on `github.ref`, every push to the default branch
shares one group with the merge before it, so a burst of merges loses the middle
ones.

Measured twice in this repository. Over the 100 most recent `ci` runs on `main`,
six ended `cancelled` with zero jobs dispatched, which #147 fixed for `ci.yml`.
Then on 2026-09-06, in the same pair of merges, `ci.yml` kept both of its runs
while `portfolio standards` (run 34035866790) and `scorecard` (run 34035866788)
lost theirs to the identical mechanism on commit `abde41c` -- and
`portfolio standards conformance` is a required status check on `main`.

`cancel-in-progress: false` does not protect against this. It governs the
running run; the eviction happens to the pending one. `scorecard.yml` had it set
and was cancelled anyway.

So the rule is mechanical: a workflow that declares a concurrency group must key
non-pull-request events on the commit. Exemptions are declared here, with their
reason, rather than achieved by a workflow quietly not being checked.

Parsed with a regular expression rather than a YAML loader on purpose: PyYAML is
not a dependency of this project, only a transitive one, and the other workflow
shape tests in this directory read the files the same way.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"

#: `concurrency:` at column zero, then its indented block up to the next
#: top-level key. Anchored to the start of a line so a `concurrency:` nested
#: inside a job cannot be mistaken for the workflow-level one.
_CONCURRENCY_RE = re.compile(r"^concurrency:\n((?:[ \t]+.*\n|\n)+)", re.MULTILINE)
_GROUP_RE = re.compile(r"^[ \t]+group:[ \t]*(.+?)[ \t]*$", re.MULTILINE)

#: Workflows whose concurrency group is deliberately *not* per-commit, and why.
#: A single global group is the right shape for a publish pipeline: two releases
#: must never run at once, and `release.yml` is dispatch-only, so there is no
#: burst of pushes for a pending run to be evicted by.
EXEMPT = {
    "release.yml": (
        "one global `release` group serialises publication; dispatch-only, so no "
        "push burst can evict a pending run"
    ),
}


def _workflow_files() -> list[Path]:
    files = sorted(WORKFLOWS.glob("*.yml")) + sorted(WORKFLOWS.glob("*.yaml"))
    assert files, "no workflow files found; this test would pass vacuously"
    return files


def _concurrency_group(text: str) -> str | None:
    block = _CONCURRENCY_RE.search(text)
    if block is None:
        return None
    group = _GROUP_RE.search(block.group(1))
    assert group is not None, "a concurrency block with no group: key"
    return group.group(1)


def test_every_workflow_with_a_concurrency_group_keys_pushes_on_the_commit() -> None:
    checked = 0
    for path in _workflow_files():
        group = _concurrency_group(path.read_text(encoding="utf-8"))
        if group is None or path.name in EXEMPT:
            continue
        checked += 1
        assert "github.sha" in group, (
            f"{path.name}: concurrency group {group!r} does not key on the commit, "
            "so consecutive pushes share one group and the pending run is evicted "
            "with zero jobs and no verdict"
        )

    # Not a vacuous pass, and not a hand-maintained number either. This read
    # `assert checked == 4` until 2026-09-09, when adding a sixth workflow --
    # one that keys on the commit correctly -- turned it red for having done
    # the right thing. A count somebody has to remember to bump is the shape
    # this repository has already been caught by elsewhere; the anti-vacuity
    # property it was reaching for is structural instead.
    #
    # Every workflow is either exempt or checked, so the parser losing a file
    # fails here, and a *new* workflow with no concurrency block at all fails
    # here too -- which the old count could not see, because a group of None is
    # skipped above.
    unaccounted = sorted(
        path.name
        for path in _workflow_files()
        if path.name not in EXEMPT and _concurrency_group(path.read_text(encoding="utf-8")) is None
    )
    assert not unaccounted, (
        f"{', '.join(unaccounted)} declare(s) no workflow-level concurrency group, so this "
        "rule says nothing about it. Add a group, or add it to EXEMPT with its reason"
    )
    assert checked + len(EXEMPT) == len(_workflow_files())
    assert checked, "no workflow was checked; the parser found no concurrency group at all"


def test_every_exemption_names_a_workflow_that_exists_and_gives_a_reason() -> None:
    # An exemption for a file that no longer exists is coverage silently dropped.
    for name, reason in EXEMPT.items():
        assert (WORKFLOWS / name).exists(), f"{name} is exempted but does not exist"
        assert reason.strip(), f"{name} is exempted with no reason"
        assert _concurrency_group((WORKFLOWS / name).read_text(encoding="utf-8")) is not None


def test_the_parser_reads_a_ref_only_key_and_the_rule_rejects_it() -> None:
    # The negative control, run through the same parser the test uses rather
    # than against a hand-written string, so it cannot pass while the parser is
    # broken. This is the exact shape all four workflows had before #147.
    regressed = "concurrency:\n  group: portfolio-standards-${{ github.ref }}\n"
    regressed += "  cancel-in-progress: false\n\njobs:\n"

    group = _concurrency_group(regressed)

    assert group == "portfolio-standards-${{ github.ref }}"
    assert "github.sha" not in group
