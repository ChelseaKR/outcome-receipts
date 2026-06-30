"""Tests for the provenance statement embedded in every export.

The product's answer to AI-skepticism is structural: numbers come from queries,
not from a model. These tests pin that the export says so, both in the report body
a funder reads and in the manifest a machine can check, and that the gate result
and count are stated rather than implied.
"""

from __future__ import annotations

import json

from outcome_receipts.models import Figure, Receipt
from outcome_receipts.provenance import (
    Provenance,
    provenance_markdown,
    provenance_record,
)
from outcome_receipts.report import receipts_manifest, render_report


def _figure(metric_id: str, display: str) -> Figure:
    receipt = Receipt(
        metric_id=metric_id,
        value_sql="SELECT 1",
        row_count=1,
        slice_hash="x",
        value=1.0,
        unit="count",
        computed_at="t",
    )
    return Figure(metric_id=metric_id, value=1.0, display=display, receipt=receipt)


def test_provenance_markdown_states_no_model_and_the_count() -> None:
    block = provenance_markdown(Provenance(numbers_bound=4))
    assert "## Provenance" in block
    assert "No figure was written by a language model" in block
    assert "bound all 4 of its numbers to a receipt" in block


def test_provenance_record_is_machine_readable() -> None:
    record = provenance_record(Provenance(numbers_bound=4))
    assert record["model_wrote_numbers"] is False
    assert record["numbers_from"] == "deterministic_sql"
    assert record["grounding_gate"] == "pass"
    assert record["numbers_bound"] == 4


def test_unbound_count_marks_the_gate_failed() -> None:
    prov = Provenance(numbers_bound=3, numbers_unbound=1)
    assert prov.gate_pass is False
    assert provenance_record(prov)["grounding_gate"] == "fail"
    assert "not cleared for export" in provenance_markdown(prov)


def test_render_report_embeds_provenance_when_given() -> None:
    figures = [_figure("a", "5")]
    report = render_report(
        "Title", "We served 5 clients.", figures, provenance=Provenance(numbers_bound=1)
    )
    assert "## Provenance" in report
    assert "No figure was written by a language model" in report


def test_render_report_omits_provenance_when_absent() -> None:
    report = render_report("Title", "We served 5 clients.", [_figure("a", "5")])
    assert "## Provenance" not in report


def test_manifest_carries_the_provenance_record() -> None:
    figures = [_figure("a", "5")]
    manifest = json.loads(receipts_manifest(figures, provenance=Provenance(numbers_bound=1)))
    assert manifest["provenance"]["model_wrote_numbers"] is False
    assert manifest["provenance"]["numbers_bound"] == 1


def test_manifest_without_provenance_has_no_provenance_key() -> None:
    manifest = json.loads(receipts_manifest([_figure("a", "5")]))
    assert "provenance" not in manifest
