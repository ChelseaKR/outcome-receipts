"""Extract eval/hud/hud_pit_2024_by_coc_subpopulation.csv from HUD's raw PIT file.

One-time, human-run data-preparation script. Not part of `make verify`, not a
project dependency: run it in an ad hoc environment with pandas, pyxlsb, and
openpyxl (pyxlsb reads the source .xlsb; openpyxl is pandas' writer backend).
See SOURCE.md in this directory for where the source file comes from, its
checksum, and why this script filters and selects the columns it does.

    curl -A "Mozilla/5.0" \\
      https://www.huduser.gov/portal/sites/default/files/xls/2007-2024-PIT-Counts-by-CoC.xlsb \\
      -o 2007-2024-PIT-Counts-by-CoC.xlsb
    uv run --with pandas --with pyxlsb --with openpyxl python3 extract.py
"""

import pandas as pd

df = pd.read_excel("2007-2024-PIT-Counts-by-CoC.xlsb", sheet_name="2024", engine="pyxlsb")

# Only CoCs that did a full sheltered+unsheltered count this year: the
# Overall = Sheltered Total + Unsheltered identity is only meaningful for
# these. "Sheltered-Only Count" CoCs have no real unsheltered figure that
# year (blank/waived under HUD's biennial unsheltered-count policy, not a
# true zero), and mixing them in would silently treat "not counted" as
# "counted as zero" -- the absence-rendered-as-a-value bug class this
# portfolio has hit before, here at the data-ingestion boundary rather than
# in this repository's own code.
full = df[df["Count Types"] == "Sheltered and Unsheltered Count"].copy()

# subpopulation name -> (overall column, sheltered-total column, unsheltered column)
GROUPS = {
    "overall": (
        "Overall Homeless",
        "Sheltered Total Homeless",
        "Unsheltered Homeless",
    ),
    "veterans": (
        "Overall Homeless Veterans",
        "Sheltered Total Homeless Veterans",
        "Unsheltered Homeless Veterans",
    ),
    "chronically_homeless": (
        "Overall Chronically Homeless",
        "Sheltered Total Chronically Homeless",
        "Unsheltered Chronically Homeless",
    ),
    "chronically_homeless_individuals": (
        "Overall Chronically Homeless Individuals",
        "Sheltered Total Chronically Homeless Individuals",
        "Unsheltered Chronically Homeless Individuals",
    ),
    "chronically_homeless_in_families": (
        "Overall Chronically Homeless People in Families",
        "Sheltered Total Chronically Homeless People in Families",
        "Unsheltered Chronically Homeless People in Families",
    ),
    "unaccompanied_youth_under25": (
        "Overall Homeless Unaccompanied Youth (Under 25)",
        "Sheltered Total Homeless Unaccompanied Youth (Under 25)",
        "Unsheltered Homeless Unaccompanied Youth (Under 25)",
    ),
    "unaccompanied_youth_under18": (
        "Overall Homeless Unaccompanied Youth Under 18",
        "Sheltered Total Homeless Unaccompanied Youth Under 18",
        "Unsheltered Homeless Unaccompanied Youth Under 18",
    ),
    "unaccompanied_youth_18to24": (
        "Overall Homeless Unaccompanied Youth Age 18-24",
        "Sheltered Total Homeless Unaccompanied Youth Age 18-24",
        "Unsheltered Homeless Unaccompanied Youth Age 18-24",
    ),
    "parenting_youth_under25": (
        "Overall Homeless Parenting Youth (Under 25)",
        "Sheltered Total Homeless Parenting Youth (Under 25)",
        "Unsheltered Homeless Parenting Youth (Under 25)",
    ),
    "children_of_parenting_youth": (
        "Overall Homeless Children of Parenting Youth",
        "Sheltered Total Homeless Children of Parenting Youth",
        "Unsheltered Homeless Children of Parenting Youth",
    ),
}

missing = [
    (name, column)
    for name, columns in GROUPS.items()
    for column in columns
    if column not in df.columns
]
if missing:
    raise SystemExit(f"MISSING COLUMNS (HUD workbook schema changed?): {missing}")

rows = []
for _, coc_row in full.iterrows():
    for subpopulation, (overall_col, sheltered_col, unsheltered_col) in GROUPS.items():
        overall, sheltered_total, unsheltered = (
            coc_row[overall_col],
            coc_row[sheltered_col],
            coc_row[unsheltered_col],
        )
        for value in (overall, sheltered_total, unsheltered):
            assert float(value) == int(value), (coc_row["CoC Number"], subpopulation, value)
        rows.append(
            {
                "coc_number": coc_row["CoC Number"],
                "coc_category": coc_row["CoC Category"],
                "subpopulation": subpopulation,
                "overall": int(overall),
                "sheltered_total": int(sheltered_total),
                "unsheltered": int(unsheltered),
            }
        )

out = pd.DataFrame(rows)
out.to_csv("hud_pit_2024_by_coc_subpopulation.csv", index=False)
print(f"wrote {len(out)} rows for {full.shape[0]} CoCs x {len(GROUPS)} subpopulation groups")
