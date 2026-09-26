"""Versioned, explainable personal weights over available analytics categories."""

from dataclasses import dataclass
from math import isfinite

from app.analytics.models import CategoryScores
from app.recommendations.models import MatchProfile

RANKING_VERSION = "personal-v1"
BASE_WEIGHTS = {"infrastructure": .30, "transport": .25, "market": .25, "future_growth": .20}


def answered_value(preferences: dict, name: str) -> float | None:
    answer = preferences.get(name)
    if not isinstance(answer, dict) or not answer.get("is_answered"):
        return None
    value = answer.get("value")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        return None
    return float(value) if 0 <= value <= 100 else None


def _priority(preferences: dict, names: tuple[str, ...]) -> float:
    values = [value for name in names if (value := answered_value(preferences, name)) is not None]
    return sum(values) / len(values) / 100 if values else 0


def adapted_weights(profile: MatchProfile) -> dict[str, float]:
    """Increase importance, never fabricate district evidence or travel times."""
    weights = BASE_WEIGHTS.copy()
    preferences = profile.preferences
    weights["infrastructure"] *= 1 + _priority(preferences, (
        "education_weight", "kindergarten_weight", "healthcare_weight", "parks_weight", "shopping_weight"))
    if profile.children_ages:
        weights["infrastructure"] *= 1.5
        if any(age < 7 for age in profile.children_ages):
            weights["infrastructure"] *= 1.2
    elif profile.household_type in ("family", "family_with_relatives"):
        weights["infrastructure"] *= 1.2

    weights["transport"] *= 1 + _priority(preferences, ("transport_weight",))
    if profile.work_point_priority > 0:
        weights["transport"] *= 1 + .25 * min(1, profile.work_point_priority)
    if "mobility" in profile.home_values:
        weights["transport"] *= 1.2

    weights["future_growth"] *= 1 + _priority(preferences, ("future_growth_weight", "today_vs_future"))
    if profile.planning_horizon in ("5_10_years", "long_term"):
        weights["future_growth"] *= 1.2
    if "district_growth" in profile.home_values:
        weights["future_growth"] *= 1.3

    weights["market"] *= 1 + _priority(preferences, ("housing_price_weight",))
    if profile.has_purchase_budget or profile.has_rent_budget:
        weights["market"] *= 1.2
    return weights


@dataclass(frozen=True)
class MatchResult:
    score: float | None
    weights: dict[str, float]
    used_categories: tuple[str, ...]


def personal_match(categories: CategoryScores, profile: MatchProfile) -> MatchResult:
    weights = adapted_weights(profile)
    available = {name: getattr(categories, name) for name in BASE_WEIGHTS
                 if getattr(categories, name) is not None}
    if not available:
        return MatchResult(score=None, weights=weights, used_categories=())
    score = sum(weights[name] * value for name, value in available.items()) / sum(
        weights[name] for name in available)
    return MatchResult(score=round(max(0, min(100, score)), 2), weights=weights,
                       used_categories=tuple(available))
