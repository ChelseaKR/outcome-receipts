"""The example-manifest gate finds what is committed, and fails when it should.

`scripts/check_example_manifests.py` exists because the manifest `dogfood-action`
verifies sat at schema 1.0 for every green run after 2.0 shipped (#198). These
tests inject a validator, because `jsonschema` is deliberately not in the
project environment (`docs/decisions/0005`); the real Draft 2020-12 validator runs in
`make example-manifests`. What they pin is everything around it: that the
committed example is in scope, that finding nothing is a failure, that a file
which does not parse or has a malformed `receipts` key cannot drop out of
scope, and that an error names the receipt it is in.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
from scripts.check_example_manifests import SCHEMA, SchemaError, run

ROOT = Path(__file__).resolve().parents[1]
MAKEFILE = ROOT / "Makefile"
COUNTS = re.compile(r"validated (\d+) / committed (\d+)")


def _no_errors(schema: dict[str, Any], document: Any) -> list[SchemaError]:
    return []


def _repo(tmp_path: Path, files: dict[str, str]) -> Path:
    schema = tmp_path / SCHEMA
    schema.parent.mkdir(parents=True)
    schema.write_bytes((ROOT / SCHEMA).read_bytes())
    for relative, text in files.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return tmp_path


def _counts(output: str) -> tuple[int, int]:
    match = COUNTS.search(output)
    assert match is not None, output
    return int(match.group(1)), int(match.group(2))


def test_the_committed_dogfood_example_is_in_scope(capsys: pytest.CaptureFixture[str]) -> None:
    seen: list[Any] = []

    def record(schema: dict[str, Any], document: Any) -> list[SchemaError]:
        seen.append(document)
        return []

    assert run(ROOT, record) == 0
    output = capsys.readouterr().out
    validated, committed = _counts(output)

    assert "[ok] examples/housing-demo/receipts.json: 0 errors" in output
    assert validated == committed == len(seen) >= 1


def test_finding_no_manifest_is_a_failure_not_a_pass(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    root = _repo(tmp_path, {"examples/mapping/requirements.json": '{"requirements": []}'})

    assert run(root, _no_errors) == 1
    captured = capsys.readouterr()
    assert _counts(captured.out) == (0, 0)
    assert "found no manifest" in captured.err


def test_an_error_names_the_receipt_it_is_in(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    manifest = {"receipts": [{"metric_id": "clients_served"}, {"metric_id": "exits"}]}
    root = _repo(tmp_path, {"examples/demo/receipts.json": json.dumps(manifest)})

    def missing_suppressed(schema: dict[str, Any], document: Any) -> list[SchemaError]:
        return [SchemaError(("receipts", 1), "'suppressed' is a required property")]

    assert run(root, missing_suppressed) == 1
    captured = capsys.readouterr()
    assert "[FAIL] examples/demo/receipts.json: 1 error(s)" in captured.out
    assert "receipts/1 (metric_id 'exits'): 'suppressed' is a required property" in captured.out
    assert "1 of 1 committed" in captured.err


def test_a_manifest_that_does_not_parse_is_committed_but_not_validated(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    root = _repo(tmp_path, {"examples/demo/receipts.json": "{"})

    assert run(root, _no_errors) == 1
    captured = capsys.readouterr()
    assert _counts(captured.out) == (0, 1)
    assert "does not parse as JSON" in captured.out


def test_a_malformed_receipts_key_does_not_leave_the_scope(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    root = _repo(tmp_path, {"examples/demo/exported.json": '{"receipts": {}}'})
    seen: list[Any] = []

    def record(schema: dict[str, Any], document: Any) -> list[SchemaError]:
        seen.append(document)
        return []

    assert run(root, record) == 0
    assert _counts(capsys.readouterr().out) == (1, 1)
    assert seen == [{"receipts": {}}]


def test_a_schema_that_is_not_draft_2020_12_is_refused(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    root = _repo(tmp_path, {"examples/demo/receipts.json": '{"receipts": []}'})
    schema = json.loads((root / SCHEMA).read_text(encoding="utf-8"))
    schema["$schema"] = "http://json-schema.org/draft-07/schema#"
    (root / SCHEMA).write_text(json.dumps(schema), encoding="utf-8")

    assert run(root, _no_errors) == 1
    assert "this gate validates https://json-schema.org/draft/2020-12/schema" in (
        capsys.readouterr().err
    )


def test_the_makefile_runs_a_pinned_validator_outside_the_project_environment() -> None:
    text = MAKEFILE.read_text(encoding="utf-8")
    match = re.search(r"^example-manifests:[^\n]*\n((?:\t[^\n]*\n)+)", text, re.MULTILINE)
    assert match is not None, "no `example-manifests` recipe in the Makefile"
    recipe = match.group(1).replace("\\\n", " ")

    assert re.search(r"--with jsonschema==\d+\.\d+\.\d+\b", recipe), recipe
    assert "--no-project" in recipe
    assert "scripts/check_example_manifests.py" in recipe
