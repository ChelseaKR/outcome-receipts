"""Merge-relevant: a committed receipts manifest must re-derive from the data.

``receipts verify`` recomputes every figure from the spec and the cited data, then
checks each value, slice hash, row count, query, unit, and display against the
manifest. These tests pin the passing case (a freshly written manifest re-derives)
and the failing cases (a tampered value, a receipt with no figure, a figure with no
receipt), since re-derivation is only worth shipping if drift fails closed.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from outcome_receipts.cli import main
from outcome_receipts.clock import FixedClock
from outcome_receipts.config import load_spec
from outcome_receipts.engine import compute_figures, read_csv
from outcome_receipts.models import Figure
from outcome_receipts.report import receipts_manifest
from outcome_receipts.verify import verify_bundle, verify_manifest

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
HOUSING = EXAMPLES / "housing-demo" / "report.toml"
GRANT = EXAMPLES / "grant-report" / "report.toml"


def _figures(config: Path = HOUSING) -> list[Figure]:
    spec = load_spec(config)
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
    # `n_ok` spans both kinds and is therefore not a count of receipts. That the
    # two numbers differ is the whole reason the kinds are recorded: this
    # assertion used to be the only statement of the total, and reading it as
    # "how many receipts re-derived" overstated it by the two descriptors.
    assert result.n_receipts_ok == len(figures)
    assert len(result.receipt_checks) == len(figures)
    assert [check.metric_id for check in result.manifest_checks] == ["schema_version", "hash"]
    assert all(check.kind == "receipt" for check in result.receipt_checks)


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
    run_args = ["run", "--config", str(GRANT), "--out", str(out)]
    run_args += ["--reproducible", "--approved-by", "CI"]
    assert main(run_args) == 0
    code = main(["verify", "--config", str(GRANT), "--receipts", str(out / "receipts.json")])
    assert code == 0


def test_cli_verify_fails_on_a_tampered_manifest(tmp_path: Path) -> None:
    out = tmp_path / "grant"
    run_args = ["run", "--config", str(GRANT), "--out", str(out)]
    run_args += ["--reproducible", "--approved-by", "CI"]
    assert main(run_args) == 0
    manifest_path = out / "receipts.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["receipts"][0]["value"] = -1.0
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    code = main(["verify", "--config", str(GRANT), "--receipts", str(manifest_path)])
    assert code == 1


# --- Whole-bundle verification (FIX-04) ------------------------------------


def _bundle_figures() -> list[Figure]:
    """The full figure set the grant bundle asserts, comparison figures included.

    ``verify_bundle`` re-derives against the same figures ``run`` exported, so the
    bundle tests must compute the comparison figures too, not only the narrative
    metrics.
    """

    from outcome_receipts.cli import _compute_all
    from outcome_receipts.suppression import suppress_figures

    _spec, _rows, figures, _comparison, _reconciliation = _compute_all(
        str(GRANT), reproducible=True
    )
    suppressed, _result = suppress_figures(figures)
    return suppressed


def _export_grant_bundle(tmp_path: Path) -> Path:
    out = tmp_path / "grant"
    run_args = ["run", "--config", str(GRANT), "--out", str(out)]
    run_args += ["--reproducible", "--approved-by", "CI"]
    assert main(run_args) == 0
    return out


def test_fresh_bundle_verifies_green(tmp_path: Path) -> None:
    out = _export_grant_bundle(tmp_path)
    result = verify_bundle(out, _bundle_figures())
    assert result.ok
    assert all(a.ok for a in result.artifacts)
    assert result.grounding.ok
    # report.md, trace.html, and each chart SVG are all covered.
    covered = {a.path for a in result.artifacts}
    assert "report.md" in covered
    assert "trace.html" in covered
    assert any(p.startswith("charts/") and p.endswith(".svg") for p in covered)


def test_cli_verify_bundle_passes(tmp_path: Path) -> None:
    out = _export_grant_bundle(tmp_path)
    assert main(["verify", "--config", str(GRANT), "--bundle", str(out)]) == 0


def test_flipping_report_byte_fails_naming_report(tmp_path: Path) -> None:
    out = _export_grant_bundle(tmp_path)
    report = out / "report.md"
    report.write_text(report.read_text(encoding="utf-8") + " ", encoding="utf-8")
    result = verify_bundle(out, _bundle_figures())
    assert not result.ok
    assert [a.path for a in result.failed_artifacts] == ["report.md"]
    assert main(["verify", "--config", str(GRANT), "--bundle", str(out)]) == 1


def test_flipping_trace_byte_fails_naming_trace(tmp_path: Path) -> None:
    out = _export_grant_bundle(tmp_path)
    trace = out / "trace.html"
    trace.write_text(trace.read_text(encoding="utf-8") + "<!-- x -->", encoding="utf-8")
    result = verify_bundle(out, _bundle_figures())
    assert not result.ok
    assert [a.path for a in result.failed_artifacts] == ["trace.html"]


def test_flipping_chart_svg_byte_fails_naming_chart(tmp_path: Path) -> None:
    out = _export_grant_bundle(tmp_path)
    svgs = sorted((out / "charts").glob("*.svg"))
    assert svgs, "grant bundle should export at least one chart SVG"
    target = svgs[0]
    target.write_text(target.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    result = verify_bundle(out, _bundle_figures())
    assert not result.ok
    failed = [a.path for a in result.failed_artifacts]
    assert failed == [f"charts/{target.stem}.svg"]


def test_missing_artifact_fails_closed(tmp_path: Path) -> None:
    out = _export_grant_bundle(tmp_path)
    (out / "trace.html").unlink()
    result = verify_bundle(out, _bundle_figures())
    assert not result.ok
    assert any(a.path == "trace.html" and "missing" in a.detail for a in result.failed_artifacts)


def test_missing_artifacts_key_fails_closed(tmp_path: Path) -> None:
    out = _export_grant_bundle(tmp_path)
    manifest_path = out / "receipts.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    del manifest["artifacts"]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    result = verify_bundle(out, _bundle_figures())
    assert not result.ok
    assert any("artifacts" in a.detail for a in result.failed_artifacts)


def test_unbound_number_in_report_fails_grounding(tmp_path: Path) -> None:
    out = _export_grant_bundle(tmp_path)
    report = out / "report.md"
    lines = report.read_text(encoding="utf-8").splitlines()
    # Inject an ungrounded number into the narrative (before the first ## section),
    # then re-hash so the digest still matches and only grounding can fail.
    for i, line in enumerate(lines):
        if line.startswith("## "):
            lines.insert(i, "An unverified 4242 appears here.")
            break
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    tampered = report.read_text(encoding="utf-8")
    manifest_path = out / "receipts.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifacts"]["report.md"] = hashlib.sha256(tampered.encode("utf-8")).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    result = verify_bundle(out, _bundle_figures())
    assert not result.ok
    # The digest still matches; the failure is the grounding gate, not an artifact.
    assert all(a.ok for a in result.artifacts)
    assert not result.grounding.ok
    assert any(span.text == "4242" for span in result.grounding.unbound)


def test_the_reported_receipt_count_is_the_manifest_receipt_count() -> None:
    """The count `verify` prints must be the number of receipts in the document.

    It was not. `schema_version` and `hash` are descriptors of the manifest,
    compared against a constant rather than re-derived from anything, and they
    were built as the same `Check` type as a receipt and counted with them. The
    housing demo's four-receipt manifest reported "receipts checked: 6
    (re-derived 6, drift 0)" -- a reported number, wrong by two, describing the
    strength of the verification a reader would quote.
    """

    figures = _figures()
    manifest = json.loads(receipts_manifest(figures))
    assert len(manifest["receipts"]) == 4

    result = verify_manifest(figures, manifest)

    assert len(result.receipt_checks) == len(manifest["receipts"])
    assert result.n_receipts_ok == len(manifest["receipts"])
    assert len(result.checks) > len(result.receipt_checks), (
        "the manifest carried no descriptors, so this no longer tests the conflation"
    )
    stored = {receipt["metric_id"] for receipt in manifest["receipts"]}
    assert {check.metric_id for check in result.receipt_checks} == stored


def test_a_version_only_failure_does_not_blame_the_data(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A refused version is a document failure, not a data failure.

    Every receipt re-derives here. The only thing wrong is the declared schema
    major, and the failure has to say so: the headline used to read "a receipt
    does not match the data" for this exact case, sending the reader to the one
    place the problem was not. Asserted on what the CLI actually prints, since
    the headline is the part a person reads first and acts on.
    """

    figures = _figures()
    manifest = json.loads(receipts_manifest(figures))
    manifest["schema_version"] = "3.0"

    result = verify_manifest(figures, manifest)
    assert not result.ok
    assert result.n_receipts_ok == len(figures)
    assert result.failed_receipts == ()
    assert [check.metric_id for check in result.failed_manifest_checks] == ["schema_version"]

    # The CLI half needs a manifest the CLI itself wrote: `verify` suppresses the
    # re-derived figures before comparing, so a manifest built from unsuppressed
    # ones would drift for a reason that has nothing to do with this test.
    out = tmp_path / "out"
    run_args = ["run", "--config", str(HOUSING), "--out", str(out)]
    assert main([*run_args, "--reproducible", "--approved-by", "CI"]) == 0
    capsys.readouterr()
    exported = json.loads((out / "receipts.json").read_text(encoding="utf-8"))
    exported["schema_version"] = "3.0"
    relabelled = tmp_path / "receipts.json"
    relabelled.write_text(json.dumps(exported, indent=2, sort_keys=True), encoding="utf-8")

    assert main(["verify", "--config", str(HOUSING), "--receipts", str(relabelled)]) == 1
    captured = capsys.readouterr()

    assert "verify: FAIL" in captured.err
    assert "schema_version" in captured.err
    assert "does not match the data" not in captured.err
    # The receipt count stays honest under a failing document check.
    receipts = exported["receipts"]
    assert (
        f"receipts checked: {len(receipts)} (re-derived {len(receipts)}, drift 0)" in captured.out
    )


def test_verify_json_separates_receipts_from_manifest_descriptors(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The machine-readable payload carries the same distinction, additively.

    `n_ok` and `drift` keep their old meaning -- totals across both kinds -- so a
    script reading them still works. What is new is that a script can now ask for
    the receipt count without having to know which `metric_id` values are secretly
    descriptors.
    """

    out = tmp_path / "out"
    assert (
        main(
            [
                "run",
                "--config",
                str(HOUSING),
                "--out",
                str(out),
                "--reproducible",
                "--approved-by",
                "CI",
            ]
        )
        == 0
    )
    capsys.readouterr()

    assert (
        main(
            ["verify", "--config", str(HOUSING), "--receipts", str(out / "receipts.json"), "--json"]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    stored = json.loads((out / "receipts.json").read_text(encoding="utf-8"))["receipts"]

    assert payload["receipts_checked"] == len(stored)
    assert payload["receipts_ok"] == len(stored)
    assert payload["receipts_drift"] == 0
    assert payload["manifest_checks"] == 2
    assert payload["manifest_checks_failed"] == 0
    # The totals are unchanged, and are larger than the receipt count.
    assert payload["n_ok"] == len(payload["checks"]) == len(stored) + 2
    kinds = {check["metric_id"]: check["kind"] for check in payload["checks"]}
    assert kinds["schema_version"] == "manifest"
    assert kinds["hash"] == "manifest"
    assert all(kinds[receipt["metric_id"]] == "receipt" for receipt in stored)
