"""Compatibility evidence frozen from the signed v0.1.0 and v0.2.0 releases."""

from __future__ import annotations

import json
from pathlib import Path

from outcome_receipts.clock import FixedClock
from outcome_receipts.config import SPEC_SCHEMA_VERSION, load_spec
from outcome_receipts.engine import compute_figures, read_csv
from outcome_receipts.models import SCHEMA_VERSION
from outcome_receipts.suppression import suppress_figures
from outcome_receipts.verify import verify_manifest

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "tests" / "fixtures" / "compat" / "v0.1.0"
BASELINE_V020 = ROOT / "tests" / "fixtures" / "compat" / "v0.2.0"


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
    # The baseline is a manifest-schema 1.0 document, which is no longer what
    # this package writes: 2.0 withholds a suppressed receipt's numerics as null
    # where 1.0 wrote zeros. Assert the older shape is really what was read, so
    # this cannot start passing vacuously if the fixture is ever regenerated.
    assert manifest["schema_version"] == "1.0"
    assert manifest["schema_version"] != SCHEMA_VERSION
    withheld = [record for record in manifest["receipts"] if record["value"] == 0.0]
    assert withheld, "the baseline no longer exercises the 1.0 suppressed rendering"
    assert all("suppressed" not in record for record in manifest["receipts"])
    assert any(figure.receipt.suppressed for figure in publishable)


def test_v010_baseline_names_immutable_source_commit() -> None:
    source = (BASELINE / "SOURCE.md").read_text(encoding="utf-8")

    assert "v0.1.0" in source
    assert "51d18fc4cdd9f9dcd91dd4588ededc80a6b6bb7d" in source
    assert "byte-for-byte copies" in source


def test_current_code_rederives_signed_v020_receipt_manifest() -> None:
    # The second released implementation. `v0.2.0` is the first tag whose spec
    # names its own contract version; `v0.1.0`'s carried no `schema_version` key
    # and was interpreted as 1.0 by default. Both are read by the same loader,
    # and the manifest each release shipped still re-derives field-for-field.
    spec = load_spec(BASELINE_V020 / "report.toml")
    figures = compute_figures(
        read_csv(spec.data_path),
        spec.report.metrics,
        clock=FixedClock(),
        data_checks=spec.report.data_checks,
    )
    publishable, suppression = suppress_figures(figures)
    manifest = json.loads((BASELINE_V020 / "receipts.json").read_text(encoding="utf-8"))

    result = verify_manifest(publishable, manifest)

    assert suppression.ok
    assert result.ok
    assert manifest["schema_version"] == "1.0"
    assert manifest["schema_version"] != SCHEMA_VERSION
    # Same vacuity guard as the v0.1.0 case: the 1.0 rendering writes a
    # suppressed receipt's numerics as zeros, and this fixture must still carry
    # one or it has stopped exercising the older shape.
    withheld = [record for record in manifest["receipts"] if record["value"] == 0.0]
    assert withheld, "the v0.2.0 baseline no longer exercises the 1.0 suppressed rendering"
    assert all("suppressed" not in record for record in manifest["receipts"])


def test_the_two_release_baselines_differ_only_in_declaring_the_spec_version() -> None:
    # What the second release did to the contract, asserted rather than asserted
    # about. If a future release moves the artifact, this is the test that says
    # so, and the compatibility matrix in docs/SPEC-STABILITY.md is what has to
    # be updated in the same change.
    v010 = load_spec(BASELINE / "report.toml")
    v020 = load_spec(BASELINE_V020 / "report.toml")

    assert "schema_version" not in (BASELINE / "report.toml").read_text(encoding="utf-8")
    assert 'schema_version = "1.0"' in (BASELINE_V020 / "report.toml").read_text(encoding="utf-8")
    # The unversioned spec is not read as "unknown": it is read as 1.0, the same
    # contract the versioned one names. An absent version defaulting to the
    # current one is only safe while 1.0 is the only spec version there is, and
    # `load_spec` refuses any other value outright.
    assert v010.schema_version == v020.schema_version == SPEC_SCHEMA_VERSION


def test_v020_baseline_names_immutable_source_commit() -> None:
    source = (BASELINE_V020 / "SOURCE.md").read_text(encoding="utf-8")

    assert "v0.2.0" in source
    assert "b8f5a27e48283e6b97add1841d1f8a110f760265" in source
    assert "byte-for-byte copies" in source
