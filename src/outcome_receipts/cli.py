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
  eval    score the drafted narrative's grounding and write the eval report

argparse only; no runtime dependency beyond the standard library.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from outcome_receipts import __version__
from outcome_receipts.charts import Chart, render_charts
from outcome_receipts.clock import Clock, FixedClock, SystemClock
from outcome_receipts.comparison import ComparisonResult, compute_comparison
from outcome_receipts.config import Spec, load_spec
from outcome_receipts.draft import draft
from outcome_receipts.engine import compute_figures, read_csv
from outcome_receipts.evaluate import evaluate
from outcome_receipts.grounding import ground
from outcome_receipts.ledger import append_export, verify_chain
from outcome_receipts.models import Figure, GroundingResult
from outcome_receipts.provenance import Provenance
from outcome_receipts.report import (
    receipts_manifest,
    render_eval_markdown,
    render_report,
)
from outcome_receipts.scaffold import scaffold_spec
from outcome_receipts.trace import render_trace_html
from outcome_receipts.verify import verify_manifest

# The chart subdirectory under the output directory, referenced from the report.
_CHART_DIR = "charts"


def _clock(*, reproducible: bool) -> Clock:
    return FixedClock() if reproducible else SystemClock()


def _load_and_compute(
    config: str, *, reproducible: bool
) -> tuple[Spec, list[dict[str, str]], list[Figure]]:
    spec = load_spec(config)
    rows = read_csv(spec.data_path)
    figures = compute_figures(
        rows,
        spec.report.metrics,
        clock=_clock(reproducible=reproducible),
        data_checks=spec.report.data_checks,
    )
    return spec, rows, figures


def _compute_all(
    config: str, *, reproducible: bool
) -> tuple[Spec, list[dict[str, str]], list[Figure], ComparisonResult | None]:
    """Compute the full figure set, including any comparison figures.

    The narrative metrics and the comparison are computed over the same data, so a
    caller (``run`` and ``verify`` alike) sees one figure list whose receipts cover
    every number the report can claim.
    """

    spec, rows, figures = _load_and_compute(config, reproducible=reproducible)
    comparison: ComparisonResult | None = None
    if spec.report.comparison is not None:
        comparison = compute_comparison(
            rows, spec.report.comparison, clock=_clock(reproducible=reproducible)
        )
        figures = [*figures, *comparison.figures]
    return spec, rows, figures, comparison


def _claims_text(comparison: ComparisonResult | None, charts: Sequence[Chart]) -> str:
    """The numbers a comparison and charts assert, as plain text for the gate.

    Only the figure displays go here, never category labels or SVG geometry, so
    the gate checks the numbers a chart or table claims and binds each to a
    receipt. A rendered number that is not a figure display would be unbound and
    block export, which is what catches a separate, ungrounded data path.
    """

    parts: list[str] = []
    if comparison is not None:
        parts.append(" ".join(figure.display for figure in comparison.figures))
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
    """

    if args.approved_by is not None:
        name = args.approved_by.strip()
        return name or None

    if args.no_confirm or not sys.stdin.isatty():
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
    name = entered.strip()
    return name or None


def _cmd_run(args: argparse.Namespace) -> int:
    spec, _rows, figures, comparison = _compute_all(args.config, reproducible=args.reproducible)

    narrative = draft(spec.report, figures)
    charts = render_charts(spec.report.charts, figures)

    narrative_result = ground(narrative, figures)
    claims_result = ground(_claims_text(comparison, charts), figures)

    print(f"figures computed: {len(figures)}")
    print(
        f"numbers in narrative: {narrative_result.total} "
        f"(bound {len(narrative_result.bound)}, unbound {len(narrative_result.unbound)})"
    )
    print(
        f"chart and comparison numbers: {claims_result.total} "
        f"(bound {len(claims_result.bound)}, unbound {len(claims_result.unbound)})"
    )

    if not (narrative_result.ok and claims_result.ok):
        print("\ngrounding gate: FAIL — refusing to export", file=sys.stderr)
        for span in (*narrative_result.unbound, *claims_result.unbound):
            print(f"  unverifiable number: {span.text!r}", file=sys.stderr)
        return 2

    # Human sign-off gate. The grounding gate proves every number traces to a
    # receipt; this gate records that a named person approved the export. It runs
    # only after the grounding gate PASSes and before any file is written, so a
    # missing sign-off aborts fail-closed with nothing on disk.
    approver = _approver(spec.report.title, narrative_result, claims_result, args)
    if approver is None:
        print("export aborted: no approver sign-off", file=sys.stderr)
        return 3

    provenance = Provenance(
        numbers_bound=len(narrative_result.bound) + len(claims_result.bound),
        numbers_unbound=0,
        approved_by=approver,
        approved_at=_clock(reproducible=args.reproducible).now_iso(),
    )

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / "report.md"
    manifest_path = out_dir / "receipts.json"
    trace_path = out_dir / "trace.html"
    if charts:
        chart_dir = out_dir / _CHART_DIR
        chart_dir.mkdir(parents=True, exist_ok=True)
        for chart in charts:
            (chart_dir / f"{chart.chart_id}.svg").write_text(chart.svg, encoding="utf-8")
    report_path.write_text(
        render_report(
            spec.report.title,
            narrative,
            figures,
            comparison=comparison,
            charts=charts,
            chart_dir=_CHART_DIR,
            provenance=provenance,
        ),
        encoding="utf-8",
    )
    manifest_path.write_text(receipts_manifest(figures, provenance=provenance), encoding="utf-8")
    trace_path.write_text(
        render_trace_html(spec.report.title, figures, provenance=provenance),
        encoding="utf-8",
    )

    ledger_path = Path(args.ledger) if args.ledger else out_dir.parent / "export-ledger.jsonl"
    entry = append_export(
        ledger_path,
        report_title=spec.report.title,
        manifest_json_or_hash=manifest_path.read_text(encoding="utf-8"),
        recipient=args.recipient,
        clock=_clock(reproducible=args.reproducible),
    )

    print("\ngrounding gate: PASS")
    print(f"  report:   {report_path}")
    print(f"  receipts: {manifest_path}")
    print(f"  trace:    {trace_path}")
    if charts:
        print(f"  charts:   {out_dir / _CHART_DIR} ({len(charts)} SVG)")
    print(f"  ledger:   {ledger_path} (entry {entry.index}, hash {entry.entry_hash})")
    return 0


def _cmd_audit(args: argparse.Namespace) -> int:
    _spec, _rows, figures = _load_and_compute(args.config, reproducible=args.reproducible)
    narrative = Path(args.narrative).read_text(encoding="utf-8")
    result = ground(narrative, figures)
    print(f"numbers: {result.total}, bound: {len(result.bound)}, unbound: {len(result.unbound)}")
    for span in result.unbound:
        print(f"  unverifiable: {span.text!r} at offset {span.start}")
    return 0 if result.ok else 1


def _cmd_verify(args: argparse.Namespace) -> int:
    _spec, _rows, figures, _comparison = _compute_all(args.config, reproducible=args.reproducible)
    manifest = json.loads(Path(args.receipts).read_text(encoding="utf-8"))
    result = verify_manifest(figures, manifest)

    print(
        f"receipts checked: {len(result.checks)} "
        f"(re-derived {result.n_ok}, drift {len(result.checks) - result.n_ok})"
    )
    for check in result.checks:
        status = "ok" if check.ok else "DRIFT"
        print(f"  [{status}] {check.metric_id}: {check.detail}")
    if result.ok:
        print("\nverify: PASS — every receipt re-derives from the data")
        return 0
    print("\nverify: FAIL — a receipt does not match the data", file=sys.stderr)
    return 1


def _cmd_verify_ledger(args: argparse.Namespace) -> int:
    ledger_path = Path(args.ledger)
    problems = verify_chain(ledger_path)
    if not problems:
        print(f"export ledger: {ledger_path}")
        print("verify-ledger: PASS — the export chain is intact")
        return 0
    print(f"export ledger: {ledger_path}", file=sys.stderr)
    for problem in problems:
        print(f"  {problem}", file=sys.stderr)
    print("\nverify-ledger: FAIL — the export chain is broken", file=sys.stderr)
    return 1


def _cmd_eval(args: argparse.Namespace) -> int:
    spec, _rows, figures = _load_and_compute(args.config, reproducible=True)
    narrative = draft(spec.report, figures)
    result = ground(narrative, figures)
    report = evaluate(result)
    markdown = render_eval_markdown(report, dataset=Path(args.config).parent.name)
    if args.out:
        Path(args.out).write_text(markdown, encoding="utf-8")
        print(f"wrote eval report: {args.out}")
    else:
        print(markdown)
    return 0 if report.gate_pass else 1


def _cmd_init(args: argparse.Namespace) -> int:
    spec_text = scaffold_spec(Path(args.data), title=args.title)
    if args.out:
        out_path = Path(args.out)
        out_path.write_text(spec_text, encoding="utf-8")
        print(f"wrote starter spec: {out_path}")
        print(
            "every metric is an empty stub; fill value_sql/slice_sql/definition "
            "before `receipts run`"
        )
    else:
        print(spec_text, end="")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="receipts",
        description="Draft funder outcome reports where every number is a receipt.",
    )
    parser.add_argument("--version", action="version", version=f"receipts {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    run_parser = sub.add_parser("run", help="compute, draft, gate, and write the report")
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

    audit_parser = sub.add_parser("audit", help="run the grounding gate over a narrative file")
    audit_parser.add_argument("--config", required=True, help="path to the report spec TOML")
    audit_parser.add_argument("--narrative", required=True, help="narrative text to check")
    audit_parser.add_argument("--reproducible", action="store_true", help=argparse.SUPPRESS)
    audit_parser.set_defaults(func=_cmd_audit)

    verify_parser = sub.add_parser(
        "verify", help="re-derive a receipts manifest from the spec and data"
    )
    verify_parser.add_argument("--config", required=True, help="path to the report spec TOML")
    verify_parser.add_argument(
        "--receipts", required=True, help="path to the receipts.json manifest to verify"
    )
    verify_parser.add_argument("--reproducible", action="store_true", help=argparse.SUPPRESS)
    verify_parser.set_defaults(func=_cmd_verify)

    verify_ledger_parser = sub.add_parser(
        "verify-ledger", help="check the hash-chained export ledger for tampering"
    )
    verify_ledger_parser.add_argument(
        "--ledger", required=True, help="path to the export-ledger.jsonl to check"
    )
    verify_ledger_parser.set_defaults(func=_cmd_verify_ledger)

    eval_parser = sub.add_parser("eval", help="score the drafted narrative's grounding")
    eval_parser.add_argument("--config", required=True, help="path to the report spec TOML")
    eval_parser.add_argument("--out", help="write the report here instead of stdout")
    eval_parser.set_defaults(func=_cmd_eval)

    init_parser = sub.add_parser(
        "init", help="scaffold a starter metric spec from an export's columns"
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
