"""Validate every committed example receipts manifest against the published schema.

`examples/housing-demo/receipts.json` is the manifest `ci.yml`'s `dogfood-action`
job verifies the reusable action against, and the sdist ships it. It was last
written under manifest schema 1.0 and was not regenerated when 2.0 made a
withheld figure `suppressed: true` with null numerics, so it published three
withheld figures as `value: 0.0` and `row_count: 0` and failed
`docs/schema/receipts.schema.json` with five errors while every gate stayed
green (#198). `receipts verify` could not see it: verify re-derives figures from
the data, it does not validate a document against the schema, and re-deriving
under 1.0 reproduces the zeros.

This gate is that validation, and how it is built is deliberate.

It uses a real Draft 2020-12 validator, `jsonschema`, rather than the structural
subset `tests/test_manifest_schema.py` carries. That subset implements the
keywords an emitted manifest exercises and ignores `pattern`, `enum` and
`minimum`, so it would pass a slice hash that is not hex or a `kind` the schema
does not name. `docs/decisions/0005` keeps `jsonschema` out of the project
environment, so the Makefile runs this file in an isolated `uv run --with`
environment at a pinned version, the way it runs Semgrep and zizmor, and
nothing is added to `uv.lock`.

It finds the manifests rather than being handed a list. Every JSON file under
`examples/` that is named `receipts.json` or carries a top-level `receipts` key
is one, whatever that key holds, so a malformed manifest cannot leave the scope
by being malformed. A JSON file there that does not parse is counted as
committed and not validated, because it cannot be ruled out. A list of paths
would validate only the files someone remembered to add to it.

It prints two numbers, manifests validated and manifests committed, and fails
when they differ or when the second is zero: a check that found nothing to
validate proved nothing.

The frozen compatibility baselines under `tests/fixtures/compat/` are out of
scope on purpose. They are byte-for-byte copies of what signed releases shipped
under schema 1.0, and `tests/test_release_compatibility.py` asserts they stay
that way.
"""

from __future__ import annotations

import importlib
import importlib.metadata
import json
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = Path("docs") / "schema" / "receipts.schema.json"
EXAMPLES = Path("examples")
DRAFT_2020_12 = "https://json-schema.org/draft/2020-12/schema"


@dataclass(frozen=True)
class SchemaError:
    """One validation error: where in the document, and what the validator said."""

    path: tuple[str | int, ...]
    message: str


#: Validates one document against the schema and returns every error in it.
Validate = Callable[[dict[str, Any], Any], list[SchemaError]]


def jsonschema_errors(schema: dict[str, Any], document: Any) -> list[SchemaError]:
    """Every Draft 2020-12 error in ``document``, sorted by location.

    `jsonschema` is imported here rather than at module level because it is
    deliberately absent from the project environment (`docs/decisions/0005`).
    The test suite imports the rest of this module and injects its own validator.
    """

    jsonschema = importlib.import_module("jsonschema")
    validator_class = jsonschema.Draft202012Validator
    validator_class.check_schema(schema)
    errors = [
        SchemaError(tuple(error.absolute_path), str(error.message))
        for error in validator_class(schema).iter_errors(document)
    ]
    return sorted(errors, key=lambda error: ([str(part) for part in error.path], error.message))


def is_manifest(path: Path, document: Any) -> bool:
    """Whether a parsed JSON file under ``examples/`` is a receipts manifest."""

    return path.name == "receipts.json" or (isinstance(document, dict) and "receipts" in document)


def describe(path: tuple[str | int, ...], document: Any) -> str:
    """The error's location, naming the receipt's ``metric_id`` when it is inside one."""

    location = "/".join(str(part) for part in path) or "(document root)"
    if len(path) < 2 or path[0] != "receipts" or not isinstance(path[1], int):
        return location
    receipts = document.get("receipts") if isinstance(document, dict) else None
    if not isinstance(receipts, list) or not 0 <= path[1] < len(receipts):
        return location
    record = receipts[path[1]]
    if isinstance(record, dict) and "metric_id" in record:
        return f"{location} (metric_id {record['metric_id']!r})"
    return location


def regenerate_hint(path: Path, root: Path) -> str:
    """How to rewrite a manifest through the export path rather than by hand."""

    spec = path.parent / "report.toml"
    if not spec.is_file():
        return "re-export it with a current `receipts run` from the spec that produced it"
    return (
        f"receipts run --config {spec.relative_to(root).as_posix()} --out <dir> "
        f"--reproducible --approved-by CI, then copy <dir>/receipts.json over "
        f"{path.relative_to(root).as_posix()}"
    )


@dataclass(frozen=True)
class Outcome:
    """What the gate found in one JSON file under ``examples/``."""

    manifest: bool
    validated: bool
    valid: bool
    lines: tuple[str, ...]


def check_file(path: Path, root: Path, schema: dict[str, Any], validate: Validate) -> Outcome:
    """Classify one JSON file and, when it is a manifest, validate it."""

    relative = path.relative_to(root).as_posix()
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        line = f"  [FAIL] {relative}: not validated, it does not parse as JSON ({exc})"
        return Outcome(manifest=True, validated=False, valid=False, lines=(line,))
    if not is_manifest(path, document):
        return Outcome(manifest=False, validated=False, valid=False, lines=())
    errors = validate(schema, document)
    if not errors:
        return Outcome(True, True, True, (f"  [ok] {relative}: 0 errors",))
    lines = [f"  [FAIL] {relative}: {len(errors)} error(s)"]
    lines.extend(f"    {describe(error.path, document)}: {error.message}" for error in errors)
    lines.append(f"    regenerate: {regenerate_hint(path, root)}")
    return Outcome(True, True, False, tuple(lines))


def run(root: Path, validate: Validate) -> int:
    """Validate every example manifest under ``root``; 0 only when all of them pass."""

    schema = json.loads((root / SCHEMA).read_text(encoding="utf-8"))
    declared = schema.get("$schema")
    if declared != DRAFT_2020_12:
        print(
            f"example-manifests FAIL: {SCHEMA.as_posix()} declares $schema {declared!r}, "
            f"and this gate validates {DRAFT_2020_12}",
            file=sys.stderr,
        )
        return 1

    outcomes = [
        check_file(path, root, schema, validate)
        for path in sorted((root / EXAMPLES).rglob("*.json"))
    ]
    manifests = [outcome for outcome in outcomes if outcome.manifest]
    committed = len(manifests)
    validated = sum(1 for outcome in manifests if outcome.validated)
    valid = sum(1 for outcome in manifests if outcome.valid)

    print(
        f"example manifests: validated {validated} / committed {committed} "
        f"(against {SCHEMA.as_posix()}, Draft 2020-12)"
    )
    for outcome in manifests:
        for line in outcome.lines:
            print(line)

    if committed == 0:
        print(
            f"example-manifests FAIL: found no manifest under {EXAMPLES.as_posix()}/, "
            "and a check that validated nothing proves nothing",
            file=sys.stderr,
        )
        return 1
    if validated != committed or valid != committed:
        print(
            f"example-manifests FAIL: {committed - valid} of {committed} committed "
            "example manifest(s) do not validate against the published schema",
            file=sys.stderr,
        )
        return 1
    print("example-manifests PASS: every committed example manifest validates")
    return 0


def main() -> int:
    try:
        importlib.import_module("jsonschema")
        version = importlib.metadata.version("jsonschema")
    except ImportError:
        print(
            "example-manifests FAIL: jsonschema is not importable here. Run "
            "`make example-manifests`, which supplies a pinned copy in an isolated "
            "environment.",
            file=sys.stderr,
        )
        return 1
    print(f"validator: jsonschema {version} (Draft202012Validator)")
    return run(ROOT, jsonschema_errors)


if __name__ == "__main__":
    raise SystemExit(main())
