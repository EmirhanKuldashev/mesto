"""Allowed signal kinds and opt-in deterministic demo records; no ingestion here."""

from datetime import date

from sqlalchemy import select

from app.intelligence.models import ExternalSignal

SOURCE_TYPES = ("news", "tender", "construction", "government_plan", "other")
CATEGORIES = ("education", "transport", "healthcare", "environment", "commercial", "housing")
DIRECTIONS = ("positive", "negative", "neutral")

DEMO_SIGNALS = (
    {"title": "Строительство новой школы", "description": "Демонстрационный план строительства школы",
     "source_type": "government_plan", "category": "education", "impact_direction": "positive",
     "impact_value": 25, "confidence": .5, "event_date": date(2028, 9, 1)},
    {"title": "Развитие транспортной инфраструктуры",
     "description": "Демонстрационное изменение транспортной инфраструктуры",
     "source_type": "construction", "category": "transport", "impact_direction": "positive",
     "impact_value": 20, "confidence": .5, "event_date": date(2029, 1, 1)},
    {"title": "Рост коммерческой активности", "description": "Демонстрационный коммерческий сигнал",
     "source_type": "other", "category": "commercial", "impact_direction": "positive",
     "impact_value": 10, "confidence": .5, "event_date": date(2028, 1, 1)},
)


def seed_demo_signals(session, district_ids: list[int]) -> int:
    """Seed examples once per synthetic district, without impersonating real sources."""
    for district_id, values in zip(district_ids, DEMO_SIGNALS):
        existing = session.scalar(select(ExternalSignal.id).where(
            ExternalSignal.district_id == district_id,
            ExternalSignal.title == values["title"],
            ExternalSignal.is_demo.is_(True),
        ))
        if existing is None:
            session.add(ExternalSignal(district_id=district_id, is_demo=True, **values))
    session.flush()
    return min(len(district_ids), len(DEMO_SIGNALS))
