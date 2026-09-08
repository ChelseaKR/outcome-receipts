"""A batch of specs, and the index an auditor enters the portfolio through.

Two things are being pinned here. The batch runs every spec through the ordinary
export path, so a spec that fails the gate stops it and leaves no record behind;
and the index is composed from what those exports already proved, so a bundle
edited after the batch stops verifying and says which one.

The shared-figure table is where the project's three-state discipline has to
hold across reports rather than within one. A withheld cell is not a
disagreement with a published number, and it is certainly not a zero; two
reports counting different things are not comparable at all. Only two reports
that count the same thing and publish different numbers contradict each other,
and that is the only case the table says so about.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from outcome_receipts.bundle import bundle_manifest
from outcome_receipts.cli import main
from outcome_receipts.portfolio import (
    AGREES,
    DEFINITION_DIFFERS,
    NOT_COMPARABLE,
    VALUE_DIFFERS,
    shared_figures,
)

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"

_SPEC = """
schema_version = "1.0"
[data]
path = "services.csv"
[report]
title = "{title}"
template = "The program served {{served}} clients."
[metrics.served]
description = "Clients served"
definition = "{definition}"
unit = "count"
value_sql = "SELECT COUNT(DISTINCT client_id) FROM data"
slice_sql = "SELECT client_id FROM data"
"""


def _spec(directory: Path, *, title: str, definition: str, rows: int = 30) -> Path:
    """A one-metric spec over ``rows`` synthetic clients.

    Thirty rows by default so the figure clears the suppression threshold and the
    report publishes a number; a caller that wants a withheld cell passes fewer.
    """

    directory.mkdir(parents=True, exist_ok=True)
    (directory / "services.csv").write_text(
        "\n".join(["client_id"] + [f"p{i}" for i in range(rows)]) + "\n", encoding="utf-8"
    )
    config = directory / "report.toml"
    config.write_text(_SPEC.format(title=title, definition=definition), encoding="utf-8")
    return config


def _batch(out: Path, *specs: Path, extra: tuple[str, ...] = ()) -> int:
    argv = ["portfolio", "--specs", *[str(spec) for spec in specs]]
    argv += ["--out", str(out), "--approved-by", "A. Reviewer", "--reproducible", *extra]
    return main(argv)


def _verify(out: Path, *extra: str) -> int:
    return main(["portfolio-verify", "--dir", str(out), "--reproducible", *extra])


def _example(tmp_path: Path, name: str) -> Path:
    target = tmp_path / name
    shutil.copytree(EXAMPLES / name, target)
    return target / "report.toml"


# --------------------------------------------------------------------------
# The batch
# --------------------------------------------------------------------------


def test_the_batch_records_every_report_it_exported(tmp_path: Path) -> None:
    grant = _example(tmp_path, "grant-report")
    board = _example(tmp_path, "board-report")
    out = tmp_path / "portfolio"
    assert _batch(out, grant, board) == 0

    record = json.loads((out / "portfolio.json").read_text(encoding="utf-8"))
    directories = [report["directory"] for report in record["reports"]]
    assert directories == ["board-report", "grant-report"], "reports are ordered by spec path"
    for report in record["reports"]:
        assert report["approved_by"] == "A. Reviewer"
        assert len(report["bundle_digest"]) == 64
        assert report["signed"] is False
        assert (out / report["directory"] / "receipts.json").is_file()


def test_a_multi_template_spec_contributes_one_row_per_funder_format(tmp_path: Path) -> None:
    # A spec with [[report.templates]] writes one bundle per format. Each of
    # those is a report an auditor holds, so each is a row.
    multi = _example(tmp_path, "multi-funder")
    out = tmp_path / "portfolio"
    assert _batch(out, multi) == 0

    record = json.loads((out / "portfolio.json").read_text(encoding="utf-8"))
    assert [report["directory"] for report in record["reports"]] == [
        "multi-funder/funder-a",
        "multi-funder/funder-b",
    ]
    assert len({report["ledger_index"] for report in record["reports"]}) == 2


def test_every_export_appends_to_one_shared_ledger(tmp_path: Path) -> None:
    grant = _example(tmp_path, "grant-report")
    board = _example(tmp_path, "board-report")
    out = tmp_path / "portfolio"
    assert _batch(out, grant, board) == 0

    ledger = out / "export-ledger.jsonl"
    assert len(ledger.read_text(encoding="utf-8").splitlines()) == 2
    assert main(["verify-ledger", "--ledger", str(ledger)]) == 0


def test_a_spec_that_fails_the_gate_aborts_the_batch_and_writes_no_record(
    tmp_path: Path,
) -> None:
    good = _spec(tmp_path / "good", title="Good", definition="Clients, counted once.")
    broken = _spec(tmp_path / "broken", title="Broken", definition="Clients, counted once.")
    broken.write_text(
        broken.read_text(encoding="utf-8").replace(
            "The program served {served} clients.",
            "The program served {served} clients, and 999 more besides.",
        ),
        encoding="utf-8",
    )
    out = tmp_path / "portfolio"
    # 2 is the grounding gate's own code, returned unchanged: the batch does not
    # translate a spec's refusal into a batch-shaped one.
    assert _batch(out, broken, good) == 2
    assert not (out / "portfolio.json").exists()
    assert not (out / "index.html").exists()


def test_the_same_spec_twice_is_refused(tmp_path: Path) -> None:
    spec = _spec(tmp_path / "one", title="One", definition="Clients, counted once.")
    out = tmp_path / "portfolio"
    assert _batch(out, spec, spec) == 1
    assert not (out / "portfolio.json").exists()


def test_two_specs_that_would_export_into_one_directory_are_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Both are `<dir>/report.toml`, and both directories are named `shared`.
    first = _spec(tmp_path / "a" / "shared", title="First", definition="Clients.")
    second = _spec(tmp_path / "b" / "shared", title="Second", definition="Clients.")
    out = tmp_path / "portfolio"
    assert _batch(out, first, second) == 1
    assert "would both export into 'shared'" in capsys.readouterr().err


def test_the_batch_honours_a_spec_approval_policy(tmp_path: Path) -> None:
    # The batch runs `run` itself, so a spec's [approval] policy applies to it
    # exactly as it does to a single export.
    spec = _spec(tmp_path / "dual", title="Dual", definition="Clients, counted once.")
    spec.write_text(
        spec.read_text(encoding="utf-8") + '\n[approval]\nrequired = ["program", "finance"]\n',
        encoding="utf-8",
    )
    out = tmp_path / "portfolio"
    assert _batch(out, spec) == 3
    assert not (out / "portfolio.json").exists()

    assert (
        main(
            [
                "portfolio",
                "--specs",
                str(spec),
                "--out",
                str(out),
                "--reproducible",
                "--approve",
                "program:A. Lee",
                "--approve",
                "finance:B. Cruz",
            ]
        )
        == 0
    )
    record = json.loads((out / "portfolio.json").read_text(encoding="utf-8"))
    assert record["reports"][0]["approved_by"] == "A. Lee (program), B. Cruz (finance)"


# --------------------------------------------------------------------------
# The index
# --------------------------------------------------------------------------


def test_the_index_has_a_verified_row_per_report(tmp_path: Path) -> None:
    specs = [
        _spec(tmp_path / "alpha", title="Alpha report", definition="Clients, counted once."),
        _spec(tmp_path / "beta", title="Beta report", definition="Clients, counted once."),
        _spec(tmp_path / "gamma", title="Gamma report", definition="Clients, counted once."),
        _spec(tmp_path / "delta", title="Delta report", definition="Clients, counted once."),
    ]
    out = tmp_path / "portfolio"
    assert _batch(out, *specs) == 0
    assert _verify(out) == 0

    page = (out / "index.html").read_text(encoding="utf-8")
    assert page.count("Verified") == 4
    assert "Did not verify" not in page
    for title in ("Alpha report", "Beta report", "Gamma report", "Delta report"):
        assert title in page
    assert "4 of 4 report(s) re-verified" in page
    assert "<script" not in page


def test_a_bundle_edited_after_the_batch_shows_as_failed(tmp_path: Path) -> None:
    spec = _spec(tmp_path / "one", title="One", definition="Clients, counted once.")
    other = _spec(tmp_path / "two", title="Two", definition="Clients, counted once.")
    out = tmp_path / "portfolio"
    assert _batch(out, spec, other) == 0

    report = out / "one" / "report.md"
    report.write_text(report.read_text(encoding="utf-8") + "\nA line nobody signed off.\n")
    assert _verify(out) == 1

    page = (out / "index.html").read_text(encoding="utf-8")
    assert "Did not verify" in page
    assert "Verified" in page, "the untouched report still verifies"


def _reseal(bundle_dir: Path) -> None:
    """Make a bundle internally consistent again after an artifact was edited.

    Re-hashes the edited artifact into the receipts manifest's ``artifacts``
    block, then re-seals ``bundle.json`` over the resulting members. Everything
    inside the directory now agrees with everything else, which is exactly the
    state the digest recorded by the batch exists to refuse.
    """

    manifest_path = bundle_dir / "receipts.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifacts"] = {
        name: hashlib.sha256((bundle_dir / name).read_bytes()).hexdigest()
        for name in manifest["artifacts"]
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    members = {
        path.relative_to(bundle_dir).as_posix(): path.read_bytes()
        for path in sorted(bundle_dir.rglob("*"))
        if path.is_file() and path.name != "bundle.json"
    }
    (bundle_dir / "bundle.json").write_text(bundle_manifest(members), encoding="utf-8")


def test_a_re_sealed_bundle_is_caught_by_the_digest_the_batch_recorded(
    tmp_path: Path,
) -> None:
    """Only the recorded digest can refuse a bundle that was made consistent again.

    The first version of this test set ``bundle_digest`` to a run of zeroes and
    left everything else alone, so the sealed-bundle check refused it before the
    recorded digest was ever consulted. A control that removed the recorded-digest
    comparison left the whole file green, which is what exposed the fixture: it
    sat where the failure it was meant to prove is impossible.
    """

    spec = _spec(tmp_path / "one", title="One", definition="Clients, counted once.")
    out = tmp_path / "portfolio"
    assert _batch(out, spec) == 0

    bundle_dir = out / "one"
    report = bundle_dir / "report.md"
    report.write_text(
        report.read_text(encoding="utf-8") + "\nA sentence nobody approved.\n", encoding="utf-8"
    )
    _reseal(bundle_dir)

    # Everything inside the directory now agrees: the artifact digests match the
    # files, and the seal matches the members.
    assert main(["verify-bundle", "--dir", str(bundle_dir)]) == 0

    assert _verify(out) == 1
    page = (out / "index.html").read_text(encoding="utf-8")
    assert "Did not verify" in page
    assert "recorded when the batch ran" in page


def test_a_missing_bundle_is_a_failed_row_not_an_aborted_run(tmp_path: Path) -> None:
    first = _spec(tmp_path / "one", title="One", definition="Clients, counted once.")
    second = _spec(tmp_path / "two", title="Two", definition="Clients, counted once.")
    out = tmp_path / "portfolio"
    assert _batch(out, first, second) == 0

    shutil.rmtree(out / "one")
    assert _verify(out) == 1
    page = (out / "index.html").read_text(encoding="utf-8")
    assert "Did not verify" in page
    assert "Two" in page, "one broken bundle must not hide the state of the others"


def test_verify_refuses_a_directory_with_no_portfolio_record(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # A verifier that read no reports has verified nothing, and must not say PASS.
    empty = tmp_path / "empty"
    empty.mkdir()
    assert _verify(empty) == 1
    assert "no portfolio record" in capsys.readouterr().err


def test_verify_refuses_a_record_that_names_no_reports(tmp_path: Path) -> None:
    directory = tmp_path / "portfolio"
    directory.mkdir()
    (directory / "portfolio.json").write_text('{"reports": []}\n', encoding="utf-8")
    assert _verify(directory) == 1
    assert not (directory / "index.html").exists()


def test_the_index_is_the_same_whichever_order_the_specs_were_given(tmp_path: Path) -> None:
    # Two orderings of the same input, not two runs of one ordering: the second
    # proves nothing about ordering, because it iterates the same list.
    def _build(name: str, order: tuple[Path, ...]) -> str:
        out = tmp_path / name
        assert _batch(out, *order) == 0
        assert _verify(out) == 0
        return (out / "index.html").read_text(encoding="utf-8")

    specs = tuple(
        _spec(tmp_path / letter, title=f"Report {letter}", definition="Clients, counted once.")
        for letter in ("a", "b", "c")
    )
    assert _build("forward", specs) == _build("reversed", tuple(reversed(specs)))


def test_the_index_renders_in_spanish(tmp_path: Path) -> None:
    spec = _spec(tmp_path / "uno", title="Informe", definition="Clientes, contados una vez.")
    out = tmp_path / "portfolio"
    assert _batch(out, spec, extra=("--locale", "es")) == 0
    assert _verify(out, "--locale", "es") == 0
    page = (out / "index.html").read_text(encoding="utf-8")
    assert '<html lang="es">' in page
    assert "Cartera de informes" in page
    assert "Verificado" in page


def test_the_json_summary_names_every_report_and_its_verdict(tmp_path: Path) -> None:
    spec = _spec(tmp_path / "one", title="One", definition="Clients, counted once.")
    out = tmp_path / "portfolio"
    assert _batch(out, spec, extra=("--json",)) == 0
    assert _verify(out, "--json") == 0


# --------------------------------------------------------------------------
# Shared figures: where the three-state discipline has to hold across reports
# --------------------------------------------------------------------------


def _receipt(
    metric_id: str, definition: str, display: str, *, suppressed: bool = False
) -> dict[str, object]:
    return {
        "metric_id": metric_id,
        "definition": definition,
        "display": display,
        "suppressed": suppressed,
    }


def _manifest(*receipts: dict[str, object]) -> dict[str, object]:
    return {"receipts": list(receipts)}


def test_a_metric_only_one_report_states_is_not_shared() -> None:
    shared = shared_figures(
        [
            ("A", _manifest(_receipt("served", "Clients.", "30"))),
            ("B", _manifest(_receipt("exited", "Exits.", "12"))),
        ]
    )
    assert shared == ()


def test_two_reports_that_agree_are_reported_as_agreeing() -> None:
    shared = shared_figures(
        [
            ("A", _manifest(_receipt("served", "Clients.", "30"))),
            ("B", _manifest(_receipt("served", "Clients.", "30"))),
        ]
    )
    assert [(figure.metric_id, figure.status) for figure in shared] == [("served", AGREES)]


def test_the_same_metric_id_with_different_definitions_is_flagged() -> None:
    shared = shared_figures(
        [
            ("A", _manifest(_receipt("served", "Clients in the grant period.", "30"))),
            ("B", _manifest(_receipt("served", "Clients in the fiscal year.", "30"))),
        ]
    )
    assert shared[0].status == DEFINITION_DIFFERS
    assert shared[0].definition == "", "no single definition can be shown for a disagreement"


def test_the_same_definition_with_different_values_is_flagged() -> None:
    shared = shared_figures(
        [
            ("A", _manifest(_receipt("served", "Clients.", "30"))),
            ("B", _manifest(_receipt("served", "Clients.", "31"))),
        ]
    )
    assert shared[0].status == VALUE_DIFFERS


def test_a_withheld_cell_is_not_a_disagreement_and_not_a_zero() -> None:
    shared = shared_figures(
        [
            ("A", _manifest(_receipt("served", "Clients.", "30"))),
            ("B", _manifest(_receipt("served", "Clients.", "[SUPPRESSED]", suppressed=True))),
        ]
    )
    assert shared[0].status == NOT_COMPARABLE
    assert dict(shared[0].values)["B"] == "[SUPPRESSED]"
    assert "0" not in dict(shared[0].values)["B"]


def test_a_definition_disagreement_outranks_a_withheld_cell() -> None:
    # Two reports counting different things are not comparable whatever either
    # of them published, so the definition disagreement is what a reader needs.
    shared = shared_figures(
        [
            ("A", _manifest(_receipt("served", "Clients in the grant period.", "30"))),
            (
                "B",
                _manifest(
                    _receipt(
                        "served", "Clients in the fiscal year.", "[SUPPRESSED]", suppressed=True
                    )
                ),
            ),
        ]
    )
    assert shared[0].status == DEFINITION_DIFFERS


def test_shared_figures_are_ordered_by_metric_id() -> None:
    shared = shared_figures(
        [
            ("A", _manifest(_receipt("zeta", "z", "1"), _receipt("alpha", "a", "1"))),
            ("B", _manifest(_receipt("alpha", "a", "1"), _receipt("zeta", "z", "1"))),
        ]
    )
    assert [figure.metric_id for figure in shared] == ["alpha", "zeta"]


def test_a_manifest_with_no_receipts_list_contributes_nothing() -> None:
    shared = shared_figures([("A", {"receipts": "not a list"}), ("B", _manifest())])
    assert shared == ()


def test_a_real_withheld_figure_reaches_the_index_as_the_marker(tmp_path: Path) -> None:
    # End to end rather than from a hand-built manifest: four clients is below
    # the suppression threshold, so one report withholds the cell the other
    # publishes, and the index has to say so without inventing a comparison.
    published = _spec(tmp_path / "big", title="Big", definition="Clients, counted once.")
    withheld = _spec(tmp_path / "small", title="Small", definition="Clients, counted once.", rows=4)
    out = tmp_path / "portfolio"
    assert _batch(out, published, withheld) == 0
    assert _verify(out) == 0

    page = (out / "index.html").read_text(encoding="utf-8")
    assert "Withheld in at least one report" in page
    assert "[SUPPRESSED]" in page


# --------------------------------------------------------------------------
# A record that cannot be read must not read as a portfolio with no problems.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("record", "expected"),
    [
        ("not json at all", "cannot be read as a portfolio record"),
        ('["reports"]', "portfolio record is not an object"),
        ('{"reports": "one"}', "names no reports"),
        ('{"reports": ["one"]}', "a report entry is not an object"),
        ('{"reports": [{"spec": "a.toml"}]}', "is missing"),
    ],
)
def test_an_unreadable_portfolio_record_is_refused_and_says_why(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], record: str, expected: str
) -> None:
    directory = tmp_path / "portfolio"
    directory.mkdir()
    (directory / "portfolio.json").write_text(record, encoding="utf-8")
    assert _verify(directory) == 1
    assert expected in capsys.readouterr().err
    assert not (directory / "index.html").exists()


def test_a_receipts_entry_that_is_not_an_object_is_skipped_not_read() -> None:
    shared = shared_figures(
        [
            ("A", {"receipts": ["not an object", _receipt("served", "Clients.", "30")]}),
            ("B", _manifest(_receipt("served", "Clients.", "30"))),
        ]
    )
    assert [(figure.metric_id, figure.status) for figure in shared] == [("served", AGREES)]


def test_the_json_summary_carries_the_shared_figure_table(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    first = _spec(tmp_path / "one", title="One", definition="Clients in the grant period.")
    second = _spec(tmp_path / "two", title="Two", definition="Clients in the fiscal year.")
    out = tmp_path / "portfolio"
    assert _batch(out, first, second) == 0
    capsys.readouterr()
    assert _verify(out, "--json") == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert [report["title"] for report in payload["reports"]] == ["One", "Two"]
    assert payload["shared_figures"] == [
        {
            "metric_id": "served",
            "status": DEFINITION_DIFFERS,
            "definition": "",
            "values": [
                {"report": "One", "display": "30"},
                {"report": "Two", "display": "30"},
            ],
        }
    ]
