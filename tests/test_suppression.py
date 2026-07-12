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

import json
from itertools import product
from pathlib import Path

from outcome_receipts.cli import main
from outcome_receipts.clock import FixedClock
from outcome_receipts.config import load_spec
from outcome_receipts.engine import compute_figures, read_csv
from outcome_receipts.grounding import find_numbers
from outcome_receipts.models import Figure, Receipt
from outcome_receipts.suppression import (
    SuppressionResult,
    filter_for_aggregate_only,
    suppress_figures,
)


def _make_figure(
    metric_id: str, value: float, display: str | None = None, unit: str = "count"
) -> Figure:
    """Helper to create a test figure."""
    if display is None:
        display = str(int(value)) if value == int(value) else f"{value:.1f}"
    receipt = Receipt(
        metric_id=metric_id,
        value_sql="SELECT COUNT(*)",
        row_count=int(value),
        slice_hash="abc123" * 10 + "12",  # 64 chars
        value=value,
        unit=unit,
        computed_at="2026-07-01T00:00:00Z",
        definition=f"Count of {metric_id}",
    )
    return Figure(
        metric_id=metric_id,
        value=value,
        display=display,
        receipt=receipt,
    )


def _signed_subset_recovers(target: float, values: list[float]) -> bool:
    """The adversary's own brute force: does any +/- combination equal ``target``?

    Deliberately independent of the implementation under test (it does not import
    or share code with ``suppression.py``), so a bug in the module's search cannot
    hide the same bug here. Every non-empty subset of ``values``, with every
    assignment of + or - to each member, is checked against ``target``.
    """

    for signs in product((-1, 0, 1), repeat=len(values)):
        if all(sign == 0 for sign in signs):
            continue
        total = sum(sign * value for sign, value in zip(signs, values, strict=True))
        if abs(total - target) < 1e-9:
            return True
    return False


def _report_receipt_block(report_md: str, metric_id: str) -> str:
    """The single figure's receipt bullet block from a rendered report.md.

    `render_report` writes one `- **metric_id** = display` bullet per figure,
    followed by its indented sub-bullets, in metric_id order. This isolates just
    that figure's block, so a check against it cannot be confused by another,
    legitimately unsuppressed figure's receipt elsewhere in the document.
    """

    marker = f"- **{metric_id}**"
    start = report_md.index(marker)
    rest = report_md[start + len(marker) :]
    end = rest.find("\n- **")
    return marker + (rest if end == -1 else rest[:end])


def _trace_figure_section(trace_html: str, metric_id: str) -> str:
    """The single figure's <section> from a rendered trace.html."""

    marker = f'id="metric-{metric_id}"'
    start = trace_html.index(marker)
    rest = trace_html[start:]
    end = rest.find("</section>")
    return rest if end == -1 else rest[: end + len("</section>")]


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

    def test_small_non_count_values_are_not_primary_suppressed(self) -> None:
        """Cell-size policy applies to people/count cells, not money or duration."""

        figures = [
            _make_figure("grant_spend", 5, display="$5.00", unit="money"),
            _make_figure("median_stay", 7, display="7 days", unit="duration"),
        ]
        redacted, result = suppress_figures(figures)

        assert result.suppressed == ()
        assert redacted == figures

    def test_mixed_threshold_behavior(self) -> None:
        """A realistic figure set with mixed values around the threshold."""
        figures = [
            _make_figure("served", 100),  # Above threshold, unsuppressed
            _make_figure("exited_housing", 8),  # Below threshold, suppressed
            _make_figure("no_service", 0),  # True zero, unsuppressed
            _make_figure("pending", 11),  # At threshold, unsuppressed
            _make_figure("referral", 1),  # Below threshold, suppressed
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
        """When a category is suppressed, suppress the cell that would derive it.

        total_exits(25) - exits_other(17) == exits_to_housing(8), so leaving both
        total_exits and exits_other visible would let a reader recover the
        suppressed value by subtraction. The real arithmetic check (not a name
        match against "total") finds this and suppresses the smaller of the two
        recovering cells, exits_other, the standard "next-smallest" rule: it is
        the least additional redaction that still breaks the recovery.
        """
        figures = [
            _make_figure("total_exits", 25),  # Total = suppressed + unsuppressed
            _make_figure("exits_to_housing", 8),  # Suppressed (below threshold)
            _make_figure("exits_other", 17),  # 25 - 8 = 17: recovers the suppressed cell
        ]
        _redacted, result = suppress_figures(figures, complementary_rule=True)

        assert "exits_to_housing" in result.suppressed
        assert "exits_other" in result.complementary_suppressed
        # Recovery is genuinely broken: only total_exits remains visible, and a
        # single number cannot reconstruct exits_to_housing by itself.
        assert result.unsuppressed == ("total_exits",)

    def test_complementary_suppression_can_be_disabled(self) -> None:
        """When complementary_rule=False, only primary suppression is applied."""
        figures = [
            _make_figure("total_exits", 25),
            _make_figure("exits_to_housing", 8),
            _make_figure("exits_other", 17),
        ]
        _redacted, result = suppress_figures(figures, complementary_rule=False)

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
        _redacted, result = suppress_figures(figures, complementary_rule=True)

        # small_group is suppressed, but high-count figures are not affected.
        assert "small_group" in result.suppressed
        assert "category_a" in result.unsuppressed
        assert "category_b" in result.unsuppressed
        # None of these values combine to reconstruct small_group (5), so a
        # genuine arithmetic check leaves total_served visible too -- unlike a
        # name-substring heuristic, which would have suppressed it just for
        # being called "total_served" regardless of whether it discloses anything.
        assert "total_served" in result.unsuppressed
        assert result.complementary_suppressed == ()


class TestSuppressionRedaction:
    """Suppressed figures must have their display redacted."""

    def test_suppressed_figures_display_redacted_placeholder(self) -> None:
        """Suppressed figures must have display = '[SUPPRESSED]'."""
        figures = [
            _make_figure("count_5", 5, display="5"),
        ]
        redacted, _result = suppress_figures(figures)

        assert redacted[0].display == "[SUPPRESSED]"
        assert redacted[0].metric_id == "count_5"

    def test_unsuppressed_figures_display_preserved(self) -> None:
        """Unsuppressed figures must keep their original display."""
        figures = [
            _make_figure("count_100", 100, display="100"),
            _make_figure("percent_rate", 0.75, display="75.0%"),
        ]
        redacted, _result = suppress_figures(figures)

        assert redacted[0].display == "100"
        assert redacted[1].display == "75.0%"

    def test_suppressed_receipt_value_zeroed(self) -> None:
        """A suppressed figure's *receipt* must also be scrubbed, not just the figure.

        report.py and trace.py render `receipt.row_count` and the manifest renders
        `receipt.value` directly -- neither reads `Figure.value`. A suppressed
        figure that keeps its original, unredacted receipt "for audit trail" is
        not suppressed at all: the raw count is still sitting right there for
        every renderer that reads the receipt instead of the figure.
        """
        figures = [
            _make_figure("count_8", 8),
        ]
        redacted, _result = suppress_figures(figures)

        assert redacted[0].value == 0.0
        assert redacted[0].receipt.value == 0.0
        assert redacted[0].receipt.row_count == 0
        assert redacted[0].receipt.slice_hash != figures[0].receipt.slice_hash


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

    def test_scalar_id_count_is_still_aggregate(self) -> None:
        """A metric name cannot turn a scalar Figure into a row-level export."""
        figures = [
            _make_figure("client_id_count", 12345),
        ]
        assert filter_for_aggregate_only(figures) == figures

    def test_scalar_name_count_is_still_aggregate(self) -> None:
        """Aggregate-only is structural, not a substring denylist."""
        figures = [
            _make_figure("clients_with_recorded_name", 42),
        ]
        assert filter_for_aggregate_only(figures) == figures


class TestSuppressionResult:
    """SuppressionResult.ok must check the actual privacy invariant, not counts.

    The old implementation was `len(suppressed) == 0 or len(unsuppressed) <
    len(suppressed)`: a comparison of two tuple lengths that says nothing about
    whether any below-threshold cell was actually left unredacted. These tests
    pin the real check: ok is False exactly when a figure recorded as
    unsuppressed had an original value below threshold.
    """

    def test_result_ok_when_no_figures_suppressed(self) -> None:
        """ok=True when all figures passed through unsuppressed, above threshold."""
        result = SuppressionResult(
            suppressed=(),
            complementary_suppressed=(),
            unsuppressed=("metric1", "metric2"),
            aggregate_only=True,
            values=(("metric1", 100.0), ("metric2", 0.0)),
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

    def test_ok_is_false_when_a_below_threshold_cell_is_left_unsuppressed(self) -> None:
        """A below-threshold figure marked unsuppressed must fail ok.

        This is the scenario the old `len(unsuppressed) < len(suppressed)` check
        could not catch: a single leaked small cell, with nothing else suppressed
        to compare it against.
        """
        result = SuppressionResult(
            suppressed=(),
            complementary_suppressed=(),
            unsuppressed=("leaked_small_cell",),
            aggregate_only=True,
            values=(("leaked_small_cell", 4.0),),
        )
        assert not result.ok

    def test_ok_ignores_unsuppressed_zero_and_above_threshold_values(self) -> None:
        """A true zero or an at/above-threshold value is correctly not a violation."""
        result = SuppressionResult(
            suppressed=(),
            complementary_suppressed=(),
            unsuppressed=("zero_cell", "big_cell", "threshold_cell"),
            aggregate_only=True,
            values=(("zero_cell", 0.0), ("big_cell", 500.0), ("threshold_cell", 11.0)),
        )
        assert result.ok

    def test_ok_is_true_for_every_real_suppress_figures_call(self) -> None:
        """Every result suppress_figures actually returns must be ok."""
        figures = [
            _make_figure("served", 100),
            _make_figure("small", 5),
            _make_figure("zero", 0),
        ]
        _redacted, result = suppress_figures(figures)
        assert result.ok


class TestRealWorldScenario:
    """A realistic outcome-report scenario: housing program with suppressed cells."""

    def test_housing_program_with_two_small_exits_suppressed(self) -> None:
        """Two suppressed cells whose *sum* (not either alone) is derivable.

        total_served(150) - exited_to_ph(45) - exited_to_th(95) == 10, the
        combined total of the two suppressed cells, exited_to_sh(7) and
        still_housed(3). But that arithmetic only pins down their sum; it does
        not reconstruct either exact value (7+3, 6+4, 5+5, ... are all
        consistent with 10), so a real disclosure check correctly leaves
        total_served visible. A name-substring heuristic could not tell this
        apart from a genuinely recoverable case and would suppress total_served
        regardless.
        """
        figures = [
            _make_figure("total_served", 150),
            _make_figure("exited_to_ph", 45),  # Above threshold
            _make_figure("exited_to_th", 95),  # Above threshold
            _make_figure("exited_to_sh", 7),  # Below threshold, suppressed
            _make_figure("still_housed", 3),  # Below threshold, suppressed
        ]
        redacted, result = suppress_figures(figures, complementary_rule=True)

        # Small exit groups are suppressed.
        assert "exited_to_sh" in result.suppressed
        assert "still_housed" in result.suppressed

        # Above-threshold figures pass through: neither individual suppressed
        # value is recoverable from them.
        assert "exited_to_ph" in result.unsuppressed
        assert "exited_to_th" in result.unsuppressed
        assert "total_served" in result.unsuppressed
        assert result.complementary_suppressed == ()

        # Check that the redacted version has [SUPPRESSED] placeholders.
        redacted_by_id = {f.metric_id: f for f in redacted}
        assert redacted_by_id["exited_to_sh"].display == "[SUPPRESSED]"
        assert redacted_by_id["still_housed"].display == "[SUPPRESSED]"

    def test_housing_program_with_one_small_exit_group_suppressed(self) -> None:
        """A single suppressed cell whose value *is* exactly recoverable.

        Here total_served is a true sum of the three categories, so once
        exited_to_sh is suppressed, total_served - exited_to_ph - exited_to_th
        reconstructs it exactly (150 - 45 - 98 == 7). The real check catches
        this via the 3-term combination and suppresses the smallest cell in
        it -- exited_to_ph -- the standard "next-smallest" rule. (The total is
        the sum of its parts, so it is never the smallest cell in a genuine
        recovering combination; suppressing a category instead of the total
        matches real disclosure-control practice, unlike the old heuristic,
        which suppressed whatever happened to be named "total".)
        """
        figures = [
            _make_figure("total_served", 150),  # 45 + 98 + 7
            _make_figure("exited_to_ph", 45),
            _make_figure("exited_to_th", 98),
            _make_figure("exited_to_sh", 7),  # Below threshold, suppressed
        ]
        redacted, result = suppress_figures(figures, complementary_rule=True)

        assert "exited_to_sh" in result.suppressed
        assert "exited_to_ph" in result.complementary_suppressed
        assert "total_served" in result.unsuppressed
        assert "exited_to_th" in result.unsuppressed

        redacted_by_id = {f.metric_id: f for f in redacted}
        assert redacted_by_id["exited_to_ph"].display == "[SUPPRESSED]"
        assert redacted_by_id["exited_to_ph"].receipt.value == 0.0


class TestArithmeticDisclosureNotNameMatching:
    """Bug: the complementary pass used to only match metric_id keywords.

    None of "clients_served", "clients_white", or "clients_black" contains
    "total", "all", "sum", or "aggregate", so the old heuristic suppressed
    nothing beyond the primary cell -- even though clients_black is trivially
    recoverable as clients_served - clients_white.
    """

    def test_demographic_breakdown_without_total_or_all_in_the_name(self) -> None:
        figures = [
            _make_figure("clients_served", 103),
            _make_figure("clients_white", 95),
            _make_figure("clients_black", 8),  # Below threshold; 103 - 95 == 8
        ]
        redacted, result = suppress_figures(figures, complementary_rule=True)

        assert "clients_black" in result.suppressed
        # A real recovering combination exists (clients_served - clients_white),
        # so one of its members must be suppressed too -- the smaller of the two,
        # clients_white, is the minimal additional redaction.
        assert "clients_white" in result.complementary_suppressed
        assert "clients_served" in result.unsuppressed

        redacted_by_id = {f.metric_id: f for f in redacted}
        assert redacted_by_id["clients_black"].display == "[SUPPRESSED]"
        assert redacted_by_id["clients_white"].display == "[SUPPRESSED]"
        # clients_served alone cannot reconstruct clients_black: no combination
        # of the figures still visible after suppression equals 8.
        assert redacted_by_id["clients_served"].display == "103"
        assert redacted_by_id["clients_served"].value == 103.0

    def test_no_false_positive_when_nothing_is_actually_recoverable(self) -> None:
        """A name containing 'total' must not be suppressed if it discloses nothing.

        This is the other half of the fix: the old heuristic suppressed any
        "total"-ish figure whenever *anything* was suppressed, whether or not it
        was actually part of a recoverable relationship.
        """
        figures = [
            _make_figure("clients_served", 500),
            _make_figure("total_donations_thousands", 220),  # Unrelated metric
            _make_figure("clients_black", 8),  # Below threshold, unrelated to the above
        ]
        _redacted, result = suppress_figures(figures, complementary_rule=True)

        assert "clients_black" in result.suppressed
        assert result.complementary_suppressed == ()
        assert "total_donations_thousands" in result.unsuppressed
        assert "clients_served" in result.unsuppressed


class TestSuppressionArtifactIntegration:
    """Merge-blocking: a suppressed value must not appear in any exported artifact.

    Unit tests on `suppress_figures` alone can't catch a leak that happens
    downstream, in a renderer that reads `figure.receipt` instead of
    `figure.value` (this is exactly what Bug 1 was). This test runs the real
    `receipts run` pipeline end to end and greps the actual rendered
    report.md, receipts.json, and trace.html for the raw suppressed numbers,
    the same way a reviewer would.
    """

    def test_raw_suppressed_values_do_not_appear_in_any_exported_artifact(
        self, tmp_path: Path
    ) -> None:
        examples = Path(__file__).resolve().parents[1] / "examples"
        config = examples / "housing-demo" / "report.toml"
        out = tmp_path / "out"

        # housing-demo's `exits` metric is 10 and `exits_permanent` is 6, both
        # below the suppression threshold of 11.
        spec = load_spec(config)
        rows = read_csv(spec.data_path)
        raw_figures = compute_figures(rows, spec.report.metrics, clock=FixedClock())
        raw_by_id = {f.metric_id: f for f in raw_figures}
        assert raw_by_id["exits"].value == 10.0
        assert raw_by_id["exits_permanent"].value == 6.0

        code = main(
            [
                "run",
                "--config",
                str(config),
                "--out",
                str(out),
                "--reproducible",
                "--approved-by",
                "CI",
            ]
        )
        assert code == 0

        report_md = (out / "report.md").read_text(encoding="utf-8")
        receipts_json = json.loads((out / "receipts.json").read_text(encoding="utf-8"))
        trace_html = (out / "trace.html").read_text(encoding="utf-8")

        # The narrative must show the redacted placeholder, not the raw counts:
        # neither "10" nor "6" may appear as a number the drafter wrote.
        narrative_section = report_md.split("## Receipts")[0]
        narrative_numbers = {span.text for span in find_numbers(narrative_section)}
        assert "10" not in narrative_numbers
        assert "6" not in narrative_numbers
        assert report_md.count("[SUPPRESSED]") >= 2

        # The receipts manifest must carry the redaction through every field a
        # reader could use to recover the count, not just `display`.
        by_metric = {r["metric_id"]: r for r in receipts_json["receipts"]}
        for metric_id in ("exits", "exits_permanent"):
            record = by_metric[metric_id]
            assert record["display"] == "[SUPPRESSED]"
            assert record["value"] == 0.0
            assert record["row_count"] == 0
            assert record["slice_hash"] != raw_by_id[metric_id].receipt.slice_hash

        # The exact leak this bug reported: "rows in slice: 10" right under a
        # "[SUPPRESSED]" line in the rendered Markdown -- scoped to *this*
        # figure's own receipt block, not the whole document. housing-demo's
        # `pct_permanent` is a legitimately unsuppressed rate whose own,
        # legitimate row_count happens to also be 10 (same slice as `exits`), so
        # a blind whole-document substring search would false-positive on it; the
        # bug is specifically the suppressed figure's *own* block still showing
        # its raw count.
        assert "rows in slice: 10" not in _report_receipt_block(report_md, "exits")
        assert "rows in slice: 6" not in _report_receipt_block(report_md, "exits_permanent")

        # The trace view's per-figure detail must show the redacted row count,
        # not the raw one, for both suppressed figures (again scoped to each
        # figure's own <section>, for the same reason).
        assert "<dd>10</dd>" not in _trace_figure_section(trace_html, "exits")
        assert "<dd>6</dd>" not in _trace_figure_section(trace_html, "exits_permanent")


class TestFullDepthDisclosureSearch:
    """Merge-blocking: the disclosure search must cover the whole figure group.

    The search used to stop at combinations of 4 terms (`_MAX_DISCLOSURE_TERMS`),
    so a total decomposed into five or more named categories -- an ordinary shape
    in HMIS-style reporting -- evaded it: the only recovering combination has as
    many terms as the breakdown has figures, and the cap meant it was never tried.
    """

    def test_five_term_breakdown_is_not_recoverable(self) -> None:
        """The demonstrated evasion: 162 = 52 + 30 + 61 + 17 + 2, dept_e suppressed.

        total - a - b - c - d reconstructs dept_e exactly, but the recovering
        combination has five terms, one past the old cap. After suppression, no
        signed combination of the figures still visible may equal 2.
        """
        figures = [
            _make_figure("total_clients", 162),
            _make_figure("dept_a", 52),
            _make_figure("dept_b", 30),
            _make_figure("dept_c", 61),
            _make_figure("dept_d", 17),
            _make_figure("dept_e", 2),
        ]
        redacted, result = suppress_figures(figures, complementary_rule=True)

        assert "dept_e" in result.suppressed
        # The adversary's check, run against exactly what the export shows: no
        # +/- combination of visible values may reconstruct the suppressed 2.
        visible_values = [f.value for f in redacted if f.display != "[SUPPRESSED]"]
        assert not _signed_subset_recovers(2.0, visible_values)
        # The next-smallest-cell rule breaks the five-term identity by redacting
        # dept_d (17), the smallest figure in the recovering combination; the
        # total and the three larger categories stay visible.
        assert "dept_d" in result.complementary_suppressed
        for still_visible in ("total_clients", "dept_a", "dept_b", "dept_c"):
            assert still_visible in result.unsuppressed


# A report spec with exactly the shipped grant-report structure: a headline
# count metric, and a comparison of the same base metric across two quarters.
# The headline is computed over the whole period, so it is the sum of the two
# period figures -- the cross-scope accounting identity the old per-group
# disclosure check never examined.
_HEADLINE_PLUS_COMPARISON_TOML = """
[data]
path = "services.csv"

[report]
title = "Cross-scope reproduction"
template = "Of the clients who exited, {exits_permanent} moved into permanent housing."

[metrics.exits_permanent]
description = "Exits whose destination was permanent housing."
unit = "count"
value_sql = "SELECT COUNT(*) FROM data WHERE exit_destination = 'permanent'"
slice_sql = "SELECT * FROM data WHERE exit_destination = 'permanent'"

[comparison]
current = "q2"
prior = "q1"

[[comparison.periods]]
id = "q1"
label = "Q1 2025"
predicate = "enrolled_date >= '2025-01-01' AND enrolled_date < '2025-04-01'"

[[comparison.periods]]
id = "q2"
label = "Q2 2025"
predicate = "enrolled_date >= '2025-04-01' AND enrolled_date < '2025-07-01'"

[comparison.metrics.exits_permanent]
description = "Permanent-housing exits, by quarter of enrollment."
unit = "count"
value_sql = "SELECT COUNT(*) FROM data WHERE exit_destination = 'permanent' AND ({period})"
slice_sql = "SELECT * FROM data WHERE exit_destination = 'permanent' AND ({period})"
"""


class TestCrossScopeRecoveryThroughRealCli:
    """Merge-blocking: a headline and its period figures share a disclosure scope.

    `_group_key` used to bucket `exits_permanent__q1/__q2/__delta` into group
    "exits_permanent" while the whole-period headline `exits_permanent` landed in
    "__report__", so the identity headline = q1 + q2 was never checked:
    headline(68) - q2(63) printed the suppressed q1(5) into the same report.md.
    Reproduced through the real CLI with the shipped grant-report structure.
    """

    def test_headline_and_period_cannot_recover_a_suppressed_quarter(self, tmp_path: Path) -> None:
        # Data shaped like examples/grant-report: every enrollment exits to
        # permanent housing; 5 enrolled in Q1 and 63 in Q2, so the headline is
        # 68, the Q1 figure is 5 (suppressed), and Q2 is 63.
        rows = ["client_id,program,enrolled_date,exit_date,exit_destination"]
        rows.extend(
            f"C{i:03d},housing,2025-02-{(i % 28) + 1:02d},2025-03-15,permanent" for i in range(5)
        )
        rows.extend(
            f"C{i:03d},housing,2025-05-{(i % 28) + 1:02d},2025-06-15,permanent"
            for i in range(5, 68)
        )
        (tmp_path / "services.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")
        config = tmp_path / "report.toml"
        config.write_text(_HEADLINE_PLUS_COMPARISON_TOML, encoding="utf-8")

        out = tmp_path / "out"
        code = main(
            [
                "run",
                "--config",
                str(config),
                "--out",
                str(out),
                "--reproducible",
                "--approved-by",
                "CI",
            ]
        )
        assert code == 0

        manifest = json.loads((out / "receipts.json").read_text(encoding="utf-8"))
        by_id = {record["metric_id"]: record for record in manifest["receipts"]}

        # The quarter with five clients is suppressed.
        assert by_id["exits_permanent__q1"]["display"] == "[SUPPRESSED]"
        # The demonstrated attack: with the headline (68) and Q2 (63) both
        # visible in the same report, 68 - 63 recovers the suppressed 5. After
        # the fix, no signed combination of the values still visible anywhere in
        # the manifest (and therefore in report.md, whose every number is a
        # figure display) may reconstruct it.
        visible_counts = [
            float(record["value"])
            for record in manifest["receipts"]
            if record["display"] != "[SUPPRESSED]" and record["unit"] == "count"
        ]
        assert not _signed_subset_recovers(5.0, visible_counts)
        # The specific resolution: the headline stays (it is the largest cell in
        # the identity), the recovering period figure is complementary-suppressed,
        # and the delta goes with its suppressed period -- a visible delta next
        # to the visible headline would pin q1 at (headline - delta) / 2.
        assert by_id["exits_permanent"]["display"] == "68"
        assert by_id["exits_permanent__q2"]["display"] == "[SUPPRESSED]"
        assert by_id["exits_permanent__delta"]["display"] == "[SUPPRESSED]"


class TestPercentTriangulation:
    """Merge-blocking: a percent must not triangulate a suppressed count.

    The complementary check used to restrict itself to unit == "count", waving
    every percent through. A percent with a visible denominator uniquely
    determines a suppressed numerator via rounding. The MetricSpec data model
    cannot express which count metrics feed a percent (value_sql is opaque SQL),
    so the module implements the conservative rule: when any count in the report
    is suppressed, every percent figure is suppressed with it.
    """

    def test_percent_with_visible_denominator_is_suppressed(self) -> None:
        """The demonstrated case: exits = 14 visible, pct_permanent = 71%.

        Among numerators 1..14 only 10/14 rounds to 71%, so the "suppressed"
        numerator is uniquely recoverable while the percent prints. The percent
        must be suppressed along with the count it discloses.
        """
        figures = [
            _make_figure("exits", 14),
            _make_figure("exits_permanent", 10),
            _make_figure("pct_permanent", 71.0, display="71%", unit="percent"),
        ]
        redacted, result = suppress_figures(figures, complementary_rule=True)
        by_id = {figure.metric_id: figure for figure in redacted}

        assert "exits_permanent" in result.suppressed
        assert by_id["pct_permanent"].display == "[SUPPRESSED]"
        assert by_id["pct_permanent"].value == 0.0
        assert by_id["pct_permanent"].receipt.value == 0.0
        assert "pct_permanent" in result.complementary_suppressed
        # The denominator itself is at no risk and stays visible: the rule
        # removes the triangulating percent, not every count in sight.
        assert by_id["exits"].display == "14"
        assert "exits" in result.unsuppressed

    def test_housing_demo_percent_is_suppressed_end_to_end(self, tmp_path: Path) -> None:
        """The shipped housing-demo has this exact shape: 6/10 exits, 60%.

        With exits (10) and exits_permanent (6) suppressed, a visible 60% next
        to any inference about the denominator narrows the suppressed pair to
        almost nothing; the exported manifest must carry the percent as
        suppressed too.
        """
        examples = Path(__file__).resolve().parents[1] / "examples"
        config = examples / "housing-demo" / "report.toml"
        out = tmp_path / "out"
        code = main(
            [
                "run",
                "--config",
                str(config),
                "--out",
                str(out),
                "--reproducible",
                "--approved-by",
                "CI",
            ]
        )
        assert code == 0

        manifest = json.loads((out / "receipts.json").read_text(encoding="utf-8"))
        by_id = {record["metric_id"]: record for record in manifest["receipts"]}
        assert by_id["pct_permanent"]["display"] == "[SUPPRESSED]"
        assert by_id["pct_permanent"]["value"] == 0.0
        # clients_served (12) is above threshold, in no recovering relationship,
        # and not a percent: it stays visible.
        assert by_id["clients_served"]["display"] == "12"
