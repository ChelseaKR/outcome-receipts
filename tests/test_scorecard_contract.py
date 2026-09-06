"""Static contract tests tying the Scorecard CI floor to its own waiver.

SEC-38 (issue 92) found the committed Scorecard report overdue and its
recorded numbers no longer true. The floor and the waiver that justifies it
are two separate files (`.github/workflows/scorecard.yml`,
`waivers.yml`) that agree only by someone remembering to update both at
once; nothing mechanical checked that before. These tests don't re-run
Scorecard -- CI does that -- they pin that the *shape* of the waived floor
cannot silently drift out of sync with WVR-006 or with the dated report it
cites.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "scorecard.yml"
WAIVERS = ROOT / "waivers.yml"


def _wvr_006_block(text: str) -> str:
    match = re.search(r"^  - id: WVR-006\n(?:.+\n)+?(?=^  - id: |\Z)", text, re.MULTILINE)
    assert match is not None, "WVR-006 not found in waivers.yml"
    return match.group(0)


def test_scorecard_floor_matches_the_wvr_006_waiver() -> None:
    workflow_text = WORKFLOW.read_text(encoding="utf-8")
    floor_match = re.search(r"jq -e '\.score >= ([\d.]+)' results\.json", workflow_text)
    assert floor_match is not None, "scorecard.yml has no '.score >= N' floor assertion"
    floor = float(floor_match.group(1))

    block = _wvr_006_block(WAIVERS.read_text(encoding="utf-8"))
    reason_match = re.search(r"aggregate is ([\d.]+)", block)
    assert reason_match is not None, "WVR-006's reason does not state the measured aggregate"
    waived_aggregate = float(reason_match.group(1))

    # The floor is documented as sitting 0.1 below the measured aggregate
    # (routine Scorecard noise tolerance), never above it -- a floor above
    # the number the waiver justifies would fail on the very measurement
    # the waiver exists to accept.
    assert floor <= waived_aggregate
    assert waived_aggregate - floor < 0.5


def test_wvr_006_links_to_a_report_dated_on_or_after_its_grant_date() -> None:
    block = _wvr_006_block(WAIVERS.read_text(encoding="utf-8"))
    granted_match = re.search(r"granted:\s*(\d{4}-\d{2}-\d{2})", block)
    link_match = re.search(r"link:\s*(\S+)", block)
    assert granted_match is not None
    assert link_match is not None

    link = link_match.group(1)
    date_in_link = re.search(r"(\d{4}-\d{2}-\d{2})", link)
    assert date_in_link is not None, f"WVR-006 link {link!r} has no dated report name"
    assert date_in_link.group(1) == granted_match.group(1), (
        "WVR-006 links a report dated differently from its own `granted` date -- "
        "the waiver and the evidence it cites have drifted apart"
    )
    assert (ROOT / link).exists(), f"WVR-006 links a report that does not exist: {link}"


def test_wvr_006_expiry_does_not_exceed_the_maintained_score_clear_date() -> None:
    # Issue 92: "the honest move may be to shorten it rather than extend
    # it" -- the waiver's own reason names 2026-09-25 (90 days from the
    # 2026-06-27 first commit) as the date its Maintained-score premise
    # stops applying. The waiver should not coast past that date unreviewed.
    block = _wvr_006_block(WAIVERS.read_text(encoding="utf-8"))
    expires_match = re.search(r"expires:\s*(\d{4}-\d{2}-\d{2})", block)
    assert expires_match is not None
    assert expires_match.group(1) <= "2026-09-25"


def test_the_measured_scores_are_printed_and_kept_even_when_a_floor_fails() -> None:
    """The floors are enforced with `jq -e ... >/dev/null`, which prints nothing.

    On 2026-09-06 this job failed three consecutive times on `main` and the log
    said only "Process completed with exit code 1" -- not which floor broke, nor
    what the measurement was. `results.json` held the answer both times and was
    uploaded by a step that ran only after the floors passed, so the one run
    whose evidence a reader needs was the one that discarded it.

    Two properties, so that cannot recur: the scores are printed before anything
    is asserted, and the artifact upload is unconditional.
    """

    text = WORKFLOW.read_text(encoding="utf-8")

    report = text.index("Report every measured score before any of them is enforced")
    enforce = text.index("Enforce portfolio score floors")
    upload = text.index("actions/upload-artifact@")
    assert report < enforce, "the scores must be printed before a floor can abort the job"

    # The upload step's own `if:` directive, read as a line rather than as a
    # substring. Written as a substring first, this assertion passed while the
    # directive was deleted, because the comment above it quotes `if: always()`
    # in prose -- a check matching the explanation of the property instead of
    # the property. Proven by deleting the directive: this now fails.
    step = text[upload:]
    header = step[: step.index("with:")]
    directives = [
        line.strip()
        for line in header.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    assert "if: always()" in directives, (
        "the scorecard results upload is conditional, so a failing run -- the "
        "only run whose results.json anyone needs -- would not keep it"
    )
