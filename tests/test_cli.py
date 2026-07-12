"""The CLI's machine-readable output and its exit-code contract.

A caller that scripts ``receipts`` needs two guarantees: a stable JSON shape under
``--json`` and an exit code that means the same thing every run. These tests pin
both. They assert the JSON parses and carries the documented keys, that ``--json``
never changes the exit code (it is presentational), and that each command returns
the single-sourced constant the README documents: ``EXIT_OK`` on success,
``EXIT_VERIFY_FAIL`` when an audit or verify fails closed, and ``EXIT_GATE_FAIL``
when the grounding gate refuses to export. The human-readable path is pinned too,
so adding JSON did not silently change what a person sees.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from outcome_receipts.cli import (
    EXIT_APPROVAL_FAIL,
    EXIT_GATE_FAIL,
    EXIT_OK,
    EXIT_VERIFY_FAIL,
    main,
)

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
HOUSING = str(EXAMPLES / "housing-demo" / "report.toml")
GRANT = str(EXAMPLES / "grant-report" / "report.toml")


def test_run_json_parses_and_reports_a_passing_gate(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "out"
    run_args = ["run", "--config", HOUSING, "--out", str(out)]
    run_args += ["--reproducible", "--approved-by", "CI", "--json"]
    code = main(run_args)
    assert code == EXIT_OK

    payload = json.loads(capsys.readouterr().out)
    assert payload["command"] == "run"
    assert payload["gate_pass"] is True
    assert payload["figures"] == 4
    assert payload["narrative"] == {"total": 4, "bound": 4, "unbound": 0}
    assert payload["claims"] == {"total": 0, "bound": 0, "unbound": 0}
    assert payload["unbound"] == []
    assert payload["outputs"]["report"] == str(out / "report.md")
    assert payload["outputs"]["receipts"] == str(out / "receipts.json")
    assert payload["outputs"]["trace"] == str(out / "trace.html")
    assert payload["outputs"]["charts"] is None


def test_run_json_flag_before_subcommand_is_equivalent(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "out"
    run_args = ["--json", "run", "--config", HOUSING, "--out", str(out)]
    run_args += ["--reproducible", "--approved-by", "CI"]
    code = main(run_args)
    assert code == EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    assert payload["command"] == "run"
    assert payload["gate_pass"] is True


def test_run_json_charts_report_a_chart_output_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "grant"
    run_args = ["run", "--config", GRANT, "--out", str(out)]
    run_args += ["--reproducible", "--approved-by", "CI", "--json"]
    code = main(run_args)
    assert code == EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    assert payload["claims"]["total"] > 0
    assert payload["outputs"]["charts"] == str(out / "charts")


def test_run_human_output_still_prints_the_existing_lines(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "out"
    run_args = ["run", "--config", HOUSING, "--out", str(out)]
    run_args += ["--reproducible", "--approved-by", "CI"]
    code = main(run_args)
    assert code == EXIT_OK
    captured = capsys.readouterr().out
    assert "figures computed: 4" in captured
    assert "grounding gate: PASS" in captured
    assert str(out / "report.md") in captured
    # The human path prints prose, never a JSON object.
    with pytest.raises(json.JSONDecodeError):
        json.loads(captured)


def _drafted_narrative() -> str:
    """The housing demo's drafted narrative, fully grounded by construction."""

    from outcome_receipts.clock import FixedClock
    from outcome_receipts.config import load_spec
    from outcome_receipts.draft import draft
    from outcome_receipts.engine import compute_figures, read_csv

    spec = load_spec(HOUSING)
    rows = read_csv(spec.data_path)
    figures = compute_figures(rows, spec.report.metrics, clock=FixedClock())
    return draft(spec.report, figures)


def test_audit_of_a_grounded_narrative_exits_ok(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    narrative = tmp_path / "narrative.md"
    narrative.write_text(_drafted_narrative(), encoding="utf-8")

    code = main(["audit", "--config", HOUSING, "--narrative", str(narrative), "--json"])
    assert code == EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    assert payload["command"] == "audit"
    assert payload["ok"] is True
    assert payload["bound"] == payload["total"]
    assert payload["unbound"] == []


def test_audit_of_an_ungrounded_narrative_fails_closed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    narrative = tmp_path / "draft.md"
    narrative.write_text("In 2024 we supported 42 families.", encoding="utf-8")

    code = main(["audit", "--config", HOUSING, "--narrative", str(narrative), "--json"])
    assert code == EXIT_VERIFY_FAIL
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert {span["text"] for span in payload["unbound"]} == {"2024", "42"}
    # Each unbound span is a plain dict, not a dumped dataclass.
    assert set(payload["unbound"][0]) == {"text", "start", "end"}


def test_verify_of_a_fresh_manifest_exits_ok(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "out"
    run_args = ["run", "--config", HOUSING, "--out", str(out)]
    run_args += ["--reproducible", "--approved-by", "CI"]
    assert main(run_args) == EXIT_OK
    capsys.readouterr()

    receipts = out / "receipts.json"
    code = main(["verify", "--config", HOUSING, "--receipts", str(receipts), "--json"])
    assert code == EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    assert payload["command"] == "verify"
    assert payload["ok"] is True
    assert payload["drift"] == 0
    assert payload["n_ok"] == len(payload["checks"])


def test_verify_drift_fails_with_the_documented_code(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "out"
    run_args = ["run", "--config", HOUSING, "--out", str(out)]
    run_args += ["--reproducible", "--approved-by", "CI"]
    assert main(run_args) == EXIT_OK
    capsys.readouterr()

    receipts = out / "receipts.json"
    manifest = json.loads(receipts.read_text(encoding="utf-8"))
    manifest["receipts"][0]["value"] = -1.0
    receipts.write_text(json.dumps(manifest), encoding="utf-8")

    code = main(["verify", "--config", HOUSING, "--receipts", str(receipts), "--json"])
    assert code == EXIT_VERIFY_FAIL
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["drift"] >= 1
    assert any(not check["ok"] for check in payload["checks"])


def test_run_gate_failure_uses_the_gate_exit_code(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    # Force an unbound number into the drafted narrative so the gate refuses to
    # export. The run must exit with EXIT_GATE_FAIL (2), distinct from a verify
    # failure (1), and write no report.
    from collections.abc import Sequence

    import outcome_receipts.cli as cli
    from outcome_receipts.draft import draft as real_draft
    from outcome_receipts.models import Figure, ReportSpec

    def _tampered_draft(spec: ReportSpec, figures: Sequence[Figure]) -> str:
        return real_draft(spec, figures) + " We also served 99999 ghosts."

    monkeypatch.setattr(cli, "draft", _tampered_draft)

    out = tmp_path / "out"
    run_args = ["run", "--config", HOUSING, "--out", str(out)]
    run_args += ["--reproducible", "--approved-by", "CI", "--json"]
    code = main(run_args)
    assert code == EXIT_GATE_FAIL
    payload = json.loads(capsys.readouterr().out)
    assert payload["gate_pass"] is False
    assert any(span["text"] == "99999" for span in payload["unbound"])
    assert payload["outputs"]["report"] is None
    assert not (out / "report.md").exists()


def test_eval_json_reports_the_gate(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["eval", "--config", HOUSING, "--json"])
    assert code == EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    assert payload["command"] == "eval"
    assert payload["gate_pass"] is True
    assert payload["n_unbound"] == 0
    assert len(payload["grounding_ci"]) == 2


def test_exit_codes_are_distinct_constants() -> None:
    assert (EXIT_OK, EXIT_VERIFY_FAIL, EXIT_GATE_FAIL, EXIT_APPROVAL_FAIL) == (0, 1, 2, 3)


def test_run_json_without_approver_aborts_fail_closed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Under --json there is no interactive prompt, so a missing --approved-by
    # must abort with the approval exit code, emit one JSON object with a null
    # approval, and write nothing.
    out = tmp_path / "out"
    code = main(["run", "--config", HOUSING, "--out", str(out), "--reproducible", "--json"])
    assert code == EXIT_APPROVAL_FAIL
    payload = json.loads(capsys.readouterr().out)
    assert payload["gate_pass"] is True
    assert payload["approval"] is None
    assert payload["outputs"]["report"] is None
    assert not out.exists()


def test_run_json_records_the_approval(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "out"
    run_args = ["run", "--config", HOUSING, "--out", str(out)]
    run_args += ["--reproducible", "--approved-by", "Jane Doe", "--json"]
    code = main(run_args)
    assert code == EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    assert payload["approval"]["approved_by"] == "Jane Doe"
    assert payload["approval"]["approved_at"]


def test_run_json_records_the_ledger_entry(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "out"
    ledger = tmp_path / "ledger.jsonl"
    code = main(
        [
            "run",
            "--config",
            HOUSING,
            "--out",
            str(out),
            "--reproducible",
            "--ledger",
            str(ledger),
            "--approved-by",
            "CI",
            "--json",
        ]
    )
    assert code == EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    assert payload["ledger"]["path"] == str(ledger)
    assert payload["ledger"]["index"] == 0
    assert len(payload["ledger"]["entry_hash"]) == 64
    assert ledger.exists()


def test_run_gate_failure_appends_no_ledger_entry(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from collections.abc import Sequence

    import outcome_receipts.cli as cli
    from outcome_receipts.draft import draft as real_draft
    from outcome_receipts.models import Figure, ReportSpec

    def _tampered_draft(spec: ReportSpec, figures: Sequence[Figure]) -> str:
        return real_draft(spec, figures) + " We also served 99999 ghosts."

    monkeypatch.setattr(cli, "draft", _tampered_draft)

    out = tmp_path / "out"
    ledger = tmp_path / "ledger.jsonl"
    code = main(
        [
            "run",
            "--config",
            HOUSING,
            "--out",
            str(out),
            "--reproducible",
            "--ledger",
            str(ledger),
            "--approved-by",
            "CI",
            "--json",
        ]
    )
    assert code == EXIT_GATE_FAIL
    payload = json.loads(capsys.readouterr().out)
    assert payload["ledger"] is None
    assert not ledger.exists()


def test_verify_ledger_json_passes_on_an_intact_chain(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "out"
    ledger = tmp_path / "ledger.jsonl"
    assert (
        main(
            [
                "run",
                "--config",
                HOUSING,
                "--out",
                str(out),
                "--reproducible",
                "--ledger",
                str(ledger),
                "--approved-by",
                "CI",
            ]
        )
        == EXIT_OK
    )
    capsys.readouterr()

    code = main(["verify-ledger", "--ledger", str(ledger), "--json"])
    assert code == EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    assert payload["command"] == "verify-ledger"
    assert payload["ok"] is True
    assert payload["ledger"] == str(ledger)
    assert payload["problems"] == []


def test_verify_ledger_json_fails_on_a_tampered_chain(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "out"
    ledger = tmp_path / "ledger.jsonl"
    assert (
        main(
            [
                "run",
                "--config",
                HOUSING,
                "--out",
                str(out),
                "--reproducible",
                "--ledger",
                str(ledger),
                "--approved-by",
                "CI",
            ]
        )
        == EXIT_OK
    )
    capsys.readouterr()

    record = json.loads(ledger.read_text(encoding="utf-8").splitlines()[0])
    record["report_title"] = "tampered"
    ledger.write_text(json.dumps(record) + "\n", encoding="utf-8")

    code = main(["verify-ledger", "--ledger", str(ledger), "--json"])
    assert code == EXIT_VERIFY_FAIL
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["problems"]


def test_verify_bundle_json_reports_receipts_artifacts_and_grounding(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "out"
    run_args = ["run", "--config", HOUSING, "--out", str(out)]
    run_args += ["--reproducible", "--approved-by", "CI"]
    assert main(run_args) == EXIT_OK
    capsys.readouterr()

    code = main(["verify", "--config", HOUSING, "--bundle", str(out), "--json"])
    assert code == EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    assert payload["command"] == "verify"
    assert payload["mode"] == "bundle"
    assert payload["ok"] is True
    assert payload["drift"] == 0
    assert payload["artifacts"]
    assert all(artifact["ok"] for artifact in payload["artifacts"])
    assert payload["grounding"]["unbound"] == []


def test_init_json_carries_the_scaffolded_spec(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data = EXAMPLES / "housing-demo" / "services.csv"
    spec_path = tmp_path / "report.toml"
    code = main(["init", "--data", str(data), "--out", str(spec_path), "--json"])
    assert code == EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    assert payload["command"] == "init"
    assert payload["out"] == str(spec_path)
    assert payload["spec_toml"] == spec_path.read_text(encoding="utf-8")
