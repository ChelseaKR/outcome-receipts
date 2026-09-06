"""Preview what a suppression policy would withhold, before anything is exported.

Issue 160. Each test maps to one of that issue's "Done when" bullets, plus the
two invariants that make a preview safe to share and honest to read: the
shareable profile never carries a withheld value, and the registry's default
cannot drift from the threshold the engine actually applies.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from outcome_receipts.cli import main
from outcome_receipts.models import Figure, Receipt
from outcome_receipts.policy import (
    AD_HOC_POLICY_ID,
    DEFAULT_POLICY_ID,
    SuppressionPolicy,
    UnknownPolicyError,
    ad_hoc_policy,
    get_policy,
    registered_policies,
)
from outcome_receipts.preview import (
    preview_payload,
    preview_policies,
    preview_policy,
    render_preview_markdown,
)
from outcome_receipts.suppression import SUPPRESSION_THRESHOLD, suppress_figures


def _policies(payload: dict[str, object]) -> list[dict[str, object]]:
    """Narrow the payload's policy list for `mypy --strict`."""
    policies = payload["policies"]
    assert isinstance(policies, list)
    return [dict(item) for item in policies]


ROOT = Path(__file__).resolve().parents[1]
DEMO = str(ROOT / "examples" / "housing-demo" / "report.toml")


def _figures() -> list[Figure]:
    from outcome_receipts.cli import _compute_all

    _spec, _rows, figures, _comparison, _reconciliation = _compute_all(
        DEMO, reproducible=True, quiet=True
    )
    return figures


# --- the registry ---------------------------------------------------------


def test_the_default_policy_matches_the_threshold_the_engine_applies() -> None:
    """A registry that disagreed with the engine would mislabel every receipt."""
    assert get_policy(DEFAULT_POLICY_ID).threshold == SUPPRESSION_THRESHOLD


def test_the_default_policy_is_cited_with_a_read_date() -> None:
    policy = get_policy(DEFAULT_POLICY_ID)
    assert policy.cited
    assert "hhs.gov" in policy.citation
    assert policy.citation_read == "2026-08-21"


def test_every_registered_policy_is_cited() -> None:
    """An uncited entry in the registry would be a fabricated source."""
    for policy in registered_policies():
        assert policy.cited, f"{policy.policy_id} is registered with no citation"
        assert policy.citation_read


def test_an_unknown_policy_id_fails_closed_naming_it() -> None:
    with pytest.raises(UnknownPolicyError, match="cms-small-cell-v2"):
        get_policy("cms-small-cell-v2")


def test_an_ad_hoc_threshold_claims_no_source() -> None:
    policy = ad_hoc_policy(6)
    assert policy.policy_id == AD_HOC_POLICY_ID
    assert policy.threshold == 6
    assert not policy.cited
    assert policy.citation == ""


@pytest.mark.parametrize("threshold", [0, -1, -11])
def test_a_threshold_below_one_is_refused_not_clamped(threshold: int) -> None:
    """At threshold <= 0 the rule is empty: a control that cannot fire."""
    with pytest.raises(ValueError, match="at least 1"):
        ad_hoc_policy(threshold)


# --- the preview itself ---------------------------------------------------


def test_thresholds_six_and_eleven_withhold_different_sets() -> None:
    """Issue 160: 'previews thresholds 6 and 11 with differing withheld sets'."""
    figures = _figures()
    six, eleven = preview_policies(figures, [ad_hoc_policy(6), ad_hoc_policy(11)])
    assert six.withheld_total != eleven.withheld_total
    assert eleven.withheld_total > six.withheld_total
    assert six.surviving_total > eleven.surviving_total


def test_the_threshold_eleven_preview_equals_what_run_withholds() -> None:
    """Issue 160: 'the threshold-11 set equals what `run` withholds'.

    This is the load-bearing one: a preview that disagreed with the exporter
    would be worse than no preview, because an operator would choose a policy
    on it.
    """
    figures = _figures()
    preview = preview_policy(figures, get_policy(DEFAULT_POLICY_ID))
    _redacted, actual = suppress_figures(list(figures))

    assert preview.primary_suppressed == actual.suppressed
    assert tuple(entry.metric_id for entry in preview.complementary) == (
        actual.complementary_suppressed
    )
    assert preview.surviving == actual.unsuppressed


def test_previewing_does_not_consume_the_raw_figures() -> None:
    """Every policy must be measured against identical inputs."""
    figures = _figures()
    before = [(figure.metric_id, figure.value) for figure in figures]
    preview_policies(figures, [ad_hoc_policy(3), ad_hoc_policy(6), ad_hoc_policy(11)])
    after = [(figure.metric_id, figure.value) for figure in figures]
    assert before == after
    assert all(not figure.receipt.suppressed for figure in figures)


def test_a_cascade_is_attributed_to_the_rule_that_caused_it() -> None:
    figures = _figures()
    preview = preview_policy(figures, ad_hoc_policy(11))
    assert preview.complementary, "the housing demo should cascade at threshold 11"
    for entry in preview.complementary:
        assert entry.rule in {"delta", "percent", "recovery"}
    assert preview.percent_control_engaged


# --- the sentinel: the shareable profile carries no withheld value --------


def test_the_shareable_markdown_contains_no_withheld_value() -> None:
    """Issue 160 sentinel: 'The shareable output contains no withheld value'."""
    figures = _figures()
    previews = preview_policies(figures, [ad_hoc_policy(6), get_policy(DEFAULT_POLICY_ID)])
    shareable = render_preview_markdown(previews, include_withheld_values=False)

    local = render_preview_markdown(previews, include_withheld_values=True)
    withheld = {
        metric_id: value for preview in previews for metric_id, value in preview.withheld_values
    }
    assert withheld, "no cell was withheld, so this test would prove nothing"

    # A bare `str(value)` is far too coarse a needle: the withheld counts are
    # small integers whose digits also occur in thresholds, dates and the
    # citation. The precise claim is that no withheld metric is ever rendered
    # NEXT TO its value, which is the only shape that discloses one.
    assert "Withheld metric" not in shareable
    assert "Withheld metric" in local
    for metric_id, value in withheld.items():
        row = f"| `{metric_id}` | {value:g} |"
        assert row in local, f"local preview should print {metric_id}"
        assert row not in shareable, f"shareable preview leaked {metric_id} = {value:g}"


def test_the_shareable_json_contains_no_withheld_value() -> None:
    figures = _figures()
    previews = preview_policies(figures, [get_policy(DEFAULT_POLICY_ID)])
    payload = preview_payload(previews, include_withheld_values=False)
    rendered = json.dumps(payload)

    assert payload["includes_withheld_values"] is False
    # Key presence, not a substring: `includes_withheld_values` contains the
    # substring `withheld_values` and would make a naive check pass forever.
    assert "withheld_values" not in _policies(payload)[0]
    withheld = dict(previews[0].withheld_values)
    assert withheld
    for metric_id, value in withheld.items():
        assert f'"{metric_id}": {value:g}' not in rendered, f"shareable payload leaked {metric_id}"


def test_the_local_profile_does_print_the_withheld_values() -> None:
    """The opt-in has to actually opt in, or the flag is decorative."""
    figures = _figures()
    previews = preview_policies(figures, [get_policy(DEFAULT_POLICY_ID)])
    local = render_preview_markdown(previews, include_withheld_values=True)
    payload = preview_payload(previews, include_withheld_values=True)

    withheld = dict(previews[0].withheld_values)
    assert withheld
    for _metric_id, value in withheld.items():
        assert f"{value:g}" in local
    assert payload["includes_withheld_values"] is True
    values = _policies(payload)[0]["withheld_values"]
    assert isinstance(values, dict)
    assert set(values) == set(withheld)


# --- the CLI --------------------------------------------------------------


def test_cli_preview_writes_nothing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Issue 160: 'Preview writes nothing to the ledger or the out directory'."""
    out = tmp_path / "out"
    out.mkdir()
    before = sorted(path.name for path in out.iterdir())

    code = main(["suppress-preview", "--config", DEMO, "--threshold", "6", "--threshold", "11"])
    assert code == 0
    assert sorted(path.name for path in out.iterdir()) == before == []
    assert "Nothing was written" in capsys.readouterr().out


def test_cli_preview_json_is_one_object(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["suppress-preview", "--config", DEMO, "--json", "--threshold", "11"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["kind"] == "suppression-preview"
    assert payload["wrote_nothing"] is True
    assert payload["policies"][0]["threshold"] == 11


def test_cli_defaults_to_the_registered_policy(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["suppress-preview", "--config", DEMO, "--json"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["policies"][0]["policy_id"] == DEFAULT_POLICY_ID
    assert payload["policies"][0]["cited"] is True


def test_cli_unknown_policy_exits_non_zero_naming_it(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Issue 160: 'An unknown policy id exits non-zero naming it'."""
    code = main(["suppress-preview", "--config", DEMO, "--policy", "not-a-policy"])
    assert code != 0
    assert "not-a-policy" in capsys.readouterr().err


def test_cli_threshold_below_one_is_refused(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(ValueError, match="at least 1"):
        main(["suppress-preview", "--config", DEMO, "--threshold", "0"])


def test_cli_local_flag_reaches_the_output(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["suppress-preview", "--config", DEMO, "--json", "--local"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["includes_withheld_values"] is True
    assert payload["policies"][0]["withheld_values"]


def test_cli_repeated_policy_and_threshold_are_deduplicated(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = main(
        [
            "suppress-preview",
            "--config",
            DEMO,
            "--json",
            "--policy",
            DEFAULT_POLICY_ID,
            "--policy",
            DEFAULT_POLICY_ID,
            "--threshold",
            "6",
            "--threshold",
            "6",
        ]
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert len(payload["policies"]) == 2


def test_markdown_names_the_uncited_threshold_as_uncited() -> None:
    previews = preview_policies(_figures(), [ad_hoc_policy(6)])
    rendered = render_preview_markdown(previews, include_withheld_values=False)
    assert "no source" in rendered
    assert "claims no source" in rendered


def test_a_policy_dataclass_is_frozen() -> None:
    policy = get_policy(DEFAULT_POLICY_ID)
    # `setattr` through a name, so asserting immutability needs no type
    # suppression -- the hygiene gate requires an issue reference on those.
    field_name = "threshold"
    with pytest.raises(AttributeError):
        setattr(policy, field_name, 3)


def test_preview_of_an_already_suppressed_set_is_refused() -> None:
    """Re-previewing redacted figures would report a false all-clear."""
    figures = _figures()
    redacted, _result = suppress_figures(list(figures))
    with pytest.raises(ValueError, match="already"):
        preview_policy(redacted, get_policy(DEFAULT_POLICY_ID))


def test_a_policy_with_the_complementary_rule_off_withholds_no_cascade() -> None:
    figures = _figures()
    without = SuppressionPolicy(
        policy_id="test-no-complementary",
        threshold=11,
        complementary_rule=False,
        citation="test",
        citation_read="2026-09-06",
    )
    preview = preview_policy(figures, without)
    assert preview.complementary == ()
    assert not preview.percent_control_engaged
    # The primary set is unchanged; only the cascade is off.
    assert (
        preview.primary_suppressed
        == preview_policy(figures, get_policy(DEFAULT_POLICY_ID)).primary_suppressed
    )


# --- cascade attribution over constructed figure sets ---------------------


def _figure(metric_id: str, value: float, unit: str = "count") -> Figure:
    """A minimal raw figure, mirroring tests/test_suppression.py's helper."""
    receipt = Receipt(
        metric_id=metric_id,
        value_sql="SELECT COUNT(*)",
        row_count=int(value),
        slice_hash="abc123" * 10 + "12",
        value=value,
        unit=unit,
        computed_at="2026-07-01T00:00:00Z",
        definition=f"Count of {metric_id}",
    )
    return Figure(metric_id=metric_id, value=value, display=str(value), receipt=receipt)


def test_a_suppressed_period_pulls_its_delta_and_the_rule_says_so() -> None:
    """The delta rule: a hidden period figure takes its own delta with it."""
    figures = [
        _figure("housed__2025", 4.0),
        _figure("housed__2026", 40.0),
        _figure("housed__delta", 36.0),
        _figure("unrelated", 90.0),
    ]
    preview = preview_policy(figures, ad_hoc_policy(11))
    assert "housed__2025" in preview.primary_suppressed
    rules = {entry.metric_id: entry.rule for entry in preview.complementary}
    assert rules.get("housed__delta") == "delta"
    assert preview.comparison_control_engaged


def test_the_recovery_rule_names_the_disclosing_combination() -> None:
    """The recovery rule: a total minus its other parts rebuilds a hidden cell."""
    figures = [
        _figure("total", 100.0),
        _figure("part_large", 96.0),
        _figure("part_small", 4.0),
    ]
    preview = preview_policy(figures, ad_hoc_policy(11))
    assert preview.primary_suppressed == ("part_small",)
    assert preview.complementary, "a recoverable total must cascade"
    entry = preview.complementary[0]
    assert entry.rule == "recovery"
    assert entry.disclosing_combination, "the recovery rule must name its combination"
    assert preview.recovery_control_engaged


def test_a_cascade_with_no_reconstructable_target_still_reports_the_rule() -> None:
    """The fallback arm: attributed to `recovery` with no combination named."""
    from outcome_receipts.preview import _classify_cascade

    figures = [_figure("a", 4.0), _figure("b", 50.0)]
    entry = _classify_cascade("b", figures, primary=set(), withheld={"a"})
    assert entry.rule == "recovery"
    assert entry.disclosing_combination == ()
