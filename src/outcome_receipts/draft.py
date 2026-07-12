"""The deterministic drafter.

v0.1 fills a report template's ``{metric_id}`` placeholders with the display
strings of the matching figures. It writes no number of its own, so its output is
grounded by construction. The grounding gate still checks it, both as defense in
depth and because the same gate will guard a model-written draft in a later
version, where "grounded by construction" no longer holds.
"""

from __future__ import annotations

import string
from collections.abc import Sequence

from outcome_receipts.models import Figure, ReportSpec


class _FigureFormatter(string.Formatter):
    """Formats ``{metric_id}`` by substituting a figure's display string.

    A placeholder that names no computed figure raises ``KeyError`` via
    ``get_value``, so a template referencing a missing metric fails loudly rather
    than emitting an empty or guessed value.
    """

    def __init__(self, displays: dict[str, str]) -> None:
        self._displays = displays

    def get_value(self, key: object, args: object, kwargs: object) -> str:
        if isinstance(key, str):
            if key not in self._displays:
                raise KeyError(f"template references unknown metric {key!r}")
            return self._displays[key]
        raise KeyError(f"positional placeholders are not supported: {key!r}")


def draft_template(template: str, figures: Sequence[Figure]) -> str:
    """Render one template string with the figures' display strings.

    The same shared figures can render into several funder templates, so the
    per-template narrative is drafted here from the template text alone while the
    figure set stays fixed across formats.
    """

    displays = {figure.metric_id: figure.display for figure in figures}
    formatter = _FigureFormatter(displays)
    return formatter.format(template)


def draft(spec: ReportSpec, figures: Sequence[Figure]) -> str:
    """Render the report template with the figures' display strings."""

    return draft_template(spec.template, figures)
