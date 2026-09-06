"""Diagnose an unbound span: what it most likely meant, and what may be done.

Issue 155. The gate is fail-closed and stays fail-closed; this is the layer that
says *why* it refused. Every test below either maps to one of that issue's "Done
when" bullets or holds one of the two invariants that make advice safe to give:

1. Advice never changes a verdict. ``explain_audit`` returns a copy carrying the
   diagnoses, ``ok`` does not read them, and the exit code is the same number
   whether or not a caller asked.
2. A substitution is always an exact receipted display, checked against the
   figure set as it is at the moment of application -- never against what the
   plan claims, and never against a withheld cell.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from outcome_receipts.cli import _compute_all, _publishable_and_hidden, main
from outcome_receipts.grounding import (
    FIX_PLAN_SCHEMA_VERSION,
    FixPlanRefused,
    apply_fix_plan,
    audit_narrative,
    build_fix_plan,
    explain_audit,
    explain_span,
    explain_unbound,
    find_numbers,
    ground,
    narrative_digest,
)
from outcome_receipts.models import Explanation, Figure, Receipt

ROOT = Path(__file__).resolve().parents[1]
DEMO = str(ROOT / "examples" / "housing-demo" / "report.toml")


def _figure(
    metric_id: str, value: float | None, display: str, *, suppressed: bool = False
) -> Figure:
    return Figure(
        metric_id=metric_id,
        value=value,
        display=display,
        receipt=Receipt(
            metric_id=metric_id,
            value_sql="SELECT 1 FROM data",
            row_count=None if suppressed else 1,
            slice_hash=None if suppressed else "0" * 64,
            value=None if suppressed else value,
            unit="count",
            computed_at="2026-01-01T00:00:00Z",
            suppressed=suppressed,
        ),
    )


def _only(text: str, publishable: list[Figure]) -> Explanation:
    """The one diagnosis for a narrative written to contain one failing number."""

    result = explain_audit(audit_narrative(text, publishable, []), publishable, [])
    assert len(result.explanations) == 1, [item.span.text for item in result.explanations]
    return result.explanations[0]


# --- "Done when": the nearest display is named -----------------------------


def test_a_number_one_off_from_a_receipt_names_that_receipt_and_the_gap() -> None:
    """The issue's own example, verbatim.

    The fixture matters: 1,234 against a receipted 1,235 is a relative gap of
    8e-4 and an absolute gap of 1. A tolerance expressed only as a percentage
    would pass this and still be blind to the far commoner 11-against-10, which
    the next test covers, so both fixtures are here.
    """

    publishable = [_figure("clients_served", 1235.0, "1,235")]
    explanation = _only("We served 1,234 clients.", publishable)

    assert explanation.remedy == "replace"
    assert explanation.detail == "nearest: clients_served 1,235 (off by 1)"
    replacement = explanation.replacement
    assert replacement is not None
    assert replacement.display == "1,235"
    assert replacement.metric_id == "clients_served"
    assert replacement.distance == 1.0


def test_an_off_by_one_on_a_small_count_is_still_diagnosed() -> None:
    """11 against a receipted 10 is a 9% relative gap.

    A purely relative window would have to be that wide to catch it, and a
    window that wide would offer 1,150 as "nearest" to a receipted 1,235. The
    absolute floor exists so both cases work; without it this test fails and the
    previous one passes, which is why they are two tests.
    """

    publishable = [_figure("families", 10.0, "10")]
    explanation = _only("We housed 11 families.", publishable)

    assert explanation.remedy == "replace"
    assert "families 10" in explanation.detail


def test_a_number_far_from_every_receipt_is_told_so_rather_than_guessed_at() -> None:
    publishable = [_figure("clients_served", 12.0, "12")]
    explanation = _only("We served 4,001 clients.", publishable)

    assert explanation.remedy == "none"
    assert explanation.candidates == ()
    assert "no receipted display is near" in explanation.detail


# --- "Done when": a withheld value offers only removal ---------------------


def test_a_span_stating_a_withheld_cell_is_offered_removal_and_no_substitution() -> None:
    """The load-bearing one.

    The candidate here carries the protected cell's real display. Offering it as
    a replacement would be the tool proposing the disclosure it had just
    refused, so ``substitutable`` is false and the remedy is removal.
    """

    _spec, _rows, figures, _comparison, _reconciliation = _compute_all(
        DEMO, reproducible=True, quiet=True
    )
    publishable, hidden = _publishable_and_hidden(figures)
    assert any(figure.display == "6" for figure in hidden), "fixture must withhold a 6"
    assert not any(figure.display == "6" for figure in publishable)

    result = explain_audit(
        audit_narrative("Only 6 people moved on.", publishable, hidden), publishable, hidden
    )
    (explanation,) = [item for item in result.explanations if item.span.text == "6"]

    assert explanation.remedy == "remove"
    assert explanation.replacement is None
    assert explanation.candidates
    assert not any(candidate.substitutable for candidate in explanation.candidates)
    assert "exits_permanent" in explanation.detail


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # The fixture has to sit where the failure is possible. "1" is eleven
        # away from the only real figure and *one* away from the zero an
        # unparseable display collapses to, so if the marker were read as a
        # number at all it would be the nearest thing in the set and would be
        # offered. A span of 13 would be far from both and the same bug would
        # show nothing.
        ("We had 1 of them.", []),
        # ...and the real figure is still found when something is genuinely near.
        ("We served 13 clients.", ["12"]),
    ],
)
def test_a_suppression_marker_is_never_offered_as_a_candidate_display(
    text: str, expected: list[str]
) -> None:
    """``[SUPPRESSED]`` is a publishable "display" and parses as no number.

    It reaches the candidate loop like any other figure. A near-miss search that
    treated an unparseable display as zero -- absence rendered as a value --
    would offer the redaction marker as the thing an author's number most likely
    meant.
    """

    publishable = [
        _figure("withheld", None, "[SUPPRESSED]", suppressed=True),
        _figure("served", 12.0, "12"),
    ]
    explanation = _only(text, publishable)

    assert [candidate.display for candidate in explanation.candidates] == expected
    assert all(candidate.display != "[SUPPRESSED]" for candidate in explanation.candidates)


# --- "Done when": an ambiguous span is refused, not resolved ---------------


def test_apply_fixes_refuses_a_span_two_displays_are_equally_near() -> None:
    publishable = [_figure("a", 10.0, "10"), _figure("b", 12.0, "12")]
    explanation = _only("We had 11 of them.", publishable)

    assert explanation.remedy == "review"
    assert explanation.replacement is None
    assert len(explanation.candidates) == 2

    plan = build_fix_plan("We had 11 of them.", (explanation,))
    assert plan["fixes"] == []
    unfixable = plan["unfixable"]
    assert isinstance(unfixable, list)
    assert unfixable[0]["remedy"] == "review"


def test_apply_fixes_on_a_tied_span_exits_one_from_the_command_line(tmp_path: Path) -> None:
    """The plan a tie produces has no fix in it, so nothing is substituted.

    A hand-written plan that names one of the two anyway is a different refusal
    (the display is real, so it applies); the protection there is that a human
    wrote it deliberately. The mechanical path never chooses.
    """

    narrative = tmp_path / "draft.md"
    narrative.write_text("We served 4,001 clients.\n", encoding="utf-8")
    plan = tmp_path / "fixes.json"

    code = main(
        [
            "audit",
            "--config",
            DEMO,
            "--narrative",
            str(narrative),
            "--reproducible",
            "--fixes-out",
            str(plan),
        ]
    )
    assert code == 1
    written = json.loads(plan.read_text(encoding="utf-8"))
    assert written["fixes"] == []

    fixed = tmp_path / "fixed.md"
    assert (
        main(
            [
                "audit",
                "--config",
                DEMO,
                "--narrative",
                str(narrative),
                "--reproducible",
                "--apply-fixes",
                str(plan),
                "--fixed-out",
                str(fixed),
            ]
        )
        == 1
    )
    # Nothing was substituted, so the number the gate refused is still there.
    assert "4,001" in fixed.read_text(encoding="utf-8")


# --- "Done when": no existing exit code moves ------------------------------


def test_explaining_does_not_change_the_verdict_or_the_counts() -> None:
    publishable = [_figure("clients_served", 12.0, "12")]
    text = "We served 13 clients, up from twelve."
    plain = audit_narrative(text, publishable, [])
    explained = explain_audit(plain, publishable, [])

    assert explained.ok == plain.ok
    assert explained.total == plain.total
    assert explained.bound == plain.bound
    assert explained.unbound == plain.unbound
    assert explained.suppressed == plain.suppressed
    assert plain.explanations == ()
    assert explained.explanations != ()


@pytest.mark.parametrize("flags", [[], ["--explain"]])
def test_the_audit_exit_code_is_the_same_with_and_without_explain(
    tmp_path: Path, flags: list[str]
) -> None:
    passing = tmp_path / "pass.md"
    passing.write_text("We served 12 clients.\n", encoding="utf-8")
    failing = tmp_path / "fail.md"
    failing.write_text("We served 99 clients.\n", encoding="utf-8")

    base = ["audit", "--config", DEMO, "--reproducible"]
    assert main([*base, "--narrative", str(passing), *flags]) == 0
    assert main([*base, "--narrative", str(failing), *flags]) == 1


def _ungroundable_spec(tmp_path: Path) -> Path:
    """A spec whose template hard-codes a number no receipt produces.

    The literal 99 is not a rounding of the receipted 12 and is not near it, so
    the gate refuses and the diagnosis has something real to say. Written to a
    temporary directory so the committed examples keep grounding cleanly.
    """

    (tmp_path / "services.csv").write_text(
        (ROOT / "examples" / "housing-demo" / "services.csv").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    spec = tmp_path / "report.toml"
    spec.write_text(
        'schema_version = "1.0"\n'
        "\n"
        "[data]\n"
        'path = "services.csv"\n'
        "\n"
        "[report]\n"
        'title = "Ungroundable"\n'
        'template = "We served {clients_served} clients, up from 99 last year."\n'
        "\n"
        "[metrics.clients_served]\n"
        'description = "Distinct clients."\n'
        'definition = "Each person enrolled during the period, counted once by client_id."\n'
        'kind = "output"\n'
        'unit = "count"\n'
        'value_sql = "SELECT COUNT(DISTINCT client_id) FROM data"\n'
        'slice_sql = "SELECT client_id FROM data"\n',
        encoding="utf-8",
    )
    return spec


@pytest.mark.parametrize("explain", [False, True])
def test_run_explain_adds_a_reason_without_softening_the_refusal(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], explain: bool
) -> None:
    """``run`` writes nothing and exits 2 either way.

    Both halves are asserted from the same fixture: the exit code and the
    absence of an output directory are identical with and without the flag, and
    only the "why" lines differ. A diagnosis that changed either would be a
    diagnosis that let a number through.
    """

    spec = _ungroundable_spec(tmp_path)
    out = tmp_path / "out"
    argv = ["run", "--config", str(spec), "--out", str(out), "--reproducible"]
    if explain:
        argv.append("--explain")

    code = main(argv)
    captured = capsys.readouterr()

    assert code == 2
    assert not out.exists()
    assert "unverifiable number" in captured.err
    assert ("why '99'" in captured.err) is explain
    if explain:
        assert "no receipted display is near" in captured.err


# --- the fix plan applies only what a receipt actually says ----------------


def test_a_plan_applies_and_the_gate_is_re_run_over_what_was_written(tmp_path: Path) -> None:
    narrative = tmp_path / "draft.md"
    narrative.write_text("We served 13 clients.\n", encoding="utf-8")
    plan = tmp_path / "fixes.json"
    fixed = tmp_path / "fixed.md"

    assert (
        main(
            [
                "audit",
                "--config",
                DEMO,
                "--narrative",
                str(narrative),
                "--reproducible",
                "--fixes-out",
                str(plan),
            ]
        )
        == 1
    )
    written = json.loads(plan.read_text(encoding="utf-8"))
    assert written["schema_version"] == FIX_PLAN_SCHEMA_VERSION
    assert written["fixes"] == [
        {
            "start": 10,
            "end": 12,
            "was": "13",
            "replace_with": "12",
            "metric_id": "clients_served",
            "reason": "nearest",
        }
    ]

    assert (
        main(
            [
                "audit",
                "--config",
                DEMO,
                "--narrative",
                str(narrative),
                "--reproducible",
                "--apply-fixes",
                str(plan),
                "--fixed-out",
                str(fixed),
            ]
        )
        == 0
    )
    assert fixed.read_text(encoding="utf-8") == "We served 12 clients.\n"
    assert narrative.read_text(encoding="utf-8") == "We served 13 clients.\n"


def test_apply_fixes_without_fixed_out_refuses_rather_than_writing_in_place(
    tmp_path: Path,
) -> None:
    """The plan here is *valid and applicable*, which is the whole point.

    A malformed plan would be refused by the digest check three lines later and
    this test would pass with the missing-destination guard deleted -- an
    earlier branch returning before the thing under test is reached. So the plan
    is generated by the tool, is applicable as-is, and the only thing standing
    between it and an in-place rewrite is the guard.
    """

    narrative = tmp_path / "draft.md"
    narrative.write_text("We served 13 clients.\n", encoding="utf-8")
    plan = tmp_path / "fixes.json"
    base = ["audit", "--config", DEMO, "--narrative", str(narrative), "--reproducible"]
    assert main([*base, "--fixes-out", str(plan)]) == 1
    fixes = json.loads(plan.read_text(encoding="utf-8"))["fixes"]
    assert len(fixes) == 1, "the plan must be applicable or this proves nothing"

    assert main([*base, "--apply-fixes", str(plan)]) == 1
    assert narrative.read_text(encoding="utf-8") == "We served 13 clients.\n"
    assert sorted(item.name for item in tmp_path.iterdir()) == ["draft.md", "fixes.json"]


def test_a_plan_built_for_a_different_narrative_is_refused_whole() -> None:
    publishable = [_figure("served", 12.0, "12")]
    text = "We served 13 clients."
    plan = build_fix_plan(text, (explain_span(find_numbers(text)[0], publishable),))

    edited = "Last year, we served 13 clients."
    with pytest.raises(FixPlanRefused, match="different narrative"):
        apply_fix_plan(edited, plan, publishable, [])


def test_a_replacement_that_is_not_a_current_display_is_refused() -> None:
    """The plan is a proposal, so the applier re-derives the allowed set.

    A display that was publishable when the plan was written and is not now --
    because the data moved, or because suppression now withholds it -- must not
    be substituted on the plan's say-so.
    """

    publishable = [_figure("served", 12.0, "12")]
    text = "We served 13 clients."
    plan = build_fix_plan(text, (explain_span(find_numbers(text)[0], publishable),))

    with pytest.raises(FixPlanRefused, match="not the display of any publishable figure"):
        apply_fix_plan(text, plan, [_figure("served", 14.0, "14")], [])


def test_a_replacement_naming_a_withheld_display_is_refused_by_name() -> None:
    publishable = [_figure("served", 12.0, "12")]
    hidden = [_figure("tiny", 3.0, "3")]
    text = "We served 13 clients."
    plan = build_fix_plan(text, (explain_span(find_numbers(text)[0], publishable),))
    fixes = plan["fixes"]
    assert isinstance(fixes, list)
    fixes[0]["replace_with"] = "3"

    with pytest.raises(FixPlanRefused, match="withheld value"):
        apply_fix_plan(text, plan, publishable, hidden)


def test_overlapping_fixes_are_refused() -> None:
    publishable = [_figure("served", 12.0, "12")]
    text = "We served 1234 clients."
    plan = {
        "schema_version": FIX_PLAN_SCHEMA_VERSION,
        "narrative_sha256": narrative_digest(text),
        "fixes": [
            {"start": 10, "end": 14, "was": "1234", "replace_with": "12"},
            {"start": 12, "end": 14, "was": "34", "replace_with": "12"},
        ],
    }
    with pytest.raises(FixPlanRefused, match="overlap"):
        apply_fix_plan(text, plan, publishable, [])


@pytest.mark.parametrize(
    ("plan", "match"),
    [
        ("not an object", "not an object"),
        ({"schema_version": 99}, "schema_version"),
        ({"schema_version": FIX_PLAN_SCHEMA_VERSION}, "no 'fixes' list"),
        ({"schema_version": FIX_PLAN_SCHEMA_VERSION, "fixes": ["nope"]}, "not an object"),
    ],
)
def test_a_malformed_plan_is_refused_rather_than_partially_read(plan: object, match: str) -> None:
    with pytest.raises(FixPlanRefused, match=match):
        apply_fix_plan("text", plan, [], [])


@pytest.mark.parametrize(
    ("fix", "match"),
    [
        ({"start": True, "end": 2, "was": "1", "replace_with": "12"}, "boolean offsets"),
        ({"start": "0", "end": 2, "was": "1", "replace_with": "12"}, "integer offsets"),
        ({"start": 0, "end": 2, "was": 1, "replace_with": "12"}, "'was'/'replace_with'"),
        ({"start": 0, "end": 999, "was": "x", "replace_with": "12"}, "outside the narrative"),
        ({"start": 0, "end": 2, "was": "zz", "replace_with": "12"}, "but the narrative has"),
    ],
)
def test_a_fix_entry_that_no_longer_describes_the_text_is_refused(
    fix: dict[str, object], match: str
) -> None:
    text = "We served 13 clients."
    plan = {
        "schema_version": FIX_PLAN_SCHEMA_VERSION,
        "narrative_sha256": narrative_digest(text),
        "fixes": [fix],
    }
    with pytest.raises(FixPlanRefused, match=match):
        apply_fix_plan(text, plan, [_figure("served", 12.0, "12")], [])


# --- the other diagnosis classes -------------------------------------------


def test_a_percentage_written_as_a_bare_count_says_so() -> None:
    publishable = [_figure("rate", 87.5, "87.5%")]
    explanation = _only("Retention was 87.5 for the year.", publishable)

    assert explanation.remedy == "replace"
    assert "a count where the receipt is a percentage" in explanation.detail


def test_a_count_written_as_a_percentage_says_so() -> None:
    publishable = [_figure("served", 42.0, "42")]
    explanation = _only("We served 42% of them.", publishable)

    assert "a percentage where the receipt is a count" in explanation.detail


def test_the_same_digits_at_the_wrong_magnitude_name_the_separator() -> None:
    publishable = [_figure("cost", 12.34, "12.34")]
    explanation = _only("Cost per outcome was 1234 dollars.", publishable)

    assert explanation.candidates[0].reason == "magnitude"
    assert "thousands separator" in explanation.detail


def test_a_number_rounded_differently_is_named_as_rounding() -> None:
    publishable = [_figure("rate", 87.5, "87.5%")]
    explanation = _only("Retention was 88% this year.", publishable)

    assert explanation.candidates[0].reason == "rounding"
    assert "rounded differently" in explanation.detail


def test_an_ambiguous_span_is_told_the_convention_the_report_writes_in() -> None:
    """ADR 0011: "1.234" is refused a value reading and must match a display.

    The diagnosis says which display and that it must be written that way; it
    does not resolve the ambiguity, because resolving it is exactly what the
    gate refuses to do.
    """

    publishable = [_figure("cost", 1.234, "1.234")]
    explanation = _only("The rate was 1,234 per client.", publishable)

    assert explanation.candidates[0].reason == "separator_ambiguity"
    assert "exactly as the receipt writes it" in explanation.detail


def test_a_written_out_numeral_is_told_it_can_never_bind() -> None:
    publishable = [_figure("served", 12.0, "12")]
    explanation = _only("We served twelve clients.", publishable)

    assert explanation.remedy == "none"
    assert "written-out numeral" in explanation.detail


def test_candidate_order_does_not_depend_on_the_order_figures_arrive_in() -> None:
    """A fix plan has to be reproducible, so the ranking is a total order."""

    figures = [
        _figure("bravo", 12.0, "12"),
        _figure("alpha", 12.0, "12"),
        _figure("charlie", 11.5, "11.5"),
    ]
    forward = _only("We had 13 of them.", figures)
    backward = _only("We had 13 of them.", list(reversed(figures)))

    assert [item.metric_id for item in forward.candidates] == [
        item.metric_id for item in backward.candidates
    ]


def test_explain_unbound_diagnoses_a_plain_grounding_result() -> None:
    publishable = [_figure("served", 12.0, "12")]
    result = ground("We served 13 clients.", publishable)

    (explanation,) = explain_unbound(result.unbound, publishable)
    assert explanation.remedy == "replace"


# --- the Explanation record cannot be built into an empty suggestion --------


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"remedy": "wat"}, "unknown remedy"),
        ({"remedy": "replace"}, "requires at least one candidate"),
        ({"remedy": "review"}, "requires at least one candidate"),
    ],
)
def test_an_explanation_that_promises_a_remedy_it_has_no_candidate_for_is_refused(
    kwargs: dict[str, str], match: str
) -> None:
    span = find_numbers("13")[0]
    with pytest.raises(ValueError, match=match):
        Explanation(span=span, detail="", candidates=(), **kwargs)


def test_a_remedy_of_none_cannot_carry_candidates() -> None:
    publishable = [_figure("served", 12.0, "12")]
    explanation = _only("We served 13 clients.", publishable)
    with pytest.raises(ValueError, match="cannot carry candidates"):
        Explanation(
            span=explanation.span,
            remedy="none",
            detail="",
            candidates=explanation.candidates,
        )


def test_a_number_that_is_both_published_and_withheld_says_both() -> None:
    """The genuinely ambiguous disclosure.

    ``audit_narrative`` classifies this as a disclosure -- resolving it toward
    "they meant the published one" is the unsafe direction -- but the author
    cannot act on that without being told the number is also a figure the report
    does publish. Both facts, or the advice sends them to rewrite the wrong
    sentence.
    """

    publishable = [_figure("total_served", 6.0, "6")]
    hidden = [_figure("exits_permanent", 6.0, "6")]
    result = explain_audit(
        audit_narrative("We reached 6 households.", publishable, hidden), publishable, hidden
    )

    (explanation,) = result.explanations
    assert explanation.remedy == "remove"
    assert "withheld value of exits_permanent" in explanation.detail
    assert "also the published value of total_served" in explanation.detail
