"""Every published release must be on the index, and "cannot tell" is its own answer.

The defect this covers is issue #173, and its shape is worth restating because
the tests below are written against it rather than against the code: the job
that verifies publication was cancelled by the same stop that cancelled the
publish, so the check and the thing it checks shared a failure mode, and a
`cancelled` run is not a `failure`.

Everything here is written as literals. No fixture is derived from
`pyproject.toml`, from the live index, or from the checker's own output: a
fixture computed from the value it checks moves with that value and can never
catch a wrong one.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from scripts.check_release_reality import (
    OK,
    UNMEASURABLE,
    UNPUBLISHED,
    Unmeasurable,
    index_versions,
    main,
    missing_from_index,
    published_releases,
    version_of,
)

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "release-reality.yml"

#: The shape GitHub returns, reduced to the three fields this check reads.
RELEASES: list[dict[str, Any]] = [
    {"tag_name": "v0.2.0", "draft": False, "prerelease": False},
    {"tag_name": "v0.1.0", "draft": False, "prerelease": False},
]

#: The shape `https://pypi.org/simple/<name>/` returns under
#: `Accept: application/vnd.pypi.simple.v1+json`, reduced the same way. The
#: live document declared api-version 1.4 on 2026-09-09.
INDEX: dict[str, Any] = {"meta": {"api-version": "1.1"}, "versions": ["0.1.0", "0.2.0"]}


def _write(tmp_path: Path, releases: Any = RELEASES, index: Any = INDEX) -> tuple[Path, Path]:
    releases_path = tmp_path / "releases.json"
    index_path = tmp_path / "index.json"
    releases_path.write_text(
        releases if isinstance(releases, str) else json.dumps(releases), encoding="utf-8"
    )
    index_path.write_text(index if isinstance(index, str) else json.dumps(index), encoding="utf-8")
    return releases_path, index_path


def _run(tmp_path: Path, releases: Any = RELEASES, index: Any = INDEX) -> int:
    releases_path, index_path = _write(tmp_path, releases, index)
    return main(["--releases", str(releases_path), "--index", str(index_path)])


# -- the three outcomes ------------------------------------------------------


def test_an_index_serving_every_release_passes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _run(tmp_path) == OK
    assert "2 of 2 published release(s) are on the index" in capsys.readouterr().out


def test_the_state_this_check_was_written_for_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`main` on 2026-09-09: two published releases, one version on the index.

    Measured against the live APIs the same day and reproduced here as
    literals, because a test that fetched them would go green the moment the
    maintainer publishes and would then be checking nothing.
    """

    assert (
        _run(tmp_path, index={"meta": {"api-version": "1.1"}, "versions": ["0.1.0"]}) == UNPUBLISHED
    )
    reported = capsys.readouterr().err
    assert "1 of 2 published release(s) are on the index" in reported
    assert "v0.2.0" in reported
    assert "0.1.0 is not on the index" not in reported


def test_an_index_serving_nothing_reports_every_release_and_not_none(tmp_path: Path) -> None:
    """The vacuity check. A comparison that quietly examined no release would
    pass here, and it would look exactly like a healthy one."""

    assert missing_from_index(RELEASES, set()) == [
        "v0.2.0 was published as a GitHub release and version 0.2.0 is not on the index",
        "v0.1.0 was published as a GitHub release and version 0.1.0 is not on the index",
    ]


# -- unmeasurable, which is never a pass and never a finding ------------------


@pytest.mark.parametrize(
    ("releases", "index", "expected"),
    [
        pytest.param("", INDEX, "is empty", id="an empty releases file"),
        pytest.param(RELEASES, "", "is empty", id="an empty index file"),
        pytest.param("not json", INDEX, "is not JSON", id="releases that do not parse"),
        pytest.param(RELEASES, "not json", "is not JSON", id="an index that does not parse"),
        pytest.param({"releases": []}, INDEX, "is not a JSON array", id="releases as an object"),
        pytest.param(RELEASES, [], "is not a JSON object", id="an index as an array"),
        pytest.param([], INDEX, "lists no published release", id="an empty releases array"),
        pytest.param(
            [{"draft": True, "tag_name": "v9.9.9"}],
            INDEX,
            "lists no published release",
            id="only drafts",
        ),
        pytest.param(
            [{"name": "v0.1.0", "draft": False}], INDEX, "no tag_name", id="a release with no tag"
        ),
        pytest.param(
            [{"tag_name": "0.1.0", "draft": False}],
            INDEX,
            "is not the vX.Y.Z shape",
            id="a tag with no v",
        ),
        pytest.param(
            [{"tag_name": "v", "draft": False}],
            INDEX,
            "is not the vX.Y.Z shape",
            id="a tag that is only a v",
        ),
        pytest.param(
            RELEASES,
            {"versions": ["0.1.0", "0.2.0"]},
            "declares no meta.api-version",
            id="an index with no meta",
        ),
        pytest.param(
            RELEASES,
            {"meta": {"api-version": "2.0"}, "versions": ["0.1.0", "0.2.0"]},
            "declares simple-API version 2.0",
            id="an index contract this script does not read",
        ),
        pytest.param(
            RELEASES,
            {"meta": {"api-version": "1.1"}},
            "carries no `versions` list",
            id="an index with no versions",
        ),
        pytest.param(
            RELEASES,
            {"meta": {"api-version": "1.1"}, "versions": [1, 2]},
            "carries no `versions` list",
            id="versions that are not strings",
        ),
    ],
)
def test_a_document_this_check_cannot_read_is_not_a_pass(
    tmp_path: Path,
    releases: Any,
    index: Any,
    expected: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert _run(tmp_path, releases, index) == UNMEASURABLE
    reported = capsys.readouterr().err
    assert expected in reported
    assert "Unmeasurable is not a pass" in reported


def test_a_missing_file_is_unmeasurable_rather_than_a_crash(tmp_path: Path) -> None:
    assert (
        main(["--releases", str(tmp_path / "gone.json"), "--index", str(tmp_path / "gone.json")])
        == UNMEASURABLE
    )


def test_the_three_exit_codes_are_three_different_numbers() -> None:
    """`unpublished` and `unmeasurable` say different things and a caller has
    to be able to tell them apart; collapsing them would let a document nobody
    could read report a finding, or a finding report as an unreadable
    document."""

    assert len({OK, UNPUBLISHED, UNMEASURABLE}) == 3


# -- what is and is not compared ---------------------------------------------


def test_a_draft_release_is_not_expected_on_the_index(tmp_path: Path) -> None:
    """A draft has published nothing. It is excluded, and the run still has
    something to compare, so the exclusion cannot be what makes it pass."""

    releases = [*RELEASES, {"tag_name": "v0.3.0", "draft": True, "prerelease": False}]
    assert _run(tmp_path, releases) == OK
    assert [entry["tag_name"] for entry in published_releases(releases, Path("x"))] == [
        "v0.2.0",
        "v0.1.0",
    ]


def test_a_prerelease_is_compared_and_is_named_as_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A prerelease is published, so it is expected on the index. Excluding it
    would carve out exactly the class most likely to be forgotten."""

    releases = [{"tag_name": "v0.3.0", "draft": False, "prerelease": True}, *RELEASES]
    assert _run(tmp_path, releases) == UNPUBLISHED
    reported = capsys.readouterr().err
    assert "v0.3.0 was published as a GitHub release (prerelease) and version 0.3.0" in reported


def test_a_tag_that_cannot_be_read_stops_the_run_rather_than_being_skipped() -> None:
    """A release quietly left out of the comparison is a release this check
    says nothing about while appearing to have covered everything."""

    with pytest.raises(Unmeasurable):
        version_of("0.1.0")
    assert version_of("v0.1.0") == "0.1.0"


def test_the_index_reader_returns_the_served_set(tmp_path: Path) -> None:
    assert index_versions(INDEX, tmp_path) == {"0.1.0", "0.2.0"}
    with pytest.raises(Unmeasurable):
        index_versions("a string", tmp_path)


# -- the workflow that runs it -----------------------------------------------


def test_the_workflow_runs_this_checker() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "scripts/check_release_reality.py" in text
    assert "--releases releases.json" in text
    assert "--index index.json" in text


def test_the_workflow_reads_the_simple_api_and_not_the_project_page() -> None:
    """`https://pypi.org/project/<name>/` answers an automated caller with HTTP
    200 and a bot-detection page, so a check built on it cannot fail on a
    missing version — it fails on parsing, or worse, does not."""

    text = WORKFLOW.read_text(encoding="utf-8")
    # The exact URL that is fetched, not merely the host: the workflow's own
    # comment names the project page as the thing it does not use, so a
    # substring search for that host would match the explanation.
    assert '"https://pypi.org/simple/${DISTRIBUTION}/"' in text
    assert "application/vnd.pypi.simple.v1+json" in text
    assert "curl -fsS" in text, "without -f, an HTTP error body is written to the file and read"


def test_the_workflow_fetches_the_distribution_this_project_publishes() -> None:
    """The one hand-written string in the workflow that can go stale silently.

    A rename in `pyproject.toml` would leave this fetching a distribution that
    is not this one — and the index would answer for it, so the check would
    keep passing about the wrong package.
    """

    import tomllib

    declared = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    name = declared["project"]["name"]
    assert f"DISTRIBUTION: {name}" in WORKFLOW.read_text(encoding="utf-8")


def test_the_workflow_does_not_run_on_a_commit() -> None:
    """It is a statement about what has been published, not about a diff.

    It is expected to be red until a release reaches the index, so a
    `pull_request` or `push` trigger here would turn every branch red for a
    fact that has nothing to do with it.
    """

    text = WORKFLOW.read_text(encoding="utf-8")
    triggers = text.split("on:\n", 1)[1].split("\npermissions:", 1)[0]
    assert "schedule:" in triggers
    assert "workflow_dispatch:" in triggers
    assert "pull_request" not in triggers
    assert "push:" not in triggers
