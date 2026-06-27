"""Time source for receipts.

Receipts carry a ``computed_at`` timestamp. So the committed eval is reproducible
and CI can diff it, the time comes from an injected clock rather than the wall
clock directly. The default uses the real UTC time; the eval uses a fixed clock.
This mirrors the timestamp-authority seam in the sibling constituent-reconciler
project: the same honesty about where time comes from.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol


class Clock(Protocol):
    def now_iso(self) -> str: ...


class SystemClock:
    """Real UTC time, ISO-8601."""

    def now_iso(self) -> str:
        return datetime.now(UTC).isoformat()


class FixedClock:
    """A constant timestamp, for reproducible runs and the committed eval."""

    def __init__(self, value: str = "1970-01-01T00:00:00+00:00") -> None:
        self._value = value

    def now_iso(self) -> str:
        return self._value
