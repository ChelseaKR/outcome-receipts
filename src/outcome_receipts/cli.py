"""Command-line interface.

Commands:
  run     compute figures, draft the narrative, run the grounding gate, and write
          the report, receipts manifest, and trace view (export blocked if any
          number is unbound)
  audit   run the grounding gate over an existing narrative file and report unbound
          numbers
  verify  re-derive every receipt in a manifest from the spec and data, and fail
          on any drift
  eval    score the drafted narrative's grounding and write the eval report

Every command exits with a code from the contract below, and ``--json`` makes any
command emit one machine-readable object instead of the human-readable lines. The
exit code is the same either way; the JSON is purely presentational.

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
from outcome_receipts.evaluate import EvalReport, evaluate
from outcome_receipts.grounding import ground
from outcome_receipts.models import Figure, GroundingResult, NumericSpan
from outcome_receipts.provenance import Provenance
from outcome_receipts.report import (
    receipts_manifest,
    render_eval_markdown,
    render_report,
)
from outcome_receipts.trace import render_trace_html
from outcome_receipts.verify import VerifyResult, verify_manifest

# The chart subdirectory under the output directory, referenced from the report.
_CHART_DIR = "charts"

# The exit-code contract, single-sourced. Every command returns one of these, and
# the value is the machine-readable contract callers script against; ``--json``
# only changes what is printed, never the code.
EXIT_OK = 0
"""Success: the command ran and the grounding gate (where one applies) passed."""

EXIT_VERIFY_FAIL = 1
"""An audit, verify, or eval check failed: a number is unbound, a receipt drifted,
or the eval gate did not pass."""

EXIT_GATE_FAIL = 2
"""The grounding gate refused to export: ``run`` found an unbound number and wrote
nothing."""


def _clock(*, reproducible: bool) -> Clock:
    return FixedClock() if reproducible else SystemClock()


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
    config: str, *, reproducible: bool
) -> tuple[Spec, list[dict[str, str]], list[Figure]]:
    spec = load_spec(config)
    rows = read_csv(spec.data_path)
    figures = compute_figures(rows, spec.report.metrics, clock=_clock(reproducible=reproducible))
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


def _run_payload(
    *,
    gate_pass: bool,
    figures: Sequence[Figure],
    narrative_result: GroundingResult,
    claims_result: GroundingResult,
    outputs: dict[str, str | None],
) -> dict[str, object]:
    """The machine-readable record of a ``run`` invocation."""

    return {
        "command": "run",
        "gate_pass": gate_pass,
        "figures": len(figures),
        "narrative": _grounding_payload(narrative_result),
        "claims": _grounding_payload(claims_result),
        "unbound": [
            _span_payload(span)
            for span in (*narrative_result.unbound, *claims_result.unbound)
        ],
        "outputs": outputs,
    }


def _cmd_run(args: argparse.Namespace) -> int:
    spec, _rows, figures, comparison = _compute_all(
        args.config, reproducible=args.reproducible
    )

    narrative = draft(spec.report, figures)
    charts = render_charts(spec.report.charts, figures)

    narrative_result = ground(narrative, figures)
    claims_result = ground(_claims_text(comparison, charts), figures)
    gate_pass = narrative_result.ok and claims_result.ok

    outputs: dict[str, str | None] = {
        "report": None,
        "receipts": None,
        "trace": None,
        "charts": None,
    }

    if gate_pass:
        provenance = Provenance(
            numbers_bound=len(narrative_result.bound) + len(claims_result.bound),
            numbers_unbound=0,
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
            outputs["charts"] = str(chart_dir)
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
        manifest_path.write_text(
            receipts_manifest(figures, provenance=provenance), encoding="utf-8"
        )
        trace_path.write_text(
            render_trace_html(spec.report.title, figures, provenance=provenance),
            encoding="utf-8",
        )
        outputs["report"] = str(report_path)
        outputs["receipts"] = str(manifest_path)
        outputs["trace"] = str(trace_path)

    if args.json:
        _emit_json(
            _run_payload(
                gate_pass=gate_pass,
                figures=figures,
                narrative_result=narrative_result,
                claims_result=claims_result,
                outputs=outputs,
            )
        )
        return EXIT_OK if gate_pass else EXIT_GATE_FAIL

    print(f"figures computed: {len(figures)}")
    print(f"numbers in narrative: {narrative_result.total} "
          f"(bound {len(narrative_result.bound)}, unbound {len(narrative_result.unbound)})")
    print(f"chart and comparison numbers: {claims_result.total} "
          f"(bound {len(claims_result.bound)}, unbound {len(claims_result.unbound)})")

    if not gate_pass:
        print("\ngrounding gate: FAIL — refusing to export", file=sys.stderr)
        for span in (*narrative_result.unbound, *claims_result.unbound):
            print(f"  unverifiable number: {span.text!r}", file=sys.stderr)
        return EXIT_GATE_FAIL

    print("\ngrounding gate: PASS")
    print(f"  report:   {outputs['report']}")
    print(f"  receipts: {outputs['receipts']}")
    print(f"  trace:    {outputs['trace']}")
    if outputs["charts"] is not None:
        print(f"  charts:   {outputs['charts']} ({len(charts)} SVG)")
    return EXIT_OK


def _cmd_audit(args: argparse.Namespace) -> int:
    _spec, _rows, figures = _load_and_compute(args.config, reproducible=args.reproducible)
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

    print(f"numbers: {result.total}, bound: {len(result.bound)}, "
          f"unbound: {len(result.unbound)}")
    for span in result.unbound:
        print(f"  unverifiable: {span.text!r} at offset {span.start}")
    return EXIT_OK if result.ok else EXIT_VERIFY_FAIL


def _verify_payload(result: VerifyResult) -> dict[str, object]:
    """The machine-readable record of a ``verify`` invocation."""

    return {
        "command": "verify",
        "ok": result.ok,
        "checks": [
            {"metric_id": check.metric_id, "ok": check.ok, "detail": check.detail}
            for check in result.checks
        ],
        "n_ok": result.n_ok,
        "drift": len(result.checks) - result.n_ok,
    }


def _cmd_verify(args: argparse.Namespace) -> int:
    _spec, _rows, figures, _comparison = _compute_all(
        args.config, reproducible=args.reproducible
    )
    manifest = json.loads(Path(args.receipts).read_text(encoding="utf-8"))
    result = verify_manifest(figures, manifest)

    if args.json:
        _emit_json(_verify_payload(result))
        return EXIT_OK if result.ok else EXIT_VERIFY_FAIL

    print(f"receipts checked: {len(result.checks)} "
          f"(re-derived {result.n_ok}, drift {len(result.checks) - result.n_ok})")
    for check in result.checks:
        status = "ok" if check.ok else "DRIFT"
        print(f"  [{status}] {check.metric_id}: {check.detail}")
    if result.ok:
        print("\nverify: PASS — every receipt re-derives from the data")
        return EXIT_OK
    print("\nverify: FAIL — a receipt does not match the data", file=sys.stderr)
    return EXIT_VERIFY_FAIL


def _eval_payload(report: EvalReport) -> dict[str, object]:
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
    }


def _cmd_eval(args: argparse.Namespace) -> int:
    spec, _rows, figures = _load_and_compute(args.config, reproducible=True)
    narrative = draft(spec.report, figures)
    result = ground(narrative, figures)
    report = evaluate(result)

    if args.json:
        _emit_json(_eval_payload(report))
        return EXIT_OK if report.gate_pass else EXIT_VERIFY_FAIL

    markdown = render_eval_markdown(report, dataset=Path(args.config).parent.name)
    if args.out:
        Path(args.out).write_text(markdown, encoding="utf-8")
        print(f"wrote eval report: {args.out}")
    else:
        print(markdown)
    return EXIT_OK if report.gate_pass else EXIT_VERIFY_FAIL


def build_parser() -> argparse.ArgumentParser:
    # ``--json`` is understood both before the subcommand (on the top parser) and
    # after it (via this shared parent), so `receipts --json run …` and
    # `receipts run … --json` behave the same. The parent uses a suppressed
    # default so a subcommand parse never resets a `--json` already seen on the
    # top parser; the top parser carries the real default.
    _JSON_HELP = "emit one machine-readable JSON object instead of human-readable lines"
    json_parent = argparse.ArgumentParser(add_help=False)
    json_parent.add_argument(
        "--json", action="store_true", default=argparse.SUPPRESS, help=_JSON_HELP
    )

    parser = argparse.ArgumentParser(
        prog="receipts",
        description="Draft funder outcome reports where every number is a receipt.",
    )
    parser.add_argument("--json", action="store_true", default=False, help=_JSON_HELP)
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
    verify_parser.add_argument(
        "--receipts", required=True, help="path to the receipts.json manifest to verify"
    )
    verify_parser.add_argument("--reproducible", action="store_true", help=argparse.SUPPRESS)
    verify_parser.set_defaults(func=_cmd_verify)

    eval_parser = sub.add_parser(
        "eval", help="score the drafted narrative's grounding", parents=[json_parent]
    )
    eval_parser.add_argument("--config", required=True, help="path to the report spec TOML")
    eval_parser.add_argument("--out", help="write the report here instead of stdout")
    eval_parser.set_defaults(func=_cmd_eval)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    func = args.func
    result: int = func(args)
    return result


if __name__ == "__main__":
    sys.exit(main())
