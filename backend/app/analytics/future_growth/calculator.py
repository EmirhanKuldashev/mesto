"""Transparent potential score; planned objects never alter today's categories."""

from datetime import date

from app.analytics.future_growth.impact_rules import (
    IMPACT_RULES, SATURATION_IMPACT_POINTS, STATUS_MULTIPLIERS,
    distance_multiplier, time_multiplier,
)
from app.analytics.future_growth.models import FutureFactor, FutureGrowthResult, FutureObjectEvidence
from app.intelligence.impact import SignalEvidence, SignalImpactCalculator


class FutureGrowthCalculator:
    def __init__(self) -> None:
        self.signal_calculator = SignalImpactCalculator()

    def calculate(self, district_id: int, objects: list[FutureObjectEvidence],
                  *, signals: list[SignalEvidence] | None = None,
                  as_of: date | None = None) -> FutureGrowthResult:
        today = as_of or date.today()
        factors: list[FutureFactor] = []
        impacts: dict[str, float] = {}
        warnings: list[str] = []
        for item in objects:
            if item.district_id != district_id:
                continue
            rule = IMPACT_RULES.get(item.category.lower())
            status_weight = STATUS_MULTIPLIERS.get(item.status.lower())
            if rule is None or status_weight is None:
                continue
            if item.confidence is None or not 0 <= item.confidence <= 1:
                warnings.append(f"У объекта «{item.name}» нет проверяемого confidence")
                continue
            year = item.planned_year or (item.expected_date.year if item.expected_date else None)
            time_weight = time_multiplier(year - today.year if year is not None else None)
            space_weight = distance_multiplier(item.distance_km)
            if time_weight == 0 or space_weight == 0:
                continue
            if year is None:
                warnings.append(f"У объекта «{item.name}» не указан срок реализации")
            if item.distance_km is None:
                warnings.append(f"Расстояние до района для «{item.name}» не подтверждено")
            factor = status_weight * time_weight * space_weight * item.confidence
            adjusted = {name: round(value * factor, 2) for name, value in rule.impacts.items()}
            for name, value in adjusted.items():
                impacts[name] = round(impacts.get(name, 0) + value, 2)
            factors.append(FutureFactor(
                object_id=item.id, name=item.name, type=item.category,
                year=year, status=item.status, impact=adjusted, reason=rule.reason,
                distance_km=item.distance_km, confidence=item.confidence,
                is_synthetic=item.is_synthetic,
            ))
        signal_impacts = [self.signal_calculator.calculate(item) for item in (signals or [])
                          if item.district_id == district_id]
        signal_impacts = [item for item in signal_impacts if item.future_growth_impact != 0]
        if not factors and not signal_impacts:
            return FutureGrowthResult(score=None, warnings=warnings)
        base_score = min(100.0, sum(impacts.values()) / SATURATION_IMPACT_POINTS * 100)
        score = max(0.0, min(100.0, base_score + sum(
            item.future_growth_impact for item in signal_impacts)))
        return FutureGrowthResult(score=round(score, 2), factors=factors,
                                  category_impacts=impacts, warnings=warnings,
                                  signal_impacts=signal_impacts)
