"""gettext-backed copy catalog for report, provenance, and trace output."""

from __future__ import annotations

import gettext
from dataclasses import dataclass

# nosemgrep: python37-compatibility-importlib2  https://github.com/ChelseaKR/outcome-receipts/issues/53
from importlib import resources
from typing import Literal

Locale = Literal["en", "es"]
DEFAULT_LOCALE: Locale = "en"
SUPPORTED_LOCALES: tuple[Locale, ...] = ("en", "es")


@dataclass(frozen=True)
class ReportCopy:
    """All reviewer-facing fixed copy; templates use ``str.format`` placeholders."""

    comparison_heading: str
    comparing_sentence_template: str
    header_outcome: str
    header_change: str
    header_direction: str
    direction_increase: str
    direction_decrease: str
    direction_no_change: str
    rate_metric_note: str
    reconciliation_heading: str
    reconciliation_sentence_template: str
    header_item: str
    outcome_suffix: str
    financial_suffix: str
    charts_heading: str
    chart_data_caption_template: str
    chart_alt_template: str
    receipts_heading: str
    receipt_kind_label: str
    receipt_definition_label: str
    receipt_indicator_label: str
    receipt_data_source_label: str
    receipt_collection_frequency_label: str
    receipt_caveat_label: str
    receipt_query_label: str
    receipt_rows_label: str
    receipt_slice_hash_label: str
    receipt_computed_at_label: str
    provenance_heading: str
    provenance_statement: str
    provenance_gate_pass_template: str
    provenance_gate_fail_template: str
    provenance_approval_template: str
    provenance_approval_when_template: str
    trace_title_template: str
    trace_intro: str
    trace_figures_caption: str
    trace_header_figure: str
    trace_header_value: str
    trace_header_definition: str
    trace_header_caveat: str
    trace_header_rows: str
    trace_no_definition: str
    trace_none: str
    trace_increase_template: str
    trace_decrease_template: str
    trace_details_heading: str
    trace_compared_periods_label: str
    trace_compared_periods_template: str
    trace_provenance_pass_template: str
    trace_provenance_fail_template: str


def _translation(locale: Locale) -> gettext.GNUTranslations:
    catalog_dir = resources.files("outcome_receipts").joinpath("locales")
    with resources.as_file(catalog_dir) as localedir:
        translation = gettext.translation(
            "messages", localedir=str(localedir), languages=[locale], fallback=False
        )
    if not isinstance(translation, gettext.GNUTranslations):
        raise TypeError("compiled gettext catalog did not load as GNUTranslations")
    return translation


def _build_copy(locale: Locale) -> ReportCopy:
    _ = _translation(locale).gettext
    return ReportCopy(
        comparison_heading=_("comparison_heading"),
        comparing_sentence_template=_("comparing_sentence_template"),
        header_outcome=_("header_outcome"),
        header_change=_("header_change"),
        header_direction=_("header_direction"),
        direction_increase=_("direction_increase"),
        direction_decrease=_("direction_decrease"),
        direction_no_change=_("direction_no_change"),
        rate_metric_note=_("rate_metric_note"),
        reconciliation_heading=_("reconciliation_heading"),
        reconciliation_sentence_template=_("reconciliation_sentence_template"),
        header_item=_("header_item"),
        outcome_suffix=_("outcome_suffix"),
        financial_suffix=_("financial_suffix"),
        charts_heading=_("charts_heading"),
        chart_data_caption_template=_("chart_data_caption_template"),
        chart_alt_template=_("chart_alt_template"),
        receipts_heading=_("receipts_heading"),
        receipt_kind_label=_("receipt_kind_label"),
        receipt_definition_label=_("receipt_definition_label"),
        receipt_indicator_label=_("receipt_indicator_label"),
        receipt_data_source_label=_("receipt_data_source_label"),
        receipt_collection_frequency_label=_("receipt_collection_frequency_label"),
        receipt_caveat_label=_("receipt_caveat_label"),
        receipt_query_label=_("receipt_query_label"),
        receipt_rows_label=_("receipt_rows_label"),
        receipt_slice_hash_label=_("receipt_slice_hash_label"),
        receipt_computed_at_label=_("receipt_computed_at_label"),
        provenance_heading=_("provenance_heading"),
        provenance_statement=_("provenance_statement"),
        provenance_gate_pass_template=_("provenance_gate_pass_template"),
        provenance_gate_fail_template=_("provenance_gate_fail_template"),
        provenance_approval_template=_("provenance_approval_template"),
        provenance_approval_when_template=_("provenance_approval_when_template"),
        trace_title_template=_("trace_title_template"),
        trace_intro=_("trace_intro"),
        trace_figures_caption=_("trace_figures_caption"),
        trace_header_figure=_("trace_header_figure"),
        trace_header_value=_("trace_header_value"),
        trace_header_definition=_("trace_header_definition"),
        trace_header_caveat=_("trace_header_caveat"),
        trace_header_rows=_("trace_header_rows"),
        trace_no_definition=_("trace_no_definition"),
        trace_none=_("trace_none"),
        trace_increase_template=_("trace_increase_template"),
        trace_decrease_template=_("trace_decrease_template"),
        trace_details_heading=_("trace_details_heading"),
        trace_compared_periods_label=_("trace_compared_periods_label"),
        trace_compared_periods_template=_("trace_compared_periods_template"),
        trace_provenance_pass_template=_("trace_provenance_pass_template"),
        trace_provenance_fail_template=_("trace_provenance_fail_template"),
    )


STRINGS: dict[Locale, ReportCopy] = {locale: _build_copy(locale) for locale in SUPPORTED_LOCALES}


def normalize_locale(locale: str = DEFAULT_LOCALE) -> Locale:
    """Return the supported artifact locale, falling back to English."""

    if locale == "es":
        return "es"
    return DEFAULT_LOCALE


def get_copy(locale: str = DEFAULT_LOCALE) -> ReportCopy:
    """Return ``locale`` copy, falling back to English for an unsupported tag."""

    return STRINGS[normalize_locale(locale)]
