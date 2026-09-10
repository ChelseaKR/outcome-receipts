#!/usr/bin/env python3
"""Follow a release all the way from the changelog to the index, and say where it stopped.

`v0.2.0` was cut on 2026-08-16 as a signed GitHub release with its full
attested asset set, and it is not on PyPI. The run that cut it did not fail:
`authorize`, `verify`, `build` and `github-release` all succeeded, then
`pypi-publish` — which declares `environment: pypi`, the one environment in
this portfolio with a real `required_reviewers` rule — sat at *Waiting for
review* for thirteen days and was cancelled. `verify-published` was cancelled
with it.

That is the shape this script exists for, and issue #173 states it in one
sentence: **the check and the thing it checks shared a failure mode.** A
post-publication verification that only runs when publication succeeded cannot
report that publication did not happen, and a run whose conclusion is
`cancelled` is not `failure`, so nothing alerted. Nine days later the gap was
found by a portfolio-wide sweep rather than by anything in this repository.

So this runs **from outside the release run**, on a schedule, over documents
that are all public. It needs no state, no credential beyond a read token, and
nothing from the run that published.

## Three links, because a release can stop at any of them

Measured across this portfolio on 2026-09-09: **43 repositories have release
or publish CI, 21 have ever published a release, and 22 have the machinery and
have never once produced one.** So *"the workflow exists"* is worth nothing as
a signal, and neither is any single link in the chain:

1. **the changelog names a version → a tag names that version.** A dated
   `## [X.Y.Z]` section is a claim that X.Y.Z was released. Elsewhere in this
   portfolio a `1.5.0` section dated 2026-08-18 has no tag at all, so a pin
   written against it resolves to nothing. A check that reads only the
   changelog passes over that.
2. **a tag → a published GitHub release.** A tag is a ref; it publishes
   nothing on its own. In this repository `release.yml` is dispatch-only, so a
   pushed tag with no dispatch is exactly a release that stopped here.
3. **a published release → the package index.** This is where `v0.2.0`
   stopped.

Each link is reported with both of its numbers, `N of M`, so a link that
examined nothing cannot read like a link that passed.

**Assets are deliberately not part of any verdict.** A published release with
zero assets is not a failed release: two repositories here publish
source-only releases on purpose, and a check that assumed assets would report
both as broken. What is being followed is the version, not the artifact.

## Three outcomes, and the third is the reason for the shape of the code

* **ok** — every link holds. Exit 0, with each link's numbers printed.
* **stalled** — a link does not. Exit 1, naming which link and which version.
* **unmeasurable** — a document did not parse, carried no version list,
  declared a contract this script does not read, or held a tag it could not
  read as a version. Exit 2. An input this script cannot read is never a pass,
  and an empty list is never read as "nothing to report": that is the failure
  this whole repository is about, and a release checker that shrugged at a
  listing it could not read would be committing it in its own release path.

Every document is supplied as a file rather than fetched here. The workflow
fetches them, so a failed fetch fails the step in the fetcher's own words and
with its own status code, and this script stays a pure function of its inputs
that `tests/test_release_reality.py` drives over fixtures.

The index document is the PEP 691 JSON simple API
(`https://pypi.org/simple/<name>/` with
`Accept: application/vnd.pypi.simple.v1+json`), which carries a `versions`
array under PEP 700. **Not** `https://pypi.org/project/<name>/`, which returns
HTTP 200 with a bot-detection page for an automated caller, and **not**
`/pypi/<name>/json`, whose `info.version` is one number where the question is
about a set.

The changelog is parsed by `check_release_version.changelog_release`, imported
rather than reimplemented: two readers of one file drift, and the other one is
already a merge-blocking gate.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

# The changelog reader is imported, not reimplemented. `make release-version`
# already gates on it, and two readers of one file drift.
#
# `scripts/` is run as top-level modules by the workflows (`python3
# scripts/check_release_reality.py`) and imported as `scripts.<name>` by the
# test suite, so both spellings have to work at run time. Only the first is
# visible to a type checker: importing both statically makes mypy see one file
# under two module names, which is the collision the Makefile's two separate
# mypy invocations exist for.
if TYPE_CHECKING:
    from check_release_version import changelog_release
else:
    try:
        from check_release_version import changelog_release
    except ModuleNotFoundError:
        from scripts.check_release_version import changelog_release

#: Exit codes. `UNMEASURABLE` is deliberately distinct from `STALLED`: one says
#: a release stopped at a link, the other says this run could not tell, and
#: collapsing them would let an unreadable document read as a finding — or,
#: worse the other way, as a clean run.
OK = 0
STALLED = 1
UNMEASURABLE = 2

#: A stable release tag, the shape `docs/RELEASING.md` and
#: `scripts/check_release_version.py` both fix.
_TAG = re.compile(r"^v(?P<version>\d+\.\d+\.\d+)$")

#: The simple-API major this script knows how to read. PEP 700 added
#: `versions` in 1.1; a document declaring a different major is refused rather
#: than read on a guess, for the same reason `tools/action_runner.py` refuses a
#: report schema it does not know.
SUPPORTED_API_MAJOR = "1"


class Unmeasurable(Exception):
    """This run could not decide. Never a pass, and never a finding either."""


def _load(path: Path, what: str) -> Any:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise Unmeasurable(f"{what} could not be read from {path}: {exc}") from exc
    if not text.strip():
        raise Unmeasurable(
            f"{what} at {path} is empty. An empty file is not an empty answer: the fetch "
            f"that wrote it may have produced nothing at all."
        )
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise Unmeasurable(f"{what} at {path} is not JSON: {exc}") from exc


def index_versions(document: Any, path: Path) -> set[str]:
    """Every version the index serves, from a PEP 691/700 simple-API document."""

    if not isinstance(document, dict):
        raise Unmeasurable(f"the index document at {path} is not a JSON object")
    meta = document.get("meta")
    if not isinstance(meta, dict) or not isinstance(meta.get("api-version"), str):
        raise Unmeasurable(
            f"the index document at {path} declares no meta.api-version, so this script "
            f"cannot tell which contract it is reading"
        )
    declared = str(meta["api-version"])
    if declared.split(".")[0] != SUPPORTED_API_MAJOR:
        raise Unmeasurable(
            f"the index document at {path} declares simple-API version {declared}, and this "
            f"script reads {SUPPORTED_API_MAJOR}.x"
        )
    versions = document.get("versions")
    if not isinstance(versions, list) or not all(isinstance(v, str) for v in versions):
        raise Unmeasurable(
            f"the index document at {path} carries no `versions` list. PEP 700 adds it at "
            f"simple-API 1.1; without it this script would have to infer the served set "
            f"from filenames, and an inference is not a measurement"
        )
    return {str(version) for version in versions}


def version_of(tag: str) -> str:
    """The distribution version a release tag names.

    `docs/RELEASING.md` and `scripts/check_release_version.py` both fix the tag
    shape at `vX.Y.Z`, so the mapping is stripping one leading `v`. A tag this
    cannot read is raised rather than skipped: a release quietly left out of
    the comparison is a release this check reports nothing about while
    appearing to have covered everything.
    """

    if not tag.startswith("v") or not tag[1:]:
        raise Unmeasurable(
            f"release tag {tag!r} is not the vX.Y.Z shape docs/RELEASING.md fixes, so the "
            f"version it publishes cannot be read from it"
        )
    return tag[1:]


def published_releases(document: Any, path: Path) -> list[dict[str, Any]]:
    """Every release that is not a draft, from a GitHub releases listing.

    A draft is excluded because it has published nothing and is not expected on
    the index. A prerelease is **not** excluded: it is published, it is
    expected on the index, and excluding it would carve out exactly the class
    of release most likely to be forgotten.

    A listing with no releases at all is unmeasurable rather than clean. This
    check's only pass means "every release is on the index", and over an empty
    set that sentence is true of a repository that has published two releases
    and of a listing that lost them both.
    """

    if not isinstance(document, list):
        raise Unmeasurable(f"the releases document at {path} is not a JSON array")
    releases = []
    for entry in document:
        if not isinstance(entry, dict) or not isinstance(entry.get("tag_name"), str):
            raise Unmeasurable(f"a release in {path} carries no tag_name this script can read")
        if entry.get("draft") is True:
            continue
        releases.append(entry)
    if not releases:
        raise Unmeasurable(
            f"the releases document at {path} lists no published release. That is not the "
            f"same as every release being on the index, and this check must not report it "
            f"as if it were"
        )
    return releases


def release_tags(document: Any, path: Path) -> list[str]:
    """Every stable release tag, from a GitHub tag listing.

    A tag that is not the `vX.Y.Z` shape is raised rather than skipped, for the
    reason ``version_of`` gives: a ref quietly left out of a comparison is a
    ref this check says nothing about while appearing to have covered
    everything.

    An empty listing is unmeasurable. A repository with no tags has nothing for
    this link to be about, and "no tag is missing a release" is true of that
    repository and of a listing that lost them all.
    """

    if not isinstance(document, list):
        raise Unmeasurable(f"the tags document at {path} is not a JSON array")
    tags = []
    for entry in document:
        if not isinstance(entry, dict) or not isinstance(entry.get("name"), str):
            raise Unmeasurable(f"a tag in {path} carries no name this script can read")
        tags.append(str(entry["name"]))
    if not tags:
        raise Unmeasurable(
            f"the tags document at {path} lists no tag. That is not the same as every "
            f"tag having a release, and this check must not report it as if it were"
        )
    return tags


#: One link in the chain: what it is called, how many of its population held,
#: how many there were, and the ones that did not, spelled out.
class Link:
    def __init__(self, name: str, held: int, examined: int, broken: list[str]) -> None:
        self.name = name
        self.held = held
        self.examined = examined
        self.broken = broken

    def render(self) -> str:
        return f"{self.held} of {self.examined} {self.name}"


def changelog_has_a_tag(changelog: str, tags: list[str], path: Path) -> Link:
    """Link 1: the version the changelog says was released has a tag.

    Only the newest dated section, because that is the one a reader acts on and
    the one `check_release_version.py` already holds the manifest to. An older
    section whose tag was never cut is history this check cannot repair.
    """

    version, _released, failure = changelog_release(changelog)
    if failure is not None or version is None:
        raise Unmeasurable(f"{path}: {failure or 'no dated release section was read'}")
    broken = (
        []
        if f"v{version}" in tags
        else [
            f"CHANGELOG.md dates a {version} release and no tag names it. A dated section "
            f"is a claim that the version shipped, and a pin written against it resolves "
            f"to nothing"
        ]
    )
    return Link("changelog release(s) have a tag", 1 - len(broken), 1, broken)


def tags_have_a_release(tags: list[str], releases: list[dict[str, Any]]) -> Link:
    """Link 2: a stable tag has a published GitHub release.

    A tag is a ref and publishes nothing on its own. `release.yml` here is
    dispatch-only — `docs/RELEASING.md` says pushing the tag alone starts
    nothing — so a tag with no release is a release that stopped at this link.
    """

    stable = [tag for tag in tags if _TAG.match(tag)]
    if not stable:
        raise Unmeasurable(
            f"none of the {len(tags)} tag(s) is the stable vX.Y.Z shape, so this link has "
            f"nothing to examine and must not report that as agreement"
        )
    released = {str(entry["tag_name"]) for entry in releases}
    broken = [
        f"tag {tag} exists and no GitHub release was published for it. Pushing a tag "
        f"starts nothing here; the release is a separate dispatch"
        for tag in stable
        if tag not in released
    ]
    return Link("stable tag(s) have a release", len(stable) - len(broken), len(stable), broken)


def releases_are_on_the_index(releases: list[dict[str, Any]], served: set[str]) -> Link:
    """Link 3: a published GitHub release's version is on the package index.

    Assets are deliberately not read. A release with none is not a failed
    release — two repositories in this portfolio publish source-only releases
    on purpose — and what is being followed here is the version, not the
    artifact.
    """

    broken = [
        f"{entry['tag_name']} was published as a GitHub release "
        f"{'(prerelease) ' if entry.get('prerelease') is True else ''}"
        f"and version {version_of(str(entry['tag_name']))} is not on the index"
        for entry in releases
        if version_of(str(entry["tag_name"])) not in served
    ]
    return Link(
        "published release(s) are on the index", len(releases) - len(broken), len(releases), broken
    )


def links(
    changelog: str,
    changelog_path: Path,
    tags: list[str],
    releases: list[dict[str, Any]],
    served: set[str],
) -> list[Link]:
    """Every link, in the order a release travels them."""

    return [
        changelog_has_a_tag(changelog, tags, changelog_path),
        tags_have_a_release(tags, releases),
        releases_are_on_the_index(releases, served),
    ]


def _read_text(path: Path, what: str) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise Unmeasurable(f"{what} could not be read from {path}: {exc}") from exc
    if not text.strip():
        raise Unmeasurable(f"{what} at {path} is empty")
    return text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Follow a release from the changelog to the package index."
    )
    parser.add_argument(
        "--releases",
        type=Path,
        required=True,
        help="a JSON array as returned by GET /repos/{owner}/{repo}/releases",
    )
    parser.add_argument(
        "--tags",
        type=Path,
        required=True,
        help="a JSON array as returned by GET /repos/{owner}/{repo}/tags",
    )
    parser.add_argument(
        "--index",
        type=Path,
        required=True,
        help="the PEP 691 simple-API JSON document for this distribution",
    )
    parser.add_argument(
        "--changelog",
        type=Path,
        required=True,
        help="CHANGELOG.md, read by check_release_version.changelog_release",
    )
    args = parser.parse_args(argv)

    try:
        chain = links(
            _read_text(args.changelog, "the changelog"),
            args.changelog,
            release_tags(_load(args.tags, "the tags document"), args.tags),
            published_releases(_load(args.releases, "the releases document"), args.releases),
            index_versions(_load(args.index, "the index document"), args.index),
        )
    except Unmeasurable as exc:
        print(f"release reality is unmeasurable: {exc}", file=sys.stderr)
        print(
            "Unmeasurable is not a pass. Nothing here says a release stalled, and nothing "
            "here says one did not.",
            file=sys.stderr,
        )
        return UNMEASURABLE

    broken = [line for link in chain for line in link.broken]
    where = sys.stderr if broken else sys.stdout
    for link in chain:
        print(link.render(), file=where)
    if not broken:
        return OK

    print("", file=sys.stderr)
    for line in broken:
        print(f"- {line}", file=sys.stderr)
    print(
        "\nThis is the state issue #173 records; it is not a defect in this commit. A "
        "release run that published the GitHub release and then stopped at the `pypi` "
        "environment's required review leaves exactly this, and the job that would have "
        "reported it was cancelled by the same stop. Tagging and publishing are the "
        "maintainer's; this check only refuses to let a stall be silent.",
        file=sys.stderr,
    )
    return STALLED


if __name__ == "__main__":  # pragma: no cover - exercised through main() in tests
    raise SystemExit(main())


#: `changelog_release` is re-exported on purpose: it is the reader
#: `make release-version` already gates on, and
#: `tests/test_release_reality.py` asserts the two names are the same object
#: so a second copy cannot appear here unnoticed.
__all__ = [
    "OK",
    "STALLED",
    "UNMEASURABLE",
    "Link",
    "Unmeasurable",
    "changelog_has_a_tag",
    "changelog_release",
    "index_versions",
    "links",
    "main",
    "published_releases",
    "release_tags",
    "releases_are_on_the_index",
    "tags_have_a_release",
    "version_of",
]
