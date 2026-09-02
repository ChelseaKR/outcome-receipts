"""Tests for charts drawn from grounded figures.

The load-bearing property is that a chart has no data path of its own: its bars
and points are the figures' values, and every number it renders is a figure
display, so the grounding gate verifies a chart the same way it verifies prose.
These tests pin that, plus the accessible data table and the SVG's image role.
"""

from __future__ import annotations

import re

import pytest

from outcome_receipts.charts import _scale_max, render_chart, render_charts
from outcome_receipts.grounding import ground
from outcome_receipts.models import ChartSpec, Figure, Receipt


def _figure(metric_id: str, value: float, display: str) -> Figure:
    receipt = Receipt(
        metric_id=metric_id,
        value_sql="SELECT 1",
        row_count=1,
        slice_hash="x",
        value=value,
        unit="count",
        computed_at="t",
    )
    return Figure(metric_id=metric_id, value=value, display=display, receipt=receipt)


FIGURES = [
    _figure("permanent", 13.0, "13"),
    _figure("temporary", 3.0, "3"),
    _figure("unknown", 2.0, "2"),
]

BAR = ChartSpec(
    chart_id="exits",
    title="Exits by destination",
    kind="bar",
    metric_ids=("permanent", "temporary", "unknown"),
    labels=("Permanent", "Temporary", "Unknown"),
)


def test_chart_points_are_the_figure_values_not_a_separate_path() -> None:
    chart = render_chart(BAR, FIGURES)
    assert [p.value for p in chart.points] == [13.0, 3.0, 2.0]
    assert chart.displays == ("13", "3", "2")


def test_chart_numbers_all_ground_to_the_figures() -> None:
    chart = render_chart(BAR, FIGURES)
    result = ground(chart.claims_text, FIGURES)
    assert result.ok
    assert result.total == 3


def test_claims_text_excludes_svg_geometry() -> None:
    # The SVG has pixel coordinates; the claims text the gate sees must not, or a
    # presentational number would be mistaken for an ungrounded claim.
    chart = render_chart(BAR, FIGURES)
    assert "640" in chart.svg  # canvas width is in the image
    assert "640" not in chart.claims_text


def test_data_table_carries_the_grounded_numbers() -> None:
    chart = render_chart(BAR, FIGURES)
    assert "| Permanent | 13 |" in chart.data_table
    assert "| Unknown | 2 |" in chart.data_table


def test_svg_is_an_accessible_image() -> None:
    chart = render_chart(BAR, FIGURES)
    assert 'role="img"' in chart.svg
    assert "<title" in chart.svg
    assert "<desc" in chart.svg
    assert "Exits by destination" in chart.svg


def test_line_chart_renders_a_polyline() -> None:
    spec = ChartSpec(
        chart_id="trend", title="Trend", kind="line", metric_ids=("permanent", "temporary")
    )
    chart = render_chart(spec, FIGURES)
    assert "<polyline" in chart.svg
    assert chart.displays == ("13", "3")


def test_label_falls_back_to_metric_id() -> None:
    spec = ChartSpec(chart_id="c", title="t", kind="bar", metric_ids=("permanent",))
    chart = render_chart(spec, FIGURES)
    assert chart.points[0].label == "permanent"


def test_unknown_metric_raises() -> None:
    spec = ChartSpec(chart_id="c", title="t", kind="bar", metric_ids=("missing",))
    with pytest.raises(KeyError, match="unknown metric"):
        render_chart(spec, FIGURES)


def test_unknown_kind_raises() -> None:
    spec = ChartSpec(chart_id="c", title="t", kind="pie", metric_ids=("permanent",))
    with pytest.raises(ValueError, match="kind"):
        render_chart(spec, FIGURES)


def test_render_charts_handles_several() -> None:
    charts = render_charts([BAR, BAR], FIGURES)
    assert len(charts) == 2


# --- Withheld cells: a bar height and a line slope are both claims. ---
#
# Merge-blocking (issue #78). A suppressed figure used to arrive here carrying
# ``value = 0.0``, so the bar drew flat on the axis baseline and the polyline
# ran straight through the floor and back up. The label said "[SUPPRESSED]" and
# the picture said "we housed nobody this quarter". These tests assert on the
# geometry, never on the label, because the label was always right.

_RECT = re.compile(r'<rect x="([\d.]+)" y="([\d.]+)" width="([\d.]+)" height="([\d.]+)"([^>]*)')
_POLYLINE = re.compile(r'<polyline[^>]*points="([^"]+)"')


def _bars(svg: str) -> list[tuple[str, str, str, str, str]]:
    """Every plotted rectangle except the white canvas background."""

    return [match for match in _RECT.findall(svg) if "#ffffff" not in match[4]]


def _withheld_figure(metric_id: str) -> Figure:
    """A figure in the state ``suppress_figures`` leaves a withheld cell in."""

    from outcome_receipts.suppression import suppress_figures

    publishable, result = suppress_figures([_figure(metric_id, 4.0, "4")])
    assert result.suppressed == (metric_id,)
    return publishable[0]


def _mixed_figures() -> list[Figure]:
    """One healthy value, one genuine zero, one withheld cell."""

    return [
        _figure("visible", 40.0, "40"),
        _figure("true_zero", 0.0, "0"),
        _withheld_figure("withheld"),
    ]


def test_a_withheld_bar_and_a_true_zero_bar_are_not_the_same_shape() -> None:
    """The exact comparison from the issue: identical geometry, before."""

    spec = ChartSpec(
        chart_id="mixed",
        title="Mixed",
        kind="bar",
        metric_ids=("visible", "true_zero", "withheld"),
        labels=("Visible", "Zero", "Withheld"),
    )
    svg = render_chart(spec, _mixed_figures()).svg
    _visible, zero, withheld = _bars(svg)

    assert (zero[1], zero[3]) != (withheld[1], withheld[3])
    # The true zero keeps the old, correct rendering: nothing above the axis.
    assert float(zero[3]) == 0.0
    # The withheld slot occupies the full plot height, so it cannot be read as
    # a small value either.
    assert float(withheld[3]) > 0.0
    assert float(withheld[1]) < float(zero[1])
    # And it is visibly not a bar: not the data colour, and outlined dashed.
    assert "#2b6cb0" not in withheld[4]
    assert "stroke-dasharray" in withheld[4]
    assert "url(#mixed-withheld)" in withheld[4]


def test_a_withheld_bar_is_announced_not_only_drawn() -> None:
    spec = ChartSpec(
        chart_id="mixed",
        title="Mixed",
        kind="bar",
        metric_ids=("visible", "withheld"),
        labels=("Visible", "Withheld"),
    )
    svg = render_chart(spec, _mixed_figures()).svg

    assert "withheld under the small-cell suppression policy" in svg
    assert "not a value of zero" in svg
    assert "<desc" in svg and "1 category is withheld" in svg


def test_a_line_chart_does_not_interpolate_through_a_withheld_point() -> None:
    """40, withheld, 36. The old chart drew a collapse and a recovery."""

    figures = [
        _figure("q1", 40.0, "40"),
        _withheld_figure("q2"),
        _figure("q3", 36.0, "36"),
    ]
    spec = ChartSpec(
        chart_id="trend",
        title="Trend",
        kind="line",
        metric_ids=("q1", "q2", "q3"),
        labels=("Q1", "Q2", "Q3"),
    )
    svg = render_chart(spec, figures).svg

    # No segment may span the gap. With a withheld point between the only two
    # drawable ones, that leaves no polyline at all.
    assert _POLYLINE.findall(svg) == []
    # And no point is plotted on the axis floor at the withheld x position.
    assert "<circle" in svg  # the two real points are still drawn
    assert 'cy="296.0"' not in svg


def test_a_line_chart_still_joins_the_points_on_either_side_of_a_gap() -> None:
    """The break must be exactly at the gap, not a refusal to draw anything."""

    figures = [
        _figure("q1", 40.0, "40"),
        _figure("q2", 38.0, "38"),
        _withheld_figure("q3"),
        _figure("q4", 30.0, "30"),
        _figure("q5", 36.0, "36"),
    ]
    spec = ChartSpec(
        chart_id="trend",
        title="Trend",
        kind="line",
        metric_ids=("q1", "q2", "q3", "q4", "q5"),
    )
    svg = render_chart(spec, figures).svg

    segments = _POLYLINE.findall(svg)
    assert len(segments) == 2
    assert all(len(segment.split()) == 2 for segment in segments)
    # The withheld x (the midpoint of the plot) appears in neither segment.
    assert not any("332.0," in segment for segment in segments)


def test_a_withheld_cell_does_not_participate_in_the_axis_scale() -> None:
    """A hidden cell must take no part in scaling the bars that are drawn.

    Note this was latent rather than observable: `_scale_max` is a `max`, and a
    withheld cell arriving as `0.0` could only have raised the maximum if every
    real value were already at or below zero, which cannot change the clamped
    result either. The test asserts the property directly, both on the scale
    function and end to end, so it stays true if the scaling rule ever becomes
    something other than a maximum.
    """

    figures = _mixed_figures()
    points = render_chart(
        ChartSpec(
            chart_id="c", title="t", kind="bar", metric_ids=("visible", "true_zero", "withheld")
        ),
        figures,
    ).points
    drawable = tuple(point for point in points if not point.withheld)

    assert _scale_max(points) == _scale_max(drawable)

    with_withheld = ChartSpec(
        chart_id="c",
        title="t",
        kind="bar",
        metric_ids=("visible", "withheld"),
    )
    without = ChartSpec(chart_id="c", title="t", kind="bar", metric_ids=("visible",))
    drawn = _bars(render_chart(with_withheld, figures).svg)[0]
    alone = _bars(render_chart(without, figures).svg)[0]
    assert drawn[3] == alone[3]

    # A chart of nothing but withheld cells must not divide by zero.
    only = ChartSpec(chart_id="c", title="t", kind="bar", metric_ids=("withheld",))
    assert render_chart(only, figures).svg
    assert _scale_max(render_chart(only, figures).points) == 1.0


def test_a_withheld_point_carries_no_value_into_the_chart_data() -> None:
    spec = ChartSpec(chart_id="c", title="t", kind="bar", metric_ids=("withheld",))
    chart = render_chart(spec, _mixed_figures())

    assert chart.points[0].value is None
    assert chart.points[0].suppressed is True
    assert chart.points[0].withheld is True
    assert chart.data_table.endswith("| withheld | [SUPPRESSED] |")


# --- Real negative values: a decrease is not a zero, and it is not a magnitude. ---


def _delta_figures() -> list[Figure]:
    """Two comparison-shaped delta figures: signed value, magnitude-only display.

    This is exactly what ``comparison.compute_comparison`` produces. ``value``
    carries the signed change and ``display`` is ``_magnitude_display``, the
    absolute change, because the direction is reported as a word on
    ``ComparisonRow`` rather than as a sign in the figure. Nothing stops a
    ``[[charts]]`` block from naming one: the delta figures are ordinary members
    of the flat figure list a run builds.
    """

    return [_figure("exits_permanent__delta", -12.0, "12"), _figure("intake__delta", 8.0, "8")]


def test_a_negative_bar_value_is_refused_instead_of_drawn_as_a_zero() -> None:
    # A decrease of 12 used to draw as height="0.0", flush on the baseline, with
    # its own text label and <title> both correctly reading 12. The bar claimed
    # "no change" while the receipt said -12 and the label said 12.
    spec = ChartSpec(
        chart_id="change",
        title="Change by category",
        kind="bar",
        metric_ids=("exits_permanent__delta", "intake__delta"),
        labels=("Decreased", "Increased"),
    )
    with pytest.raises(ValueError, match="exits_permanent__delta"):
        render_chart(spec, _delta_figures())


def test_a_negative_line_value_is_refused_too() -> None:
    # The line path put the same point at y=668.0 on a canvas 360 high: outside
    # the image entirely, with a polyline running off the bottom to reach it.
    spec = ChartSpec(
        chart_id="change-line",
        title="Change over time",
        kind="line",
        metric_ids=("exits_permanent__delta", "intake__delta"),
        labels=("Decreased", "Increased"),
    )
    with pytest.raises(ValueError, match="exits_permanent__delta"):
        render_chart(spec, _delta_figures())


def test_the_refusal_names_the_value_and_says_what_to_do() -> None:
    # The author has to be able to act on it, so the message carries the metric,
    # the value, and the reason a chart cannot render a signed figure: the only
    # string a chart may draw is the figure display, and a delta display is the
    # unsigned magnitude by design.
    spec = ChartSpec(
        chart_id="change",
        title="Change by category",
        kind="bar",
        metric_ids=("exits_permanent__delta",),
        labels=("Decreased",),
    )
    with pytest.raises(ValueError) as excinfo:
        render_chart(spec, _delta_figures())

    message = str(excinfo.value)
    assert "'change'" in message
    assert "exits_permanent__delta" in message
    assert "-12" in message


def test_a_true_zero_still_draws_and_is_not_refused() -> None:
    # The control. Zero is a real, publishable value and draws a zero-height bar
    # on the baseline, which is the truthful geometry for it. It passes before and
    # after the refusal, so a red result above is the negative-value defect and
    # not a check that swallowed the zero case with it.
    spec = ChartSpec(
        chart_id="zero",
        title="Exits by destination",
        kind="bar",
        metric_ids=("none", "some"),
        labels=("None", "Some"),
    )
    figures = [_figure("none", 0.0, "0"), _figure("some", 4.0, "4")]

    chart = render_chart(spec, figures)

    assert 'height="0.0"' in chart.svg
    assert [point.value for point in chart.points] == [0.0, 4.0]
