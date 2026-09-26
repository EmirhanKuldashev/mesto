"""Small, transparent baseline calculators over existing district records."""

from collections import Counter
from dataclasses import dataclass, field
from statistics import median


@dataclass
class DistrictFacts:
    population: int | None
    poi_counts: Counter[str] = field(default_factory=Counter)
    sale_prices: list[float] = field(default_factory=list)
    rent_prices: list[float] = field(default_factory=list)
    future_confidences: list[float] = field(default_factory=list)
    synthetic: bool = False

    @property
    def poi_total(self) -> int:
        return sum(self.poi_counts.values())


def _per_10000(count: int, population: int | None) -> float | None:
    if not population or population <= 0:
        return None
    return count * 10000 / population


def _saturation(count: int, population: int | None, target: float) -> float | None:
    density = _per_10000(count, population)
    return None if density is None else min(100.0, density / target * 100)


class InfrastructureCalculator:
    """POI coverage per 10k residents; no distance or quality claim."""

    def calculate(self, facts: DistrictFacts) -> float | None:
        if facts.poi_total == 0:
            return None
        groups = (
            ("education", "kindergarten", "university"),
            ("healthcare", "hospital", "pharmacy"),
            ("park",),
            ("shop", "mall"),
        )
        targets = (2, 3, 1, 4)
        values = [_saturation(sum(facts.poi_counts[name] for name in group), facts.population, target)
                  for group, target in zip(groups, targets)]
        return None if any(value is None for value in values) else round(sum(values) / len(values), 2)


class TransportCalculator:
    """Transit-stop density proxy; not a route or travel-time calculation."""

    def calculate(self, facts: DistrictFacts) -> float | None:
        if facts.poi_total == 0:
            return None
        value = _saturation(facts.poi_counts["transport_stop"], facts.population, 3)
        return None if value is None else round(value, 2)


class MarketCalculator:
    """Compare median observed listing price with the profile budget."""

    def calculate(self, facts: DistrictFacts, *, goal: str, purchase_budget: float | None,
                  rent_budget: float | None) -> float | None:
        candidates = []
        if goal in ("buy", "compare") and purchase_budget and facts.sale_prices:
            candidates.append(min(100.0, 75 * purchase_budget / median(facts.sale_prices)))
        if goal in ("rent", "compare") and rent_budget and facts.rent_prices:
            candidates.append(min(100.0, 75 * rent_budget / median(facts.rent_prices)))
        return round(sum(candidates) / len(candidates), 2) if candidates else None


class FutureGrowthCalculator:
    """Planned-object density discounted by recorded source confidence."""

    def calculate(self, facts: DistrictFacts) -> float | None:
        if not facts.future_confidences:
            return None
        density = _saturation(len(facts.future_confidences), facts.population, 2)
        if density is None:
            return None
        reliability = sum(facts.future_confidences) / len(facts.future_confidences)
        return round(density * reliability, 2)


def lifestyle_score(preferences: dict, categories: dict[str, float | None]) -> tuple[float | None, bool]:
    """Preference-weighted fit over supported category proxies.

    The boolean reports whether answered preferences lacked a supported signal.
    """
    mapping = {
        "education_weight": "infrastructure", "kindergarten_weight": "infrastructure",
        "healthcare_weight": "infrastructure", "parks_weight": "infrastructure",
        "shopping_weight": "infrastructure", "transport_weight": "transport",
        "housing_price_weight": "market", "future_growth_weight": "future_growth",
    }
    weighted = []
    unsupported = False
    for name, answer in (preferences or {}).items():
        if not isinstance(answer, dict) or not answer.get("is_answered"):
            continue
        category = mapping.get(name)
        value = categories.get(category) if category else None
        if value is None:
            unsupported = True
            continue
        importance = answer.get("value")
        if isinstance(importance, (int, float)) and 0 < importance <= 100:
            weighted.append((importance, value))
    if not weighted:
        return None, unsupported
    return round(sum(weight * value for weight, value in weighted) /
                 sum(weight for weight, _ in weighted), 2), unsupported
