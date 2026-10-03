"""Small, transparent baseline calculators over existing district records."""

from collections import Counter
from dataclasses import dataclass, field
from statistics import median


@dataclass
class DistrictFacts:
    population: int | None
    area_km2: float | None = None
    poi_counts: Counter[str] = field(default_factory=Counter)
    sale_prices: list[float] = field(default_factory=list)
    rent_prices: list[float] = field(default_factory=list)
    synthetic: bool = False

    @property
    def poi_total(self) -> int:
        return sum(self.poi_counts.values())


def _per_10000(count: int, population: int | None) -> float | None:
    if not population or population <= 0:
        return None
    return count * 10000 / population


def _saturation(count: int, population: int | None, area_km2: float | None,
                target_per_10000: float, target_per_km2: float) -> float | None:
    density = _per_10000(count, population)
    if density is not None:
        return min(100.0, density / target_per_10000 * 100)
    if area_km2 and area_km2 > 0:
        return min(100.0, count / area_km2 / target_per_km2 * 100)
    return None


class InfrastructureCalculator:
    """POI density by population or area; no distance or quality claim."""

    def calculate(self, facts: DistrictFacts) -> float | None:
        if facts.poi_total == 0:
            return None
        if facts.population and facts.population > 0:
            groups = (
                ("education", "kindergarten", "university"),
                ("healthcare", "hospital", "pharmacy"),
                ("park",),
                ("shop", "mall"),
            )
            targets = ((2, 1), (3, 0.4), (1, 0.15), (4, 1))
        else:
            # The bundled OSM snapshot covers education, healthcare and parks.
            groups = (("education", "kindergarten"), ("healthcare",), ("park",))
            targets = ((2, 1), (3, 0.4), (1, 0.15))
        values = [_saturation(sum(facts.poi_counts[name] for name in group),
                              facts.population, facts.area_km2, per_10000, per_km2)
                  for group, (per_10000, per_km2) in zip(groups, targets)]
        return None if any(value is None for value in values) else round(sum(values) / len(values), 2)


class TransportCalculator:
    """Transit-stop density proxy; not a route or travel-time calculation."""

    def calculate(self, facts: DistrictFacts) -> float | None:
        if facts.poi_total == 0:
            return None
        value = _saturation(facts.poi_counts["transport_stop"], facts.population,
                            facts.area_km2, 3, 6)
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


def lifestyle_score(preferences: dict, categories: dict[str, float | None],
                    *, include_future_growth: bool = True) -> tuple[float | None, bool]:
    """Preference-weighted fit over supported category proxies.

    The boolean reports whether answered preferences lacked a supported signal.
    Current-only callers exclude future proxies without removing their mapping.
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
        if category == "future_growth" and not include_future_growth:
            continue
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
