"""Change accounting between two receipted runs.

Two receipts manifests, as emitted by :func:`outcome_receipts.report.receipts_manifest`,
are one reporting cycle apart. ``receipts diff`` compares them and reports which
figures moved, were added, or were removed, and *why* each one moved: the value
changed, the row count of the slice changed, the slice hash changed, or the query
that produced it changed.

This is a manifest-to-manifest comparison, distinct from the in-run period-over-period
comparison in :mod:`outcome_receipts.comparison`. It reads only the JSON manifests, so
it needs no data table or SQL engine, and is a pure function so it is trivially testable.

The ``computed_at`` timestamp is deliberately never a reason: it differs run to run by
design, so counting it would flag every re-run as a move while saying nothing about
whether a figure actually changed. This mirrors the field exclusion in
:mod:`outcome_receipts.verify`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FigureDelta:
    """Why one metric present in both manifests moved between the two runs.

    ``prior`` and ``current`` are the per-metric receipt dicts from each manifest.
    The four flags record which fields differ; ``reasons`` is a human-readable
    tuple describing each move (e.g. ``"value 42 -> 47"``, ``"slice hash changed"``).
    """

    metric_id: str
    prior: dict[str, Any] | None
    current: dict[str, Any] | None
    value_changed: bool
    row_count_changed: bool
    slice_hash_changed: bool
    query_changed: bool
    reasons: tuple[str, ...]

    @property
    def moved(self) -> bool:
        """Whether any tracked field differs between the two runs."""

        return (
            self.value_changed
            or self.row_count_changed
            or self.slice_hash_changed
            or self.query_changed
        )


@dataclass(frozen=True)
class ManifestDiff:
    """The full change accounting between a prior and a current manifest.

    ``added`` and ``removed`` carry the per-metric receipt dicts that appear in
    only one manifest. ``changed`` carries a :class:`FigureDelta` for each metric
    present in both whose tracked fields differ. ``unchanged`` names the metrics
    present in both that are identical (ignoring the timestamp).
    """

    added: tuple[dict[str, Any], ...]
    removed: tuple[dict[str, Any], ...]
    changed: tuple[FigureDelta, ...]
    unchanged: tuple[str, ...]


def _index_by_metric_id(manifest: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Index a manifest's ``receipts`` list by ``metric_id``.

    Missing keys are handled defensively: a manifest with no ``receipts`` yields an
    empty index, and a receipt with no ``metric_id`` is keyed by the empty string.
    """

    receipts = manifest.get("receipts", [])
    index: dict[str, dict[str, Any]] = {}
    for receipt in receipts:
        metric_id = str(receipt.get("metric_id", ""))
        index[metric_id] = dict(receipt)
    return index


def _delta(metric_id: str, prior: Mapping[str, Any], current: Mapping[str, Any]) -> FigureDelta:
    """Compare one metric's prior and current receipts into a :class:`FigureDelta`.

    ``value`` is compared exactly: the stored numbers are deterministic, so there is
    no tolerance. ``computed_at`` is never compared; see the module docstring.
    """

    value_changed = prior.get("value") != current.get("value")
    row_count_changed = prior.get("row_count") != current.get("row_count")
    slice_hash_changed = prior.get("slice_hash") != current.get("slice_hash")
    query_changed = prior.get("value_sql") != current.get("value_sql")

    reasons: list[str] = []
    if value_changed:
        reasons.append(f"value {prior.get('value')} -> {current.get('value')}")
    if row_count_changed:
        reasons.append(f"row count {prior.get('row_count')} -> {current.get('row_count')}")
    if slice_hash_changed:
        reasons.append("slice hash changed")
    if query_changed:
        reasons.append("query changed")

    return FigureDelta(
        metric_id=metric_id,
        prior=dict(prior),
        current=dict(current),
        value_changed=value_changed,
        row_count_changed=row_count_changed,
        slice_hash_changed=slice_hash_changed,
        query_changed=query_changed,
        reasons=tuple(reasons),
    )


def diff_manifests(prior: Mapping[str, Any], current: Mapping[str, Any]) -> ManifestDiff:
    """Classify every metric across two receipts manifests.

    Each manifest's ``receipts`` list is indexed by ``metric_id``. A metric present
    only in ``current`` is *added*; only in ``prior`` is *removed*. A metric in both
    is *changed* if its value, row count, slice hash, or query differs (with populated
    reasons), else *unchanged*. Value is compared exactly and the timestamp is ignored.
    """

    prior_index = _index_by_metric_id(prior)
    current_index = _index_by_metric_id(current)

    added: list[dict[str, Any]] = []
    removed: list[dict[str, Any]] = []
    changed: list[FigureDelta] = []
    unchanged: list[str] = []

    for metric_id in sorted(current_index):
        if metric_id not in prior_index:
            added.append(current_index[metric_id])

    for metric_id in sorted(prior_index):
        if metric_id not in current_index:
            removed.append(prior_index[metric_id])

    for metric_id in sorted(prior_index.keys() & current_index.keys()):
        delta = _delta(metric_id, prior_index[metric_id], current_index[metric_id])
        if delta.moved:
            changed.append(delta)
        else:
            unchanged.append(metric_id)

    return ManifestDiff(
        added=tuple(added),
        removed=tuple(removed),
        changed=tuple(changed),
        unchanged=tuple(unchanged),
    )


__all__: Sequence[str] = ("FigureDelta", "ManifestDiff", "diff_manifests")
