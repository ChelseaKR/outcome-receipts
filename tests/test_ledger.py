"""The hash-chained export ledger is tamper-evident.

Every successful export appends one line linking to the entry before it by hash.
These tests pin the passing case (three exports chain with contiguous indices and
correct prev_hash linkage, and verify_chain returns no problems) and the failing
case (a middle entry edited on disk makes verify_chain report the break at that
entry's index). A fixed clock keeps timestamps deterministic, the same way the
receipt tests do, so the ledger is byte-for-byte reproducible.
"""

from __future__ import annotations

import json
from pathlib import Path

from outcome_receipts.cli import main
from outcome_receipts.clock import FixedClock
from outcome_receipts.ledger import (
    GENESIS_PREV_HASH,
    append_export,
    read_ledger,
    verify_chain,
)

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
GRANT = EXAMPLES / "grant-report" / "report.toml"

MANIFEST_A = '{"receipts": [{"metric_id": "clients_served", "value": 42.0}]}'
MANIFEST_B = '{"receipts": [{"metric_id": "exits", "value": 7.0}]}'
MANIFEST_C = '{"receipts": [{"metric_id": "retained", "value": 19.0}]}'


def _clock() -> FixedClock:
    return FixedClock("2026-01-01T00:00:00+00:00")


def test_append_chains_indices_and_prev_hash(tmp_path: Path) -> None:
    ledger = tmp_path / "export-ledger.jsonl"
    first = append_export(ledger, "Q1 report", MANIFEST_A, "Funder A", clock=_clock())
    second = append_export(ledger, "Q2 report", MANIFEST_B, "Funder A", clock=_clock())
    third = append_export(ledger, "Q3 report", MANIFEST_C, None, clock=_clock())

    assert [first.index, second.index, third.index] == [0, 1, 2]
    assert second.prev_hash == first.entry_hash
    assert third.prev_hash == second.entry_hash

    entries = read_ledger(ledger)
    assert [e.index for e in entries] == [0, 1, 2]
    assert [e.entry_hash for e in entries] == [
        first.entry_hash,
        second.entry_hash,
        third.entry_hash,
    ]


def test_genesis_prev_hash_is_all_zeros(tmp_path: Path) -> None:
    ledger = tmp_path / "export-ledger.jsonl"
    first = append_export(ledger, "Q1 report", MANIFEST_A, "Funder A", clock=_clock())
    assert first.prev_hash == GENESIS_PREV_HASH
    assert first.prev_hash == "0" * 64


def test_verify_chain_intact_returns_empty(tmp_path: Path) -> None:
    ledger = tmp_path / "export-ledger.jsonl"
    append_export(ledger, "Q1 report", MANIFEST_A, "Funder A", clock=_clock())
    append_export(ledger, "Q2 report", MANIFEST_B, "Funder A", clock=_clock())
    append_export(ledger, "Q3 report", MANIFEST_C, None, clock=_clock())
    assert verify_chain(ledger) == []


def test_tampered_middle_entry_reports_break_at_its_index(tmp_path: Path) -> None:
    ledger = tmp_path / "export-ledger.jsonl"
    append_export(ledger, "Q1 report", MANIFEST_A, "Funder A", clock=_clock())
    append_export(ledger, "Q2 report", MANIFEST_B, "Funder A", clock=_clock())
    append_export(ledger, "Q3 report", MANIFEST_C, None, clock=_clock())

    lines = ledger.read_text(encoding="utf-8").splitlines()
    middle = json.loads(lines[1])
    middle["report_title"] = "Q2 report (edited)"
    middle["manifest_hash"] = "deadbeef" * 8
    lines[1] = json.dumps(middle)
    ledger.write_text("\n".join(lines) + "\n", encoding="utf-8")

    problems = verify_chain(ledger)
    assert problems != []
    assert any("entry 1" in problem for problem in problems)
    # The untouched entries do not report a hash mismatch of their own.
    assert not any("entry 0: entry_hash" in problem for problem in problems)


def test_empty_ledger_verifies_and_reads_empty(tmp_path: Path) -> None:
    ledger = tmp_path / "does-not-exist.jsonl"
    assert read_ledger(ledger) == []
    assert verify_chain(ledger) == []


def test_recipient_none_round_trips(tmp_path: Path) -> None:
    ledger = tmp_path / "export-ledger.jsonl"
    append_export(ledger, "Q1 report", MANIFEST_A, None, clock=_clock())
    entries = read_ledger(ledger)
    assert entries[0].recipient is None
    assert verify_chain(ledger) == []


def test_cli_run_appends_and_grows_the_ledger(tmp_path: Path) -> None:
    ledger = tmp_path / "export-ledger.jsonl"
    for _ in range(2):
        code = main(
            [
                "run",
                "--config",
                str(GRANT),
                "--out",
                str(tmp_path / "out"),
                "--reproducible",
                "--ledger",
                str(ledger),
                "--recipient",
                "County Housing Authority",
                "--approved-by",
                "Dana Reviewer",
            ]
        )
        assert code == 0
    entries = read_ledger(ledger)
    assert [e.index for e in entries] == [0, 1]
    assert entries[1].prev_hash == entries[0].entry_hash
    assert entries[0].recipient == "County Housing Authority"
    assert verify_chain(ledger) == []


def test_cli_verify_ledger_passes_then_fails_on_tamper(tmp_path: Path) -> None:
    ledger = tmp_path / "export-ledger.jsonl"
    assert (
        main(
            [
                "run",
                "--config",
                str(GRANT),
                "--out",
                str(tmp_path / "out"),
                "--reproducible",
                "--ledger",
                str(ledger),
                "--approved-by",
                "Dana Reviewer",
            ]
        )
        == 0
    )
    assert main(["verify-ledger", "--ledger", str(ledger)]) == 0

    record = json.loads(ledger.read_text(encoding="utf-8").splitlines()[0])
    record["recipient"] = "someone else"
    ledger.write_text(json.dumps(record) + "\n", encoding="utf-8")
    assert main(["verify-ledger", "--ledger", str(ledger)]) == 1
