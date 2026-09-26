"""Versioned baseline weights. Values sum to one."""

from dataclasses import dataclass

CATEGORIES = ("lifestyle", "infrastructure", "transport", "future_growth", "market")
CALCULATION_VERSION = "baseline-v1"


@dataclass(frozen=True)
class ScoringWeights:
    lifestyle: float = 0.20
    infrastructure: float = 0.25
    transport: float = 0.20
    future_growth: float = 0.15
    market: float = 0.20

    def as_dict(self) -> dict[str, float]:
        values = {name: getattr(self, name) for name in CATEGORIES}
        if any(value < 0 for value in values.values()) or abs(sum(values.values()) - 1) > 1e-9:
            raise ValueError("Scoring weights must be nonnegative and sum to one")
        return values
