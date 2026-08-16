"""Passing and failing fixtures for the six bounded evidence workflows."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from outcome_receipts.cli import EXIT_OK, EXIT_VERIFY_FAIL, main
from outcome_receipts.workflows import (
    MIGRATION_STATUSES,
    WORKFLOW_SCHEMA_VERSION,
    WorkflowError,
    build_contract_evidence,
    build_equity_review,
    build_migration_check,
    build_requirement_change,
    build_restatement,
    build_rollup,
    verify_workflow_artifact,
)

ROOT = Path(__file__).resolve().parents[1]


def _report(tmp_path: Path, name: str, count: int, *, definition: str = "People served.") -> Path:
    directory = tmp_path / name
    directory.mkdir()
    data = directory / "data.csv"
    rows = ["client_id"] + [f"p{index}" for index in range(count)]
    data.write_text("\n".join(rows) + "\n", encoding="utf-8")
    config = directory / "report.toml"
    spec_text = """
schema_version = "1.0"
[data]
path = "data.csv"
[report]
title = "Program report"
template = "People served: {{served}}."
[metrics.served]
description = "People served"
definition = "__DEFINITION__"
kind = "output"
unit = "count"
value_sql = "SELECT COUNT(*) FROM data"
slice_sql = "SELECT client_id FROM data"
""".lstrip()
    config.write_text(spec_text.replace("__DEFINITION__", definition), encoding="utf-8")
    return config


def _bundle(config: Path, out: Path) -> None:
    code = main(
        [
            "run",
            "--config",
            str(config),
            "--out",
            str(out),
            "--approved-by",
            "Test reviewer",
            "--reproducible",
        ]
    )
    assert code == EXIT_OK


def _write_json(path: Path, value: object) -> Path:
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def test_restatement_verifies_prior_bundle_and_composes_delta(tmp_path: Path) -> None:
    prior_config = _report(tmp_path, "prior", 12)
    current_config = _report(tmp_path, "current", 14)
    bundle = tmp_path / "prior-bundle"
    _bundle(prior_config, bundle)

    artifact = build_restatement(
        prior_config=prior_config,
        prior_bundle=bundle,
        current_config=current_config,
        reason="Late records were accepted.",
        approved_by="Grant manager",
        reproducible=True,
    )

    assert artifact["kind"] == "restatement"
    assert artifact["relationship"]["type"] == "supersedes"
    changed = artifact["changed"][0]
    assert changed["delta_receipt"]["provenance_type"] == "receipt_composed"
    assert changed["delta_receipt"]["display"] == "2"
    assert verify_workflow_artifact(artifact).ok


def test_restatement_over_a_suppressed_metric_states_no_delta(tmp_path: Path) -> None:
    """A metric withheld on one side is restated without a composed delta.

    ``build_restatement`` already guarded this case; what was missing was any
    test whose input report contained a small cell, so the guard was never
    exercised. The delta must be *absent*, not zero and not derived: a
    difference between a published count and a withheld one is arithmetic on a
    cell the prior report declined to state.
    """

    prior_config = _report_with_small_cell(tmp_path, "prior", 14, 4)
    current_config = _report_with_small_cell(tmp_path, "current", 20, 12)
    bundle = tmp_path / "prior-bundle"
    _bundle(prior_config, bundle)

    artifact = build_restatement(
        prior_config=prior_config,
        prior_bundle=bundle,
        current_config=current_config,
        reason="Cohort A grew past the small-cell threshold.",
        approved_by="Grant manager",
        reproducible=True,
    )

    by_id = {record["metric_id"]: record for record in artifact["changed"]}
    assert by_id["served"]["delta_receipt"]["display"] == "6"
    withheld = by_id["small_group"]
    assert withheld["delta_status"] == "suppressed"
    assert "delta_receipt" not in withheld
    assert withheld["prior"]["suppressed"] is True
    assert withheld["prior"]["value"] is None
    assert verify_workflow_artifact(artifact).ok


def test_restatement_rejects_tampered_prior_bundle(tmp_path: Path) -> None:
    config = _report(tmp_path, "prior", 12)
    bundle = tmp_path / "prior-bundle"
    _bundle(config, bundle)
    (bundle / "report.md").write_text("tampered", encoding="utf-8")

    with pytest.raises(WorkflowError, match="verification failed"):
        build_restatement(
            prior_config=config,
            prior_bundle=bundle,
            current_config=config,
            reason="Correction",
            approved_by="Reviewer",
            reproducible=True,
        )


def test_migration_classifies_equal_and_changed_metrics(tmp_path: Path) -> None:
    before = _report(tmp_path, "before", 12)
    equal = _report(tmp_path, "equal", 12)
    changed = _report(tmp_path, "changed", 13)

    equal_artifact = build_migration_check(
        before_config=before,
        after_config=equal,
        approved_by="Data lead",
        reproducible=True,
    )
    changed_artifact = build_migration_check(
        before_config=before,
        after_config=changed,
        approved_by="Data lead",
        reproducible=True,
    )

    assert equal_artifact["metrics"][0]["status"] == "equivalent"
    assert changed_artifact["metrics"][0]["status"] == "changed"
    assert changed_artifact["metrics"][0]["delta_receipt"]["display"] == "1"
    assert verify_workflow_artifact(equal_artifact).ok
    assert verify_workflow_artifact(changed_artifact).ok


def _report_with_small_cell(tmp_path: Path, name: str, total: int, small: int) -> Path:
    """A spec whose second metric is a small cell, so suppression fires on it.

    Every workflow builder that takes a report has to be exercised against one
    of these: until issue #79 not one of them was, even though any real
    human-services export has at least one small cell, and `migrate-check`
    aborted on every spec that did.
    """

    directory = tmp_path / name
    directory.mkdir()
    rows = ["client_id,cohort"]
    rows.extend(f"p{index},{'a' if index < small else 'b'}" for index in range(total))
    (directory / "data.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")
    config = directory / "report.toml"
    config.write_text(
        """
schema_version = "1.0"
[data]
path = "data.csv"
[report]
title = "Program report"
template = "People served: {served}. Cohort A: {small_group}."
[metrics.served]
description = "People served"
definition = "People represented by one row."
kind = "output"
unit = "count"
value_sql = "SELECT COUNT(*) FROM data"
slice_sql = "SELECT client_id FROM data"
[metrics.small_group]
description = "Cohort A"
definition = "People represented by one row whose cohort is A."
kind = "output"
unit = "count"
value_sql = "SELECT COUNT(*) FROM data WHERE cohort = 'a'"
slice_sql = "SELECT client_id FROM data WHERE cohort = 'a'"
""".lstrip(),
        encoding="utf-8",
    )
    return config


def test_migration_classifies_a_suppressed_metric_instead_of_aborting(tmp_path: Path) -> None:
    """Merge-blocking (issue #79): one small cell must not silence the whole report.

    ``_composed_receipt`` refuses a suppressed input, and ``build_migration_check``
    composed a delta for every metric unconditionally, so a single small cell
    anywhere in a spec aborted the artifact and reported nothing about the
    metrics that could have been compared. All four shipped example specs failed
    against themselves.
    """

    before = _report_with_small_cell(tmp_path, "before", 14, 4)
    after = _report_with_small_cell(tmp_path, "after", 14, 4)

    artifact = build_migration_check(
        before_config=before,
        after_config=after,
        approved_by="Data lead",
        reproducible=True,
    )

    by_id = {record["metric_id"]: record for record in artifact["metrics"]}
    assert by_id["served"]["status"] == "equivalent"
    assert by_id["served"]["delta_receipt"]["display"] == "0"

    withheld = by_id["small_group"]
    assert withheld["status"] == "indeterminate"
    assert withheld["delta_status"] == "suppressed"
    # The unsafe outcomes, asserted as absences. Not "equivalent": two withheld
    # cells compare equal on their nulls, and asserting equivalence nobody can
    # see is worse than saying nothing. And no composed delta, which would be a
    # number derived from a cell neither side publishes.
    assert withheld["status"] != "equivalent"
    assert "delta_receipt" not in withheld
    assert verify_workflow_artifact(artifact).ok


def test_migration_verifier_refuses_an_indeterminate_metric_with_a_delta(
    tmp_path: Path,
) -> None:
    """The classification has to hold at the artifact boundary, not just at build.

    An artifact reaches a consumer as a file. A record claiming no comparison was
    possible while carrying a composed delta is the shape that would put a number
    derived from a withheld cell in front of a reader.
    """

    config = _report_with_small_cell(tmp_path, "spec", 14, 4)
    artifact = build_migration_check(
        before_config=config,
        after_config=config,
        approved_by="Data lead",
        reproducible=True,
    )
    by_id = {record["metric_id"]: record for record in artifact["metrics"]}
    assert verify_workflow_artifact(artifact).ok

    by_id["small_group"]["delta_receipt"] = by_id["served"]["delta_receipt"]
    result = verify_workflow_artifact(artifact)
    assert not result.ok
    assert any(check.scope == "delta_receipt" and not check.ok for check in result.checks)

    del by_id["small_group"]["delta_receipt"]
    del by_id["served"]["delta_receipt"]
    comparable = verify_workflow_artifact(artifact)
    assert not comparable.ok, "a comparable metric with no delta receipt must not verify"


@pytest.mark.parametrize(
    "example", ["housing-demo", "grant-report", "board-report", "multi-funder"]
)
def test_migrate_check_runs_on_every_shipped_example(example: str, tmp_path: Path) -> None:
    """Each shipped spec compared against itself: the trivially-equivalent case.

    Four of four used to exit 1 with "a suppressed input cannot be composed",
    including board-report, where no headline metric is suppressed -- its
    comparison delta figures are, which was enough.
    """

    config = ROOT / "examples" / example / "report.toml"
    out = tmp_path / "migration.json"
    code = main(
        [
            "migrate-check",
            "--before-config",
            str(config),
            "--after-config",
            str(config),
            "--approved-by",
            "A. Reviewer",
            "--out",
            str(out),
            "--reproducible",
        ]
    )

    assert code == EXIT_OK, f"{example}: migrate-check still aborts"
    artifact = json.loads(out.read_text(encoding="utf-8"))
    assert verify_workflow_artifact(artifact).ok
    statuses = {record["status"] for record in artifact["metrics"]}
    # A spec compared against itself has no changed metric: every metric is
    # either equivalent or withheld on both sides.
    assert statuses <= {"equivalent", "indeterminate"}, statuses
    assert "indeterminate" in statuses, f"{example} no longer exercises a suppressed metric"
    for record in artifact["metrics"]:
        if record["status"] == "indeterminate":
            assert "delta_receipt" not in record


def test_migration_rejects_definition_drift(tmp_path: Path) -> None:
    before = _report(tmp_path, "before", 12)
    after = _report(tmp_path, "after", 12, definition="Enrollments served.")

    with pytest.raises(WorkflowError, match="definition differs"):
        build_migration_check(
            before_config=before,
            after_config=after,
            approved_by="Data lead",
            reproducible=True,
        )


def test_requirement_diff_uses_stable_ids_and_text_hashes(tmp_path: Path) -> None:
    prior = _write_json(
        tmp_path / "prior.json",
        {"requirements": [{"requirement_id": "served", "definition": "People served"}]},
    )
    current = _write_json(
        tmp_path / "current.json",
        {
            "requirements": [
                {"requirement_id": "served", "definition": "Unduplicated people served"},
                {"requirement_id": "exits", "definition": "Program exits"},
            ]
        },
    )

    artifact = build_requirement_change(prior, current)

    by_id = {item["requirement_id"]: item for item in artifact["requirements"]}
    assert by_id["served"]["status"] == "definition_changed"
    assert by_id["served"]["review_status"] == "required"
    assert by_id["exits"]["status"] == "added"
    assert verify_workflow_artifact(artifact).ok


def test_requirement_diff_rejects_missing_or_duplicate_stable_ids(tmp_path: Path) -> None:
    prior = _write_json(tmp_path / "prior.json", {"requirements": [{"definition": "Missing"}]})
    current = _write_json(tmp_path / "current.json", {"requirements": []})

    with pytest.raises(WorkflowError, match="stable ID"):
        build_requirement_change(prior, current)


def test_requirement_diff_has_no_figures_to_suppress(tmp_path: Path) -> None:
    """The one builder for which "a report with a suppressed figure" is vacuous.

    Issue #79 asks for a suppressed-figure test on each of the six workflow
    builders. Five take a report spec. This one takes two requirement documents
    and never computes a figure, so it has no receipt to withhold; this test
    records that as a fact about the artifact rather than leaving the gap
    looking like an oversight.
    """

    prior = _write_json(
        tmp_path / "prior.json",
        {"requirements": [{"requirement_id": "served", "definition": "People served"}]},
    )
    current = _write_json(
        tmp_path / "current.json",
        {"requirements": [{"requirement_id": "served", "definition": "Unduplicated people"}]},
    )

    artifact = build_requirement_change(prior, current)

    assert not [
        record for record in artifact["requirements"] if {"value", "display"} & record.keys()
    ]
    assert verify_workflow_artifact(artifact).ok


def _contract_report(tmp_path: Path, *, observed: int = 12) -> Path:
    data = tmp_path / "contract.csv"
    rows = ["client_id,threshold,amount"] + [f"p{i},11,5000" for i in range(observed)]
    data.write_text("\n".join(rows) + "\n", encoding="utf-8")
    config = tmp_path / "contract.toml"
    config.write_text(
        """
schema_version = "1.0"
[data]
path = "contract.csv"
[report]
title = "Contract report"
template = "Observed {observed}; threshold {threshold}; finance {financial}."
[metrics.observed]
description = "Observed milestone"
definition = "People served."
kind = "outcome"
unit = "count"
value_sql = "SELECT COUNT(*) FROM data"
slice_sql = "SELECT client_id FROM data"
[metrics.threshold]
description = "Contract threshold"
definition = "Threshold transcribed from the controlling contract field."
kind = "output"
unit = "count"
value_sql = "SELECT MAX(CAST(threshold AS INTEGER)) FROM data"
slice_sql = "SELECT threshold FROM data"
[metrics.financial]
description = "Associated financial line"
definition = "Payment amount from the controlling contract field."
kind = "output"
unit = "money"
decimals = 0
value_sql = "SELECT MAX(CAST(amount AS INTEGER)) FROM data"
slice_sql = "SELECT amount FROM data"
""".lstrip(),
        encoding="utf-8",
    )
    return config


def _contract(path: Path, *, comparison: str = "gte") -> Path:
    return _write_json(
        path,
        {
            "contract_id": "housing-services",
            "controlling_text": "Milestone copied by the operator from section A.",
            "policy_citation": "Operator copy of contract section A.",
            "milestones": [
                {
                    "milestone_id": "m1",
                    "observed_metric_id": "observed",
                    "threshold_metric_id": "threshold",
                    "financial_metric_id": "financial",
                    "comparison": comparison,
                }
            ],
        },
    )


def test_contract_evidence_links_observed_threshold_and_finance_receipts(
    tmp_path: Path,
) -> None:
    artifact = build_contract_evidence(
        config_path=_contract_report(tmp_path),
        contract_path=_contract(tmp_path / "contract.json"),
        approved_by="Contracts reviewer",
        reproducible=True,
    )

    milestone = artifact["milestones"][0]
    assert milestone["status"] == "met"
    assert milestone["observed"]["metric_id"] == "observed"
    assert milestone["threshold"]["metric_id"] == "threshold"
    assert milestone["financial"]["metric_id"] == "financial"
    assert artifact["legal_determination"] == "not_made"
    assert verify_workflow_artifact(artifact).ok


def test_contract_evidence_over_a_suppressed_observation_is_indeterminate(
    tmp_path: Path,
) -> None:
    """A milestone over a withheld cell is not met and not unmet.

    Four people served against a threshold of eleven: the count is a small cell,
    so the report does not publish it and no comparison can be asserted. The
    milestone must say that rather than resolve to ``unmet``, which would be a
    statement about a number the report withheld.
    """

    artifact = build_contract_evidence(
        config_path=_contract_report(tmp_path, observed=4),
        contract_path=_contract(tmp_path / "contract.json"),
        approved_by="Contracts reviewer",
        reproducible=True,
    )

    milestone = artifact["milestones"][0]
    assert milestone["status"] == "indeterminate"
    assert milestone["status"] not in {"met", "unmet"}
    assert milestone["observed"]["suppressed"] is True
    assert milestone["observed"]["value"] is None
    assert verify_workflow_artifact(artifact).ok


def test_contract_evidence_rejects_unknown_operator(tmp_path: Path) -> None:
    with pytest.raises(WorkflowError, match="unsupported comparison"):
        build_contract_evidence(
            config_path=_contract_report(tmp_path),
            contract_path=_contract(tmp_path / "contract.json", comparison="approximately"),
            approved_by="Contracts reviewer",
            reproducible=True,
        )


def _rollup_plan(path: Path, entries: list[dict[str, str]], *, overlap: str = "disjoint") -> Path:
    normalized = [
        {
            **entry,
            "period": "2026-Q2",
            "suppression_policy_id": "cms-small-cell-v1",
        }
        for entry in entries
    ]
    return _write_json(
        path,
        {
            "population_overlap": overlap,
            "period": "2026-Q2",
            "suppression_policy_id": "cms-small-cell-v1",
            "inputs": normalized,
        },
    )


def test_rollup_verifies_bundles_and_is_order_independent(tmp_path: Path) -> None:
    first_config = _report(tmp_path, "partner-a", 12)
    second_config = _report(tmp_path, "partner-b", 13)
    first_bundle = tmp_path / "bundle-a"
    second_bundle = tmp_path / "bundle-b"
    _bundle(first_config, first_bundle)
    _bundle(second_config, second_bundle)
    entries = [
        {
            "partner": "A",
            "config": str(first_config),
            "bundle": str(first_bundle),
            "metric_id": "served",
        },
        {
            "partner": "B",
            "config": str(second_config),
            "bundle": str(second_bundle),
            "metric_id": "served",
        },
    ]
    forward = _rollup_plan(tmp_path / "forward.json", entries)
    reverse = _rollup_plan(tmp_path / "reverse.json", list(reversed(entries)))

    one = build_rollup(plan_path=forward, approved_by="Lead agency", reproducible=True)
    two = build_rollup(plan_path=reverse, approved_by="Lead agency", reproducible=True)

    assert one["rollup_receipt"]["display"] == "25"
    assert one["rollup_receipt"] == two["rollup_receipt"]
    assert one["inputs"] == two["inputs"]
    assert verify_workflow_artifact(one).ok


def test_rollup_rejects_suppressed_partner_cell(tmp_path: Path) -> None:
    small = _report(tmp_path, "small", 5)
    safe = _report(tmp_path, "safe", 12)
    small_bundle = tmp_path / "small-bundle"
    safe_bundle = tmp_path / "safe-bundle"
    _bundle(small, small_bundle)
    _bundle(safe, safe_bundle)
    plan = _rollup_plan(
        tmp_path / "rollup.json",
        [
            {
                "partner": "Small",
                "config": str(small),
                "bundle": str(small_bundle),
                "metric_id": "served",
            },
            {
                "partner": "Safe",
                "config": str(safe),
                "bundle": str(safe_bundle),
                "metric_id": "served",
            },
        ],
    )

    with pytest.raises(WorkflowError, match="suppressed metrics cannot be rolled up"):
        build_rollup(plan_path=plan, approved_by="Lead agency", reproducible=True)


def _equity_report(tmp_path: Path) -> Path:
    data = tmp_path / "equity.csv"
    rows = ["client_id,group"]
    rows.extend(f"a{i},A" for i in range(5))
    rows.extend(f"b{i},B" for i in range(15))
    data.write_text("\n".join(rows) + "\n", encoding="utf-8")
    config = tmp_path / "equity.toml"
    config.write_text(
        """
schema_version = "1.0"
[data]
path = "equity.csv"
[report]
title = "Equity review"
template = "Group A {group_a}; group B {group_b}; total {total}."
[metrics.group_a]
description = "Approved group A"
definition = "People in operator-reviewed group A."
kind = "outcome"
unit = "count"
value_sql = "SELECT COUNT(*) FROM data WHERE `group` = 'A'"
slice_sql = "SELECT client_id FROM data WHERE `group` = 'A'"
[metrics.group_b]
description = "Approved group B"
definition = "People in operator-reviewed group B."
kind = "outcome"
unit = "count"
value_sql = "SELECT COUNT(*) FROM data WHERE `group` = 'B'"
slice_sql = "SELECT client_id FROM data WHERE `group` = 'B'"
[metrics.total]
description = "All approved groups"
definition = "People in the complete reviewed grouping."
kind = "outcome"
unit = "count"
value_sql = "SELECT COUNT(*) FROM data"
slice_sql = "SELECT client_id FROM data"
""".lstrip(),
        encoding="utf-8",
    )
    return config


def _equity_plan(path: Path, *, consent: str = "Documented program consent") -> Path:
    return _write_json(
        path,
        {
            "dimension": "operator-approved demographic grouping",
            "purpose": "Review access differences without causal inference.",
            "controlling_policy": "CMS small-cell policy applied to the whole report.",
            "consent_basis": consent,
            "category_provenance": "Categories reviewed by the program and privacy lead.",
            "groups": [
                {"label": "Group A", "metric_id": "group_a"},
                {"label": "Group B", "metric_id": "group_b"},
            ],
        },
    )


def test_equity_review_carries_suppressed_receipts_and_interpretation_limits(
    tmp_path: Path,
) -> None:
    artifact = build_equity_review(
        config_path=_equity_report(tmp_path),
        plan_path=_equity_plan(tmp_path / "equity.json"),
        approved_by="Privacy reviewer",
        reproducible=True,
    )

    by_label = {item["label"]: item["receipt"] for item in artifact["groups"]}
    assert by_label["Group A"]["display"] == "[SUPPRESSED]"
    # A withheld group must not read as a group of nobody. This artifact exists
    # to let a reviewer look at small groups, so it is the one most likely to be
    # plotted or summed straight out of the JSON.
    assert by_label["Group A"]["suppressed"] is True
    assert by_label["Group A"]["value"] is None
    assert by_label["Group A"]["row_count"] is None
    assert artifact["interpretation_limits"]
    # And the artifact has to say so in words, not only in a field.
    assert any("suppression" in limit.lower() for limit in artifact["interpretation_limits"]), (
        artifact["interpretation_limits"]
    )
    assert verify_workflow_artifact(artifact).ok


def test_equity_review_without_the_suppression_limit_fails_verification(
    tmp_path: Path,
) -> None:
    """A withheld group with no stated limit must not verify.

    The check has to be on the artifact, not on the builder: an artifact reaches
    a consumer as a file, and a file can be edited. Dropping the limit while
    keeping the withheld group is exactly the edit that makes the group look
    empty, so `verify-workflow` must refuse it.
    """

    artifact = build_equity_review(
        config_path=_equity_report(tmp_path),
        plan_path=_equity_plan(tmp_path / "equity.json"),
        approved_by="Privacy reviewer",
        reproducible=True,
    )
    assert verify_workflow_artifact(artifact).ok

    artifact["interpretation_limits"] = ["No group ranking is produced."]
    result = verify_workflow_artifact(artifact)

    assert not result.ok
    assert any(
        check.scope == "interpretation_limits" and not check.ok for check in result.checks
    ), [check for check in result.checks if not check.ok]


def test_a_withheld_receipt_that_still_carries_a_number_fails_verification(
    tmp_path: Path,
) -> None:
    """The unsafe outcome, asserted as an absence, at the artifact boundary.

    ``suppressed: true`` beside ``value: 4`` is worse than either state alone:
    it publishes the protected cell and labels it as protected in the same
    object. Nothing this package builds can reach that shape; a hand-edited
    artifact, or one from a build that zeroed the fields instead of withholding
    them, can.
    """

    artifact = build_equity_review(
        config_path=_equity_report(tmp_path),
        plan_path=_equity_plan(tmp_path / "equity.json"),
        approved_by="Privacy reviewer",
        reproducible=True,
    )
    withheld = next(item["receipt"] for item in artifact["groups"] if item["receipt"]["suppressed"])

    for field, leaked in (("value", 4.0), ("row_count", 4), ("slice_hash", "ab" * 32)):
        restore = withheld[field]
        withheld[field] = leaked
        result = verify_workflow_artifact(artifact)
        assert not result.ok, field
        assert any(check.scope == "suppression" and not check.ok for check in result.checks), field
        withheld[field] = restore

    assert verify_workflow_artifact(artifact).ok


def test_equity_review_requires_consent_basis(tmp_path: Path) -> None:
    with pytest.raises(WorkflowError, match="consent_basis is required"):
        build_equity_review(
            config_path=_equity_report(tmp_path),
            plan_path=_equity_plan(tmp_path / "equity.json", consent=""),
            approved_by="Privacy reviewer",
            reproducible=True,
        )


def test_workflow_cli_writes_only_after_success(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    prior = _write_json(
        tmp_path / "prior.json",
        {"requirements": [{"requirement_id": "served", "definition": "People"}]},
    )
    current = _write_json(
        tmp_path / "current.json",
        {"requirements": [{"requirement_id": "served", "definition": "People served"}]},
    )
    out = tmp_path / "impact.json"

    code = main(
        [
            "requirements-diff",
            "--prior",
            str(prior),
            "--current",
            str(current),
            "--out",
            str(out),
            "--json",
        ]
    )

    assert code == EXIT_OK
    assert json.loads(capsys.readouterr().out)["artifact"]["kind"] == "requirement_change"
    assert out.is_file()

    blocked_out = tmp_path / "blocked.json"
    code = main(
        [
            "requirements-diff",
            "--prior",
            str(tmp_path / "missing.json"),
            "--current",
            str(current),
            "--out",
            str(blocked_out),
        ]
    )
    assert code == EXIT_VERIFY_FAIL
    assert not blocked_out.exists()


def test_published_workflow_schema_pins_all_artifact_kinds() -> None:
    schema = json.loads(
        (ROOT / "docs/schema/workflow-artifact.schema.json").read_text(encoding="utf-8")
    )

    assert schema["properties"]["schema_version"]["const"] == WORKFLOW_SCHEMA_VERSION
    assert set(schema["properties"]["kind"]["enum"]) == {
        "restatement",
        "migration_equivalence",
        "requirement_change",
        "contract_evidence",
        "federated_rollup",
        "equity_review",
    }
    assert len(schema["oneOf"]) == 6
    assert schema["properties"]["rollup_receipt"]["$ref"] == "#/$defs/composedReceipt"


def test_the_schema_and_the_docs_agree_on_the_migration_status_vocabulary() -> None:
    """Issue #79: the code raised where the docs said it classified.

    ``docs/NOVEL-USE-CASES.md`` UC-2 described a third status the schema did not
    enumerate and the code did not produce. All three now name the same set, and
    this test is what keeps them naming it.
    """

    schema = json.loads(
        (ROOT / "docs/schema/workflow-artifact.schema.json").read_text(encoding="utf-8")
    )
    published = set(schema["properties"]["metrics"]["items"]["properties"]["status"]["enum"])
    use_cases = (ROOT / "docs/NOVEL-USE-CASES.md").read_text(encoding="utf-8")

    assert published == set(MIGRATION_STATUSES)
    for status in published:
        assert f"`{status}`" in use_cases, f"UC-2 does not name {status}"
    # The word the docs used to promise and nothing produced.
    assert "blocked" not in published


def test_committed_v1_compatibility_fixtures_cover_and_verify_every_kind() -> None:
    payload = json.loads(
        (ROOT / "tests/fixtures/compat/v1/workflow-artifacts.json").read_text(encoding="utf-8")
    )
    artifacts = payload["artifacts"]

    assert payload["artifact_schema_version"] == WORKFLOW_SCHEMA_VERSION
    assert {artifact["kind"] for artifact in artifacts} == {
        "restatement",
        "migration_equivalence",
        "requirement_change",
        "contract_evidence",
        "federated_rollup",
        "equity_review",
    }
    assert all(verify_workflow_artifact(artifact).ok for artifact in artifacts)

    # The frozen set covers the classifications a suppressed figure produces, not
    # only the happy path: a migration artifact with an indeterminate metric, and
    # an equity review with a withheld group.
    migrations = [a for a in artifacts if a["kind"] == "migration_equivalence"]
    statuses = {record["status"] for artifact in migrations for record in artifact["metrics"]}
    assert "indeterminate" in statuses
    withheld = [
        group
        for artifact in artifacts
        if artifact["kind"] == "equity_review"
        for group in artifact["groups"]
        if group["receipt"]["suppressed"]
    ]
    assert withheld


def test_workflow_verifier_rejects_future_versions_bad_digests_and_client_rows() -> None:
    artifact = {
        "schema_version": "2.0",
        "kind": "requirement_change",
        "relationship": {"type": "compares_to"},
        "prior_document_digest": "not-a-digest",
        "current_document_digest": "0" * 64,
        "requirements": [],
        "source_rows": [{"person": "not allowed"}],
    }

    result = verify_workflow_artifact(artifact)

    assert not result.ok
    failed = {check.scope for check in result.checks if not check.ok}
    assert "schema_version" in failed
    assert "$.prior_document_digest" in failed
    assert "aggregate_only" in failed


def test_workflow_verifier_rejects_forged_composed_query_and_invalid_statuses() -> None:
    payload = json.loads(
        (ROOT / "tests/fixtures/compat/v1/workflow-artifacts.json").read_text(encoding="utf-8")
    )
    by_kind = {artifact["kind"]: artifact for artifact in payload["artifacts"]}

    restatement = by_kind["restatement"]
    restatement["changed"][0]["delta_receipt"]["query"] = "SELECT 0"
    result = verify_workflow_artifact(restatement)
    assert not result.ok
    assert any(not check.ok and check.scope.endswith(".delta_receipt") for check in result.checks)

    migration = by_kind["migration_equivalence"]
    migration["metrics"][0]["status"] = "approved"
    assert not verify_workflow_artifact(migration).ok

    contract = by_kind["contract_evidence"]
    contract["legal_determination"] = "payment_due"
    assert not verify_workflow_artifact(contract).ok

    rollup = by_kind["federated_rollup"]
    rollup["inputs"] = rollup["inputs"][:1]
    assert not verify_workflow_artifact(rollup).ok

    equity = by_kind["equity_review"]
    equity["groups"] = equity["groups"][:1]
    assert not verify_workflow_artifact(equity).ok


def test_verify_workflow_cli_accepts_current_artifact_and_rejects_invalid_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    artifact = _write_json(
        tmp_path / "artifact.json",
        {
            "schema_version": "1.0",
            "kind": "requirement_change",
            "relationship": {"type": "compares_to"},
            "prior_document_digest": "a" * 64,
            "current_document_digest": "b" * 64,
            "requirements": [],
        },
    )

    code = main(["verify-workflow", "--artifact", str(artifact), "--json"])
    assert code == EXIT_OK
    assert json.loads(capsys.readouterr().out)["ok"] is True

    invalid = tmp_path / "invalid.json"
    invalid.write_text("{", encoding="utf-8")
    assert main(["verify-workflow", "--artifact", str(invalid)]) == EXIT_VERIFY_FAIL
