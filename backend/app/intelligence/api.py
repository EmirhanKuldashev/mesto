"""Read-only district intelligence endpoint."""

from fastapi import APIRouter, Depends, Path
from sqlalchemy.orm import Session

from app.api import get_session
from app.intelligence.schemas import SignalsResponse
from app.intelligence.service import IntelligenceService

router = APIRouter(prefix="/api/intelligence", tags=["intelligence"])


def get_intelligence_service(session: Session = Depends(get_session)) -> IntelligenceService:
    return IntelligenceService(session)


@router.get("/signals/{district_id}", response_model=SignalsResponse)
def signals(district_id: int = Path(gt=0), service: IntelligenceService = Depends(get_intelligence_service)):
    return service.get_signals(district_id)
