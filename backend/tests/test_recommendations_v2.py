"""Match V2: mathematical boundaries, ranking, availability and disposable PostGIS."""
import itertools
import math
from decimal import Decimal
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import event, func, select, text
from app import models
from app.main import app
from app.analytics.local.models import LocalRequest
from app.analytics.local.service import LocalAnalyticsService, compose as compose_local
from app.analytics.match_v2.models import InfrastructureImportance
from app.analytics.objective.provider import ObjectiveProvider
from app.mobility.models import RouteFacts
from app.mobility.service import MobilityService
from app.recommendations.v2_api import get_v2_service
from app.recommendations.v2_models import DomainWeights, ProfileV2, RequestV2, Trip
from app.recommendations.v2_math import compose, constraint, decreasing_utility, eligibility
from app.recommendations.v2_service import BoundedCache, CachedCar, Observation, RecommendationsV2Service, evaluate
from test_local import inputs

POINT=LocalRequest(latitude=56.01,longitude=92.85)


def profile(**changes):
    data=dict(weights=DomainWeights(infrastructure=1,mobility=0,affordability=0),
        infrastructure=InfrastructureImportance(stop=1,school=1,kindergarten=1,healthcare=1,parks=1),maximum_budget=Decimal('8000000'))
    return ProfileV2(**{**data,**changes})


def local(values=(90,80,70,60,50)):
    return compose_local(POINT,inputs(values))


def car(minutes=20):
    provider=Mock();provider.route.return_value=RouteFacts(availability='AVAILABLE',duration_seconds=float(minutes*60),
        distance_meters=1000.0,provider='test-car',provider_version='fixture')
    return MobilityService(provider)


def candidate(p=None,price=Decimal('6000000'),minutes=20,values=(90,80,70,60,50)):
    return evaluate(Observation(1,'Test observed anchor',POINT,8,'District',price,{'source_id':'test-fixture'}),local(values),p or profile(),car(minutes))


@pytest.mark.parametrize('actual,expected',[(0,100),(10,100),(20,50),(30,0),(40,0)])
def test_utility_boundaries_and_monotonicity(actual,expected):
    assert decreasing_utility(actual,10,30)==expected
    scores=[decreasing_utility(t,10,30) for t in range(50)]
    assert scores==sorted(scores,reverse=True)


def test_decimal_money_and_missing_anchors():
    assert decreasing_utility(Decimal('7000000'),Decimal('6000000'),Decimal('8000000'))==50
    assert decreasing_utility(None,10,30) is None
    assert decreasing_utility(20,None,30) is None
    with pytest.raises(ValueError):decreasing_utility(20,30,10)


@pytest.mark.parametrize('changes',[
    {'weights':{'infrastructure':.5,'mobility':.3,'affordability':.3}},
    {'comfortable_price':9000000,'maximum_budget':8000000},
    {'weights':{'infrastructure':float('nan'),'mobility':0,'affordability':0}},
    {'weights':{'infrastructure':10,'mobility':None,'affordability':None}},
    {'maximum_budget':0}, {'infrastructure':{'school':True}},
    {'max_distance_m':{'school':-1}},
])
def test_invalid_profile_rejected(changes):
    with pytest.raises(ValidationError):ProfileV2(**changes)


@pytest.mark.parametrize('changes',[{'comfortable_minutes':20},{'comfortable_minutes':30,'soft_limit_minutes':20},
    {'hard_limit_minutes':0},{'visits_per_week':1.5},{'importance':4},{'hard_limit_minutes':1441}])
def test_invalid_trip_rejected(changes):
    with pytest.raises(ValidationError):Trip(latitude=56.0,longitude=92.9,**changes)


def test_only_budget_is_constraint_not_financial_utility():
    result=candidate()
    assert result.score==70 and result.bucket=='verified'
    assert result.domains['affordability'].score is None
    assert result.domains['affordability'].contribution==0
    assert result.constraints[0].status=='PASS'
    assert result.objective_local.score==70
    assert result.domains['infrastructure'].contribution==70  # No objective bonus.


@pytest.mark.parametrize('excluded', [{'importance':0}, {'visits_per_week':0}])
def test_explicit_excluded_trip_does_not_require_other_soft_preferences(excluded):
    active=Trip(latitude=56.02,longitude=92.9,importance=3,visits_per_week=5,
                comfortable_minutes=10,soft_limit_minutes=30)
    omitted=Trip(latitude=56.03,longitude=92.9,**excluded,hard_limit_minutes=15)
    result=candidate(profile(mode='car',frequency_weighting_confirmed=True,
        weights=DomainWeights(infrastructure=0,mobility=1,affordability=0),trips=(active,omitted)))
    assert result.domains['mobility'].score==50 and result.score==50
    assert result.bucket=='failed'  # Exclusion from utility never disables the hard limit.
    assert next(c for c in result.constraints if c.key=='trip:1').status=='FAIL'


@pytest.mark.parametrize('price,state',[(Decimal('8000000'),'PASS'),(Decimal('8000001'),'FAIL'),(None,'UNKNOWN')])
def test_hard_budget_boundary_and_unknown(price,state):
    result=candidate(price=price)
    assert result.eligibility==state
    assert result.bucket=={'PASS':'verified','FAIL':'failed','UNKNOWN':'unknown'}[state]


def test_included_finances_need_real_price_and_comfortable_anchor():
    p=profile(weights=DomainWeights(infrastructure=.5,mobility=0,affordability=.5))
    result=candidate(p)
    assert result.score is None and result.coverage==.5
    p=p.model_copy(update={'comfortable_price':Decimal('6000000')})
    assert candidate(p,price=Decimal('7000000')).score==60
    assert candidate(p,price=None).score is None


def test_soft_zero_is_not_hard_violation_and_frequency_weights():
    trip=Trip(latitude=55.985,longitude=92.9,label='Work',importance=3,visits_per_week=5,
        comfortable_minutes=10,soft_limit_minutes=30,hard_limit_minutes=40)
    p=profile(weights=DomainWeights(infrastructure=0,mobility=1,affordability=0),mode='car',trips=(trip,),frequency_weighting_confirmed=True)
    assert candidate(p,minutes=35).score==0
    assert candidate(p,minutes=35).eligibility=='PASS'
    assert candidate(p,minutes=41).bucket=='failed'
    assert candidate(p,minutes=40).eligibility=='PASS'
    assert candidate(p.model_copy(update={'frequency_weighting_confirmed':False})).score is None


def test_trip_weighting_and_hard_only_trip():
    trips=(Trip(latitude=56.,longitude=92.9,importance=1,visits_per_week=1,comfortable_minutes=0,soft_limit_minutes=40),
           Trip(latitude=56.,longitude=93.,importance=3,visits_per_week=5,comfortable_minutes=20,soft_limit_minutes=40))
    p=profile(weights=DomainWeights(infrastructure=0,mobility=1,affordability=0),mode='car',trips=trips,frequency_weighting_confirmed=True)
    assert candidate(p,minutes=20).score==(50+15*100)/16
    hard=Trip(latitude=56.,longitude=92.9,importance=0,visits_per_week=0,hard_limit_minutes=15)
    assert candidate(profile(mode='car',trips=(hard,)),minutes=20).bucket=='failed'


def test_work_and_budget_change_ranking_without_changing_objective():
    trip=Trip(latitude=56.,longitude=92.9,importance=3,visits_per_week=5,comfortable_minutes=10,soft_limit_minutes=40)
    p=profile(mode='car',trips=(trip,),frequency_weighting_confirmed=True,
        weights=DomainWeights(infrastructure=.2,mobility=.8,affordability=0))
    a=candidate(p,minutes=40,values=(90,90,90,90,90))
    b=candidate(p,minutes=10,values=(60,60,60,60,60))
    assert a.objective_local.score>b.objective_local.score and a.score<b.score
    tight=profile(maximum_budget=Decimal('5000000'))
    assert candidate(tight,price=Decimal('6000000')).bucket=='failed'
    assert candidate(tight,price=Decimal('4000000')).bucket=='verified'


def test_pt_never_calls_car_and_missing_routes_are_unknown():
    trip=Trip(latitude=56.,longitude=92.9,importance=1,visits_per_week=5,comfortable_minutes=10,soft_limit_minutes=30,hard_limit_minutes=40)
    p=profile(weights=DomainWeights(infrastructure=0,mobility=1,affordability=0),mode='public_transport',trips=(trip,),frequency_weighting_confirmed=True)
    provider=car()
    result=evaluate(Observation(1,'Test',POINT,price=Decimal('6000000')),local(),p,provider)
    provider.providers['car'].route.assert_not_called()
    assert result.score is None and result.eligibility=='UNKNOWN'


@pytest.mark.parametrize('goal',['rent','compare'])
def test_unsupported_housing_has_no_overall(goal):
    result=candidate(profile(housing_goal=goal))
    assert result.score is None and result.bucket=='unknown'


def test_arbitrary_point_has_no_attached_market_price():
    result=evaluate(Observation(None,'Point',POINT),local(),profile(),car())
    assert result.price_from is None and result.eligibility=='UNKNOWN'
    assert result.domains['affordability'].score is None


def test_distance_constraint_and_failed_precedence():
    result=candidate(profile(max_distance_m={'school':99}),price=None)
    assert result.eligibility=='FAIL' and result.bucket=='failed'
    assert eligibility([constraint('a',None,20),constraint('b',21,20)])=='FAIL'


def test_null_zero_and_no_hidden_renormalization():
    values={'infrastructure':(80,None,{}),'mobility':(None,'missing',{}),'affordability':(None,'missing',{})}
    assert compose(values,DomainWeights(infrastructure=1,mobility=0,affordability=0))[1]==80
    assert compose(values,DomainWeights(infrastructure=.5,mobility=.5,affordability=0))[1] is None
    assert compose(values,DomainWeights())[2]=='domain_weights_missing'
    assert compose(values,DomainWeights(infrastructure=0,mobility=0,affordability=0))[2]=='all_domains_excluded'


def test_all_1023_infrastructure_profiles_are_deterministic_and_reverse_ranks():
    a=(90,20,20,30,10);b=(20,90,90,60,80)
    outcomes=set()
    for weights in itertools.product(range(4),repeat=5):
        if not any(weights):continue
        importance=InfrastructureImportance(**dict(zip(('stop','school','kindergarten','healthcare','parks'),weights)))
        p=profile(infrastructure=importance)
        first,second=candidate(p,values=a),candidate(p,values=b)
        assert first==candidate(p,values=a)
        assert math.isclose(first.score,math.fsum(w*u for w,u in zip(weights,a))/sum(weights),abs_tol=1e-12)
        outcomes.add(first.score>second.score)
    assert outcomes=={True,False}


@pytest.mark.parametrize('name,weights,expected',[
    ('student',(3,0,0,0,0),'A'),('work',(3,0,0,1,0),'A'),('family',(0,3,3,0,0),'B'),
    ('parks_medicine',(0,0,0,3,3),'B'),('high_budget',(1,1,1,1,1),'B'),('strict',(0,3,3,0,0),'B')])
def test_six_infrastructure_personas_on_explicit_synthetic_facts(name,weights,expected):
    p=profile(infrastructure=InfrastructureImportance(**dict(zip(('stop','school','kindergarten','healthcare','parks'),weights))))
    a,b=candidate(p,values=(90,20,20,30,10)),candidate(p,values=(20,90,90,60,80))
    assert ('A' if a.score>b.score else 'B')==expected
    if name=='strict':assert candidate(p.model_copy(update={'max_distance_m':{'school':50}})).bucket=='failed'


def test_cache_bounded_and_route_keys_exclude_personal_labels():
    cache=BoundedCache(capacity=2)
    for i in range(3):cache.put(i,i)
    assert cache.get(0) is None and cache.get(2)==2
    cache.ttl=-1
    assert cache.get(2) is None
    provider=car().providers['car'];provider.manifest={'sha':'unit-cache-test'};provider.base_url='http://unit-test'
    cached=MobilityService(CachedCar(provider))
    from app.mobility.models import MobilityRequest,Coordinate,PersonalDestination
    request=MobilityRequest(origin=Coordinate(**POINT.model_dump()),destination=PersonalDestination(latitude=56.,longitude=93.,label='First'),mode='car')
    first=cached.calculate(request)
    second=cached.calculate(request.model_copy(update={'destination':request.destination.model_copy(update={'label':'Second'})}))
    assert provider.route.call_count==1 and second.destination.label=='Second'
    assert first.duration_seconds==second.duration_seconds
    provider.manifest={'sha':'changed-graph'}
    cached.calculate(request)
    assert provider.route.call_count==2


def test_api_version_invalid_input_and_foundation_compatibility():
    service=Mock()
    from app.recommendations.v2_models import ResponseV2
    service.calculate.return_value=ResponseV2(profile=profile(),sample={'count':1},candidates=(candidate(),),districts=(),limitations=())
    app.dependency_overrides[get_v2_service]=lambda:service
    try:
        with TestClient(app) as client:
            response=client.post('/api/recommendations/v2',json={'profile':profile().model_dump(mode='json')})
            assert response.status_code==200 and response.json()['version']=='match-recommendations-v2'
            assert response.json()['candidates'][0]['score']==70
            assert client.post('/api/recommendations/v2',content='{"profile":{},"point":{"latitude":NaN,"longitude":93}}',headers={'Content-Type':'application/json'}).status_code==422
            assert client.post('/api/recommendations/v2',json={'profile':{},'candidate_ids':[1,1]}).status_code==422
            paths=client.get('/openapi.json').json()['paths']
            assert '/api/recommendations' in paths and '/api/analytics/match-v2' in paths
    finally:app.dependency_overrides.pop(get_v2_service,None)


@pytest.mark.integration
def test_postgis_batch_cache_read_only_and_price_binding(test_database_url):
    from app.db import create_session_factory
    from sqlalchemy.orm import Session
    _,engine=create_session_factory(test_database_url)
    try:
        with engine.connect().execution_options(isolation_level='REPEATABLE READ',postgresql_readonly=True) as connection:
            with connection.begin(),Session(bind=connection) as session:
                assert session.scalar(text('SHOW transaction_read_only'))=='on'
                service=RecommendationsV2Service(session,LocalAnalyticsService(session),car())
                statements=[]
                event.listen(connection,'before_cursor_execute',lambda *args:statements.append(args[2]))
                request=RequestV2(profile=profile(),point=POINT)
                first=service.calculate(request)
                initial=len(statements);statements.clear()
                second=service.calculate(request)
                assert first==second and len(statements)<initial
                assert first.candidates[0].price_from is None
                assert first.candidates[0].objective_local.availability=='AVAILABLE'
                assert not any(s.lstrip().upper().startswith(('INSERT','UPDATE','DELETE','ALTER')) for s in statements)
    finally:engine.dispose()


@pytest.mark.integration
def test_postgis_two_candidates_one_spatial_batch_and_geometry_binding(test_database_url):
    from app.db import create_session_factory
    from geoalchemy2.elements import WKTElement
    from sqlalchemy.orm import Session
    from datetime import datetime,timezone
    _,engine=create_session_factory(test_database_url)
    try:
        with engine.connect() as connection:
            transaction=connection.begin()
            try:
                with Session(bind=connection,join_transaction_mode='create_savepoint') as session:
                    d=models.District
                    district=session.scalar(select(d.id).where(d.source_id=='osm',
                        func.ST_Covers(func.coalesce(d.geometry,d.boundary),WKTElement('POINT(92.85 56.01)',srid=4326))))
                    rows=[]
                    for i,price in enumerate((Decimal('6000000'),None)):
                        row=models.ResidentialComplex(name=f'V2 test {i}',source_id='cian',source_type='real_estate_portal',
                            source_version='unit-postgis',external_id=f'v2-test-{i}',fetched_at=datetime.now(timezone.utc),
                            is_synthetic=False,district_id=district,price_from=price,
                            location=WKTElement(f'POINT({92.85+i*.00001} 56.01)',srid=4326))
                        session.add(row);rows.append(row)
                    session.flush()
                    ids=tuple(r.id for r in rows)
                    service=RecommendationsV2Service(session,LocalAnalyticsService(session),car())
                    spy=Mock(wraps=service.local.points);service.local.points=spy
                    result=service.calculate(RequestV2(profile=profile(),candidate_ids=ids))
                    assert result.sample['count']==2 and len(result.districts)==1
                    assert result.districts[0].observed_count==2
                    assert {c.bucket for c in result.candidates}=={'verified','unknown'}
                    assert spy.call_count<=1  # One spatial batch, regardless of candidate count.
                    provider=service.mobility.providers['car']
                    provider.manifest={'sha':'postgis-v2-parallel-cache'}
                    provider.base_url='http://test-batch'
                    routed=RequestV2(candidate_ids=ids,profile=profile(mode='car',frequency_weighting_confirmed=True,
                        weights=DomainWeights(infrastructure=.5,mobility=.5,affordability=0),
                        trips=(Trip(latitude=56.02,longitude=92.9,importance=3,visits_per_week=5,
                                    comfortable_minutes=10,soft_limit_minutes=30),)))
                    cold=service.calculate(routed)
                    warm=service.calculate(routed)
                    assert cold==warm
                    assert all(c.domains['mobility'].score==50 for c in cold.candidates)
                    assert provider.route.call_count==2  # All candidates measured cold; cached warm.
                    rows[0].district_id=session.scalar(select(d.id).where(d.source_id=='osm',d.id!=district))
                    session.flush()
                    changed=service.calculate(RequestV2(profile=profile(),candidate_ids=(rows[0].id,)))
                    assert changed.candidates[0].district_id is None
            finally:transaction.rollback()
    finally:engine.dispose()
