"""Deterministic schema mapping that always routes candidates to human review."""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path

_ALIASES: dict[str, tuple[str, ...]] = {
    "client_id": ("clientid", "personalid", "participantid", "personid", "uniqueidentifier"),
    "enrolled_date": ("enrolleddate", "entrydate", "projectstartdate", "startdate"),
    "exit_date": ("exitdate", "projectexitdate", "enddate"),
    "exit_destination": ("exitdestination", "destination", "destinationat exit"),
    "program": ("program", "project", "projectname", "programname"),
}
_AGGREGATIONS = {"count_rows", "count_distinct"}


def _normalize(name: str) -> str:
    return "".join(char for char in name.casefold() if char.isalnum())


def _quote_identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _quote_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


@dataclass(frozen=True)
class FieldMatch:
    logical_field: str
    source_column: str
    confidence: float
    basis: str


@dataclass(frozen=True)
class MappingCandidate:
    metric_id: str
    status: str
    confidence: float
    field_matches: tuple[FieldMatch, ...]
    metric_spec: dict[str, object] | None
    blockers: tuple[str, ...] = ()
    decision: str = "pending"


@dataclass(frozen=True)
class MappingQueue:
    source: str
    columns: tuple[str, ...]
    candidates: tuple[MappingCandidate, ...]
    requires_human_review: bool = True

    @property
    def ok(self) -> bool:
        return all(candidate.status == "review_required" for candidate in self.candidates)

    def payload(self) -> dict[str, object]:
        payload = asdict(self)
        payload["ok"] = self.ok
        return payload


def _columns(path: Path) -> tuple[str, ...]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        row = next(csv.reader(handle), None)
    if not row:
        raise ValueError(f"{path}: no header row")
    columns = tuple(name.strip() for name in row)
    if any(not name for name in columns) or len(set(columns)) != len(columns):
        raise ValueError(f"{path}: headers must be non-empty and unique")
    return columns


def _match_field(logical: str, columns: tuple[str, ...]) -> tuple[FieldMatch | None, str | None]:
    wanted = _normalize(logical)
    normalized = {column: _normalize(column) for column in columns}
    exact = [column for column, value in normalized.items() if value == wanted]
    aliases = {_normalize(alias) for alias in _ALIASES.get(logical, ())}
    matches = exact or [column for column, value in normalized.items() if value in aliases]
    if not matches:
        return None, f"no source column matches logical field {logical!r}"
    if len(matches) > 1:
        return None, f"ambiguous source columns for {logical!r}: {', '.join(matches)}"
    basis = "canonical_name" if exact else "known_alias"
    confidence = 1.0 if exact else 0.9
    return FieldMatch(logical, matches[0], confidence, basis), None


def _requirement_fields(
    requirement: dict[str, object], aggregation: str
) -> tuple[str, list[dict[str, object]], list[str], list[str]]:
    blockers: list[str] = []
    fields: list[str] = []
    source_field = str(requirement.get("field", "")).strip()
    if aggregation == "count_distinct":
        if source_field:
            fields.append(source_field)
        else:
            blockers.append("count_distinct requires field")
    raw_filters = requirement.get("filters", [])
    if not isinstance(raw_filters, list):
        return source_field, [], fields, [*blockers, "filters must be a list"]
    filters: list[dict[str, object]] = []
    for item in raw_filters:
        if (
            not isinstance(item, dict)
            or not str(item.get("field", "")).strip()
            or "equals" not in item
        ):
            blockers.append("each filter requires field and equals")
            continue
        filters.append(item)
        fields.append(str(item["field"]).strip())
    return source_field, filters, fields, blockers


def _map_fields(
    logical_fields: list[str], columns: tuple[str, ...]
) -> tuple[list[FieldMatch], dict[str, str], list[str]]:
    matches: list[FieldMatch] = []
    by_logical: dict[str, str] = {}
    blockers: list[str] = []
    for logical in dict.fromkeys(logical_fields):
        match, blocker = _match_field(logical, columns)
        if blocker:
            blockers.append(blocker)
        elif match:
            matches.append(match)
            by_logical[logical] = match.source_column
    return matches, by_logical, blockers


def _candidate(requirement: dict[str, object], columns: tuple[str, ...]) -> MappingCandidate:
    metric_id = str(requirement.get("metric_id", "")).strip()
    aggregation = str(requirement.get("aggregation", "")).strip()
    blockers: list[str] = []
    if not metric_id:
        blockers.append("metric_id is required")
    if aggregation not in _AGGREGATIONS:
        blockers.append(f"unsupported aggregation {aggregation!r}")

    source_field, filters, logical_fields, field_blockers = _requirement_fields(
        requirement, aggregation
    )
    blockers.extend(field_blockers)
    matches, by_logical, field_blockers = _map_fields(logical_fields, columns)
    blockers.extend(field_blockers)

    if blockers:
        return MappingCandidate(metric_id, "blocked", 0.0, tuple(matches), None, tuple(blockers))

    predicates = [
        f"{_quote_identifier(by_logical[str(item['field']).strip()])} = "
        f"{_quote_literal(str(item.get('equals', '')))}"
        for item in filters
    ]
    where = f" WHERE {' AND '.join(predicates)}" if predicates else ""
    if aggregation == "count_distinct":
        value_sql = (
            f"SELECT COUNT(DISTINCT {_quote_identifier(by_logical[source_field])}) "  # noqa: S608  https://github.com/ChelseaKR/outcome-receipts/issues/52
            f"FROM data{where}"
        )
    else:
        value_sql = f"SELECT COUNT(*) FROM data{where}"  # noqa: S608  https://github.com/ChelseaKR/outcome-receipts/issues/52
    spec: dict[str, object] = {
        "metric_id": metric_id,
        "description": str(requirement.get("description", "")).strip(),
        "definition": str(requirement.get("definition", "")).strip(),
        "unit": str(requirement.get("unit", "count")).strip(),
        "decimals": int(str(requirement.get("decimals", 0))),
        "value_sql": value_sql,
        "slice_sql": f"SELECT * FROM data{where}",  # noqa: S608  https://github.com/ChelseaKR/outcome-receipts/issues/52
    }
    confidence = min((match.confidence for match in matches), default=1.0)
    return MappingCandidate(metric_id, "review_required", confidence, tuple(matches), spec)


def build_mapping_queue(data_path: Path, requirements_path: Path) -> MappingQueue:
    """Map logical requirement fields to headers without reading or exporting rows."""

    document = json.loads(requirements_path.read_text(encoding="utf-8"))
    requirements = document.get("requirements") if isinstance(document, dict) else None
    if not isinstance(requirements, list) or not requirements:
        raise ValueError("requirements JSON must contain a non-empty requirements list")
    columns = _columns(data_path)
    candidates = tuple(
        _candidate(item, columns)
        if isinstance(item, dict)
        else MappingCandidate("", "blocked", 0.0, (), None, ("requirement must be an object",))
        for item in requirements
    )
    return MappingQueue(str(data_path), columns, candidates)
