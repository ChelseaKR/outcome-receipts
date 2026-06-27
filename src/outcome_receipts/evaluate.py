"""Eval scoring.

Correctness here is asymmetric, like the sibling project's. A number in a funder
report that is wrong or invented is the expensive, sometimes reputation-ending
error; a number that is correct but phrased awkwardly is not. So the gated metric
is the grounding rate: the share of numbers in the narrative that bind to a
receipt. It must be 100%, fail-closed, before a report can be exported. The
hallucinated-number rate (the complement) is reported with a Wilson confidence
interval because the denominator is small.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from outcome_receipts.models import GroundingResult


def wilson_interval(successes: int, trials: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion, clamped to [0, 1]."""

    if trials <= 0:
        return (0.0, 1.0)
    phat = successes / trials
    z2 = z * z
    denom = 1.0 + z2 / trials
    center = (phat + z2 / (2 * trials)) / denom
    margin = (z / denom) * math.sqrt(phat * (1 - phat) / trials + z2 / (4 * trials * trials))
    return (max(0.0, center - margin), min(1.0, center + margin))


@dataclass(frozen=True)
class EvalReport:
    n_numbers: int
    n_bound: int
    n_unbound: int
    grounding_rate: float
    grounding_ci: tuple[float, float]
    hallucinated_rate: float
    hallucinated_ci: tuple[float, float]

    @property
    def gate_pass(self) -> bool:
        # Fail-closed: a single unbound number fails the gate.
        return self.n_unbound == 0


def evaluate(result: GroundingResult) -> EvalReport:
    """Score a grounding result into the committed eval metrics."""

    total = result.total
    n_bound = len(result.bound)
    n_unbound = len(result.unbound)
    grounding_rate = (n_bound / total) if total else 1.0
    hallucinated_rate = (n_unbound / total) if total else 0.0
    return EvalReport(
        n_numbers=total,
        n_bound=n_bound,
        n_unbound=n_unbound,
        grounding_rate=grounding_rate,
        grounding_ci=wilson_interval(n_bound, total),
        hallucinated_rate=hallucinated_rate,
        hallucinated_ci=wilson_interval(n_unbound, total),
    )
