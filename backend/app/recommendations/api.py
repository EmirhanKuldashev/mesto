"""On-demand personalized district ranking endpoint."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api import get_session
from app.recommendations.schemas import RecommendationRequest, RecommendationResponse
from app.recommendations.service import RecommendationService

router = APIRouter(prefix="/api", tags=["recommendations"])


def get_recommendation_service(session: Session = Depends(get_session)) -> RecommendationService:
    return RecommendationService(session)


@router.post("/recommendations", response_model=RecommendationResponse)
def recommendations(payload: RecommendationRequest,
                    service: RecommendationService = Depends(get_recommendation_service)):
    return RecommendationResponse(recommendations=service.recommend(payload.profile_id))
