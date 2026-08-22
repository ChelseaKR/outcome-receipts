"""Issue 94: the HUD suppression-calibration write-up's numbers, recomputed.

`docs/audits/hud-coc-suppression-calibration-2026-08-21.md` reports headline
numbers about running the shipped small-cell suppression engine over real HUD
2024 PIT-Count-by-CoC data. Every number in that write-up is required to trace
back to `scripts/hud_suppression_calibration.calibrate()`, run fresh here
against the committed `eval/hud/hud_pit_2024_by_coc_subpopulation.csv` --
not copied from a one-time notebook run and pasted into prose. If the
suppression engine's behavior ever changes, or the committed CSV is ever
edited, this is what catches the write-up going stale, the same way
`tests/test_release_compatibility.py` catches a receipts-manifest change the
frozen baseline no longer matches.
"""

from __future__ import annotations

from pathlib import Path

from scripts.hud_suppression_calibration import CSV_PATH, _figures_for_coc, calibrate, load_rows

from outcome_receipts.suppression import SUPPRESSION_THRESHOLD, suppress_figures

ROOT = Path(__file__).resolve().parents[1]


def test_source_csv_satisfies_its_own_documented_identities() -> None:
    """SOURCE.md claims two identities hold across the whole extract; reprove them."""

    by_coc = load_rows()
    assert len(by_coc) == 363

    for coc, rows in by_coc.items():
        by_subpopulation = {row["subpopulation"]: row for row in rows}
        assert set(by_subpopulation) == {
            "overall",
            "veterans",
            "chronically_homeless",
            "chronically_homeless_individuals",
            "chronically_homeless_in_families",
            "unaccompanied_youth_under25",
            "unaccompanied_youth_under18",
            "unaccompanied_youth_18to24",
            "parenting_youth_under25",
            "children_of_parenting_youth",
        }, f"{coc}: unexpected subpopulation set"

        for row in rows:
            overall = int(row["overall"])
            sheltered = int(row["sheltered_total"])
            unsheltered = int(row["unsheltered"])
            assert overall == sheltered + unsheltered, (
                f"{coc}/{row['subpopulation']}: overall != sheltered_total + unsheltered"
            )

        under25 = int(by_subpopulation["unaccompanied_youth_under25"]["overall"])
        under18 = int(by_subpopulation["unaccompanied_youth_under18"]["overall"])
        age_18to24 = int(by_subpopulation["unaccompanied_youth_18to24"]["overall"])
        assert under25 == under18 + age_18to24, f"{coc}: youth age-band nesting broken"

        chronic = int(by_subpopulation["chronically_homeless"]["overall"])
        chronic_individuals = int(by_subpopulation["chronically_homeless_individuals"]["overall"])
        chronic_families = int(by_subpopulation["chronically_homeless_in_families"]["overall"])
        assert chronic == chronic_individuals + chronic_families, (
            f"{coc}: chronically-homeless individuals/families nesting broken"
        )


def test_calibration_matches_the_committed_write_up() -> None:
    """Every headline number in the 2026-08-21 write-up, recomputed from the real engine."""

    result = calibrate()

    assert result["cocs"] == 363
    assert result["total_cells"] == 10890
    assert result["primary_suppressed_cells"] == 2832
    assert result["complementary_suppressed_cells"] == 3781
    assert result["total_suppressed_cells"] == 6613
    assert result["total_suppressed_share"] == 0.6073
    assert result["primary_suppressed_share"] == 0.2601
    assert result["true_zero_cells"] == 2005
    assert result["cocs_with_any_suppression"] == 352
    assert result["cocs_needing_complementary_suppression"] == 346
    assert result["cocs_needing_complementary_suppression_share"] == 0.9532
    assert result["zero_adjacent_to_small_cell_triples"] == 630
    assert result["total_triples"] == 3630
    assert result["zero_adjacent_share"] == 0.1736

    rates = result["per_subpopulation_primary_suppression_rate"]
    assert rates["overall"] == 0.0101
    assert rates["veterans"] == 0.3095
    assert rates["parenting_youth_under25"] == 0.4426
    assert rates["unaccompanied_youth_under18"] == 0.3581
    # The coarsest breakdown (whole-CoC totals) is suppressed far less often
    # than every named subpopulation -- the write-up's central claim, pinned
    # here so a change that erodes it can't pass silently.
    assert rates["overall"] < min(v for k, v in rates.items() if k != "overall")


def test_a_named_real_example_from_the_write_up_reproduces() -> None:
    """AK-500's unaccompanied-youth triple, as cited in the write-up.

    Overall unaccompanied youth (under 25) is 141; the 18-24 age band alone is
    131; both are comfortably above the suppression threshold on their own.
    But the under-18 age band is 10 -- itself suppressed -- and 141 - 131 = 10
    would hand a reader the suppressed value directly if the 18-24 figure were
    left visible. The engine must suppress the 18-24 figure too.
    """

    by_coc = load_rows()
    ak_500 = {row["subpopulation"]: row for row in by_coc["AK-500"]}
    assert int(ak_500["unaccompanied_youth_under25"]["overall"]) == 141
    assert int(ak_500["unaccompanied_youth_18to24"]["overall"]) == 131
    assert int(ak_500["unaccompanied_youth_under18"]["overall"]) == 10

    figures = _figures_for_coc(by_coc["AK-500"])
    _redacted, result = suppress_figures(figures, threshold=SUPPRESSION_THRESHOLD)

    assert "unaccompanied_youth_under18__overall" in result.suppressed
    assert "unaccompanied_youth_18to24__overall" in result.complementary_suppressed
    assert "unaccompanied_youth_under25__overall" not in (
        result.suppressed + result.complementary_suppressed
    )


def test_calibration_is_run_against_the_committed_csv_path() -> None:
    assert CSV_PATH == ROOT / "eval" / "hud" / "hud_pit_2024_by_coc_subpopulation.csv"
    assert CSV_PATH.exists()
