"""Public request and response contract for district recommendations."""

from uuid import UUID

from pydantic import BaseModel

from app.recommendations.models import DistrictRecommendation


class RecommendationRequest(BaseModel):
    profile_id: UUID


class RecommendationResponse(BaseModel):
    recommendations: list[DistrictRecommendation]
