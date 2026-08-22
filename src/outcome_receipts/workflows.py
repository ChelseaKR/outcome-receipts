"""Deterministic evidence workflows built on verified aggregate receipts.

These workflows extend the report trust chain without creating a second source of
program numbers. Row-backed figures are computed by the metric engine. Derived
figures, such as a restatement delta or partner rollup, are computed by SQLite
over verified receipt values and are labeled ``receipt_composed`` so they cannot
be mistaken for row-backed receipts.

Every builder is pure with respect to its output: it validates all inputs and
returns a complete JSON-compatible artifact, or raises :class:`WorkflowError`.
The CLI writes the artifact only after the builder succeeds, preserving the
project's fail-closed rule.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from outcome_receipts.bundle import verify_bundle as verify_sealed_bundle
from outcome_receipts.clock import FixedClock, SystemClock
from outcome_receipts.comparison import compute_comparison, compute_reconciliation
from outcome_receipts.config import load_spec
from outcome_receipts.diff import diff_manifests
from outcome_receipts.engine import compute_figures, read_csv_meta
from outcome_receipts.models import EMPTY_SLICE_HASH, REDACTED_DISPLAY, Figure
from outcome_receipts.report import receipts_manifest
from outcome_receipts.suppression import suppress_figures
from outcome_receipts.verify import verify_bundle

WORKFLOW_SCHEMA_VERSION = "1.0"
_SUPPRESSED = REDACTED_DISPLAY

# The interpretation limit added to an equity review whose groups include a
# withheld cell. This artifact exists to let a reviewer look at small groups, so
# it is the artifact most likely to be read by someone who will otherwise take a
# withheld group for an empty one.
_SUPPRESSION_LIMIT = (
    "One or more groups are withheld under the small-cell suppression policy. "
    "A withheld group carries suppressed: true and a null value; it is not a "
    "count of zero and must not be read, plotted, or summed as one."
)


class WorkflowError(ValueError):
    """A workflow input or trust gate failed and no artifact may be written."""


def _is_suppressed(receipt: Mapping[str, Any]) -> bool:
    """True if a manifest receipt is a withheld cell.

    Either signal is sufficient. ``suppressed`` is the field a schema-2.0
    manifest declares; the ``display`` sentinel is what a 1.0 manifest carried
    and is still what a reader sees. Accepting either is the fail-closed
    direction: a workflow that composes, rolls up, or scores a withheld cell is
    the failure this guards, so a receipt that looks withheld by any signal is
    treated as withheld.
    """

    return receipt.get("suppressed") is True or receipt.get("display") == _SUPPRESSED


@dataclass(frozen=True)
class VerifiedBundle:
    """A bundle whose seal, artifacts, grounding, and receipts all verify."""

    directory: Path
    manifest: dict[str, Any]
    figures: tuple[Figure, ...]
    digest: str


@dataclass(frozen=True)
class WorkflowCheck:
    """One structural or integrity check over a workflow artifact."""

    scope: str
    ok: bool
    detail: str


@dataclass(frozen=True)
class WorkflowVerifyResult:
    """The complete fail-closed verification result for a workflow artifact."""

    checks: tuple[WorkflowCheck, ...]

    @property
    def ok(self) -> bool:
        return all(check.ok for check in self.checks)


_KIND_RELATIONSHIPS = {
    "restatement": "supersedes",
    "migration_equivalence": "compares_to",
    "requirement_change": "compares_to",
    "contract_evidence": "supports_contract",
    "federated_rollup": "rolls_up",
    "equity_review": "slices",
}
_KIND_FIELDS: dict[str, tuple[tuple[str, type], ...]] = {
    "restatement": (
        ("reason", str),
        ("approved_by", str),
        ("current_spec_digest", str),
        ("current_manifest_digest", str),
        ("changed", list),
        ("added", list),
        ("removed", list),
        ("unchanged", list),
    ),
    "migration_equivalence": (
        ("approved_by", str),
        ("before_spec_digest", str),
        ("after_spec_digest", str),
        ("metrics", list),
    ),
    "requirement_change": (
        ("prior_document_digest", str),
        ("current_document_digest", str),
        ("requirements", list),
    ),
    "contract_evidence": (
        ("contract_id", str),
        ("contract_digest", str),
        ("controlling_text", str),
        ("policy_citation", str),
        ("approved_by", str),
        ("milestones", list),
        ("legal_determination", str),
    ),
    "federated_rollup": (
        ("plan_digest", str),
        ("period", str),
        ("population_overlap", str),
        ("suppression_policy_id", str),
        ("approved_by", str),
        ("inputs", list),
        ("rollup_receipt", dict),
    ),
    "equity_review": (
        ("spec_digest", str),
        ("plan_digest", str),
        ("dimension", str),
        ("purpose", str),
        ("controlling_policy", str),
        ("consent_basis", str),
        ("category_provenance", str),
        ("approved_by", str),
        ("groups", list),
        ("interpretation_limits", list),
    ),
}
_FORBIDDEN_ARTIFACT_KEYS = frozenset(
    {
        "client_id",
        "client_identifier",
        "client_rows",
        "source_rows",
        "raw_records",
        "records",
        "rows",
        "clients",
        "participants",
        "people",
        "client_data",
        "raw_data",
    }
)
# The migration-equivalence status vocabulary. ``indeterminate`` is the same word
# ``contract_evidence`` uses for the same reason -- a receipted comparison the
# suppression policy makes impossible -- so a consumer reading two artifacts does
# not have to learn two words for one meaning. It is published in
# docs/schema/workflow-artifact.schema.json and described in docs/NOVEL-USE-CASES.md.
MIGRATION_STATUSES = frozenset({"equivalent", "changed", "indeterminate"})

_COMPOSED_QUERIES = {
    "sum": "SELECT SUM(value) FROM receipt_inputs",
    "delta": (
        "SELECT "
        "(SELECT value FROM receipt_inputs WHERE position = 1) - "
        "(SELECT value FROM receipt_inputs WHERE position = 0)"
    ),
}


def _canonical_digest(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.blake2b(raw.encode("utf-8"), digest_size=32).hexdigest()


def _file_digest(path: Path) -> str:
    return hashlib.blake2b(path.read_bytes(), digest_size=32).hexdigest()


def _valid_digest(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _walk(value: object, path: str = "$") -> Sequence[tuple[str, object]]:
    nodes: list[tuple[str, object]] = [(path, value)]
    if isinstance(value, dict):
        for key, child in value.items():
            nodes.extend(_walk(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            nodes.extend(_walk(child, f"{path}[{index}]"))
    return nodes


def _envelope_checks(artifact: Mapping[str, Any]) -> list[WorkflowCheck]:
    checks: list[WorkflowCheck] = []
    version = artifact.get("schema_version")
    checks.append(
        WorkflowCheck(
            "schema_version",
            version == WORKFLOW_SCHEMA_VERSION,
            (
                "schema version matches"
                if version == WORKFLOW_SCHEMA_VERSION
                else f"unsupported schema version {version!r}"
            ),
        )
    )
    kind = artifact.get("kind")
    checks.append(
        WorkflowCheck(
            "kind",
            kind in _KIND_RELATIONSHIPS,
            "known workflow kind" if kind in _KIND_RELATIONSHIPS else f"unknown kind {kind!r}",
        )
    )
    if not isinstance(kind, str) or kind not in _KIND_RELATIONSHIPS:
        return checks

    relationship = artifact.get("relationship")
    expected = _KIND_RELATIONSHIPS[kind]
    actual = relationship.get("type") if isinstance(relationship, dict) else None
    checks.append(
        WorkflowCheck(
            "relationship",
            actual == expected,
            "relationship matches kind" if actual == expected else f"expected {expected!r}",
        )
    )
    for field, expected_type in _KIND_FIELDS[kind]:
        value = artifact.get(field)
        ok = isinstance(value, expected_type)
        if expected_type is str:
            ok = ok and bool(str(value).strip())
        checks.append(
            WorkflowCheck(
                field,
                ok,
                f"{field} is present"
                if ok
                else f"{field} must be a non-empty {expected_type.__name__}",
            )
        )
    return checks


def _digest_checks(artifact: Mapping[str, Any]) -> list[WorkflowCheck]:
    checks: list[WorkflowCheck] = []
    for path, value in _walk(artifact):
        field = path.rsplit(".", maxsplit=1)[-1]
        if field.endswith("_digest") or field in {"bundle_digest", "receipt_digest"}:
            if value is None and field in {"prior_text_digest", "current_text_digest"}:
                continue
            ok = _valid_digest(value)
            checks.append(
                WorkflowCheck(
                    path,
                    ok,
                    "digest is canonical" if ok else "digest must be 64 lowercase hex characters",
                )
            )
    return checks


def _privacy_checks(artifact: Mapping[str, Any]) -> list[WorkflowCheck]:
    offenders = [
        path
        for path, value in _walk(artifact)
        if isinstance(value, dict) and _FORBIDDEN_ARTIFACT_KEYS.intersection(value)
    ]
    return [
        WorkflowCheck(
            "aggregate_only",
            not offenders,
            "no client-level fields" if not offenders else f"client-level fields at {offenders}",
        )
    ]


# The receipt fields a withheld cell must not carry a number in. ``value`` is
# the one a consumer plots or sums; ``row_count`` is the same number again for an
# ordinary count metric; ``slice_hash`` is a content hash of the exact withheld
# rows, comparable against a guessed row set to confirm a guess.
_WITHHELD_RECEIPT_FIELDS = ("value", "row_count", "slice_hash")


def _suppression_checks(artifact: Mapping[str, Any]) -> list[WorkflowCheck]:
    """No embedded receipt may declare itself withheld and still carry the number.

    A workflow artifact embeds manifest receipts verbatim, so this is the last
    gate before a consumer interprets one. It asserts the absence of the unsafe
    outcome rather than the presence of a label: a receipt with
    ``suppressed: true`` whose ``value``, ``row_count``, or ``slice_hash`` is not
    ``null`` is a protected cell published beside its own redaction marker, which
    is worse than either state alone. An artifact produced by this package cannot
    reach that shape; one that was hand-edited, or produced by a build that
    zeroed the fields instead of withholding them, can.
    """

    offenders: list[str] = []
    for path, value in _walk(artifact):
        if not isinstance(value, dict) or value.get("suppressed") is not True:
            continue
        published = [field for field in _WITHHELD_RECEIPT_FIELDS if value.get(field) is not None]
        if published:
            offenders.append(f"{path} ({', '.join(published)})")
    return [
        WorkflowCheck(
            "suppression",
            not offenders,
            "no withheld receipt carries a number"
            if not offenders
            else f"withheld receipts still carry numbers at {offenders}",
        )
    ]


def _composed_check(path: str, receipt: Mapping[str, Any]) -> WorkflowCheck:
    required = {
        "metric_id",
        "operation",
        "query",
        "inputs",
        "input_digest",
        "value",
        "display",
        "unit",
        "computed_at",
    }
    inputs = receipt.get("inputs")
    missing = sorted(required - receipt.keys())
    digest_ok = isinstance(inputs, list) and receipt.get("input_digest") == _canonical_digest(
        inputs
    )
    operation = receipt.get("operation")
    operation_ok = operation in _COMPOSED_QUERIES and receipt.get("query") == (
        _COMPOSED_QUERIES.get(str(operation))
    )
    if operation == "delta":
        operation_ok = operation_ok and isinstance(inputs, list) and len(inputs) == 2
    value = receipt.get("value")
    value_ok = isinstance(value, (int, float)) and not isinstance(value, bool)
    ok = (
        receipt.get("provenance_type") == "receipt_composed"
        and not missing
        and isinstance(inputs, list)
        and bool(inputs)
        and digest_ok
        and operation_ok
        and value_ok
    )
    detail = (
        "receipt-composed provenance and input digest verify"
        if ok
        else f"invalid receipt-composed record; missing={missing}, digest_ok={digest_ok}"
    )
    return WorkflowCheck(path, ok, detail)


def _composed_checks(artifact: Mapping[str, Any]) -> list[WorkflowCheck]:
    return [
        _composed_check(path, value)
        for path, value in _walk(artifact)
        if isinstance(value, dict) and value.get("provenance_type") == "receipt_composed"
    ]


def _records_valid(
    value: object,
    *,
    required: frozenset[str],
    status_field: str | None = None,
    statuses: frozenset[str] = frozenset(),
) -> bool:
    if not isinstance(value, list):
        return False
    for record in value:
        if not isinstance(record, dict) or not required.issubset(record):
            return False
        if status_field is not None and record.get(status_field) not in statuses:
            return False
    return True


def _collection_check(
    scope: str,
    value: object,
    *,
    required: frozenset[str],
    status_field: str | None = None,
    statuses: frozenset[str] = frozenset(),
) -> WorkflowCheck:
    ok = _records_valid(
        value,
        required=required,
        status_field=status_field,
        statuses=statuses,
    )
    return WorkflowCheck(
        scope,
        ok,
        f"{scope} records are valid" if ok else f"{scope} records are incomplete or invalid",
    )


def _semantic_checks(artifact: Mapping[str, Any]) -> list[WorkflowCheck]:
    kind = artifact.get("kind")
    checks: list[WorkflowCheck] = []
    if kind == "restatement":
        checks.append(
            _collection_check(
                "changed",
                artifact.get("changed"),
                required=frozenset({"metric_id", "prior", "current", "reasons"}),
            )
        )
    elif kind == "migration_equivalence":
        checks.append(
            _collection_check(
                "metrics",
                artifact.get("metrics"),
                required=frozenset({"metric_id", "status", "before", "after"}),
                status_field="status",
                statuses=MIGRATION_STATUSES,
            )
        )
        checks.append(_migration_delta_check(artifact.get("metrics")))
    elif kind == "requirement_change":
        checks.append(
            _collection_check(
                "requirements",
                artifact.get("requirements"),
                required=frozenset(
                    {
                        "requirement_id",
                        "status",
                        "prior_text_digest",
                        "current_text_digest",
                        "review_status",
                    }
                ),
                status_field="status",
                statuses=frozenset({"unchanged", "definition_changed", "added", "removed"}),
            )
        )
    elif kind == "contract_evidence":
        checks.append(
            WorkflowCheck(
                "legal_determination",
                artifact.get("legal_determination") == "not_made",
                "no legal determination is made",
            )
        )
        milestones = artifact.get("milestones")
        checks.append(
            WorkflowCheck(
                "milestones",
                isinstance(milestones, list) and bool(milestones),
                "at least one milestone is present",
            )
        )
        checks.append(
            _collection_check(
                "milestones",
                milestones,
                required=frozenset(
                    {
                        "milestone_id",
                        "status",
                        "comparison",
                        "observed",
                        "threshold",
                        "financial",
                    }
                ),
                status_field="status",
                statuses=frozenset({"met", "unmet", "indeterminate"}),
            )
        )
    elif kind == "federated_rollup":
        inputs = artifact.get("inputs")
        checks.append(
            WorkflowCheck(
                "inputs",
                isinstance(inputs, list) and len(inputs) >= 2,
                "at least two partner inputs are present",
            )
        )
        checks.append(
            _collection_check(
                "inputs",
                inputs,
                required=frozenset({"partner", "bundle_digest"}),
            )
        )
        checks.append(
            WorkflowCheck(
                "population_overlap",
                artifact.get("population_overlap") in {"disjoint", "not_deduplicated"},
                "population overlap declaration is supported",
            )
        )
    elif kind == "equity_review":
        groups = artifact.get("groups")
        checks.append(
            WorkflowCheck(
                "groups",
                isinstance(groups, list) and len(groups) >= 2,
                "at least two allowlisted groups are present",
            )
        )
        checks.append(
            _collection_check(
                "groups",
                groups,
                required=frozenset({"label", "receipt"}),
            )
        )
        checks.append(_equity_suppression_limit_check(artifact, groups))
    return checks


def _migration_delta_check(metrics: object) -> WorkflowCheck:
    """Each migration metric carries a delta receipt exactly when it can.

    Both directions matter. A comparable metric without a delta receipt is an
    equivalence claim with nothing behind it. An ``indeterminate`` metric *with*
    one is worse: it would be a composed number derived from a cell neither side
    publishes, presented beside a status saying no comparison was possible.
    """

    if not isinstance(metrics, list):
        return WorkflowCheck("delta_receipt", False, "metrics are not a list")
    offenders: list[str] = []
    for record in metrics:
        if not isinstance(record, dict):
            return WorkflowCheck("delta_receipt", False, "a metric record is not an object")
        metric_id = str(record.get("metric_id", "?"))
        has_delta = isinstance(record.get("delta_receipt"), dict)
        if record.get("status") == "indeterminate":
            if has_delta:
                offenders.append(f"{metric_id} is indeterminate but carries a delta receipt")
            if record.get("delta_status") != "suppressed":
                offenders.append(f"{metric_id} is indeterminate without a stated reason")
        elif not has_delta:
            offenders.append(f"{metric_id} is comparable but carries no delta receipt")
    return WorkflowCheck(
        "delta_receipt",
        not offenders,
        "every metric's delta receipt matches its status"
        if not offenders
        else "; ".join(offenders),
    )


def _equity_suppression_limit_check(artifact: Mapping[str, Any], groups: object) -> WorkflowCheck:
    """An equity review with a withheld group must say so in its limits.

    This artifact is read by people looking for exactly the small groups
    suppression hides, so an unlabelled withheld group is the one most likely to
    be read as an empty one. If any group's receipt is withheld, the artifact has
    to carry the suppression interpretation limit; a reader must not have to
    notice it themselves.
    """

    if not isinstance(groups, list):
        return WorkflowCheck("interpretation_limits", False, "groups are not a list")
    withheld = [
        group
        for group in groups
        if isinstance(group, dict)
        and isinstance(group.get("receipt"), dict)
        and _is_suppressed(group["receipt"])
    ]
    limits = artifact.get("interpretation_limits")
    stated = isinstance(limits, list) and _SUPPRESSION_LIMIT in limits
    ok = not withheld or stated
    return WorkflowCheck(
        "interpretation_limits",
        ok,
        "suppression is stated as an interpretation limit"
        if ok
        else "a group is withheld but no suppression interpretation limit is stated",
    )


def verify_workflow_artifact(artifact: Mapping[str, Any]) -> WorkflowVerifyResult:
    """Verify a versioned workflow artifact without trusting its producer.

    This verifier is intentionally structural. Row-backed figures remain subject
    to ``receipts verify`` against their source data, and rollup source bundles
    remain subject to ``load_verified_bundle``. Here the compatibility contract,
    typed relationship, digest syntax, aggregate-only boundary, and any composed
    receipt's input digest are checked so an older artifact can be accepted or
    rejected before a consumer interprets it.
    """

    checks = [
        *_envelope_checks(artifact),
        *_digest_checks(artifact),
        *_privacy_checks(artifact),
        *_suppression_checks(artifact),
        *_composed_checks(artifact),
        *_semantic_checks(artifact),
    ]
    return WorkflowVerifyResult(tuple(checks))


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WorkflowError(f"{path}: cannot read a JSON object: {exc}") from exc
    if not isinstance(value, dict):
        raise WorkflowError(f"{path}: expected a JSON object")
    return value


def _required_text(value: object, *, field: str) -> str:
    text = str(value).strip() if value is not None else ""
    if not text:
        raise WorkflowError(f"{field} is required")
    return text


def _required_number(value: object, *, field: str) -> float:
    """A receipt numeric field that must be present, mirroring `_required_text`.

    A missing key and an explicit `None` both read as `None` through
    `Mapping.get`, and both fail closed the same way here: neither is a `0.0`
    the disjointness gate below may safely reason about.
    """

    if value is None:
        raise WorkflowError(f"{field} is required")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise WorkflowError(f"{field} must be numeric")
    return float(value)


def _bundle_members(directory: Path) -> dict[str, bytes]:
    return {
        path.relative_to(directory).as_posix(): path.read_bytes()
        for path in sorted(directory.rglob("*"))
        if path.is_file() and path != directory / "bundle.json"
    }


def _compute_publishable(config_path: Path, *, reproducible: bool) -> tuple[Figure, ...]:
    spec = load_spec(config_path)
    table = read_csv_meta(spec.data_path)
    clock = FixedClock() if reproducible else SystemClock()
    figures = compute_figures(
        table.rows,
        spec.report.metrics,
        clock=clock,
        data_checks=spec.report.data_checks,
    )
    if spec.report.comparison is not None:
        comparison = compute_comparison(table.rows, spec.report.comparison, clock=clock)
        figures.extend(comparison.figures)
    if spec.report.reconciliation is not None:
        reconciliation = compute_reconciliation(table.rows, spec.report.reconciliation, clock=clock)
        figures.extend(reconciliation.figures)
    publishable, suppression = suppress_figures(figures)
    if not suppression.ok or not suppression.aggregate_only:
        raise WorkflowError("privacy suppression did not produce an aggregate-only safe result")
    return tuple(publishable)


def _manifest(figures: Sequence[Figure]) -> dict[str, Any]:
    value = json.loads(receipts_manifest(figures))
    if not isinstance(value, dict):
        raise WorkflowError("internal manifest renderer returned a non-object")
    return value


def _receipt_index(manifest: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    receipts = manifest.get("receipts")
    if not isinstance(receipts, list):
        raise WorkflowError("manifest receipts must be a list")
    index: dict[str, dict[str, Any]] = {}
    for position, value in enumerate(receipts):
        if not isinstance(value, dict):
            raise WorkflowError(f"manifest receipt {position} must be an object")
        metric_id = _required_text(value.get("metric_id"), field=f"receipt {position} metric_id")
        if metric_id in index:
            raise WorkflowError(f"duplicate metric_id in manifest: {metric_id}")
        index[metric_id] = dict(value)
    return index


def load_verified_bundle(
    config_path: Path, bundle_dir: Path, *, reproducible: bool
) -> VerifiedBundle:
    """Recompute, suppress, and verify one complete export bundle."""

    figures = _compute_publishable(config_path, reproducible=reproducible)
    result = verify_bundle(bundle_dir, figures)
    if not result.ok:
        raise WorkflowError(f"{bundle_dir}: receipt, artifact, or grounding verification failed")

    seal_path = bundle_dir / "bundle.json"
    seal = _read_object(seal_path)
    seal_result = verify_sealed_bundle(_bundle_members(bundle_dir), seal)
    if not seal_result.ok:
        raise WorkflowError(f"{bundle_dir}: bundle seal verification failed")

    manifest = _read_object(bundle_dir / "receipts.json")
    _receipt_index(manifest)
    provenance = manifest.get("provenance")
    if not isinstance(provenance, dict) or not str(provenance.get("approved_by", "")).strip():
        raise WorkflowError(f"{bundle_dir}: bundle has no named human approval")
    digest = _required_text(seal.get("bundle_digest"), field="bundle_digest")
    return VerifiedBundle(bundle_dir, manifest, figures, digest)


def _display(value: float, unit: str, template: str) -> str:
    decimals = 0
    if "." in template:
        decimals = len(template.rstrip("%").split(".", maxsplit=1)[1].replace(",", ""))
    if unit == "percent":
        return f"{value:.{decimals}f}%"
    if unit == "money":
        return f"${value:,.{decimals}f}"
    if unit == "duration":
        return f"{value:,.{decimals}f} days"
    if unit == "count" and decimals == 0:
        return f"{round(value):,}"
    return f"{value:,.{decimals}f}"


def _composed_receipt(
    *,
    metric_id: str,
    operation: str,
    inputs: Sequence[Mapping[str, Any]],
    reproducible: bool,
) -> dict[str, Any]:
    if not inputs:
        raise WorkflowError(f"{metric_id}: a composed receipt needs at least one input")
    units = {_required_text(item.get("unit"), field=f"{metric_id} input unit") for item in inputs}
    if len(units) != 1:
        raise WorkflowError(f"{metric_id}: composed receipt units do not match")
    if any(_is_suppressed(item) for item in inputs):
        raise WorkflowError(f"{metric_id}: a suppressed input cannot be composed")

    values = [float(item["value"]) for item in inputs]
    conn = sqlite3.connect(":memory:")
    try:
        conn.execute("CREATE TABLE receipt_inputs (position INTEGER, value REAL)")
        conn.executemany(
            "INSERT INTO receipt_inputs VALUES (?, ?)",
            list(enumerate(values)),
        )
        if operation not in _COMPOSED_QUERIES or (operation == "delta" and len(values) != 2):
            raise WorkflowError(f"{metric_id}: unsupported composed operation {operation!r}")
        query = _COMPOSED_QUERIES[operation]
        value = float(conn.execute(query).fetchone()[0])
    finally:
        conn.close()

    input_records = [
        {
            "metric_id": item.get("metric_id"),
            "receipt_digest": _canonical_digest(item),
        }
        for item in inputs
    ]
    unit = units.pop()
    clock = FixedClock() if reproducible else SystemClock()
    return {
        "provenance_type": "receipt_composed",
        "metric_id": metric_id,
        "operation": operation,
        "query": query,
        "inputs": input_records,
        "input_digest": _canonical_digest(input_records),
        "value": value,
        "display": _display(value, unit, str(inputs[0].get("display", ""))),
        "unit": unit,
        "computed_at": clock.now_iso(),
    }


def build_restatement(
    *,
    prior_config: Path,
    prior_bundle: Path,
    current_config: Path,
    reason: str,
    approved_by: str,
    reproducible: bool,
) -> dict[str, Any]:
    """Build a non-destructive restatement linked to a verified prior bundle."""

    reason = _required_text(reason, field="reason")
    approved_by = _required_text(approved_by, field="approved_by")
    prior = load_verified_bundle(prior_config, prior_bundle, reproducible=reproducible)
    current_figures = _compute_publishable(current_config, reproducible=reproducible)
    current_manifest = _manifest(current_figures)
    changes = diff_manifests(prior.manifest, current_manifest)

    changed: list[dict[str, Any]] = []
    for item in changes.changed:
        if item.prior is None or item.current is None:
            raise WorkflowError(f"{item.metric_id}: changed receipt is incomplete")
        record: dict[str, Any] = {
            "metric_id": item.metric_id,
            "prior": item.prior,
            "current": item.current,
            "reasons": list(item.reasons),
        }
        if not _is_suppressed(item.prior) and not _is_suppressed(item.current):
            record["delta_receipt"] = _composed_receipt(
                metric_id=f"{item.metric_id}__restatement_delta",
                operation="delta",
                inputs=(item.prior, item.current),
                reproducible=reproducible,
            )
        else:
            record["delta_status"] = "suppressed"
        changed.append(record)

    return {
        "schema_version": WORKFLOW_SCHEMA_VERSION,
        "kind": "restatement",
        "relationship": {"type": "supersedes", "bundle_digest": prior.digest},
        "current_spec_digest": _file_digest(current_config),
        "current_manifest_digest": _canonical_digest(current_manifest),
        "reason": reason,
        "approved_by": approved_by,
        "changed": changed,
        "added": list(changes.added),
        "removed": list(changes.removed),
        "unchanged": list(changes.unchanged),
    }


def build_migration_check(
    *,
    before_config: Path,
    after_config: Path,
    approved_by: str,
    reproducible: bool,
) -> dict[str, Any]:
    """Compare two reviewed source-specific specs without inferring equivalence."""

    approved_by = _required_text(approved_by, field="approved_by")
    before_manifest = _manifest(_compute_publishable(before_config, reproducible=reproducible))
    after_manifest = _manifest(_compute_publishable(after_config, reproducible=reproducible))
    before = _receipt_index(before_manifest)
    after = _receipt_index(after_manifest)
    if before.keys() != after.keys():
        raise WorkflowError("migration metric IDs differ; equivalence is blocked")

    metrics: list[dict[str, Any]] = []
    for metric_id in sorted(before):
        left = before[metric_id]
        right = after[metric_id]
        for field in ("definition", "unit", "kind"):
            if left.get(field) != right.get(field):
                raise WorkflowError(f"{metric_id}: {field} differs; equivalence is blocked")
        record: dict[str, Any] = {"metric_id": metric_id, "before": left, "after": right}
        if _is_suppressed(left) or _is_suppressed(right):
            # Classify, do not abort. A withheld cell cannot be compared: its
            # value is not published on either side, so neither equivalence nor
            # change can be asserted about it. Two withheld cells would compare
            # equal on their nulls, which is worse than saying nothing -- it
            # would assert an equivalence nobody can see. The sibling workflows
            # already do this (`contract-check` returns `indeterminate`,
            # `restate` returns `delta_status: "suppressed"`), and aborting the
            # whole artifact instead meant one small cell anywhere in a spec
            # reported nothing about the metrics that *could* be compared.
            record["status"] = "indeterminate"
            record["delta_status"] = "suppressed"
        else:
            record["status"] = (
                "equivalent" if left.get("value") == right.get("value") else "changed"
            )
            record["delta_receipt"] = _composed_receipt(
                metric_id=f"{metric_id}__migration_delta",
                operation="delta",
                inputs=(left, right),
                reproducible=reproducible,
            )
        metrics.append(record)
    return {
        "schema_version": WORKFLOW_SCHEMA_VERSION,
        "kind": "migration_equivalence",
        "relationship": {"type": "compares_to"},
        "before_spec_digest": _file_digest(before_config),
        "after_spec_digest": _file_digest(after_config),
        "approved_by": approved_by,
        "metrics": metrics,
    }


def _requirements(path: Path) -> dict[str, dict[str, Any]]:
    payload = _read_object(path)
    values = payload.get("requirements")
    if not isinstance(values, list):
        raise WorkflowError(f"{path}: requirements must be a list")
    index: dict[str, dict[str, Any]] = {}
    for position, value in enumerate(values):
        if not isinstance(value, dict):
            raise WorkflowError(f"{path}: requirement {position} must be an object")
        requirement_id = _required_text(
            value.get("requirement_id", value.get("metric_id")),
            field=f"{path} requirement {position} stable ID",
        )
        if requirement_id in index:
            raise WorkflowError(f"{path}: duplicate requirement ID {requirement_id}")
        index[requirement_id] = dict(value)
    return index


def build_requirement_change(prior_path: Path, current_path: Path) -> dict[str, Any]:
    """Diff requirement documents by stable ID and canonical text hash."""

    prior = _requirements(prior_path)
    current = _requirements(current_path)
    records: list[dict[str, Any]] = []
    for requirement_id in sorted(prior.keys() | current.keys()):
        before = prior.get(requirement_id)
        after = current.get(requirement_id)
        if before is None:
            status = "added"
        elif after is None:
            status = "removed"
        elif _canonical_digest(before) == _canonical_digest(after):
            status = "unchanged"
        else:
            status = "definition_changed"
        records.append(
            {
                "requirement_id": requirement_id,
                "status": status,
                "prior_text_digest": _canonical_digest(before) if before is not None else None,
                "current_text_digest": _canonical_digest(after) if after is not None else None,
                "review_status": "required" if status == "definition_changed" else "not_required",
            }
        )
    return {
        "schema_version": WORKFLOW_SCHEMA_VERSION,
        "kind": "requirement_change",
        "relationship": {"type": "compares_to"},
        "prior_document_digest": _file_digest(prior_path),
        "current_document_digest": _file_digest(current_path),
        "requirements": records,
    }


def build_contract_evidence(
    *,
    config_path: Path,
    contract_path: Path,
    approved_by: str,
    reproducible: bool,
) -> dict[str, Any]:
    """Evaluate operator-authored milestone comparisons over receipted metrics."""

    approved_by = _required_text(approved_by, field="approved_by")
    contract = _read_object(contract_path)
    contract_id = _required_text(contract.get("contract_id"), field="contract_id")
    controlling_text = _required_text(contract.get("controlling_text"), field="controlling_text")
    policy_citation = _required_text(contract.get("policy_citation"), field="policy_citation")
    milestones = contract.get("milestones")
    if not isinstance(milestones, list) or not milestones:
        raise WorkflowError("milestones must be a non-empty list")

    figures = _receipt_index(
        _manifest(_compute_publishable(config_path, reproducible=reproducible))
    )
    records: list[dict[str, Any]] = []
    operators = {
        "gte": lambda observed, threshold: observed >= threshold,
        "lte": lambda observed, threshold: observed <= threshold,
        "eq": lambda observed, threshold: observed == threshold,
    }
    for position, milestone in enumerate(milestones):
        if not isinstance(milestone, dict):
            raise WorkflowError(f"milestone {position} must be an object")
        milestone_id = _required_text(
            milestone.get("milestone_id"), field=f"milestone {position} ID"
        )
        observed_id = _required_text(
            milestone.get("observed_metric_id"), field=f"{milestone_id} observed_metric_id"
        )
        threshold_id = _required_text(
            milestone.get("threshold_metric_id"), field=f"{milestone_id} threshold_metric_id"
        )
        financial_id = _required_text(
            milestone.get("financial_metric_id"), field=f"{milestone_id} financial_metric_id"
        )
        operator = _required_text(milestone.get("comparison"), field=f"{milestone_id} comparison")
        if operator not in operators:
            raise WorkflowError(f"{milestone_id}: unsupported comparison {operator!r}")
        try:
            observed = figures[observed_id]
            threshold = figures[threshold_id]
            financial = figures[financial_id]
        except KeyError as exc:
            raise WorkflowError(f"{milestone_id}: metric {exc.args[0]!r} is missing") from exc
        if observed["unit"] != threshold["unit"]:
            raise WorkflowError(f"{milestone_id}: observed and threshold units differ")
        for label, receipt in (
            ("observed", observed),
            ("threshold", threshold),
            ("financial", financial),
        ):
            _required_text(receipt.get("definition"), field=f"{milestone_id} {label} definition")
        if any(_is_suppressed(receipt) for receipt in (observed, threshold, financial)):
            status = "indeterminate"
        else:
            comparison = operators[operator](float(observed["value"]), float(threshold["value"]))
            status = "met" if comparison else "unmet"
        records.append(
            {
                "milestone_id": milestone_id,
                "status": status,
                "comparison": operator,
                "observed": observed,
                "threshold": threshold,
                "financial": financial,
            }
        )
    return {
        "schema_version": WORKFLOW_SCHEMA_VERSION,
        "kind": "contract_evidence",
        "relationship": {"type": "supports_contract"},
        "contract_id": contract_id,
        "contract_digest": _file_digest(contract_path),
        "controlling_text": controlling_text,
        "policy_citation": policy_citation,
        "approved_by": approved_by,
        "milestones": records,
        "legal_determination": "not_made",
    }


def _resolve_plan_path(plan_path: Path, value: object, *, field: str) -> Path:
    text = _required_text(value, field=field)
    candidate = Path(text)
    return candidate if candidate.is_absolute() else plan_path.parent / candidate


def _rollup_input(
    plan_path: Path,
    item: object,
    *,
    position: int,
    period: str,
    policy_id: str,
    reproducible: bool,
) -> tuple[str, str, dict[str, Any]]:
    if not isinstance(item, dict):
        raise WorkflowError(f"rollup input {position} must be an object")
    config = _resolve_plan_path(plan_path, item.get("config"), field="rollup input config")
    bundle_dir = _resolve_plan_path(plan_path, item.get("bundle"), field="rollup input bundle")
    metric_id = _required_text(item.get("metric_id"), field="rollup input metric_id")
    partner = _required_text(item.get("partner"), field="rollup input partner")
    input_period = _required_text(item.get("period"), field=f"{partner} period")
    input_policy = _required_text(
        item.get("suppression_policy_id"), field=f"{partner} suppression_policy_id"
    )
    if input_period != period:
        raise WorkflowError(f"{partner}: period does not match the rollup period")
    if input_policy != policy_id:
        raise WorkflowError(f"{partner}: suppression policy does not match the rollup policy")
    verified = load_verified_bundle(config, bundle_dir, reproducible=reproducible)
    receipt = _receipt_index(verified.manifest).get(metric_id)
    if receipt is None:
        raise WorkflowError(f"{partner}: metric {metric_id!r} is missing")
    if receipt.get("unit") != "count":
        raise WorkflowError(f"{partner}: only count metrics can be rolled up")
    if _is_suppressed(receipt):
        raise WorkflowError(f"{partner}: suppressed metrics cannot be rolled up")
    return partner, verified.digest, receipt


def _slice_collision_names(first: tuple[str, str], second: tuple[str, str]) -> tuple[str, str]:
    """Name the two colliding inputs, distinguishing one partner from itself.

    One organization can appear twice in a plan under two different bundles (two
    programs, one client list). The bundle digests differ, so the duplicate-digest
    check does not fire, and naming the partner alone would report "alpha and
    alpha", which tells the operator nothing about which two submissions to open.
    The bundle digest is the identifier that separates them. Names are sorted so
    the message does not depend on the order the plan lists the inputs.
    """

    if first[0] == second[0]:
        labels = sorted(f"{name} (bundle {digest})" for name, digest in (first, second))
    else:
        labels = sorted((first[0], second[0]))
    return labels[0], labels[1]


def _record_disjoint_slice(
    slices: dict[str, tuple[str, str]],
    *,
    partner: str,
    digest: str,
    receipt: Mapping[str, Any],
) -> None:
    """Fail closed when a partner receipt cannot support a ``disjoint`` plan.

    A slice hash is a content hash of the exact rows a figure was computed from,
    so two partner receipts carrying the same non-empty slice hash counted the
    same people. Summing both double counts them, and the plan declared the
    populations disjoint, so the declaration is contradicted by evidence the
    partners already published. The lead agency reaches that conclusion without
    ever holding a client row: the hashes are enough.

    This is the one duplicate-client case the tool can decide on its own. Every
    other overlap stays what the plan says it is, an operator declaration, so a
    plan labeled ``not_deduplicated`` is left alone: it has already told the
    reader the combined figure counts some people more than once.

    The exemption for an empty slice is keyed on what the receipt reports, not on
    the hash. A slice with zero rows hashes to ``EMPTY_SLICE_HASH`` no matter
    whose data produced it, so two partners both reporting a true zero are not a
    collision. But that sentinel is also what a receipt carries when its value was
    computed over rows its slice query does not return, and such a receipt would
    otherwise skip the gate while contributing a non-zero count to the sum: the
    hash it publishes cannot be compared with any other partner's. A receipt that
    reports a non-zero count over an empty slice is therefore refused rather than
    exempted. See ``docs/adr/0004-fail-closed-disjoint-rollup-slice-check.md``.

    ``slice_hash``, ``value``, and ``row_count`` are required, not defaulted. This
    function runs only after the caller already rejected an explicitly withheld
    receipt (``_is_suppressed``), so a receipt reaching here that is still missing
    one of these fields is malformed or foreign, not suppressed. The old code
    defaulted a missing field to ``""``/``0.0``/``0``, which is exactly the shape
    of a genuine empty-slice zero -- so a receipt with, say, no ``slice_hash`` key
    at all sailed through as "verified empty" and was silently exempted from the
    one duplicate-client check this function exists to run, while its count still
    entered the rollup sum.
    """

    slice_hash = _required_text(receipt.get("slice_hash"), field=f"{partner} slice_hash")
    value = _required_number(receipt.get("value"), field=f"{partner} value")
    row_count = int(_required_number(receipt.get("row_count"), field=f"{partner} row_count"))
    if slice_hash == EMPTY_SLICE_HASH:
        if value != 0.0 or row_count != 0:
            raise WorkflowError(
                f"{partner}: a non-zero count over an empty data slice carries no evidence "
                "of a disjoint population"
            )
        return
    other = slices.get(slice_hash)
    if other is not None:
        first, second = _slice_collision_names(other, (partner, digest))
        raise WorkflowError(
            f"{first} and {second}: identical data slices cannot be a disjoint population"
        )
    slices[slice_hash] = (partner, digest)


def build_rollup(*, plan_path: Path, approved_by: str, reproducible: bool) -> dict[str, Any]:
    """Compose count receipts from independently verified partner bundles."""

    approved_by = _required_text(approved_by, field="approved_by")
    plan = _read_object(plan_path)
    overlap = _required_text(plan.get("population_overlap"), field="population_overlap")
    if overlap not in {"disjoint", "not_deduplicated"}:
        raise WorkflowError("population_overlap must be 'disjoint' or 'not_deduplicated'")
    period = _required_text(plan.get("period"), field="period")
    policy_id = _required_text(plan.get("suppression_policy_id"), field="suppression_policy_id")
    inputs = plan.get("inputs")
    if not isinstance(inputs, list) or len(inputs) < 2:
        raise WorkflowError("rollup inputs must contain at least two partner bundles")

    grouped: dict[str, list[dict[str, Any]]] = {}
    bundle_refs: list[dict[str, str]] = []
    seen_digests: set[str] = set()
    disjoint_slices: dict[str, tuple[str, str]] = {}
    for position, item in enumerate(inputs):
        partner, digest, receipt = _rollup_input(
            plan_path,
            item,
            position=position,
            period=period,
            policy_id=policy_id,
            reproducible=reproducible,
        )
        if digest in seen_digests:
            raise WorkflowError(f"duplicate partner bundle digest: {digest}")
        seen_digests.add(digest)
        if overlap == "disjoint":
            _record_disjoint_slice(disjoint_slices, partner=partner, digest=digest, receipt=receipt)
        metric_id = str(receipt["metric_id"])
        grouped.setdefault(metric_id, []).append(receipt)
        bundle_refs.append({"partner": partner, "bundle_digest": digest})

    if len(grouped) != 1:
        raise WorkflowError("all rollup inputs must name the same metric_id")
    metric_id, receipts = next(iter(grouped.items()))
    definitions = {str(receipt.get("definition", "")) for receipt in receipts}
    if len(definitions) != 1 or not next(iter(definitions)):
        raise WorkflowError(f"{metric_id}: partner definitions do not match")
    receipts = sorted(receipts, key=_canonical_digest)
    composed = _composed_receipt(
        metric_id=f"{metric_id}__rollup",
        operation="sum",
        inputs=receipts,
        reproducible=reproducible,
    )
    value = float(composed["value"])
    if 1 <= abs(value) < 11:
        raise WorkflowError(f"{metric_id}: rollup result is a protected small cell")

    return {
        "schema_version": WORKFLOW_SCHEMA_VERSION,
        "kind": "federated_rollup",
        "relationship": {"type": "rolls_up"},
        "plan_digest": _file_digest(plan_path),
        "period": period,
        "population_overlap": overlap,
        "suppression_policy_id": policy_id,
        "approved_by": approved_by,
        "inputs": sorted(bundle_refs, key=lambda item: (item["partner"], item["bundle_digest"])),
        "rollup_receipt": composed,
    }


def build_equity_review(
    *,
    config_path: Path,
    plan_path: Path,
    approved_by: str,
    reproducible: bool,
) -> dict[str, Any]:
    """Package an allowlisted, already-suppressed set of subgroup receipts."""

    approved_by = _required_text(approved_by, field="approved_by")
    plan = _read_object(plan_path)
    purpose = _required_text(plan.get("purpose"), field="purpose")
    policy = _required_text(plan.get("controlling_policy"), field="controlling_policy")
    consent = _required_text(plan.get("consent_basis"), field="consent_basis")
    provenance = _required_text(plan.get("category_provenance"), field="category_provenance")
    dimension = _required_text(plan.get("dimension"), field="dimension")
    groups = plan.get("groups")
    if not isinstance(groups, list) or len(groups) < 2:
        raise WorkflowError("equity review groups must contain at least two allowlisted groups")

    figures = _receipt_index(
        _manifest(_compute_publishable(config_path, reproducible=reproducible))
    )
    records: list[dict[str, Any]] = []
    seen_labels: set[str] = set()
    units: set[str] = set()
    for position, item in enumerate(groups):
        if not isinstance(item, dict):
            raise WorkflowError(f"equity group {position} must be an object")
        label = _required_text(item.get("label"), field=f"equity group {position} label")
        metric_id = _required_text(
            item.get("metric_id"), field=f"equity group {position} metric_id"
        )
        if label in seen_labels:
            raise WorkflowError(f"duplicate equity group label: {label}")
        seen_labels.add(label)
        receipt = figures.get(metric_id)
        if receipt is None:
            raise WorkflowError(f"equity group {label}: metric {metric_id!r} is missing")
        units.add(str(receipt.get("unit", "")))
        records.append({"label": label, "receipt": receipt})
    if len(units) != 1:
        raise WorkflowError("equity group units do not match")

    limits = [
        "No group ranking is produced.",
        "No causal or fairness conclusion is produced.",
    ]
    if any(_is_suppressed(record["receipt"]) for record in records):
        limits.append(_SUPPRESSION_LIMIT)

    return {
        "schema_version": WORKFLOW_SCHEMA_VERSION,
        "kind": "equity_review",
        "relationship": {"type": "slices"},
        "spec_digest": _file_digest(config_path),
        "plan_digest": _file_digest(plan_path),
        "dimension": dimension,
        "purpose": purpose,
        "controlling_policy": policy,
        "consent_basis": consent,
        "category_provenance": provenance,
        "approved_by": approved_by,
        "groups": records,
        "interpretation_limits": limits,
    }


def write_artifact(path: Path, artifact: Mapping[str, Any]) -> None:
    """Write one already-validated workflow artifact."""

    path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")


__all__ = (
    "MIGRATION_STATUSES",
    "WORKFLOW_SCHEMA_VERSION",
    "WorkflowCheck",
    "WorkflowError",
    "WorkflowVerifyResult",
    "build_contract_evidence",
    "build_equity_review",
    "build_migration_check",
    "build_requirement_change",
    "build_restatement",
    "build_rollup",
    "load_verified_bundle",
    "verify_workflow_artifact",
    "write_artifact",
)
