from __future__ import annotations

import json
from pathlib import Path

from outcome_receipts.cli import EXIT_OK, EXIT_VERIFY_FAIL, main
from outcome_receipts.mapping import build_mapping_queue


def _files(tmp_path: Path, requirement: dict[str, object]) -> tuple[Path, Path]:
    data = tmp_path / "export.csv"
    data.write_text("PersonalID,ProjectStartDate,Destination\nP1,2025-01-01,Permanent\n")
    requirements = tmp_path / "requirements.json"
    requirements.write_text(json.dumps({"requirements": [requirement]}))
    return data, requirements


def test_known_hmis_aliases_produce_review_required_candidate(tmp_path: Path) -> None:
    data, requirements = _files(
        tmp_path,
        {
            "metric_id": "clients_served",
            "description": "Unduplicated clients",
            "definition": "Distinct participants in the export.",
            "aggregation": "count_distinct",
            "field": "client_id",
        },
    )
    queue = build_mapping_queue(data, requirements)
    candidate = queue.candidates[0]

    assert queue.ok
    assert queue.requires_human_review
    assert candidate.status == "review_required"
    assert candidate.decision == "pending"
    assert candidate.confidence == 0.9
    assert candidate.metric_spec is not None
    assert candidate.metric_spec["value_sql"] == 'SELECT COUNT(DISTINCT "PersonalID") FROM data'


def test_filter_fields_are_mapped_and_sql_literals_are_escaped(tmp_path: Path) -> None:
    data, requirements = _files(
        tmp_path,
        {
            "metric_id": "permanent_exits",
            "aggregation": "count_rows",
            "filters": [{"field": "exit_destination", "equals": "Permanent's"}],
        },
    )
    candidate = build_mapping_queue(data, requirements).candidates[0]
    assert candidate.metric_spec is not None
    assert candidate.metric_spec["value_sql"] == (
        "SELECT COUNT(*) FROM data WHERE \"Destination\" = 'Permanent''s'"
    )
    assert str(candidate.metric_spec["slice_sql"]).startswith("SELECT * FROM data WHERE")


def test_missing_field_is_blocked_without_metric_spec(tmp_path: Path) -> None:
    data, requirements = _files(
        tmp_path,
        {"metric_id": "income", "aggregation": "count_distinct", "field": "income_id"},
    )
    candidate = build_mapping_queue(data, requirements).candidates[0]
    assert candidate.status == "blocked"
    assert candidate.metric_spec is None
    assert "no source column" in candidate.blockers[0]


def test_ambiguous_aliases_fail_closed(tmp_path: Path) -> None:
    data = tmp_path / "export.csv"
    data.write_text("PersonalID,ParticipantID\nP1,P1\n")
    requirements = tmp_path / "requirements.json"
    requirements.write_text(
        json.dumps(
            {
                "requirements": [
                    {
                        "metric_id": "clients",
                        "aggregation": "count_distinct",
                        "field": "client_id",
                    }
                ]
            }
        )
    )
    candidate = build_mapping_queue(data, requirements).candidates[0]
    assert candidate.status == "blocked"
    assert "ambiguous" in candidate.blockers[0]


def test_cli_writes_machine_readable_review_queue(tmp_path: Path) -> None:
    data, requirements = _files(
        tmp_path,
        {"metric_id": "clients", "aggregation": "count_distinct", "field": "client_id"},
    )
    out = tmp_path / "queue.json"
    assert (
        main(["map", "--data", str(data), "--requirements", str(requirements), "--out", str(out)])
        == EXIT_OK
    )
    payload = json.loads(out.read_text())
    assert payload["requires_human_review"] is True
    assert payload["candidates"][0]["decision"] == "pending"


def test_cli_returns_nonzero_when_mapping_is_blocked(tmp_path: Path) -> None:
    data, requirements = _files(
        tmp_path,
        {"metric_id": "income", "aggregation": "count_distinct", "field": "income_id"},
    )
    assert (
        main(["map", "--data", str(data), "--requirements", str(requirements)]) == EXIT_VERIFY_FAIL
    )
