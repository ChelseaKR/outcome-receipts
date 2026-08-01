"""Passing and failing fixtures for the six bounded evidence workflows."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from outcome_receipts.cli import EXIT_OK, EXIT_VERIFY_FAIL, main
from outcome_receipts.workflows import (
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


def _contract_report(tmp_path: Path) -> Path:
    data = tmp_path / "contract.csv"
    rows = ["client_id,threshold,amount"] + [f"p{i},11,5000" for i in range(12)]
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
    assert by_label["Group A"]["value"] == 0.0
    assert artifact["interpretation_limits"]
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
