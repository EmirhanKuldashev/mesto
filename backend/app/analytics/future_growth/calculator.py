"""Transparent potential score; planned objects never alter today's categories."""

from datetime import date

from app.analytics.future_growth.impact_rules import (
    IMPACT_RULES, SATURATION_IMPACT_POINTS, STATUS_MULTIPLIERS,
    distance_multiplier, time_multiplier,
)
from app.analytics.future_growth.models import FutureFactor, FutureGrowthResult, FutureObjectEvidence


class FutureGrowthCalculator:
    def calculate(self, district_id: int, objects: list[FutureObjectEvidence],
                  *, as_of: date | None = None) -> FutureGrowthResult:
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
        if not factors:
            return FutureGrowthResult(score=None, warnings=warnings)
        score = min(100.0, sum(impacts.values()) / SATURATION_IMPACT_POINTS * 100)
        return FutureGrowthResult(score=round(score, 2), factors=factors,
                                  category_impacts=impacts, warnings=warnings)
