"""The Scorecard floors hold, and a deduction is accepted only by name.

`tests/fixtures/scorecard/results-2026-08-15.json` is the real OpenSSF report
for commit 2326dd9 -- the one that turned `main` red. Nothing in this repository
had changed: OSV published GHSA-jmr9-qjv8-65gv against extract-zip 2.0.1, the
Vulnerabilities check dropped from 10 to 9, and the workflow's
`Vulnerabilities == 10` assertion failed. That advisory was then fixed properly,
by taking extract-zip out of the dependency graph, and its waiver was retired --
but the gate shape that turned a third party's publication into a red default
branch is unchanged, and the next advisory will arrive the same way.

So the floor stays and the deduction is adjudicated, exactly as SEC-12 already
does for `npm audit`. Because the committed registry now waives nothing, this
gate is currently identical in effect to the `== 10` assertion it replaces;
`test_with_nothing_waived_this_is_exactly_the_old_assertion` pins that. The
behavioural tests run against `tests/fixtures/npm-audit/waivers.yml` instead,
for the same reason the npm-audit gate's tests do: a mechanism tested only
while an exception happens to be live is untested exactly when it is needed.

These pin what the gate will *not* accept: an advisory with no waiver, an
advisory alongside the waived one, an expired or mislabelled waiver, a
deduction Scorecard declines to attribute, any other floor slipping, and a
report the gate cannot read. Every report below is either the recorded real one
or a mutation of it, so none of this needs a network call.
"""

from __future__ import annotations

import copy
import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from scripts.check_scorecard import main, named_advisories

ROOT = Path(__file__).resolve().parents[1]
WAIVERS = ROOT / "tests" / "fixtures" / "npm-audit" / "waivers.yml"
COMMITTED_WAIVERS = ROOT / "waivers.yml"
WORKFLOW = ROOT / ".github" / "workflows" / "scorecard.yml"
RECORDED = ROOT / "tests" / "fixtures" / "scorecard" / "results-2026-08-15.json"

WAIVED_ADVISORY = "GHSA-jmr9-qjv8-65gv"
TODAY = "2026-08-15"


def _recorded() -> dict[str, Any]:
    """Return a mutable copy of the real report from the red run."""

    loaded: dict[str, Any] = json.loads(RECORDED.read_text(encoding="utf-8"))
    return copy.deepcopy(loaded)


def _set_check(report: dict[str, Any], name: str, **fields: Any) -> dict[str, Any]:
    """Overwrite fields on one named check, in place, and return the report."""

    for check in report["checks"]:
        if check["name"] == name:
            check.update(fields)
            return report
    raise AssertionError(f"the recorded report has no {name} check")


def _write(tmp_path: Path, report: dict[str, Any]) -> str:
    path = tmp_path / "results.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    return str(path)


def _gate(
    tmp_path: Path, report: dict[str, Any], waivers: Path = WAIVERS, today: str = TODAY
) -> int:
    return main(["--report", _write(tmp_path, report), "--waivers", str(waivers), "--today", today])


def test_the_report_that_turned_main_red_is_accepted_by_a_waiver_that_names_it(
    tmp_path: Path,
) -> None:
    """The regression under repair, using the exact bytes OpenSSF produced."""

    report = _recorded()
    assert report["score"] == 7.0
    assert named_advisories(report) == [WAIVED_ADVISORY.upper()]
    assert _gate(tmp_path, report) == 0


def test_with_nothing_waived_this_is_exactly_the_old_assertion(tmp_path: Path) -> None:
    """Today the change is a no-op, and that is the point.

    The committed registry holds no dependency waiver, so against the real
    registry this gate accepts a Vulnerabilities score of 10 and rejects
    anything less -- byte for byte the behaviour of the `jq -e ... == 10`
    assertion it replaces. It only diverges once someone records a dated,
    owned, named exception, which is the decision this gate exists to allow.
    """

    clean = _set_check(_recorded(), "Vulnerabilities", score=10, details=None)
    assert main(["--report", _write(tmp_path, clean), "--waivers", str(COMMITTED_WAIVERS)]) == 0
    assert (
        main(["--report", _write(tmp_path, _recorded()), "--waivers", str(COMMITTED_WAIVERS)]) == 1
    )


def test_a_full_vulnerabilities_score_needs_no_waiver_at_all(tmp_path: Path) -> None:
    report = _set_check(_recorded(), "Vulnerabilities", score=10, details=None)
    assert _gate(tmp_path, report) == 0


def test_a_different_advisory_still_fails(tmp_path: Path) -> None:
    """The point of the whole exercise: the waiver is not an allowlist."""

    report = _set_check(
        _recorded(),
        "Vulnerabilities",
        score=9,
        details=["Warn: Project is vulnerable to: GHSA-aaaa-bbbb-cccc"],
    )
    assert _gate(tmp_path, report) == 1


def test_a_new_advisory_alongside_the_waived_one_still_fails(tmp_path: Path) -> None:
    report = _set_check(
        _recorded(),
        "Vulnerabilities",
        score=8,
        details=[
            f"Warn: Project is vulnerable to: {WAIVED_ADVISORY}",
            "Warn: Project is vulnerable to: GHSA-aaaa-bbbb-cccc",
        ],
    )
    assert _gate(tmp_path, report) == 1


def test_a_deduction_scorecard_will_not_attribute_fails_closed(tmp_path: Path) -> None:
    """Two points gone, one advisory named: the other one is not waived away."""

    report = _set_check(
        _recorded(),
        "Vulnerabilities",
        score=8,
        details=[f"Warn: Project is vulnerable to: {WAIVED_ADVISORY}"],
    )
    assert _gate(tmp_path, report) == 1


def test_a_deduction_with_no_advisory_named_at_all_fails_closed(tmp_path: Path) -> None:
    report = _set_check(_recorded(), "Vulnerabilities", score=9, details=None)
    assert _gate(tmp_path, report) == 1


def test_an_expired_waiver_accepts_nothing(tmp_path: Path) -> None:
    day_after = (date.fromisoformat("2026-11-15") + timedelta(days=1)).isoformat()
    assert _gate(tmp_path, _recorded(), today=day_after) == 1


def test_a_semgrep_waiver_cannot_accept_a_dependency_advisory(tmp_path: Path) -> None:
    """Waiver kinds are not interchangeable here either."""

    mislabelled = tmp_path / "waivers.yml"
    mislabelled.write_text(
        WAIVERS.read_text(encoding="utf-8").replace("    kind: npm-audit\n", "    kind: semgrep\n"),
        encoding="utf-8",
    )
    assert _gate(tmp_path, _recorded(), waivers=mislabelled) == 1


def test_no_waiver_moves_any_other_floor(tmp_path: Path) -> None:
    """Vulnerabilities is the only adjudicated check; the rest are assertions."""

    for name, below in (
        ("Pinned-Dependencies", 8),
        ("Token-Permissions", 9),
        ("Dangerous-Workflow", 9),
        ("Branch-Protection", 3),
        ("Signed-Releases", 9),
    ):
        assert _gate(tmp_path, _set_check(_recorded(), name, score=below)) == 1, name


def test_the_aggregate_ratchet_still_bites(tmp_path: Path) -> None:
    report = _recorded()
    report["score"] = 6.7
    assert _gate(tmp_path, report) == 1


def test_a_floor_the_report_does_not_measure_fails_closed(tmp_path: Path) -> None:
    """A check OpenSSF stopped emitting is an unmeasured floor, not a met one."""

    report = _recorded()
    report["checks"] = [check for check in report["checks"] if check["name"] != "Signed-Releases"]
    assert _gate(tmp_path, report) == 1


def test_a_missing_report_fails_closed(tmp_path: Path) -> None:
    """An analysis that produced no report is not an analysis that passed."""

    absent = tmp_path / "nothing.json"
    assert main(["--report", str(absent), "--waivers", str(WAIVERS), "--today", TODAY]) == 1


def test_an_empty_report_fails_closed(tmp_path: Path) -> None:
    empty = tmp_path / "results.json"
    empty.write_text("", encoding="utf-8")
    assert main(["--report", str(empty), "--waivers", str(WAIVERS), "--today", TODAY]) == 1


def test_a_report_shape_the_gate_cannot_read_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "results.json"
    path.write_text(json.dumps({"score": 9.9}), encoding="utf-8")
    assert main(["--report", str(path), "--waivers", str(WAIVERS), "--today", TODAY]) == 1


def test_the_workflow_actually_runs_this_gate() -> None:
    """A gate wired out of the workflow is the failure mode nobody notices."""

    text = WORKFLOW.read_text(encoding="utf-8")
    assert "python3 -m scripts.check_scorecard --report results.json" in text
    # The evidence has to survive a red run: reconstructing this report from a
    # log line is how the regression above had to be diagnosed in the first place.
    assert "if: ${{ !cancelled() && hashFiles('results.json') != '' }}" in text
    assert "name: scorecard-results" in text


def test_the_recorded_report_is_the_one_from_the_red_run() -> None:
    """Provenance for the fixture, so a future reader can re-derive it."""

    report = json.loads(RECORDED.read_text(encoding="utf-8"))
    assert report["repo"]["name"] == "github.com/ChelseaKR/outcome-receipts"
    assert report["repo"]["commit"] == "2326dd90af5fc5b237f0e9066ba675a65d5f31dc"
    assert report["date"] == "2026-08-15T07:34:00Z"
    assert report["scorecard"]["version"] == "v5.3.0"
