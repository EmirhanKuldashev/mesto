"""On-demand district score endpoint."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api import get_session
from app.analytics.models import DistrictScoreResponse, ScoreRequest
from app.analytics.service import AnalyticsService

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


def get_analytics_service(session: Session = Depends(get_session)) -> AnalyticsService:
    return AnalyticsService(session)


@router.post("/score", response_model=list[DistrictScoreResponse])
def score_districts(payload: ScoreRequest, service: AnalyticsService = Depends(get_analytics_service)):
    return service.score(payload.profile_id, payload.district_ids)
