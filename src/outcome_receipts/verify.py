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

from outcome_receipts.models import (
    HASH_ALGORITHM,
    HASH_CANONICALIZATION,
    HASH_DIGEST_SIZE,
    SCHEMA_VERSION,
    Figure,
)

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


def _schema_checks(manifest: Mapping[str, Any]) -> list[Check]:
    """Version and hash-descriptor checks against the current constants.

    Run before any field re-derivation so a manifest written under a different
    schema fails with a named reason ("schema_version: manifest '0.9' != expected
    '1.0'") rather than as a wave of opaque per-receipt slice-hash drift. Each
    descriptor is checked only when the manifest carries it, so a pre-schema
    manifest (no ``schema_version``, no ``hash``) is not flagged here and falls
    through to plain re-derivation.
    """

    checks: list[Check] = []
    if "schema_version" in manifest:
        got = manifest["schema_version"]
        ok = got == SCHEMA_VERSION
        detail = (
            "schema_version matches"
            if ok
            else f"schema_version: manifest {got!r} != expected {SCHEMA_VERSION!r}"
        )
        checks.append(Check("schema_version", ok, detail))
    if "hash" in manifest:
        got_hash = manifest["hash"]
        expected = {
            "algorithm": HASH_ALGORITHM,
            "digest_size": HASH_DIGEST_SIZE,
            "canonicalization": HASH_CANONICALIZATION,
        }
        drifts = [
            f"{key}: manifest {got_hash.get(key)!r} != expected {want!r}"
            for key, want in expected.items()
            if got_hash.get(key) != want
        ]
        if drifts:
            checks.append(Check("hash", False, "hash descriptor drift — " + "; ".join(drifts)))
        else:
            checks.append(Check("hash", True, "hash descriptor matches"))
    return checks


def _compare(stored: Mapping[str, Any], recomputed: Mapping[str, Any]) -> list[str]:
    drifts: list[str] = []
    for field in _CHECKED_FIELDS:
        want = recomputed[field]
        got = stored.get(field)
        if got != want:
            drifts.append(f"{field}: manifest {got!r} != re-derived {want!r}")
    return drifts


def verify_manifest(figures: Sequence[Figure], manifest: Mapping[str, Any]) -> VerifyResult:
    """Check each manifest receipt against the figure re-derived from the data.

    Every receipt must re-derive to a figure with the same value, slice hash, row
    count, query, unit, and display. A receipt with no matching figure, or a figure
    with no receipt, is reported as a failure so the two sets must agree exactly.

    When the manifest carries a ``schema_version`` or ``hash`` descriptor, they are
    checked against the current constants first, so a manifest written under a
    different schema fails with a named version/descriptor reason before any
    per-receipt re-derivation is attempted.
    """

    by_id = {figure.metric_id: figure for figure in figures}
    receipts = manifest.get("receipts", [])
    checks: list[Check] = _schema_checks(manifest)
    seen: set[str] = set()
    for stored in receipts:
        metric_id = str(stored.get("metric_id", ""))
        seen.add(metric_id)
        figure = by_id.get(metric_id)
        if figure is None:
            checks.append(Check(metric_id, False, "no figure re-derives for this receipt"))
            continue
        drifts = _compare(stored, _recomputed_fields(figure))
        if drifts:
            checks.append(Check(metric_id, False, "; ".join(drifts)))
        else:
            checks.append(Check(metric_id, True, "re-derived, matches"))
    for metric_id in sorted(by_id):
        if metric_id not in seen:
            checks.append(Check(metric_id, False, "figure has no receipt in the manifest"))
    return VerifyResult(tuple(checks))
