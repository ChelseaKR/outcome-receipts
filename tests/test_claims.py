"""The comparative-claim gate.

Two invariants are under test and they fail in opposite directions. The detector must
not miss a direction word, because a missed one is a claim the drafter got to make for
free. The binder must not bind a claim to something that is not a receipted direction,
because that would be the gate manufacturing the very thing it exists to check.

The catalog and the compiled detector are checked against each other, in both
directions, so a phrase added to one and not the other is a failure rather than a
silent hole.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from outcome_receipts import claims
from outcome_receipts.claims import (
    DECREASE,
    INCREASE,
    KIND_DIRECTION,
    KIND_EVALUATIVE,
    KIND_MAGNITUDE,
    KIND_PROPORTION,
    KIND_RANK,
    NO_CHANGE,
    STATUS_BOUND,
    STATUS_CONTRADICTED,
    STATUS_DISCLOSED,
    STATUS_UNBOUND,
    UNBINDABLE_KINDS,
    ClaimAudit,
    ClaimVerdict,
    DirectionEvidence,
    audit_claims,
    audit_payload,
    evidence_from_rows,
    find_claims,
    summarize,
    vocabulary,
)
from outcome_receipts.cli import main
from outcome_receipts.comparison import ComparisonRow
from outcome_receipts.models import REDACTED_DISPLAY, Figure, Receipt


def _figure(metric_id: str, *, suppressed: bool = False) -> Figure:
    return Figure(
        metric_id=metric_id,
        value=None if suppressed else 12.0,
        display=REDACTED_DISPLAY if suppressed else "12",
        receipt=Receipt(
            metric_id=metric_id,
            value_sql="SELECT COUNT(*) FROM data",
            row_count=None if suppressed else 3,
            slice_hash=None if suppressed else "a" * 64,
            value=None if suppressed else 12.0,
            unit="count",
            computed_at="2026-01-01T00:00:00Z",
            definition="how the figure is defined",
            suppressed=suppressed,
        ),
    )


def _row(base: str, direction: str, *, suppressed: bool = False) -> ComparisonRow:
    return ComparisonRow(
        base_metric_id=base,
        description=base,
        prior=_figure(f"{base}__prior", suppressed=suppressed),
        current=_figure(f"{base}__current", suppressed=suppressed),
        delta=_figure(f"{base}__delta", suppressed=suppressed),
        direction=direction,
    )


class TestVocabularyAndDetectorAgree:
    """The catalog is the specification; the regex is a compiled copy of it.

    Both directions are asserted because they fail differently: an entry the detector
    cannot find is a word the gate silently permits, and a phrase the detector finds
    that is not an entry would have no kind to report and would raise on lookup.
    """

    @pytest.mark.parametrize("entry", vocabulary(), ids=lambda entry: entry[0])
    def test_every_catalog_entry_is_findable(self, entry: tuple[str, str, str | None]) -> None:
        phrase, kind, direction = entry
        found = find_claims(f"The report says {phrase} for the period.")
        assert [(span.text.casefold(), span.kind, span.direction) for span in found] == [
            (phrase.casefold(), kind, direction)
        ]

    def test_nothing_findable_is_outside_the_catalog(self) -> None:
        catalog = {phrase.casefold() for phrase, _k, _d in vocabulary()}
        corpus = " ".join(phrase for phrase, _k, _d in vocabulary())
        assert {span.text.casefold() for span in find_claims(corpus)} <= catalog

    def test_a_direction_entry_always_carries_a_direction_and_no_other_kind_does(self) -> None:
        for phrase, kind, direction in vocabulary():
            if kind == KIND_DIRECTION:
                assert direction in (INCREASE, DECREASE, NO_CHANGE), phrase
            else:
                assert kind in UNBINDABLE_KINDS, phrase
                assert direction is None, phrase

    def test_no_entry_appears_twice(self) -> None:
        phrases = [phrase.casefold() for phrase, _k, _d in vocabulary()]
        assert len(phrases) == len(set(phrases))


class TestDetector:
    def test_it_is_case_insensitive(self) -> None:
        assert [span.direction for span in find_claims("Placements ROSE.")] == [INCREASE]

    def test_a_line_wrapped_phrase_is_not_a_hole(self) -> None:
        """A narrative template is wrapped in the spec file, so a multi-word entry
        arrives with a newline inside it. Matching only single-space text would let a
        drafter through on formatting alone."""
        found = find_claims("The figure was\nunchanged, and outcomes stayed\n  the same.")
        assert [span.direction for span in found] == [NO_CHANGE, NO_CHANGE]

    def test_it_does_not_fire_inside_a_longer_word(self) -> None:
        assert find_claims("The uppermost roster and the fellowship") == []

    def test_offsets_locate_the_phrase_in_the_text(self) -> None:
        text = "Exits fell this quarter."
        span = find_claims(text)[0]
        assert text[span.start : span.end] == "fell"

    def test_prose_with_no_comparative_form_yields_nothing(self) -> None:
        assert find_claims("We served 412 clients and exited 288 of them.") == []


class TestUnbindableKinds:
    """Four families are detected and can never bind, each for its own reason."""

    @pytest.mark.parametrize(
        ("text", "kind"),
        [
            ("Outcomes improved this quarter.", KIND_EVALUATIVE),
            ("Placements doubled.", KIND_MAGNITUDE),
            ("Most clients exited to permanent housing.", KIND_PROPORTION),
            ("This was the highest quarter on record.", KIND_RANK),
        ],
    )
    def test_they_are_unbound_even_with_a_perfectly_agreeing_comparison(
        self, text: str, kind: str
    ) -> None:
        evidence = (
            DirectionEvidence("placements", INCREASE),
            DirectionEvidence("exits", DECREASE),
            DirectionEvidence("spend", NO_CHANGE),
        )
        audit = audit_claims(text, evidence)
        assert [verdict.status for verdict in audit.verdicts] == [STATUS_UNBOUND]
        assert audit.verdicts[0].span.kind == kind
        assert not audit.ok

    def test_the_reason_says_what_is_missing_not_merely_that_it_missed(self) -> None:
        audit = audit_claims("Outcomes improved.", (DirectionEvidence("placements", INCREASE),))
        assert "polarity" in audit.unbound[0].detail

    def test_a_ratio_claim_says_no_figure_is_a_ratio(self) -> None:
        audit = audit_claims("Placements doubled.", (DirectionEvidence("p", INCREASE),))
        assert "ratio" in audit.unbound[0].detail


class TestBindingADirection:
    def test_a_claim_agreeing_with_a_receipted_direction_binds(self) -> None:
        audit = audit_claims("Placements rose.", (DirectionEvidence("placements", INCREASE),))
        assert [verdict.status for verdict in audit.verdicts] == [STATUS_BOUND]
        assert audit.ok
        assert audit.bound[0].metric_ids == ("placements",)

    def test_a_claim_contradicting_every_receipted_direction_is_refused(self) -> None:
        """The Done-when case: the message names both the claim and what the receipts
        actually say, because "unbound" alone would send the author looking for a
        missing metric rather than at a sentence that is false."""
        audit = audit_claims("Placements rose.", (DirectionEvidence("placements", DECREASE),))
        assert [verdict.status for verdict in audit.verdicts] == [STATUS_CONTRADICTED]
        assert not audit.ok
        detail = audit.contradicted[0].detail
        assert "'rose'" in detail
        assert "placements decrease" in detail

    def test_a_claim_with_no_declared_comparison_at_all_is_unbound(self) -> None:
        audit = audit_claims("Placements rose.", ())
        assert [verdict.status for verdict in audit.verdicts] == [STATUS_UNBOUND]
        assert "declares no comparison" in audit.unbound[0].detail

    def test_no_change_is_a_direction_like_any_other(self) -> None:
        assert audit_claims("Exits were unchanged.", (DirectionEvidence("e", NO_CHANGE),)).ok
        assert not audit_claims("Exits were unchanged.", (DirectionEvidence("e", INCREASE),)).ok

    def test_a_spanish_claim_binds_exactly_as_its_english_counterpart_does(self) -> None:
        evidence = (DirectionEvidence("colocaciones", INCREASE),)
        assert audit_claims("Las colocaciones aumentaron.", evidence).ok
        assert audit_claims("Placements rose.", evidence).ok
        assert not audit_claims("Las colocaciones bajaron.", evidence).ok


class TestDisclosure:
    """A direction word recovers a withheld comparison. This is #75 through prose."""

    def test_a_claim_agreeing_only_with_a_withheld_row_is_a_disclosure(self) -> None:
        audit = audit_claims("Exits fell.", (DirectionEvidence("exits", DECREASE, withheld=True),))
        assert [verdict.status for verdict in audit.verdicts] == [STATUS_DISCLOSED]
        assert not audit.ok
        assert "withholds" in audit.disclosed[0].detail

    def test_a_disclosure_outranks_a_binding(self) -> None:
        """The fail-closed ordering ``audit_narrative`` uses for a number that is both
        a publishable figure and a protected cell's raw value. Nothing in the text says
        which row the sentence is about, so the unsafe reading is the one that governs."""
        audit = audit_claims(
            "Exits fell.",
            (
                DirectionEvidence("exits", DECREASE, withheld=True),
                DirectionEvidence("spend", DECREASE),
            ),
        )
        assert [verdict.status for verdict in audit.verdicts] == [STATUS_DISCLOSED]
        assert audit.disclosed[0].metric_ids == ("exits",)

    def test_a_withheld_row_that_disagrees_does_not_make_a_claim_a_disclosure(self) -> None:
        audit = audit_claims(
            "Exits rose.",
            (
                DirectionEvidence("exits", DECREASE, withheld=True),
                DirectionEvidence("spend", INCREASE),
            ),
        )
        assert [verdict.status for verdict in audit.verdicts] == [STATUS_BOUND]


class TestEvidenceFromRows:
    def test_a_row_carries_its_real_direction(self) -> None:
        evidence = evidence_from_rows([_row("placements", INCREASE)])
        assert evidence == (DirectionEvidence("placements", INCREASE, withheld=False),)

    def test_a_row_whose_figures_were_suppressed_is_marked_withheld(self) -> None:
        evidence = evidence_from_rows(
            [_row("placements", INCREASE)], withheld_metric_ids=["placements__current"]
        )
        assert evidence[0].withheld is True

    def test_a_row_already_redacted_is_dropped_rather_than_read(self) -> None:
        """``redact_comparison`` overwrites ``direction`` with the suppression
        sentinel. Reading that as a fourth direction would compare a claim against a
        string, and a caller who passed the redacted rows would silently get a gate
        that binds nothing rather than a loud mistake."""
        assert evidence_from_rows([_row("placements", REDACTED_DISPLAY)]) == ()

    def test_a_figure_suppressed_in_its_own_receipt_marks_the_row_withheld(self) -> None:
        assert evidence_from_rows([_row("p", INCREASE, suppressed=True)])[0].withheld is True


class TestAuditShape:
    def test_a_narrative_with_no_comparative_form_is_an_empty_passing_audit(self) -> None:
        """The compatibility guarantee: a spec whose prose carries no vocabulary entry
        gates exactly as it did before this module existed."""
        audit = audit_claims("We served 412 clients.", (DirectionEvidence("p", INCREASE),))
        assert audit == ClaimAudit()
        assert audit.ok
        assert audit.total == 0

    def test_verdicts_come_back_in_the_order_the_claims_appear(self) -> None:
        audit = audit_claims(
            "Placements rose, spend was unchanged, and outcomes improved.",
            (DirectionEvidence("placements", INCREASE), DirectionEvidence("spend", NO_CHANGE)),
        )
        assert [verdict.span.text for verdict in audit.verdicts] == [
            "rose",
            "unchanged",
            "improved",
        ]

    def test_an_unknown_status_is_refused_rather_than_reported(self) -> None:
        with pytest.raises(ValueError, match="unknown claim status"):
            ClaimVerdict(span=find_claims("rose")[0], status="probably-fine", detail="")

    def test_the_summary_counts_are_computed_from_the_verdicts(self) -> None:
        audit = audit_claims(
            "Placements rose, exits fell, and most clients improved.",
            (DirectionEvidence("placements", INCREASE),),
        )
        summary = summarize(audit)
        assert summary.total == audit.total
        assert summary.bound + summary.unbound + summary.contradicted + summary.disclosed == (
            summary.total
        )
        assert summary.by_kind == {KIND_DIRECTION: 2, KIND_PROPORTION: 1, KIND_EVALUATIVE: 1}


class TestPayload:
    def test_only_the_blocking_verdicts_are_listed(self) -> None:
        audit = audit_claims(
            "Placements rose and exits rose.", (DirectionEvidence("placements", INCREASE),)
        )
        payload = audit_payload(audit)
        assert payload["bound"] == 2
        assert payload["blocking"] == []

    def test_a_blocking_verdict_carries_its_span_kind_and_reason(self) -> None:
        audit = audit_claims("Exits rose.", (DirectionEvidence("exits", DECREASE),))
        blocking = audit_payload(audit)["blocking"]
        assert isinstance(blocking, list)
        entry = blocking[0]
        assert entry["status"] == STATUS_CONTRADICTED
        assert entry["kind"] == KIND_DIRECTION
        assert entry["direction"] == INCREASE
        assert entry["text"] == "rose"
        assert entry["metric_ids"] == ["exits"]

    def test_the_payload_is_json_serialisable(self) -> None:
        import json

        json.dumps(audit_payload(audit_claims("Exits rose.", (DirectionEvidence("e", DECREASE),))))


class TestKnownCollisions:
    """Recorded so a future reader knows they were measured, not overlooked."""

    def test_declined_meaning_refused_is_detected_as_a_decrease_claim(self) -> None:
        """ "12 clients declined services" is ordinary prose in this domain and it is
        blocked. That is the fail-closed direction, matching a gate that already blocks
        a stray "2024", and the author is told the exact word and offset."""
        found = find_claims("Twelve clients declined services.")
        assert [(span.text, span.kind, span.direction) for span in found] == [
            ("declined", KIND_DIRECTION, DECREASE)
        ]

    def test_no_example_report_narrative_carries_a_vocabulary_entry(self) -> None:
        """The committed examples and the compat fixtures must gate as before. Their
        caveats do use "dropped", which is why the gate is scoped to the drafted
        narrative and not to every string in a spec."""
        import tomllib
        from pathlib import Path

        root = Path(__file__).resolve().parents[1]
        specs = sorted(root.glob("examples/*/report.toml")) + sorted(
            root.glob("tests/fixtures/compat/*/report.toml")
        )
        assert specs, "no example specs found to check"
        for path in specs:
            report = tomllib.loads(path.read_text(encoding="utf-8")).get("report", {})
            narratives = [report.get("template")] + [
                template.get("template") for template in report.get("templates", []) or []
            ]
            for narrative in narratives:
                if narrative:
                    assert find_claims(narrative) == [], path


def test_the_module_exposes_the_catalog_as_a_tuple_not_a_mutable_list() -> None:
    """A caller that could append to the vocabulary could widen the gate at runtime."""

    assert isinstance(claims.vocabulary(), tuple)


# --------------------------------------------------------------------------
# End to end: the gate has to actually refuse an export, not merely have an opinion.
# --------------------------------------------------------------------------

GRANT_REPORT = Path(__file__).resolve().parents[1] / "examples" / "grant-report"


def _spec_with_narrative(tmp_path: Path, sentence: str) -> str:
    """The committed grant-report example, with one sentence added to its narrative.

    The example is used rather than an invented spec because its comparison is real:
    four metrics, two increasing and two decreasing, every direction from a receipted
    delta. A sentence bolted onto its narrative is exactly what a drafter would emit.
    """

    destination = tmp_path / "grant"
    shutil.copytree(GRANT_REPORT, destination)
    spec = destination / "report.toml"
    text = spec.read_text(encoding="utf-8")
    marker = "The permanent-housing rate for the \\\nperiod was {pct_permanent}."
    assert marker in text, "the example narrative moved; this fixture needs updating"
    spec.write_text(text.replace(marker, f"{marker} {sentence}", 1), encoding="utf-8")
    return str(spec)


class TestExportIsActuallyRefused:
    def test_a_claim_no_receipted_direction_supports_blocks_the_export(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Every declared comparison moved. A narrative saying nothing changed is
        false, and the gate refuses rather than exporting a receipted report with an
        unreceipted sentence in it."""
        config = _spec_with_narrative(tmp_path, "Outcomes were unchanged this period.")
        code = main(
            ["run", "--config", config, "--out", str(tmp_path / "out"), "--reproducible", "--json"]
        )
        payload = json.loads(capsys.readouterr().out)
        assert code != 0
        assert payload["gate_pass"] is False
        blocking = payload["comparative_claims"]["report"]["blocking"]
        assert [entry["status"] for entry in blocking] == [STATUS_CONTRADICTED]
        assert not (tmp_path / "out").exists() or not list((tmp_path / "out").glob("report.md"))

    def test_an_evaluative_claim_blocks_even_though_every_number_binds(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """The leak this gate exists for: the drafter invents a direction, not a digit,
        so the numeric gate sees nothing wrong."""
        config = _spec_with_narrative(tmp_path, "Outcomes improved this period.")
        code = main(
            ["run", "--config", config, "--out", str(tmp_path / "out"), "--reproducible", "--json"]
        )
        payload = json.loads(capsys.readouterr().out)
        assert code != 0
        assert payload["narrative"]["unbound"] == 0, "every number still binds"
        assert payload["comparative_claims"]["report"]["unbound"] == 1

    def test_a_direction_claim_over_a_suppressed_comparison_is_a_disclosure(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Measured on the committed example, and it is the #75 leak through prose.

        Every one of the grant report's four comparison rows has a suppressed figure:
        each delta is smaller than the threshold, and complementary suppression takes a
        period figure with it. ``_redact_row_direction`` therefore renders the whole
        direction column as the suppression sentinel, so the report itself refuses to
        say which way anything moved. A sentence saying "rose" publishes exactly that,
        beside a table that declines to. It is reported as a disclosure and not as
        merely unbound, because the remedies differ: this one is a privacy finding.
        """
        config = _spec_with_narrative(tmp_path, "The number we served rose.")
        code = main(
            ["run", "--config", config, "--out", str(tmp_path / "out"), "--reproducible", "--json"]
        )
        payload = json.loads(capsys.readouterr().out)
        assert code != 0
        assert payload["narrative"]["unbound"] == 0, "every number still binds"
        report = payload["comparative_claims"]["report"]
        assert report["disclosed"] == 1
        assert [entry["status"] for entry in report["blocking"]] == [STATUS_DISCLOSED]

    def test_a_claim_a_published_direction_supports_does_not_block(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """The same sentence over a comparison nothing withholds. Split from the case
        above so a change that made every claim a disclosure could not pass as a
        working gate."""
        audit = audit_claims(
            "The number we served rose.", (DirectionEvidence("clients_served", INCREASE),)
        )
        assert audit.ok
        assert [verdict.status for verdict in audit.verdicts] == [STATUS_BOUND]

    def test_the_committed_example_is_unaffected(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A narrative with no comparative form gates exactly as it did before."""
        main(
            [
                "run",
                "--config",
                str(GRANT_REPORT / "report.toml"),
                "--out",
                str(tmp_path / "out"),
                "--reproducible",
                "--json",
            ]
        )
        payload = json.loads(capsys.readouterr().out)
        assert payload["gate_pass"] is True
        assert payload["comparative_claims"]["report"]["total"] == 0
