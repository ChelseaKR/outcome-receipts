"""A release travels three links, and "cannot tell" is its own answer at each one.

The defect this covers is issue #173, and its shape is worth restating because
the tests below are written against it rather than against the code: the job
that verifies publication was cancelled by the same stop that cancelled the
publish, so the check and the thing it checks shared a failure mode, and a
`cancelled` run is not a `failure`.

Measured across this portfolio on 2026-09-09: 43 repositories have release or
publish CI, 21 have ever published a release, and 22 have the machinery and
have never once produced one. So the checks here are aimed at the links, not
at the machinery — and each link asserts its own denominator, because a link
that examined nothing reads exactly like a link that held.

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
    STALLED,
    UNMEASURABLE,
    Unmeasurable,
    changelog_has_a_tag,
    index_versions,
    main,
    published_releases,
    release_tags,
    releases_are_on_the_index,
    tags_have_a_release,
    version_of,
)

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "release-reality.yml"

#: The shape GitHub returns from /releases, reduced to the fields this check
#: reads. `assets` is carried on one of them and read by nothing, deliberately:
#: see `test_a_release_with_no_assets_is_not_a_failed_release`.
RELEASES: list[dict[str, Any]] = [
    {"tag_name": "v0.2.0", "draft": False, "prerelease": False, "assets": [{"name": "x.whl"}]},
    {"tag_name": "v0.1.0", "draft": False, "prerelease": False, "assets": []},
]

#: The shape GitHub returns from /tags.
TAGS: list[dict[str, Any]] = [{"name": "v0.2.0"}, {"name": "v0.1.0"}]

#: The shape `https://pypi.org/simple/<name>/` returns under
#: `Accept: application/vnd.pypi.simple.v1+json`. The live document declared
#: api-version 1.4 on 2026-09-09.
INDEX: dict[str, Any] = {"meta": {"api-version": "1.1"}, "versions": ["0.1.0", "0.2.0"]}

#: A changelog whose newest dated section names the newest tag.
CHANGELOG = "# Changelog\n\n## [Unreleased]\n\n## [0.2.0] - 2026-08-16\n\n### Added\n- A thing.\n"


def _write(tmp_path: Path, name: str, payload: Any) -> Path:
    path = tmp_path / name
    path.write_text(payload if isinstance(payload, str) else json.dumps(payload), encoding="utf-8")
    return path


def _run(
    tmp_path: Path,
    releases: Any = RELEASES,
    tags: Any = TAGS,
    index: Any = INDEX,
    changelog: Any = CHANGELOG,
) -> int:
    return main(
        [
            "--releases",
            str(_write(tmp_path, "releases.json", releases)),
            "--tags",
            str(_write(tmp_path, "tags.json", tags)),
            "--index",
            str(_write(tmp_path, "index.json", index)),
            "--changelog",
            str(_write(tmp_path, "CHANGELOG.md", changelog)),
        ]
    )


# -- the whole chain ---------------------------------------------------------


def test_an_intact_chain_passes_and_prints_every_denominator(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _run(tmp_path) == OK
    reported = capsys.readouterr().out
    assert "1 of 1 changelog release(s) have a tag" in reported
    assert "2 of 2 stable tag(s) have a release" in reported
    assert "2 of 2 published release(s) are on the index" in reported


def test_the_state_this_check_was_written_for_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`main` on 2026-09-09, measured against the live APIs and reproduced as
    literals: three tags, two releases, one version on the index, and a
    changelog whose newest dated section is `0.2.1`.

    Reproduced rather than fetched, because a test that fetched would go green
    the moment the maintainer publishes and would then be checking nothing.
    """

    assert (
        _run(
            tmp_path,
            tags=[{"name": "v0.2.1"}, *TAGS],
            index={"meta": {"api-version": "1.1"}, "versions": ["0.1.0"]},
            changelog="# Changelog\n\n## [Unreleased]\n\n## [0.2.1] - 2026-09-07\n\n- A thing.\n",
        )
        == STALLED
    )
    reported = capsys.readouterr().err
    assert "1 of 1 changelog release(s) have a tag" in reported
    assert "2 of 3 stable tag(s) have a release" in reported
    assert "1 of 2 published release(s) are on the index" in reported
    assert "tag v0.2.1 exists and no GitHub release was published for it" in reported
    assert "v0.2.0 was published as a GitHub release and version 0.2.0 is not on the index" in (
        reported
    )


def test_the_three_exit_codes_are_three_different_numbers() -> None:
    """`stalled` and `unmeasurable` say different things and a caller has to be
    able to tell them apart; collapsing them would let a document nobody could
    read report a finding, or a finding report as an unreadable document."""

    assert len({OK, STALLED, UNMEASURABLE}) == 3


# -- link 1: a dated changelog section must have a tag ------------------------


def test_a_changelog_version_is_not_a_fetchable_tag(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Measured elsewhere in this portfolio: a `1.5.0` section dated
    2026-08-18 with no tag at all, so a pin written against it resolves to
    nothing. A check that reads only the changelog passes over that."""

    assert (
        _run(
            tmp_path,
            changelog="# Changelog\n\n## [Unreleased]\n\n## [1.5.0] - 2026-08-18\n\n- A thing.\n",
        )
        == STALLED
    )
    reported = capsys.readouterr().err
    assert "0 of 1 changelog release(s) have a tag" in reported
    assert "CHANGELOG.md dates a 1.5.0 release and no tag names it" in reported


def test_a_changelog_with_no_dated_release_is_unmeasurable(tmp_path: Path) -> None:
    assert _run(tmp_path, changelog="# Changelog\n\n## [Unreleased]\n\n- pending\n") == UNMEASURABLE


def test_the_changelog_reader_is_the_one_the_release_gate_already_uses() -> None:
    """Two readers of one file drift, and the other one is merge-blocking."""

    from scripts import check_release_reality, check_release_version

    assert check_release_reality.changelog_release is check_release_version.changelog_release
    assert "changelog_release" in check_release_reality.__all__


# -- link 2: a stable tag must have a published release -----------------------


def test_a_tag_publishes_nothing_on_its_own(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _run(tmp_path, tags=[{"name": "v9.9.9"}, *TAGS]) == STALLED
    reported = capsys.readouterr().err
    assert "2 of 3 stable tag(s) have a release" in reported
    assert "tag v9.9.9 exists and no GitHub release was published for it" in reported


def test_a_tag_that_is_not_the_release_shape_is_not_expected_to_have_one(tmp_path: Path) -> None:
    """`docs/RELEASING.md` fixes the shape at `vX.Y.Z`. A `nightly` ref is not
    a release that stalled, and the run still has stable tags to compare, so
    the exclusion cannot be what makes it pass."""

    assert _run(tmp_path, tags=[{"name": "nightly"}, *TAGS]) == OK
    link = tags_have_a_release(["nightly", "v0.2.0", "v0.1.0"], RELEASES)
    assert (link.held, link.examined) == (2, 2)


def test_a_listing_with_no_stable_tag_is_unmeasurable() -> None:
    """Nothing to examine is not agreement."""

    with pytest.raises(Unmeasurable):
        tags_have_a_release(["nightly"], RELEASES)


# -- link 3: a published release must be on the index -------------------------


def test_an_index_serving_nothing_reports_every_release_and_not_none() -> None:
    """The vacuity check. A comparison that quietly examined no release would
    pass here, and it would look exactly like a healthy one."""

    link = releases_are_on_the_index(RELEASES, set())
    assert (link.held, link.examined) == (0, 2)
    assert len(link.broken) == 2


def test_a_release_with_no_assets_is_not_a_failed_release(tmp_path: Path) -> None:
    """Measured in this portfolio: `ca-tariff-parse` v0.3.0 and
    `power-content-check` v0.1.0 are real releases with zero assets, correct in
    both cases because their workflows publish source-only releases. A check
    that assumed assets would report both as broken.

    `v0.1.0` in the fixture carries `assets: []` and this passes, so the
    absence of an artifact is provably not part of any verdict.
    """

    assert RELEASES[1]["assets"] == []
    assert _run(tmp_path) == OK


def test_a_draft_release_is_not_expected_on_the_index(tmp_path: Path) -> None:
    """A draft has published nothing. It is excluded, and the run still has
    something to compare, so the exclusion cannot be what makes it pass."""

    releases = [*RELEASES, {"tag_name": "v0.3.0", "draft": True, "prerelease": False}]
    assert _run(tmp_path, releases, tags=[{"name": "v0.3.0"}, *TAGS]) == STALLED
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
    assert _run(tmp_path, releases, tags=[{"name": "v0.3.0"}, *TAGS]) == STALLED
    reported = capsys.readouterr().err
    assert "v0.3.0 was published as a GitHub release (prerelease) and version 0.3.0" in reported


# -- unmeasurable, which is never a pass and never a finding ------------------


@pytest.mark.parametrize(
    ("releases", "tags", "index", "expected"),
    [
        pytest.param("", TAGS, INDEX, "is empty", id="an empty releases file"),
        pytest.param(RELEASES, "", INDEX, "is empty", id="an empty tags file"),
        pytest.param(RELEASES, TAGS, "", "is empty", id="an empty index file"),
        pytest.param("not json", TAGS, INDEX, "is not JSON", id="releases that do not parse"),
        pytest.param(RELEASES, "not json", INDEX, "is not JSON", id="tags that do not parse"),
        pytest.param(RELEASES, TAGS, "not json", "is not JSON", id="an index that does not parse"),
        pytest.param(
            {"releases": []}, TAGS, INDEX, "is not a JSON array", id="releases as an object"
        ),
        pytest.param(RELEASES, {"tags": []}, INDEX, "is not a JSON array", id="tags as an object"),
        pytest.param(RELEASES, TAGS, [], "is not a JSON object", id="an index as an array"),
        pytest.param([], TAGS, INDEX, "lists no published release", id="an empty releases array"),
        pytest.param(RELEASES, [], INDEX, "lists no tag", id="an empty tags array"),
        pytest.param(
            [{"draft": True, "tag_name": "v9.9.9"}],
            TAGS,
            INDEX,
            "lists no published release",
            id="only drafts",
        ),
        pytest.param(
            [{"name": "v0.1.0", "draft": False}],
            TAGS,
            INDEX,
            "no tag_name",
            id="a release with no tag",
        ),
        pytest.param(RELEASES, [{"tag": "v0.1.0"}], INDEX, "no name", id="a tag with no name"),
        pytest.param(
            [{"tag_name": "0.1.0", "draft": False}],
            TAGS,
            INDEX,
            "is not the vX.Y.Z shape",
            id="a release tag with no v",
        ),
        pytest.param(
            [{"tag_name": "v", "draft": False}],
            TAGS,
            INDEX,
            "is not the vX.Y.Z shape",
            id="a release tag that is only a v",
        ),
        pytest.param(
            RELEASES,
            TAGS,
            {"versions": ["0.1.0", "0.2.0"]},
            "declares no meta.api-version",
            id="an index with no meta",
        ),
        pytest.param(
            RELEASES,
            TAGS,
            {"meta": {"api-version": "2.0"}, "versions": ["0.1.0"]},
            "declares simple-API version 2.0",
            id="an index contract this script does not read",
        ),
        pytest.param(
            RELEASES,
            TAGS,
            {"meta": {"api-version": "1.1"}},
            "carries no `versions` list",
            id="an index with no versions",
        ),
        pytest.param(
            RELEASES,
            TAGS,
            {"meta": {"api-version": "1.1"}, "versions": [1, 2]},
            "carries no `versions` list",
            id="versions that are not strings",
        ),
    ],
)
def test_a_document_this_check_cannot_read_is_not_a_pass(
    tmp_path: Path,
    releases: Any,
    tags: Any,
    index: Any,
    expected: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert _run(tmp_path, releases, tags, index) == UNMEASURABLE
    reported = capsys.readouterr().err
    assert expected in reported
    assert "Unmeasurable is not a pass" in reported


def test_a_missing_file_is_unmeasurable_rather_than_a_crash(tmp_path: Path) -> None:
    gone = str(tmp_path / "gone.json")
    assert (
        main(["--releases", gone, "--tags", gone, "--index", gone, "--changelog", gone])
        == UNMEASURABLE
    )


def test_a_tag_that_cannot_be_read_stops_the_run_rather_than_being_skipped() -> None:
    """A release quietly left out of a comparison is a release this check says
    nothing about while appearing to have covered everything."""

    with pytest.raises(Unmeasurable):
        version_of("0.1.0")
    assert version_of("v0.1.0") == "0.1.0"


def test_the_readers_return_what_they_read(tmp_path: Path) -> None:
    assert index_versions(INDEX, tmp_path) == {"0.1.0", "0.2.0"}
    assert release_tags(TAGS, tmp_path) == ["v0.2.0", "v0.1.0"]
    assert changelog_has_a_tag(CHANGELOG, ["v0.2.0"], tmp_path).broken == []
    with pytest.raises(Unmeasurable):
        index_versions("a string", tmp_path)


# -- the workflow that runs it -----------------------------------------------


def test_the_workflow_runs_this_checker_over_every_link() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "scripts/check_release_reality.py" in text
    for flag in ("--releases releases.json", "--tags tags.json", "--index index.json"):
        assert flag in text
    assert "--changelog CHANGELOG.md" in text


def test_the_workflow_reads_the_simple_api_and_not_the_project_page() -> None:
    """`https://pypi.org/project/<name>/` answers an automated caller with HTTP
    200 and a bot-detection page, so a check built on it cannot fail on a
    missing version — it fails on parsing, or worse, does not. A 404 from
    `/simple/` is how absence is reported, and `curl -f` is what turns that
    into a failed step instead of an error page written to the file."""

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
