"""Versioned, explicit impact rules for supported future-object categories."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ImpactRule:
    reason: str
    impacts: dict[str, float]


IMPACT_RULES: dict[str, ImpactRule] = {
    "school": ImpactRule("Новый объект образования", {"education": 15, "family": 10, "infrastructure": 10}),
    "education": ImpactRule("Новый объект образования", {"education": 15, "family": 10, "infrastructure": 10}),
    "kindergarten": ImpactRule("Новый детский сад", {"education": 10, "family": 15}),
    "road": ImpactRule("Новая дорога", {"transport": 20}),
    "transport_stop": ImpactRule("Новая остановка общественного транспорта", {"transport": 25}),
    "metro": ImpactRule("Новый транспортный узел", {"transport": 25}),
    "park": ImpactRule("Новая зелёная зона", {"environment": 15}),
    "hospital": ImpactRule("Новый медицинский объект", {"healthcare": 15}),
    "healthcare": ImpactRule("Новый медицинский объект", {"healthcare": 15}),
    "residential_complex": ImpactRule("Новый жилой комплекс", {"market": 10, "infrastructure": 5}),
}

STATUS_MULTIPLIERS = {"planned": 0.55, "approved": 0.75, "under_construction": 0.90}
MAX_DISTANCE_KM = 5.0
SATURATION_IMPACT_POINTS = 40.0


def time_multiplier(years_until_delivery: int | None) -> float:
    if years_until_delivery is None:
        return 0.5
    if years_until_delivery < 0:
        return 0.0
    if years_until_delivery <= 2:
        return 1.0
    if years_until_delivery <= 5:
        return 0.75
    if years_until_delivery <= 10:
        return 0.5
    return 0.25


def distance_multiplier(distance_km: float | None) -> float:
    if distance_km is None:
        return 0.75
    if distance_km < 0 or distance_km > MAX_DISTANCE_KM:
        return 0.0
    if distance_km <= 1:
        return 1.0
    if distance_km <= 3:
        return 0.75
    return 0.5
