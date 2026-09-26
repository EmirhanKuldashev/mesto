"""Combine available 0–100 category scores without inventing missing data."""

from dataclasses import dataclass
from typing import Mapping

from app.analytics.scoring.weights import CATEGORIES, ScoringWeights


@dataclass(frozen=True)
class ScoreResult:
    total_score: float | None
    coverage: float


class ScoringEngine:
    def __init__(self, weights: ScoringWeights | None = None) -> None:
        self.weights = (weights or ScoringWeights()).as_dict()

    def calculate(self, categories: Mapping[str, float | None]) -> ScoreResult:
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
        """Today excludes plans; future is today's score plus a bounded weighted uplift."""
        current_categories = dict(categories)
        growth = current_categories["future_growth"]
        current_categories["future_growth"] = None
        current = self.calculate(current_categories).total_score
        if current is None:
            return None, None
        future = None if growth is None else round(min(100.0, current + self.weights["future_growth"] * growth), 2)
        return current, future
