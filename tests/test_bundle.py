"""Merge-relevant: an exported audit bundle must be tamper-evident.

``bundle_manifest`` seals a set of export files with per-member BLAKE2b digests, a
``bundle_digest`` over the canonicalized ``(name, digest)`` list, and an optional
keyed-BLAKE2b signature. These tests pin the passing case (a fresh bundle verifies)
and the failing cases (a mutated member, a missing or extra member, and a wrong or
tampered signature), since a tamper-evident seal is only worth shipping if tamper
fails closed. A keyed round-trip and the CLI ``run`` / ``verify-bundle`` path are
covered too.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from outcome_receipts.bundle import bundle_manifest, verify_bundle
from outcome_receipts.cli import main

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
GRANT = EXAMPLES / "grant-report" / "report.toml"

FILES = {
    "report.md": b"# Report\n\nEvery number is a receipt.\n",
    "receipts.json": b'{"receipts": []}\n',
    "charts/served.svg": b"<svg></svg>",
}
KEY = b"a-shared-signing-key"


def test_fresh_bundle_verifies() -> None:
    manifest = json.loads(bundle_manifest(FILES))
    result = verify_bundle(FILES, manifest)
    assert result.ok
    # one check per member plus the aggregate bundle_digest check
    assert result.n_ok == len(FILES) + 1


def test_manifest_is_sorted_and_reproducible() -> None:
    assert bundle_manifest(FILES) == bundle_manifest(dict(reversed(list(FILES.items()))))
    manifest = json.loads(bundle_manifest(FILES))
    names = [member["name"] for member in manifest["members"]]
    assert names == sorted(names)
    assert "signature" not in manifest


def test_mutated_member_is_tampered_and_named() -> None:
    manifest = json.loads(bundle_manifest(FILES))
    mutated = {**FILES, "report.md": b"# Report\n\nInvented number: 999.\n"}
    result = verify_bundle(mutated, manifest)
    assert not result.ok
    failed = [c for c in result.checks if not c.ok]
    assert "report.md" in {c.name for c in failed}
    assert any("digest" in c.detail for c in failed if c.name == "report.md")
    # tampering the bytes also breaks the aggregate digest
    assert any(c.name == "bundle_digest" and not c.ok for c in result.checks)


def test_missing_member_fails() -> None:
    manifest = json.loads(bundle_manifest(FILES))
    without = {k: v for k, v in FILES.items() if k != "receipts.json"}
    result = verify_bundle(without, manifest)
    assert not result.ok
    assert any(
        c.name == "receipts.json" and "missing" in c.detail for c in result.checks if not c.ok
    )


def test_extra_member_fails() -> None:
    manifest = json.loads(bundle_manifest(FILES))
    extra = {**FILES, "stowaway.txt": b"not sealed"}
    result = verify_bundle(extra, manifest)
    assert not result.ok
    assert any(
        c.name == "stowaway.txt" and "not in manifest" in c.detail
        for c in result.checks
        if not c.ok
    )


def test_keyed_signature_round_trips() -> None:
    manifest = json.loads(bundle_manifest(FILES, key=KEY))
    assert "signature" in manifest
    result = verify_bundle(FILES, manifest, key=KEY)
    assert result.ok
    assert any(c.name == "signature" and c.ok for c in result.checks)


def test_wrong_key_fails_the_signature() -> None:
    manifest = json.loads(bundle_manifest(FILES, key=KEY))
    result = verify_bundle(FILES, manifest, key=b"the-wrong-key")
    assert not result.ok
    assert any(c.name == "signature" and not c.ok for c in result.checks)


def test_tampered_signature_field_fails() -> None:
    manifest = json.loads(bundle_manifest(FILES, key=KEY))
    manifest["signature"] = "00" * 32
    result = verify_bundle(FILES, manifest, key=KEY)
    assert not result.ok
    assert any(c.name == "signature" and not c.ok for c in result.checks)


def test_key_expected_but_manifest_unsigned_fails() -> None:
    manifest = json.loads(bundle_manifest(FILES))  # no signature written
    result = verify_bundle(FILES, manifest, key=KEY)
    assert not result.ok
    assert any(c.name == "signature" and not c.ok for c in result.checks)


def test_tampered_bundle_digest_fails() -> None:
    manifest = json.loads(bundle_manifest(FILES))
    manifest["bundle_digest"] = "deadbeef"
    result = verify_bundle(FILES, manifest)
    assert not result.ok
    assert any(c.name == "bundle_digest" and not c.ok for c in result.checks)


def test_cli_run_writes_a_verifiable_bundle(tmp_path: Path) -> None:
    out = tmp_path / "grant"
    assert (
        main(
            [
                "run",
                "--config",
                str(GRANT),
                "--out",
                str(out),
                "--reproducible",
                "--approved-by",
                "CI",
            ]
        )
        == 0
    )
    assert (out / "bundle.json").exists()
    assert main(["verify-bundle", "--dir", str(out)]) == 0


def test_cli_verify_bundle_fails_when_a_file_is_edited(tmp_path: Path) -> None:
    out = tmp_path / "grant"
    assert (
        main(
            [
                "run",
                "--config",
                str(GRANT),
                "--out",
                str(out),
                "--reproducible",
                "--approved-by",
                "CI",
            ]
        )
        == 0
    )
    report = out / "report.md"
    report.write_text(report.read_text(encoding="utf-8") + "\ntampered\n", encoding="utf-8")
    assert main(["verify-bundle", "--dir", str(out)]) == 1


def test_cli_run_and_verify_bundle_with_a_signing_key(tmp_path: Path) -> None:
    out = tmp_path / "grant"
    key_file = tmp_path / "key.bin"
    key_file.write_bytes(KEY)
    assert (
        main(
            [
                "run",
                "--config",
                str(GRANT),
                "--out",
                str(out),
                "--reproducible",
                "--approved-by",
                "CI",
                "--sign-key-file",
                str(key_file),
            ]
        )
        == 0
    )
    manifest = json.loads((out / "bundle.json").read_text(encoding="utf-8"))
    assert "signature" in manifest
    assert main(["verify-bundle", "--dir", str(out), "--sign-key-file", str(key_file)]) == 0


def test_json_run_still_writes_and_reports_the_bundle(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "grant"
    assert (
        main(
            [
                "run",
                "--config",
                str(GRANT),
                "--out",
                str(out),
                "--reproducible",
                "--approved-by",
                "CI",
                "--json",
            ]
        )
        == 0
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["outputs"]["bundle"] == str(out / "bundle.json")
    assert (out / "bundle.json").is_file()


def test_nested_bundle_json_is_not_exempt_from_extra_member_check(tmp_path: Path) -> None:
    out = tmp_path / "grant"
    assert (
        main(
            [
                "run",
                "--config",
                str(GRANT),
                "--out",
                str(out),
                "--reproducible",
                "--approved-by",
                "CI",
            ]
        )
        == 0
    )
    nested = out / "charts" / "bundle.json"
    nested.parent.mkdir(exist_ok=True)
    nested.write_text("{}\n", encoding="utf-8")
    assert main(["verify-bundle", "--dir", str(out)]) == 1
