"""The receipts manifest is versioned, self-describing, and schema-valid.

FIX-03 formalizes and versions ``receipts.json``: a top-level ``schema_version``
and a ``hash`` descriptor ride alongside the receipts, and a JSON Schema is
published at ``docs/schema/receipts.schema.json``. These tests pin that the
emitted manifest carries the new keys, structurally validates against the
published schema (checked with the standard library only, to keep runtime
dependencies empty — see ADR 0005), and that ``verify`` names a schema_version
mismatch before re-deriving fields.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from outcome_receipts.clock import FixedClock
from outcome_receipts.config import load_spec
from outcome_receipts.engine import compute_figures, read_csv
from outcome_receipts.models import (
    HASH_ALGORITHM,
    HASH_CANONICALIZATION,
    HASH_DIGEST_SIZE,
    SCHEMA_VERSION,
    Figure,
)
from outcome_receipts.report import receipts_manifest
from outcome_receipts.verify import verify_manifest

ROOT = Path(__file__).resolve().parents[1]
HOUSING = ROOT / "examples" / "housing-demo" / "report.toml"
SCHEMA_PATH = ROOT / "docs" / "schema" / "receipts.schema.json"


def _figures() -> list[Figure]:
    spec = load_spec(HOUSING)
    rows = read_csv(spec.data_path)
    return compute_figures(rows, spec.report.metrics, clock=FixedClock())


def test_manifest_carries_schema_version_and_hash_block() -> None:
    manifest = json.loads(receipts_manifest(_figures()))
    assert manifest["schema_version"] == SCHEMA_VERSION
    assert manifest["hash"] == {
        "algorithm": HASH_ALGORITHM,
        "digest_size": HASH_DIGEST_SIZE,
        "canonicalization": HASH_CANONICALIZATION,
    }


def test_published_schema_pins_the_manifest_version() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert schema["properties"]["schema_version"]["const"] == SCHEMA_VERSION


def test_manifest_receipts_carry_column_names() -> None:
    manifest = json.loads(receipts_manifest(_figures()))
    for receipt in manifest["receipts"]:
        assert isinstance(receipt["column_names"], list)
        assert receipt["column_names"]  # non-empty for these metrics


def test_published_schema_declares_caveat() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    receipt_properties = schema["properties"]["receipts"]["items"]["properties"]
    assert receipt_properties["caveat"]["type"] == "string"


def test_published_schema_declares_logic_model_fields() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    receipt_properties = schema["properties"]["receipts"]["items"]["properties"]
    for field in ("indicator", "data_source", "collection_frequency"):
        assert receipt_properties[field]["type"] == "string"


# --- A tiny stdlib structural validator for a subset of JSON Schema. ---
# We validate the emitted manifest against the published schema using only the
# standard library, so the zero runtime-dependency posture holds (ADR 0005).

_JSON_TYPES: dict[str, type | tuple[type, ...]] = {
    "object": dict,
    "array": list,
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "null": type(None),
}


def _matches_type(instance: Any, expected: str) -> bool:
    # bool is a subclass of int; reject it where a number/integer is wanted.
    if expected in ("integer", "number") and isinstance(instance, bool):
        return False
    return isinstance(instance, _JSON_TYPES[expected])


def _validate_type(instance: Any, expected: str | list[str], path: str) -> list[str]:
    """Check ``instance`` against a JSON Schema ``type``; empty list on match.

    ``type`` may be a list, which is how the manifest schema declares a withheld
    figure's numerics as ``["number", "null"]``. Any member matching is a match.
    """

    options = [expected] if isinstance(expected, str) else list(expected)
    if any(_matches_type(instance, option) for option in options):
        return []
    return [f"{path}: expected {options}, got {type(instance).__name__}"]


def _validate_object(instance: dict[str, Any], schema: dict[str, Any], path: str) -> list[str]:
    errors: list[str] = []
    for key in schema.get("required", []):
        if key not in instance:
            errors.append(f"{path}: missing required key {key!r}")
    props = schema.get("properties", {})
    if schema.get("additionalProperties") is False:
        for key in instance:
            if key not in props:
                errors.append(f"{path}: unexpected key {key!r}")
    for key, subschema in props.items():
        if key in instance:
            errors.extend(_validate(instance[key], subschema, f"{path}.{key}"))
    return errors


def _validate_array(instance: list[Any], schema: dict[str, Any], path: str) -> list[str]:
    item_schema = schema.get("items")
    if item_schema is None:
        return []
    errors: list[str] = []
    for i, item in enumerate(instance):
        errors.extend(_validate(item, item_schema, f"{path}[{i}]"))
    return errors


def _applies(instance: Any, condition: dict[str, Any]) -> bool:
    """Whether an ``if`` subschema matches, for the ``allOf``/``if``/``then`` form.

    Only the shape the manifest schema actually uses is supported: required keys
    plus ``const`` on a property. Anything richer would be a second JSON Schema
    implementation, which is not what this file is for.
    """

    if not isinstance(instance, dict):
        return False
    if any(key not in instance for key in condition.get("required", [])):
        return False
    for key, subschema in condition.get("properties", {}).items():
        if "const" in subschema and instance.get(key) != subschema["const"]:
            return False
    return True


def _validate(instance: Any, schema: dict[str, Any], path: str = "$") -> list[str]:
    expected = schema.get("type")
    if expected is not None:
        type_errors = _validate_type(instance, expected, path)
        if type_errors:
            return type_errors
    errors: list[str] = []
    if "const" in schema and instance != schema["const"]:
        errors.append(f"{path}: expected const {schema['const']!r}, got {instance!r}")
    # An untyped subschema carrying `properties` is how the `then` branch of a
    # conditional constrains a few fields of an already-typed object.
    if isinstance(instance, dict) and (
        expected == "object" or (expected is None and {"properties", "required"} & schema.keys())
    ):
        errors.extend(_validate_object(instance, schema, path))
    if expected == "array":
        errors.extend(_validate_array(instance, schema, path))
    for clause in schema.get("allOf", []):
        if "if" in clause:
            if _applies(instance, clause["if"]):
                errors.extend(_validate(instance, clause.get("then", {}), path))
        else:
            errors.extend(_validate(instance, clause, path))
    return errors


def test_emitted_manifest_validates_against_published_schema() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    manifest = json.loads(receipts_manifest(_figures()))
    errors = _validate(manifest, schema)
    assert errors == [], errors


def test_manifest_with_artifacts_validates_against_published_schema() -> None:
    """A run-exported manifest carries `artifacts`; the schema must allow it."""
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    artifacts = {"report.md": "0" * 64, "trace.html": "a" * 64}
    manifest = json.loads(receipts_manifest(_figures(), artifacts=artifacts))
    assert manifest["artifacts"] == artifacts
    assert "artifacts" in schema["properties"]
    errors = _validate(manifest, schema)
    assert errors == [], errors


def _suppressed_manifest() -> dict[str, Any]:
    """A manifest whose figures include a withheld cell and a true zero."""

    from outcome_receipts.suppression import suppress_figures

    publishable, result = suppress_figures(_figures())
    assert result.suppressed, "the housing demo must still contain a small cell"
    manifest: dict[str, Any] = json.loads(receipts_manifest(publishable))
    return manifest


def test_a_withheld_receipt_validates_only_while_it_carries_no_number() -> None:
    """The schema must actively reject the shape this issue is about.

    A validator that merely tolerates ``null`` proves nothing; the point is that
    ``suppressed: true`` beside a real number is invalid. Each field is restored
    afterwards so the test also shows the manifest is otherwise valid, and so a
    later failure cannot be blamed on the previous mutation.
    """

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    manifest = _suppressed_manifest()
    assert _validate(manifest, schema) == []

    withheld = next(record for record in manifest["receipts"] if record["suppressed"])
    for field, leaked in (("value", 0.0), ("row_count", 0), ("slice_hash", "0" * 64)):
        restore = withheld[field]
        withheld[field] = leaked
        assert _validate(manifest, schema) != [], field
        withheld[field] = restore

    assert _validate(manifest, schema) == []


def test_a_published_receipt_validates_only_while_it_carries_a_number() -> None:
    """The other direction: ``suppressed: false`` with a null value is invalid.

    Without this the conditional could be satisfied by nulling everything, which
    would make every figure indistinguishable in the opposite direction.
    """

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    manifest = _suppressed_manifest()
    published = next(record for record in manifest["receipts"] if not record["suppressed"])

    published["value"] = None

    assert _validate(manifest, schema) != []


def test_wrong_schema_version_is_a_named_failure() -> None:
    figures = _figures()
    manifest = json.loads(receipts_manifest(figures))
    manifest["schema_version"] = "0.9"
    result = verify_manifest(figures, manifest)
    assert not result.ok
    drifted = [c for c in result.checks if not c.ok]
    assert any(c.metric_id == "schema_version" for c in drifted)
    detail = next(c.detail for c in drifted if c.metric_id == "schema_version")
    assert "'0.9'" in detail and f"'{SCHEMA_VERSION}'" in detail


def test_wrong_hash_descriptor_is_a_named_failure() -> None:
    figures = _figures()
    manifest = json.loads(receipts_manifest(figures))
    manifest["hash"]["canonicalization"] = "v0"
    result = verify_manifest(figures, manifest)
    assert not result.ok
    assert any(c.metric_id == "hash" and not c.ok for c in result.checks)


def test_pre_schema_manifest_still_re_derives() -> None:
    """A manifest without the version keys is not flagged by the schema check."""
    figures = _figures()
    manifest = json.loads(receipts_manifest(figures))
    del manifest["schema_version"]
    del manifest["hash"]
    result = verify_manifest(figures, manifest)
    assert result.ok
