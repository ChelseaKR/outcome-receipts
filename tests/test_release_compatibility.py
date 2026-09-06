"""Compatibility evidence frozen from the signed v0.1.0 and v0.2.0 releases.

Two halves. The tests that re-derive a released manifest establish that an
artifact this package shipped is still readable by the package as it stands. The
tests that relabel or edit one of those same artifacts establish the other half,
which a passing row alone cannot: that the reader is discriminating. A verifier
that accepts every document accepts a released one too, and its PASS says
nothing. Issue 65 asks for both, recorded together.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from outcome_receipts.cli import EXIT_VERIFY_FAIL, main
from outcome_receipts.clock import FixedClock
from outcome_receipts.config import SPEC_SCHEMA_VERSION, load_spec
from outcome_receipts.engine import compute_figures, read_csv
from outcome_receipts.models import SCHEMA_VERSION, SUPPORTED_SCHEMA_VERSIONS, Figure
from outcome_receipts.suppression import suppress_figures
from outcome_receipts.verify import verify_manifest

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "tests" / "fixtures" / "compat" / "v0.1.0"
BASELINE_V020 = ROOT / "tests" / "fixtures" / "compat" / "v0.2.0"


def _rederive(baseline: Path) -> list[Figure]:
    """The publishable figures a frozen baseline's spec and data produce today."""

    spec = load_spec(baseline / "report.toml")
    figures = compute_figures(
        read_csv(spec.data_path),
        spec.report.metrics,
        clock=FixedClock(),
        data_checks=spec.report.data_checks,
    )
    publishable, suppression = suppress_figures(figures)
    assert suppression.ok
    return list(publishable)


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


def _relabelled_baseline_spec(tmp_path: Path, schema_version: str) -> Path:
    """The frozen v0.2.0 spec, relabelled to a schema major, with unreadable data.

    The data path is deliberately pointed at a CSV that does not exist. If the
    loader refuses the declared version *before* computation, that missing file is
    never opened and the error names the version; if refusal ever moved to after
    the read, this helper's spec would fail on the data instead, and the test
    asserting the version error would say so.
    """

    source = (BASELINE_V020 / "report.toml").read_text(encoding="utf-8")
    relabelled = source.replace(
        f'schema_version = "{SPEC_SCHEMA_VERSION}"', f'schema_version = "{schema_version}"'
    )
    assert f'schema_version = "{schema_version}"' in relabelled, "the version line did not move"
    relabelled = relabelled.replace('path = "services.csv"', 'path = "no-such-data.csv"')
    assert 'path = "no-such-data.csv"' in relabelled, "the data path did not move"

    spec_path = tmp_path / "report.toml"
    spec_path.write_text(relabelled, encoding="utf-8")
    assert not (tmp_path / "no-such-data.csv").exists()
    return spec_path


def test_a_future_major_spec_is_refused_before_computation_and_writes_nothing(
    tmp_path: Path,
) -> None:
    """Issue 65: an unsupported future major fails early, by name, with no output.

    Three things have to hold together, and only the first is about the message.
    The error must *name* the version it was handed and the one this package
    implements, so a reader is not left guessing which end is wrong. It must be
    raised before any figure is computed — proved here by a spec whose data file
    does not exist, which would raise a different, louder error if the read were
    reached. And the run must leave the output directory as it found it: a
    half-written bundle from a refused spec is a receipt set with nothing behind
    it, which is the one artifact this repository exists to make impossible.
    """

    out = tmp_path / "out"
    spec_path = _relabelled_baseline_spec(tmp_path, "2.0")

    with pytest.raises(ValueError) as raised:
        main(
            [
                "run",
                "--config",
                str(spec_path),
                "--out",
                str(out),
                "--reproducible",
                "--approved-by",
                "CI",
            ]
        )

    message = str(raised.value)
    assert "schema_version" in message
    assert "'2.0'" in message, "the refusal must name the version it was handed"
    assert f"{SPEC_SCHEMA_VERSION!r}" in message, "and the version it implements"
    assert "not supported" in message
    # Nothing was computed: the missing CSV was never reached.
    assert "no-such-data.csv" not in message
    # Nothing was written.
    assert not out.exists() or not list(out.iterdir())


def test_the_current_verifier_refuses_a_frozen_manifest_relabelled_to_a_future_major(
    tmp_path: Path,
) -> None:
    """Issue 65: the intentionally incompatible half of the old-artifact exercise.

    The compatible cases are the two tests above: a released manifest, unedited,
    re-derives under current code. This is the same released manifest with one
    field changed to a major nobody implements. It has to be refused, and the
    refusal has to be attributable — every receipt in it still re-derives, so if
    the version check were dropped tomorrow this document would pass and a
    consumer would read a contract it does not understand as a verified one.
    """

    publishable = _rederive(BASELINE)
    manifest = json.loads((BASELINE / "receipts.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] in SUPPORTED_SCHEMA_VERSIONS
    manifest["schema_version"] = "3.0"

    result = verify_manifest(publishable, manifest)

    assert not result.ok
    versions = [check for check in result.checks if check.metric_id == "schema_version"]
    assert len(versions) == 1
    assert not versions[0].ok
    assert "3.0" in versions[0].detail, "the refusal must name the version it was handed"
    for supported in SUPPORTED_SCHEMA_VERSIONS:
        assert supported in versions[0].detail, "and the ones it accepts"
    # The refusal is the version and nothing else.
    receipts = [check for check in result.checks if check.metric_id != "schema_version"]
    assert receipts, "the manifest carried no other checks to attribute the failure away from"
    assert all(check.ok for check in receipts)

    # And it fails closed at the CLI boundary, not only in the library.
    relabelled = tmp_path / "receipts.json"
    relabelled.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    code = main(
        ["verify", "--config", str(BASELINE / "report.toml"), "--receipts", str(relabelled)]
    )
    assert code == EXIT_VERIFY_FAIL


def test_an_edited_frozen_receipt_is_reported_as_drift_not_quietly_accepted() -> None:
    """Issue 65: an old artifact altered after the fact must not verify.

    The other intentionally incompatible case, and the one the manifest's whole
    purpose rests on. A released manifest whose figure was edited by hand is
    indistinguishable from a genuine one by inspection; it is distinguishable
    only by re-derivation. The edit here is deliberately small and plausible —
    one client added to a count — because a verifier that only catches implausible
    numbers catches nothing worth catching.
    """

    publishable = _rederive(BASELINE)
    manifest = json.loads((BASELINE / "receipts.json").read_text(encoding="utf-8"))
    edited = [record for record in manifest["receipts"] if record["metric_id"] == "clients_served"]
    assert len(edited) == 1
    original = edited[0]["value"]
    edited[0]["value"] = original + 1
    edited[0]["display"] = str(int(original) + 1)

    result = verify_manifest(publishable, manifest)

    assert not result.ok
    drifted = [check for check in result.checks if not check.ok]
    assert [check.metric_id for check in drifted] == ["clients_served"]
    assert "value" in drifted[0].detail
