"""Generate stable version-1.0 fixtures for every evidence workflow artifact."""

from __future__ import annotations

import argparse
import io
import json
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

from outcome_receipts.cli import EXIT_OK, main
from outcome_receipts.workflows import (
    build_contract_evidence,
    build_equity_review,
    build_migration_check,
    build_requirement_change,
    build_restatement,
    build_rollup,
)

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "tests" / "fixtures" / "compat" / "v1" / "workflow-artifacts.json"

_BASIC_SPEC = """
schema_version = "1.0"
[data]
path = "data.csv"
[report]
title = "Compatibility fixture"
template = "People served: {served}."
[metrics.served]
description = "People served"
definition = "People represented by one row in the synthetic compatibility fixture."
kind = "output"
unit = "count"
value_sql = "SELECT COUNT(*) FROM data"
slice_sql = "SELECT synthetic_key FROM data"
""".lstrip()

_CONTRACT_SPEC = """
schema_version = "1.0"
[data]
path = "data.csv"
[report]
title = "Contract compatibility fixture"
template = "Observed {observed}; threshold {threshold}; finance {financial}."
[metrics.observed]
description = "Observed milestone"
definition = "Synthetic people represented by one row."
kind = "outcome"
unit = "count"
value_sql = "SELECT COUNT(*) FROM data"
slice_sql = "SELECT synthetic_key FROM data"
[metrics.threshold]
description = "Contract threshold"
definition = "Threshold copied into the synthetic controlling field."
kind = "output"
unit = "count"
value_sql = "SELECT MAX(CAST(threshold AS INTEGER)) FROM data"
slice_sql = "SELECT threshold FROM data"
[metrics.financial]
description = "Associated financial line"
definition = "Amount copied into the synthetic controlling field."
kind = "output"
unit = "money"
decimals = 0
value_sql = "SELECT MAX(CAST(amount AS INTEGER)) FROM data"
slice_sql = "SELECT amount FROM data"
""".lstrip()

# A spec whose second metric is a small cell, so migration equivalence has to
# classify it rather than compose a delta over it. Frozen as its own fixture so
# the `indeterminate` status is covered by the compatibility contract and not
# only by the unit tests.
_SMALL_CELL_SPEC = """
schema_version = "1.0"
[data]
path = "data.csv"
[report]
title = "Small-cell compatibility fixture"
template = "Total {served}; cohort A {small_group}."
[metrics.served]
description = "People served"
definition = "Synthetic people represented by one row."
kind = "output"
unit = "count"
value_sql = "SELECT COUNT(*) FROM data"
slice_sql = "SELECT synthetic_key FROM data"
[metrics.small_group]
description = "Cohort A"
definition = "Synthetic people represented by one row whose cohort is A."
kind = "output"
unit = "count"
value_sql = "SELECT COUNT(*) FROM data WHERE cohort = 'a'"
slice_sql = "SELECT synthetic_key FROM data WHERE cohort = 'a'"
""".lstrip()

_EQUITY_SPEC = """
schema_version = "1.0"
[data]
path = "data.csv"
[report]
title = "Equity compatibility fixture"
template = "Group A {group_a}; group B {group_b}; total {total}."
[metrics.group_a]
description = "Reviewed group A"
definition = "Synthetic records in operator-reviewed group A."
kind = "outcome"
unit = "count"
value_sql = "SELECT COUNT(*) FROM data WHERE category = 'A'"
slice_sql = "SELECT synthetic_key FROM data WHERE category = 'A'"
[metrics.group_b]
description = "Reviewed group B"
definition = "Synthetic records in operator-reviewed group B."
kind = "outcome"
unit = "count"
value_sql = "SELECT COUNT(*) FROM data WHERE category = 'B'"
slice_sql = "SELECT synthetic_key FROM data WHERE category = 'B'"
[metrics.total]
description = "All reviewed groups"
definition = "All synthetic records in the reviewed grouping."
kind = "outcome"
unit = "count"
value_sql = "SELECT COUNT(*) FROM data"
slice_sql = "SELECT synthetic_key FROM data"
""".lstrip()


def _write_basic(directory: Path, count: int) -> Path:
    directory.mkdir()
    rows = ["synthetic_key", *(f"fixture-{index}" for index in range(count))]
    (directory / "data.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")
    config = directory / "report.toml"
    config.write_text(_BASIC_SPEC, encoding="utf-8")
    return config


def _write_small_cell(directory: Path, total: int, small: int) -> Path:
    directory.mkdir()
    rows = ["synthetic_key,cohort"]
    rows.extend(f"fixture-{index},{'a' if index < small else 'b'}" for index in range(total))
    (directory / "data.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")
    config = directory / "report.toml"
    config.write_text(_SMALL_CELL_SPEC, encoding="utf-8")
    return config


def _export_bundle(config: Path, bundle: Path, ledger: Path) -> None:
    with redirect_stdout(io.StringIO()):
        result = main(
            [
                "run",
                "--config",
                str(config),
                "--out",
                str(bundle),
                "--ledger",
                str(ledger),
                "--approved-by",
                "Compatibility fixture generator",
                "--reproducible",
            ]
        )
    if result != EXIT_OK:
        raise RuntimeError(f"fixture bundle export failed with exit code {result}")


def _write_json(path: Path, value: object) -> Path:
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _contract_files(directory: Path) -> tuple[Path, Path]:
    directory.mkdir()
    rows = ["synthetic_key,threshold,amount"]
    rows.extend(f"fixture-{index},11,5000" for index in range(12))
    (directory / "data.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")
    config = directory / "report.toml"
    config.write_text(_CONTRACT_SPEC, encoding="utf-8")
    contract = _write_json(
        directory / "contract.json",
        {
            "contract_id": "synthetic-contract",
            "controlling_text": "Synthetic compatibility fixture section A.",
            "policy_citation": "Synthetic compatibility fixture section A.",
            "milestones": [
                {
                    "milestone_id": "synthetic-milestone",
                    "observed_metric_id": "observed",
                    "threshold_metric_id": "threshold",
                    "financial_metric_id": "financial",
                    "comparison": "gte",
                }
            ],
        },
    )
    return config, contract


def _equity_files(directory: Path) -> tuple[Path, Path]:
    directory.mkdir()
    rows = ["synthetic_key,category"]
    rows.extend(f"a-{index},A" for index in range(5))
    rows.extend(f"b-{index},B" for index in range(15))
    (directory / "data.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")
    config = directory / "report.toml"
    config.write_text(_EQUITY_SPEC, encoding="utf-8")
    plan = _write_json(
        directory / "plan.json",
        {
            "dimension": "synthetic operator-approved grouping",
            "purpose": "Compatibility testing without interpretation.",
            "controlling_policy": "CMS-modeled small-cell test policy.",
            "consent_basis": "Synthetic data; no people represented.",
            "category_provenance": "Generated compatibility fixture.",
            "groups": [
                {"label": "Group A", "metric_id": "group_a"},
                {"label": "Group B", "metric_id": "group_b"},
            ],
        },
    )
    return config, plan


def _artifacts(workspace: Path) -> list[dict[str, object]]:
    prior = _write_basic(workspace / "prior", 12)
    current = _write_basic(workspace / "current", 14)
    prior_bundle = workspace / "prior-bundle"
    _export_bundle(prior, prior_bundle, workspace / "prior-ledger.jsonl")

    requirements_before = _write_json(
        workspace / "requirements-before.json",
        {"requirements": [{"requirement_id": "served", "definition": "People served."}]},
    )
    requirements_after = _write_json(
        workspace / "requirements-after.json",
        {
            "requirements": [
                {"requirement_id": "served", "definition": "Unduplicated people served."},
                {"requirement_id": "exits", "definition": "Program exits."},
            ]
        },
    )

    contract_config, contract = _contract_files(workspace / "contract")

    partner_a = _write_basic(workspace / "partner-a", 12)
    partner_b = _write_basic(workspace / "partner-b", 13)
    bundle_a = workspace / "bundle-a"
    bundle_b = workspace / "bundle-b"
    _export_bundle(partner_a, bundle_a, workspace / "partner-a-ledger.jsonl")
    _export_bundle(partner_b, bundle_b, workspace / "partner-b-ledger.jsonl")
    rollup = _write_json(
        workspace / "rollup.json",
        {
            "period": "2026-Q2",
            "population_overlap": "not_deduplicated",
            "suppression_policy_id": "cms-small-cell-v1",
            "inputs": [
                {
                    "partner": "Partner A",
                    "config": "partner-a/report.toml",
                    "bundle": "bundle-a",
                    "metric_id": "served",
                    "period": "2026-Q2",
                    "suppression_policy_id": "cms-small-cell-v1",
                },
                {
                    "partner": "Partner B",
                    "config": "partner-b/report.toml",
                    "bundle": "bundle-b",
                    "metric_id": "served",
                    "period": "2026-Q2",
                    "suppression_policy_id": "cms-small-cell-v1",
                },
            ],
        },
    )

    equity_config, equity_plan = _equity_files(workspace / "equity")
    small_cell = _write_small_cell(workspace / "small-cell", 14, 4)
    reproducible = True
    return [
        build_restatement(
            prior_config=prior,
            prior_bundle=prior_bundle,
            current_config=current,
            reason="Synthetic late records were accepted.",
            approved_by="Compatibility fixture reviewer",
            reproducible=reproducible,
        ),
        build_migration_check(
            before_config=prior,
            after_config=current,
            approved_by="Compatibility fixture reviewer",
            reproducible=reproducible,
        ),
        build_migration_check(
            before_config=small_cell,
            after_config=small_cell,
            approved_by="Compatibility fixture reviewer",
            reproducible=reproducible,
        ),
        build_requirement_change(requirements_before, requirements_after),
        build_contract_evidence(
            config_path=contract_config,
            contract_path=contract,
            approved_by="Compatibility fixture reviewer",
            reproducible=reproducible,
        ),
        build_rollup(
            plan_path=rollup,
            approved_by="Compatibility fixture reviewer",
            reproducible=reproducible,
        ),
        build_equity_review(
            config_path=equity_config,
            plan_path=equity_plan,
            approved_by="Compatibility fixture reviewer",
            reproducible=reproducible,
        ),
    ]


def generate() -> str:
    """Generate the canonical compatibility-fixture document."""

    with tempfile.TemporaryDirectory(prefix="outcome-receipts-compat-") as temporary:
        artifacts = _artifacts(Path(temporary))
    payload = {
        "fixture_schema_version": "1.0",
        "artifact_schema_version": "1.0",
        "artifacts": artifacts,
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def main_cli() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    generated = generate()
    if args.check:
        current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.is_file() else ""
        if current != generated:
            print(f"workflow compatibility fixtures are stale: {OUTPUT}")
            return 1
        print("workflow compatibility fixtures: current")
        return 0
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(generated, encoding="utf-8")
    print(f"wrote workflow compatibility fixtures: {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main_cli())
