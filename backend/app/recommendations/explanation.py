"""Evidence-bound reasons for a personal match."""

from app.analytics.models import DistrictScoreResponse
from app.recommendations.models import MatchProfile
from app.recommendations.ranking import MatchResult, answered_value


class RecommendationExplanation:
    def generate(self, district: DistrictScoreResponse, profile: MatchProfile,
                 match: MatchResult) -> tuple[list[str], list[str]]:
        categories = district.categories
        reasons: list[str] = []
        warnings = list(district.warnings)
        if profile.children_ages and categories.infrastructure is not None and categories.infrastructure >= 70:
            reasons.append("Высокая оценка инфраструктуры соответствует семейному сценарию")
        if (answered_value(profile.preferences, "transport_weight") or 0) >= 60 and \
                categories.transport is not None and categories.transport >= 70:
            reasons.append("Доступность остановок соответствует транспортному приоритету")
        future_priority = answered_value(profile.preferences, "future_growth_weight") or 0
        if (future_priority >= 60 or "district_growth" in profile.home_values) and \
                categories.future_growth is not None and categories.future_growth >= 60:
            reasons.append("Потенциал роста поддержан учтёнными будущими объектами")
        if (profile.has_purchase_budget or profile.has_rent_budget) and \
                categories.market is not None and categories.market >= 70:
            reasons.append("Учтённые предложения жилья соотносятся с вашим бюджетом")
        if not reasons and match.used_categories:
            labels = {"infrastructure": "инфраструктура", "transport": "транспорт",
                      "market": "рынок жилья", "future_growth": "развитие района"}
            strongest = max(match.used_categories,
                            key=lambda name: match.weights[name] * getattr(categories, name))
            reasons.append(f"Наибольший вклад в персональную оценку внесла категория «{labels[strongest]}» "
                           f"({getattr(categories, strongest):.0f}/100)")
        if profile.life_point_kinds:
            warnings.append("Время в пути до важных мест пока не рассчитывается")
        missing = [name for name in match.weights if name not in match.used_categories]
        if missing:
            warnings.append("Нет данных для персонального подбора по категориям: " + ", ".join(missing))
        return reasons, list(dict.fromkeys(warnings))
