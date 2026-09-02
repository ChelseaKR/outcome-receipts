"""Tests for the provenance statement embedded in every export.

The product's answer to AI-skepticism is structural: numbers come from queries,
not from a model. These tests pin that the export says so, both in the report body
a funder reads and in the manifest a machine can check, and that the gate result
and count are stated rather than implied.
"""

from __future__ import annotations

import json

from outcome_receipts.grounding import ground
from outcome_receipts.models import Figure, Receipt
from outcome_receipts.provenance import (
    Provenance,
    provenance_markdown,
    provenance_record,
)
from outcome_receipts.report import receipts_manifest, render_report
from outcome_receipts.verify import _report_narrative


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
    assert record["narrative_drafter"] == "deterministic"


def test_provenance_records_bedrock_narrative_without_claiming_model_numbers() -> None:
    record = provenance_record(Provenance(numbers_bound=4, narrative_drafter="bedrock"))
    assert record["narrative_drafter"] == "bedrock"
    assert record["model_wrote_numbers"] is False


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


# --- The scope the provenance block and the README are allowed to claim. ---


def _receipted(metric_id: str, display: str, value: float) -> Figure:
    receipt = Receipt(
        metric_id=metric_id,
        value_sql="SELECT COUNT(DISTINCT client_id) FROM data",
        row_count=12,
        slice_hash="5fb9cf7a45262e7ecb099944819e8605f28a036d084034898fd93edda1f7e01e",
        value=value,
        unit="count",
        computed_at="1970-01-01T00:00:00+00:00",
    )
    return Figure(metric_id=metric_id, value=value, display=display, receipt=receipt)


def test_the_gate_covers_the_claims_not_every_numeral_in_the_file() -> None:
    """The gate's scope is the claims, and the published copy must say only that.

    The README headline, `DEFINITION_OF_DONE.md`, and the shipped
    `provenance_statement` string used to promise that every number in a report
    traced to a receipt. A rendered report falsifies that: the receipts section
    and the provenance block print row counts, slice hashes, timestamps, and the
    text of each query, and the gate never read them. Running `ground` over a
    whole rendered report reports them as unbound.

    So this pins both halves. Over the narrative region the gate is clean, which
    is the claim the documents may make. Over the whole file it is not, which is
    why they may not make the broader one. A change that genuinely widens the
    scope should widen the copy and then update this test, not the other way
    round.
    """

    figures = [_receipted("clients_served", "12", 12.0)]
    report = render_report(
        "Housing Program Outcome Report",
        "In the reporting period, our housing program served 12 clients.",
        figures,
        provenance=Provenance(numbers_bound=1),
    )

    narrative_only = ground(_report_narrative(report), figures)
    assert narrative_only.ok, [span.text for span in narrative_only.unbound]

    whole_file = ground(report, figures)
    assert not whole_file.ok
    unbound = {span.text for span in whole_file.unbound}
    # Receipt metadata, not reported figures: the export timestamp, the row
    # count, and the numerals inside the printed query.
    assert "1970" in unbound
    assert unbound - {span.text for span in narrative_only.unbound}
