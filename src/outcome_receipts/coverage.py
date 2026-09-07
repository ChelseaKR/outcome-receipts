"""Prove the export answers the bound requirement set, or says why it cannot.

The project proves every published number traces to a receipt. It did not prove
every *required* number was published. Those are the two halves of one claim,
and the second is the one an auditor checks first.

``receipts map`` produced per-requirement candidates that can come back
``blocked``, ``requirements-diff`` compared two requirement documents by stable
id, and ``contract-check`` refused a milestone whose metric was absent. Nothing
connected a requirement set to an export, so a spec that simply omitted a
required metric ran, grounded, was approved, and exported a report that was
fully receipted and silently incomplete.

That is this portfolio's dominant defect shape at the document level. A
requirement nobody could answer and a requirement nobody was asked about
rendered identically -- as nothing on the page -- which is the same error as a
suppressed cell rendering as a zero, one level up. ADR 0009 refuses that error
inside a figure; this refuses it for the report as a whole.

Four states, kept distinguishable:

``answered``
    A metric names this requirement and its figure was published with a receipt.
``withheld``
    A metric names this requirement, the figure exists, and small-cell
    suppression withheld it. Answered, and reads as unanswered nowhere.
``unanswerable``
    No metric answers it, and the spec carries **both** the machine-readable
    blocker ``mapping.build_mapping_queue`` produces for it *and* a reason a
    person wrote. The blocker is re-derived here and must match, so the field
    cannot be used to wave a requirement away.
``unanswered``
    Anything else. Export refuses, writes nothing, and names the requirement.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from outcome_receipts.mapping import build_mapping_queue
from outcome_receipts.models import Figure, RequirementsSpec, UnanswerableRequirement

#: Versioned separately from the receipts manifest so a consumer can tell a
#: coverage record it understands from one it does not, without inferring it
#: from the presence of a key.
COVERAGE_SCHEMA_VERSION = "1.0"

STATUS_ANSWERED = "answered"
STATUS_WITHHELD = "withheld"
STATUS_UNANSWERABLE = "unanswerable"
STATUS_UNANSWERED = "unanswered"

#: The statuses an export may carry. `unanswered` is deliberately absent.
EXPORTABLE_STATUSES = frozenset({STATUS_ANSWERED, STATUS_WITHHELD, STATUS_UNANSWERABLE})


class CoverageError(ValueError):
    """Raised when a requirement binding is unusable, before anything is written."""


@dataclass(frozen=True)
class RequirementRecord:
    """One requirement's coverage, as it rides in the manifest and the report."""

    requirement_id: str
    description: str
    status: str
    metric_id: str | None
    blocker: str | None
    reason: str | None
    detail: str

    def payload(self) -> dict[str, Any]:
        return {
            "blocker": self.blocker,
            "description": self.description,
            "detail": self.detail,
            "metric_id": self.metric_id,
            "reason": self.reason,
            "requirement_id": self.requirement_id,
            "status": self.status,
        }


@dataclass(frozen=True)
class RequirementCoverage:
    """The whole coverage record for one export."""

    document_path: str
    document_digest: str
    records: tuple[RequirementRecord, ...]

    @property
    def ok(self) -> bool:
        return all(record.status in EXPORTABLE_STATUSES for record in self.records)

    @property
    def unanswered(self) -> tuple[RequirementRecord, ...]:
        return tuple(record for record in self.records if record.status == STATUS_UNANSWERED)

    def counts(self) -> dict[str, int]:
        """Every status, including the ones at zero.

        Reported rather than derived by the reader from a list they may have
        filtered. A status missing from a count table and a status counted at
        zero are different claims.
        """
        counted = {
            STATUS_ANSWERED: 0,
            STATUS_WITHHELD: 0,
            STATUS_UNANSWERABLE: 0,
            STATUS_UNANSWERED: 0,
        }
        for record in self.records:
            counted[record.status] += 1
        return counted

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": COVERAGE_SCHEMA_VERSION,
            "document_path": self.document_path,
            "document_sha256": self.document_digest,
            "counts": self.counts(),
            "requirements": [record.payload() for record in self.records],
        }


def document_digest(path: Path) -> str:
    """The sha256 of the requirement document's bytes, exactly as read."""

    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _requirement_id(entry: Mapping[str, Any], position: int, path: Path) -> str:
    """The stable id, under the same rule ``workflows._requirements`` uses.

    A document keyed only by ``metric_id`` is the shape `receipts map` reads, so
    both spellings resolve here rather than making the author maintain two
    documents that must agree.
    """

    raw = entry.get("requirement_id", entry.get("metric_id"))
    if not isinstance(raw, str) or not raw.strip():
        raise CoverageError(f"{path}: requirement {position} has no stable requirement_id")
    return raw.strip()


def read_requirements(path: Path) -> tuple[tuple[str, dict[str, Any]], ...]:
    """Read the requirement document in document order, ids resolved.

    Order is the document's own, not sorted: a funder's requirement set is a
    numbered list and the coverage table is read against it.
    """

    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CoverageError(f"{path}: requirement document could not be read: {error}") from error
    values = payload.get("requirements") if isinstance(payload, dict) else None
    if not isinstance(values, list) or not values:
        raise CoverageError(f"{path}: requirements must be a non-empty list")
    entries: list[tuple[str, dict[str, Any]]] = []
    seen: set[str] = set()
    for position, value in enumerate(values):
        if not isinstance(value, dict):
            raise CoverageError(f"{path}: requirement {position} must be an object")
        requirement_id = _requirement_id(value, position, Path(path))
        if requirement_id in seen:
            raise CoverageError(f"{path}: duplicate requirement id {requirement_id!r}")
        seen.add(requirement_id)
        entries.append((requirement_id, dict(value)))
    return tuple(entries)


def _metrics_by_requirement(
    metric_requirements: Mapping[str, str],
    declared: Sequence[str],
    path: Path,
) -> dict[str, str]:
    """Invert metric -> requirement, refusing an ambiguous or dangling binding."""

    by_requirement: dict[str, str] = {}
    known = set(declared)
    for metric_id, requirement_id in sorted(metric_requirements.items()):
        if requirement_id not in known:
            raise CoverageError(
                f"metric {metric_id!r} names requirement {requirement_id!r}, "
                f"which {path} does not declare"
            )
        if requirement_id in by_requirement:
            raise CoverageError(
                f"requirement {requirement_id!r} is claimed by two metrics: "
                f"{by_requirement[requirement_id]!r} and {metric_id!r}"
            )
        by_requirement[requirement_id] = metric_id
    return by_requirement


def _declarations(
    unanswerable: Sequence[UnanswerableRequirement],
    declared: Sequence[str],
    answered_by: Mapping[str, str],
    path: Path,
) -> dict[str, UnanswerableRequirement]:
    by_id: dict[str, UnanswerableRequirement] = {}
    known = set(declared)
    for entry in unanswerable:
        if entry.requirement_id not in known:
            raise CoverageError(
                f"[[requirements.unanswerable]] names requirement "
                f"{entry.requirement_id!r}, which {path} does not declare"
            )
        if entry.requirement_id in by_id:
            raise CoverageError(
                f"requirement {entry.requirement_id!r} is declared unanswerable twice"
            )
        if entry.requirement_id in answered_by:
            # A contradiction the reader could not see. Preferring one silently
            # would let a spec carry a signed "we could not answer this" beside
            # a metric that answers it, and whichever the tool ignored would
            # still be in the file for a person to read.
            raise CoverageError(
                f"requirement {entry.requirement_id!r} is declared unanswerable and "
                f"answered by metric {answered_by[entry.requirement_id]!r}"
            )
        by_id[entry.requirement_id] = entry
    return by_id


def _produced_blockers(
    data_path: Path,
    requirements_path: Path,
    entries: Sequence[tuple[str, dict[str, Any]]],
) -> dict[str, tuple[str, ...]]:
    """What ``receipts map`` actually says is wrong with each requirement.

    Candidates come back in document order, so they are zipped positionally
    rather than joined on ``metric_id`` -- a requirement keyed only by
    ``requirement_id`` produces a candidate whose ``metric_id`` is empty, and
    joining on it would silently pair the wrong rows.
    """

    queue = build_mapping_queue(data_path, requirements_path)
    if len(queue.candidates) != len(entries):
        raise CoverageError(
            f"{requirements_path}: the mapping queue returned "
            f"{len(queue.candidates)} candidates for {len(entries)} requirements"
        )
    return {
        requirement_id: candidate.blockers
        for (requirement_id, _entry), candidate in zip(entries, queue.candidates, strict=True)
    }


def _description(entry: Mapping[str, Any], requirement_id: str) -> str:
    raw = entry.get("description", entry.get("definition", ""))
    return str(raw).strip() or requirement_id


def _answered_record(
    requirement_id: str,
    description: str,
    metric_id: str,
    figure: Figure | None,
) -> RequirementRecord:
    if figure is None:
        return RequirementRecord(
            requirement_id=requirement_id,
            description=description,
            status=STATUS_UNANSWERED,
            metric_id=metric_id,
            blocker=None,
            reason=None,
            detail=(
                f"metric {metric_id!r} names this requirement but produced no "
                "figure in the published set"
            ),
        )
    if figure.receipt.suppressed:
        return RequirementRecord(
            requirement_id=requirement_id,
            description=description,
            status=STATUS_WITHHELD,
            metric_id=metric_id,
            blocker=None,
            reason=None,
            detail=(
                f"answered by metric {metric_id!r}; the cell is withheld by the "
                "small-cell suppression policy and its value is null, not zero"
            ),
        )
    return RequirementRecord(
        requirement_id=requirement_id,
        description=description,
        status=STATUS_ANSWERED,
        metric_id=metric_id,
        blocker=None,
        reason=None,
        detail=f"answered by metric {metric_id!r} with a receipt",
    )


def _unanswerable_record(
    requirement_id: str,
    description: str,
    declaration: UnanswerableRequirement,
    produced: tuple[str, ...],
) -> RequirementRecord:
    """A declaration is only accepted when the tool agrees with its blocker.

    Three outcomes, not two. The blocker is one `map` produces (accepted); the
    blocker is not one `map` produces (refused, and the record says what `map`
    did say); or the declaration is missing a half (refused). "The operator
    typed something in the blocker field" is not a measurement of anything.
    """

    if not declaration.blocker.strip() or not declaration.reason.strip():
        return RequirementRecord(
            requirement_id=requirement_id,
            description=description,
            status=STATUS_UNANSWERED,
            metric_id=None,
            blocker=declaration.blocker or None,
            reason=declaration.reason or None,
            detail=(
                "an unanswerable declaration needs both a blocker `map` produces "
                "and a reason a person wrote; one of them is empty"
            ),
        )
    if declaration.blocker not in produced:
        produced_text = "; ".join(produced) if produced else "nothing — it maps cleanly"
        return RequirementRecord(
            requirement_id=requirement_id,
            description=description,
            status=STATUS_UNANSWERED,
            metric_id=None,
            blocker=declaration.blocker,
            reason=declaration.reason,
            detail=(
                f"the declared blocker is not one `map` produces for this "
                f"requirement. `map` reports: {produced_text}"
            ),
        )
    return RequirementRecord(
        requirement_id=requirement_id,
        description=description,
        status=STATUS_UNANSWERABLE,
        metric_id=None,
        blocker=declaration.blocker,
        reason=declaration.reason,
        detail="declared unanswerable; the blocker was reproduced by `map`",
    )


def build_requirement_coverage(
    *,
    requirements: RequirementsSpec,
    requirements_path: Path,
    data_path: Path,
    metric_requirements: Mapping[str, str],
    figures: Sequence[Figure],
) -> RequirementCoverage:
    """Bind a requirement document to a computed figure set.

    ``metric_requirements`` maps metric id to the requirement id its spec names.
    ``figures`` is the *published* set, after suppression, because that is what
    the report actually carries -- grading coverage against the raw set would
    report a withheld cell as answered.
    """

    requirements_path = Path(requirements_path)
    entries = read_requirements(requirements_path)
    declared = [requirement_id for requirement_id, _entry in entries]
    by_requirement = _metrics_by_requirement(metric_requirements, declared, requirements_path)
    declarations = _declarations(
        requirements.unanswerable, declared, by_requirement, requirements_path
    )
    figures_by_id = {figure.metric_id: figure for figure in figures}
    blockers = _produced_blockers(data_path, requirements_path, entries)

    records: list[RequirementRecord] = []
    for requirement_id, entry in entries:
        description = _description(entry, requirement_id)
        metric_id = by_requirement.get(requirement_id)
        if metric_id is not None:
            records.append(
                _answered_record(
                    requirement_id, description, metric_id, figures_by_id.get(metric_id)
                )
            )
            continue
        declaration = declarations.get(requirement_id)
        if declaration is None:
            records.append(
                RequirementRecord(
                    requirement_id=requirement_id,
                    description=description,
                    status=STATUS_UNANSWERED,
                    metric_id=None,
                    blocker=None,
                    reason=None,
                    detail="no metric names this requirement and nothing declares it unanswerable",
                )
            )
            continue
        records.append(
            _unanswerable_record(
                requirement_id,
                description,
                declaration,
                blockers.get(requirement_id, ()),
            )
        )
    return RequirementCoverage(
        document_path=requirements.path,
        document_digest=document_digest(requirements_path),
        records=tuple(records),
    )
