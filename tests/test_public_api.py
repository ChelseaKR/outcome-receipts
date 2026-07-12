"""Tests for the supported top-level Python API.

These lock the documented v0.x surface: every name promised in ``__all__`` must be
importable as an attribute of the package, and a small end-to-end flow must work
using only top-level imports, so integrations never need to reach into submodules.
"""

from __future__ import annotations

import outcome_receipts as orx

# The names the package promises as its supported surface. Kept explicit (rather
# than derived from ``__all__``) so a dropped export is caught here, not silently.
PROMISED = (
    "__version__",
    "compute_figures",
    "compute_figure",
    "read_csv",
    "load_table",
    "ground",
    "redact_unbound",
    "GroundingResult",
    "draft",
    "verify_manifest",
    "VerifyResult",
    "Check",
    "render_report",
    "receipts_manifest",
    "compute_comparison",
    "ComparisonResult",
    "diff_manifests",
    "FigureDelta",
    "ManifestDiff",
    "load_spec",
    "Spec",
    "Clock",
    "SystemClock",
    "FixedClock",
    "Figure",
    "MetricSpec",
    "Receipt",
    "ReportSpec",
)


def test_all_has_no_duplicates() -> None:
    assert len(orx.__all__) == len(set(orx.__all__))


def test_all_matches_promised_surface() -> None:
    assert set(orx.__all__) == set(PROMISED)


def test_every_all_name_is_importable() -> None:
    for name in orx.__all__:
        assert hasattr(orx, name), f"{name} in __all__ but not an attribute"


def test_end_to_end_flow_via_top_level_only() -> None:
    from outcome_receipts import (
        FixedClock,
        MetricSpec,
        compute_figures,
        draft,
        ground,
    )

    rows = [
        {"client_id": "C1", "dest": "permanent"},
        {"client_id": "C2", "dest": "permanent"},
        {"client_id": "C3", "dest": "temporary"},
    ]
    spec = MetricSpec(
        metric_id="permanent",
        description="permanent exits",
        value_sql="SELECT COUNT(*) FROM data WHERE dest = 'permanent'",
        slice_sql="SELECT * FROM data WHERE dest = 'permanent'",
        unit="count",
    )

    figures = compute_figures(rows, [spec], clock=FixedClock())
    assert len(figures) == 1
    assert figures[0].display == "2"

    report_spec = orx.ReportSpec(
        title="Demo",
        template="We recorded {permanent} permanent exits.",
        metrics=(spec,),
    )
    narrative = draft(report_spec, figures)
    assert "2 permanent exits" in narrative

    result = ground(narrative, figures)
    assert result.ok
    assert not result.unbound
