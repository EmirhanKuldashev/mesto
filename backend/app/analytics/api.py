"""On-demand district score endpoint."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api import get_session
from app.analytics.models import DistrictScoreResponse, ScoreRequest
from app.analytics.service import AnalyticsService
from app.analytics.local.models import LocalRequest, LocalResult
from app.analytics.local.service import LocalAnalyticsService
from app.db import create_session_factory

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


def get_analytics_service(session: Session = Depends(get_session)) -> AnalyticsService:
    return AnalyticsService(session)


@router.post("/score", response_model=list[DistrictScoreResponse])
def score_districts(payload: ScoreRequest, service: AnalyticsService = Depends(get_analytics_service)):
    return service.score(payload.profile_id, payload.district_ids)


def get_local_service():
    """All point queries see one read-only MVCC snapshot; no effect on legacy APIs."""
    _, engine = create_session_factory()
    try:
        with engine.connect().execution_options(isolation_level="REPEATABLE READ", postgresql_readonly=True) as connection:
            with connection.begin(), Session(bind=connection) as session:
                yield LocalAnalyticsService(session)
    finally:
        engine.dispose()


@router.post("/local", response_model=LocalResult)
def score_local(payload: LocalRequest, service: LocalAnalyticsService = Depends(get_local_service)):
    return service.point(payload)
