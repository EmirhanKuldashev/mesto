from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db import create_session_factory
from app.analytics.local.service import LocalAnalyticsService
from app.mobility.api import MobilityRoute, get_mobility_service
from .v2_models import RequestV2, ResponseV2
from .v2_service import RecommendationsV2Service

router=APIRouter(prefix='/api/recommendations',tags=['recommendations-v2'],route_class=MobilityRoute)


def get_v2_service(mobility=Depends(get_mobility_service)):
    _,engine=create_session_factory()
    try:
        with engine.connect().execution_options(isolation_level='REPEATABLE READ',postgresql_readonly=True) as connection:
            with connection.begin(),Session(bind=connection) as session:
                yield RecommendationsV2Service(session,LocalAnalyticsService(session),mobility)
    finally:
        engine.dispose()


@router.post('/v2',response_model=ResponseV2)
def recommend_v2(request:RequestV2,service=Depends(get_v2_service)):
    return service.calculate(request)
