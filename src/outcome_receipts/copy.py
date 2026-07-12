"""Locale-keyed copy catalog for report and provenance output.

CLAUDE.md sets an internationalization bar: report output and any reviewer-facing
copy are externalized, with EN and ES at parity for public-facing strings. This
module is where that externalization lives. Every human-facing string that the
report and provenance renderers emit is held here, once per locale, so the same
receipted figures render bilingually.

Only prose and labels translate. Figures, SQL, hashes, row counts, timestamps,
and period labels are data: they flow through the templates as interpolated
values and stay byte-identical across locales. A translator touches this file and
nothing in the render path.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Locale = Literal["en", "es"]

# The locale used when none is given or an unknown one is requested.
DEFAULT_LOCALE: Locale = "en"


@dataclass(frozen=True)
class ReportCopy:
    """Every human-facing string the report and provenance renderers emit.

    Fields ending in ``_template`` carry ``str.format`` placeholders that the
    renderer fills with receipted data (period labels, chart titles, gate
    counts); the placeholder values are never translated. All other fields are
    fixed prose or labels.
    """

    # Comparison table.
    comparison_heading: str
    comparing_sentence_template: str
    header_outcome: str
    header_change: str
    header_direction: str
    direction_increase: str
    direction_decrease: str
    direction_no_change: str
    rate_metric_note: str

    # Reconciliation section.
    reconciliation_heading: str
    reconciliation_sentence_template: str
    header_item: str
    outcome_suffix: str
    financial_suffix: str

    # Charts section.
    charts_heading: str
    chart_data_caption_template: str
    chart_alt_template: str

    # Receipts section.
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

    # Provenance block.
    provenance_heading: str
    provenance_statement: str
    provenance_gate_pass_template: str
    provenance_gate_fail_template: str
    provenance_approval_template: str
    provenance_approval_when_template: str


_EN = ReportCopy(
    comparison_heading="## Period comparison",
    comparing_sentence_template=(
        "Comparing {current} with {prior}. Each value is "
        "a figure with a receipt; the change is itself computed by a single query, "
        "not arithmetic over the page."
    ),
    header_outcome="Outcome",
    header_change="Change",
    header_direction="Direction",
    direction_increase="increase",
    direction_decrease="decrease",
    direction_no_change="no change",
    rate_metric_note="Change for a rate metric is in percentage points.",
    reconciliation_heading="## Board reconciliation",
    reconciliation_sentence_template=(
        "Pairing each receipted outcome figure with its financial line, "
        "{prior} to {current}. Every value is a figure with a receipt."
    ),
    header_item="Item",
    outcome_suffix="outcome",
    financial_suffix="financial",
    charts_heading="## Charts",
    chart_data_caption_template="Data for the chart above ({title}):",
    chart_alt_template="{title} (see data table below)",
    receipts_heading="## Receipts",
    receipt_kind_label="kind",
    receipt_definition_label="definition",
    receipt_indicator_label="indicator",
    receipt_data_source_label="data source",
    receipt_collection_frequency_label="collection frequency",
    receipt_caveat_label="caveat",
    receipt_query_label="query",
    receipt_rows_label="rows in slice",
    receipt_slice_hash_label="slice hash",
    receipt_computed_at_label="computed at",
    provenance_heading="## Provenance",
    provenance_statement=(
        "Every number in this report was computed by a deterministic SQL query "
        "over the organization's own service data. No figure was written by a "
        "language model. Each figure carries a receipt below: the exact query, "
        "the count of rows it drew from, a content hash of that data slice, and "
        "a timestamp."
    ),
    provenance_gate_pass_template=(  # noqa: S106 — template text, not a password
        "Before this report was exported, the grounding gate bound all "
        "{bound} of its numbers to a receipt; a number that traced "
        "to no receipt would have blocked the export."
    ),
    provenance_gate_fail_template=(
        "The grounding gate left {unbound} number(s) unbound, so "
        "this report is not cleared for export."
    ),
    provenance_approval_template=(
        "This report was reviewed and approved for export by {approver}{when}."
    ),
    provenance_approval_when_template=" on {timestamp}",
)

_ES = ReportCopy(
    comparison_heading="## Comparación de periodos",
    comparing_sentence_template=(
        "Comparando {current} con {prior}. Cada valor es "
        "un dato con un recibo; el cambio se calcula a su vez mediante una sola "
        "consulta, no con aritmética sobre la página."
    ),
    header_outcome="Resultado",
    header_change="Cambio",
    header_direction="Dirección",
    direction_increase="aumento",
    direction_decrease="disminución",
    direction_no_change="sin cambio",
    rate_metric_note=("El cambio de una métrica de tasa se expresa en puntos porcentuales."),
    reconciliation_heading="## Conciliación de la junta directiva",
    reconciliation_sentence_template=(
        "Se empareja cada resultado con recibo con su partida financiera, "
        "de {prior} a {current}. Cada valor es un dato con recibo."
    ),
    header_item="Elemento",
    outcome_suffix="resultado",
    financial_suffix="financiero",
    charts_heading="## Gráficos",
    chart_data_caption_template="Datos del gráfico anterior ({title}):",
    chart_alt_template="{title} (véase la tabla de datos a continuación)",
    receipts_heading="## Recibos",
    receipt_kind_label="tipo",
    receipt_definition_label="definición",
    receipt_indicator_label="indicador",
    receipt_data_source_label="fuente de datos",
    receipt_collection_frequency_label="frecuencia de recopilación",
    receipt_caveat_label="salvedad",
    receipt_query_label="consulta",
    receipt_rows_label="filas en el segmento",
    receipt_slice_hash_label="hash del segmento",
    receipt_computed_at_label="calculado en",
    provenance_heading="## Procedencia",
    provenance_statement=(
        "Cada número de este informe fue calculado por una consulta SQL "
        "determinista sobre los propios datos de servicio de la organización. "
        "Ningún dato fue redactado por un modelo de lenguaje. Cada dato lleva un "
        "recibo a continuación: la consulta exacta, el número de filas de las que "
        "se extrajo, un hash de contenido de ese segmento de datos y una marca de "
        "tiempo."
    ),
    provenance_gate_pass_template=(  # noqa: S106 — template text, not a password
        "Antes de exportar este informe, la verificación de fundamentación vinculó "
        "los {bound} números a un recibo; un número que no correspondiera a ningún "
        "recibo habría bloqueado la exportación."
    ),
    provenance_gate_fail_template=(
        "La verificación de fundamentación dejó {unbound} número(s) sin vincular, "
        "por lo que este informe no está autorizado para exportación."
    ),
    provenance_approval_template=(
        "Este informe fue revisado y aprobado para su exportación por {approver}{when}."
    ),
    provenance_approval_when_template=" el {timestamp}",
)

STRINGS: dict[Locale, ReportCopy] = {"en": _EN, "es": _ES}


def get_copy(locale: Locale = DEFAULT_LOCALE) -> ReportCopy:
    """Return the copy catalog for ``locale``, falling back to the default.

    An unknown or missing locale falls back to :data:`DEFAULT_LOCALE` (``"en"``)
    rather than raising, so a caller that passes an unrecognized value still gets
    a coherent, fully rendered report instead of a crash mid-export.
    """

    return STRINGS.get(locale, STRINGS[DEFAULT_LOCALE])
