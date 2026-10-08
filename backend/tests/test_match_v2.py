"""Foundation rules plus migrated PostGIS service reuse; no calibrated overall score."""
import math
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import event, select
from sqlalchemy.orm import Session
from app.db import create_session_factory

from app import models
from app.analytics.local.models import LocalRequest
from app.analytics.local.service import LocalAnalyticsService, compose, unavailable_component
from app.analytics.match_v2.api import get_match_service
from app.analytics.match_v2.models import (Destination,InfrastructureImportance,MatchRequest,
    MobilityPreferences,PersonalProfile)
from app.analytics.match_v2.service import (KEYS,MatchService,affordability_fit,infrastructure_fit,mobility_fit)
from app.main import app
from app.mobility.models import RouteFacts
from app.mobility.service import MobilityService
from test_local import POINT, inputs
from test_market import DATE


def weights(values=(2,2,2,2,2)):
    return InfrastructureImportance(**dict(zip(('stop','school','kindergarten','healthcare','parks'),values,strict=True)))


def test_equal_full_precision_contribution_sum_and_determinism():
    local=compose(POINT,inputs())
    result=infrastructure_fit(local,weights())
    assert result.score==local.score==math.fsum(c.contribution for c in result.contributions)
    assert result.score!=round(result.score,2)
    assert result==infrastructure_fit(local,weights())
    assert tuple(c.component for c in result.contributions)==KEYS
    assert all(c.normalized_weight==.2 and c.provenance['reference_checksum'] for c in result.contributions)


@pytest.mark.parametrize('position',range(5))
def test_single_factor_and_explicit_zero(position):
    values=[0]*5;values[position]=3
    local=compose(POINT,inputs())
    result=infrastructure_fit(local,weights(values))
    assert result.score==local.components[KEYS[position]].score
    assert [c.contribution for i,c in enumerate(result.contributions) if i!=position]==[0.]*4


@pytest.mark.parametrize('importance',[None,InfrastructureImportance(),weights((0,0,None,0,0)),weights((0,)*5)])
def test_missing_and_all_zero_distinct(importance):
    result=infrastructure_fit(compose(POINT,inputs()),importance)
    assert result.availability=='NOT_CALCULATED' and result.score is None
    assert result.unavailable_reason==('all_importance_zero' if importance==weights((0,)*5) else 'importance_missing')
    assert all(c.normalized_weight is None and c.contribution is None for c in result.contributions)


@pytest.mark.parametrize('position',range(5))
def test_weighted_missing_no_hidden_renormalization_and_zero_weight_missing(position):
    components=inputs();components[KEYS[position]]=unavailable_component(KEYS[position],'test_missing')
    local=compose(POINT,components)
    result=infrastructure_fit(local,weights())
    assert result.score is None and result.availability=='UNAVAILABLE'
    assert all(c.normalized_weight==.2 for c in result.contributions)
    values=[2]*5;values[position]=0
    result=infrastructure_fit(local,weights(values))
    assert local.score is None and result.availability=='AVAILABLE'
    assert result.contributions[position].contribution==0 and result.contributions[position].utility is None
    assert result.score==math.fsum(.25*c.score for c in components.values() if c.available)


@pytest.mark.parametrize('value',[-1,4,True,1.5,'2'])
def test_importance_strict(value):
    with pytest.raises(ValidationError):InfrastructureImportance(stop=value)


@pytest.mark.parametrize('budget',[0,-1,True,'Infinity','NaN','1e1000'])
def test_invalid_purchase_budget(budget):
    with pytest.raises(ValidationError):PersonalProfile(purchase_budget=budget)


def test_destination_bound_prevents_unbounded_provider_calls():
    destination=Destination(latitude=56.,longitude=92.,importance=1)
    with pytest.raises(ValidationError):MobilityPreferences(destinations=(destination,)*6)


def test_research_reversal_counter_excludes_ties_and_matches_brute_force():
    from data.analytics.match_v2_research import strict_reversals
    import itertools
    for objective in ((3.,2.,1.),(3.,3.,1.),(0.,0.,0.)):
        for values in itertools.product(range(3),repeat=3):
            expected=sum((objective[i]-objective[j])*(values[i]-values[j])<0 for i in range(3) for j in range(i+1,3))
            assert strict_reversals(objective,values)==expected


def test_contributions_reproduce_unequal_weights_and_precision():
    local=compose(POINT,inputs((12.1234567890123,65.9876543210987,28.1234567890123,92.4444444444444,81.8888888888888)))
    result=infrastructure_fit(local,weights((1,3,3,2,2)))
    assert result.score==math.fsum(c.contribution for c in result.contributions)
    assert result.score==math.fsum(w/11*local.components[k].score for k,w in zip(KEYS,(1,3,3,2,2),strict=True))
    assert result.score!=round(result.score,2)


def provider(seconds=600.,available=True):
    fake=Mock()
    fake.route.return_value=RouteFacts(availability='AVAILABLE',duration_seconds=seconds,distance_meters=5000.,
        provider='test-recorded',provider_version='v1',limitations=('no traffic',)) if available else RouteFacts(
            availability='UNAVAILABLE',unavailable_reason='routing_timeout')
    return fake


def preference(threshold=None,mode='car',importance=2):
    return MobilityPreferences(preferred_mode=mode,destinations=(Destination(latitude=55.985,longitude=92.9,
        label='Work',kind='work',importance=importance,max_acceptable_minutes=threshold),))


@pytest.mark.parametrize('threshold,within,delta',[(15.,True,-5.),(10.,True,0.),(5.,False,5.),(None,None,None)])
def test_real_route_threshold_fact_not_score(threshold,within,delta):
    fake=provider();result=mobility_fit(POINT,preference(threshold),MobilityService(fake))
    row=result.destinations[0]
    assert result.availability=='AVAILABLE' and row.route.duration_seconds==600
    assert row.within_threshold is within and row.delta_minutes==delta
    assert row.destination.kind=='work' and row.destination.label=='Work' and row.destination.importance==2
    assert fake.route.call_count==1 and 'score' not in result.model_dump()


def test_pt_unavailable_does_not_call_car_and_provider_error_no_fallback():
    fake=provider()
    result=mobility_fit(POINT,preference(mode='public_transport'),MobilityService(fake))
    assert result.availability=='UNAVAILABLE' and fake.route.call_count==0
    assert result.destinations[0].route.unavailable_reason=='public_transport_source_unavailable'
    result=mobility_fit(POINT,preference(15.),MobilityService(provider(available=False)))
    assert result.destinations[0].route.duration_seconds is None
    assert result.destinations[0].within_threshold is None and result.destinations[0].delta_minutes is None


@pytest.mark.parametrize('prefs',[None,MobilityPreferences(),preference(mode=None),preference(importance=0)])
def test_missing_or_excluded_mobility_never_routes(prefs):
    fake=provider();result=mobility_fit(POINT,prefs,MobilityService(fake))
    assert result.availability=='NOT_CALCULATED' and fake.route.call_count==0


def test_partial_mobility_keeps_available_sibling():
    fake=provider()
    fake.route.side_effect=[fake.route.return_value,RouteFacts(availability='UNAVAILABLE',unavailable_reason='no_route')]
    prefs=preference(15.)
    prefs=prefs.model_copy(update={'destinations':prefs.destinations*2})
    result=mobility_fit(POINT,prefs,MobilityService(fake))
    assert result.availability=='UNAVAILABLE' and result.destinations[0].route.duration_seconds==600
    assert result.destinations[1].route.duration_seconds is None and fake.route.call_count==2


def candidate(price=Decimal('6000000')):
    return SimpleNamespace(price_from=price,source_id='cian',source_version='original-v1',fetched_at=DATE,district_id=7)


@pytest.mark.parametrize('budget,within,delta',[(Decimal('8000000'),True,Decimal('2000000')),
    (Decimal('5000000'),False,Decimal('-1000000')),(Decimal('6000000'),True,Decimal('0'))])
def test_affordability_existing_assessment_provenance(budget,within,delta):
    result=affordability_fit(budget,candidate())
    assert result.availability=='AVAILABLE' and result.within_budget is within and result.budget_delta==delta
    assert result.observed_price_from==Decimal('6000000')
    assert result.source=='cian' and result.source_version=='original-v1' and result.fetched_at==DATE.isoformat()
    assert result.observed_at is None and result.observed_affordability.methodology_version=='observed-starting-price-v1'
    assert result.observed_affordability.ranking_eligible is False and 'score' not in result.model_dump()


def test_no_budget_or_price_remains_missing():
    assert affordability_fit(None,candidate()).availability=='NOT_APPLICABLE'
    result=affordability_fit(Decimal('8000000'),candidate(None))
    assert result.availability=='UNAVAILABLE' and result.within_budget is None and result.budget_delta is None


def service(local=None):
    local=local or compose(POINT,inputs())
    return MatchService(SimpleNamespace(point=lambda _:local),MobilityService(provider()),Mock())


@pytest.fixture
def db_session(test_database_url):
    _,engine=create_session_factory(test_database_url)
    try:
        with engine.connect() as connection:
            transaction=connection.begin()
            try:
                with Session(bind=connection,join_transaction_mode='create_savepoint') as session:
                    yield session
            finally:transaction.rollback()
    finally:engine.dispose()


def test_structured_independent_availability_overall_null_and_no_fallback():
    request=MatchRequest(candidate=POINT,profile=PersonalProfile(infrastructure=weights(),mobility=preference(mode='public_transport')))
    result=service().calculate(request)
    assert result.overall_match is None and result.version=='match-v2-foundation-v1'
    assert result.personal_fit.infrastructure.score==result.objective.mesto_local.score
    assert result.personal_fit.mobility.availability=='UNAVAILABLE'
    assert result.personal_fit.affordability.availability=='NOT_APPLICABLE'
    assert result.personal_fit.housing.availability=='NOT_IMPLEMENTED'
    assert service().calculate(request)==result
    local=compose(POINT,{'school':inputs()['school']})
    result=service(local).calculate(request)
    assert result.objective.mesto_local.availability=='UNAVAILABLE'
    assert result.personal_fit.infrastructure.availability=='UNAVAILABLE'
    assert result.personal_fit.mobility.availability=='UNAVAILABLE' and result.overall_match is None


def test_local_unavailable_does_not_destroy_car_or_affordability_state():
    local=compose(POINT,{'school':inputs()['school']})
    request=MatchRequest(candidate=POINT,profile=PersonalProfile(infrastructure=weights(),mobility=preference(15.)))
    result=service(local).calculate(request)
    assert result.objective.mesto_local.score is None and result.personal_fit.infrastructure.score is None
    assert result.personal_fit.mobility.availability=='AVAILABLE'
    assert result.personal_fit.mobility.destinations[0].within_threshold is True
    assert result.personal_fit.affordability.availability=='NOT_APPLICABLE'


@pytest.mark.parametrize('changes',[{'latitude':91},{'longitude':181},{'latitude':True},{'latitude':'56'},
    {'latitude':float('nan')},{'longitude':float('inf')}])
def test_coordinate_validation(changes):
    with pytest.raises(ValidationError):MatchRequest(candidate={**POINT.model_dump(),**changes},profile={})


def test_api_schema_repeat_and_nonfinite_422():
    app.dependency_overrides[get_match_service]=lambda:service()
    try:
        client=TestClient(app);payload={'candidate':POINT.model_dump(),'profile':{'infrastructure':weights().model_dump()}}
        response=client.post('/api/analytics/match-v2',json=payload)
        assert response.status_code==200 and response.json()==client.post('/api/analytics/match-v2',json=payload).json()
        assert response.json()['overall_match'] is None
        bad=client.post('/api/analytics/match-v2',content='{"candidate":{"latitude":NaN,"longitude":92.85},"profile":{}}',headers={'Content-Type':'application/json'})
        assert bad.status_code==422
    finally:app.dependency_overrides.pop(get_match_service,None)


@pytest.mark.integration
def test_postgis_local_reuse_queries_and_real_anchor_binding(db_session):
    from geoalchemy2.elements import WKTElement
    local=LocalAnalyticsService(db_session)
    fake=provider();match=MatchService(local,MobilityService(fake),db_session)
    statements=[];conn=db_session.connection()
    def capture(*args):statements.append(args[2])
    event.listen(conn,'before_cursor_execute',capture)
    try:
        request=MatchRequest(candidate=POINT,profile=PersonalProfile(infrastructure=weights()))
        first=match.calculate(request)
    finally:event.remove(conn,'before_cursor_execute',capture)
    assert first.objective.mesto_local==local.point(POINT)
    assert first.personal_fit.infrastructure.score==first.objective.mesto_local.score
    assert len(statements)==7 and fake.route.call_count==0
    district=db_session.scalar(select(models.District.id).where(models.District.source_id=='osm'))
    rc=models.ResidentialComplex(name='Test anchor',external_id='match-test',source_id='cian',source_type='real_estate_portal',
        source_version='test',fetched_at=DATE,is_synthetic=False,district_id=district,price_from=Decimal('6000000'),
        location=WKTElement('POINT(92.85 56.01)',srid=4326))
    db_session.add(rc);db_session.flush()
    request=MatchRequest(candidate=POINT,market_candidate_id=rc.id,profile=PersonalProfile(infrastructure=weights(),purchase_budget=8000000))
    result=match.calculate(request)
    assert result.personal_fit.affordability.within_budget is True and result.objective.mesto_local==first.objective.mesto_local
    mismatch=request.model_copy(update={'candidate':LocalRequest(latitude=56.02,longitude=92.85)})
    result=match.calculate(mismatch)
    assert result.personal_fit.affordability.unavailable_reason=='market_candidate_coordinate_mismatch'
    assert result.personal_fit.infrastructure.availability=='AVAILABLE'
    assert match.calculate(request)==match.calculate(request)
    rc.location=WKTElement('POINT(92.8500000004 56.0100000004)',srid=4326);db_session.flush()
    # Existing public catalogue rounds to 9 decimals; its exact anchor is accepted.
    assert match.calculate(request).personal_fit.affordability.within_budget is True
    near=request.model_copy(update={'candidate':LocalRequest(latitude=56.01,longitude=92.850000001)})
    assert match.calculate(near).personal_fit.affordability.unavailable_reason=='market_candidate_coordinate_mismatch'
    rc.is_synthetic=True;db_session.flush()
    assert match.calculate(request).personal_fit.affordability.unavailable_reason=='market_candidate_not_found_or_not_real'
