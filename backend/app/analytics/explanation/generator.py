"""Short, evidence-bound reasons and limitations for a district score."""

from app.analytics.future_growth.models import FutureGrowthResult
from app.analytics.scoring.calculators import DistrictFacts


class ExplanationGenerator:
    def objective(self, result, legacy_warnings):
        """V2 explanation; compatibility category scores do not explain MESTO."""
        labels = {"stop_availability": "Остановки", "school": "Школы", "kindergarten": "Детские сады",
                  "healthcare": "Медицина", "parks": "Парки"}
        reasons = [f"{labels[name]}: {component.score:.2f}/100; вес 20%"
                   for name, component in result.components.items() if component.score is not None]
        warnings = ["MESTO V2 — равновесный территориальный индекс пяти компонентов; "
                    "персональные предпочтения учитываются отдельно в Match.",
                    "Покрытие означает наличие пяти компонентов, не полноту данных. "
                    "Прямые расстояния не являются временем или маршрутом поездки."]
        if result.unavailable_reason:
            warnings.append("MESTO V2 недоступен: " + result.unavailable_reason)
        warnings.extend(w for w in legacy_warnings if w.startswith("Growth:") or "синтетические" in w)
        return reasons, warnings

    def generate(self, categories: dict[str, float | None], facts: DistrictFacts,
                 *, unsupported_preferences: bool, future_result: FutureGrowthResult) -> tuple[list[str], list[str]]:
        reasons: list[str] = []
        warnings: list[str] = []
        if categories["infrastructure"] is not None and categories["infrastructure"] >= 70:
            reasons.append("В данных района учтены несколько типов повседневных объектов")
        if categories["transport"] is not None and categories["transport"] >= 70:
            reasons.append("В районе учтены остановки общественного транспорта")
        negative_signals = [signal for signal in future_result.signal_impacts
                            if signal.future_growth_impact < 0]
        warnings.append("MESTO — базовый индекс текущей инфраструктуры и доступности остановок; "
                        "100 означает достижение proxy-порогов, а не идеальность района")
        warnings.append("Покрытие MESTO показывает наличие двух обязательных компонентов методики, "
                        "а не полноту информации о районе")
        if any(signal.source_type in ("government_plan", "construction", "tender")
               for signal in future_result.signal_impacts):
            warnings.append("Growth: сигнал основан на планируемом проекте; реализация не гарантирована")
        if negative_signals:
            warnings.append("Growth: есть внешние сигналы, снижающие оценку потенциала")
        if any(signal.is_demo for signal in future_result.signal_impacts):
            warnings.append("Growth: внешние сигналы содержат демонстрационные данные")
        missing = [name for name in ("infrastructure", "transport") if categories[name] is None]
        if missing:
            warnings.append("Полный MESTO недоступен: нет данных для обязательных компонентов: " + ", ".join(missing))
        if categories["transport"] is not None:
            warnings.append("Транспортный балл основан на числе остановок, без расчёта времени в пути")
        if future_result.factors:
            warnings.append("Growth: часть факторов основана на планируемых объектах; сроки и реализация не гарантированы")
        warnings.extend("Growth: " + warning for warning in future_result.warnings)
        if facts.synthetic:
            warnings.append("Доступные данные включают синтетические демонстрационные записи")
        return reasons, warnings
