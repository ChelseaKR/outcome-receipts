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

from dataclasses import dataclass


@dataclass(frozen=True)
class Provenance:
    """The grounding outcome an export attests to.

    ``numbers_bound`` is how many numeric spans across the report (the narrative
    and any chart or comparison claims) bound to a receipt. ``numbers_unbound`` is
    how many did not; an export only happens when it is zero, but the field is kept
    so the record states the gate result rather than implying it.
    """

    numbers_bound: int
    numbers_unbound: int = 0
    approved_by: str | None = None
    approved_at: str | None = None

    @property
    def gate_pass(self) -> bool:
        return self.numbers_unbound == 0


def provenance_markdown(prov: Provenance) -> str:
    """Render the provenance block as a Markdown section for the report body."""

    gate_line = (
        f"Before this report was exported, the grounding gate bound all "
        f"{prov.numbers_bound} of its numbers to a receipt; a number that traced "
        "to no receipt would have blocked the export."
        if prov.gate_pass
        else (
            f"The grounding gate left {prov.numbers_unbound} number(s) unbound, so "
            "this report is not cleared for export."
        )
    )
    lines = [
        "## Provenance",
        "",
        "Every number in this report was computed by a deterministic SQL query "
        "over the organization's own service data. No figure was written by a "
        "language model. Each figure carries a receipt below: the exact query, "
        "the count of rows it drew from, a content hash of that data slice, and "
        "a timestamp.",
        "",
        gate_line,
    ]
    if prov.approved_by is not None:
        when = f" on {prov.approved_at}" if prov.approved_at is not None else ""
        lines.extend(
            [
                "",
                f"This report was reviewed and approved for export by "
                f"{prov.approved_by}{when}.",
            ]
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
    }
    if prov.approved_by is not None:
        record["approved_at"] = prov.approved_at
    return record
