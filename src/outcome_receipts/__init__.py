"""outcome-receipts: funder outcome reports where every number is a receipt.

The supported entry points for v0.x are the command-line interface (``receipts``)
and the functions re-exported here. Everything else is internal and may change
between minor releases until v1.0.
"""

from __future__ import annotations

__version__ = "0.1.0"

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
