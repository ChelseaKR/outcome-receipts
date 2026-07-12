"""Command-line interface.

Commands:
  init    inspect an export and scaffold a starter TOML metric spec (empty stubs
          that fail loudly until a human fills in the SQL and definitions)
  run     compute figures, draft the narrative, run the grounding gate, and write
          the report, receipts manifest, and trace view (export blocked if any
          number is unbound)
  audit   run the grounding gate over an existing narrative file and report unbound
          numbers
  verify  re-derive every receipt in a manifest from the spec and data, and fail
          on any drift
  verify-ledger
          re-hash the append-only export ledger and fail if the chain is broken
  verify-bundle
          recompute the bundle manifest over an output directory and fail on any
          member that was tampered, is missing, or is extra
  diff    compare two receipts manifests from different reporting cycles and report
          which figures moved, were added, or removed, and why
  eval    score the drafted narrative's grounding and write the eval report

Every command exits with a code from the contract below, and ``--json`` makes any
command emit one machine-readable object instead of the human-readable lines. The
exit code is the same either way; the JSON is purely presentational.

argparse only; no runtime dependency beyond the standard library.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from outcome_receipts import __version__
from outcome_receipts.bundle import bundle_manifest
from outcome_receipts.bundle import verify_bundle as verify_signed_bundle
from outcome_receipts.charts import Chart, render_charts
from outcome_receipts.clock import Clock, FixedClock, SystemClock
from outcome_receipts.comparison import (
    ComparisonResult,
    ReconciliationResult,
    compute_comparison,
    compute_reconciliation,
)
from outcome_receipts.config import Spec, load_spec
from outcome_receipts.diff import diff_manifests
from outcome_receipts.draft import draft, draft_template
from outcome_receipts.engine import compute_figures, read_csv_meta
from outcome_receipts.evaluate import EvalReport, evaluate
from outcome_receipts.grounding import ground
from outcome_receipts.ledger import LedgerEntry, append_export, verify_chain
from outcome_receipts.models import Figure, GroundingResult, NumericSpan, TemplateSpec
from outcome_receipts.provenance import Provenance
from outcome_receipts.report import (
    receipts_manifest,
    render_diff_markdown,
    render_eval_markdown,
    render_report,
)
from outcome_receipts.scaffold import scaffold_spec
from outcome_receipts.trace import render_trace_html
from outcome_receipts.verify import BundleResult, VerifyResult, verify_bundle, verify_manifest

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
"""An audit, verify, verify-ledger, or eval check failed: a number is unbound, a
receipt or artifact drifted, the export ledger's hash chain is broken, or the
eval gate did not pass."""

EXIT_GATE_FAIL = 2
"""The grounding gate refused to export: ``run`` found an unbound number and wrote
nothing."""

EXIT_APPROVAL_FAIL = 3
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


def _export_outputs(
    args: argparse.Namespace,
    spec: Spec,
    figures: Sequence[Figure],
    narrative: str,
    charts: Sequence[Chart],
    comparison: ComparisonResult | None,
    reconciliation: ReconciliationResult | None,
    provenance: Provenance,
    *,
    out_dir: Path | None = None,
    title: str | None = None,
    ledger_path: Path | None = None,
) -> tuple[dict[str, str | None], LedgerEntry, Path]:
    """Write the report, trace, charts, and manifest, then append the export ledger.

    Every artifact string is built in memory first so the manifest, written last,
    can hash its siblings. The manifest never hashes itself; the report embeds
    the receipts section but not the artifact digests, so the hash relation is
    one-directional (no circularity). See ADR 0006. Write order: charts, then
    report, then trace, then the manifest, then the ledger entry.
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
        locale=args.locale,
    )
    trace_text = render_trace_html(
        export_title, figures, provenance=provenance, comparison=comparison
    )

    digests = {
        "report.md": _sha256(report_text),
        "trace.html": _sha256(trace_text),
    }
    for chart in charts:
        digests[f"{_CHART_DIR}/{chart.chart_id}.svg"] = _sha256(chart.svg)
    manifest_text = receipts_manifest(figures, provenance=provenance, artifacts=digests)

    out_dir = out_dir or Path(args.out)
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
    report_path.write_text(report_text, encoding="utf-8")
    trace_path.write_text(trace_text, encoding="utf-8")
    manifest_path.write_text(manifest_text, encoding="utf-8")

    ledger_path = ledger_path or (
        Path(args.ledger) if args.ledger else out_dir.parent / "export-ledger.jsonl"
    )
    entry = append_export(
        ledger_path,
        report_title=export_title,
        manifest_json_or_hash=manifest_text,
        recipient=args.recipient,
        clock=_clock(reproducible=args.reproducible),
    )
    return outputs, entry, ledger_path


def _draft_templates(
    spec: Spec, figures: Sequence[Figure]
) -> list[tuple[TemplateSpec, str, GroundingResult]]:
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


def _print_gate_failure(
    claims_result: GroundingResult,
    drafts: Sequence[tuple[TemplateSpec, str, GroundingResult]],
) -> None:
    print("\ngrounding gate: FAIL — refusing to export", file=sys.stderr)
    for span in claims_result.unbound:
        print(f"  unverifiable number: {span.text!r}", file=sys.stderr)
    for template, _narrative, result in drafts:
        for span in result.unbound:
            print(
                f"  unverifiable number in {template.template_id!r}: {span.text!r}",
                file=sys.stderr,
            )


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
) -> tuple[list[tuple[TemplateSpec, dict[str, str | None], LedgerEntry]], Path, bool]:
    base_out = Path(args.out)
    fan_out = bool(spec.report.templates)
    ledger_path = Path(args.ledger) if args.ledger else base_out.parent / "export-ledger.jsonl"
    written: list[tuple[TemplateSpec, dict[str, str | None], LedgerEntry]] = []
    for template, narrative, result in drafts:
        provenance = Provenance(
            numbers_bound=len(result.bound) + len(claims_result.bound),
            numbers_unbound=0,
            approved_by=approver,
            approved_at=approved_at,
        )
        out_dir = base_out / template.template_id if fan_out else base_out
        outputs, entry, _ = _export_outputs(
            args,
            spec,
            figures,
            narrative,
            charts,
            comparison,
            reconciliation,
            provenance,
            out_dir=out_dir,
            title=template.title,
            ledger_path=ledger_path,
        )
        bundle_path = out_dir / _BUNDLE_NAME
        bundle_path.write_text(bundle_manifest(_bundle_members(out_dir), key=key), encoding="utf-8")
        outputs["bundle"] = str(bundle_path)
        written.append((template, outputs, entry))
    return written, ledger_path, fan_out


def _cmd_run(args: argparse.Namespace) -> int:
    spec, _rows, figures, comparison, reconciliation = _compute_all(
        args.config, reproducible=args.reproducible, quiet=args.json
    )
    charts = render_charts(spec.report.charts, figures)
    claims_result = ground(_claims_text(comparison, reconciliation, charts), figures)

    drafts = _draft_templates(spec, figures)
    combined_result = ground(" ".join(narrative for _t, narrative, _r in drafts), figures)
    gate_pass = claims_result.ok and all(result.ok for _t, _n, result in drafts)
    template_payload = {
        template.template_id: _grounding_payload(result) for template, _n, result in drafts
    }
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
        _print_template_summary(figures, claims_result, drafts)

    if not gate_pass:
        if args.json:
            payload = _run_payload(
                gate_pass=False,
                figures=figures,
                narrative_result=combined_result,
                claims_result=claims_result,
                outputs=failed_outputs,
                ledger=None,
                approval=None,
            )
            payload["templates"] = template_payload
            _emit_json(payload)
            return EXIT_GATE_FAIL
        _print_gate_failure(claims_result, drafts)
        return EXIT_GATE_FAIL

    approver = _approver(spec.report.title, combined_result, claims_result, args)
    if approver is None:
        if args.json:
            payload = _run_payload(
                gate_pass=True,
                figures=figures,
                narrative_result=combined_result,
                claims_result=claims_result,
                outputs=failed_outputs,
                ledger=None,
                approval=None,
            )
            payload["templates"] = template_payload
            _emit_json(payload)
        print("export aborted: no approver sign-off", file=sys.stderr)
        return EXIT_APPROVAL_FAIL

    key = _load_key(getattr(args, "sign_key_file", None))
    approved_at = _clock(reproducible=args.reproducible).now_iso()
    written, ledger_path, fan_out = _write_template_exports(
        args,
        spec,
        figures,
        comparison,
        reconciliation,
        charts,
        claims_result,
        drafts,
        approver,
        approved_at,
        key,
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
            figures=figures,
            narrative_result=combined_result,
            claims_result=claims_result,
            outputs=flat_outputs,
            ledger=ledgers[0] if not fan_out else {"entries": ledgers},
            approval={"approved_by": approver, "approved_at": approved_at},
        )
        payload["templates"] = template_payload
        _emit_json(payload)
        return EXIT_OK

    print("\ngrounding gate: PASS")
    print(f"  approved: {approver}")
    for template, outputs, entry in written:
        prefix = f"{template.template_id}: " if fan_out else ""
        print(f"  {prefix}report:   {outputs['report']}")
        print(f"  {prefix}receipts: {outputs['receipts']}")
        print(f"  {prefix}trace:    {outputs['trace']}")
        if outputs["charts"] is not None:
            print(f"  {prefix}charts:   {outputs['charts']} ({len(charts)} SVG)")
        print(f"  {prefix}bundle:   {outputs['bundle']} ({'signed' if key else 'digests-only'})")
        print(f"  {prefix}ledger:   {ledger_path} (entry {entry.index}, hash {entry.entry_hash})")
    return EXIT_OK


def _cmd_audit(args: argparse.Namespace) -> int:
    _spec, _rows, figures = _load_and_compute(
        args.config, reproducible=args.reproducible, quiet=args.json
    )
    narrative = Path(args.narrative).read_text(encoding="utf-8")
    result = ground(narrative, figures)

    if args.json:
        _emit_json(
            {
                "command": "audit",
                "ok": result.ok,
                "total": result.total,
                "bound": len(result.bound),
                "unbound": [_span_payload(span) for span in result.unbound],
            }
        )
        return EXIT_OK if result.ok else EXIT_VERIFY_FAIL

    print(f"numbers: {result.total}, bound: {len(result.bound)}, unbound: {len(result.unbound)}")
    for span in result.unbound:
        print(f"  unverifiable: {span.text!r} at offset {span.start}")
    return EXIT_OK if result.ok else EXIT_VERIFY_FAIL


def _verify_payload(result: VerifyResult) -> dict[str, object]:
    """The machine-readable record of a manifest ``verify`` invocation."""

    return {
        "command": "verify",
        "mode": "manifest",
        "ok": result.ok,
        "checks": [
            {"metric_id": check.metric_id, "ok": check.ok, "detail": check.detail}
            for check in result.checks
        ],
        "n_ok": result.n_ok,
        "drift": len(result.checks) - result.n_ok,
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
        "checks": [
            {"metric_id": check.metric_id, "ok": check.ok, "detail": check.detail}
            for check in manifest.checks
        ],
        "n_ok": manifest.n_ok,
        "drift": len(manifest.checks) - manifest.n_ok,
        "artifacts": [
            {"path": artifact.path, "ok": artifact.ok, "detail": artifact.detail}
            for artifact in result.artifacts
        ],
        "grounding": {
            "total": result.grounding.total,
            "bound": len(result.grounding.bound),
            "unbound": [_span_payload(span) for span in result.grounding.unbound],
        },
    }


def _cmd_verify(args: argparse.Namespace) -> int:
    _spec, _rows, figures, _comparison, _reconciliation = _compute_all(
        args.config, reproducible=args.reproducible, quiet=args.json
    )
    if args.bundle is not None:
        return _verify_bundle(args, figures)
    manifest = json.loads(Path(args.receipts).read_text(encoding="utf-8"))
    result = verify_manifest(figures, manifest)

    if args.json:
        _emit_json(_verify_payload(result))
        return EXIT_OK if result.ok else EXIT_VERIFY_FAIL

    print(
        f"receipts checked: {len(result.checks)} "
        f"(re-derived {result.n_ok}, drift {len(result.checks) - result.n_ok})"
    )
    for check in result.checks:
        status = "ok" if check.ok else "DRIFT"
        print(f"  [{status}] {check.metric_id}: {check.detail}")
    if result.ok:
        print("\nverify: PASS — every receipt re-derives from the data")
        return EXIT_OK
    print("\nverify: FAIL — a receipt does not match the data", file=sys.stderr)
    return EXIT_VERIFY_FAIL


def _cmd_verify_ledger(args: argparse.Namespace) -> int:
    ledger_path = Path(args.ledger)
    problems = verify_chain(ledger_path)

    if args.json:
        _emit_json(
            {
                "command": "verify-ledger",
                "ok": not problems,
                "ledger": str(ledger_path),
                "problems": list(problems),
            }
        )
        return EXIT_OK if not problems else EXIT_VERIFY_FAIL

    if not problems:
        print(f"export ledger: {ledger_path}")
        print("verify-ledger: PASS — the export chain is intact")
        return EXIT_OK
    print(f"export ledger: {ledger_path}", file=sys.stderr)
    for problem in problems:
        print(f"  {problem}", file=sys.stderr)
    print("\nverify-ledger: FAIL — the export chain is broken", file=sys.stderr)
    return EXIT_VERIFY_FAIL


def _verify_bundle(args: argparse.Namespace, figures: Sequence[Figure]) -> int:
    result = verify_bundle(Path(args.bundle), figures)
    manifest = result.manifest

    if args.json:
        _emit_json(_bundle_payload(result))
        return EXIT_OK if result.ok else EXIT_VERIFY_FAIL

    print(
        f"receipts checked: {len(manifest.checks)} "
        f"(re-derived {manifest.n_ok}, drift {len(manifest.checks) - manifest.n_ok})"
    )
    for check in manifest.checks:
        status = "ok" if check.ok else "DRIFT"
        print(f"  [{status}] {check.metric_id}: {check.detail}")
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

    if result.ok:
        print("\nverify: PASS — the whole bundle is coherent")
        return EXIT_OK
    print("\nverify: FAIL — the exported bundle does not verify", file=sys.stderr)
    for artifact in result.failed_artifacts:
        print(f"  offending file: {artifact.path} ({artifact.detail})", file=sys.stderr)
    if not result.grounding.ok:
        for span in result.grounding.unbound:
            print(f"  ungrounded number in report.md: {span.text!r}", file=sys.stderr)
    return EXIT_VERIFY_FAIL


def _eval_payload(report: EvalReport, *, out: str | None) -> dict[str, object]:
    """The machine-readable record of an ``eval`` invocation."""

    return {
        "command": "eval",
        "gate_pass": report.gate_pass,
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
    spec, _rows, figures = _load_and_compute(args.config, reproducible=True, quiet=args.json)
    narrative = draft(spec.report, figures)
    result = ground(narrative, figures)
    report = evaluate(result)
    markdown = render_eval_markdown(report, dataset=Path(args.config).parent.name)
    if args.out:
        Path(args.out).write_text(markdown, encoding="utf-8")

    if args.json:
        _emit_json(_eval_payload(report, out=args.out or None))
        return EXIT_OK if report.gate_pass else EXIT_VERIFY_FAIL

    if args.out:
        print(f"wrote eval report: {args.out}")
    else:
        print(markdown)
    return EXIT_OK if report.gate_pass else EXIT_VERIFY_FAIL


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
        "--yes",
        "--no-confirm",
        dest="no_confirm",
        action="store_true",
        help="skip the interactive sign-off prompt; requires --approved-by, "
        "otherwise the export aborts with no approver",
    )
    run_parser.set_defaults(func=_cmd_run)

    audit_parser = sub.add_parser(
        "audit", help="run the grounding gate over a narrative file", parents=[json_parent]
    )
    audit_parser.add_argument("--config", required=True, help="path to the report spec TOML")
    audit_parser.add_argument("--narrative", required=True, help="narrative text to check")
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

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    func = args.func
    result: int = func(args)
    return result


if __name__ == "__main__":
    sys.exit(main())
