"""The provenance statement that travels with every export.

Funders are beginning to reject reports that are substantially written by a
language model, because a model that writes plausible outcome numbers is a
liability. This tool's answer is structural: every number comes from a
deterministic query and carries a receipt. The point is worth stating on the
report itself, in language the funder who receives it can read.

So each export embeds a short, standard provenance block: the numbers were
computed by deterministic SQL, no figure was written by a model, and the
grounding gate bound every number to a receipt before the report could leave.
The same facts go into the receipts manifest as a machine-readable record, so the
claim is checkable and not only printed. Nothing here is generated text; the block
is assembled from the counts the gate already produced.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from outcome_receipts.copy import Locale, get_copy
from outcome_receipts.models import ApprovalPolicy, person_key, role_key


class ApprovalError(Exception):
    """A sign-off that does not satisfy the spec's approval policy.

    Raised before anything is written. Every message names the role or the
    person at fault, because "approval failed" tells the operator to guess which
    of two or three sign-offs is the one missing.
    """


@dataclass(frozen=True)
class Approval:
    """One recorded human sign-off: which role, who filled it, and when.

    ``approved_at`` is when this run recorded the approval, which is the same
    instant for every role in one invocation: a ``run`` is a single sign-off
    event, not an asynchronous workflow, and writing three different sub-second
    stamps would imply a sequence the tool does not observe. The field is per
    approval rather than per export so that a future flow which does collect
    sign-offs over time has somewhere truthful to record them.
    """

    role: str
    name: str
    approved_at: str


def _by_role(supplied: Sequence[tuple[str, str]]) -> dict[str, tuple[str, str]]:
    """Index the supplied sign-offs by role key, refusing a role given twice."""

    indexed: dict[str, tuple[str, str]] = {}
    for role, name in supplied:
        key = role_key(role)
        if key in indexed:
            raise ApprovalError(f"role {role!r} was approved more than once")
        indexed[key] = (role, name.strip())
    return indexed


def _check_roles(policy: ApprovalPolicy, by_role: dict[str, tuple[str, str]]) -> None:
    """Refuse a role the policy does not name, and a role it names that is unfilled."""

    known = set(policy.normalized())
    unknown = [role for key, (role, _name) in by_role.items() if key not in known]
    if unknown:
        raise ApprovalError(
            ", ".join(repr(role) for role in unknown)
            + " is not required by this spec; it requires "
            + ", ".join(repr(role) for role in policy.required)
        )
    missing = [role for role in policy.required if role_key(role) not in by_role]
    if missing:
        raise ApprovalError(
            "the spec requires a sign-off for "
            + ", ".join(repr(role) for role in missing)
            + " and none was given"
        )


def _check_distinct_people(approvals: Sequence[Approval]) -> None:
    """Refuse one person filling two roles, comparing folded names."""

    people: dict[str, str] = {}
    for approval in approvals:
        key = person_key(approval.name)
        if key in people:
            raise ApprovalError(
                f"{approval.name!r} cannot fill both {people[key]!r} and {approval.role!r}; "
                "a dual sign-off needs two people"
            )
        people[key] = approval.role


def resolve_approvals(
    policy: ApprovalPolicy | None,
    supplied: Sequence[tuple[str, str]],
    *,
    approved_at: str,
) -> tuple[Approval, ...]:
    """Check ``role:name`` sign-offs against a spec's policy, or refuse.

    Returns the approvals in the policy's own order, so the recorded set does not
    depend on the order the roles were given on the command line. Every refusal
    is an ``ApprovalError``; there is no partial result, because a partially
    satisfied dual sign-off is exactly the evidence the policy exists to refuse.
    """

    if policy is None:
        if supplied:
            raise ApprovalError(
                "this spec declares no [approval] policy, so --approve has no roles to "
                "fill; record the single approver with --approved-by"
            )
        return ()

    by_role = _by_role(supplied)
    _check_roles(policy, by_role)

    approvals: list[Approval] = []
    for role in policy.required:
        _given_role, name = by_role[role_key(role)]
        if not name:
            raise ApprovalError(f"the sign-off for role {role!r} has no approver name")
        approvals.append(Approval(role=role, name=name, approved_at=approved_at))

    _check_distinct_people(approvals)
    return tuple(approvals)


def approvals_summary(approvals: Sequence[Approval]) -> str:
    """The approvers as one display string, in policy order.

    This is what ``approved_by`` carries for a role-based spec. Keeping that
    field populated rather than blank is deliberate: every reader that already
    checks a bundle has a named human approval -- ``verify-workflow`` and the
    rollup composition among them -- keeps working, and it keeps working by
    reading a string that names all of the approvers rather than one of them.
    """

    return ", ".join(f"{approval.name} ({approval.role})" for approval in approvals)


@dataclass(frozen=True)
class Provenance:
    """The grounding outcome an export attests to.

    ``numbers_bound`` is how many numeric spans across the report (the narrative
    and any chart or comparison claims) bound to a receipt. ``numbers_unbound`` is
    how many did not; an export only happens when it is zero, but the field is kept
    so the record states the gate result rather than implying it.

    ``suppression_applied`` is True when small-cell suppression has been run on
    the figures (CMS policy: values < 11 suppressed, true zeros preserved, with
    complementary suppression). ``aggregate_only`` is True when no row-level data
    was emitted in the export; the report contains only counts and aggregates.
    """

    numbers_bound: int
    numbers_unbound: int = 0
    approved_by: str | None = None
    approved_at: str | None = None
    suppression_applied: bool = False
    aggregate_only: bool = True
    narrative_drafter: str = "deterministic"
    #: The role-based sign-offs this export recorded, in the spec's policy order.
    #: Empty for a spec that declares no ``[approval]`` policy, and the manifest
    #: then carries no ``approvals`` key at all -- such a spec has not satisfied
    #: zero roles, it has declared none. ``verify --bundle`` re-reads the policy
    #: from the spec, so a manifest missing the key against a spec that does
    #: declare one fails there rather than reading as an empty pass.
    approvals: tuple[Approval, ...] = field(default_factory=tuple)

    @property
    def gate_pass(self) -> bool:
        return self.numbers_unbound == 0


def provenance_markdown(prov: Provenance, *, locale: Locale = "en") -> str:
    """Render the provenance block as a Markdown section for the report body."""

    copy = get_copy(locale)
    gate_line = (
        copy.provenance_gate_pass_template.format(bound=prov.numbers_bound)
        if prov.gate_pass
        else copy.provenance_gate_fail_template.format(unbound=prov.numbers_unbound)
    )
    lines = [
        copy.provenance_heading,
        "",
        copy.provenance_statement,
        "",
        gate_line,
    ]
    if prov.approved_by is not None:
        when = (
            copy.provenance_approval_when_template.format(timestamp=prov.approved_at)
            if prov.approved_at is not None
            else ""
        )
        lines.extend(
            ["", copy.provenance_approval_template.format(approver=prov.approved_by, when=when)]
        )
    return "\n".join(lines)


def provenance_record(prov: Provenance) -> dict[str, object]:
    """Render the provenance attestation as a machine-readable manifest record."""

    record: dict[str, object] = {
        "numbers_from": "deterministic_sql",
        "model_wrote_numbers": False,
        "grounding_gate": "pass" if prov.gate_pass else "fail",
        "numbers_bound": prov.numbers_bound,
        "numbers_unbound": prov.numbers_unbound,
        # State approval status explicitly, always: ``None`` when no human signed
        # off, so the manifest never leaves the reader to infer it (fail-closed).
        "approved_by": prov.approved_by,
        "suppression_applied": prov.suppression_applied,
        "aggregate_only": prov.aggregate_only,
        "narrative_drafter": prov.narrative_drafter,
    }
    if prov.approved_by is not None:
        record["approved_at"] = prov.approved_at
    if prov.approvals:
        record["approvals"] = [
            {
                "role": approval.role,
                "approved_by": approval.name,
                "approved_at": approval.approved_at,
            }
            for approval in prov.approvals
        ]
    return record
