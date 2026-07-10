"""Tests for the manifest-to-manifest receipts diff.

A diff between two receipted runs is change accounting: it must say which figures
moved, were added, or removed, and why each one moved. These tests pin that a value,
row-count, and slice-hash move are all reported; that a timestamp-only difference is
never a move; that added-only and removed-only metrics land in the right bucket; and
that the rendered Markdown carries the summary counts and each changed figure's
before/after values.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from outcome_receipts.cli import main
from outcome_receipts.diff import diff_manifests
from outcome_receipts.report import render_diff_markdown


def _receipt(
    metric_id: str,
    *,
    value: float,
    display: str,
    value_sql: str = "SELECT COUNT(*) FROM data",
    row_count: int = 100,
    slice_hash: str = "hash0",
    computed_at: str = "2025-01-01T00:00:00Z",
) -> dict[str, Any]:
    return {
        "metric_id": metric_id,
        "value": value,
        "display": display,
        "unit": "count",
        "definition": f"definition of {metric_id}",
        "value_sql": value_sql,
        "row_count": row_count,
        "slice_hash": slice_hash,
        "computed_at": computed_at,
    }


def _manifest(*receipts: dict[str, Any]) -> dict[str, Any]:
    return {"receipts": list(receipts)}


def test_value_row_count_and_slice_hash_change_is_reported_with_all_reasons() -> None:
    prior = _manifest(_receipt("served", value=42.0, display="42", row_count=120, slice_hash="h1"))
    current = _manifest(
        _receipt("served", value=47.0, display="47", row_count=131, slice_hash="h2")
    )

    diff = diff_manifests(prior, current)

    assert len(diff.changed) == 1
    delta = diff.changed[0]
    assert delta.metric_id == "served"
    assert delta.value_changed
    assert delta.row_count_changed
    assert delta.slice_hash_changed
    assert not delta.query_changed
    assert "value 42.0 -> 47.0" in delta.reasons
    assert "row count 120 -> 131" in delta.reasons
    assert "slice hash changed" in delta.reasons
    assert diff.added == ()
    assert diff.removed == ()
    assert diff.unchanged == ()


def test_query_change_alone_is_a_move() -> None:
    prior = _manifest(
        _receipt("served", value=42.0, display="42", value_sql="SELECT COUNT(*) FROM data")
    )
    current = _manifest(
        _receipt(
            "served",
            value=42.0,
            display="42",
            value_sql="SELECT COUNT(DISTINCT id) FROM data",
        )
    )

    diff = diff_manifests(prior, current)

    assert len(diff.changed) == 1
    delta = diff.changed[0]
    assert delta.query_changed
    assert not delta.value_changed
    assert "query changed" in delta.reasons


def test_timestamp_only_difference_is_unchanged() -> None:
    prior = _manifest(
        _receipt("served", value=42.0, display="42", computed_at="2025-01-01T00:00:00Z")
    )
    current = _manifest(
        _receipt("served", value=42.0, display="42", computed_at="2025-06-30T12:00:00Z")
    )

    diff = diff_manifests(prior, current)

    assert diff.changed == ()
    assert diff.unchanged == ("served",)


def test_added_and_removed_metrics_land_in_the_right_bucket() -> None:
    prior = _manifest(
        _receipt("kept", value=1.0, display="1"),
        _receipt("dropped", value=2.0, display="2"),
    )
    current = _manifest(
        _receipt("kept", value=1.0, display="1"),
        _receipt("fresh", value=3.0, display="3"),
    )

    diff = diff_manifests(prior, current)

    assert [r["metric_id"] for r in diff.added] == ["fresh"]
    assert [r["metric_id"] for r in diff.removed] == ["dropped"]
    assert diff.unchanged == ("kept",)
    assert diff.changed == ()


def test_missing_receipts_key_is_handled_defensively() -> None:
    diff = diff_manifests({}, {"receipts": [_receipt("x", value=1.0, display="1")]})

    assert [r["metric_id"] for r in diff.added] == ["x"]
    assert diff.removed == ()


def test_render_diff_markdown_carries_counts_and_before_after_values() -> None:
    prior = _manifest(
        _receipt("served", value=42.0, display="42", row_count=120, slice_hash="h1"),
        _receipt("dropped", value=9.0, display="9"),
    )
    current = _manifest(
        _receipt("served", value=47.0, display="47", row_count=131, slice_hash="h2"),
        _receipt("fresh", value=3.0, display="3"),
    )

    diff = diff_manifests(prior, current)
    md = render_diff_markdown(diff, prior_label="q1", current_label="q2")

    assert "## Receipts diff" in md
    assert "1 added, 1 removed, 1 changed, 0 unchanged" in md
    assert "| served |" in md
    assert "42" in md
    assert "47" in md
    assert "### Added" in md
    assert "fresh = 3" in md
    assert "### Removed" in md
    assert "dropped = 9" in md


def test_cli_diff_over_tmp_files_exits_zero(tmp_path: Path, capsys: Any) -> None:
    prior_path = tmp_path / "prior.json"
    current_path = tmp_path / "current.json"
    prior_path.write_text(
        json.dumps(_manifest(_receipt("served", value=42.0, display="42"))),
        encoding="utf-8",
    )
    current_path.write_text(
        json.dumps(_manifest(_receipt("served", value=47.0, display="47"))),
        encoding="utf-8",
    )

    code = main(["diff", str(prior_path), str(current_path)])

    assert code == 0
    out = capsys.readouterr().out
    assert "## Receipts diff" in out
    assert "value 42.0 -> 47.0" in out
