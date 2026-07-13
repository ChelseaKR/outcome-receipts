"""Merge-blocking: a human sign-off gates every export.

The grounding gate proves each number traces to a receipt; it does not prove a
person reviewed the report before it left. R8 adds that second gate: the export
records a named approver, and refuses to write anything when nobody signed off.
These tests pin that the approver reaches both surfaces a reader trusts — the
report body and the machine-readable manifest — that the gate fails closed off a
TTY, and that it never runs before or instead of the grounding gate.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

import pytest

from outcome_receipts import cli
from outcome_receipts.cli import main
from outcome_receipts.draft import draft
from outcome_receipts.models import Figure, ReportSpec
from outcome_receipts.provenance import Provenance, provenance_record

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
GRANT = EXAMPLES / "grant-report" / "report.toml"


def test_run_with_approved_by_records_the_approver(tmp_path: Path) -> None:
    out = tmp_path / "grant"
    code = main(
        [
            "run",
            "--config",
            str(GRANT),
            "--out",
            str(out),
            "--reproducible",
            "--approved-by",
            "Jane Doe",
        ]
    )
    assert code == 0

    manifest = json.loads((out / "receipts.json").read_text(encoding="utf-8"))
    assert manifest["provenance"]["approved_by"] == "Jane Doe"

    report = (out / "report.md").read_text(encoding="utf-8")
    assert "reviewed and approved for export by Jane Doe" in report


def test_run_without_approver_off_a_tty_aborts_and_writes_nothing(
    tmp_path: Path,
) -> None:
    # pytest runs with stdin not a TTY, so there is nobody to prompt. Without
    # --approved-by the export must fail closed: a nonzero code and no files.
    out = tmp_path / "grant"
    code = main(["run", "--config", str(GRANT), "--out", str(out), "--reproducible"])
    assert code == 3
    assert not out.exists()


def test_grounding_gate_fail_returns_2_before_the_approval_prompt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A stray, ungrounded number must be caught by the grounding gate (exit 2)
    # before the approval gate is ever consulted — approval never bypasses it.
    def _tampered_draft(spec: ReportSpec, figures: Sequence[Figure]) -> str:
        clean = draft(spec, figures)
        return clean + " We also served 999 extra clients."

    monkeypatch.setattr(cli, "draft", _tampered_draft)

    out = tmp_path / "grant"
    code = main(
        [
            "run",
            "--config",
            str(GRANT),
            "--out",
            str(out),
            "--reproducible",
            "--approved-by",
            "Jane Doe",
        ]
    )
    assert code == 2
    assert not out.exists()


def test_manifest_with_no_approver_records_approved_by_null() -> None:
    record = provenance_record(Provenance(numbers_bound=4))
    assert record["approved_by"] is None
    assert "approved_at" not in record
