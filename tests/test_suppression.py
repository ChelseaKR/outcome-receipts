"""Merge-blocking: small-cell suppression must follow the CMS policy.

Suppression is a privacy invariant: aggregate counts below the threshold (1-10,
modeled on the CMS Cell Size Suppression Policy) are redacted from the export.
True zeros are preserved (they contain no privacy risk). Complementary
suppression is applied to prevent recovery of suppressed cells by subtraction.

This test suite is merge-blocking: if suppression fails, the privacy promise
is broken and the export must not proceed.

Sourced from:
  CMS Cell Size Suppression Policy (ResDAC)
  https://resdac.org/articles/cms-cell-size-suppression-policy
  HHS Guidance Portal
  https://www.hhs.gov/guidance/document/cms-cell-suppression-policy
"""

from __future__ import annotations

import pytest

from outcome_receipts.models import Figure, Receipt
from outcome_receipts.suppression import (
    SuppressionResult,
    filter_for_aggregate_only,
    suppress_figures,
)


def _make_figure(metric_id: str, value: float, display: str | None = None) -> Figure:
    """Helper to create a test figure."""
    if display is None:
        display = str(int(value)) if value == int(value) else f"{value:.1f}"
    receipt = Receipt(
        metric_id=metric_id,
        value_sql="SELECT COUNT(*)",
        row_count=int(value),
        slice_hash="abc123" * 10 + "12",  # 64 chars
        value=value,
        unit="count",
        computed_at="2026-07-01T00:00:00Z",
        definition=f"Count of {metric_id}",
    )
    return Figure(
        metric_id=metric_id,
        value=value,
        display=display,
        receipt=receipt,
    )


class TestSuppressionThreshold:
    """The suppression threshold (CMS policy: 1-10 suppressed) must be enforced."""

    def test_values_below_threshold_are_suppressed(self) -> None:
        """Values in [1, 10] must be suppressed."""
        figures = [
            _make_figure("count_1", 1),
            _make_figure("count_5", 5),
            _make_figure("count_10", 10),
        ]
        redacted, result = suppress_figures(figures)

        assert set(result.suppressed) == {"count_1", "count_5", "count_10"}
        assert result.unsuppressed == ()
        assert all(f.display == "[SUPPRESSED]" for f in redacted)

    def test_values_at_threshold_and_above_are_not_suppressed(self) -> None:
        """Values >= 11 must pass through unredacted."""
        figures = [
            _make_figure("count_11", 11),
            _make_figure("count_100", 100),
            _make_figure("count_1000", 1000),
        ]
        redacted, result = suppress_figures(figures)

        assert result.suppressed == ()
        assert set(result.unsuppressed) == {"count_11", "count_100", "count_1000"}
        assert all(f.display != "[SUPPRESSED]" for f in redacted)

    def test_true_zeros_are_never_suppressed(self) -> None:
        """True zeros (0) contain no privacy risk and are preserved."""
        figures = [
            _make_figure("count_zero", 0),
            _make_figure("count_zero_households", 0),
        ]
        redacted, result = suppress_figures(figures)

        assert result.suppressed == ()
        assert set(result.unsuppressed) == {"count_zero", "count_zero_households"}
        assert all(f.display != "[SUPPRESSED]" for f in redacted)

    def test_mixed_threshold_behavior(self) -> None:
        """A realistic figure set with mixed values around the threshold."""
        figures = [
            _make_figure("served", 100),        # Above threshold, unsuppressed
            _make_figure("exited_housing", 8),  # Below threshold, suppressed
            _make_figure("no_service", 0),      # True zero, unsuppressed
            _make_figure("pending", 11),        # At threshold, unsuppressed
            _make_figure("referral", 1),        # Below threshold, suppressed
        ]
        redacted, result = suppress_figures(figures)

        assert set(result.suppressed) == {"exited_housing", "referral"}
        assert set(result.unsuppressed) == {"served", "no_service", "pending"}
        assert len(redacted) == 5
        assert redacted[1].display == "[SUPPRESSED]"  # exited_housing
        assert redacted[4].display == "[SUPPRESSED]"  # referral


class TestComplementarySuppression:
    """Complementary suppression must prevent recovery of suppressed cells."""

    def test_complementary_suppression_on_total(self) -> None:
        """When a category is suppressed, suppress its total so the category can't be derived."""
        figures = [
            _make_figure("total_exits", 25),           # Total = suppressed + unsuppressed
            _make_figure("exits_to_housing", 8),       # Suppressed (below threshold)
            _make_figure("exits_other", 17),           # Unsuppressed (25 - 8 = 17)
        ]
        redacted, result = suppress_figures(
            figures, complementary_rule=True
        )

        # The total should be complementary-suppressed to prevent: other = total - suppressed
        assert "exits_to_housing" in result.suppressed
        assert "total_exits" in result.complementary_suppressed

    def test_complementary_suppression_can_be_disabled(self) -> None:
        """When complementary_rule=False, only primary suppression is applied."""
        figures = [
            _make_figure("total_exits", 25),
            _make_figure("exits_to_housing", 8),
            _make_figure("exits_other", 17),
        ]
        redacted, result = suppress_figures(
            figures, complementary_rule=False
        )

        # Only primary suppression, no complementary.
        assert "exits_to_housing" in result.suppressed
        assert result.complementary_suppressed == ()

    def test_suppression_does_not_affect_figures_above_threshold(self) -> None:
        """Complementary suppression should not affect figures well above threshold."""
        figures = [
            _make_figure("total_served", 5000),
            _make_figure("category_a", 2500),
            _make_figure("category_b", 2500),
            _make_figure("small_group", 5),  # Below threshold
        ]
        redacted, result = suppress_figures(
            figures, complementary_rule=True
        )

        # small_group is suppressed, but high-count figures are not affected.
        assert "small_group" in result.suppressed
        assert "category_a" in result.unsuppressed
        assert "category_b" in result.unsuppressed


class TestSuppressionRedaction:
    """Suppressed figures must have their display redacted."""

    def test_suppressed_figures_display_redacted_placeholder(self) -> None:
        """Suppressed figures must have display = '[SUPPRESSED]'."""
        figures = [
            _make_figure("count_5", 5, display="5"),
        ]
        redacted, result = suppress_figures(figures)

        assert redacted[0].display == "[SUPPRESSED]"
        assert redacted[0].metric_id == "count_5"

    def test_unsuppressed_figures_display_preserved(self) -> None:
        """Unsuppressed figures must keep their original display."""
        figures = [
            _make_figure("count_100", 100, display="100"),
            _make_figure("percent_rate", 0.75, display="75.0%"),
        ]
        redacted, result = suppress_figures(figures)

        assert redacted[0].display == "100"
        assert redacted[1].display == "75.0%"

    def test_suppressed_receipt_value_zeroed(self) -> None:
        """Suppressed figures have value set to 0 in their receipt (signal suppression)."""
        figures = [
            _make_figure("count_8", 8),
        ]
        redacted, result = suppress_figures(figures)

        assert redacted[0].value == 0.0
        # Original receipt is still attached for audit trail.
        assert redacted[0].receipt.value == 8.0


class TestAggregateOnlyAssertion:
    """The export is aggregate-only: no row-level data is emitted."""

    def test_filter_for_aggregate_only_passes_clean_figures(self) -> None:
        """Aggregate metrics pass through the aggregate-only filter."""
        figures = [
            _make_figure("clients_served", 100),
            _make_figure("households_housed", 25),
            _make_figure("total_transactions", 500),
        ]
        # Should not raise.
        result = filter_for_aggregate_only(figures)
        assert len(result) == len(figures)

    def test_filter_rejects_pii_patterns(self) -> None:
        """Figures that look like row-level data (PII fields) must be rejected."""
        figures = [
            _make_figure("client_id", 12345),  # Looks like PII
        ]
        with pytest.raises(ValueError, match="row-level data"):
            filter_for_aggregate_only(figures)

    def test_filter_rejects_name_field(self) -> None:
        """Name fields are PII and must be rejected."""
        figures = [
            _make_figure("client_name", 42),
        ]
        with pytest.raises(ValueError, match="row-level data"):
            filter_for_aggregate_only(figures)


class TestSuppressionResult:
    """The SuppressionResult captures the suppression outcome."""

    def test_result_ok_when_no_figures_suppressed(self) -> None:
        """ok=True when all figures passed through unsuppressed."""
        result = SuppressionResult(
            suppressed=(),
            complementary_suppressed=(),
            unsuppressed=("metric1", "metric2"),
            aggregate_only=True,
        )
        assert result.ok

    def test_result_carries_suppression_metadata(self) -> None:
        """The result lists which metrics were suppressed and how."""
        result = SuppressionResult(
            suppressed=("metric_a", "metric_b"),
            complementary_suppressed=("metric_total",),
            unsuppressed=("metric_x", "metric_y"),
            aggregate_only=True,
        )
        assert len(result.suppressed) == 2
        assert len(result.complementary_suppressed) == 1
        assert len(result.unsuppressed) == 2


class TestRealWorldScenario:
    """A realistic outcome-report scenario: housing program with suppressed cells."""

    def test_housing_program_with_small_exits_suppressed(self) -> None:
        """A realistic outcome report where a small exit group is suppressed."""
        figures = [
            _make_figure("total_served", 150),
            _make_figure("exited_to_ph", 45),            # Above threshold
            _make_figure("exited_to_th", 95),            # Above threshold
            _make_figure("exited_to_sh", 7),             # Below threshold, suppressed
            _make_figure("still_housed", 3),             # Below threshold, suppressed
        ]
        redacted, result = suppress_figures(figures, complementary_rule=True)

        # Small exit groups are suppressed.
        assert "exited_to_sh" in result.suppressed
        assert "still_housed" in result.suppressed

        # Above-threshold figures pass through.
        assert "exited_to_ph" in result.unsuppressed
        assert "exited_to_th" in result.unsuppressed

        # Total is complementary-suppressed to prevent recovery.
        assert "total_served" in result.complementary_suppressed

        # Check that the redacted version has [SUPPRESSED] placeholders.
        redacted_by_id = {f.metric_id: f for f in redacted}
        assert redacted_by_id["exited_to_sh"].display == "[SUPPRESSED]"
        assert redacted_by_id["still_housed"].display == "[SUPPRESSED]"
