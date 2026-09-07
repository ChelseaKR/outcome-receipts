#!/usr/bin/env python3
"""Check that everything in the tree that carries a version number agrees.

`tests/test_version.py` opens by saying the version is single-sourced from
package metadata "so a tagged release cannot ship a wheel, a CLI, and a tag
that disagree." It proves the first two: `outcome_receipts.__version__` is the
installed distribution's version, and `receipts --version` prints that. **The
tag is the one term in that sentence nothing compared against anything.**

That gap was live on 2026-09-07. `CHANGELOG.md` carried a dated
`## [0.2.1] - 2026-09-07` section, a signed `v0.2.1` tag existed, and
`pyproject.toml` still read `version = "0.2.0"` — the release-prep commit for
`v0.2.0` (`b8f5a27`) had moved the CHANGELOG *and* bumped every place carrying
the version together, and the promotion to `0.2.1` did only the first half.
Nothing was red. `make verify` passed, `ci` passed, and `release.yml`'s
`verify` job had one version check in it -- that `CHANGELOG.md` contains a
section for the tag -- which that tree satisfied.

What a `v0.2.1` dispatch would then have done is worth stating exactly,
because none of it fails early:

* `build` runs `uv build`, which reads `pyproject.toml`, and produces
  `outcome_receipts-0.2.0-*.whl`;
* Sigstore attests those bytes, and the GitHub release for `v0.2.1` is
  published carrying a `0.2.0` wheel;
* `pypi-publish` uploads it, and PyPI accepts it as version `0.2.0` -- a first
  upload, since PyPI has never seen `0.2.0`, so nothing rejects it;
* only then does `verify-published` run
  `uvx --from "outcome-receipts==0.2.1" receipts --help` and fail, on a version
  the index does not have and now never will, because the filename it did get
  is spent.

The gate that would have caught it therefore ran after the irreversible step.
This script moves that comparison to before the first one.

The invariant is the one `b8f5a27` followed by hand: **the version
`pyproject.toml` declares is the newest version `CHANGELOG.md` says was
released, `CITATION.cff` says the same, and `CITATION.cff`'s `date-released`
is that section's date.** So a CHANGELOG promotion that forgets the bump fails
here, and a bump that forgets the CHANGELOG fails here too.

Three outcomes, not two. A file that cannot be parsed for a version -- no
`project.version`, no dated CHANGELOG section, a `## [0.2.1] - not-a-date`
heading -- is **unmeasurable**, and unmeasurable fails. A check of this shape
that shrugged at a missing value would report agreement between two numbers it
never read.

`--tag vX.Y.Z` adds the release-time comparison: the tag being published must
name the version the tree declares. `release.yml` passes it; `make hygiene`
does not, because there is no tag at that point.

Reads the repository by default; `--root` exists so tests/test_release_version.py
drives the identical code path over fixtures.
"""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: A dated release heading, e.g. `## [0.2.1] - 2026-09-07`. `## [Unreleased]`
#: deliberately does not match: it is not a release, and treating it as one
#: would make every development tree look like it had shipped.
_RELEASE_HEADING = re.compile(r"^## \[(?P<version>[^\]]+)\]\s*-\s*(?P<released>\S+)\s*$")

#: `## [Unreleased]`, matched separately so a malformed dated heading below it
#: can be told apart from "this changelog has no releases yet".
_UNRELEASED_HEADING = re.compile(r"^## \[Unreleased\]\s*$", re.IGNORECASE)

#: Any level-2 heading, so a release heading that is *almost* right -- the date
#: dropped, or an en dash where the separator should be a hyphen -- is reported
#: as malformed rather than silently skipped in favour of an older section that
#: does parse. Skipping it would let a botched promotion pass by comparing
#: against the previous release.
_ANY_HEADING = re.compile(r"^## \[.*")

#: CITATION.cff is read line-wise rather than with a YAML parser: the file is
#: flat, the two fields are top-level scalars, and this script is a gate that
#: must not add a dependency the release path would have to resolve.
_CITATION_VERSION = re.compile(r'^version:\s*"?(?P<value>[^"\s]+)"?\s*$', re.MULTILINE)
_CITATION_RELEASED = re.compile(r'^date-released:\s*"?(?P<value>[^"\s]+)"?\s*$', re.MULTILINE)

#: The tag shape the release workflow accepts, per docs/RELEASING.md.
_TAG = re.compile(r"^v(?P<version>\d+\.\d+\.\d+)$")


def changelog_release(text: str) -> tuple[str | None, str | None, str | None]:
    """Return `(version, date, failure)` for the newest dated CHANGELOG section.

    Exactly one of the first pair or `failure` is populated. `## [Unreleased]`
    is skipped; the first level-2 heading after it must be a well-formed dated
    release heading, and anything else is a failure rather than a reason to
    keep looking further down the file.
    """

    for line in text.splitlines():
        if _UNRELEASED_HEADING.match(line):
            continue
        if not _ANY_HEADING.match(line):
            continue
        match = _RELEASE_HEADING.match(line)
        if match is None:
            return None, None, f"CHANGELOG.md's newest release heading is malformed: {line!r}"
        version = match.group("version")
        released = match.group("released")
        try:
            date.fromisoformat(released)
        except ValueError:
            return (
                None,
                None,
                f"CHANGELOG.md's {version} section has an unparseable date: {released!r}",
            )
        return version, released, None
    return None, None, "CHANGELOG.md declares no dated release section"


def pyproject_version(text: str) -> tuple[str | None, str | None]:
    """Return `(version, failure)` for `project.version` in a pyproject document."""

    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:  # pragma: no cover - defensive
        return None, f"pyproject.toml does not parse: {exc}"
    version = data.get("project", {}).get("version")
    if not isinstance(version, str) or not version:
        return None, "pyproject.toml declares no project.version"
    return version, None


def citation_fields(text: str) -> tuple[str | None, str | None, list[str]]:
    """Return `(version, date-released, failures)` for a CITATION.cff document."""

    failures: list[str] = []
    version_match = _CITATION_VERSION.search(text)
    released_match = _CITATION_RELEASED.search(text)
    if version_match is None:
        failures.append("CITATION.cff declares no version")
    if released_match is None:
        failures.append("CITATION.cff declares no date-released")
    return (
        version_match.group("value") if version_match else None,
        released_match.group("value") if released_match else None,
        failures,
    )


def version_failures(root: Path, tag: str | None = None) -> list[str]:
    """Every disagreement between the tree's version declarations."""

    failures: list[str] = []

    changelog_path = root / "CHANGELOG.md"
    pyproject_path = root / "pyproject.toml"
    citation_path = root / "CITATION.cff"
    for path in (changelog_path, pyproject_path, citation_path):
        if not path.is_file():
            failures.append(f"{path.name} is missing")
    if failures:
        return failures

    released_version, released_date, changelog_failure = changelog_release(
        changelog_path.read_text(encoding="utf-8")
    )
    if changelog_failure is not None:
        failures.append(changelog_failure)

    declared, pyproject_failure = pyproject_version(pyproject_path.read_text(encoding="utf-8"))
    if pyproject_failure is not None:
        failures.append(pyproject_failure)

    cited, cited_date, citation_failures = citation_fields(
        citation_path.read_text(encoding="utf-8")
    )
    failures.extend(citation_failures)

    # Every comparison below is guarded on both of its terms having been read.
    # An unreadable declaration has already been reported above as its own
    # failure; it must not also be compared as if it were a value.
    if released_version is not None and declared is not None and declared != released_version:
        failures.append(
            f"pyproject.toml declares version {declared}, but CHANGELOG.md's newest "
            f"released section is {released_version}. A release-prep commit moves both."
        )
    if released_version is not None and cited is not None and cited != released_version:
        failures.append(
            f"CITATION.cff declares version {cited}, but CHANGELOG.md's newest "
            f"released section is {released_version}."
        )
    if released_date is not None and cited_date is not None and cited_date != released_date:
        failures.append(
            f"CITATION.cff's date-released is {cited_date}, but CHANGELOG.md dates "
            f"that release {released_date}."
        )

    if tag is not None:
        failures.extend(tag_failures(tag, declared))

    return failures


def tag_failures(tag: str, declared: str | None) -> list[str]:
    """The release-time comparison: the tag must name what the wheel will carry."""

    tag_match = _TAG.match(tag)
    if tag_match is None:
        return [f"{tag!r} is not a stable vX.Y.Z release tag"]
    if declared is None or tag_match.group("version") == declared:
        return []
    return [
        f"the release tag is {tag}, but pyproject.toml declares version "
        f"{declared}. `uv build` reads pyproject.toml, so this run would "
        f"publish {declared} under the name {tag}."
    ]


def main(argv: list[str] | None = None) -> int:
    """Return nonzero when the tree's version declarations disagree."""

    parser = argparse.ArgumentParser(description="Check version declarations agree.")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument(
        "--tag",
        default=None,
        help="the release tag being published, for the release-time comparison",
    )
    args = parser.parse_args(argv)

    failures = version_failures(args.root, args.tag)
    if failures:
        print("release version parity failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1

    declared, _ = pyproject_version((args.root / "pyproject.toml").read_text(encoding="utf-8"))
    scope = f" and tag {args.tag}" if args.tag else ""
    print(
        f"release version parity: pyproject.toml, CITATION.cff, CHANGELOG.md{scope} agree on {declared}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
