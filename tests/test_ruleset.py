"""The owner's standing bypass, held against each side on its own.

`bypass_actors` is the one ruleset field where an edit that looks like
tightening is the outage. The repository owner keeps a standing
`RepositoryRole` 5 / `always` bypass, deliberately and permanently: an agent
once applied a ruleset with no bypass and locked the owner out of their own
repository, and restoring access took a sweep across eighteen repositories.

Until 2026-08-28 both committed definitions said `"bypass_actors": []` while
the live `protect-main` ruleset carried the owner's bypass, and
`docs/rulesets/README.md` published a `gh api -X POST --input` step for
applying a file -- so this repository documented, as its own procedure, the
exact action that causes the lockout.

These tests never compare the two sides to each other. Two wrong values that
agree is the failure mode that matters here, so
`test_both_sides_emptied_is_still_a_failure` pins it: two findings, not zero.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from scripts.check_ruleset import (
    COMMITTED_FILES,
    OWNER_BYPASS,
    bypass_findings,
    committed_findings,
    main,
    report,
    side_findings,
)

ROOT = Path(__file__).resolve().parents[1]

# The live ruleset as the API returned it on 2026-08-28, from
# `gh api repos/ChelseaKR/outcome-receipts/rulesets/18752852`, trimmed to the
# fields this check reads and recorded rather than fetched so the suite stays
# offline and deterministic. **The live value is the correct one**: the bypass
# below is the owner's own, and a check that failed against it would be a
# broken check, not a strict one.
LIVE_2026_08_28: dict[str, Any] = {
    "id": 18752852,
    "name": "protect-main",
    "target": "branch",
    "enforcement": "active",
    "conditions": {"ref_name": {"exclude": [], "include": ["refs/heads/main"]}},
    "bypass_actors": [{"actor_id": 5, "actor_type": "RepositoryRole", "bypass_mode": "always"}],
    "current_user_can_bypass": "always",
}

# Actors that are not the owner's own bypass. Any one of them on either side is
# the threat actually worth guarding: a second party able to skip the gate.
OTHER_ACTORS: tuple[dict[str, Any], ...] = (
    {"actor_id": 4242, "actor_type": "Team", "bypass_mode": "pull_request"},
    {"actor_id": 99, "actor_type": "Integration", "bypass_mode": "always"},
    {"actor_id": 2, "actor_type": "RepositoryRole", "bypass_mode": "always"},
    {"actor_id": 5, "actor_type": "RepositoryRole", "bypass_mode": "pull_request"},
)


def _committed(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


@pytest.mark.parametrize("path", COMMITTED_FILES, ids=lambda p: str(p.relative_to(ROOT)))
def test_every_committed_file_records_the_owner_bypass(path: Path) -> None:
    """Not a fixture: the actual files. `docs/rulesets/README.md` documents
    applying one of these to the repository, so an omission here is a lockout
    the moment somebody follows the instruction. Both files are checked because
    both are appliable, and the two are not copies of each other."""

    assert _committed(path)["bypass_actors"] == [OWNER_BYPASS]


def test_the_real_configuration_is_a_pass_not_a_finding() -> None:
    """Live as recorded today, against the files as committed today."""

    assert report([LIVE_2026_08_28]) == []
    assert committed_findings() == []


@pytest.mark.parametrize("extra", OTHER_ACTORS)
def test_a_second_bypass_actor_is_reported_on_either_side(extra: dict[str, Any]) -> None:
    """A team, a GitHub App, a second role, or the owner's role at a weaker
    bypass mode -- planted live or in the file, each is one finding naming the
    actor, and the owner's own bypass being present does not excuse it."""

    live = {**LIVE_2026_08_28, "bypass_actors": [OWNER_BYPASS, extra]}
    found = bypass_findings(live, {"bypass_actors": [OWNER_BYPASS]})
    assert len(found) == 1, found
    assert "unreviewed bypass actor" in found[0]
    assert str(extra["actor_id"]) in found[0]

    found = bypass_findings(LIVE_2026_08_28, {"bypass_actors": [OWNER_BYPASS, extra]})
    assert len(found) == 1, found
    assert "unreviewed bypass actor" in found[0]


def test_the_owner_losing_the_live_bypass_is_reported() -> None:
    """The incident itself. An empty bypass list coming back from the API is
    the owner locked out of their own repository, however tidy the committed
    file looks."""

    found = bypass_findings(
        {**LIVE_2026_08_28, "bypass_actors": []}, {"bypass_actors": [OWNER_BYPASS]}
    )
    assert len(found) == 1, found
    assert found[0].startswith("live ruleset:")
    assert "lockout" in found[0]


def test_both_sides_emptied_is_still_a_failure() -> None:
    """The case an equality check would pass, and the whole reason each side is
    judged on its own: a tidy revert of a committed file, on a day the owner had
    also been locked out, would otherwise report conformance on exactly the
    incident this guards. Two findings, not zero."""

    found = bypass_findings({**LIVE_2026_08_28, "bypass_actors": []}, {"bypass_actors": []})
    assert len(found) == 2, found
    assert any(line.startswith("live ruleset:") for line in found), found
    assert any(line.startswith("committed ruleset:") for line in found), found


def test_an_absent_field_is_not_read_as_no_one_bypasses() -> None:
    """A token without permission to read repository administration gets a
    reduced payload with `bypass_actors` omitted. Treating that as `[]` would
    be a verdict drawn from a field nothing read."""

    found = side_findings(
        "live ruleset", {k: v for k, v in LIVE_2026_08_28.items() if k != "bypass_actors"}
    )
    assert len(found) == 1, found
    assert "no `bypass_actors` field to read" in found[0]
    assert "has been verified" in found[0]


def test_a_committed_file_that_would_apply_the_lockout_is_reported(tmp_path: Path) -> None:
    """A file shaped like the pre-2026-08-28 ones, in the field that matters.
    Applying it is what the README documents, so the file itself has to be
    wrong-proof, not only the comparison."""

    emptied = tmp_path / "main.json"
    emptied.write_text(json.dumps({"name": "protect-main", "bypass_actors": []}), encoding="utf-8")

    found = committed_findings((emptied,))
    assert len(found) == 1, found
    assert "lockout" in found[0]


def test_the_cli_passes_against_the_repository_as_it_stands(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """End to end over the real committed files and the recorded live payload."""

    live = tmp_path / "live.json"
    live.write_text(json.dumps([LIVE_2026_08_28]), encoding="utf-8")

    assert main(["--live", str(live)]) == 0
    assert "pass" in capsys.readouterr().out


def test_the_cli_reports_the_lockout_and_exits_non_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    live = tmp_path / "live.json"
    live.write_text(json.dumps([{**LIVE_2026_08_28, "bypass_actors": []}]), encoding="utf-8")

    assert main(["--live", str(live)]) == 1
    assert "lockout" in capsys.readouterr().err


def test_the_documented_apply_step_carries_the_bypass_warning() -> None:
    """`docs/rulesets/README.md` publishes a `gh api -X POST --input` step. The
    warning beside it is the only thing standing between that instruction and
    the incident, so it is pinned rather than left to survive an edit."""

    readme = (ROOT / "docs" / "rulesets" / "README.md").read_text(encoding="utf-8")
    apply_step = readme.split("## Applying it")[1]
    assert "Check `bypass_actors` in the file before running that." in apply_step
    assert "Why the owner can bypass" in readme
    assert "no bypass actors" not in readme.split("## Why the owner can bypass")[0]
