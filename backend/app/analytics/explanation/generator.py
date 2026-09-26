"""Short, evidence-bound reasons and limitations for a district score."""

from app.analytics.scoring.calculators import DistrictFacts


class ExplanationGenerator:
    def generate(self, categories: dict[str, float | None], facts: DistrictFacts,
                 *, unsupported_preferences: bool) -> tuple[list[str], list[str]]:
        reasons: list[str] = []
        warnings: list[str] = []
        if categories["infrastructure"] is not None and categories["infrastructure"] >= 70:
            reasons.append("В данных района учтены несколько типов повседневных объектов")
        if categories["transport"] is not None and categories["transport"] >= 70:
            reasons.append("В районе учтены остановки общественного транспорта")
        if categories["market"] is not None and categories["market"] >= 70:
            reasons.append("Учтённые предложения жилья соотносятся с вашим бюджетом")
        if categories["future_growth"] is not None and categories["future_growth"] >= 50:
            reasons.append("В данных отмечены планируемые объекты развития")
        if categories["lifestyle"] is not None and categories["lifestyle"] >= 70:
            reasons.append("Часть выбранных приоритетов согласуется с учтёнными данными района")
        missing = [name for name, value in categories.items() if value is None]
        if missing:
            warnings.append("Нет данных для категорий: " + ", ".join(missing))
        if categories["transport"] is not None:
            warnings.append("Транспортный балл основан на числе остановок, без расчёта времени в пути")
        if categories["future_growth"] is not None:
            warnings.append("Планируемые объекты не гарантируют реализацию")
        if unsupported_preferences:
            warnings.append("Часть ответов профиля пока не имеет измеримого сигнала")
        if facts.synthetic:
            warnings.append("Расчёт использует синтетические демонстрационные данные")
        return reasons, warnings
