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

import hashlib
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from outcome_receipts.coverage import RequirementCoverage
from outcome_receipts.docx import (
    DOCX_NAME,
    Block,
    DocxError,
    DocxText,
    document_blocks,
    document_title,
    read_docx,
)
from outcome_receipts.grounding import ground
from outcome_receipts.models import (
    EMPTY_SLICE_HASH,
    HASH_ALGORITHM,
    HASH_CANONICALIZATION,
    HASH_DIGEST_SIZE,
    REDACTED_DISPLAY,
    SCHEMA_VERSION,
    SUPPORTED_SCHEMA_VERSIONS,
    ApprovalPolicy,
    Figure,
    GroundingResult,
)
from outcome_receipts.provenance import ApprovalError, resolve_approvals

# The receipt fields re-derivation compares. ``computed_at`` is excluded on
# purpose; see the module docstring.
_CHECKED_FIELDS = (
    "value",
    "slice_hash",
    "row_count",
    "value_sql",
    "unit",
    "display",
    "suppressed",
)

# The same list for a manifest written under schema 1.0, which had no
# ``suppressed`` field. Comparing it against a re-derived ``False``/``True``
# would report drift on every receipt of an older manifest and say nothing about
# whether the numbers still hold.
_CHECKED_FIELDS_V1 = tuple(field for field in _CHECKED_FIELDS if field != "suppressed")


#: What a :class:`Check` is about. ``"receipt"`` is one receipt re-derived from
#: the data. ``"manifest"`` is a descriptor of the document itself -- its declared
#: schema version, its hash descriptor -- which is compared against a constant and
#: is not re-derived from anything.
#:
#: The distinction used to go unrecorded, and everything downstream inherited the
#: conflation: a four-receipt manifest was reported as "receipts checked: 6
#: (re-derived 6)", and a manifest whose only failure was its declared version was
#: announced as "a receipt does not match the data" with ``drift 1`` pointing the
#: reader at data that was fine.
CheckKind = Literal["receipt", "manifest"]


@dataclass(frozen=True)
class Check:
    """The verification outcome for one check against the manifest.

    ``metric_id`` names a metric when ``kind`` is ``"receipt"``, and names the
    descriptor (``schema_version``, ``hash``) when ``kind`` is ``"manifest"``.
    """

    metric_id: str
    ok: bool
    detail: str
    kind: CheckKind = "receipt"


@dataclass(frozen=True)
class VerifyResult:
    """Every check run against the manifest, and whether it verified as a whole.

    ``checks`` holds both kinds in report order, manifest descriptors first.
    ``n_ok`` counts all of them; the receipt-only counts are the ones to quote as
    "how many receipts re-derived", because they are the only ones that did.
    """

    checks: tuple[Check, ...]

    @property
    def ok(self) -> bool:
        return all(check.ok for check in self.checks)

    @property
    def n_ok(self) -> int:
        """Every passing check, of both kinds. Not a count of receipts."""

        return sum(1 for check in self.checks if check.ok)

    @property
    def receipt_checks(self) -> tuple[Check, ...]:
        """The checks that re-derived a receipt from the data."""

        return tuple(check for check in self.checks if check.kind == "receipt")

    @property
    def manifest_checks(self) -> tuple[Check, ...]:
        """The checks against the manifest document's own descriptors."""

        return tuple(check for check in self.checks if check.kind == "manifest")

    @property
    def n_receipts_ok(self) -> int:
        """How many receipts re-derived. This is the number to report as such."""

        return sum(1 for check in self.receipt_checks if check.ok)

    @property
    def failed_receipts(self) -> tuple[Check, ...]:
        return tuple(check for check in self.receipt_checks if not check.ok)

    @property
    def failed_manifest_checks(self) -> tuple[Check, ...]:
        return tuple(check for check in self.manifest_checks if not check.ok)


def _recomputed_fields(figure: Figure, *, legacy: bool) -> dict[str, Any]:
    """The re-derived receipt fields, rendered as the stored receipt's schema wrote them.

    Schema 2.0 withholds a suppressed receipt's numerics as ``null``. Schema 1.0
    wrote zeros there (``value: 0.0``, ``row_count: 0``, the all-zero slice-hash
    sentinel) -- the defect that made a withheld cell indistinguishable from a
    true zero. A 1.0 manifest is still verifiable: with ``legacy`` set this
    reconstructs that rendering from the current figure, so the comparison
    answers "do the numbers still hold" rather than reporting the schema change
    as drift on every suppressed receipt. Nothing writes 1.0 any more.
    """

    receipt = figure.receipt
    fields: dict[str, Any] = {
        "value": receipt.value,
        "slice_hash": receipt.slice_hash,
        "row_count": receipt.row_count,
        "value_sql": receipt.value_sql,
        "unit": receipt.unit,
        "display": figure.display,
        "suppressed": receipt.suppressed,
    }
    if legacy and receipt.suppressed:
        fields["value"] = 0.0
        fields["row_count"] = 0
        fields["slice_hash"] = EMPTY_SLICE_HASH
    return fields


def _schema_checks(manifest: Mapping[str, Any]) -> list[Check]:
    """Version and hash-descriptor checks against the current constants.

    Reported first, so a manifest written under a different schema names its
    reason ("schema_version: manifest '0.9' is not one of ['1.0', '2.0']") at the
    top rather than leaving a reader to infer it from a wave of opaque
    per-receipt slice-hash drift below. Each descriptor is checked only when the
    manifest carries it, so a pre-schema manifest (no ``schema_version``, no
    ``hash``) is not flagged here and falls through to plain re-derivation.

    These are ``kind="manifest"`` checks: they are compared against a constant,
    not re-derived from the data, and counting them among the re-derived receipts
    overstated every verification by the number of descriptors present.
    """

    checks: list[Check] = []
    if "schema_version" in manifest:
        got = manifest["schema_version"]
        ok = got in SUPPORTED_SCHEMA_VERSIONS
        if not ok:
            detail = (
                f"schema_version: manifest {got!r} is not one of {list(SUPPORTED_SCHEMA_VERSIONS)}"
            )
        elif got == SCHEMA_VERSION:
            detail = "schema_version matches"
        else:
            detail = (
                f"schema_version {got!r} is supported for reading (current is {SCHEMA_VERSION!r})"
            )
        checks.append(Check("schema_version", ok, detail, kind="manifest"))
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
            checks.append(
                Check(
                    "hash",
                    False,
                    "hash descriptor drift — " + "; ".join(drifts),
                    kind="manifest",
                )
            )
        else:
            checks.append(Check("hash", True, "hash descriptor matches", kind="manifest"))
    return checks


def _compare(stored: Mapping[str, Any], figure: Figure) -> list[str]:
    """Field-by-field drift between one stored receipt and its re-derived figure.

    Which rendering to compare against is read off the stored receipt itself
    rather than off the manifest envelope: a 2.0 receipt declares ``suppressed``
    and a 1.0 receipt does not, so the presence of the key is exact for a
    well-formed manifest of either version, and a 2.0 manifest missing the key on
    one receipt is compared against the 1.0 rendering and reported as drift
    rather than waved through.
    """

    legacy = "suppressed" not in stored
    fields = _CHECKED_FIELDS_V1 if legacy else _CHECKED_FIELDS
    recomputed = _recomputed_fields(figure, legacy=legacy)
    drifts: list[str] = []
    for field in fields:
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
    checked against the current constants and reported first, so a manifest
    written under an unsupported schema names its reason at the top. Re-derivation
    still runs for every receipt underneath it — deliberately, and this docstring
    used to claim otherwise. Reporting both is what makes a refusal attributable:
    when the version fails and all the receipts re-derive, the reader can see that
    the document declared a contract nobody implements rather than that its data
    moved. A manifest written under an older but still supported schema is compared
    field-for-field as *that* schema wrote it, so a schema change is not reported
    as data drift; see ``_recomputed_fields``.
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
        drifts = _compare(stored, figure)
        if drifts:
            checks.append(Check(metric_id, False, "; ".join(drifts)))
        else:
            checks.append(Check(metric_id, True, "re-derived, matches"))
    for metric_id in sorted(by_id):
        if metric_id not in seen:
            checks.append(Check(metric_id, False, "figure has no receipt in the manifest"))
    return VerifyResult(tuple(checks))


@dataclass(frozen=True)
class ArtifactCheck:
    """The digest-match outcome for one sibling artifact of the bundle."""

    path: str
    ok: bool
    detail: str


@dataclass(frozen=True)
class CoverageCheck:
    """Whether the manifest's requirement coverage still holds.

    ``checked`` is false when neither the spec nor the manifest carries a
    requirement binding -- nothing was compared, which is a different fact from
    "the comparison passed". A verifier that reported ``ok`` for an unbound spec
    and ``ok`` for a bound one that matched would be saying the same word about
    two different situations.
    """

    checked: bool
    ok: bool
    detail: str


@dataclass(frozen=True)
class ApprovalCheck:
    """Whether the manifest's recorded sign-offs still satisfy the spec's policy.

    ``checked`` is false only when neither the spec declares an ``[approval]``
    policy nor the manifest records one, which is "there was nothing to compare"
    rather than "the comparison passed". The two are reported with different
    words for the same reason ``CoverageCheck`` does.
    """

    checked: bool
    ok: bool
    detail: str


@dataclass(frozen=True)
class DocumentCheck:
    """Whether ``report.docx`` says what ``report.md`` says, and its narrative grounds.

    ``checked`` is false only when the bundle holds no document export and the
    manifest attests none: nothing was compared, which is a different fact from
    "the comparison passed". ``grounding`` is the gate's result over the
    narrative read back out of the document's own bytes, and ``None`` when the
    document could not be read at all.
    """

    checked: bool
    ok: bool
    detail: str
    grounding: GroundingResult | None = None


@dataclass(frozen=True)
class BundleResult:
    """The whole-bundle verification: receipts, artifact digests, and grounding.

    ``manifest`` is the per-receipt re-derivation. ``artifacts`` is one check per
    file the manifest hashes (``report.md``, ``trace.html``, each chart SVG).
    ``grounding`` re-runs the gate over the exported narrative. ``coverage``
    re-derives the requirement coverage record and compares it, including the
    digest of the requirement document, so an edit to that document after export
    is caught. ``approval`` re-reads the spec's sign-off policy and checks the
    recorded approvals against it. ``document`` reads ``report.docx`` back out of
    its bytes, when the export wrote one, and holds it to ``report.md`` and to the
    gate. The bundle is ``ok`` only when all six hold, so any drift, swap,
    ungrounded number, moved requirement, sign-off that no longer satisfies the
    policy, or document that no longer says what its report says fails closed.
    """

    manifest: VerifyResult
    artifacts: tuple[ArtifactCheck, ...]
    grounding: GroundingResult
    coverage: CoverageCheck = CoverageCheck(False, True, "no requirement binding to check")
    approval: ApprovalCheck = ApprovalCheck(False, True, "no approval policy to check")
    document: DocumentCheck = DocumentCheck(False, True, "no document export to check")

    @property
    def ok(self) -> bool:
        return (
            self.manifest.ok
            and all(check.ok for check in self.artifacts)
            and self.grounding.ok
            and self.coverage.ok
            and self.approval.ok
            and self.document.ok
        )

    @property
    def failed_artifacts(self) -> tuple[ArtifactCheck, ...]:
        return tuple(check for check in self.artifacts if not check.ok)


def _report_narrative(report_text: str) -> str:
    """The drafted narrative extracted from an exported ``report.md``.

    The report is the title, then the narrative, then ``##`` sections (comparison,
    charts, provenance, receipts). Only the narrative is the drafted prose whose
    every number the gate must bind; the receipts and provenance sections carry
    row counts, hashes, and timestamps that are not figure displays. So the
    grounding re-check runs over the region from after the title up to the first
    ``##`` heading, mirroring what ``run`` grounded before it exported.
    """

    collected: list[str] = []
    for line in report_text.splitlines():
        if line.startswith("## "):
            break
        if line.startswith("# "):
            continue
        collected.append(line)
    return "\n".join(collected).strip()


def _check_artifacts(bundle_dir: Path, manifest: Mapping[str, Any]) -> tuple[ArtifactCheck, ...]:
    if "artifacts" not in manifest:
        return (
            ArtifactCheck(
                "receipts.json",
                False,
                "manifest has no 'artifacts' key; cannot verify the bundle",
            ),
        )
    artifacts = manifest["artifacts"]
    checks: list[ArtifactCheck] = []
    for rel_path, want in sorted(artifacts.items()):
        sibling = bundle_dir / rel_path
        if not sibling.is_file():
            checks.append(ArtifactCheck(rel_path, False, "artifact file is missing"))
            continue
        got = hashlib.sha256(sibling.read_bytes()).hexdigest()
        if got != want:
            checks.append(ArtifactCheck(rel_path, False, f"digest {got} != manifest {want}"))
        else:
            checks.append(ArtifactCheck(rel_path, True, "digest matches"))
    return tuple(checks)


def _check_coverage(
    manifest: Mapping[str, Any], coverage: RequirementCoverage | None
) -> CoverageCheck:
    """Compare the manifest's coverage record with a freshly derived one.

    Both directions are failures, and both are real. A manifest that records a
    binding the spec no longer declares was exported against a requirement set
    somebody has since removed. A spec that declares a binding the manifest does
    not carry was exported before the binding existed, and its report proves
    nothing about the requirement set now in force.
    """

    recorded = manifest.get("requirements")
    if recorded is None and coverage is None:
        return CoverageCheck(False, True, "no requirement binding to check")
    if recorded is None:
        return CoverageCheck(
            True,
            False,
            "the spec binds a requirement document but the manifest carries no coverage record",
        )
    if coverage is None:
        return CoverageCheck(
            True,
            False,
            "the manifest carries a coverage record but the spec binds no requirement document",
        )
    if not isinstance(recorded, Mapping):
        return CoverageCheck(True, False, "the manifest's requirements record is not an object")
    derived = coverage.payload()
    recorded_digest = recorded.get("document_sha256")
    if recorded_digest != derived["document_sha256"]:
        return CoverageCheck(
            True,
            False,
            f"requirement document sha256 {recorded_digest} does not match "
            f"{derived['document_sha256']} recomputed from {coverage.document_path}",
        )
    if dict(recorded) != derived:
        return CoverageCheck(
            True,
            False,
            "the coverage record does not match the coverage re-derived from the spec and data",
        )
    return CoverageCheck(True, True, f"coverage matches; document sha256 {recorded_digest}")


def _recorded_approvals(manifest: Mapping[str, Any]) -> list[tuple[str, str]] | None:
    """The ``role``/``approved_by`` pairs a manifest records, or ``None``.

    ``None`` means the manifest carries no ``approvals`` list at all. A list that
    is present but malformed returns an empty list instead, so a hand-edited
    record fails the policy comparison rather than being read as "no policy was
    in force" and skipping the check.
    """

    provenance = manifest.get("provenance")
    if not isinstance(provenance, Mapping):
        return None
    recorded = provenance.get("approvals")
    if recorded is None:
        return None
    if not isinstance(recorded, list):
        return []
    pairs: list[tuple[str, str]] = []
    for entry in recorded:
        if not isinstance(entry, Mapping):
            continue
        pairs.append((str(entry.get("role", "")), str(entry.get("approved_by", ""))))
    return pairs


def _check_approval(manifest: Mapping[str, Any], policy: ApprovalPolicy | None) -> ApprovalCheck:
    """Compare the manifest's recorded sign-offs with the spec's policy now.

    The policy is read from the spec, never from the manifest, for the reason the
    issue behind this check gives: a requirement that travels with the report
    definition cannot be satisfied by a different invocation. Both directions are
    failures. A manifest with no approvals against a spec that requires them was
    exported before the policy existed, so its report proves nothing about the
    policy in force. A manifest carrying approvals against a spec that declares
    none records a gate nothing now defines.
    """

    recorded = _recorded_approvals(manifest)
    if policy is None:
        if recorded is None:
            return ApprovalCheck(False, True, "no approval policy to check")
        return ApprovalCheck(
            True,
            False,
            "the manifest records role approvals but the spec declares no [approval] policy",
        )
    if recorded is None:
        return ApprovalCheck(
            True,
            False,
            "the spec requires sign-off from "
            + ", ".join(repr(role) for role in policy.required)
            + " but the manifest records no role approvals",
        )
    try:
        approvals = resolve_approvals(policy, recorded, approved_at="")
    except ApprovalError as exc:
        return ApprovalCheck(
            True, False, f"the recorded approvals do not satisfy the policy: {exc}"
        )
    return ApprovalCheck(
        True,
        True,
        "sign-off recorded for " + ", ".join(f"{a.role} ({a.name})" for a in approvals),
    )


def _excerpt(text: str, start: int) -> str:
    begin = max(0, start - 20)
    end = start + 40
    return ("…" if begin else "") + repr(text[begin:end]) + ("…" if end < len(text) else "")


def _first_difference(expected: Sequence[Block], found: Sequence[Block]) -> str | None:
    """Where a document first stops saying what ``report.md`` says, or ``None``."""

    for index, (want, got) in enumerate(zip(expected, found, strict=False), start=1):
        if want == got:
            continue
        if want.text == got.text:
            return f"block {index} has report.md's text in a different form"
        start = next(
            (i for i, (a, b) in enumerate(zip(want.text, got.text, strict=False)) if a != b),
            min(len(want.text), len(got.text)),
        )
        return (
            f"block {index} reads {_excerpt(got.text, start)} where report.md has "
            f"{_excerpt(want.text, start)}"
        )
    if len(expected) != len(found):
        return f"it has {len(found)} block(s) where report.md renders {len(expected)}"
    return None


def _digits(text: str) -> Counter[str]:
    return Counter(character for character in text if character.isdecimal())


def _document_problems(read: DocxText, report_text: str) -> list[str]:
    """Every way a document stops saying what ``report.md`` says.

    Three comparisons, and the last two do not trust the first. The blocks are
    compared with the ones ``report.md`` renders to, character for character.
    The digits are compared with ``report.md``'s raw text, so a renderer that
    lost a number could not also hide it by leaving it out of the blocks it
    expects. The redaction marker is counted against the raw text the same way,
    so a withheld cell cannot drop out of the document unnoticed.
    """

    expected = document_blocks(report_text, locale=read.language)
    problems: list[str] = []
    difference = _first_difference(expected, read.blocks)
    if difference is not None:
        problems.append(f"it does not say what report.md says: {difference}")
    title = document_title(expected)
    if read.title != title:
        problems.append(f"its title {read.title!r} is not report.md's {title!r}")
    if _digits(read.text) != _digits(report_text):
        problems.append("it does not carry the same digits as report.md")
    shown, marked = read.text.count(REDACTED_DISPLAY), report_text.count(REDACTED_DISPLAY)
    if shown != marked:
        problems.append(
            f"it shows {REDACTED_DISPLAY} {shown} time(s) where report.md shows it {marked}"
        )
    return problems


def check_document(document: bytes, report_text: str, figures: Sequence[Figure]) -> DocumentCheck:
    """Hold a Word export to the report it was rendered from, and to the gate.

    The document is read back out of its bytes -- never taken from the object
    that rendered it, which could not disagree with itself -- and compared with
    what ``report_text`` renders to. Its own narrative is then grounded against
    ``figures``: the numbers a funder reads in the document, not the ones in the
    Markdown beside it. ``run --format docx`` calls this before it writes
    anything, and ``verify --bundle`` calls it again on the file the bundle holds.
    """

    try:
        read = read_docx(document)
    except DocxError as exc:
        return DocumentCheck(True, False, f"{DOCX_NAME} is not a document this tool wrote: {exc}")
    problems = _document_problems(read, report_text)
    grounding = ground(read.narrative, figures)
    if not grounding.ok:
        unbound = ", ".join(repr(span.text) for span in grounding.unbound)
        problems.append(
            f"{len(grounding.unbound)} number(s) in its narrative bind to no receipt: {unbound}"
        )
    if problems:
        return DocumentCheck(True, False, f"{DOCX_NAME}: " + "; ".join(problems), grounding)
    return DocumentCheck(
        True,
        True,
        f"{DOCX_NAME} says what report.md says; its narrative grounds "
        f"{len(grounding.bound)} of {grounding.total} number(s)",
        grounding,
    )


def _check_bundle_document(
    bundle_dir: Path,
    manifest: Mapping[str, Any],
    report_text: str,
    figures: Sequence[Figure],
) -> DocumentCheck:
    """The document check for a bundle, in both directions.

    A ``report.docx`` the manifest does not attest is a failure rather than an
    unchecked extra: nothing in the export says this run wrote it, so a reader
    holding it has no receipt for it. An attested one that is missing is a
    failure too, and the artifact check names it as well.
    """

    artifacts = manifest.get("artifacts")
    attested = isinstance(artifacts, Mapping) and DOCX_NAME in artifacts
    path = bundle_dir / DOCX_NAME
    if not attested and not path.is_file():
        return DocumentCheck(False, True, "no document export to check")
    if not attested:
        return DocumentCheck(
            True, False, f"{DOCX_NAME} is in the bundle but the manifest does not attest it"
        )
    if not path.is_file():
        return DocumentCheck(True, False, f"the manifest attests {DOCX_NAME} but it is missing")
    return check_document(path.read_bytes(), report_text, figures)


def verify_bundle(
    bundle_dir: Path,
    figures: Sequence[Figure],
    *,
    coverage: RequirementCoverage | None = None,
    approval_policy: ApprovalPolicy | None = None,
) -> BundleResult:
    """Verify an exported bundle is internally coherent, not just re-derivable.

    Beyond re-deriving every receipt (``verify_manifest``), this reads each file
    the manifest hashes and recomputes its sha256, so a swapped ``report.md``,
    ``trace.html``, or chart SVG is caught; and it re-runs the grounding gate over
    the exported narrative, so a number that no longer binds to a receipt is
    caught. It fails closed: a manifest with no ``artifacts`` key is an error, and
    a missing artifact file is a failure. When the manifest attests
    ``report.docx``, the document is read back out of its bytes and held to
    ``report.md`` and to the gate; a ``report.docx`` it does not attest fails.
    """

    bundle_dir = Path(bundle_dir)
    manifest = json.loads((bundle_dir / "receipts.json").read_text(encoding="utf-8"))
    manifest_result = verify_manifest(figures, manifest)
    artifacts = _check_artifacts(bundle_dir, manifest)

    report_path = bundle_dir / "report.md"
    report_text = report_path.read_text(encoding="utf-8") if report_path.is_file() else ""
    grounding = ground(_report_narrative(report_text), figures)
    return BundleResult(
        manifest_result,
        artifacts,
        grounding,
        _check_coverage(manifest, coverage),
        _check_approval(manifest, approval_policy),
        _check_bundle_document(bundle_dir, manifest, report_text, figures),
    )
