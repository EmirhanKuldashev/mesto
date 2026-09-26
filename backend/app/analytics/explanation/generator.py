"""Short, evidence-bound reasons and limitations for a district score."""

from app.analytics.future_growth.models import FutureGrowthResult
from app.analytics.scoring.calculators import DistrictFacts


class ExplanationGenerator:
    def generate(self, categories: dict[str, float | None], facts: DistrictFacts,
                 *, unsupported_preferences: bool, future_result: FutureGrowthResult) -> tuple[list[str], list[str]]:
        reasons: list[str] = []
        warnings: list[str] = []
        if categories["infrastructure"] is not None and categories["infrastructure"] >= 70:
            reasons.append("В данных района учтены несколько типов повседневных объектов")
        if categories["transport"] is not None and categories["transport"] >= 70:
            reasons.append("В районе учтены остановки общественного транспорта")
        if categories["market"] is not None and categories["market"] >= 70:
            reasons.append("Учтённые предложения жилья соотносятся с вашим бюджетом")
        if categories["lifestyle"] is not None and categories["lifestyle"] >= 70:
            reasons.append("Часть выбранных приоритетов согласуется с учтёнными данными района")
        if future_result.factors and future_result.score is not None and future_result.score >= 50:
            reasons.append("Район имеет высокий потенциал развития благодаря будущим объектам")
        positive_signals = [signal for signal in future_result.signal_impacts
                            if signal.future_growth_impact > 0]
        negative_signals = [signal for signal in future_result.signal_impacts
                            if signal.future_growth_impact < 0]
        if positive_signals:
            reasons.append("Район имеет потенциал роста благодаря внешним сигналам развития")
        if any(signal.category == "education" for signal in positive_signals):
            reasons.append("Учтён положительный сигнал для образовательной инфраструктуры")
        if any(signal.source_type in ("government_plan", "construction", "tender")
               for signal in future_result.signal_impacts):
            warnings.append("Сигнал основан на планируемом проекте; реализация не гарантирована")
        if negative_signals:
            warnings.append("Есть внешние сигналы, снижающие оценку потенциала")
        if any(signal.is_demo for signal in future_result.signal_impacts):
            warnings.append("Внешние сигналы содержат демонстрационные данные")
        missing = [name for name, value in categories.items() if value is None]
        if missing:
            warnings.append("Нет данных для категорий: " + ", ".join(missing))
        if categories["transport"] is not None:
            warnings.append("Транспортный балл основан на числе остановок, без расчёта времени в пути")
        if future_result.factors:
            warnings.append("Часть факторов основана на планируемых объектах; сроки и реализация не гарантированы")
        warnings.extend(future_result.warnings)
        if unsupported_preferences:
            warnings.append("Часть ответов профиля пока не имеет измеримого сигнала")
        if facts.synthetic:
            warnings.append("Расчёт использует синтетические демонстрационные данные")
        return reasons, warnings
