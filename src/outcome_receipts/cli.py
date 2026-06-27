"""Command-line interface.

Commands:
  run    compute figures, draft the narrative, run the grounding gate, and write
         the report and receipts manifest (export blocked if any number is unbound)
  audit  run the grounding gate over an existing narrative file and report unbound
         numbers
  eval   score the drafted narrative's grounding and write the eval report

argparse only; no runtime dependency beyond the standard library.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from outcome_receipts import __version__
from outcome_receipts.clock import FixedClock, SystemClock
from outcome_receipts.config import Spec, load_spec
from outcome_receipts.draft import draft
from outcome_receipts.engine import compute_figures, read_csv
from outcome_receipts.evaluate import evaluate
from outcome_receipts.grounding import ground
from outcome_receipts.models import Figure
from outcome_receipts.report import (
    receipts_manifest,
    render_eval_markdown,
    render_report,
)


def _load_and_compute(config: str, *, reproducible: bool) -> tuple[Spec, list[Figure]]:
    spec = load_spec(config)
    rows = read_csv(spec.data_path)
    clock = FixedClock() if reproducible else SystemClock()
    figures = compute_figures(rows, spec.report.metrics, clock=clock)
    return spec, figures


def _cmd_run(args: argparse.Namespace) -> int:
    spec, figures = _load_and_compute(args.config, reproducible=args.reproducible)
    narrative = draft(spec.report, figures)
    result = ground(narrative, figures)

    print(f"figures computed: {len(figures)}")
    print(f"numbers in narrative: {result.total} (bound {len(result.bound)}, "
          f"unbound {len(result.unbound)})")

    if not result.ok:
        print("\ngrounding gate: FAIL — refusing to export", file=sys.stderr)
        for span in result.unbound:
            print(f"  unverifiable number: {span.text!r} at offset {span.start}", file=sys.stderr)
        return 2

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / "report.md"
    manifest_path = out_dir / "receipts.json"
    report_path.write_text(
        render_report(spec.report.title, narrative, figures), encoding="utf-8"
    )
    manifest_path.write_text(receipts_manifest(figures), encoding="utf-8")
    print("\ngrounding gate: PASS")
    print(f"  report:   {report_path}")
    print(f"  receipts: {manifest_path}")
    return 0


def _cmd_audit(args: argparse.Namespace) -> int:
    _spec, figures = _load_and_compute(args.config, reproducible=args.reproducible)
    narrative = Path(args.narrative).read_text(encoding="utf-8")
    result = ground(narrative, figures)
    print(f"numbers: {result.total}, bound: {len(result.bound)}, "
          f"unbound: {len(result.unbound)}")
    for span in result.unbound:
        print(f"  unverifiable: {span.text!r} at offset {span.start}")
    return 0 if result.ok else 1


def _cmd_eval(args: argparse.Namespace) -> int:
    spec, figures = _load_and_compute(args.config, reproducible=True)
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
    run_parser.set_defaults(func=_cmd_run)

    audit_parser = sub.add_parser("audit", help="run the grounding gate over a narrative file")
    audit_parser.add_argument("--config", required=True, help="path to the report spec TOML")
    audit_parser.add_argument("--narrative", required=True, help="narrative text to check")
    audit_parser.add_argument("--reproducible", action="store_true", help=argparse.SUPPRESS)
    audit_parser.set_defaults(func=_cmd_audit)

    eval_parser = sub.add_parser("eval", help="score the drafted narrative's grounding")
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
