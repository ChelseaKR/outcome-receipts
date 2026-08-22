#!/usr/bin/env python3
"""Run the shipped small-cell suppression engine over real HUD CoC PIT data.

Issue 94: does the shipped default (`SUPPRESSION_THRESHOLD = 11`, the CMS Cell
Size Suppression Policy) match real practice in the domain this tool targets?
`docs/ROADMAP.md` already names the gap: CMS, not HUD, supplies the numeric
default, because HUD's own HMIS publication guide leaves the number to local
policy. This script answers the calibration question the ROADMAP could only
pose, against real data: `eval/hud/hud_pit_2024_by_coc_subpopulation.csv`, an
extract of HUD's own 2024 Point-in-Time Count by CoC (see `eval/hud/SOURCE.md`
for provenance, checksums, and the extraction recipe).

For each of the 363 CoCs that did a full sheltered-and-unsheltered count, this
builds one report-shaped `Figure` set (10 named subpopulations x 3 components
-- Overall, Sheltered Total, Unsheltered -- 30 count figures, the same shape
and rough scale `suppress_figures`'s own docstring assumes: "report figure
sets are small, tens of figures at most") and runs the real, unmodified
`outcome_receipts.suppression.suppress_figures` against it -- not a
reimplementation, the exact function `receipts run` calls.

Run directly for a human-readable summary:

    .venv/bin/python scripts/hud_suppression_calibration.py

`calibrate()` is also imported directly by
`tests/test_hud_suppression_calibration.py`, which asserts today's committed
headline numbers in `docs/audits/hud-coc-suppression-calibration-2026-08-21.md`
still match a fresh recomputation from the committed CSV -- so a future change
to the suppression engine, or an edit to the CSV, cannot leave the write-up's
numbers silently stale.
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from outcome_receipts.models import Figure, Receipt
from outcome_receipts.suppression import SUPPRESSION_THRESHOLD, suppress_figures

ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "eval" / "hud" / "hud_pit_2024_by_coc_subpopulation.csv"

#: The three components extracted per subpopulation; see extract.py. Their sum
#: identity (overall == sheltered_total + unsheltered) is what makes
#: complementary suppression something this data can actually exercise.
COMPONENTS = ("overall", "sheltered_total", "unsheltered")


def load_rows(csv_path: Path = CSV_PATH) -> dict[str, list[dict[str, str]]]:
    """CoC number -> its ten subpopulation rows, in committed-file order."""

    by_coc: dict[str, list[dict[str, str]]] = defaultdict(list)
    with csv_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            by_coc[row["coc_number"]].append(row)
    return by_coc


def _figures_for_coc(rows: list[dict[str, str]]) -> list[Figure]:
    """One `Figure` per (subpopulation, component) cell, as `suppress_figures` expects."""

    figures = []
    for row in rows:
        subpopulation = row["subpopulation"]
        for component in COMPONENTS:
            metric_id = f"{subpopulation}__{component}"
            value = float(row[component])
            figures.append(
                Figure(
                    metric_id=metric_id,
                    value=value,
                    display=str(int(value)),
                    receipt=Receipt(
                        metric_id=metric_id,
                        value_sql="-- HUD 2024 PIT Count by CoC (published aggregate)",
                        row_count=None,
                        slice_hash=None,
                        value=value,
                        unit="count",
                        computed_at="2026-08-21T00:00:00Z",
                        definition=f"HUD 2024 PIT {subpopulation} ({component})",
                        data_source="HUD 2024 PIT Count by CoC",
                    ),
                )
            )
    return figures


def calibrate(csv_path: Path = CSV_PATH) -> dict[str, Any]:
    """Run `suppress_figures` per CoC and tabulate the three questions issue 94 asks."""

    by_coc = load_rows(csv_path)

    total_cells = 0
    primary_suppressed = 0
    complementary_suppressed = 0
    true_zero_cells = 0
    cocs_with_any_suppression = 0
    cocs_needing_complementary = 0
    per_subpopulation_cells: dict[str, int] = defaultdict(int)
    per_subpopulation_primary: dict[str, int] = defaultdict(int)
    zero_adjacent_triples = 0
    total_triples = 0

    for _coc, rows in sorted(by_coc.items()):
        figures = _figures_for_coc(rows)
        _redacted, result = suppress_figures(figures, threshold=SUPPRESSION_THRESHOLD)

        total_cells += len(figures)
        primary_suppressed += len(result.suppressed)
        complementary_suppressed += len(result.complementary_suppressed)
        if result.suppressed or result.complementary_suppressed:
            cocs_with_any_suppression += 1
        if result.complementary_suppressed:
            cocs_needing_complementary += 1
        true_zero_cells += sum(1 for _mid, value in result.values if value == 0)

        for row in rows:
            subpopulation = row["subpopulation"]
            for component in COMPONENTS:
                per_subpopulation_cells[subpopulation] += 1
                metric_id = f"{subpopulation}__{component}"
                if metric_id in result.suppressed:
                    per_subpopulation_primary[subpopulation] += 1
            values = [int(row[c]) for c in COMPONENTS]
            total_triples += 1
            if any(v == 0 for v in values) and any(1 <= v <= 10 for v in values):
                zero_adjacent_triples += 1

    total_suppressed = primary_suppressed + complementary_suppressed
    return {
        "cocs": len(by_coc),
        "total_cells": total_cells,
        "primary_suppressed_cells": primary_suppressed,
        "complementary_suppressed_cells": complementary_suppressed,
        "total_suppressed_cells": total_suppressed,
        "total_suppressed_share": round(total_suppressed / total_cells, 4),
        "primary_suppressed_share": round(primary_suppressed / total_cells, 4),
        "true_zero_cells": true_zero_cells,
        "cocs_with_any_suppression": cocs_with_any_suppression,
        "cocs_needing_complementary_suppression": cocs_needing_complementary,
        "cocs_needing_complementary_suppression_share": round(
            cocs_needing_complementary / len(by_coc), 4
        ),
        "zero_adjacent_to_small_cell_triples": zero_adjacent_triples,
        "total_triples": total_triples,
        "zero_adjacent_share": round(zero_adjacent_triples / total_triples, 4),
        "per_subpopulation_primary_suppression_rate": {
            subpopulation: round(per_subpopulation_primary[subpopulation] / cells, 4)
            for subpopulation, cells in sorted(per_subpopulation_cells.items())
        },
    }


def main() -> int:
    print(json.dumps(calibrate(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
