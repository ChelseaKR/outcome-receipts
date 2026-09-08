"""Merge-blocking: a human sign-off gates every export.

The grounding gate proves each number traces to a receipt; it does not prove a
person reviewed the report before it left. R8 adds that second gate: the export
records a named approver, and refuses to write anything when nobody signed off.
These tests pin that the approver reaches both surfaces a reader trusts — the
report body and the machine-readable manifest — that the gate fails closed off a
TTY, and that it never runs before or instead of the grounding gate.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import pytest

from outcome_receipts import cli
from outcome_receipts.cli import main
from outcome_receipts.config import load_spec
from outcome_receipts.draft import draft
from outcome_receipts.models import Figure, ReportSpec
from outcome_receipts.provenance import Provenance, provenance_record

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
GRANT = EXAMPLES / "grant-report" / "report.toml"


def test_run_with_approved_by_records_the_approver(tmp_path: Path) -> None:
    out = tmp_path / "grant"
    code = main(
        [
            "run",
            "--config",
            str(GRANT),
            "--out",
            str(out),
            "--reproducible",
            "--approved-by",
            "Jane Doe",
        ]
    )
    assert code == 0

    manifest = json.loads((out / "receipts.json").read_text(encoding="utf-8"))
    assert manifest["provenance"]["approved_by"] == "Jane Doe"

    report = (out / "report.md").read_text(encoding="utf-8")
    assert "reviewed and approved for export by Jane Doe" in report


def test_run_without_approver_off_a_tty_aborts_and_writes_nothing(
    tmp_path: Path,
) -> None:
    # pytest runs with stdin not a TTY, so there is nobody to prompt. Without
    # --approved-by the export must fail closed: a nonzero code and no files.
    out = tmp_path / "grant"
    code = main(["run", "--config", str(GRANT), "--out", str(out), "--reproducible"])
    assert code == 3
    assert not out.exists()


def test_grounding_gate_fail_returns_2_before_the_approval_prompt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A stray, ungrounded number must be caught by the grounding gate (exit 2)
    # before the approval gate is ever consulted — approval never bypasses it.
    def _tampered_draft(spec: ReportSpec, figures: Sequence[Figure]) -> str:
        clean = draft(spec, figures)
        return clean + " We also served 999 extra clients."

    monkeypatch.setattr(cli, "draft", _tampered_draft)

    out = tmp_path / "grant"
    code = main(
        [
            "run",
            "--config",
            str(GRANT),
            "--out",
            str(out),
            "--reproducible",
            "--approved-by",
            "Jane Doe",
        ]
    )
    assert code == 2
    assert not out.exists()


def test_manifest_with_no_approver_records_approved_by_null() -> None:
    record = provenance_record(Provenance(numbers_bound=4))
    assert record["approved_by"] is None
    assert "approved_at" not in record


# --------------------------------------------------------------------------
# Role-based dual sign-off (issue 162).
#
# A spec may declare `[approval] required = ["program", "finance"]`. The policy
# then travels with the report definition, which is the point: it cannot be
# satisfied by a different invocation flag, and the check that reads it back is
# `verify --bundle`, which re-reads the spec rather than the manifest.
# --------------------------------------------------------------------------

TWO_ROLES = '\n[approval]\nrequired = ["program", "finance"]\n'


def _spec_with_approval(tmp_path: Path, policy: str = TWO_ROLES) -> Path:
    """A copy of the shipped grant-report example carrying an approval policy.

    Copied whole rather than invented, because `data.path` resolves against the
    spec's own directory and the example's data, metrics, comparison and caveats
    are the ones every other export test runs against. The only difference from
    the committed spec is the appended section.
    """

    target = tmp_path / "grant"
    shutil.copytree(GRANT.parent, target)
    config = target / "report.toml"
    config.write_text(config.read_text(encoding="utf-8") + policy, encoding="utf-8")
    return config


def _run(config: Path, out: Path, *approve: str, extra: Sequence[str] = ()) -> int:
    argv = ["run", "--config", str(config), "--out", str(out), "--reproducible"]
    for pair in approve:
        argv += ["--approve", pair]
    return main([*argv, *extra])


def test_loader_reads_a_two_role_policy_in_the_order_the_spec_wrote_it(
    tmp_path: Path,
) -> None:
    spec = load_spec(_spec_with_approval(tmp_path))
    assert spec.report.approval is not None
    assert spec.report.approval.required == ("program", "finance")


def test_loader_refuses_an_approval_section_that_requires_nobody(tmp_path: Path) -> None:
    # An empty policy would read in the manifest exactly like a satisfied one:
    # a declared sign-off gate that cannot fail. It is an authoring error.
    config = _spec_with_approval(tmp_path, "\n[approval]\n")
    with pytest.raises(ValueError, match="non-empty array of role names"):
        load_spec(config)


def test_loader_refuses_the_same_role_named_twice(tmp_path: Path) -> None:
    config = _spec_with_approval(tmp_path, '\n[approval]\nrequired = ["program", "Program"]\n')
    with pytest.raises(ValueError, match="more than once"):
        load_spec(config)


def test_two_role_run_records_both_approvals_and_names_both_in_the_report(
    tmp_path: Path,
) -> None:
    config = _spec_with_approval(tmp_path)
    out = tmp_path / "export"
    assert _run(config, out, "program:A. Lee", "finance:B. Cruz") == 0

    manifest = json.loads((out / "receipts.json").read_text(encoding="utf-8"))
    provenance = manifest["provenance"]
    assert [(a["role"], a["approved_by"]) for a in provenance["approvals"]] == [
        ("program", "A. Lee"),
        ("finance", "B. Cruz"),
    ]
    # `approved_by` stays populated and names every approver, so every reader
    # that already requires a named human approval keeps working.
    assert provenance["approved_by"] == "A. Lee (program), B. Cruz (finance)"
    assert all(a["approved_at"] == provenance["approved_at"] for a in provenance["approvals"])

    report = (out / "report.md").read_text(encoding="utf-8")
    assert "A. Lee (program), B. Cruz (finance)" in report


def test_two_role_run_with_one_approver_exits_3_and_writes_nothing(tmp_path: Path) -> None:
    config = _spec_with_approval(tmp_path)
    out = tmp_path / "export"
    assert _run(config, out, "program:A. Lee") == 3
    assert not out.exists()


def test_the_refusal_names_the_missing_role(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = _spec_with_approval(tmp_path)
    assert _run(config, tmp_path / "export", "program:A. Lee") == 3
    assert "'finance'" in capsys.readouterr().err


def test_approved_by_cannot_satisfy_a_role_policy(tmp_path: Path) -> None:
    # The whole point of putting the policy in the spec: a different invocation
    # flag must not satisfy it.
    config = _spec_with_approval(tmp_path)
    out = tmp_path / "export"
    code = main(
        [
            "run",
            "--config",
            str(config),
            "--out",
            str(out),
            "--reproducible",
            "--approved-by",
            "A. Lee",
        ]
    )
    assert code == 3
    assert not out.exists()


def test_approved_by_alongside_role_approvals_is_refused(tmp_path: Path) -> None:
    """The test above passes without the explicit refusal, so this one exists.

    With no `--approve` flags, `--approved-by` against a role policy is already
    refused by the missing-roles check, for a reason that has nothing to do with
    `--approved-by`. The combination is what the explicit guard is for: without
    it the run succeeds and the named single approver is silently dropped from a
    record that says two people signed.
    """

    config = _spec_with_approval(tmp_path)
    out = tmp_path / "export"
    code = main(
        [
            "run",
            "--config",
            str(config),
            "--out",
            str(out),
            "--reproducible",
            "--approve",
            "program:A. Lee",
            "--approve",
            "finance:B. Cruz",
            "--approved-by",
            "C. Diaz",
        ]
    )
    assert code == 3
    assert not out.exists()


# `  A. Lee  ` is folded by the command-line parser's own strip before the
# identity rule sees it, so it exercises that strip rather than the fold. The
# other two are the cases only the folded comparison can catch, which a control
# on `person_key` confirmed: identity comparison left the whitespace-padded case
# green and turned the other two red.
@pytest.mark.parametrize("second", ["a. lee", "A.  Lee", "  A. Lee  "])
def test_one_person_cannot_fill_both_roles(tmp_path: Path, second: str) -> None:
    # Case and internal whitespace do not make one person into two. The rule is
    # constituent-reconciler's, and the variants are the ones a real operator
    # types rather than the ones a normalizer is written against.
    config = _spec_with_approval(tmp_path)
    out = tmp_path / "export"
    assert _run(config, out, "program:A. Lee", f"finance:{second}") == 3
    assert not out.exists()


def test_a_role_the_spec_does_not_require_is_refused(tmp_path: Path) -> None:
    config = _spec_with_approval(tmp_path)
    out = tmp_path / "export"
    assert _run(config, out, "program:A. Lee", "finance:B. Cruz", "board:C. Diaz") == 3
    assert not out.exists()


def test_approve_without_a_colon_is_refused(tmp_path: Path) -> None:
    config = _spec_with_approval(tmp_path)
    out = tmp_path / "export"
    assert _run(config, out, "program", "finance:B. Cruz") == 3
    assert not out.exists()


def test_approve_is_refused_by_a_spec_that_declares_no_policy(tmp_path: Path) -> None:
    out = tmp_path / "export"
    assert _run(GRANT, out, "program:A. Lee") == 3
    assert not out.exists()


def test_the_recorded_set_does_not_depend_on_flag_order(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    assert (
        _run(_spec_with_approval(tmp_path / "a"), first, "program:A. Lee", "finance:B. Cruz") == 0
    )
    assert (
        _run(_spec_with_approval(tmp_path / "b"), second, "finance:B. Cruz", "program:A. Lee") == 0
    )

    def _approvals(out: Path) -> object:
        manifest = json.loads((out / "receipts.json").read_text(encoding="utf-8"))
        return manifest["provenance"]["approvals"]

    assert _approvals(first) == _approvals(second)


def test_a_single_approver_spec_records_no_approvals_key(tmp_path: Path) -> None:
    # An unbound spec has not satisfied zero roles, it has declared none. The
    # key is absent rather than an empty list, the same way an unbound
    # requirement set carries no `requirements` record.
    out = tmp_path / "export"
    assert (
        main(
            [
                "run",
                "--config",
                str(GRANT),
                "--out",
                str(out),
                "--reproducible",
                "--approved-by",
                "Jane Doe",
            ]
        )
        == 0
    )
    manifest = json.loads((out / "receipts.json").read_text(encoding="utf-8"))
    assert "approvals" not in manifest["provenance"]


def _verify(config: Path, bundle: Path) -> int:
    return main(["verify", "--config", str(config), "--bundle", str(bundle), "--reproducible"])


def test_verify_bundle_confirms_the_recorded_approvals_against_the_policy(
    tmp_path: Path,
) -> None:
    config = _spec_with_approval(tmp_path)
    out = tmp_path / "export"
    assert _run(config, out, "program:A. Lee", "finance:B. Cruz") == 0
    assert _verify(config, out) == 0


def test_verify_bundle_fails_when_the_policy_gains_a_role_after_export(
    tmp_path: Path,
) -> None:
    # The policy is re-read from the spec, never from the manifest, so a bundle
    # approved under a two-role policy stops verifying against a three-role one.
    config = _spec_with_approval(tmp_path)
    out = tmp_path / "export"
    assert _run(config, out, "program:A. Lee", "finance:B. Cruz") == 0

    config.write_text(
        config.read_text(encoding="utf-8").replace(
            'required = ["program", "finance"]',
            'required = ["program", "finance", "board"]',
        ),
        encoding="utf-8",
    )
    assert _verify(config, out) == 1


def test_verify_bundle_fails_when_an_approval_is_deleted_from_the_manifest(
    tmp_path: Path,
) -> None:
    config = _spec_with_approval(tmp_path)
    out = tmp_path / "export"
    assert _run(config, out, "program:A. Lee", "finance:B. Cruz") == 0

    manifest_path = out / "receipts.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["provenance"]["approvals"] = manifest["provenance"]["approvals"][:1]
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    assert _verify(config, out) == 1


def test_verify_bundle_fails_when_the_manifest_records_no_approvals_at_all(
    tmp_path: Path,
) -> None:
    # Absence must not read as "no policy was in force". The spec says otherwise.
    config = _spec_with_approval(tmp_path)
    out = tmp_path / "export"
    assert _run(config, out, "program:A. Lee", "finance:B. Cruz") == 0

    manifest_path = out / "receipts.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    del manifest["provenance"]["approvals"]
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    assert _verify(config, out) == 1


def test_verify_bundle_reports_not_checked_when_neither_side_declares_a_policy(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "export"
    assert (
        main(
            [
                "run",
                "--config",
                str(GRANT),
                "--out",
                str(out),
                "--reproducible",
                "--approved-by",
                "Jane Doe",
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert _verify(GRANT, out) == 0
    assert "approval policy: not checked" in capsys.readouterr().out


def test_verify_bundle_fails_when_the_manifest_records_a_policy_the_spec_dropped(
    tmp_path: Path,
) -> None:
    config = _spec_with_approval(tmp_path)
    out = tmp_path / "export"
    assert _run(config, out, "program:A. Lee", "finance:B. Cruz") == 0

    config.write_text(config.read_text(encoding="utf-8").replace(TWO_ROLES, "\n"), encoding="utf-8")
    assert _verify(config, out) == 1


# --------------------------------------------------------------------------
# The workflow commands honour the same policy. Without this, a two-role spec
# could be packaged as contract evidence with one signature -- which is the
# bypass the policy exists to close.
# --------------------------------------------------------------------------


def _contract_spec(tmp_path: Path, *, policy: str) -> tuple[Path, Path]:
    data = tmp_path / "contract.csv"
    data.write_text(
        "\n".join(["client_id,threshold,amount"] + [f"p{i},11,5000" for i in range(12)]) + "\n",
        encoding="utf-8",
    )
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
""".lstrip()
        + policy,
        encoding="utf-8",
    )
    contract = tmp_path / "contract.json"
    contract.write_text(
        json.dumps(
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
                        "comparison": "gte",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return config, contract


def _contract_check(config: Path, contract: Path, out: Path, *flags: str) -> int:
    return main(
        [
            "contract-check",
            "--config",
            str(config),
            "--contract",
            str(contract),
            "--out",
            str(out),
            "--reproducible",
            *flags,
        ]
    )


def test_contract_check_refuses_one_signature_against_a_two_role_spec(
    tmp_path: Path,
) -> None:
    config, contract = _contract_spec(tmp_path, policy=TWO_ROLES)
    out = tmp_path / "contract-evidence.json"
    assert _contract_check(config, contract, out, "--approved-by", "A. Lee") == 3
    assert not out.exists()


def test_contract_check_records_both_roles_when_the_policy_is_satisfied(
    tmp_path: Path,
) -> None:
    config, contract = _contract_spec(tmp_path, policy=TWO_ROLES)
    out = tmp_path / "contract-evidence.json"
    assert (
        _contract_check(
            config,
            contract,
            out,
            "--approve",
            "program:A. Lee",
            "--approve",
            "finance:B. Cruz",
        )
        == 0
    )
    artifact = json.loads(out.read_text(encoding="utf-8"))
    assert artifact["approved_by"] == "A. Lee (program), B. Cruz (finance)"


def test_contract_check_still_takes_a_single_approver_with_no_policy(
    tmp_path: Path,
) -> None:
    config, contract = _contract_spec(tmp_path, policy="")
    out = tmp_path / "contract-evidence.json"
    assert _contract_check(config, contract, out, "--approved-by", "A. Lee") == 0
    assert json.loads(out.read_text(encoding="utf-8"))["approved_by"] == "A. Lee"


def test_contract_check_with_no_sign_off_at_all_exits_3(tmp_path: Path) -> None:
    config, contract = _contract_spec(tmp_path, policy="")
    out = tmp_path / "contract-evidence.json"
    assert _contract_check(config, contract, out) == 3
    assert not out.exists()


# --------------------------------------------------------------------------
# The refusals a malformed record or a malformed policy takes. Each of these is
# a branch that decides whether an unreadable value reads as "nothing to check".
# --------------------------------------------------------------------------


def test_the_same_role_supplied_twice_on_one_command_line_is_refused(
    tmp_path: Path,
) -> None:
    config = _spec_with_approval(tmp_path)
    out = tmp_path / "export"
    assert _run(config, out, "program:A. Lee", "program:B. Cruz") == 3
    assert not out.exists()


def test_a_role_supplied_with_an_empty_name_is_refused(tmp_path: Path) -> None:
    config = _spec_with_approval(tmp_path)
    out = tmp_path / "export"
    assert _run(config, out, "program:A. Lee", "finance:   ") == 3
    assert not out.exists()


def test_loader_refuses_a_non_table_approval_section(tmp_path: Path) -> None:
    # The key has to go before the first table header, or TOML nests it inside
    # whichever table the spec happened to end with. The first run of this test
    # appended it and the loader never saw a top-level `approval` at all.
    config = _spec_with_approval(tmp_path, "")
    config.write_text(
        config.read_text(encoding="utf-8").replace(
            'schema_version = "1.0"', 'schema_version = "1.0"\napproval = "program"', 1
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match=r"\[approval\] must be a table"):
        load_spec(config)


def test_loader_refuses_a_role_that_is_not_a_non_empty_string(tmp_path: Path) -> None:
    config = _spec_with_approval(tmp_path, '\n[approval]\nrequired = ["program", ""]\n')
    with pytest.raises(ValueError, match="non-empty strings"):
        load_spec(config)


def _set_approvals(value: object) -> Callable[[dict[str, Any]], None]:
    def mangle(manifest: dict[str, Any]) -> None:
        manifest["provenance"]["approvals"] = value

    return mangle


def _replace_provenance(manifest: dict[str, Any]) -> None:
    manifest["provenance"] = "signed"


@pytest.mark.parametrize(
    ("mangle", "label"),
    [
        (_set_approvals("program"), "not a list"),
        (_set_approvals(["program"]), "not objects"),
        (_replace_provenance, "provenance not an object"),
    ],
)
def test_a_malformed_approvals_record_fails_rather_than_skipping_the_check(
    tmp_path: Path, mangle: Callable[[dict[str, Any]], None], label: str
) -> None:
    # The failure direction matters more than the message. A record the verifier
    # cannot read must not take the "nothing to compare" path, because that path
    # reports `not checked` and passes.
    config = _spec_with_approval(tmp_path)
    out = tmp_path / "export"
    assert _run(config, out, "program:A. Lee", "finance:B. Cruz") == 0

    manifest_path = out / "receipts.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    mangle(manifest)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    assert _verify(config, out) == 1, label
