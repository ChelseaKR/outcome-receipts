"""A batch of report specs, and the single page an auditor enters through.

An organization does not publish one report. It publishes a grant report, a
board report, and a template per funder, each from its own spec, each run
separately. The receipts prove every figure in each one; nothing proves anything
about the set. An auditor holding five output directories has no page saying
which reports exist, which still verify, who signed each one off, and whether
two of them state the same metric differently.

``receipts portfolio`` runs each spec through the ordinary export path with no
shortcuts -- the same grounding gate, the same coverage refusal, the same human
approval -- and records what it wrote in ``portfolio.json``. ``receipts
portfolio-verify`` re-verifies every bundle from its own spec and renders
``index.html`` over the result.

The index computes no figure. Every number on it was already receipted by the
run that produced it, and the shared-figure table compares receipts rather than
recomputing them. Where two reports state the same metric id, the comparison has
four outcomes and they are kept distinct: the reports agree, their definitions
differ (so their values are not comparable at all), one report withheld the cell
under suppression (an absence, never a disagreement and never a zero), or the
definitions match and the values do not, which is the only one of the four that
means the reports contradict each other.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from outcome_receipts.copy import ReportCopy, get_copy, normalize_locale
from outcome_receipts.models import REDACTED_DISPLAY

#: The batch record ``portfolio`` writes and ``portfolio-verify`` reads back.
#: It is deliberately not one of the project's published contracts: it is
#: internal to a portfolio directory, written and read by the same two commands,
#: and it carries no figure. The three published contracts stay three.
INDEX_NAME = "portfolio.json"
PAGE_NAME = "index.html"

#: How the four shared-figure outcomes are recorded. ``agrees`` and
#: ``value_differs`` are the only two that compare numbers; the other two say
#: why a comparison was not made, rather than reporting one that was not.
AGREES = "agrees"
DEFINITION_DIFFERS = "definition_differs"
VALUE_DIFFERS = "value_differs"
NOT_COMPARABLE = "not_comparable"


class PortfolioError(Exception):
    """A portfolio directory that cannot be read as one."""


@dataclass(frozen=True)
class PortfolioReport:
    """One report the batch exported, and where to find what proves it.

    ``spec`` is the path to the spec that produced it, as the operator gave it.
    ``directory`` is the bundle directory relative to the portfolio directory,
    so the whole portfolio moves as a unit. ``bundle_digest`` is the seal
    ``bundle.json`` recorded at export, kept here so a wholesale replacement of
    that file is caught rather than re-read as authoritative.
    """

    spec: str
    directory: str
    title: str
    approved_by: str
    bundle_digest: str
    signed: bool
    ledger_index: int
    ledger_entry_hash: str

    def payload(self) -> dict[str, object]:
        return {
            "spec": self.spec,
            "directory": self.directory,
            "title": self.title,
            "approved_by": self.approved_by,
            "bundle_digest": self.bundle_digest,
            "signed": self.signed,
            "ledger_index": self.ledger_index,
            "ledger_entry_hash": self.ledger_entry_hash,
        }


@dataclass(frozen=True)
class PortfolioIndex:
    """Every report one batch exported, ordered by spec path."""

    reports: tuple[PortfolioReport, ...]
    ledger: str

    def payload(self) -> dict[str, object]:
        return {
            "ledger": self.ledger,
            "reports": [report.payload() for report in self.reports],
        }


def write_index(directory: Path, index: PortfolioIndex) -> Path:
    """Write the batch record. Deterministic: sorted keys, fixed indent."""

    path = directory / INDEX_NAME
    path.write_text(json.dumps(index.payload(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _report_from(raw: object, *, source: Path) -> PortfolioReport:
    if not isinstance(raw, Mapping):
        raise PortfolioError(f"{source}: a report entry is not an object")
    missing = [
        key
        for key in ("spec", "directory", "title", "approved_by", "bundle_digest", "signed")
        if key not in raw
    ]
    if missing:
        raise PortfolioError(f"{source}: a report entry is missing {', '.join(missing)}")
    return PortfolioReport(
        spec=str(raw["spec"]),
        directory=str(raw["directory"]),
        title=str(raw["title"]),
        approved_by=str(raw["approved_by"]),
        bundle_digest=str(raw["bundle_digest"]),
        signed=bool(raw["signed"]),
        ledger_index=int(raw.get("ledger_index", -1)),
        ledger_entry_hash=str(raw.get("ledger_entry_hash", "")),
    )


def read_index(directory: Path) -> PortfolioIndex:
    """Read a portfolio directory's batch record, failing closed.

    A missing, unparseable or reportless record is an error rather than an empty
    portfolio. A verifier that read no reports has verified nothing, and saying
    so is the difference between "every report holds" and "there were none".
    """

    path = directory / INDEX_NAME
    if not path.is_file():
        raise PortfolioError(f"{path}: no portfolio record; run `receipts portfolio` first")
    try:
        raw: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PortfolioError(f"{path}: cannot be read as a portfolio record ({exc})") from exc
    if not isinstance(raw, Mapping):
        raise PortfolioError(f"{path}: portfolio record is not an object")
    reports_raw = raw.get("reports")
    if not isinstance(reports_raw, list) or not reports_raw:
        raise PortfolioError(f"{path}: portfolio record names no reports")
    return PortfolioIndex(
        reports=tuple(_report_from(entry, source=path) for entry in reports_raw),
        ledger=str(raw.get("ledger", "")),
    )


@dataclass(frozen=True)
class ReportVerification:
    """Whether one report in the portfolio still verifies, and why not."""

    report: PortfolioReport
    ok: bool
    detail: str


@dataclass(frozen=True)
class SharedFigure:
    """One metric id stated by more than one report in the portfolio.

    ``status`` is one of the four module constants. ``values`` maps each
    report's title to the display string that report published, so a reader sees
    what each one actually said, including the redaction marker where a report
    withheld the cell.
    """

    metric_id: str
    status: str
    definition: str
    values: tuple[tuple[str, str], ...]

    def payload(self) -> dict[str, object]:
        return {
            "metric_id": self.metric_id,
            "status": self.status,
            "definition": self.definition,
            "values": [{"report": title, "display": display} for title, display in self.values],
        }


def _receipts_of(manifest: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    receipts = manifest.get("receipts")
    if not isinstance(receipts, list):
        return {}
    found: dict[str, Mapping[str, Any]] = {}
    for entry in receipts:
        if isinstance(entry, Mapping) and "metric_id" in entry:
            found[str(entry["metric_id"])] = entry
    return found


def _status_for(entries: Sequence[Mapping[str, Any]]) -> str:
    """Classify one metric id stated by several reports.

    Order matters, and it is the order of what makes a comparison impossible.
    A definition disagreement is checked first: two reports counting different
    things are not comparable at all, and reporting their values as equal or
    unequal would answer a question nobody asked. Suppression is checked next,
    for the same reason in the other direction -- a withheld cell is an absence,
    and comparing it to a published number would either invent a disagreement or
    (worse) read the withheld cell as a value. Only when every report published
    the same definition and a real value does the comparison of values happen.
    """

    definitions = {str(entry.get("definition", "")) for entry in entries}
    if len(definitions) > 1:
        return DEFINITION_DIFFERS
    if any(bool(entry.get("suppressed")) for entry in entries):
        return NOT_COMPARABLE
    displays = {str(entry.get("display", "")) for entry in entries}
    return AGREES if len(displays) == 1 else VALUE_DIFFERS


def shared_figures(
    manifests: Sequence[tuple[str, Mapping[str, Any]]],
) -> tuple[SharedFigure, ...]:
    """The metric ids more than one report states, in metric-id order.

    ``manifests`` is ``(report title, receipts manifest)`` per report. A metric
    only one report states is not shared and is not listed: the table exists to
    show where reports meet, and padding it with every metric in the portfolio
    would bury the rows that matter.
    """

    by_metric: dict[str, list[tuple[str, Mapping[str, Any]]]] = {}
    for title, manifest in manifests:
        for metric_id, entry in _receipts_of(manifest).items():
            by_metric.setdefault(metric_id, []).append((title, entry))

    shared: list[SharedFigure] = []
    for metric_id in sorted(by_metric):
        stated = by_metric[metric_id]
        if len(stated) < 2:
            continue
        entries = [entry for _title, entry in stated]
        definitions = sorted({str(entry.get("definition", "")) for entry in entries})
        shared.append(
            SharedFigure(
                metric_id=metric_id,
                status=_status_for(entries),
                definition=definitions[0] if len(definitions) == 1 else "",
                values=tuple(
                    (title, str(entry.get("display", REDACTED_DISPLAY))) for title, entry in stated
                ),
            )
        )
    return tuple(shared)


_STYLE = """
:root { color-scheme: light; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica,
    Arial, sans-serif;
  color: #1a202c;
  background: #ffffff;
  line-height: 1.5;
  max-width: 60rem;
  margin: 0 auto;
  padding: 2rem 1.25rem 4rem;
}
h1 { font-size: 1.6rem; margin-bottom: 0.25rem; }
h2 { font-size: 1.15rem; margin-top: 2rem; }
table { border-collapse: collapse; table-layout: fixed; width: 100%; margin: 1rem 0; }
caption { text-align: left; font-weight: bold; margin-bottom: 0.5rem; }
th, td {
  border: 1px solid #cbd5e0;
  padding: 0.5rem 0.6rem;
  text-align: left;
  vertical-align: top;
  overflow-wrap: anywhere;
}
th { background: #edf2f7; }
.value { font-variant-numeric: tabular-nums; font-weight: bold; }
.failed { color: #822727; font-weight: bold; }
.hash {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.85rem;
  word-break: break-all;
}
.muted { color: #4a5568; }
@media (max-width: 40rem) {
  body { padding-inline: 0.5rem; }
}
""".strip()


def _esc(text: str) -> str:
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )


def _agreement_label(status: str, copy: ReportCopy) -> str:
    return {
        AGREES: copy.portfolio_agreement_agrees,
        DEFINITION_DIFFERS: copy.portfolio_agreement_definition_differs,
        VALUE_DIFFERS: copy.portfolio_agreement_value_differs,
        NOT_COMPARABLE: copy.portfolio_agreement_not_comparable,
    }[status]


def _reports_table(verifications: Sequence[ReportVerification], copy: ReportCopy) -> list[str]:
    lines = [
        "<table>",
        f"<caption>{_esc(copy.portfolio_reports_caption)}</caption>",
        "<thead>",
        "<tr>"
        f'<th scope="col">{_esc(copy.portfolio_header_report)}</th>'
        f'<th scope="col">{_esc(copy.portfolio_header_verification)}</th>'
        f'<th scope="col">{_esc(copy.portfolio_header_approvers)}</th>'
        f'<th scope="col">{_esc(copy.portfolio_header_signature)}</th>'
        f'<th scope="col">{_esc(copy.portfolio_header_bundle_digest)}</th>'
        f'<th scope="col">{_esc(copy.portfolio_header_ledger)}</th>'
        "</tr>",
        "</thead>",
        "<tbody>",
    ]
    for verification in verifications:
        report = verification.report
        status = (
            f"{_esc(copy.portfolio_status_verified)}"
            if verification.ok
            else f'<span class="failed">{_esc(copy.portfolio_status_failed)}</span>: '
            f"{_esc(verification.detail)}"
        )
        signature = (
            copy.portfolio_signature_present if report.signed else copy.portfolio_signature_absent
        )
        ledger = copy.portfolio_ledger_entry_template.format(index=report.ledger_index)
        lines.append(
            "<tr>"
            f'<th scope="row">{_esc(report.title)}<br>'
            f'<span class="muted">{_esc(report.directory)}</span></th>'
            f"<td>{status}</td>"
            f"<td>{_esc(report.approved_by)}</td>"
            f"<td>{_esc(signature)}</td>"
            f'<td class="hash">{_esc(report.bundle_digest)}</td>'
            f'<td>{_esc(ledger)}<br><span class="hash">'
            f"{_esc(report.ledger_entry_hash)}</span></td>"
            "</tr>"
        )
    lines.extend(["</tbody>", "</table>"])
    return lines


def _shared_table(shared: Sequence[SharedFigure], copy: ReportCopy) -> list[str]:
    if not shared:
        return [f'<p class="muted">{_esc(copy.portfolio_no_shared_figures)}</p>']
    lines = [
        "<table>",
        f"<caption>{_esc(copy.portfolio_shared_caption)}</caption>",
        "<thead>",
        "<tr>"
        f'<th scope="col">{_esc(copy.trace_header_figure)}</th>'
        f'<th scope="col">{_esc(copy.portfolio_header_agreement)}</th>'
        f'<th scope="col">{_esc(copy.trace_header_definition)}</th>'
        f'<th scope="col">{_esc(copy.portfolio_header_stated_by)}</th>'
        "</tr>",
        "</thead>",
        "<tbody>",
    ]
    for figure in shared:
        stated = "<br>".join(
            f'{_esc(title)}: <span class="value">{_esc(display)}</span>'
            for title, display in figure.values
        )
        definition = figure.definition or copy.portfolio_definitions_differ_note
        lines.append(
            "<tr>"
            f'<th scope="row">{_esc(figure.metric_id)}</th>'
            f"<td>{_esc(_agreement_label(figure.status, copy))}</td>"
            f"<td>{_esc(definition)}</td>"
            f"<td>{stated}</td>"
            "</tr>"
        )
    lines.extend(["</tbody>", "</table>"])
    return lines


def render_index_html(
    verifications: Sequence[ReportVerification],
    shared: Sequence[SharedFigure],
    *,
    locale: str = "en",
) -> str:
    """Render the portfolio index as one accessible, script-free HTML page.

    Follows the trace view: a single file, inline styling, semantic tables with
    ``scope`` and a ``<caption>``, one ``<h1>``, and no script, so it opens
    offline beside the bundles it describes.
    """

    selected = normalize_locale(locale)
    copy = get_copy(selected)
    verified = sum(1 for verification in verifications if verification.ok)
    head = [
        "<!doctype html>",
        f'<html lang="{selected}">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{_esc(copy.portfolio_title)}</title>",
        f"<style>{_STYLE}</style>",
        "</head>",
        "<body>",
        "<main>",
        f"<h1>{_esc(copy.portfolio_title)}</h1>",
        f'<p class="muted">{_esc(copy.portfolio_intro)}</p>',
        "<p>"
        + _esc(copy.portfolio_summary_template.format(verified=verified, total=len(verifications)))
        + "</p>",
    ]
    body = _reports_table(verifications, copy)
    body.append(f"<h2>{_esc(copy.portfolio_shared_heading)}</h2>")
    body.extend(_shared_table(shared, copy))
    tail = ["</main>", "</body>", "</html>"]
    return "\n".join([*head, *body, *tail]) + "\n"
