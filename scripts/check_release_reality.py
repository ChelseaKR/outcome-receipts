#!/usr/bin/env python3
"""Check that every published GitHub release is actually on the package index.

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

So this check runs **from outside the release run**, on a schedule, and asks
one question of two facts that are both public: is every release this
repository has published present on the index? It needs no state, no
credential beyond a read token, and nothing from the run that published.

Three outcomes, and the third is the reason for the shape of the code.

* **ok** — every published release's version is on the index. Exit 0. The
  numbers behind it are printed, both of them: `N of M`.
* **released but unpublished** — at least one is not. Exit 1, naming every
  one.
* **unmeasurable** — a document did not parse, or carried no version list, or
  a release tag could not be read as a version. Exit 2. An input this script
  cannot read is never a pass, and an empty list is never read as "nothing to
  report": that is the failure this whole repository is about, and a release
  checker that shrugged at a listing it could not read would be committing it
  in its own release path.

Both documents are supplied as files rather than fetched here. The workflow
fetches them, so a failed fetch fails the step in the fetcher's own words and
with its own status code, and this script stays a pure function of two inputs
that `tests/test_release_reality.py` drives over fixtures.

The index document is the PEP 691 JSON simple API
(`https://pypi.org/simple/<name>/` with
`Accept: application/vnd.pypi.simple.v1+json`), which carries a `versions`
array under PEP 700. **Not** `https://pypi.org/project/<name>/`, which returns
HTTP 200 with a bot-detection page for an automated caller, and **not**
`/pypi/<name>/json`, whose `info.version` is one number where the question is
about a set.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

#: Exit codes. `UNMEASURABLE` is deliberately distinct from `UNPUBLISHED`: one
#: says a release is missing from the index, the other says this run could not
#: tell, and collapsing them would let an unreadable document read as a
#: finding — or, worse the other way, as a clean run.
OK = 0
UNPUBLISHED = 1
UNMEASURABLE = 2

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


def missing_from_index(releases: list[dict[str, Any]], served: set[str]) -> list[str]:
    """The published releases the index does not serve, in the order listed."""

    return [
        f"{entry['tag_name']} was published as a GitHub release "
        f"{'(prerelease) ' if entry.get('prerelease') is True else ''}"
        f"and version {version_of(str(entry['tag_name']))} is not on the index"
        for entry in releases
        if version_of(str(entry["tag_name"])) not in served
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check every published GitHub release is on the package index."
    )
    parser.add_argument(
        "--releases",
        type=Path,
        required=True,
        help="a JSON array as returned by GET /repos/{owner}/{repo}/releases",
    )
    parser.add_argument(
        "--index",
        type=Path,
        required=True,
        help="the PEP 691 simple-API JSON document for this distribution",
    )
    args = parser.parse_args(argv)

    try:
        releases = published_releases(_load(args.releases, "the releases document"), args.releases)
        served = index_versions(_load(args.index, "the index document"), args.index)
        missing = missing_from_index(releases, served)
    except Unmeasurable as exc:
        print(f"release reality is unmeasurable: {exc}", file=sys.stderr)
        print(
            "Unmeasurable is not a pass. Nothing here says the index is behind, and "
            "nothing here says it is not.",
            file=sys.stderr,
        )
        return UNMEASURABLE

    compared = len(releases)
    if missing:
        print(
            f"{compared - len(missing)} of {compared} published release(s) are on the index:",
            file=sys.stderr,
        )
        for line in missing:
            print(f"- {line}", file=sys.stderr)
        print(
            "\nThis is the state issue #173 records; it is not a defect in this commit. "
            "A release run that published the GitHub release and then stopped at the "
            "`pypi` environment's required review leaves exactly this, and the job that "
            "would have reported it was cancelled by the same stop. Publishing is the "
            "maintainer's; this check only refuses to let the gap be silent.",
            file=sys.stderr,
        )
        return UNPUBLISHED

    print(f"{compared} of {compared} published release(s) are on the index.")
    print(f"index serves: {', '.join(sorted(served))}")
    return OK


if __name__ == "__main__":  # pragma: no cover - exercised through main() in tests
    raise SystemExit(main())
