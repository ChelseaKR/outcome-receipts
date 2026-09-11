"""Command-line interface.

Commands:
  map     map logical funder requirements to schema-variant CSV columns and emit
          a fail-closed human review queue (never executes a candidate)
  init    inspect an export and scaffold a starter TOML metric spec (empty stubs
          that fail loudly until a human fills in the SQL and definitions)
  run     compute figures, draft the narrative, run the grounding gate, and write
          the report, receipts manifest, and trace view (export blocked if any
          number is unbound)
  audit   run the grounding gate over an existing narrative file, against the
          figures the report may publish, and report both unbound numbers and
          numbers that state a cell small-cell suppression withholds
  mcp     serve audit, verify, trace, and the publishable figure list to a
          drafting tool over stdio, read-only (no export, no network)
  verify  re-derive every receipt in a manifest from the spec and data, and fail
          on any drift
  verify-ledger
          re-hash the append-only export ledger and fail if the chain is broken
  verify-bundle
          recompute the bundle manifest over an output directory and fail on any
          member that was tampered, is missing, or is extra
  diff    compare two receipts manifests from different reporting cycles and report
          which figures moved, were added, or removed, and why
  restate
          link a current run to a verified prior bundle without rewriting history
  migrate-check
          compare reviewed metrics across two schema-variant exports
  requirements-diff
          classify funder requirement changes by stable identifier
  contract-check
          package receipted milestone, threshold, and financial evidence
  rollup  compose a count from verified, unsuppressed partner bundles
  equity-review
          package allowlisted subgroup receipts after whole-report suppression
  verify-workflow
          validate a versioned evidence-workflow artifact before interpreting it
  eval    score the exported (post-suppression) narrative's grounding and write
          the eval report

Every command exits with a code from the contract below, and ``--json`` makes any
command emit one machine-readable object instead of the human-readable lines. The
exit code is the same either way; the JSON is purely presentational.

argparse only; no runtime dependency beyond the standard library.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import os
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from outcome_receipts import __version__
from outcome_receipts.bundle import bundle_manifest
from outcome_receipts.bundle import verify_bundle as verify_signed_bundle
from outcome_receipts.cards import write_cards
from outcome_receipts.charts import Chart, render_charts
from outcome_receipts.claims import (
    STATUS_BOUND,
    ClaimAudit,
    DirectionEvidence,
    audit_claims,
    audit_payload,
    evidence_from_rows,
    summarize,
)
from outcome_receipts.clock import Clock, FixedClock, SystemClock
from outcome_receipts.comparison import (
    ComparisonResult,
    ReconciliationResult,
    compute_comparison,
    compute_reconciliation,
)
from outcome_receipts.config import Spec, load_spec
from outcome_receipts.coverage import (
    CoverageError,
    RequirementCoverage,
    build_requirement_coverage,
)
from outcome_receipts.diff import diff_manifests
from outcome_receipts.docx import DOCX_NAME, DocxError, render_docx
from outcome_receipts.draft import draft, draft_template
from outcome_receipts.engine import compute_figures, read_csv_meta
from outcome_receipts.evaluate import EvalReport, evaluate
from outcome_receipts.grounding import (
    FixPlanRefused,
    apply_fix_plan,
    audit_narrative,
    build_fix_plan,
    explain_audit,
    explain_unbound,
    ground,
)
from outcome_receipts.ledger import LedgerEntry, append_export, read_ledger, verify_chain
from outcome_receipts.mapping import build_mapping_queue
from outcome_receipts.model_draft import (
    DraftingPolicyError,
    NarrativeDrafter,
    build_narrative_drafter,
)
from outcome_receipts.models import (
    ApprovalPolicy,
    AuditResult,
    Explanation,
    Figure,
    GroundingResult,
    NumericSpan,
    SpanCandidate,
    SuppressedSpan,
    TemplateSpec,
    role_key,
)
from outcome_receipts.policy import (
    DEFAULT_POLICY_ID,
    SuppressionPolicy,
    UnknownPolicyError,
    ad_hoc_policy,
    get_policy,
)
from outcome_receipts.portfolio import (
    PAGE_NAME,
    PortfolioError,
    PortfolioIndex,
    PortfolioReport,
    ReportVerification,
    read_index,
    render_index_html,
    shared_figures,
    write_index,
)
from outcome_receipts.preview import (
    preview_payload,
    preview_policies,
    render_preview_markdown,
)
from outcome_receipts.provenance import (
    Approval,
    ApprovalError,
    Provenance,
    approvals_summary,
    resolve_approvals,
)
from outcome_receipts.report import (
    receipts_manifest,
    render_diff_markdown,
    render_eval_markdown,
    render_report,
)
from outcome_receipts.scaffold import scaffold_spec
from outcome_receipts.suppression import (
    SuppressionResult,
    filter_for_aggregate_only,
    redact_comparison,
    redact_reconciliation,
    suppress_figures,
)
from outcome_receipts.trace import render_trace_html
from outcome_receipts.verify import (
    BundleResult,
    Check,
    DocumentCheck,
    VerifyResult,
    check_document,
    verify_bundle,
    verify_manifest,
)
from outcome_receipts.workflows import (
    WorkflowError,
    build_contract_evidence,
    build_equity_review,
    build_migration_check,
    build_requirement_change,
    build_restatement,
    build_rollup,
    verify_workflow_artifact,
    write_artifact,
)

# The chart subdirectory under the output directory, referenced from the report.
_CHART_DIR = "charts"

# The bundle manifest written next to the export it seals.
_BUNDLE_NAME = "bundle.json"

# The exit-code contract, single-sourced. Every command returns one of these, and
# the value is the machine-readable contract callers script against; ``--json``
# only changes what is printed, never the code.
EXIT_OK = 0
"""Success: the command ran and the grounding gate (where one applies) passed."""

EXIT_VERIFY_FAIL = 1
"""A map, audit, verify, verify-ledger, or eval check failed: a mapping is blocked,
a number is unbound, a receipt or artifact drifted, the export ledger's hash chain
is broken, or the eval gate did not pass."""

EXIT_GATE_FAIL = 2
"""The grounding gate refused to export: ``run`` found an unbound number and wrote
nothing."""

EXIT_APPROVAL_FAIL = 3

# 4: the export answers a bound requirement set incompletely. Distinct from the
# grounding gate (2), which asks whether every number in the prose traces to a
# receipt, and from approval (3). This asks the other half: whether every number
# the funder required was published, withheld with its cell marked, or declared
# unanswerable with a reason. A run can pass the gate, be approved, and still
# ship a report that silently omits a required figure -- that is the failure this
# code names.
EXIT_COVERAGE_FAIL = 4
"""The export was not approved: the grounding gate passed but no named human
signed off, so ``run`` wrote nothing."""


def _clock(*, reproducible: bool) -> Clock:
    return FixedClock() if reproducible else SystemClock()


def _load_key(path: str | None) -> bytes | None:
    """Load a signing key as raw bytes, or ``None`` for a digests-only bundle."""

    return Path(path).read_bytes() if path else None


def _bundle_members(out_dir: Path) -> dict[str, bytes]:
    """Read every export file under ``out_dir`` (except the bundle) back as bytes.

    Names are stored relative to the output directory with forward slashes, so a
    chart at ``charts/foo.svg`` is a stable member name across platforms and the
    same bytes re-bundle to the same digest.
    """

    members: dict[str, bytes] = {}
    for path in sorted(out_dir.rglob("*")):
        if not path.is_file() or path == out_dir / _BUNDLE_NAME:
            continue
        name = path.relative_to(out_dir).as_posix()
        members[name] = path.read_bytes()
    return members


def _sha256(text: str) -> str:
    """The sha256 hex digest of ``text`` encoded as UTF-8.

    Artifacts are written as UTF-8 text, so hashing the same encoding the digest
    is recomputed from at verify time makes the check exact.
    """

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _emit_json(payload: object) -> None:
    """Print one JSON object, stably ordered, as the whole of a command's output."""

    print(json.dumps(payload, indent=2, sort_keys=True))


def _span_payload(span: NumericSpan) -> dict[str, object]:
    """One unbound numeric span as a plain dict, not a dumped dataclass."""

    return {"text": span.text, "start": span.start, "end": span.end}


def _grounding_payload(result: GroundingResult) -> dict[str, int]:
    """The bound/unbound tallies of a grounding result as a plain dict."""

    return {
        "total": result.total,
        "bound": len(result.bound),
        "unbound": len(result.unbound),
    }


def _load_and_compute(
    config: str, *, reproducible: bool, quiet: bool = False
) -> tuple[Spec, list[dict[str, str]], list[Figure]]:
    spec = load_spec(config)
    table = read_csv_meta(spec.data_path)
    if not quiet:
        print(
            f"loaded {spec.data_path}: {table.row_count} rows, "
            f"{len(table.columns)} columns, digest {table.digest[:16]}"
        )
    figures = compute_figures(
        table.rows,
        spec.report.metrics,
        clock=_clock(reproducible=reproducible),
        data_checks=spec.report.data_checks,
    )
    return spec, table.rows, figures


def _compute_all(
    config: str, *, reproducible: bool, quiet: bool = False
) -> tuple[
    Spec,
    list[dict[str, str]],
    list[Figure],
    ComparisonResult | None,
    ReconciliationResult | None,
]:
    """Compute the full figure set, including comparison and reconciliation figures.

    The narrative metrics, the comparison, and the reconciliation are computed over
    the same data, so a caller (``run`` and ``verify`` alike) sees one figure list
    whose receipts cover every number the report can claim.
    """

    spec, rows, figures = _load_and_compute(config, reproducible=reproducible, quiet=quiet)
    comparison: ComparisonResult | None = None
    if spec.report.comparison is not None:
        comparison = compute_comparison(
            rows, spec.report.comparison, clock=_clock(reproducible=reproducible)
        )
        figures = [*figures, *comparison.figures]
    reconciliation: ReconciliationResult | None = None
    if spec.report.reconciliation is not None:
        reconciliation = compute_reconciliation(
            rows, spec.report.reconciliation, clock=_clock(reproducible=reproducible)
        )
        figures = [*figures, *reconciliation.figures]
    return spec, rows, figures, comparison, reconciliation


def _claims_text(
    comparison: ComparisonResult | None,
    reconciliation: ReconciliationResult | None,
    charts: Sequence[Chart],
) -> str:
    """The numbers a comparison, reconciliation, and charts assert, as plain text.

    Only the figure displays go here, never category labels or SVG geometry, so
    the gate checks the numbers a chart or table claims and binds each to a
    receipt. A rendered number that is not a figure display would be unbound and
    block export, which is what catches a separate, ungrounded data path.
    """

    parts: list[str] = []
    if comparison is not None:
        parts.append(" ".join(figure.display for figure in comparison.figures))
    if reconciliation is not None:
        parts.append(" ".join(figure.display for figure in reconciliation.figures))
    parts.extend(chart.claims_text for chart in charts)
    return " ".join(parts)


def _direction_evidence(
    comparison: ComparisonResult | None,
    reconciliation: ReconciliationResult | None,
    withheld_metric_ids: Sequence[str] = (),
) -> tuple[DirectionEvidence, ...]:
    """Every receipted direction a comparative claim in prose may be checked against.

    A reconciliation line is two comparison rows -- an outcome and its spend -- and
    both are evidence, because a claim about either is a claim about a direction this
    report computed. The rows must be the *pre*-suppression ones: a redacted row's
    ``direction`` is a sentinel, and reading it would turn a claim that discloses a
    withheld comparison into a claim that merely has nothing to bind to.
    """

    rows: list[object] = []
    if comparison is not None:
        rows.extend(comparison.rows)
    if reconciliation is not None:
        for line in reconciliation.rows:
            rows.append(line.outcome)
            rows.append(line.financial)
    return evidence_from_rows(rows, withheld_metric_ids)


def _print_claim_audit(label: str, audit: ClaimAudit) -> None:
    summary = summarize(audit)
    print(
        f"comparative claims in {label!r}: {summary.total} "
        f"(bound {summary.bound}, unbound {summary.unbound}, "
        f"contradicted {summary.contradicted}, disclosed {summary.disclosed})"
    )
    for verdict in audit.verdicts:
        if verdict.status == STATUS_BOUND:
            continue
        print(f"  {verdict.status}: at offset {verdict.span.start}, {verdict.detail}")


def _approver(
    title: str,
    narrative_result: GroundingResult,
    claims_result: GroundingResult,
    args: argparse.Namespace,
) -> str | None:
    """Resolve the human approver for this export, or ``None`` to abort.

    ``--approved-by NAME`` records the approver non-interactively, for CI and
    reproducible runs. Otherwise, on a TTY and unless ``--yes/--no-confirm`` was
    given, prompt for a sign-off: the reviewer types their name to approve, blank
    to abort. Off a TTY with no ``--approved-by``, there is nobody to prompt, so we
    return ``None`` and let the caller fail closed rather than hang on ``input()``.
    Under ``--json`` the prompt is also skipped (stdout carries exactly one JSON
    object), so an approver must arrive via ``--approved-by``.
    """

    if args.approved_by is not None:
        name: str = args.approved_by.strip()
        return name or None

    if args.no_confirm or args.json or not sys.stdin.isatty():
        return None

    figures_computed = narrative_result.total + claims_result.total
    numbers_bound = len(narrative_result.bound) + len(claims_result.bound)
    print("\nready to export:")
    print(f"  title:            {title}")
    print(f"  figures computed: {figures_computed}")
    print(f"  numbers bound:    {numbers_bound}")
    try:
        entered = input(
            "Approve this report for export? Type your name to sign off (blank to abort): "
        )
    except EOFError:
        return None
    entered_name = entered.strip()
    return entered_name or None


def _approve_pairs(args: argparse.Namespace) -> list[tuple[str, str]]:
    """The ``--approve ROLE:NAME`` sign-offs as ``(role, name)`` pairs.

    Split on the first colon only, so a name may contain one. A value with no
    colon is refused rather than read as a role with a blank approver, which
    would otherwise reach the policy check as a missing name and blame the spec
    for a typo on the command line.
    """

    pairs: list[tuple[str, str]] = []
    for raw in getattr(args, "approve", None) or []:
        role, separator, name = str(raw).partition(":")
        if not separator or not role.strip():
            raise ApprovalError(f"--approve expects ROLE:NAME, got {raw!r}")
        pairs.append((role.strip(), name.strip()))
    return pairs


def _prompt_for_roles(
    policy: ApprovalPolicy,
    supplied: Sequence[tuple[str, str]],
    args: argparse.Namespace,
) -> list[tuple[str, str]]:
    """Prompt for each required role the command line did not fill.

    Only on a TTY, and never under ``--json`` (stdout carries exactly one JSON
    object) or ``--no-confirm``. Off a TTY there is nobody to prompt, so the
    unfilled roles stay unfilled and ``resolve_approvals`` refuses by name --
    which is the fail-closed direction, and the same one the single-approver path
    already takes.
    """

    if args.no_confirm or args.json or not sys.stdin.isatty():
        return []
    given = {role_key(role) for role, _name in supplied}
    collected: list[tuple[str, str]] = []
    for role in policy.required:
        if role_key(role) in given:
            continue
        try:
            entered = input(f"Sign off as {role!r}? Type your name (blank to abort): ")
        except EOFError:
            return collected
        name = entered.strip()
        if not name:
            return collected
        collected.append((role, name))
    return collected


def _resolve_role_approvals(
    spec: Spec, args: argparse.Namespace, *, approved_at: str, interactive: bool
) -> tuple[Approval, ...]:
    """The role sign-offs this invocation records, checked against the spec.

    Returns an empty tuple when the spec declares no ``[approval]`` policy, which
    leaves the single-approver path exactly as it was. Raises ``ApprovalError``
    when a policy exists and the sign-offs do not satisfy it.
    """

    policy = spec.report.approval
    supplied = _approve_pairs(args)
    if policy is None:
        resolve_approvals(None, supplied, approved_at=approved_at)
        return ()
    if getattr(args, "approved_by", None) is not None:
        raise ApprovalError(
            "this spec requires sign-off from "
            + ", ".join(repr(role) for role in policy.required)
            + "; --approved-by records one unnamed role and cannot satisfy that policy, "
            "so use --approve ROLE:NAME once per role"
        )
    if interactive:
        supplied = [*supplied, *_prompt_for_roles(policy, supplied, args)]
    return resolve_approvals(policy, supplied, approved_at=approved_at)


def _workflow_approver(config_path: str, args: argparse.Namespace) -> str:
    """The ``approved_by`` string a workflow command records, policy checked.

    A workflow artifact is evidence packaged from a spec's receipts, so the
    spec's sign-off policy governs it too. Without this, a two-role spec could be
    packaged as a contract-check or an equity review with one signature, which is
    the bypass the policy exists to close: the requirement has to travel with the
    report definition rather than with the flag the operator happened to type.
    """

    spec = load_spec(config_path)
    approvals = _resolve_role_approvals(
        spec,
        args,
        approved_at=_clock(reproducible=args.reproducible).now_iso(),
        interactive=False,
    )
    if approvals:
        return approvals_summary(approvals)
    approved_by = str(getattr(args, "approved_by", None) or "").strip()
    if not approved_by:
        raise ApprovalError("no approver sign-off: pass --approved-by NAME")
    return approved_by


def _export_approval(
    spec: Spec,
    args: argparse.Namespace,
    narrative_result: GroundingResult,
    claims_result: GroundingResult,
    *,
    approved_at: str,
) -> tuple[tuple[Approval, ...], str | None, str]:
    """Who signed this export off, or why nobody did.

    Returns the role approvals (empty for a spec with no policy), the display
    string to record as ``approved_by``, and the reason to print when that string
    is ``None``. The refusal is returned rather than raised so ``run --json``
    still emits exactly one JSON object on the way out.
    """

    try:
        approvals = _resolve_role_approvals(spec, args, approved_at=approved_at, interactive=True)
    except ApprovalError as exc:
        return (), None, str(exc)
    if approvals:
        return approvals, approvals_summary(approvals), ""
    approver = _approver(spec.report.title, narrative_result, claims_result, args)
    return (), approver, "no approver sign-off"


def _print_approval(approver: str, approvals: Sequence[Approval]) -> None:
    """Report who signed off, one line per role when the spec declares any."""

    if not approvals:
        print(f"  approved: {approver}")
        return
    for approval in approvals:
        print(f"  approved ({approval.role}): {approval.name}")


def _approval_payload(
    approver: str, approved_at: str, approvals: Sequence[Approval]
) -> dict[str, object]:
    """The ``approval`` block of a ``run --json`` payload.

    ``approved_by`` is present either way and names every approver, so a consumer
    reading only that field reads a complete answer for a role-based export as
    well as a single-approver one. ``approvals`` appears only when the spec
    declared a policy, matching the manifest.
    """

    payload: dict[str, object] = {"approved_by": approver, "approved_at": approved_at}
    if approvals:
        payload["approvals"] = [
            {"role": a.role, "approved_by": a.name, "approved_at": a.approved_at} for a in approvals
        ]
    return payload


def _run_payload(
    *,
    gate_pass: bool,
    figures: Sequence[Figure],
    narrative_result: GroundingResult,
    claims_result: GroundingResult,
    outputs: object,
    ledger: object,
    approval: dict[str, object] | None,
) -> dict[str, object]:
    """The machine-readable record of a ``run`` invocation."""

    return {
        "command": "run",
        "gate_pass": gate_pass,
        "figures": len(figures),
        "narrative": _grounding_payload(narrative_result),
        "claims": _grounding_payload(claims_result),
        "unbound": [
            _span_payload(span) for span in (*narrative_result.unbound, *claims_result.unbound)
        ],
        "outputs": outputs,
        "ledger": ledger,
        "approval": approval,
    }


class _DocumentRefused(Exception):
    """``run --format docx`` built a document that does not hold; nothing was written."""

    def __init__(self, template_id: str, check: DocumentCheck) -> None:
        super().__init__(check.detail)
        self.template_id = template_id
        self.check = check


@dataclass(frozen=True)
class _ExportBuild:
    """One template's export, built in memory so every one can be checked before any is written."""

    title: str
    report_text: str
    trace_text: str
    manifest_text: str
    document: bytes | None


def _build_document(
    report_text: str, figures: Sequence[Figure], *, locale: str, template_id: str
) -> bytes:
    """Render ``report.docx`` from the report text and gate it on its own bytes.

    The check reads the written bytes back, never the blocks that produced them,
    and grounds the narrative it finds against the publishable figures. A report
    carrying a character a Word document cannot hold is refused here too, rather
    than exported with the character silently gone.
    """

    try:
        document = render_docx(report_text, locale=locale)
    except DocxError as exc:
        refused = DocumentCheck(True, False, f"{DOCX_NAME} cannot be written: {exc}")
        raise _DocumentRefused(template_id, refused) from exc
    check = check_document(document, report_text, figures)
    if not check.ok:
        raise _DocumentRefused(template_id, check)
    return document


def _build_export(
    args: argparse.Namespace,
    spec: Spec,
    figures: Sequence[Figure],
    narrative: str,
    charts: Sequence[Chart],
    comparison: ComparisonResult | None,
    reconciliation: ReconciliationResult | None,
    provenance: Provenance,
    *,
    title: str | None = None,
    coverage: RequirementCoverage | None = None,
    template_id: str = "",
) -> _ExportBuild:
    """Build the report, trace, optional document, and manifest, all in memory.

    Every artifact is built before the manifest so the manifest can hash its
    siblings. The manifest never hashes itself; the report embeds the receipts
    section but not the artifact digests, so the hash relation is one-directional
    (no circularity). See ADR 0006. ``report.docx`` is rendered from the finished
    report text, gated, and hashed like any other artifact; without
    ``--format docx`` nothing about the build changes.
    """

    export_title = title or spec.report.title
    report_text = render_report(
        export_title,
        narrative,
        figures,
        comparison=comparison,
        reconciliation=reconciliation,
        charts=charts,
        chart_dir=_CHART_DIR,
        provenance=provenance,
        coverage=coverage,
        locale=args.locale,
    )
    trace_text = render_trace_html(
        export_title,
        figures,
        provenance=provenance,
        comparison=comparison,
        locale=args.locale,
    )

    digests = {
        "report.md": _sha256(report_text),
        "trace.html": _sha256(trace_text),
    }
    for chart in charts:
        digests[f"{_CHART_DIR}/{chart.chart_id}.svg"] = _sha256(chart.svg)
    document: bytes | None = None
    if getattr(args, "document_format", "md") == "docx":
        document = _build_document(
            report_text, figures, locale=args.locale, template_id=template_id
        )
        digests[DOCX_NAME] = hashlib.sha256(document).hexdigest()
    manifest_text = receipts_manifest(
        figures, provenance=provenance, artifacts=digests, coverage=coverage
    )
    return _ExportBuild(export_title, report_text, trace_text, manifest_text, document)


def _write_export(
    args: argparse.Namespace,
    build: _ExportBuild,
    charts: Sequence[Chart],
    *,
    out_dir: Path,
    ledger_path: Path,
) -> tuple[dict[str, str | None], LedgerEntry]:
    """Write one built export, then append the export ledger.

    Write order: charts, then the report and its document, then the trace, then
    the manifest, then the ledger entry.
    """

    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / "report.md"
    manifest_path = out_dir / "receipts.json"
    trace_path = out_dir / "trace.html"
    outputs: dict[str, str | None] = {
        "report": str(report_path),
        "receipts": str(manifest_path),
        "trace": str(trace_path),
        "charts": None,
    }
    if charts:
        chart_dir = out_dir / _CHART_DIR
        chart_dir.mkdir(parents=True, exist_ok=True)
        for chart in charts:
            (chart_dir / f"{chart.chart_id}.svg").write_text(chart.svg, encoding="utf-8")
        outputs["charts"] = str(chart_dir)
    report_path.write_text(build.report_text, encoding="utf-8")
    if build.document is not None:
        document_path = out_dir / DOCX_NAME
        document_path.write_bytes(build.document)
        outputs["document"] = str(document_path)
    trace_path.write_text(build.trace_text, encoding="utf-8")
    manifest_path.write_text(build.manifest_text, encoding="utf-8")

    entry = append_export(
        ledger_path,
        report_title=build.title,
        manifest_json_or_hash=build.manifest_text,
        recipient=args.recipient,
        clock=_clock(reproducible=args.reproducible),
    )
    return outputs, entry


def _draft_templates(
    spec: Spec, figures: Sequence[Figure], drafter: NarrativeDrafter | None = None
) -> list[tuple[TemplateSpec, str, GroundingResult]]:
    if drafter is not None:
        return [
            (template, narrative, ground(narrative, figures))
            for template in spec.report.effective_templates
            for narrative in (drafter.draft(template.template, figures),)
        ]
    if not spec.report.templates:
        template = spec.report.effective_templates[0]
        narrative = draft(spec.report, figures)
        return [(template, narrative, ground(narrative, figures))]
    return [
        (template, narrative, ground(narrative, figures))
        for template in spec.report.effective_templates
        for narrative in (draft_template(template.template, figures),)
    ]


def _print_template_summary(
    figures: Sequence[Figure],
    claims_result: GroundingResult,
    drafts: Sequence[tuple[TemplateSpec, str, GroundingResult]],
) -> None:
    print(f"figures computed: {len(figures)}")
    print(
        f"chart and comparison numbers: {claims_result.total} "
        f"(bound {len(claims_result.bound)}, unbound {len(claims_result.unbound)})"
    )
    for template, _narrative, result in drafts:
        print(
            f"numbers in {template.template_id!r} narrative: {result.total} "
            f"(bound {len(result.bound)}, unbound {len(result.unbound)})"
        )


def _print_run_summary(
    publishable: Sequence[Figure],
    claims_result: GroundingResult,
    drafts: Sequence[tuple[TemplateSpec, str, GroundingResult]],
    claim_audits: Sequence[tuple[TemplateSpec, ClaimAudit]],
    suppression: SuppressionResult,
) -> None:
    """What the run found, before it says whether it will export."""

    _print_template_summary(publishable, claims_result, drafts)
    for template, audit in claim_audits:
        _print_claim_audit(template.template_id, audit)
    n_hidden = len(suppression.suppressed) + len(suppression.complementary_suppressed)
    print(f"suppression policy: applied (threshold {suppression.threshold}; hidden {n_hidden})")


def _print_gate_failure(
    claims_result: GroundingResult,
    drafts: Sequence[tuple[TemplateSpec, str, GroundingResult]],
    publishable: Sequence[Figure] = (),
    *,
    explain: bool = False,
    claim_audits: Sequence[tuple[TemplateSpec, ClaimAudit]] = (),
) -> None:
    """Report the refusal, and on request why each number missed.

    The refusal lines print whether or not a diagnosis was asked for, and the
    diagnosis is only ever added beneath them. ``run`` still writes nothing and
    still exits ``EXIT_GATE_FAIL``: explaining a refusal does not soften it.
    """

    print("\ngrounding gate: FAIL — refusing to export", file=sys.stderr)
    for template, audit in claim_audits:
        for verdict in audit.verdicts:
            if verdict.status == STATUS_BOUND:
                continue
            print(
                f"  {verdict.status} claim in {template.template_id!r}: {verdict.detail}",
                file=sys.stderr,
            )
    for span in claims_result.unbound:
        print(f"  unverifiable number: {span.text!r}", file=sys.stderr)
    for template, _narrative, result in drafts:
        for span in result.unbound:
            print(
                f"  unverifiable number in {template.template_id!r}: {span.text!r}",
                file=sys.stderr,
            )
    if not explain:
        return
    spans = [
        *claims_result.unbound,
        *(span for _template, _narrative, result in drafts for span in result.unbound),
    ]
    for explanation in explain_unbound(spans, publishable):
        print(f"  why {explanation.span.text!r}: {explanation.detail}", file=sys.stderr)


def _write_template_exports(
    args: argparse.Namespace,
    spec: Spec,
    figures: Sequence[Figure],
    comparison: ComparisonResult | None,
    reconciliation: ReconciliationResult | None,
    charts: Sequence[Chart],
    claims_result: GroundingResult,
    drafts: Sequence[tuple[TemplateSpec, str, GroundingResult]],
    approver: str,
    approved_at: str,
    key: bytes | None,
    *,
    suppression_applied: bool = False,
    narrative_drafter: str = "deterministic",
    coverage: RequirementCoverage | None = None,
    approvals: Sequence[Approval] = (),
) -> tuple[list[tuple[TemplateSpec, dict[str, str | None], LedgerEntry]], Path, bool]:
    base_out = Path(args.out)
    fan_out = bool(spec.report.templates)
    ledger_path = Path(args.ledger) if args.ledger else base_out.parent / "export-ledger.jsonl"
    written: list[tuple[TemplateSpec, dict[str, str | None], LedgerEntry]] = []
    builds: list[tuple[TemplateSpec, Path, _ExportBuild]] = []
    for template, narrative, result in drafts:
        provenance = Provenance(
            numbers_bound=len(result.bound) + len(claims_result.bound),
            numbers_unbound=0,
            approved_by=approver,
            approved_at=approved_at,
            suppression_applied=suppression_applied,
            aggregate_only=True,
            narrative_drafter=narrative_drafter,
            approvals=tuple(approvals),
        )
        out_dir = base_out / template.template_id if fan_out else base_out
        build = _build_export(
            args,
            spec,
            figures,
            narrative,
            charts,
            comparison,
            reconciliation,
            provenance,
            title=template.title,
            coverage=coverage,
            template_id=template.template_id,
        )
        builds.append((template, out_dir, build))
    # Every template is built, and its document gated, before any is written, so a
    # refusal for the second template cannot leave the first on disk and in the
    # ledger as an export nobody finished.
    for template, out_dir, build in builds:
        outputs, entry = _write_export(
            args, build, charts, out_dir=out_dir, ledger_path=ledger_path
        )
        bundle_path = out_dir / _BUNDLE_NAME
        bundle_path.write_text(bundle_manifest(_bundle_members(out_dir), key=key), encoding="utf-8")
        outputs["bundle"] = str(bundle_path)
        written.append((template, outputs, entry))
    return written, ledger_path, fan_out


def _redact_report_structures(
    comparison: ComparisonResult | None,
    reconciliation: ReconciliationResult | None,
    figures: list[Figure],
) -> tuple[ComparisonResult | None, ReconciliationResult | None]:
    if comparison is not None:
        comparison = redact_comparison(comparison, figures)
    if reconciliation is not None:
        reconciliation = redact_reconciliation(reconciliation, figures)
    return comparison, reconciliation


def _requirement_coverage(spec: Spec, figures: Sequence[Figure]) -> RequirementCoverage | None:
    """Coverage for a bound spec, or ``None`` when the spec binds no requirements.

    ``None`` means "this spec makes no coverage claim". It is not the same fact
    as a coverage record whose counts are all zero, and the two are never
    rendered the same way: an unbound spec carries no `requirements` key in its
    manifest at all.
    """

    if spec.requirements_path is None or spec.report.requirements is None:
        return None
    return build_requirement_coverage(
        requirements=spec.report.requirements,
        requirements_path=spec.requirements_path,
        data_path=spec.data_path,
        metric_requirements={
            metric.metric_id: metric.requirement_id
            for metric in spec.report.metrics
            if metric.requirement_id
        },
        figures=figures,
    )


def _print_coverage_failure(coverage: RequirementCoverage) -> None:
    print(
        f"\nrequirement coverage: FAIL — {len(coverage.unanswered)} of "
        f"{len(coverage.records)} requirements in {coverage.document_path} "
        "are neither answered nor declared unanswerable",
        file=sys.stderr,
    )
    for record in coverage.unanswered:
        print(f"  {record.requirement_id}: {record.detail}", file=sys.stderr)


def _refuse_for_grounding(
    args: argparse.Namespace,
    *,
    gate_pass: bool,
    raw_gate_pass: bool,
    raw_claims: GroundingResult,
    raw_drafts: Sequence[tuple[TemplateSpec, str, GroundingResult]],
    figures: Sequence[Figure],
    publishable: Sequence[Figure],
    claims_result: GroundingResult,
    drafts: Sequence[tuple[TemplateSpec, str, GroundingResult]],
    combined_result: GroundingResult,
    outputs: object,
    template_payload: Mapping[str, object],
    claim_audits: Sequence[tuple[TemplateSpec, ClaimAudit]],
    claim_payload: object,
) -> int | None:
    """Refuse the export when the grounding gate failed, or ``None`` when it passed."""

    if gate_pass:
        return None
    if args.json:
        payload = _run_payload(
            gate_pass=False,
            figures=publishable,
            narrative_result=combined_result,
            claims_result=claims_result,
            outputs=outputs,
            ledger=None,
            approval=None,
        )
        payload["templates"] = dict(template_payload)
        payload["comparative_claims"] = claim_payload
        _emit_json(payload)
        return EXIT_GATE_FAIL
    if not raw_gate_pass:
        # The raw drafts failed, so the raw figure set is the one they were
        # written against and the only set a diagnosis of them can be true
        # about. Explaining raw spans against the publishable set would
        # report a suppressed figure as simply missing.
        _print_gate_failure(
            raw_claims, raw_drafts, figures, explain=args.explain, claim_audits=claim_audits
        )
    else:
        _print_gate_failure(
            claims_result,
            drafts,
            publishable,
            explain=args.explain,
            claim_audits=claim_audits,
        )
    return EXIT_GATE_FAIL


def _print_coverage_pass(coverage: RequirementCoverage | None) -> None:
    """One line for a bound spec, and nothing at all for an unbound one."""

    if coverage is None:
        return
    counts = coverage.counts()
    print(
        f"requirement coverage: PASS — {counts['answered']} answered, "
        f"{counts['withheld']} withheld, {counts['unanswerable']} unanswerable "
        f"of {len(coverage.records)} in {coverage.document_path}"
    )


def _with_coverage(
    payload: dict[str, object], coverage: RequirementCoverage | None
) -> dict[str, object]:
    """Add the coverage record, or leave the payload without the key entirely.

    Absent, not an empty object: a spec that binds no requirement document has
    not answered zero requirements, it has made no coverage claim at all.
    """

    if coverage is not None:
        payload["requirements"] = coverage.payload()
    return payload


def _refuse_for_coverage(
    args: argparse.Namespace,
    coverage: RequirementCoverage | None,
    *,
    figures: Sequence[Figure],
    narrative_result: GroundingResult,
    claims_result: GroundingResult,
    outputs: object,
    template_payload: Mapping[str, object],
    claim_payload: object,
) -> int | None:
    """Refuse the export and write nothing, naming every unanswered requirement.

    ``None`` means there is nothing to refuse: either the spec binds no
    requirement document, or every requirement is answered, withheld, or
    declared unanswerable with a blocker `map` reproduced.

    ``gate_pass`` is reported as true in the JSON because it was: the grounding
    gate passed and this is the other gate. Reporting it as a grounding failure
    would send whoever reads the JSON to look for an unbound number that is not
    there.
    """

    if coverage is None or coverage.ok:
        return None
    if args.json:
        payload = _run_payload(
            gate_pass=True,
            figures=figures,
            narrative_result=narrative_result,
            claims_result=claims_result,
            outputs=outputs,
            ledger=None,
            approval=None,
        )
        payload["templates"] = dict(template_payload)
        payload["comparative_claims"] = claim_payload
        payload["requirements"] = coverage.payload()
        _emit_json(payload)
        return EXIT_COVERAGE_FAIL
    _print_coverage_failure(coverage)
    return EXIT_COVERAGE_FAIL


def _print_written(
    written: Sequence[tuple[TemplateSpec, dict[str, str | None], LedgerEntry]],
    *,
    fan_out: bool,
    n_charts: int,
    key: bytes | None,
    ledger_path: Path,
) -> None:
    """One block of paths per exported template, in the order they were written."""

    for template, outputs, entry in written:
        prefix = f"{template.template_id}: " if fan_out else ""
        print(f"  {prefix}report:   {outputs['report']}")
        print(f"  {prefix}receipts: {outputs['receipts']}")
        print(f"  {prefix}trace:    {outputs['trace']}")
        if outputs.get("document") is not None:
            print(f"  {prefix}document: {outputs['document']}")
        if outputs["charts"] is not None:
            print(f"  {prefix}charts:   {outputs['charts']} ({n_charts} SVG)")
        print(f"  {prefix}bundle:   {outputs['bundle']} ({'signed' if key else 'digests-only'})")
        print(f"  {prefix}ledger:   {ledger_path} (entry {entry.index}, hash {entry.entry_hash})")


def _document_payload(check: DocumentCheck) -> dict[str, object]:
    """A document check as JSON: its verdict, and the narrative grounding it read."""

    return {
        "checked": check.checked,
        "ok": check.ok,
        "detail": check.detail,
        "grounding": None
        if check.grounding is None
        else {
            "total": check.grounding.total,
            "bound": len(check.grounding.bound),
            "unbound": [_span_payload(span) for span in check.grounding.unbound],
        },
    }


def _refuse_for_document(
    args: argparse.Namespace,
    refusal: _DocumentRefused,
    *,
    figures: Sequence[Figure],
    narrative_result: GroundingResult,
    claims_result: GroundingResult,
    outputs: object,
    template_payload: Mapping[str, object],
    claim_payload: object,
) -> int:
    """Refuse the export because ``report.docx`` did not hold, having written nothing.

    This is reached only after the grounding gate, coverage, and sign-off have all
    passed, so what failed is the document: a character it cannot carry, or a
    rendering that does not say what ``report.md`` says. Nothing is on disk and
    nothing is in the ledger, because every template is built and checked before
    any is written. The exit code is the grounding gate's, because this is that
    gate applied to the file a funder opens.
    """

    if args.json:
        payload = _run_payload(
            gate_pass=False,
            figures=figures,
            narrative_result=narrative_result,
            claims_result=claims_result,
            outputs=outputs,
            ledger=None,
            approval=None,
        )
        payload["templates"] = dict(template_payload)
        payload["comparative_claims"] = claim_payload
        payload["document"] = {
            **_document_payload(refusal.check),
            "template": refusal.template_id,
        }
        _emit_json(payload)
        return EXIT_GATE_FAIL
    print(f"\ndocument gate: FAIL — refusing to export {refusal.template_id!r}", file=sys.stderr)
    print(f"  {refusal.check.detail}", file=sys.stderr)
    return EXIT_GATE_FAIL


def _cmd_run(args: argparse.Namespace) -> int:
    spec, _rows, figures, comparison, reconciliation = _compute_all(
        args.config, reproducible=args.reproducible, quiet=args.json
    )
    narrative_drafter = build_narrative_drafter(
        spec.report.drafting, allow_cloud=args.allow_cloud_drafting
    )
    # First gate: generated/deterministic text must bind to the real computed
    # figures before privacy transforms can hide an invented number.
    raw_charts = render_charts(spec.report.charts, figures)
    raw_claims = ground(_claims_text(comparison, reconciliation, raw_charts), figures)
    raw_drafts = _draft_templates(spec, figures, narrative_drafter)
    raw_gate_pass = raw_claims.ok and all(result.ok for _t, _n, result in raw_drafts)

    # The pre-suppression rows, kept before `_redact_report_structures` overwrites
    # each row's `direction` with the redaction sentinel. The comparative-claim gate
    # needs the real direction of a withheld row to report a claim about it as a
    # disclosure rather than as merely unbound, exactly as `audit_narrative` is given
    # the pre-suppression figures for the same reason.
    raw_comparison, raw_reconciliation = comparison, reconciliation

    suppressed_figures, suppression = suppress_figures(figures)
    publishable = filter_for_aggregate_only(suppressed_figures)
    comparison, reconciliation = _redact_report_structures(comparison, reconciliation, publishable)
    charts = render_charts(spec.report.charts, publishable)
    claims_result = ground(_claims_text(comparison, reconciliation, charts), publishable)
    drafts = _draft_templates(spec, publishable, narrative_drafter)
    combined_result = ground(" ".join(narrative for _t, narrative, _r in drafts), publishable)
    # The comparative-claim gate over the drafted prose: a direction word binds only
    # to a receipted comparison direction. Scoped to the narratives, which is the one
    # surface a model writes; a metric's author-written caveat is not drafted and is
    # not gated here.
    evidence = _direction_evidence(
        raw_comparison,
        raw_reconciliation,
        (*suppression.suppressed, *suppression.complementary_suppressed),
    )
    claim_audits = [
        (template, audit_claims(narrative, evidence)) for template, narrative, _r in drafts
    ]
    gate_pass = (
        raw_gate_pass
        and claims_result.ok
        and all(result.ok for _t, _n, result in drafts)
        and all(audit.ok for _t, audit in claim_audits)
    )
    template_payload = {
        template.template_id: _grounding_payload(result) for template, _n, result in drafts
    }
    claim_payload = {template.template_id: audit_payload(audit) for template, audit in claim_audits}
    empty_outputs = {
        "report": None,
        "receipts": None,
        "trace": None,
        "charts": None,
        "bundle": None,
    }
    failed_outputs: object = (
        empty_outputs
        if not spec.report.templates
        else {t.template_id: empty_outputs for t, _n, _r in drafts}
    )

    if not args.json:
        _print_run_summary(publishable, claims_result, drafts, claim_audits, suppression)

    refusal = _refuse_for_grounding(
        args,
        gate_pass=gate_pass,
        raw_gate_pass=raw_gate_pass,
        raw_claims=raw_claims,
        raw_drafts=raw_drafts,
        figures=figures,
        publishable=publishable,
        claims_result=claims_result,
        drafts=drafts,
        combined_result=combined_result,
        outputs=failed_outputs,
        template_payload=template_payload,
        claim_audits=claim_audits,
        claim_payload=claim_payload,
    )
    if refusal is not None:
        return refusal

    # The second half of the claim, and it runs after the grounding gate on
    # purpose: grounding asks whether every number in the prose traces to a
    # receipt, coverage asks whether every number the funder required was
    # published. A run that fails grounding has nothing worth grading for
    # coverage, and a run that passes both is the only one that may be approved.
    coverage = _requirement_coverage(spec, publishable)
    refusal = _refuse_for_coverage(
        args,
        coverage,
        figures=publishable,
        narrative_result=combined_result,
        claims_result=claims_result,
        outputs=failed_outputs,
        template_payload=template_payload,
        claim_payload=claim_payload,
    )
    if refusal is not None:
        return refusal

    approved_at = _clock(reproducible=args.reproducible).now_iso()
    approvals, approver, reason = _export_approval(
        spec, args, combined_result, claims_result, approved_at=approved_at
    )
    if approver is None:
        if args.json:
            payload = _run_payload(
                gate_pass=True,
                figures=publishable,
                narrative_result=combined_result,
                claims_result=claims_result,
                outputs=failed_outputs,
                ledger=None,
                approval=None,
            )
            payload["templates"] = template_payload
            payload["comparative_claims"] = claim_payload
            _emit_json(payload)
        print(f"export aborted: {reason}", file=sys.stderr)
        return EXIT_APPROVAL_FAIL

    key = _load_key(getattr(args, "sign_key_file", None))
    try:
        written, ledger_path, fan_out = _write_template_exports(
            args,
            spec,
            publishable,
            comparison,
            reconciliation,
            charts,
            claims_result,
            drafts,
            approver,
            approved_at,
            key,
            suppression_applied=True,
            narrative_drafter="bedrock" if narrative_drafter is not None else "deterministic",
            coverage=coverage,
            approvals=approvals,
        )
    except _DocumentRefused as document_refusal:
        return _refuse_for_document(
            args,
            document_refusal,
            figures=publishable,
            narrative_result=combined_result,
            claims_result=claims_result,
            outputs=failed_outputs,
            template_payload=template_payload,
            claim_payload=claim_payload,
        )
    if args.json:
        flat_outputs: object = (
            written[0][1]
            if not fan_out
            else {template.template_id: outputs for template, outputs, _entry in written}
        )
        ledgers = [
            {"path": str(ledger_path), "index": entry.index, "entry_hash": entry.entry_hash}
            for _template, _outputs, entry in written
        ]
        payload = _run_payload(
            gate_pass=True,
            figures=publishable,
            narrative_result=combined_result,
            claims_result=claims_result,
            outputs=flat_outputs,
            ledger=ledgers[0] if not fan_out else {"entries": ledgers},
            approval=_approval_payload(approver, approved_at, approvals),
        )
        payload["templates"] = template_payload
        payload["comparative_claims"] = claim_payload
        _emit_json(_with_coverage(payload, coverage))
        return EXIT_OK

    print("\ngrounding gate: PASS")
    _print_coverage_pass(coverage)
    _print_approval(approver, approvals)
    _print_written(written, fan_out=fan_out, n_charts=len(charts), key=key, ledger_path=ledger_path)
    return EXIT_OK


def _publishable_and_hidden(
    figures: Sequence[Figure],
) -> tuple[list[Figure], list[Figure]]:
    """Split a computed figure set into what may be published and what may not.

    The second list is the *pre*-suppression form of every redacted figure, so a
    caller can recognize a raw protected value in prose. It is never rendered
    into an artifact; it exists so the tool can say "that number is a suppressed
    cell" instead of "that number is unbound".
    """

    redacted, suppression = suppress_figures(list(figures))
    hidden_ids = {*suppression.suppressed, *suppression.complementary_suppressed}
    publishable = filter_for_aggregate_only(redacted)
    hidden = [figure for figure in figures if figure.metric_id in hidden_ids]
    return publishable, hidden


def _suppressed_span_payload(disclosure: SuppressedSpan) -> dict[str, object]:
    """A disclosed protected cell as JSON, distinct from an unbound span."""

    return {
        **_span_payload(disclosure.span),
        "metric_ids": list(disclosure.metric_ids),
        "publishable_metric_ids": list(disclosure.publishable_metric_ids),
        "ambiguous": disclosure.ambiguous,
    }


def _candidate_payload(candidate: SpanCandidate) -> dict[str, object]:
    return {
        "metric_id": candidate.metric_id,
        "display": candidate.display,
        "reason": candidate.reason,
        "detail": candidate.detail,
        "distance": candidate.distance,
        "substitutable": candidate.substitutable,
    }


def _explanation_payload(explanation: Explanation) -> dict[str, object]:
    return {
        **_span_payload(explanation.span),
        "remedy": explanation.remedy,
        "detail": explanation.detail,
        "candidates": [_candidate_payload(item) for item in explanation.candidates],
    }


def _print_explanations(explanations: Sequence[Explanation]) -> None:
    """Render the diagnoses under the verdict lines, never in place of them.

    The verdict is printed first and unchanged by the caller; this only adds
    lines beneath it. An explanation that printed instead of a failure line
    would let a reader mistake advice for a result.
    """

    for explanation in explanations:
        print(f"  why {explanation.span.text!r} at offset {explanation.span.start}:")
        print(f"    {explanation.detail}")
        for candidate in explanation.candidates[1:]:
            print(f"    also: {candidate.detail}")


def _print_audit_refusals(result: AuditResult, claims: ClaimAudit) -> None:
    """The refusal lines, each naming which gate refused and why.

    Kept apart because they are different findings with different remedies: a
    disclosed number and a disclosed direction are both recoveries of a withheld
    cell, while an unbound claim is a sentence nothing receipts.
    """

    if result.suppressed:
        print(
            "\naudit: FAIL — the narrative states a cell suppression withholds",
            file=sys.stderr,
        )
    if claims.disclosed:
        print(
            "\naudit: FAIL — the narrative states the direction of a withheld comparison",
            file=sys.stderr,
        )
    elif not claims.ok:
        print(
            "\naudit: FAIL — a comparative claim binds to no receipted direction",
            file=sys.stderr,
        )


def _cmd_audit(args: argparse.Namespace) -> int:
    # The full figure set, not just the narrative metrics: complementary
    # suppression is computed over every figure in the report, so auditing
    # against a subset would leave a cell visible here that `run` redacts.
    _spec, _rows, figures, comparison, reconciliation = _compute_all(
        args.config, reproducible=args.reproducible, quiet=args.json
    )
    publishable, hidden = _publishable_and_hidden(figures)
    narrative = Path(args.narrative).read_text(encoding="utf-8")

    if args.apply_fixes:
        return _apply_fixes(args, narrative, publishable, hidden)

    # --fixes-out is a request for the diagnoses in file form, so it turns them
    # on. Without this it wrote a plan built from an empty explanation list: a
    # file that says "no fixes" about a narrative nobody diagnosed, which reads
    # exactly like a narrative nothing could be done for.
    explain = bool(args.explain or args.fixes_out)
    result = audit_narrative(narrative, publishable, hidden)
    # Explaining is a read of the same canonicalization the verdict came from,
    # and the verdict is already fixed by the line above. `explain_audit`
    # returns a copy carrying the diagnoses; `ok` does not read them, so the
    # exit code below is the same number whether or not `--explain` was given.
    explained = explain_audit(result, publishable, hidden) if explain else result
    # The same narrative's comparative claims, against the receipted directions.
    # `_compute_all` returns the pre-suppression comparison, which is the set this
    # needs: a claim agreeing with a withheld row is a disclosure, and a redacted
    # row no longer carries the direction that makes it one.
    claims = audit_claims(
        narrative,
        _direction_evidence(comparison, reconciliation, [figure.metric_id for figure in hidden]),
    )
    if args.fixes_out:
        Path(args.fixes_out).write_text(
            json.dumps(build_fix_plan(narrative, explained.explanations), indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )

    if args.json:
        payload: dict[str, object] = {
            "command": "audit",
            "ok": result.ok,
            "total": result.total,
            "bound": len(result.bound),
            "suppressed": [_suppressed_span_payload(item) for item in result.suppressed],
            "unbound": [_span_payload(span) for span in result.unbound],
            "comparative_claims": audit_payload(claims),
        }
        if explain:
            payload["explanations"] = [
                _explanation_payload(item) for item in explained.explanations
            ]
        _emit_json(payload)
        return EXIT_OK if result.ok and claims.ok else EXIT_VERIFY_FAIL

    print(
        f"numbers: {result.total}, bound: {len(result.bound)}, "
        f"suppressed cells: {len(result.suppressed)}, unbound: {len(result.unbound)}"
    )
    for disclosure in result.suppressed:
        names = ", ".join(disclosure.metric_ids)
        print(
            f"  suppressed cell: {disclosure.span.text!r} at offset {disclosure.span.start} "
            f"is the withheld value of {names}; this report does not publish it"
        )
        if disclosure.ambiguous:
            also = ", ".join(disclosure.publishable_metric_ids)
            print(f"    (it is also the published value of {also}; rephrase so the two differ)")
    for span in result.unbound:
        print(f"  unverifiable: {span.text!r} at offset {span.start}")
    _print_explanations(explained.explanations)
    _print_claim_audit("narrative", claims)
    if args.fixes_out:
        print(f"  fix plan: {args.fixes_out}")
    _print_audit_refusals(result, claims)
    return EXIT_OK if result.ok and claims.ok else EXIT_VERIFY_FAIL


def _apply_fixes(
    args: argparse.Namespace,
    narrative: str,
    publishable: Sequence[Figure],
    hidden: Sequence[Figure],
) -> int:
    """Apply a reviewed fix plan, then re-run the gate over what was written.

    The gate is re-run on the *substituted* text, not on the plan's promises.
    That is the whole point: a plan is a human's edited proposal, and the only
    statement this command makes about the result is one the gate made about
    the bytes now on disk.
    """

    if not args.fixed_out:
        # Never in place. The narrative is the author's own file and the
        # substitution is a proposal; writing over it would destroy the text a
        # reviewer would compare the result against.
        print(
            "audit: --apply-fixes needs --fixed-out; the narrative is never rewritten in place",
            file=sys.stderr,
        )
        return EXIT_VERIFY_FAIL
    plan = json.loads(Path(args.apply_fixes).read_text(encoding="utf-8"))
    try:
        fixed = apply_fix_plan(narrative, plan, publishable, hidden)
    except FixPlanRefused as refusal:
        if args.json:
            _emit_json({"command": "audit", "applied": False, "refused": str(refusal)})
        else:
            print(f"audit: refused to apply the fix plan — {refusal}", file=sys.stderr)
        return EXIT_VERIFY_FAIL

    Path(args.fixed_out).write_text(fixed, encoding="utf-8")
    result = audit_narrative(fixed, publishable, hidden)
    if args.json:
        _emit_json(
            {
                "command": "audit",
                "applied": True,
                "written": args.fixed_out,
                "ok": result.ok,
                "total": result.total,
                "bound": len(result.bound),
                "suppressed": [_suppressed_span_payload(item) for item in result.suppressed],
                "unbound": [_span_payload(span) for span in result.unbound],
            }
        )
        return EXIT_OK if result.ok else EXIT_VERIFY_FAIL

    print(f"applied {len(plan.get('fixes', []))} fix(es); wrote {args.fixed_out}")
    print(
        f"numbers: {result.total}, bound: {len(result.bound)}, "
        f"suppressed cells: {len(result.suppressed)}, unbound: {len(result.unbound)}"
    )
    for span in result.unbound:
        print(f"  unverifiable: {span.text!r} at offset {span.start}")
    return EXIT_OK if result.ok else EXIT_VERIFY_FAIL


def _cmd_mcp(args: argparse.Namespace) -> int:
    """Serve the read-only tools on stdin/stdout until the client closes them.

    The figure computation is passed in rather than imported by the server, so
    ``mcp.py`` holds the transport and four projections and nothing that knows
    how a spec is loaded. It also means the server answers from exactly the same
    ``_publishable_and_hidden`` split that ``audit`` uses, rather than from a
    second one that could come to disagree with it.

    ``--reproducible`` is honoured so a client can pin ``computed_at``; the
    figures are recomputed per call rather than cached, because a cache would
    answer from data the file no longer holds.
    """

    from outcome_receipts.mcp import serve

    def resolve(
        config: str,
    ) -> tuple[Sequence[Figure], Sequence[Figure], Sequence[DirectionEvidence]]:
        _spec, _rows, figures, comparison, reconciliation = _compute_all(
            config, reproducible=args.reproducible, quiet=True
        )
        publishable, hidden = _publishable_and_hidden(figures)
        evidence = _direction_evidence(
            comparison, reconciliation, [figure.metric_id for figure in hidden]
        )
        return publishable, hidden, evidence

    return serve(sys.stdin, sys.stdout, resolve)


def _check_payload(check: Check) -> dict[str, object]:
    """One check, carrying what it is a check *of*.

    ``kind`` is the field that distinguishes a receipt re-derived from the data
    from a descriptor of the manifest document (``schema_version``, ``hash``)
    compared against a constant. Without it a consumer counting ``checks`` counts
    descriptors as receipts, which is what every count below used to do.
    """

    return {
        "metric_id": check.metric_id,
        "ok": check.ok,
        "detail": check.detail,
        "kind": check.kind,
    }


def _receipt_counts(result: VerifyResult) -> dict[str, object]:
    """The receipt-only counts, alongside the totals across every check.

    ``n_ok`` and ``drift`` are unchanged and still span both kinds, so a script
    reading them keeps working. They are simply not counts of receipts, and were
    reported as though they were: a four-receipt manifest carrying a
    ``schema_version`` and a ``hash`` descriptor answered ``n_ok: 6``.
    """

    return {
        "n_ok": result.n_ok,
        "drift": len(result.checks) - result.n_ok,
        "receipts_checked": len(result.receipt_checks),
        "receipts_ok": result.n_receipts_ok,
        "receipts_drift": len(result.failed_receipts),
        "manifest_checks": len(result.manifest_checks),
        "manifest_checks_failed": len(result.failed_manifest_checks),
    }


def _verify_payload(result: VerifyResult) -> dict[str, object]:
    """The machine-readable record of a manifest ``verify`` invocation."""

    return {
        "command": "verify",
        "mode": "manifest",
        "ok": result.ok,
        "checks": [_check_payload(check) for check in result.checks],
        **_receipt_counts(result),
    }


def _bundle_payload(result: BundleResult) -> dict[str, object]:
    """The machine-readable record of a whole-bundle ``verify`` invocation.

    The receipt keys (``checks``, ``n_ok``, ``drift``) match the manifest mode's
    shape, so a script can read them the same way in both modes; the bundle mode
    adds the artifact digests and the narrative grounding.
    """

    manifest = result.manifest
    return {
        "command": "verify",
        "mode": "bundle",
        "ok": result.ok,
        "checks": [_check_payload(check) for check in manifest.checks],
        **_receipt_counts(manifest),
        "artifacts": [
            {"path": artifact.path, "ok": artifact.ok, "detail": artifact.detail}
            for artifact in result.artifacts
        ],
        "grounding": {
            "total": result.grounding.total,
            "bound": len(result.grounding.bound),
            "unbound": [_span_payload(span) for span in result.grounding.unbound],
        },
        "coverage": {
            "checked": result.coverage.checked,
            "ok": result.coverage.ok,
            "detail": result.coverage.detail,
        },
        "approval": {
            "checked": result.approval.checked,
            "ok": result.approval.ok,
            "detail": result.approval.detail,
        },
        "document": _document_payload(result.document),
    }


def _print_manifest_checks(result: VerifyResult) -> None:
    """The two counts, each naming what it counted, then every line.

    The receipt count is the manifest's receipts and nothing else. The manifest
    count is the document's own descriptors, which are compared against a
    constant rather than re-derived from the data. Reporting one number for both
    told a reader that a four-receipt manifest had six receipts re-derived.
    """

    print(
        f"receipts checked: {len(result.receipt_checks)} "
        f"(re-derived {result.n_receipts_ok}, drift {len(result.failed_receipts)})"
    )
    if result.manifest_checks:
        names = ", ".join(check.metric_id for check in result.manifest_checks)
        failed = len(result.failed_manifest_checks)
        print(
            f"manifest descriptors checked: {len(result.manifest_checks)} ({names}); failed {failed}"
        )
    for check in result.checks:
        status = "ok" if check.ok else "DRIFT"
        print(f"  [{status}] {check.metric_id}: {check.detail}")


def _verify_failure_reason(result: VerifyResult) -> str:
    """What actually failed, in the words of the thing that failed.

    The headline used to read "a receipt does not match the data" whenever the
    result was not ok -- including when every receipt re-derived and the only
    failure was the manifest declaring a schema version nobody implements. That
    sent the reader to the data, which was the one place the problem was not.
    """

    reasons: list[str] = []
    descriptors = result.failed_manifest_checks
    if descriptors:
        names = ", ".join(check.metric_id for check in descriptors)
        reasons.append(f"the manifest's own {names} descriptor is not one this version accepts")
    receipts = result.failed_receipts
    if receipts:
        count = len(receipts)
        noun = "receipt" if count == 1 else "receipts"
        names = ", ".join(check.metric_id for check in receipts)
        reasons.append(f"{count} {noun} do not match the data ({names})")
    if not reasons:
        # Unreachable while `ok` is the conjunction of every check, and stated
        # rather than silently rendered as an empty reason if that ever changes.
        return "the manifest did not verify, and no failing check says why"
    return " and ".join(reasons)


def _cmd_verify(args: argparse.Namespace) -> int:
    spec, _rows, figures, _comparison, _reconciliation = _compute_all(
        args.config, reproducible=args.reproducible, quiet=args.json
    )
    # Apply suppression to re-derived figures so they match the exported manifest.
    suppressed_figures, _suppression_result = suppress_figures(figures)
    if args.bundle is not None:
        return _verify_bundle(args, spec, suppressed_figures)
    manifest = json.loads(Path(args.receipts).read_text(encoding="utf-8"))
    result = verify_manifest(suppressed_figures, manifest)

    if args.json:
        _emit_json(_verify_payload(result))
        return EXIT_OK if result.ok else EXIT_VERIFY_FAIL

    _print_manifest_checks(result)
    if result.ok:
        print("\nverify: PASS — every receipt re-derives from the data")
        return EXIT_OK
    print(f"\nverify: FAIL — {_verify_failure_reason(result)}", file=sys.stderr)
    return EXIT_VERIFY_FAIL


# What a clean chain does not prove. The chain has no secret and nothing
# outside the file records its expected length, so these three tampers verify
# clean; the PASS output states them so a reader cannot take PASS for more
# than it is. tests/test_ledger.py pins each one with a hand-tampered fixture.
_LEDGER_PASS_LIMITS = (
    "entries deleted from the end leave a shorter chain that still verifies",
    "a rewrite of the whole file with recomputed hashes verifies; the chain"
    " has no secret and proves integrity of what is recorded, not authorship",
    "an export that was never appended leaves no trace; PASS is not evidence of completeness",
)


def _cmd_verify_ledger(args: argparse.Namespace) -> int:
    ledger_path = Path(args.ledger)

    # Fail closed on a missing file. read_ledger treats an absent ledger as
    # empty, which is right for the writer (first export creates the file) and
    # wrong for a verifier: a mistyped --ledger path would otherwise report
    # PASS over nothing. A check that read no file has verified no chain.
    if not ledger_path.exists():
        if args.json:
            _emit_json(
                {
                    "command": "verify-ledger",
                    "ok": False,
                    "ledger": str(ledger_path),
                    "entries": 0,
                    "problems": [f"no ledger file at {ledger_path}"],
                    "not_proven": list(_LEDGER_PASS_LIMITS),
                }
            )
            return EXIT_VERIFY_FAIL
        print(f"export ledger: {ledger_path}", file=sys.stderr)
        print(
            "\nverify-ledger: FAIL — no ledger file at that path; a check that"
            " read nothing has verified nothing",
            file=sys.stderr,
        )
        return EXIT_VERIFY_FAIL

    problems = verify_chain(ledger_path)
    n_entries = len(read_ledger(ledger_path))

    if args.json:
        _emit_json(
            {
                "command": "verify-ledger",
                "ok": not problems,
                "ledger": str(ledger_path),
                "entries": n_entries,
                "problems": list(problems),
                "not_proven": list(_LEDGER_PASS_LIMITS),
            }
        )
        return EXIT_OK if not problems else EXIT_VERIFY_FAIL

    if not problems:
        print(f"export ledger: {ledger_path}")
        print(
            f"verify-ledger: PASS — all {n_entries} recorded entries re-verify;"
            " nothing was edited, inserted, reordered, or removed mid-chain"
        )
        for limit in _LEDGER_PASS_LIMITS:
            print(f"  not proven: {limit}")
        return EXIT_OK
    print(f"export ledger: {ledger_path}", file=sys.stderr)
    for problem in problems:
        print(f"  {problem}", file=sys.stderr)
    print("\nverify-ledger: FAIL — the export chain is broken", file=sys.stderr)
    return EXIT_VERIFY_FAIL


def _verify_bundle(args: argparse.Namespace, spec: Spec, figures: Sequence[Figure]) -> int:
    # The coverage is re-derived from the spec and the requirement document as
    # they are *now*, not read back from the manifest, so an edit to the
    # requirement document after export changes the digest and fails here.
    result = verify_bundle(
        Path(args.bundle),
        figures,
        coverage=_requirement_coverage(spec, figures),
        approval_policy=spec.report.approval,
    )
    manifest = result.manifest

    if args.json:
        _emit_json(_bundle_payload(result))
        return EXIT_OK if result.ok else EXIT_VERIFY_FAIL

    _print_manifest_checks(manifest)
    print(f"artifacts checked: {len(result.artifacts)}")
    for artifact in result.artifacts:
        status = "ok" if artifact.ok else "MISMATCH"
        print(f"  [{status}] {artifact.path}: {artifact.detail}")
    print(
        f"narrative grounding: {result.grounding.total} number(s), "
        f"{len(result.grounding.unbound)} unbound"
    )
    for span in result.grounding.unbound:
        print(f"  unverifiable number: {span.text!r}")
    print(
        "requirement coverage: "
        + ("not checked" if not result.coverage.checked else "checked")
        + f" — {result.coverage.detail}"
    )
    print(
        "approval policy: "
        + ("not checked" if not result.approval.checked else "checked")
        + f" — {result.approval.detail}"
    )
    print(
        "document export: "
        + ("not checked" if not result.document.checked else "checked")
        + f" — {result.document.detail}"
    )

    if result.ok:
        print("\nverify: PASS — the whole bundle is coherent")
        return EXIT_OK
    _print_bundle_failure(result)
    return EXIT_VERIFY_FAIL


def _print_bundle_failure(result: BundleResult) -> None:
    """Name every check that failed, on stderr, one line each."""

    print("\nverify: FAIL — the exported bundle does not verify", file=sys.stderr)
    if not result.manifest.ok:
        print(f"  receipts manifest: {_verify_failure_reason(result.manifest)}", file=sys.stderr)
    for artifact in result.failed_artifacts:
        print(f"  offending file: {artifact.path} ({artifact.detail})", file=sys.stderr)
    if not result.grounding.ok:
        for span in result.grounding.unbound:
            print(f"  ungrounded number in report.md: {span.text!r}", file=sys.stderr)
    if not result.coverage.ok:
        print(f"  requirement coverage: {result.coverage.detail}", file=sys.stderr)
    if not result.approval.ok:
        print(f"  approval policy: {result.approval.detail}", file=sys.stderr)
    if not result.document.ok:
        print(f"  document export: {result.document.detail}", file=sys.stderr)


def _eval_payload(report: EvalReport, *, out: str | None) -> dict[str, object]:
    """The machine-readable record of an ``eval`` invocation."""

    return {
        "command": "eval",
        "gate_pass": report.gate_pass,
        "scored": report.scored,
        "n_numbers": report.n_numbers,
        "n_bound": report.n_bound,
        "n_unbound": report.n_unbound,
        "grounding_rate": report.grounding_rate,
        "grounding_ci": list(report.grounding_ci),
        "hallucinated_rate": report.hallucinated_rate,
        "hallucinated_ci": list(report.hallucinated_ci),
        "out": out,
    }


def _cmd_diff(args: argparse.Namespace) -> int:
    prior = json.loads(Path(args.prior).read_text(encoding="utf-8"))
    current = json.loads(Path(args.current).read_text(encoding="utf-8"))
    diff = diff_manifests(prior, current)
    markdown = render_diff_markdown(diff, prior_label=args.prior, current_label=args.current)
    if args.json:
        _emit_json(
            {
                "command": "diff",
                "prior": args.prior,
                "current": args.current,
                "added": list(diff.added),
                "removed": list(diff.removed),
                "changed": [
                    {
                        "metric_id": item.metric_id,
                        "prior": item.prior,
                        "current": item.current,
                        "reasons": list(item.reasons),
                    }
                    for item in diff.changed
                ],
                "unchanged": list(diff.unchanged),
                "out": args.out,
            }
        )
        if args.out:
            Path(args.out).write_text(markdown, encoding="utf-8")
        return EXIT_OK
    if args.out:
        Path(args.out).write_text(markdown, encoding="utf-8")
        print(f"wrote diff: {args.out}")
    else:
        print(markdown)
    return 0


def _cmd_verify_bundle(args: argparse.Namespace) -> int:
    out_dir = Path(args.dir)
    manifest = json.loads((out_dir / _BUNDLE_NAME).read_text(encoding="utf-8"))
    key = _load_key(getattr(args, "sign_key_file", None))
    result = verify_signed_bundle(_bundle_members(out_dir), manifest, key=key)

    if args.json:
        _emit_json(
            {
                "command": "verify-bundle",
                "ok": result.ok,
                "checks": [
                    {"name": check.name, "ok": check.ok, "detail": check.detail}
                    for check in result.checks
                ],
            }
        )
        return EXIT_OK if result.ok else EXIT_VERIFY_FAIL

    print(
        f"members checked: {len(result.checks)} "
        f"(ok {result.n_ok}, tampered {len(result.checks) - result.n_ok})"
    )
    for check in result.checks:
        status = "ok" if check.ok else "TAMPERED"
        print(f"  [{status}] {check.name}: {check.detail}")
    if result.ok:
        print("\nverify-bundle: PASS — every member matches the sealed manifest")
        return EXIT_OK
    print("\nverify-bundle: FAIL — the bundle has been tampered with", file=sys.stderr)
    return EXIT_VERIFY_FAIL


def _cmd_eval(args: argparse.Namespace) -> int:
    """Score the gate over every narrative the pipeline would export.

    Two things are scored, and they are scored the way `run` produces them.

    The figures are the *publishable* set. Drafting and grounding against the raw
    figures measured a narrative `run` would never produce: one whose numbers
    include the cells suppression withholds.

    The narratives are *all* of `spec.report.effective_templates`, drafted
    through the same `_draft_templates` the export path uses. This used to call
    `draft(spec.report, ...)`, which fills only the legacy single
    `[report] template`. A spec that names funder formats under
    `[[report.templates]]` leaves that field empty, so eval drafted the empty
    string, found no numbers, and reported a pass over nothing. That is the shape
    of `examples/multi-funder/report.toml`, which ships here, and whose two
    funder narratives carry real figures eval never looked at.

    A figure written into two funder narratives is counted twice, and that is the
    intended denominator, not an artifact to correct. `run` exports one report
    per format, each a separate document a separate funder reads, so each
    occurrence is its own opportunity for an ungrounded number to reach someone.
    Scoring the distinct figures instead would report a smaller population than
    the one the gate actually has to hold, and would make the measurement depend
    on how many formats happen to share a metric.
    """

    spec, _rows, figures, _comparison, _reconciliation = _compute_all(
        args.config, reproducible=True, quiet=args.json
    )
    publishable, _hidden = _publishable_and_hidden(figures)
    drafts = _draft_templates(spec, publishable)
    result = GroundingResult(
        bound=tuple(span for _t, _n, one in drafts for span in one.bound),
        unbound=tuple(span for _t, _n, one in drafts for span in one.unbound),
    )
    report = evaluate(result)
    markdown = render_eval_markdown(report, dataset=Path(args.config).parent.name)
    if args.out:
        Path(args.out).write_text(markdown, encoding="utf-8")

    # An eval that scored no number has measured nothing, and this command exists
    # to measure. `gate_pass` is still true and still reported, because it is
    # true: nothing failed to bind. But exiting 0 on it hands CI a green from a
    # run that never exercised the gate, which is how the multi-template hole
    # above stayed invisible. `render_eval_markdown` already refuses to print the
    # vacuous rate as an observed measurement; the exit code agrees with it now.
    exit_code = EXIT_OK if report.gate_pass and report.scored else EXIT_VERIFY_FAIL

    if args.json:
        _emit_json(_eval_payload(report, out=args.out or None))
        return exit_code

    if args.out:
        print(f"wrote eval report: {args.out}")
    else:
        print(markdown)
    if not report.scored:
        print(
            "\neval: FAIL — no numeric span was scored, so this run is not a "
            "measurement of the grounding gate. Check that the report spec's "
            "templates render figures and that suppression has not withheld all "
            "of them.",
            file=sys.stderr,
        )
    return exit_code


def _cmd_init(args: argparse.Namespace) -> int:
    spec_text = scaffold_spec(Path(args.data), title=args.title)
    out_path: Path | None = Path(args.out) if args.out else None
    if out_path is not None:
        out_path.write_text(spec_text, encoding="utf-8")

    if args.json:
        _emit_json(
            {
                "command": "init",
                "out": str(out_path) if out_path is not None else None,
                "spec_toml": spec_text,
            }
        )
        return EXIT_OK

    if out_path is not None:
        print(f"wrote starter spec: {out_path}")
        print(
            "every metric is an empty stub; fill value_sql/slice_sql/definition "
            "before `receipts run`"
        )
    else:
        print(spec_text, end="")
    return EXIT_OK


def _cmd_map(args: argparse.Namespace) -> int:
    queue = build_mapping_queue(Path(args.data), Path(args.requirements))
    payload = {"command": "map", "out": args.out, **queue.payload()}
    if args.out:
        Path(args.out).write_text(
            json.dumps(queue.payload(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    if args.json:
        _emit_json(payload)
    else:
        print(f"mapping candidates: {len(queue.candidates)}")
        for candidate in queue.candidates:
            print(f"  [{candidate.status}] {candidate.metric_id}: {candidate.confidence:.2f}")
        if args.out:
            print(f"review queue: {args.out}")
        print("no mapping is approved or executed; a human must review every candidate")
    return EXIT_OK if queue.ok else EXIT_VERIFY_FAIL


def _finish_workflow(args: argparse.Namespace, artifact: dict[str, object]) -> int:
    """Write and report a fully validated workflow artifact."""

    out_path = Path(args.out)
    write_artifact(out_path, artifact)
    if args.json:
        _emit_json({"command": artifact["kind"], "out": str(out_path), "artifact": artifact})
    else:
        print(f"wrote {artifact['kind']} artifact: {out_path}")
    return EXIT_OK


def _cmd_restate(args: argparse.Namespace) -> int:
    artifact = build_restatement(
        prior_config=Path(args.prior_config),
        prior_bundle=Path(args.prior_bundle),
        current_config=Path(args.config),
        reason=args.reason,
        approved_by=_workflow_approver(args.config, args),
        reproducible=args.reproducible,
    )
    return _finish_workflow(args, artifact)


def _cmd_migrate_check(args: argparse.Namespace) -> int:
    artifact = build_migration_check(
        before_config=Path(args.before_config),
        after_config=Path(args.after_config),
        approved_by=args.approved_by,
        reproducible=args.reproducible,
    )
    return _finish_workflow(args, artifact)


def _cmd_requirements_diff(args: argparse.Namespace) -> int:
    artifact = build_requirement_change(Path(args.prior), Path(args.current))
    return _finish_workflow(args, artifact)


def _cmd_contract_check(args: argparse.Namespace) -> int:
    artifact = build_contract_evidence(
        config_path=Path(args.config),
        contract_path=Path(args.contract),
        approved_by=_workflow_approver(args.config, args),
        reproducible=args.reproducible,
    )
    return _finish_workflow(args, artifact)


def _cmd_suppress_preview(args: argparse.Namespace) -> int:
    """Preview policies without writing a report, a bundle, or a ledger entry.

    The raw figures are computed once and every policy is measured against that
    same set, so a difference between two rows is a difference the policy made
    rather than a difference in what was computed.
    """
    policies: list[SuppressionPolicy] = []
    seen: set[tuple[str, int]] = set()
    for policy_id in args.policy or []:
        policy = get_policy(policy_id)
        if (policy.policy_id, policy.threshold) not in seen:
            seen.add((policy.policy_id, policy.threshold))
            policies.append(policy)
    for threshold in args.threshold or []:
        policy = ad_hoc_policy(threshold)
        if (policy.policy_id, policy.threshold) not in seen:
            seen.add((policy.policy_id, policy.threshold))
            policies.append(policy)
    if not policies:
        policies.append(get_policy(DEFAULT_POLICY_ID))

    _spec, _rows, figures, _comparison, _reconciliation = _compute_all(
        args.config, reproducible=args.reproducible, quiet=args.json
    )
    previews = preview_policies(figures, policies)

    if args.json:
        _emit_json(preview_payload(previews, include_withheld_values=args.local))
        return EXIT_OK
    print(render_preview_markdown(previews, include_withheld_values=args.local), end="")
    return EXIT_OK


def _cmd_rollup(args: argparse.Namespace) -> int:
    artifact = build_rollup(
        plan_path=Path(args.plan),
        approved_by=args.approved_by,
        reproducible=args.reproducible,
    )
    return _finish_workflow(args, artifact)


def _cmd_equity_review(args: argparse.Namespace) -> int:
    artifact = build_equity_review(
        config_path=Path(args.config),
        plan_path=Path(args.plan),
        approved_by=_workflow_approver(args.config, args),
        reproducible=args.reproducible,
    )
    return _finish_workflow(args, artifact)


def _cmd_verify_workflow(args: argparse.Namespace) -> int:
    try:
        artifact = json.loads(Path(args.artifact).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WorkflowError(f"cannot read workflow artifact: {exc}") from exc
    if not isinstance(artifact, dict):
        raise WorkflowError("workflow artifact must be a JSON object")
    result = verify_workflow_artifact(artifact)
    if args.json:
        _emit_json(
            {
                "command": "verify-workflow",
                "ok": result.ok,
                "artifact": args.artifact,
                "checks": [
                    {"scope": check.scope, "ok": check.ok, "detail": check.detail}
                    for check in result.checks
                ],
            }
        )
    else:
        for check in result.checks:
            status = "ok" if check.ok else "FAIL"
            print(f"  [{status}] {check.scope}: {check.detail}")
        outcome = "PASS" if result.ok else "FAIL"
        print(f"\nverify-workflow: {outcome}")
    return EXIT_OK if result.ok else EXIT_VERIFY_FAIL


# --------------------------------------------------------------------------
# The portfolio: a batch of specs, and the one page an auditor enters through.
# --------------------------------------------------------------------------


def _portfolio_slug(spec: Path) -> str:
    """The output subdirectory one spec's exports go into.

    A spec is conventionally ``<name>/report.toml``, so the directory name is the
    identifying half; anything else falls back to the file's own stem.
    """

    return spec.parent.name if spec.name == "report.toml" else spec.stem


def _portfolio_targets(specs: Sequence[str]) -> list[tuple[Path, str]]:
    """The specs to run, ordered by path, with the slug each writes under.

    Ordering is by resolved path so a batch is deterministic whatever order the
    arguments arrived in. A repeated spec and two specs that would write into one
    directory are both refused, naming what collided: silently running a spec
    twice, or letting the second overwrite the first, would produce an index
    whose rows do not correspond to the specs the operator asked for.
    """

    resolved = sorted({Path(spec).resolve() for spec in specs})
    if len(resolved) != len({Path(spec).resolve() for spec in specs}):  # pragma: no cover
        raise PortfolioError("duplicate spec")
    if len(resolved) < len(specs):
        raise PortfolioError("the same spec was given more than once")
    targets: list[tuple[Path, str]] = []
    taken: dict[str, Path] = {}
    for spec in resolved:
        slug = _portfolio_slug(spec)
        if slug in taken:
            raise PortfolioError(
                f"{spec} and {taken[slug]} would both export into {slug!r}; "
                "rename one directory or run them into separate portfolios"
            )
        taken[slug] = spec
        targets.append((spec, slug))
    return targets


def _portfolio_run_argv(
    args: argparse.Namespace, spec: Path, out_dir: Path, ledger: Path
) -> list[str]:
    """The `run` command line one spec in the batch is exported with.

    Built as an argv and parsed by the real parser rather than assembled as a
    Namespace, so every default comes from `run` itself. A flag added to `run`
    later cannot silently take a different default inside a batch.
    """

    argv = [
        "run",
        "--config",
        str(spec),
        "--out",
        str(out_dir),
        "--ledger",
        str(ledger),
        "--locale",
        args.locale,
    ]
    if args.reproducible:
        argv.append("--reproducible")
    if args.approved_by is not None:
        argv += ["--approved-by", args.approved_by]
    for pair in args.approve or []:
        argv += ["--approve", pair]
    if args.recipient is not None:
        argv += ["--recipient", args.recipient]
    if args.sign_key_file is not None:
        argv += ["--sign-key-file", args.sign_key_file]
    return argv


def _portfolio_bundles(spec: Spec, out_dir: Path) -> list[tuple[str, Path]]:
    """The `(title, directory)` pairs one spec's export wrote.

    A multi-template spec writes one bundle per funder format into its own
    subdirectory, so it contributes several rows to the index rather than one.
    The index is a list of reports, and each of those is a report.
    """

    if not spec.report.templates:
        return [(spec.report.title, out_dir)]
    return [(template.title, out_dir / template.template_id) for template in spec.report.templates]


def _portfolio_report(
    spec_path: Path,
    title: str,
    bundle_dir: Path,
    root: Path,
    entry: LedgerEntry,
) -> PortfolioReport:
    """One index row, read back from what the export actually wrote."""

    manifest = json.loads((bundle_dir / "receipts.json").read_text(encoding="utf-8"))
    provenance = manifest.get("provenance", {})
    approved_by = str(provenance.get("approved_by") or "")
    bundle = json.loads((bundle_dir / _BUNDLE_NAME).read_text(encoding="utf-8"))
    return PortfolioReport(
        spec=str(spec_path),
        directory=bundle_dir.relative_to(root).as_posix(),
        title=title,
        approved_by=approved_by,
        bundle_digest=str(bundle.get("bundle_digest", "")),
        signed="signature" in bundle,
        ledger_index=entry.index,
        ledger_entry_hash=entry.entry_hash,
    )


def _cmd_portfolio(args: argparse.Namespace) -> int:
    """Run every spec through the ordinary export path, then record the batch.

    No shortcut: each spec is exported by `run` itself, so the grounding gate,
    the requirement-coverage refusal, suppression and the human sign-off all
    apply exactly as they do to a single report. The first spec that does not
    export stops the batch, names itself, and returns its own exit code, and no
    portfolio record is written -- an index over a batch that did not finish
    would say the portfolio is what it is not. The exports that already
    succeeded stay on disk and stay in the ledger, because they happened.
    """

    root = Path(args.out)
    ledger = Path(args.ledger) if args.ledger else root / "export-ledger.jsonl"
    targets = _portfolio_targets(args.specs)
    reports: list[PortfolioReport] = []
    for spec_path, slug in targets:
        out_dir = root / slug
        before = len(read_ledger(ledger))
        argv = _portfolio_run_argv(args, spec_path, out_dir, ledger)
        run_args = build_parser().parse_args(argv)
        if args.json:
            # The batch's own JSON object is the only thing on stdout. Each run's
            # human output would otherwise interleave with it; stderr is left
            # alone, so a refusal still says why.
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                code = int(run_args.func(run_args))
        else:
            print(f"\n=== {spec_path} ===")
            code = int(run_args.func(run_args))
        if code != EXIT_OK:
            print(
                f"\nportfolio: FAIL -- {spec_path} did not export (exit {code}); "
                "no portfolio record was written",
                file=sys.stderr,
            )
            return code
        entries = read_ledger(ledger)[before:]
        bundles = _portfolio_bundles(load_spec(spec_path), out_dir)
        if len(entries) != len(bundles):  # pragma: no cover - defensive
            print(
                f"portfolio: FAIL -- {spec_path} wrote {len(bundles)} bundle(s) but "
                f"{len(entries)} ledger entr(ies); no portfolio record was written",
                file=sys.stderr,
            )
            return EXIT_VERIFY_FAIL
        for (title, bundle_dir), entry in zip(bundles, entries, strict=True):
            reports.append(_portfolio_report(spec_path, title, bundle_dir, root, entry))

    index = PortfolioIndex(
        reports=tuple(reports), ledger=os.path.relpath(ledger, root).replace(os.sep, "/")
    )
    path = write_index(root, index)
    if args.json:
        _emit_json(
            {
                "command": "portfolio",
                "out": str(root),
                "record": str(path),
                "ledger": str(ledger),
                "reports": [report.payload() for report in index.reports],
            }
        )
        return EXIT_OK
    print(f"\nportfolio: {len(reports)} report(s) exported")
    print(f"  record: {path}")
    print(f"  ledger: {ledger}")
    print(f"  next:   receipts portfolio-verify --dir {root}")
    return EXIT_OK


def _verify_one_report(
    report: PortfolioReport, root: Path, *, reproducible: bool
) -> tuple[ReportVerification, dict[str, Any] | None]:
    """Re-verify one report from its own spec, and hand back its manifest.

    The manifest comes back so the shared-figure table is built from what each
    report actually published rather than from a second computation. A report
    that cannot be read at all is a failed row, not an aborted run: one broken
    bundle must not hide the state of the others.
    """

    bundle_dir = root / report.directory
    try:
        spec, _rows, figures, _comparison, _reconciliation = _compute_all(
            report.spec, reproducible=reproducible, quiet=True
        )
        suppressed, _suppression = suppress_figures(figures)
        result = verify_bundle(
            bundle_dir,
            suppressed,
            coverage=_requirement_coverage(spec, suppressed),
            approval_policy=spec.report.approval,
        )
        bundle = json.loads((bundle_dir / _BUNDLE_NAME).read_text(encoding="utf-8"))
        manifest = json.loads((bundle_dir / "receipts.json").read_text(encoding="utf-8"))
    except (OSError, ValueError, KeyError, CoverageError, WorkflowError) as exc:
        return ReportVerification(report, False, f"{type(exc).__name__}: {exc}"), None

    seal = verify_signed_bundle(_bundle_members(bundle_dir), bundle)
    recorded = str(bundle.get("bundle_digest", ""))
    problems: list[str] = []
    if not result.ok:
        problems.append(_bundle_failure_reason(result))
    if not seal.ok:
        problems.append("the sealed bundle manifest does not match the files beside it")
    if recorded != report.bundle_digest:
        # Catches a wholesale replacement of bundle.json, which re-seals itself
        # and would otherwise verify against its own new digest.
        problems.append(
            f"bundle digest {recorded or '(absent)'} does not match the "
            f"{report.bundle_digest} recorded when the batch ran"
        )
    if problems:
        return ReportVerification(report, False, "; ".join(problems)), manifest
    return ReportVerification(report, True, "every receipt, artifact and seal holds"), manifest


def _bundle_failure_reason(result: BundleResult) -> str:
    """One sentence naming what in a bundle did not hold."""

    reasons: list[str] = []
    if not result.manifest.ok:
        reasons.append(_verify_failure_reason(result.manifest))
    if result.failed_artifacts:
        reasons.append(
            "artifact(s) changed after export: "
            + ", ".join(check.path for check in result.failed_artifacts)
        )
    if not result.grounding.ok:
        reasons.append(f"{len(result.grounding.unbound)} number(s) in report.md no longer bind")
    if not result.coverage.ok:
        reasons.append(result.coverage.detail)
    if not result.approval.ok:
        reasons.append(result.approval.detail)
    if not result.document.ok:
        reasons.append(result.document.detail)
    return "; ".join(reasons) or "the bundle did not verify and no check says why"


def _cmd_portfolio_verify(args: argparse.Namespace) -> int:
    """Re-verify every bundle in a portfolio and render the auditor's index."""

    root = Path(args.dir)
    index = read_index(root)
    verifications: list[ReportVerification] = []
    manifests: list[tuple[str, dict[str, Any]]] = []
    for report in index.reports:
        verification, manifest = _verify_one_report(report, root, reproducible=args.reproducible)
        verifications.append(verification)
        if manifest is not None:
            manifests.append((report.title, manifest))

    shared = shared_figures(manifests)
    page = root / PAGE_NAME
    page.write_text(render_index_html(verifications, shared, locale=args.locale), encoding="utf-8")
    ok = all(verification.ok for verification in verifications)

    if args.json:
        _emit_json(
            {
                "command": "portfolio-verify",
                "ok": ok,
                "dir": str(root),
                "index": str(page),
                "reports": [
                    {
                        "title": verification.report.title,
                        "directory": verification.report.directory,
                        "ok": verification.ok,
                        "detail": verification.detail,
                    }
                    for verification in verifications
                ],
                "shared_figures": [figure.payload() for figure in shared],
            }
        )
        return EXIT_OK if ok else EXIT_VERIFY_FAIL

    for verification in verifications:
        status = "ok" if verification.ok else "FAILED"
        print(f"  [{status}] {verification.report.title}: {verification.detail}")
    print(f"shared figures: {len(shared)}")
    for figure in shared:
        print(f"  {figure.metric_id}: {figure.status}")
    print(f"index: {page}")
    if ok:
        print(f"\nportfolio-verify: PASS -- {len(verifications)} report(s) still verify")
        return EXIT_OK
    print("\nportfolio-verify: FAIL -- at least one report no longer verifies", file=sys.stderr)
    return EXIT_VERIFY_FAIL


def _cmd_cards(args: argparse.Namespace) -> int:
    current = write_cards(Path(args.out), check=args.check)
    if args.json:
        _emit_json({"command": "cards", "ok": current, "out": args.out, "check": args.check})
    elif args.check:
        print("responsible-AI cards: current" if current else "responsible-AI cards: DRIFT")
    else:
        print(f"wrote model and data cards: {args.out}")
    return EXIT_OK if current else EXIT_VERIFY_FAIL


def build_parser() -> argparse.ArgumentParser:
    # ``--json`` is understood both before the subcommand (on the top parser) and
    # after it (via this shared parent), so `receipts --json run …` and
    # `receipts run … --json` behave the same. The parent uses a suppressed
    # default so a subcommand parse never resets a `--json` already seen on the
    # top parser; the top parser carries the real default.
    json_help = "emit one machine-readable JSON object instead of human-readable lines"
    json_parent = argparse.ArgumentParser(add_help=False)
    json_parent.add_argument(
        "--json", action="store_true", default=argparse.SUPPRESS, help=json_help
    )

    parser = argparse.ArgumentParser(
        prog="receipts",
        description="Draft funder outcome reports where every number is a receipt.",
    )
    parser.add_argument("--json", action="store_true", default=False, help=json_help)
    parser.add_argument("--version", action="version", version=f"receipts {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    run_parser = sub.add_parser(
        "run", help="compute, draft, gate, and write the report", parents=[json_parent]
    )
    run_parser.add_argument("--config", required=True, help="path to the report spec TOML")
    run_parser.add_argument("--out", default="out", help="output directory")
    run_parser.add_argument(
        "--allow-cloud-drafting",
        action="store_true",
        help="authorize the config-enabled Bedrock drafter for this run",
    )
    run_parser.add_argument(
        "--reproducible",
        action="store_true",
        help="use a fixed timestamp so receipts are byte-for-byte reproducible",
    )
    run_parser.add_argument(
        "--ledger",
        default=None,
        help="path to the append-only export ledger (default: <out>/../export-ledger.jsonl)",
    )
    run_parser.add_argument(
        "--recipient",
        default=None,
        help="who the report was exported to, recorded in the export ledger",
    )
    run_parser.add_argument(
        "--locale",
        default="en",
        choices=("en", "es"),
        help="language for the report's prose and labels (figures are unchanged)",
    )
    run_parser.add_argument(
        "--format",
        dest="document_format",
        default="md",
        choices=("md", "docx"),
        help="md (the default) writes report.md; docx also writes report.docx beside it, "
        "rendered from report.md and gated again on the document's own bytes",
    )
    run_parser.add_argument(
        "--sign-key-file",
        help="path to a key file; adds a keyed-BLAKE2b signature to bundle.json",
    )
    run_parser.add_argument(
        "--approved-by",
        metavar="NAME",
        help="record NAME as the human approver, non-interactively (for CI); "
        "skips the interactive sign-off prompt",
    )
    run_parser.add_argument(
        "--approve",
        action="append",
        metavar="ROLE:NAME",
        help="record a sign-off for one role the spec's [approval] policy requires, as ROLE:NAME; repeat once per role",
    )
    run_parser.add_argument(
        "--yes",
        "--no-confirm",
        dest="no_confirm",
        action="store_true",
        help="skip the interactive sign-off prompt; requires --approved-by, "
        "otherwise the export aborts with no approver",
    )
    run_parser.add_argument(
        "--explain",
        action="store_true",
        help=(
            "when the gate refuses, say why each number missed and which receipted "
            "displays are nearest. Advice only; the refusal and the exit code stand"
        ),
    )
    run_parser.set_defaults(func=_cmd_run)

    mcp_parser = sub.add_parser(
        "mcp",
        help="serve audit, verify, trace and the publishable figures to a drafting "
        "tool over stdio (read-only: no export, no approval, no network)",
    )
    mcp_parser.add_argument("--reproducible", action="store_true", help=argparse.SUPPRESS)
    mcp_parser.set_defaults(func=_cmd_mcp)

    audit_parser = sub.add_parser(
        "audit",
        help="check a narrative against the figures the report may publish",
        parents=[json_parent],
    )
    audit_parser.add_argument("--config", required=True, help="path to the report spec TOML")
    audit_parser.add_argument("--narrative", required=True, help="narrative text to check")
    audit_parser.add_argument(
        "--explain",
        action="store_true",
        help=(
            "diagnose each failing number: the nearest receipted displays and why they "
            "did not match. Advice only; the verdict and the exit code are unchanged"
        ),
    )
    audit_parser.add_argument(
        "--fixes-out",
        help="write a reviewable fix plan (JSON) for the diagnosed spans; implies --explain",
    )
    audit_parser.add_argument(
        "--apply-fixes",
        help=(
            "apply a reviewed fix plan, substituting only exact receipted displays, "
            "then re-run the gate over the result"
        ),
    )
    audit_parser.add_argument(
        "--fixed-out",
        help="where to write the fixed narrative; required with --apply-fixes",
    )
    audit_parser.add_argument("--reproducible", action="store_true", help=argparse.SUPPRESS)
    audit_parser.set_defaults(func=_cmd_audit)

    verify_parser = sub.add_parser(
        "verify",
        help="re-derive a receipts manifest from the spec and data",
        parents=[json_parent],
    )
    verify_parser.add_argument("--config", required=True, help="path to the report spec TOML")
    verify_target = verify_parser.add_mutually_exclusive_group(required=True)
    verify_target.add_argument("--receipts", help="path to the receipts.json manifest to verify")
    verify_target.add_argument(
        "--bundle",
        help="path to an exported bundle directory to verify whole "
        "(receipts, artifact digests, and narrative grounding)",
    )
    verify_parser.add_argument("--reproducible", action="store_true", help=argparse.SUPPRESS)
    verify_parser.set_defaults(func=_cmd_verify)

    verify_ledger_parser = sub.add_parser(
        "verify-ledger",
        help="check the hash-chained export ledger for tampering",
        parents=[json_parent],
    )
    verify_ledger_parser.add_argument(
        "--ledger", required=True, help="path to the export-ledger.jsonl to check"
    )
    verify_ledger_parser.set_defaults(func=_cmd_verify_ledger)

    verify_bundle_parser = sub.add_parser(
        "verify-bundle",
        help="recompute the bundle manifest over an output directory and fail on tamper",
        parents=[json_parent],
    )
    verify_bundle_parser.add_argument(
        "--dir", required=True, help="the output directory containing bundle.json"
    )
    verify_bundle_parser.add_argument(
        "--sign-key-file",
        help="path to the key file the bundle was signed with, to verify the signature",
    )
    verify_bundle_parser.set_defaults(func=_cmd_verify_bundle)

    diff_parser = sub.add_parser(
        "diff",
        help="compare two receipts manifests and report what moved and why",
        parents=[json_parent],
    )
    diff_parser.add_argument("prior", help="path to the prior cycle's receipts.json")
    diff_parser.add_argument("current", help="path to the current cycle's receipts.json")
    diff_parser.add_argument("--out", help="write the diff markdown here instead of stdout")
    diff_parser.set_defaults(func=_cmd_diff)

    eval_parser = sub.add_parser(
        "eval", help="score the drafted narrative's grounding", parents=[json_parent]
    )
    eval_parser.add_argument("--config", required=True, help="path to the report spec TOML")
    eval_parser.add_argument("--out", help="write the report here instead of stdout")
    eval_parser.set_defaults(func=_cmd_eval)

    init_parser = sub.add_parser(
        "init",
        help="scaffold a starter metric spec from an export's columns",
        parents=[json_parent],
    )
    init_parser.add_argument("--data", required=True, help="path to the export CSV to inspect")
    init_parser.add_argument("--title", help="report title to write into the scaffold")
    init_parser.add_argument("--out", help="write the spec here instead of stdout")
    init_parser.set_defaults(func=_cmd_init)

    map_parser = sub.add_parser(
        "map",
        help="map funder metric requirements to source columns for human review",
        parents=[json_parent],
    )
    map_parser.add_argument("--data", required=True, help="path to the schema-variant CSV")
    map_parser.add_argument(
        "--requirements", required=True, help="path to the funder requirements JSON"
    )
    map_parser.add_argument("--out", help="write the review queue JSON here")
    map_parser.set_defaults(func=_cmd_map)

    restate_parser = sub.add_parser(
        "restate",
        help="write a restatement linked to a verified prior bundle",
        parents=[json_parent],
    )
    restate_parser.add_argument("--prior-config", required=True)
    restate_parser.add_argument("--prior-bundle", required=True)
    restate_parser.add_argument("--config", required=True, help="current report spec TOML")
    restate_parser.add_argument("--reason", required=True)
    restate_parser.add_argument(
        "--approved-by",
        metavar="NAME",
        help="record NAME as the single human approver; refused when the spec's "
        "[approval] policy names roles",
    )
    restate_parser.add_argument(
        "--approve",
        action="append",
        metavar="ROLE:NAME",
        help="record a sign-off for one role the spec's [approval] policy requires, as ROLE:NAME; repeat once per role",
    )
    restate_parser.add_argument("--out", required=True)
    restate_parser.add_argument("--reproducible", action="store_true")
    restate_parser.set_defaults(func=_cmd_restate)

    migrate_parser = sub.add_parser(
        "migrate-check",
        help="compare reviewed metrics across two data-system exports",
        parents=[json_parent],
    )
    migrate_parser.add_argument("--before-config", required=True)
    migrate_parser.add_argument("--after-config", required=True)
    migrate_parser.add_argument("--approved-by", required=True, metavar="NAME")
    migrate_parser.add_argument("--out", required=True)
    migrate_parser.add_argument("--reproducible", action="store_true")
    migrate_parser.set_defaults(func=_cmd_migrate_check)

    requirements_parser = sub.add_parser(
        "requirements-diff",
        help="classify funder requirement changes by stable ID",
        parents=[json_parent],
    )
    requirements_parser.add_argument("--prior", required=True)
    requirements_parser.add_argument("--current", required=True)
    requirements_parser.add_argument("--out", required=True)
    requirements_parser.set_defaults(func=_cmd_requirements_diff)

    contract_parser = sub.add_parser(
        "contract-check",
        help="package receipted contract milestone evidence",
        parents=[json_parent],
    )
    contract_parser.add_argument("--config", required=True)
    contract_parser.add_argument("--contract", required=True)
    contract_parser.add_argument(
        "--approved-by",
        metavar="NAME",
        help="record NAME as the single human approver; refused when the spec's "
        "[approval] policy names roles",
    )
    contract_parser.add_argument(
        "--approve",
        action="append",
        metavar="ROLE:NAME",
        help="record a sign-off for one role the spec's [approval] policy requires, as ROLE:NAME; repeat once per role",
    )
    contract_parser.add_argument("--out", required=True)
    contract_parser.add_argument("--reproducible", action="store_true")
    contract_parser.set_defaults(func=_cmd_contract_check)

    preview_parser = sub.add_parser(
        "suppress-preview",
        help="preview what suppression policies would withhold, writing nothing",
        parents=[json_parent],
    )
    preview_parser.add_argument("--config", required=True)
    preview_parser.add_argument(
        "--threshold",
        type=int,
        action="append",
        metavar="N",
        help="an uncited threshold to preview; repeatable",
    )
    preview_parser.add_argument(
        "--policy",
        action="append",
        metavar="ID",
        help="a registered policy id to preview; repeatable",
    )
    preview_parser.add_argument(
        "--local",
        action="store_true",
        help="include the withheld values; omit for the shareable profile",
    )
    preview_parser.add_argument("--reproducible", action="store_true")
    preview_parser.set_defaults(func=_cmd_suppress_preview)

    rollup_parser = sub.add_parser(
        "rollup",
        help="compose a count from verified partner bundles",
        parents=[json_parent],
    )
    rollup_parser.add_argument("--plan", required=True)
    rollup_parser.add_argument("--approved-by", required=True, metavar="NAME")
    rollup_parser.add_argument("--out", required=True)
    rollup_parser.add_argument("--reproducible", action="store_true")
    rollup_parser.set_defaults(func=_cmd_rollup)

    equity_parser = sub.add_parser(
        "equity-review",
        help="package allowlisted subgroup receipts after whole-report suppression",
        parents=[json_parent],
    )
    equity_parser.add_argument("--config", required=True)
    equity_parser.add_argument("--plan", required=True)
    equity_parser.add_argument(
        "--approved-by",
        metavar="NAME",
        help="record NAME as the single human approver; refused when the spec's "
        "[approval] policy names roles",
    )
    equity_parser.add_argument(
        "--approve",
        action="append",
        metavar="ROLE:NAME",
        help="record a sign-off for one role the spec's [approval] policy requires, as ROLE:NAME; repeat once per role",
    )
    equity_parser.add_argument("--out", required=True)
    equity_parser.add_argument("--reproducible", action="store_true")
    equity_parser.set_defaults(func=_cmd_equity_review)

    verify_workflow_parser = sub.add_parser(
        "verify-workflow",
        help="validate a versioned evidence-workflow artifact",
        parents=[json_parent],
    )
    verify_workflow_parser.add_argument("--artifact", required=True)
    verify_workflow_parser.set_defaults(func=_cmd_verify_workflow)

    portfolio_parser = sub.add_parser(
        "portfolio",
        help="run several report specs through the ordinary export path as one batch",
        parents=[json_parent],
    )
    portfolio_parser.add_argument(
        "--specs",
        required=True,
        nargs="+",
        metavar="TOML",
        help="the report specs to export, in any order; the batch runs them by path",
    )
    portfolio_parser.add_argument(
        "--out", required=True, help="the portfolio directory every report writes under"
    )
    portfolio_parser.add_argument(
        "--ledger",
        default=None,
        help="the shared append-only export ledger (default: <out>/export-ledger.jsonl)",
    )
    portfolio_parser.add_argument(
        "--approved-by",
        metavar="NAME",
        help="record NAME as the human approver of every report in the batch",
    )
    portfolio_parser.add_argument(
        "--approve",
        action="append",
        metavar="ROLE:NAME",
        help="record a sign-off for one role a spec's [approval] policy requires; "
        "repeat once per role",
    )
    portfolio_parser.add_argument(
        "--recipient",
        default=None,
        help="who the reports were exported to, recorded in the shared ledger",
    )
    portfolio_parser.add_argument(
        "--locale", default="en", choices=("en", "es"), help="language for report prose"
    )
    portfolio_parser.add_argument(
        "--sign-key-file", help="path to a key file; signs every bundle in the batch"
    )
    portfolio_parser.add_argument("--reproducible", action="store_true", help=argparse.SUPPRESS)
    portfolio_parser.set_defaults(func=_cmd_portfolio)

    portfolio_verify_parser = sub.add_parser(
        "portfolio-verify",
        help="re-verify every bundle in a portfolio and render the auditor's index",
        parents=[json_parent],
    )
    portfolio_verify_parser.add_argument(
        "--dir", required=True, help="the portfolio directory `receipts portfolio` wrote"
    )
    portfolio_verify_parser.add_argument(
        "--locale", default="en", choices=("en", "es"), help="language for the index page"
    )
    portfolio_verify_parser.add_argument(
        "--reproducible", action="store_true", help=argparse.SUPPRESS
    )
    portfolio_verify_parser.set_defaults(func=_cmd_portfolio_verify)

    cards_parser = sub.add_parser(
        "cards", help="generate or check the model and data cards", parents=[json_parent]
    )
    cards_parser.add_argument("--out", default="docs", help="card output directory")
    cards_parser.add_argument("--check", action="store_true", help="fail if committed cards drift")
    cards_parser.set_defaults(func=_cmd_cards)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    func = args.func
    try:
        result: int = func(args)
    except (DraftingPolicyError, WorkflowError) as exc:
        label = "drafting policy" if isinstance(exc, DraftingPolicyError) else "workflow"
        print(f"{label}: FAIL — {exc}", file=sys.stderr)
        return EXIT_VERIFY_FAIL
    except CoverageError as exc:
        # An unusable requirement binding is an authoring defect in the spec or
        # the requirement document, not a coverage result. It exits on the
        # coverage code because nothing was exported, and it names what is wrong
        # rather than reporting zero requirements answered -- which would be a
        # measurement of a set that was never read.
        print(f"requirement coverage: FAIL — {exc}", file=sys.stderr)
        return EXIT_COVERAGE_FAIL
    except PortfolioError as exc:
        # An unreadable or contradictory portfolio is a refusal, not an empty
        # portfolio: a verifier that read no reports has verified nothing, and a
        # batch whose specs collide has not been run.
        print(f"portfolio: FAIL -- {exc}", file=sys.stderr)
        return EXIT_VERIFY_FAIL
    except ApprovalError as exc:
        # A sign-off that does not satisfy the spec's policy exits on the
        # approval code, because nothing was written and the reason is the same
        # one `run` reports: the export was not approved. `run` handles this
        # itself so its --json mode still emits exactly one object; the workflow
        # commands land here.
        print(f"approval: FAIL — {exc}", file=sys.stderr)
        return EXIT_APPROVAL_FAIL
    except UnknownPolicyError as exc:
        # Fails closed, naming the id. Falling back to the default here would
        # let a typo silently preview -- and later record -- a different policy
        # than the one the operator asked for.
        print(f"suppression policy: FAIL — {exc}", file=sys.stderr)
        return EXIT_GATE_FAIL
    return result


if __name__ == "__main__":
    sys.exit(main())
