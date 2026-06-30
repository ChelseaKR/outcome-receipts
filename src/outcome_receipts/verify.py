"""Re-derivation check for a committed receipts manifest.

A receipt is only worth trusting if it can be re-derived. ``receipts verify``
recomputes every figure from the report spec and the cited data, then checks each
recomputed value, slice hash, row count, query, and display against the receipts
manifest the report was exported with. A mismatch is drift: the data changed, the
spec changed, or the manifest was edited after the fact. Verify fails closed,
reporting every drifted receipt and any receipt it cannot re-derive, so a silent
divergence cannot pass.

The timestamp is deliberately not checked. ``computed_at`` records when a figure
was produced, so it differs run to run by design; comparing it would flag every
re-run as drift and say nothing about whether the numbers still hold.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from outcome_receipts.models import Figure

# The receipt fields re-derivation compares. ``computed_at`` is excluded on
# purpose; see the module docstring.
_CHECKED_FIELDS = ("value", "slice_hash", "row_count", "value_sql", "unit", "display")


@dataclass(frozen=True)
class Check:
    """The verification outcome for one receipt in the manifest."""

    metric_id: str
    ok: bool
    detail: str


@dataclass(frozen=True)
class VerifyResult:
    """Every per-receipt check, plus whether the manifest verified as a whole."""

    checks: tuple[Check, ...]

    @property
    def ok(self) -> bool:
        return all(check.ok for check in self.checks)

    @property
    def n_ok(self) -> int:
        return sum(1 for check in self.checks if check.ok)


def _recomputed_fields(figure: Figure) -> dict[str, Any]:
    receipt = figure.receipt
    return {
        "value": receipt.value,
        "slice_hash": receipt.slice_hash,
        "row_count": receipt.row_count,
        "value_sql": receipt.value_sql,
        "unit": receipt.unit,
        "display": figure.display,
    }


def _compare(stored: Mapping[str, Any], recomputed: Mapping[str, Any]) -> list[str]:
    drifts: list[str] = []
    for field in _CHECKED_FIELDS:
        want = recomputed[field]
        got = stored.get(field)
        if got != want:
            drifts.append(f"{field}: manifest {got!r} != re-derived {want!r}")
    return drifts


def verify_manifest(
    figures: Sequence[Figure], manifest: Mapping[str, Any]
) -> VerifyResult:
    """Check each manifest receipt against the figure re-derived from the data.

    Every receipt must re-derive to a figure with the same value, slice hash, row
    count, query, unit, and display. A receipt with no matching figure, or a figure
    with no receipt, is reported as a failure so the two sets must agree exactly.
    """

    by_id = {figure.metric_id: figure for figure in figures}
    receipts = manifest.get("receipts", [])
    checks: list[Check] = []
    seen: set[str] = set()
    for stored in receipts:
        metric_id = str(stored.get("metric_id", ""))
        seen.add(metric_id)
        figure = by_id.get(metric_id)
        if figure is None:
            checks.append(
                Check(metric_id, False, "no figure re-derives for this receipt")
            )
            continue
        drifts = _compare(stored, _recomputed_fields(figure))
        if drifts:
            checks.append(Check(metric_id, False, "; ".join(drifts)))
        else:
            checks.append(Check(metric_id, True, "re-derived, matches"))
    for metric_id in sorted(by_id):
        if metric_id not in seen:
            checks.append(
                Check(metric_id, False, "figure has no receipt in the manifest")
            )
    return VerifyResult(tuple(checks))
