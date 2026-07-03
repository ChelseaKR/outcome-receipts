"""Merge-relevant: a committed receipts manifest must re-derive from the data.

``receipts verify`` recomputes every figure from the spec and the cited data, then
checks each value, slice hash, row count, query, unit, and display against the
manifest. These tests pin the passing case (a freshly written manifest re-derives)
and the failing cases (a tampered value, a receipt with no figure, a figure with no
receipt), since re-derivation is only worth shipping if drift fails closed.
"""

from __future__ import annotations

import json
from pathlib import Path

from outcome_receipts.cli import main
from outcome_receipts.clock import FixedClock
from outcome_receipts.config import load_spec
from outcome_receipts.engine import compute_figures, read_csv
from outcome_receipts.models import Figure
from outcome_receipts.report import receipts_manifest
from outcome_receipts.verify import verify_manifest

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
HOUSING = EXAMPLES / "housing-demo" / "report.toml"
GRANT = EXAMPLES / "grant-report" / "report.toml"


def _figures() -> list[Figure]:
    spec = load_spec(HOUSING)
    rows = read_csv(spec.data_path)
    return compute_figures(rows, spec.report.metrics, clock=FixedClock())


def test_fresh_manifest_re_derives() -> None:
    figures = _figures()
    manifest = json.loads(receipts_manifest(figures))
    result = verify_manifest(figures, manifest)
    assert result.ok
    # Every check passes: one per figure plus the manifest-level schema_version
    # and hash-descriptor checks now carried by a versioned manifest.
    assert result.n_ok == len(result.checks)
    assert result.n_ok == len(figures) + 2


def test_tampered_value_is_drift() -> None:
    figures = _figures()
    manifest = json.loads(receipts_manifest(figures))
    for receipt in manifest["receipts"]:
        if receipt["metric_id"] == "clients_served":
            receipt["value"] = 999.0
    result = verify_manifest(figures, manifest)
    assert not result.ok
    drifted = [c for c in result.checks if not c.ok]
    assert [c.metric_id for c in drifted] == ["clients_served"]
    assert "value" in drifted[0].detail


def test_tampered_slice_hash_is_drift() -> None:
    figures = _figures()
    manifest = json.loads(receipts_manifest(figures))
    manifest["receipts"][0]["slice_hash"] = "deadbeef"
    result = verify_manifest(figures, manifest)
    assert not result.ok
    assert any("slice_hash" in c.detail for c in result.checks if not c.ok)


def test_receipt_with_no_figure_fails() -> None:
    figures = _figures()
    manifest = json.loads(receipts_manifest(figures))
    manifest["receipts"].append({"metric_id": "ghost", "value": 1.0})
    result = verify_manifest(figures, manifest)
    assert not result.ok
    assert any(c.metric_id == "ghost" and "no figure" in c.detail for c in result.checks)


def test_figure_with_no_receipt_fails() -> None:
    figures = _figures()
    manifest = json.loads(receipts_manifest(figures))
    manifest["receipts"] = [r for r in manifest["receipts"] if r["metric_id"] != "exits"]
    result = verify_manifest(figures, manifest)
    assert not result.ok
    assert any(c.metric_id == "exits" and "no receipt" in c.detail for c in result.checks)


def test_cli_verify_passes_on_a_just_written_manifest(tmp_path: Path) -> None:
    out = tmp_path / "grant"
    assert main(["run", "--config", str(GRANT), "--out", str(out), "--reproducible"]) == 0
    code = main(["verify", "--config", str(GRANT), "--receipts", str(out / "receipts.json")])
    assert code == 0


def test_cli_verify_fails_on_a_tampered_manifest(tmp_path: Path) -> None:
    out = tmp_path / "grant"
    assert main(["run", "--config", str(GRANT), "--out", str(out), "--reproducible"]) == 0
    manifest_path = out / "receipts.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["receipts"][0]["value"] = -1.0
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    code = main(["verify", "--config", str(GRANT), "--receipts", str(manifest_path)])
    assert code == 1
