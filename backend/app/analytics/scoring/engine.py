"""Objective Current and separate future scenario; retain legacy aggregation."""

from dataclasses import dataclass
from typing import Mapping

from app.analytics.scoring.weights import CATEGORIES, CURRENT_WEIGHTS, ScoringWeights


@dataclass(frozen=True)
class ScoreResult:
    total_score: float | None
    coverage: float


class ScoringEngine:
    def __init__(self, weights: ScoringWeights | None = None) -> None:
        self.weights = (weights or ScoringWeights()).as_dict()

    def calculate(self, categories: Mapping[str, float | None]) -> ScoreResult:
        """Legacy five-category aggregate, retained for compatibility; not MESTO."""
        if set(categories) != set(CATEGORIES):
            raise ValueError("All five scoring categories are required")
        for value in categories.values():
            if value is not None and not 0 <= value <= 100:
                raise ValueError("Category scores must be between 0 and 100")
        coverage = sum(self.weights[name] for name, value in categories.items() if value is not None)
        if coverage == 0:
            return ScoreResult(total_score=None, coverage=0)
        weighted = sum(self.weights[name] * value for name, value in categories.items() if value is not None)
        return ScoreResult(total_score=round(weighted / coverage, 2), coverage=round(coverage, 3))

    def calculate_outlook(self, categories: Mapping[str, float | None]) -> tuple[float | None, float | None]:
        """Objective today; a separate scenario keeps the existing growth uplift."""
        growth = categories["future_growth"]
        current = self.calculate_current(categories).total_score
        if current is None:
            return None, None
        future = None if growth is None else round(min(100.0, current + self.weights["future_growth"] * growth), 2)
        return current, future

    def calculate_current(self, categories: Mapping[str, float | None]) -> ScoreResult:
        """Required I/T proxies only; coverage counts components, not source completeness."""
        values = {name: categories.get(name) for name in CURRENT_WEIGHTS}
        for value in values.values():
            if value is not None and not 0 <= value <= 100:
                raise ValueError("Current category scores must be between 0 and 100")
        coverage = sum(value is not None for value in values.values()) / len(values)
        if coverage < 1:
            return ScoreResult(total_score=None, coverage=coverage)
        weighted = sum(CURRENT_WEIGHTS[name] * value for name, value in values.items())
        return ScoreResult(total_score=round(weighted / sum(CURRENT_WEIGHTS.values()), 2), coverage=1.0)
