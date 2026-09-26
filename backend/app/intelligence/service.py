"""Load stored signals for a district; never contact external systems."""

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.intelligence.impact import SignalEvidence, SignalImpactCalculator
from app.intelligence.models import ExternalSignal
from app.intelligence.schemas import SignalResponse, SignalsResponse


def as_evidence(row: ExternalSignal) -> SignalEvidence:
    return SignalEvidence(id=row.id, district_id=row.district_id, source_type=row.source_type,
                          title=row.title, category=row.category,
                          impact_direction=row.impact_direction, impact_value=float(row.impact_value),
                          confidence=float(row.confidence), event_date=row.event_date,
                          is_demo=row.is_demo)


class IntelligenceService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.calculator = SignalImpactCalculator()

    def get_signals(self, district_id: int) -> SignalsResponse:
        if self.session.scalar(select(models.District.id).where(models.District.id == district_id)) is None:
            raise HTTPException(404, "District not found")
        rows = self.session.scalars(select(ExternalSignal).where(
            ExternalSignal.district_id == district_id).order_by(ExternalSignal.id)).all()
        signals = []
        for row in rows:
            impact = self.calculator.calculate(as_evidence(row))
            signals.append(SignalResponse(
                id=row.id, district_id=row.district_id, source_type=row.source_type,
                title=row.title, description=row.description, category=row.category,
                impact_direction=row.impact_direction, impact_value=float(row.impact_value),
                impact=f"{float(row.impact_value):+g}",
                future_growth_impact=impact.future_growth_impact,
                confidence=float(row.confidence), event_date=row.event_date,
                is_demo=row.is_demo, created_at=row.created_at,
            ))
        return SignalsResponse(signals=signals)
