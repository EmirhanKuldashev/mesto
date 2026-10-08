from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.analytics.local.service import LocalAnalyticsService
from app.db import create_session_factory
from app.mobility.api import MobilityRoute, get_mobility_service
from app.mobility.service import MobilityService
from .models import MatchRequest, MatchResult
from .service import MatchService

router=APIRouter(prefix='/api/analytics',tags=['match-v2'],route_class=MobilityRoute)


def get_match_service(mobility: MobilityService = Depends(get_mobility_service)):
    _,engine=create_session_factory()
    try:
        with engine.connect().execution_options(isolation_level='REPEATABLE READ',postgresql_readonly=True) as connection:
            with connection.begin(),Session(bind=connection) as session:
                yield MatchService(LocalAnalyticsService(session),mobility,session)
    finally:
        engine.dispose()


@router.post('/match-v2',response_model=MatchResult)
def calculate_match(request: MatchRequest,service: MatchService = Depends(get_match_service)):
    return service.calculate(request)
