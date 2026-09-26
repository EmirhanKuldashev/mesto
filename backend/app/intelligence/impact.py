"""Deterministic signed impact; confidence discounts unverified signals."""

from dataclasses import dataclass
from datetime import date
from math import isfinite


@dataclass(frozen=True)
class SignalEvidence:
    id: int
    district_id: int
    source_type: str
    title: str
    category: str
    impact_direction: str
    impact_value: float
    confidence: float
    event_date: date | None = None
    is_demo: bool = False


@dataclass(frozen=True)
class SignalImpact:
    signal_id: int
    source_type: str
    title: str
    category: str
    future_growth_impact: float
    confidence: float
    is_demo: bool


class SignalImpactCalculator:
    def calculate(self, signal: SignalEvidence) -> SignalImpact:
        value = float(signal.impact_value)
        confidence = float(signal.confidence)
        if not isfinite(value) or not -100 <= value <= 100:
            raise ValueError("impact_value must be between -100 and 100")
        if not isfinite(confidence) or not 0 <= confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")
        if not ((signal.impact_direction == "positive" and value > 0) or
                (signal.impact_direction == "negative" and value < 0) or
                (signal.impact_direction == "neutral" and value == 0)):
            raise ValueError("impact_direction must agree with impact_value")
        return SignalImpact(signal_id=signal.id, source_type=signal.source_type,
                            title=signal.title, category=signal.category,
                            future_growth_impact=round(value * confidence, 2),
                            confidence=confidence, is_demo=signal.is_demo)
