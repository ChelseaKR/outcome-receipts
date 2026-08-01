"""Compatibility evidence frozen from the signed v0.1.0 release."""

from __future__ import annotations

import json
from pathlib import Path

from outcome_receipts.clock import FixedClock
from outcome_receipts.config import SPEC_SCHEMA_VERSION, load_spec
from outcome_receipts.engine import compute_figures, read_csv
from outcome_receipts.suppression import suppress_figures
from outcome_receipts.verify import verify_manifest

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "tests" / "fixtures" / "compat" / "v0.1.0"


def test_current_code_rederives_signed_v010_receipt_manifest() -> None:
    spec = load_spec(BASELINE / "report.toml")
    figures = compute_figures(
        read_csv(spec.data_path),
        spec.report.metrics,
        clock=FixedClock(),
        data_checks=spec.report.data_checks,
    )
    publishable, suppression = suppress_figures(figures)
    manifest = json.loads((BASELINE / "receipts.json").read_text(encoding="utf-8"))

    result = verify_manifest(publishable, manifest)

    assert spec.schema_version == SPEC_SCHEMA_VERSION
    assert suppression.ok
    assert result.ok


def test_v010_baseline_names_immutable_source_commit() -> None:
    source = (BASELINE / "SOURCE.md").read_text(encoding="utf-8")

    assert "v0.1.0" in source
    assert "51d18fc4cdd9f9dcd91dd4588ededc80a6b6bb7d" in source
    assert "byte-for-byte copies" in source
