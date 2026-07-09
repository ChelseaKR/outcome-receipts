"""outcome-receipts: funder outcome reports where every number is a receipt.

The supported entry points for v0.x are the command-line interface (``receipts``)
and the functions re-exported here. Everything else is internal and may change
between minor releases until v1.0.
"""

from __future__ import annotations

from importlib.metadata import version

# Single-sourced from pyproject.toml via installed package metadata (REL-02):
# the tag, the wheel, and `receipts --version` can no longer disagree. The
# package is always installed before use (`make install` / `uv sync`), so a
# missing-distribution fallback would only mask a broken environment —
# consistent with fail-closed, there is none.
__version__ = version("outcome-receipts")

from outcome_receipts.models import (
    Figure,
    GroundingResult,
    MetricSpec,
    Receipt,
    ReportSpec,
)

__all__ = [
    "Figure",
    "GroundingResult",
    "MetricSpec",
    "Receipt",
    "ReportSpec",
    "__version__",
]
