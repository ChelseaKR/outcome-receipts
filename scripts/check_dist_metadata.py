#!/usr/bin/env python3
"""Check that the built distributions say what PyPI is supposed to show.

`check_release_version.py` next door moved one comparison earlier than the
irreversible step: it fails before `uv build` when the version the wheel would
carry is not the version being tagged. This is the same argument applied one
layer out. That script, and every other gate in this repository, reads
`pyproject.toml`. PyPI reads the *artifact*, and the two are not the same thing.

Two pieces of evidence, both from this portfolio, both from this month:

* `outcome-receipts` 0.2.2 was published on 2026-09-13 with a `License:` field
  containing the entire 201-line Apache 2.0 text, because `license` was
  declared as `{ file = "LICENSE" }` and hatchling resolves that form by
  inlining the file. Every gate was green through that release.
* `gauntlet-evals` 0.2.0 shipped with no `Project-URL` lines **at all** while
  `pyproject.toml` on the default branch declared four of them, because the
  release built from a tag cut before that change merged. Source-level checks
  could not see it; it took a 0.3.0 to fix.

So this reads the wheel's `dist-info/METADATA` and the sdist's `PKG-INFO`, and
consults `pyproject.toml` for exactly two values -- the expected version and the
expected Python floor -- which it then asserts *against* the artifact, so that a
stale build fails here rather than passing quietly.

Standard library only, and no project environment: it runs from `make verify`
locally and from the release workflow's `build` job, which has neither `.venv`
nor the project installed.

Usage::

    python3 scripts/check_dist_metadata.py dist
    python3 scripts/check_dist_metadata.py dist --wheel-only
"""

from __future__ import annotations

import argparse
import email.parser
import email.policy
import re
import sys
import tarfile
import tomllib
import zipfile
from dataclasses import dataclass
from email.message import Message
from pathlib import Path

DISTRIBUTION = "outcome-receipts"
LICENSE_EXPRESSION = "Apache-2.0"
REQUIRED_URL_LABELS = ("Homepage", "Repository", "Documentation", "Issues", "Changelog")
REPO_ROOT = Path(__file__).resolve().parent.parent

# A `License:` field is legal core metadata and, under PEP 639, superseded by
# `License-Expression`. What makes it a defect rather than a style point is how
# long it can be: PyPI renders whatever is in it, so a pointer at a file becomes
# the whole license on the project page. Anything past this is not a license
# name by any reading.
MAX_SANE_LICENSE_FIELD = 64


@dataclass(frozen=True)
class Result:
    """One named field check and what the artifact actually said."""

    name: str
    ok: bool
    detail: str


def normalize(name: str) -> str:
    """Apply PEP 503 name normalization."""
    return re.sub(r"[-_.]+", "-", name).lower()


def parse_metadata(raw: bytes) -> Message:
    return email.parser.BytesParser(policy=email.policy.compat32).parsebytes(raw)


def description_of(msg: Message) -> str:
    """Return the long description from the body, or the legacy header."""
    payload = msg.get_payload(decode=False)
    if isinstance(payload, str) and payload.strip():
        return payload
    return str(msg.get("Description") or "")


def read_wheel(path: Path) -> Message:
    with zipfile.ZipFile(path) as archive:
        names = [n for n in archive.namelist() if n.endswith(".dist-info/METADATA")]
        if len(names) != 1:
            raise SystemExit(f"{path.name}: expected one dist-info/METADATA, found {names}")
        return parse_metadata(archive.read(names[0]))


def read_sdist(path: Path) -> Message:
    with tarfile.open(path) as archive:
        names = [n for n in archive.getnames() if n.count("/") == 1 and n.endswith("/PKG-INFO")]
        if len(names) != 1:
            raise SystemExit(f"{path.name}: expected one top-level PKG-INFO, found {names}")
        handle = archive.extractfile(names[0])
        if handle is None:
            raise SystemExit(f"{path.name}: PKG-INFO is not a regular file")
        with handle:
            return parse_metadata(handle.read())


def expected_from_source() -> tuple[str, str]:
    """Return ``(version, requires-python)`` as pyproject.toml declares them."""
    project = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    return str(project["version"]), str(project["requires-python"])


def check_identity(msg: Message, version: str) -> list[Result]:
    name = str(msg.get("Name") or "")
    got = str(msg.get("Version") or "")
    return [
        Result(
            "the artifact carries the published distribution name",
            normalize(name) == DISTRIBUTION,
            f"Name: {name!r} (expected {DISTRIBUTION!r})",
        ),
        Result(
            "the artifact's version is the version the tree declares",
            got == version,
            f"Version: {got!r} (pyproject.toml says {version!r})",
        ),
    ]


def check_python(msg: Message, requires_python: str) -> list[Result]:
    got = str(msg.get("Requires-Python") or "")
    return [
        Result(
            "requires-python is present and matches the tree",
            got == requires_python,
            f"Requires-Python: {got!r} (pyproject.toml says {requires_python!r})",
        )
    ]


def check_license(msg: Message) -> list[Result]:
    expression = str(msg.get("License-Expression") or "")
    legacy = msg.get("License")
    text = str(legacy) if legacy is not None else ""
    lines = len(text.splitlines())
    classifiers = [str(c) for c in (msg.get_all("Classifier") or [])]
    license_classifiers = [c for c in classifiers if c.startswith("License ::")]
    return [
        Result(
            "the license is a PEP 639 SPDX expression",
            expression == LICENSE_EXPRESSION,
            f"License-Expression: {expression!r} (expected {LICENSE_EXPRESSION!r})",
        ),
        Result(
            "no superseded License field",
            legacy is None,
            "License: absent"
            if legacy is None
            else f"License: present -- {lines} line(s), {len(text)} characters",
        ),
        Result(
            "the License field is not a license document",
            legacy is None or (lines <= 1 and len(text) <= MAX_SANE_LICENSE_FIELD),
            "no License field to measure"
            if legacy is None
            else f"License: {lines} line(s), {len(text)} characters -- PyPI renders every one of "
            f"them on the project page (a license name is under {MAX_SANE_LICENSE_FIELD})",
        ),
        # Not conditioned on the expression being present: a check written as
        # "no classifier *when* there is an expression" passes on exactly the
        # artifact that has no expression, which is the artifact in question.
        Result(
            "no superseded license classifier",
            not license_classifiers,
            f"license classifiers: {license_classifiers or 'none'}",
        ),
    ]


def check_urls(msg: Message) -> list[Result]:
    entries: dict[str, str] = {}
    for raw in msg.get_all("Project-URL") or []:
        label, _, url = str(raw).partition(",")
        entries[label.strip()] = url.strip()
    missing = [label for label in REQUIRED_URL_LABELS if label not in entries]
    relative = sorted(k for k, v in entries.items() if not v.startswith("https://"))
    return [
        Result(
            "every required Project-URL label reaches the artifact",
            not missing,
            f"labels published: {sorted(entries)}; missing: {missing or 'none'}",
        ),
        Result(
            "every published Project-URL is an absolute https URL",
            not relative,
            f"not absolute https: {relative or 'none'}",
        ),
    ]


def check_description(msg: Message) -> list[Result]:
    description = description_of(msg)
    content_type = str(msg.get("Description-Content-Type") or "")
    summary = str(msg.get("Summary") or "")
    return [
        Result(
            "the rendered description declares its content type",
            content_type.startswith("text/"),
            f"Description-Content-Type: {content_type!r}",
        ),
        Result(
            "the rendered description is not empty",
            bool(description.strip()),
            f"description: {len(description)} characters",
        ),
        Result(
            "the one-line summary is present",
            bool(summary.strip()),
            f"Summary: {summary[:70]!r}",
        ),
    ]


def check(msg: Message, version: str, requires_python: str) -> list[Result]:
    """Run every field check against one parsed metadata document."""
    return [
        *check_identity(msg, version),
        *check_python(msg, requires_python),
        *check_license(msg),
        *check_urls(msg),
        *check_description(msg),
    ]


def check_agreement(wheel: Message, sdist: Message) -> Result:
    """The wheel and the sdist must tell PyPI the same story."""
    fields = ("Name", "Version", "Requires-Python", "License-Expression", "License", "Project-URL")
    disagreements = [
        field
        for field in fields
        if sorted(str(v) for v in (wheel.get_all(field) or []))
        != sorted(str(v) for v in (sdist.get_all(field) or []))
    ]
    return Result(
        "the wheel and the sdist agree on what PyPI is told",
        not disagreements,
        f"fields that disagree: {disagreements or 'none'}",
    )


def one(paths: list[Path], kind: str) -> Path:
    if len(paths) != 1:
        raise SystemExit(f"expected exactly one {kind}, found {[p.name for p in paths]}")
    return paths[0]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check built distribution metadata.")
    parser.add_argument("dist_dir", type=Path, help="directory holding the built wheel and sdist")
    parser.add_argument(
        "--wheel-only",
        action="store_true",
        help="check a lone wheel, e.g. one already published and downloaded back",
    )
    args = parser.parse_args(argv)

    version, requires_python = expected_from_source()
    wheel_path = one(sorted(args.dist_dir.glob("*.whl")), "wheel")
    wheel = read_wheel(wheel_path)
    results = check(wheel, version, requires_python)
    measured = [f"wheel {wheel_path.name}"]

    if not args.wheel_only:
        sdist_path = one(sorted(args.dist_dir.glob("*.tar.gz")), "sdist")
        results.append(check_agreement(wheel, read_sdist(sdist_path)))
        measured.append(f"sdist {sdist_path.name}")

    print(f"metadata as published in {', '.join(measured)}")
    for result in results:
        print(f"  [{'PASS' if result.ok else 'FAIL'}] {result.name}")
        print(f"         {result.detail}")
    passed = sum(1 for r in results if r.ok)
    print(f"\nfields correct in the artifact / fields examinable: {passed}/{len(results)}")
    if passed != len(results):
        print("\nA published version's metadata cannot be edited in place. Whatever is")
        print("wrong here is wrong for as long as that version exists on the index.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
