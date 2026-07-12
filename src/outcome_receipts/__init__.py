"""outcome-receipts: funder outcome reports where every number is a receipt.

The supported entry points for v0.x are the command-line interface (``receipts``)
and the Python API re-exported here. Integrations such as the CI action and the
manifest verifier should ``import outcome_receipts`` and use these names rather
than reaching into submodules, which remain internal and may change between minor
releases until v1.0.

Supported v0.x surface:

- Pipeline: :func:`compute_figures`, :func:`compute_figure`, :func:`read_csv`,
  :func:`load_table`
- Grounding gate: :func:`ground`, :func:`redact_unbound`,
  :class:`GroundingResult`
- Narrative: :func:`draft`
- Verification: :func:`verify_manifest`, :class:`VerifyResult`, :class:`Check`
- Reporting: :func:`render_report`, :func:`receipts_manifest`
- Comparison: :func:`compute_comparison`, :class:`ComparisonResult`
- Diffing: :func:`diff_manifests`, :class:`FigureDelta`, :class:`ManifestDiff`
- Configuration: :func:`load_spec`, :class:`Spec`
- Clocks: :class:`Clock`, :class:`SystemClock`, :class:`FixedClock`
- Core models: :class:`Figure`, :class:`MetricSpec`, :class:`Receipt`,
  :class:`ReportSpec`
"""

from __future__ import annotations

from importlib.metadata import version

# Single-sourced from pyproject.toml via installed package metadata (REL-02):
# the tag, the wheel, and `receipts --version` can no longer disagree. The
# package is always installed before use (`make install` / `uv sync`), so a
# missing-distribution fallback would only mask a broken environment —
# consistent with fail-closed, there is none.
__version__ = version("outcome-receipts")

from outcome_receipts.clock import Clock, FixedClock, SystemClock
from outcome_receipts.comparison import ComparisonResult, compute_comparison
from outcome_receipts.config import Spec, load_spec
from outcome_receipts.diff import FigureDelta, ManifestDiff, diff_manifests
from outcome_receipts.draft import draft
from outcome_receipts.engine import (
    compute_figure,
    compute_figures,
    load_table,
    read_csv,
)
from outcome_receipts.grounding import ground, redact_unbound
from outcome_receipts.models import (
    Figure,
    GroundingResult,
    MetricSpec,
    Receipt,
    ReportSpec,
)
from outcome_receipts.report import receipts_manifest, render_report
from outcome_receipts.verify import Check, VerifyResult, verify_manifest

__all__ = [
    "Check",
    # Clocks
    "Clock",
    "ComparisonResult",
    # Core models
    "Figure",
    "FigureDelta",
    "FixedClock",
    "GroundingResult",
    "ManifestDiff",
    "MetricSpec",
    "Receipt",
    "ReportSpec",
    "Spec",
    "SystemClock",
    "VerifyResult",
    "__version__",
    # Comparison
    "compute_comparison",
    "compute_figure",
    # Pipeline
    "compute_figures",
    "diff_manifests",
    # Narrative
    "draft",
    # Grounding gate
    "ground",
    # Configuration
    "load_spec",
    "load_table",
    "read_csv",
    "receipts_manifest",
    "redact_unbound",
    # Reporting
    "render_report",
    # Verification
    "verify_manifest",
]
