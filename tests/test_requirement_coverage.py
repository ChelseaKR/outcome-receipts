"""Export must prove it answered the bound requirement set, or say why it cannot.

Before this, ``map`` produced per-requirement candidates that could come back
``blocked``, ``requirements-diff`` compared two requirement documents by stable
id, and ``contract-check`` refused a milestone whose metric was absent — and
nothing connected a requirement set to an export. A spec that simply omitted a
required metric ran, grounded, was approved, and exported a report that was
fully receipted and silently incomplete.

The tests here are written against the shape of that failure. The one that
matters most is
``test_a_spec_that_omits_a_required_metric_refuses_and_writes_nothing``: it is
the exact run that used to succeed.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

import outcome_receipts.cli as cli
from outcome_receipts.config import load_spec
from outcome_receipts.coverage import (
    STATUS_ANSWERED,
    STATUS_UNANSWERABLE,
    STATUS_UNANSWERED,
    STATUS_WITHHELD,
    CoverageError,
    RequirementCoverage,
    RequirementRecord,
    build_requirement_coverage,
)
from outcome_receipts.models import Figure
from outcome_receipts.report import render_requirement_coverage

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
BOUND = EXAMPLES / "requirement-coverage"
BOUND_SPEC = str(BOUND / "report.toml")
HOUSING = str(EXAMPLES / "housing-demo" / "report.toml")

EXIT_OK = cli.EXIT_OK
EXIT_COVERAGE_FAIL = cli.EXIT_COVERAGE_FAIL
EXIT_VERIFY_FAIL = cli.EXIT_VERIFY_FAIL
main = cli.main


@pytest.fixture
def bound_example(tmp_path: Path) -> Path:
    destination = tmp_path / "requirement-coverage"
    shutil.copytree(BOUND, destination)
    return destination


def _edit(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    assert old in text, old
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def _export(config: str, out: Path, *, ledger: Path | None = None) -> int:
    return main(
        [
            "run",
            "--config",
            config,
            "--out",
            str(out),
            "--ledger",
            str(ledger or (out / "export-ledger.jsonl")),
            "--approved-by",
            "Coverage test",
            "--reproducible",
        ]
    )


def test_exit_codes_stay_single_sourced_and_coverage_is_its_own_code() -> None:
    """Coverage failure is not a grounding failure and must not share its code.

    A run can bind every number in its prose to a receipt, be approved, and
    still omit a figure the funder required. A caller that saw code 2 would go
    looking for an unbound number that is not there.
    """
    assert (cli.EXIT_OK, cli.EXIT_VERIFY_FAIL, cli.EXIT_GATE_FAIL, cli.EXIT_APPROVAL_FAIL) == (
        0,
        1,
        2,
        3,
    )
    assert cli.EXIT_COVERAGE_FAIL == 4
    assert cli.EXIT_COVERAGE_FAIL not in {
        cli.EXIT_OK,
        cli.EXIT_VERIFY_FAIL,
        cli.EXIT_GATE_FAIL,
        cli.EXIT_APPROVAL_FAIL,
    }


def test_a_bound_spec_exports_and_records_all_four_states(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "out"
    assert _export(BOUND_SPEC, out) == EXIT_OK
    capsys.readouterr()

    manifest = json.loads((out / "receipts.json").read_text(encoding="utf-8"))
    coverage = manifest["requirements"]
    assert coverage["counts"] == {
        STATUS_ANSWERED: 2,
        STATUS_WITHHELD: 1,
        STATUS_UNANSWERABLE: 1,
        STATUS_UNANSWERED: 0,
    }
    statuses = {item["requirement_id"]: item["status"] for item in coverage["requirements"]}
    assert statuses == {
        "R-1": STATUS_ANSWERED,
        "R-2": STATUS_ANSWERED,
        "R-3": STATUS_WITHHELD,
        "R-4": STATUS_UNANSWERABLE,
    }


def test_a_requirement_answered_by_a_suppressed_cell_reads_as_unanswered_nowhere(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`withheld` is answered. It must never render as an absence.

    R-3 is answered by ``permanent_exits``, whose 9 is under the small-cell
    threshold, so the figure is withheld and its value is null. The requirement
    is still answered — a query exists, it ran, and it produced a receipt whose
    cell the privacy policy hides. Reporting that as unanswered would tell a
    funder the organization never measured something it did measure.
    """
    out = tmp_path / "out"
    assert _export(BOUND_SPEC, out) == EXIT_OK
    capsys.readouterr()

    manifest = json.loads((out / "receipts.json").read_text(encoding="utf-8"))
    record = next(
        item for item in manifest["requirements"]["requirements"] if item["requirement_id"] == "R-3"
    )
    assert record["status"] == STATUS_WITHHELD
    assert record["metric_id"] == "permanent_exits"
    assert "null, not zero" in record["detail"]

    receipt = next(item for item in manifest["receipts"] if item["metric_id"] == "permanent_exits")
    assert receipt["suppressed"] is True
    assert receipt["value"] is None


def test_a_spec_that_omits_a_required_metric_refuses_and_writes_nothing(
    bound_example: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The run that used to succeed.

    Dropping the unanswerable declaration leaves R-4 answered by nothing and
    explained by nothing. Before the binding existed this exported a complete,
    fully receipted, silently incomplete report.
    """
    spec_path = bound_example / "report.toml"
    text = spec_path.read_text(encoding="utf-8")
    start = text.index("[[requirements.unanswerable]]")
    spec_path.write_text(text[:start] + text[text.index("[report]") :], encoding="utf-8")

    out = tmp_path / "out"
    assert _export(str(spec_path), out) == EXIT_COVERAGE_FAIL
    captured = capsys.readouterr()
    assert "R-4" in captured.err
    assert "neither answered nor declared unanswerable" in captured.err
    assert not out.exists()


def test_the_refusal_names_the_requirement_in_json_too(
    bound_example: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    spec_path = bound_example / "report.toml"
    text = spec_path.read_text(encoding="utf-8")
    start = text.index("[[requirements.unanswerable]]")
    spec_path.write_text(text[:start] + text[text.index("[report]") :], encoding="utf-8")

    out = tmp_path / "out"
    code = main(
        [
            "run",
            "--config",
            str(spec_path),
            "--out",
            str(out),
            "--ledger",
            str(out / "export-ledger.jsonl"),
            "--approved-by",
            "Coverage test",
            "--reproducible",
            "--json",
        ]
    )
    assert code == EXIT_COVERAGE_FAIL
    payload = json.loads(capsys.readouterr().out)
    # The grounding gate passed. Reporting this as a gate failure would send a
    # caller looking for an unbound number that does not exist.
    assert payload["gate_pass"] is True
    assert payload["requirements"]["counts"][STATUS_UNANSWERED] == 1
    unanswered = [
        item
        for item in payload["requirements"]["requirements"]
        if item["status"] == STATUS_UNANSWERED
    ]
    assert [item["requirement_id"] for item in unanswered] == ["R-4"]
    assert not out.exists()


def _drop_reason(spec_path: Path) -> None:
    text = spec_path.read_text(encoding="utf-8")
    start = text.index('reason = "The HMIS export')
    end = text.index("\n", start)
    spec_path.write_text(text[:start] + 'reason = ""' + text[end:], encoding="utf-8")


def test_an_unanswerable_declaration_with_no_reason_refuses(
    bound_example: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A blocker without a reason is a tool's excuse.

    The blocker still reproduces exactly, so nothing mechanical is wrong with
    this declaration. It is refused because a machine-readable blocker on its
    own says only that the tool could not do it, and never that a person looked.
    """
    spec_path = bound_example / "report.toml"
    _drop_reason(spec_path)
    out = tmp_path / "out"
    assert _export(str(spec_path), out) == EXIT_COVERAGE_FAIL
    captured = capsys.readouterr()
    assert "a reason a person wrote" in captured.err
    assert not out.exists()


def test_a_reason_with_no_blocker_refuses(
    bound_example: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A reason without a blocker is unfalsifiable."""
    spec_path = bound_example / "report.toml"
    _edit(
        spec_path,
        "blocker = \"no source column matches logical field 'return_within_180_days'\"",
        'blocker = ""',
    )
    out = tmp_path / "out"
    assert _export(str(spec_path), out) == EXIT_COVERAGE_FAIL
    assert "a blocker `map` produces" in capsys.readouterr().err
    assert not out.exists()


def test_a_declared_blocker_the_mapper_does_not_produce_refuses(
    bound_example: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The half that makes `unanswerable` falsifiable.

    An operator can write any sentence in `reason`; nothing can check it. The
    `blocker` is different: `receipts map` either produces that exact string for
    this requirement against this data, or it does not. A declaration whose
    blocker the mapper does not produce is an operator waving a requirement
    away, and it is refused — with what the mapper actually said.
    """
    spec_path = bound_example / "report.toml"
    _edit(
        spec_path,
        "blocker = \"no source column matches logical field 'return_within_180_days'\"",
        'blocker = "the data warehouse was unavailable"',
    )
    out = tmp_path / "out"
    assert _export(str(spec_path), out) == EXIT_COVERAGE_FAIL
    captured = capsys.readouterr()
    assert "not one `map` produces" in captured.err
    assert "return_within_180_days" in captured.err
    assert not out.exists()


def test_a_declared_blocker_for_a_requirement_that_maps_cleanly_refuses(
    bound_example: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Declaring a mappable requirement unanswerable is the abuse to stop.

    R-2 maps cleanly, so `map` reports no blocker at all for it. The refusal
    says so in those words rather than only "the blocker does not match", which
    would read as a typo rather than as "this requirement is answerable".
    """
    spec_path = bound_example / "report.toml"
    _edit(
        spec_path,
        '[metrics.housing_enrollments]\nrequirement_id = "R-2"\n',
        "[metrics.housing_enrollments]\n",
    )
    _edit(spec_path, 'requirement_id = "R-4"\nblocker', 'requirement_id = "R-2"\nblocker')
    out = tmp_path / "out"
    assert _export(str(spec_path), out) == EXIT_COVERAGE_FAIL
    captured = capsys.readouterr()
    assert "it maps cleanly" in captured.err
    assert not out.exists()


def test_a_requirement_cannot_be_answered_and_declared_unanswerable_at_once(
    bound_example: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A contradiction the reader could not see, so the tool refuses to pick."""
    spec_path = bound_example / "report.toml"
    _edit(spec_path, 'requirement_id = "R-4"\nblocker', 'requirement_id = "R-1"\nblocker')
    assert _export(str(spec_path), tmp_path / "out") == EXIT_COVERAGE_FAIL
    assert "declared unanswerable and answered by metric" in capsys.readouterr().err


def test_a_metric_naming_an_undeclared_requirement_is_an_authoring_error(
    bound_example: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    spec_path = bound_example / "report.toml"
    _edit(spec_path, 'requirement_id = "R-1"\ndescription', 'requirement_id = "R-9"\ndescription')
    assert _export(str(spec_path), tmp_path / "out") == EXIT_COVERAGE_FAIL
    assert "which" in capsys.readouterr().err


def test_two_metrics_cannot_claim_the_same_requirement(
    bound_example: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    spec_path = bound_example / "report.toml"
    _edit(spec_path, 'requirement_id = "R-2"\ndescription', 'requirement_id = "R-1"\ndescription')
    assert _export(str(spec_path), tmp_path / "out") == EXIT_COVERAGE_FAIL
    assert "claimed by two metrics" in capsys.readouterr().err


def test_a_duplicate_requirement_id_in_the_document_is_refused(
    bound_example: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    document = bound_example / "requirements.json"
    _edit(document, '"requirement_id": "R-2"', '"requirement_id": "R-1"')
    assert _export(str(bound_example / "report.toml"), tmp_path / "out") == EXIT_COVERAGE_FAIL
    assert "duplicate requirement id" in capsys.readouterr().err


def test_editing_the_requirement_document_after_export_fails_verify_naming_the_digest(
    bound_example: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The reason the digest rides in the manifest at all."""
    spec_path = str(bound_example / "report.toml")
    out = tmp_path / "out"
    assert _export(spec_path, out) == EXIT_OK
    capsys.readouterr()
    assert (
        main(["verify", "--config", spec_path, "--bundle", str(out), "--reproducible"]) == EXIT_OK
    )
    recorded = json.loads((out / "receipts.json").read_text(encoding="utf-8"))["requirements"][
        "document_sha256"
    ]
    captured = capsys.readouterr()
    assert f"coverage matches; document sha256 {recorded}" in captured.out

    _edit(
        bound_example / "requirements.json",
        '"description": "Unduplicated clients served"',
        '"description": "Unduplicated households served"',
    )
    code = main(["verify", "--config", spec_path, "--bundle", str(out), "--reproducible"])
    assert code == EXIT_VERIFY_FAIL
    captured = capsys.readouterr()
    assert recorded in captured.err
    assert "does not match" in captured.err


def test_a_spec_that_drops_its_binding_after_export_fails_verify(
    bound_example: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Both directions are real failures, and only one of them is obvious.

    A report exported against a requirement set that has since been removed from
    the spec proves nothing about the set now in force, and its manifest still
    claims coverage of one.
    """
    spec_path = bound_example / "report.toml"
    out = tmp_path / "out"
    assert _export(str(spec_path), out) == EXIT_OK
    capsys.readouterr()

    text = spec_path.read_text(encoding="utf-8")
    start = text.index("\n[requirements]\n") + 1
    spec_path.write_text(text[:start] + text[text.index("[report]") :], encoding="utf-8")
    code = main(["verify", "--config", str(spec_path), "--bundle", str(out), "--reproducible"])
    assert code == EXIT_VERIFY_FAIL
    assert "the spec binds no requirement document" in capsys.readouterr().err


def test_an_unbound_spec_is_byte_identical_to_what_it_exported_before(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The compatibility half. A spec with no `[requirements]` carries no key.

    Not an empty coverage record, not zero counts — the key is absent, because
    such a spec has not answered zero requirements, it has made no coverage
    claim at all. The whole-bundle verifier says "not checked" rather than "ok"
    for the same reason.
    """
    out = tmp_path / "out"
    assert _export(HOUSING, out) == EXIT_OK
    capsys.readouterr()
    manifest = json.loads((out / "receipts.json").read_text(encoding="utf-8"))
    assert "requirements" not in manifest
    assert "Requirement coverage" not in (out / "report.md").read_text(encoding="utf-8")

    assert main(["verify", "--config", HOUSING, "--bundle", str(out), "--reproducible"]) == EXIT_OK
    assert "requirement coverage: not checked" in capsys.readouterr().out


def test_the_coverage_table_renders_in_both_locales(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    reports: dict[str, str] = {}
    for locale, heading in (
        ("en", "## Requirement coverage"),
        ("es", "## Cobertura de requisitos"),
    ):
        out = tmp_path / locale
        assert (
            main(
                [
                    "run",
                    "--config",
                    BOUND_SPEC,
                    "--out",
                    str(out),
                    "--ledger",
                    str(out / "export-ledger.jsonl"),
                    "--approved-by",
                    "Coverage test",
                    "--reproducible",
                    "--locale",
                    locale,
                ]
            )
            == EXIT_OK
        )
        capsys.readouterr()
        reports[locale] = (out / "report.md").read_text(encoding="utf-8")
        assert heading in reports[locale]
        # Every requirement, including the one nothing answered. Telling the
        # funder what was not answered is the point of the table.
        for requirement_id in ("R-1", "R-2", "R-3", "R-4"):
            assert requirement_id in reports[locale]
    assert reports["en"] != reports["es"]
    assert "coverage_heading" not in reports["es"], "the ES catalog fell back to the message id"


def test_the_requirement_document_must_be_readable_and_non_empty(
    bound_example: Path, tmp_path: Path
) -> None:
    document = bound_example / "requirements.json"
    document.write_text('{"requirements": []}', encoding="utf-8")
    spec = load_spec(bound_example / "report.toml")
    assert spec.report.requirements is not None
    assert spec.requirements_path is not None
    with pytest.raises(CoverageError, match="non-empty list"):
        build_requirement_coverage(
            requirements=spec.report.requirements,
            requirements_path=spec.requirements_path,
            data_path=spec.data_path,
            metric_requirements={},
            figures=[],
        )


def test_an_unbound_spec_resolves_no_requirement_path() -> None:
    spec = load_spec(HOUSING)
    assert spec.report.requirements is None
    assert spec.requirements_path is None
    assert all(metric.requirement_id == "" for metric in spec.report.metrics)


def _rewrite_manifest(out: Path, mutate: object) -> None:
    """Edit the exported manifest in place, the way a tamperer would."""

    path = out / "receipts.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    assert callable(mutate)
    mutate(manifest)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda manifest: manifest.pop("requirements"),
            "the manifest carries no coverage record",
        ),
        (
            lambda manifest: manifest.__setitem__("requirements", "R-1 answered"),
            "is not an object",
        ),
        (
            lambda manifest: manifest["requirements"]["requirements"][3].__setitem__(
                "status", STATUS_ANSWERED
            ),
            "does not match the coverage re-derived",
        ),
        (
            lambda manifest: manifest["requirements"]["counts"].__setitem__(STATUS_ANSWERED, 4),
            "does not match the coverage re-derived",
        ),
    ],
)
def test_a_doctored_coverage_record_fails_verify(
    bound_example: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    mutate: object,
    message: str,
) -> None:
    """The digest catches an edited *document*; this catches an edited *record*.

    Rewriting `unanswerable` to `answered`, or inflating the counts, leaves the
    requirement document untouched and its digest matching. The record itself is
    re-derived and compared, so the claim cannot be edited independently of what
    produced it.

    The manifest is rewritten with `indent=2, sort_keys=True` -- the bytes the
    exporter writes -- so `report.md`'s digest check is not what fails here.
    """
    spec_path = str(bound_example / "report.toml")
    out = tmp_path / "out"
    assert _export(spec_path, out) == EXIT_OK
    capsys.readouterr()

    _rewrite_manifest(out, mutate)
    code = main(["verify", "--config", spec_path, "--bundle", str(out), "--reproducible"])
    assert code == EXIT_VERIFY_FAIL
    assert message in capsys.readouterr().err


def test_an_unanswered_record_read_back_from_a_manifest_still_renders() -> None:
    """`unanswered` cannot reach an export, and the renderer must still name it.

    A coverage record loaded from somewhere else -- a doctored manifest, a
    future schema, a caller building one by hand -- can carry the status. A
    renderer that fell through to a blank cell would draw the one state that
    means "this was never answered" as no state at all.
    """
    coverage = RequirementCoverage(
        document_path="requirements.json",
        document_digest="0" * 64,
        records=(
            RequirementRecord(
                requirement_id="R-9",
                description="Something nobody answered",
                status=STATUS_UNANSWERED,
                metric_id=None,
                blocker=None,
                reason=None,
                detail="no metric names this requirement",
            ),
        ),
    )
    rendered = render_requirement_coverage(coverage)
    assert "R-9" in rendered
    assert "Unanswered" in rendered
    assert "| none |" in rendered


def _build(
    bound_example: Path,
    *,
    metric_requirements: Mapping[str, str] | None = None,
    figures: Sequence[Figure] = (),
) -> RequirementCoverage:
    spec = load_spec(bound_example / "report.toml")
    assert spec.report.requirements is not None
    assert spec.requirements_path is not None
    return build_requirement_coverage(
        requirements=spec.report.requirements,
        requirements_path=spec.requirements_path,
        data_path=spec.data_path,
        metric_requirements=metric_requirements or {},
        figures=figures,
    )


@pytest.mark.parametrize(
    ("document", "message"),
    [
        ("not json at all", "could not be read"),
        ('{"requirements": "R-1"}', "non-empty list"),
        ('{"requirements": ["R-1"]}', "must be an object"),
        ('{"requirements": [{"description": "no id"}]}', "no stable requirement_id"),
    ],
)
def test_an_unusable_requirement_document_is_refused_before_anything_is_written(
    bound_example: Path, document: str, message: str
) -> None:
    (bound_example / "requirements.json").write_text(document, encoding="utf-8")
    with pytest.raises(CoverageError, match=message):
        _build(bound_example)


def test_a_declaration_for_a_requirement_the_document_does_not_declare_is_refused(
    bound_example: Path,
) -> None:
    _edit(
        bound_example / "report.toml",
        'requirement_id = "R-4"\nblocker',
        'requirement_id = "R-7"\nblocker',
    )
    with pytest.raises(CoverageError, match="does not declare"):
        _build(bound_example)


def test_the_same_requirement_cannot_be_declared_unanswerable_twice(
    bound_example: Path,
) -> None:
    spec_path = bound_example / "report.toml"
    text = spec_path.read_text(encoding="utf-8")
    start = text.index("[[requirements.unanswerable]]")
    end = text.index("[report]")
    spec_path.write_text(text[:end] + text[start:end] + text[end:], encoding="utf-8")
    with pytest.raises(CoverageError, match="declared unanswerable twice"):
        _build(bound_example)


def test_a_metric_that_produced_no_figure_is_not_quietly_answered(
    bound_example: Path,
) -> None:
    """A binding to a metric that produced nothing is unanswered, not answered.

    The metric names the requirement, so the spec's author believes it is
    covered. Nothing was published for it. Treating the binding itself as the
    answer would let a metric that silently produced no figure satisfy a funder
    requirement.
    """
    coverage = _build(bound_example, metric_requirements={"clients_served": "R-1"})
    record = next(item for item in coverage.records if item.requirement_id == "R-1")
    assert record.status == STATUS_UNANSWERED
    assert "produced no figure" in record.detail
