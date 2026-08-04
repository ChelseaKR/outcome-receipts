"""Adversarial fixtures for the federated subrecipient rollup (UC-5).

`docs/NOVEL-USE-CASES.md` sets the wave 3 exit gate for the rollup workflow:
adversarial recovery tests pass, incompatible inputs fail closed, and at least
two independent partner fixtures reproduce the same rollup. The named fixtures
are a forged bundle, incompatible definitions, recoverable partner cells,
overlapping populations, and reordered inputs. Each has a test below, plus the
acceptance property the same section states: no path leads from the rollup
artifact back to a partner's suppressed cell, and the output does not depend on
the order the partners appear in the plan.

Every partner here is synthetic. The client identifiers are generated labels, so
a collision between two partners' slice hashes in these fixtures means what it
would mean in production: the two partners submitted the same rows.
"""

from __future__ import annotations

import itertools
import json
import re
from pathlib import Path

import pytest

from outcome_receipts.cli import EXIT_OK, main
from outcome_receipts.models import EMPTY_SLICE_HASH
from outcome_receipts.workflows import (
    WorkflowError,
    build_rollup,
    verify_workflow_artifact,
)

PERIOD = "2026-Q2"
POLICY = "cms-small-cell-v1"

_SPEC = """
schema_version = "1.0"
[data]
path = "data.csv"
[report]
title = "__TITLE__"
template = "People served: {served}."
[metrics.served]
description = "People served"
definition = "__DEFINITION__"
kind = "output"
unit = "count"
value_sql = "SELECT COUNT(*) FROM data"
slice_sql = "SELECT client_id FROM data"
""".lstrip()


_HOLLOW_SLICE_SPEC = """
schema_version = "1.0"
[data]
path = "data.csv"
[report]
title = "__NAME__ report"
template = "People served: {served}."
[metrics.served]
description = "People served"
definition = "Unduplicated people served in the period."
kind = "output"
unit = "count"
value_sql = "SELECT COUNT(*) FROM data"
slice_sql = "SELECT client_id FROM data WHERE client_id = 'no-such-client'"
""".lstrip()


_ZERO_SPEC = """
schema_version = "1.0"
[data]
path = "data.csv"
[report]
title = "__NAME__ report"
template = "Exited to housing: {exited}."
[metrics.exited]
description = "People who exited to permanent housing"
definition = "People who exited to permanent housing in the period."
kind = "outcome"
unit = "count"
value_sql = "SELECT COUNT(*) FROM data WHERE exited = 'yes'"
slice_sql = "SELECT client_id FROM data WHERE exited = 'yes'"
""".lstrip()


def _partner(
    root: Path,
    name: str,
    client_ids: list[str],
    *,
    definition: str = "Unduplicated people served in the period.",
) -> Path:
    """Write one partner's spec and service export, and return the spec path."""

    directory = root / name
    directory.mkdir(parents=True)
    (directory / "data.csv").write_text(
        "\n".join(["client_id", *client_ids]) + "\n", encoding="utf-8"
    )
    config = directory / "report.toml"
    config.write_text(
        _SPEC.replace("__TITLE__", f"{name} report").replace("__DEFINITION__", definition),
        encoding="utf-8",
    )
    return config


def _bundle(config: Path, out: Path) -> None:
    assert (
        main(
            [
                "run",
                "--config",
                str(config),
                "--out",
                str(out),
                "--approved-by",
                "Partner approver",
                "--reproducible",
            ]
        )
        == EXIT_OK
    )


def _plan(
    root: Path,
    name: str,
    partners: list[str],
    *,
    overlap: str = "disjoint",
    metric_id: str = "served",
    sources: list[str] | None = None,
) -> Path:
    """Write a rollup plan whose paths are relative, so its bytes are portable.

    ``sources`` names the fixture directory each input reads, defaulting to the
    partner name. They differ only when a plan submits two bundles under one
    partner name, which is a legitimate shape: one organization, two programs.
    """

    directories = partners if sources is None else sources
    path = root / name
    path.write_text(
        json.dumps(
            {
                "period": PERIOD,
                "population_overlap": overlap,
                "suppression_policy_id": POLICY,
                "inputs": [
                    {
                        "partner": partner,
                        "config": f"{source}/report.toml",
                        "bundle": f"bundle-{source}",
                        "metric_id": metric_id,
                        "period": PERIOD,
                        "suppression_policy_id": POLICY,
                    }
                    for partner, source in zip(partners, directories, strict=True)
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def _ids(prefix: str, count: int) -> list[str]:
    return [f"{prefix}{index}" for index in range(count)]


def _two_partners(root: Path) -> None:
    """Two partners with distinct client sets, each with an exported bundle."""

    _bundle(_partner(root, "alpha", _ids("alpha-", 12)), root / "bundle-alpha")
    _bundle(_partner(root, "beta", _ids("beta-", 13)), root / "bundle-beta")


def test_rollup_composes_two_independent_partner_bundles(tmp_path: Path) -> None:
    _two_partners(tmp_path)

    artifact = build_rollup(
        plan_path=_plan(tmp_path, "plan.json", ["alpha", "beta"]),
        approved_by="Lead agency",
        reproducible=True,
    )

    assert artifact["rollup_receipt"]["display"] == "25"
    assert artifact["rollup_receipt"]["provenance_type"] == "receipt_composed"
    assert verify_workflow_artifact(artifact).ok


def test_rollup_is_reproducible_across_independently_built_fixtures(tmp_path: Path) -> None:
    """The same two partner fixtures, built twice, produce the same artifact."""

    first = tmp_path / "run-one"
    second = tmp_path / "run-two"
    for root in (first, second):
        root.mkdir()
        _two_partners(root)

    one = build_rollup(
        plan_path=_plan(first, "plan.json", ["alpha", "beta"]),
        approved_by="Lead agency",
        reproducible=True,
    )
    two = build_rollup(
        plan_path=_plan(second, "plan.json", ["alpha", "beta"]),
        approved_by="Lead agency",
        reproducible=True,
    )

    assert one == two


def test_rollup_output_does_not_depend_on_partner_order(tmp_path: Path) -> None:
    """Every ordering of three partners yields a byte-identical artifact."""

    _two_partners(tmp_path)
    _bundle(_partner(tmp_path, "gamma", _ids("gamma-", 14)), tmp_path / "bundle-gamma")

    artifacts = [
        build_rollup(
            plan_path=_plan(tmp_path, f"plan-{index}.json", list(order)),
            approved_by="Lead agency",
            reproducible=True,
        )
        for index, order in enumerate(itertools.permutations(["alpha", "beta", "gamma"]))
    ]

    # plan_digest hashes the plan file, which legitimately differs with the
    # written order. Everything the consumer reads as evidence must not.
    for artifact in artifacts:
        assert artifact["rollup_receipt"]["display"] == "39"
    without_plan = [
        {key: value for key, value in artifact.items() if key != "plan_digest"}
        for artifact in artifacts
    ]
    assert all(candidate == without_plan[0] for candidate in without_plan)


def test_rollup_rejects_a_forged_partner_bundle(tmp_path: Path) -> None:
    """An inflated partner receipt fails even when the bundle is re-sealed."""

    _two_partners(tmp_path)
    manifest_path = tmp_path / "bundle-alpha" / "receipts.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["receipts"][0]["value"] = 120.0
    manifest["receipts"][0]["display"] = "120"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(WorkflowError, match="verification failed"):
        build_rollup(
            plan_path=_plan(tmp_path, "plan.json", ["alpha", "beta"]),
            approved_by="Lead agency",
            reproducible=True,
        )


def test_rollup_rejects_a_partner_bundle_with_a_swapped_narrative(tmp_path: Path) -> None:
    _two_partners(tmp_path)
    (tmp_path / "bundle-beta" / "report.md").write_text(
        "# beta report\n\nPeople served: 900.\n", encoding="utf-8"
    )

    with pytest.raises(WorkflowError, match="verification failed"):
        build_rollup(
            plan_path=_plan(tmp_path, "plan.json", ["alpha", "beta"]),
            approved_by="Lead agency",
            reproducible=True,
        )


def test_rollup_rejects_incompatible_partner_definitions(tmp_path: Path) -> None:
    _bundle(_partner(tmp_path, "alpha", _ids("alpha-", 12)), tmp_path / "bundle-alpha")
    _bundle(
        _partner(
            tmp_path,
            "beta",
            _ids("beta-", 13),
            definition="People served, counting each enrollment separately.",
        ),
        tmp_path / "bundle-beta",
    )

    with pytest.raises(WorkflowError, match="partner definitions do not match"):
        build_rollup(
            plan_path=_plan(tmp_path, "plan.json", ["alpha", "beta"]),
            approved_by="Lead agency",
            reproducible=True,
        )


def test_rollup_rejects_a_partner_reporting_a_different_period(tmp_path: Path) -> None:
    _two_partners(tmp_path)
    plan_path = _plan(tmp_path, "plan.json", ["alpha", "beta"])
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    plan["inputs"][1]["period"] = "2026-Q1"
    plan_path.write_text(json.dumps(plan, indent=2), encoding="utf-8")

    with pytest.raises(WorkflowError, match="period does not match"):
        build_rollup(plan_path=plan_path, approved_by="Lead agency", reproducible=True)


def test_rollup_rejects_a_partner_under_another_suppression_policy(tmp_path: Path) -> None:
    _two_partners(tmp_path)
    plan_path = _plan(tmp_path, "plan.json", ["alpha", "beta"])
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    plan["inputs"][0]["suppression_policy_id"] = "local-threshold-5"
    plan_path.write_text(json.dumps(plan, indent=2), encoding="utf-8")

    with pytest.raises(WorkflowError, match="suppression policy does not match"):
        build_rollup(plan_path=plan_path, approved_by="Lead agency", reproducible=True)


def test_rollup_rejects_an_undeclared_population_overlap(tmp_path: Path) -> None:
    _two_partners(tmp_path)
    plan_path = _plan(tmp_path, "plan.json", ["alpha", "beta"], overlap="probably_fine")

    with pytest.raises(WorkflowError, match="population_overlap must be"):
        build_rollup(plan_path=plan_path, approved_by="Lead agency", reproducible=True)


def test_rollup_rejects_a_single_partner(tmp_path: Path) -> None:
    _two_partners(tmp_path)
    plan_path = _plan(tmp_path, "plan.json", ["alpha"])

    with pytest.raises(WorkflowError, match="at least two partner bundles"):
        build_rollup(plan_path=plan_path, approved_by="Lead agency", reproducible=True)


def _same_rows_two_partners(root: Path) -> None:
    """Two partners whose exports carry the identical client-id slice."""

    shared = _ids("shared-", 12)
    _bundle(_partner(root, "alpha", shared), root / "bundle-alpha")
    _bundle(_partner(root, "beta", shared), root / "bundle-beta")


def _hollow_slice_partner(root: Path, name: str, client_ids: list[str]) -> Path:
    """A partner whose count is real but whose slice query returns no rows.

    The receipt this produces is the shape the disjoint gate must refuse: a
    non-zero count carrying ``EMPTY_SLICE_HASH``. That sentinel is the same for
    every empty slice, so it cannot be compared against any other partner's rows,
    and the count it accompanies still enters the sum. Nothing here is forged;
    the bundle verifies, because the spec is what it says it is.
    """

    directory = root / name
    directory.mkdir(parents=True)
    (directory / "data.csv").write_text(
        "\n".join(["client_id", *client_ids]) + "\n", encoding="utf-8"
    )
    config = directory / "report.toml"
    config.write_text(_HOLLOW_SLICE_SPEC.replace("__NAME__", name), encoding="utf-8")
    return config


def test_rollup_rejects_identical_partner_slices_declared_disjoint(tmp_path: Path) -> None:
    """The same rows submitted by two partners falsify a disjoint declaration.

    The bundles differ (each carries its own title and report), so the duplicate
    bundle-digest check does not fire. What matches is the receipt's slice hash,
    which is a content hash of the rows the count was computed from. Two equal
    non-empty slice hashes mean the same people were counted twice, which a
    disjoint population cannot produce.
    """

    _same_rows_two_partners(tmp_path)
    plan_path = _plan(tmp_path, "plan.json", ["alpha", "beta"])

    with pytest.raises(WorkflowError, match="identical data slices cannot be a disjoint"):
        build_rollup(plan_path=plan_path, approved_by="Lead agency", reproducible=True)


def test_rollup_names_the_colliding_partners_in_plan_order_independently(
    tmp_path: Path,
) -> None:
    _same_rows_two_partners(tmp_path)
    messages = []
    for index, order in enumerate([["alpha", "beta"], ["beta", "alpha"]]):
        with pytest.raises(WorkflowError) as caught:
            build_rollup(
                plan_path=_plan(tmp_path, f"plan-{index}.json", order),
                approved_by="Lead agency",
                reproducible=True,
            )
        messages.append(str(caught.value))

    assert messages[0] == messages[1]
    assert messages[0].startswith("alpha and beta:")


def test_rollup_rejects_a_non_zero_count_over_an_empty_data_slice(tmp_path: Path) -> None:
    """The empty-slice exemption must not be reachable by a non-zero count.

    Both partners here count twelve people and both publish ``EMPTY_SLICE_HASH``,
    because each spec's slice query returns no rows. Every bundle verifies. If the
    exemption were keyed on the hash alone, both receipts would skip the disjoint
    check and the rollup would publish twenty-four people served under a
    ``disjoint`` declaration, in this fixture the same twelve people counted
    twice: the exact silent pass this gate exists to prevent. An empty slice
    exempts a receipt only when the receipt reports nothing counted.
    """

    shared = _ids("shared-", 12)
    _bundle(_hollow_slice_partner(tmp_path, "alpha", shared), tmp_path / "bundle-alpha")
    _bundle(_hollow_slice_partner(tmp_path, "beta", shared), tmp_path / "bundle-beta")

    for name in ("alpha", "beta"):
        manifest = json.loads(
            (tmp_path / f"bundle-{name}" / "receipts.json").read_text(encoding="utf-8")
        )
        receipt = manifest["receipts"][0]
        assert receipt["slice_hash"] == EMPTY_SLICE_HASH
        assert receipt["value"] == 12.0

    with pytest.raises(WorkflowError, match="empty data slice carries no evidence"):
        build_rollup(
            plan_path=_plan(tmp_path, "plan.json", ["alpha", "beta"]),
            approved_by="Lead agency",
            reproducible=True,
        )


def test_rollup_names_two_bundles_from_one_partner_by_digest(tmp_path: Path) -> None:
    """One organization submitting the same rows twice is not "alpha and alpha".

    A partner can legitimately appear twice in a plan under two bundles, one per
    program. The bundle digests differ, so the duplicate-digest check does not
    fire, and the collision message has to say which two submissions carry the
    same rows. The partner name alone cannot.
    """

    _same_rows_two_partners(tmp_path)
    plan_path = _plan(tmp_path, "plan.json", ["alpha", "alpha"], sources=["alpha", "beta"])

    with pytest.raises(WorkflowError) as caught:
        build_rollup(plan_path=plan_path, approved_by="Lead agency", reproducible=True)

    message = str(caught.value)
    assert "alpha and alpha" not in message
    assert message.count("alpha (bundle ") == 2
    digests = re.findall(r"alpha \(bundle ([0-9a-f]+)\)", message)
    assert len(set(digests)) == 2


def test_rollup_allows_identical_slices_when_declared_not_deduplicated(tmp_path: Path) -> None:
    """A declared non-deduplicated rollup keeps its operator-supplied label.

    The overlap declaration is the plan's answer to duplicate-client risk. When
    it already says the combined figure counts some people more than once, the
    slice-collision gate has nothing to falsify and the rollup proceeds.
    """

    _same_rows_two_partners(tmp_path)
    plan_path = _plan(tmp_path, "plan.json", ["alpha", "beta"], overlap="not_deduplicated")

    artifact = build_rollup(plan_path=plan_path, approved_by="Lead agency", reproducible=True)

    assert artifact["population_overlap"] == "not_deduplicated"
    assert artifact["rollup_receipt"]["display"] == "24"
    assert verify_workflow_artifact(artifact).ok


def test_rollup_accepts_disjoint_partners_who_both_report_a_true_zero(tmp_path: Path) -> None:
    """An empty slice is shared by every empty partner and is not a collision."""

    for name in ("alpha", "beta"):
        directory = tmp_path / name
        directory.mkdir()
        (directory / "data.csv").write_text(
            "\n".join(["client_id,exited", *[f"{name}-{index},no" for index in range(12)]]) + "\n",
            encoding="utf-8",
        )
        (directory / "report.toml").write_text(
            _ZERO_SPEC.replace("__NAME__", name), encoding="utf-8"
        )
        _bundle(directory / "report.toml", tmp_path / f"bundle-{name}")

    artifact = build_rollup(
        plan_path=_plan(tmp_path, "plan.json", ["alpha", "beta"], metric_id="exited"),
        approved_by="Lead agency",
        reproducible=True,
    )

    assert artifact["rollup_receipt"]["value"] == 0.0
    assert verify_workflow_artifact(artifact).ok


def test_rollup_rejects_a_suppressed_partner_cell(tmp_path: Path) -> None:
    _bundle(_partner(tmp_path, "alpha", _ids("alpha-", 4)), tmp_path / "bundle-alpha")
    _bundle(_partner(tmp_path, "beta", _ids("beta-", 13)), tmp_path / "bundle-beta")

    with pytest.raises(WorkflowError, match="suppressed metrics cannot be rolled up"):
        build_rollup(
            plan_path=_plan(tmp_path, "plan.json", ["alpha", "beta"]),
            approved_by="Lead agency",
            reproducible=True,
        )


def test_rollup_artifact_carries_no_partner_value_row_count_or_slice_hash(
    tmp_path: Path,
) -> None:
    """No path leads from the artifact back to a partner's own cell.

    The artifact names each partner and the digest of the bundle that was
    verified. It does not republish the partner's value, row count, or slice
    hash, so a reader holding the rollup cannot subtract their way to any single
    partner's figure, suppressed or not.
    """

    _two_partners(tmp_path)
    alpha = json.loads((tmp_path / "bundle-alpha" / "receipts.json").read_text(encoding="utf-8"))
    beta = json.loads((tmp_path / "bundle-beta" / "receipts.json").read_text(encoding="utf-8"))

    artifact = build_rollup(
        plan_path=_plan(tmp_path, "plan.json", ["alpha", "beta"]),
        approved_by="Lead agency",
        reproducible=True,
    )
    serialized = json.dumps(artifact, sort_keys=True)

    for manifest in (alpha, beta):
        receipt = manifest["receipts"][0]
        assert receipt["slice_hash"] != EMPTY_SLICE_HASH
        assert receipt["slice_hash"] not in serialized
        assert f'"row_count": {receipt["row_count"]}' not in serialized
        assert f'"value": {float(receipt["value"])}' not in serialized
    assert {key for item in artifact["inputs"] for key in item} == {"partner", "bundle_digest"}
    assert {key for item in artifact["rollup_receipt"]["inputs"] for key in item} == {
        "metric_id",
        "receipt_digest",
    }
