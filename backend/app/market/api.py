"""Separate public context and personal comparison, without score persistence."""

from fastapi import APIRouter, Depends, Path, Response
from sqlalchemy.orm import Session

from app.api import get_session
from app.market.models import AffordabilityRequest, MarketAssessment, MarketContext
from app.market.service import MarketService

router = APIRouter(prefix="/api/market", tags=["market"])


@router.get("/districts/{district_id}", response_model=MarketContext)
def district_market(response: Response, district_id: int = Path(gt=0), session: Session = Depends(get_session)):
    response.headers["Cache-Control"] = "no-store"
    return MarketService(session).context(district_id)


@router.post("/affordability", response_model=MarketAssessment)
def affordability(payload: AffordabilityRequest, response: Response, session: Session = Depends(get_session)):
    response.headers["Cache-Control"] = "no-store"
    return MarketService(session).assessment(payload.profile_id, payload.district_id)
