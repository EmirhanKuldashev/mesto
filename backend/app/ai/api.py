"""Generate an AI summary for an existing, consented profile and district."""
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api import get_session
from app.ai.provider import OrcaConfig
from app.ai.service import build_context, runtime

router = APIRouter(prefix="/api/ai", tags=["AI summaries"])


class SummaryRequest(BaseModel):
    profile_id: UUID
    district_id: int = Field(gt=0)


class SummaryResponse(BaseModel):
    district_id: int
    summary: str = Field(min_length=1, max_length=1800)
    generated_at: datetime
    cached: bool


@router.post("/district-summary", response_model=SummaryResponse)
def district_summary(payload: SummaryRequest, response: Response, session: Session = Depends(get_session)):
    response.headers["Cache-Control"] = "no-store"
    config = OrcaConfig.from_env()
    runtime.check_rate(payload.profile_id)
    context = build_context(session, payload.profile_id, payload.district_id)
    return runtime.generate(context, config, payload.profile_id, payload.district_id)
