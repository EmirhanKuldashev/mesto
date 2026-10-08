"""Explicit read-only performance, CAR and exploratory candidate audit, never API work."""
import argparse
import json
from decimal import Decimal
import statistics
import time
from pathlib import Path

from sqlalchemy import event, func, select, text
from sqlalchemy.orm import Session

from app import models
from app.analytics.local.service import LocalAnalyticsService
from app.analytics.match_v2.models import Destination, InfrastructureImportance, MatchRequest, MobilityPreferences, PersonalProfile
from app.analytics.match_v2.service import MatchService, infrastructure_fit, affordability_fit
from app.db import create_session_factory
from app.mobility.models import Coordinate
from app.mobility.osrm import CarRoutingProvider
from app.mobility.service import MobilityService
from data.analytics.match_v2_research import PERSONAS


class CountingCar:
    def __init__(self):
        self.provider=CarRoutingProvider.from_environment();self.calls=0

    def route(self,*args,**kwargs):
        self.calls+=1
        return self.provider.route(*args,**kwargs)


def profile(weights,*,destinations=(),budget=None):
    return PersonalProfile(infrastructure=InfrastructureImportance(**dict(zip(
        ('stop','school','kindergarten','healthcare','parks'),weights,strict=True))),
        mobility=MobilityPreferences(preferred_mode='car',destinations=destinations),purchase_budget=budget)


def verify(session):
    assert session.scalar(text('SHOW transaction_read_only'))=='on'
    car=CountingCar();mobility=MobilityService(car);local=LocalAnalyticsService(session);service=MatchService(local,mobility,session)
    point=Coordinate(latitude=56.01,longitude=92.85)
    destinations=tuple(Destination(latitude=lat,longitude=lon,kind=kind,label=kind,importance=2,max_acceptable_minutes=25.)
        for lat,lon,kind in ((55.985,92.9,'work'),(56.06,92.91,'university'),(56.012,92.862,'relatives')))
    performance={};conn=session.connection();queries=[]
    def capture(*args):queries.append(args[2])
    for label,count in (('infrastructure_only',0),('one_car_destination',1),('three_car_destinations',3)):
        timings=[];call_counts=[];query_counts=[]
        request=MatchRequest(candidate=point.model_dump(),profile=profile(PERSONAS['Family'],destinations=destinations[:count]))
        for _ in range(3):
            queries.clear();before=car.calls
            event.listen(conn,'before_cursor_execute',capture)
            start=time.perf_counter()
            try:result=service.calculate(request)
            finally:event.remove(conn,'before_cursor_execute',capture)
            timings.append(time.perf_counter()-start);call_counts.append(car.calls-before);query_counts.append(len(queries))
            assert result.personal_fit.infrastructure.availability=='AVAILABLE'
            assert result.overall_match is None and len(queries)==7 and car.calls-before==count
        performance[label]={'seconds':timings,'median_seconds':statistics.median(timings),'sql_counts':query_counts,'routing_calls':call_counts}
    example=result.model_dump(mode='json')
    rows=session.execute(select(models.ResidentialComplex,func.ST_Y(models.ResidentialComplex.location),
        func.ST_X(models.ResidentialComplex.location)).where(models.ResidentialComplex.source_id=='cian',
        models.ResidentialComplex.is_synthetic.is_(False)).order_by(models.ResidentialComplex.external_id)).all()
    assert len(rows)==108
    from app.analytics.local.models import LocalRequest
    local_results=local.points([LocalRequest(latitude=lat,longitude=lon) for _,lat,lon in rows])
    assert all(r.availability=='AVAILABLE' for r in local_results)
    # A single illustrative work anchor, not a claim about real users' jobs.
    work=destinations[:1]
    candidate_results=[]
    for (candidate,lat,lon),objective in zip(rows,local_results,strict=True):
        from app.analytics.match_v2.service import mobility_fit
        route=mobility_fit(LocalRequest(latitude=lat,longitude=lon),MobilityPreferences(preferred_mode='car',destinations=work),mobility).destinations[0]
        candidate_results.append({'id':candidate.external_id,'name':candidate.name,'local':objective.score,
            'fits':{name:infrastructure_fit(objective,profile(w).infrastructure).score for name,w in PERSONAS.items()},
            'route':route.model_dump(mode='json'),'budgets':{str(b):affordability_fit(Decimal(str(b)),candidate).model_dump(mode='json') for b in (6000000,8000000,10000000)}})
    scenarios={}
    for name in ('Family','Education','Parks','Healthcare','Balanced','Car commuter','Budget constrained'):
        persona='Balanced' if name in ('Car commuter','Budget constrained') else name
        commute=15. if name=='Car commuter' else 25.
        budget=6000000 if name=='Budget constrained' else 8000000
        rejected={};eligible=[];within_car=[];within_budget=[]
        for row in candidate_results:
            reasons=[];route=row['route']['route'];afford=row['budgets'][str(budget)]
            if route['availability']!='AVAILABLE':reasons.append('route_unavailable')
            elif route['duration_seconds']/60>commute:reasons.append('commute_above_threshold')
            else:within_car.append(row)
            if afford['availability']!='AVAILABLE':reasons.append('price_unavailable')
            elif not afford['within_budget']:reasons.append('price_above_budget')
            else:within_budget.append(row)
            if reasons:rejected[row['id']]=reasons
            else:eligible.append(row)
        ordered=lambda sample,key:[{'id':r['id'],'name':r['name'],'score':r['local'] if key=='local' else r['fits'][persona]} for r in sorted(sample,key=lambda r:(-(r['local'] if key=='local' else r['fits'][persona]),r['id']))[:10]]
        objective_top=ordered(candidate_results,'local');fit_top=ordered(candidate_results,'fit');shortlist=ordered(eligible,'fit')
        scenarios[name]={'weights':PERSONAS[persona],'car_destination':work[0].model_dump(mode='json'),
            'max_minutes':commute,'purchase_budget':budget,'objective_top10':objective_top,'infrastructure_top10':fit_top,
            'car_only_top10':ordered(within_car,'fit'),'budget_only_top10':ordered(within_budget,'fit'),
            'experimental_constrained_top10':shortlist,'eligible_count':len(eligible),'within_car_count':len(within_car),
            'within_budget_count':len(within_budget),'excluded':rejected,
            'fit_to_constrained_top10_overlap_count':len({r['id'] for r in fit_top}&{r['id'] for r in shortlist})}
    return {'version':'match-v2-foundation-v1','gate':'B','read_only':True,'performance':performance,
        'timing_scope':'MatchService.calculate; excludes HTTP, engine and service construction',
        'example':example,'candidate_count':108,'car_routes_available':sum(r['route']['availability']=='AVAILABLE' for r in candidate_results),
        'candidate_scenarios':scenarios,'candidate_results':candidate_results,
        'limitations':['Local Docker timings, not a production SLA.','Experimental constraints then Infrastructure ranking; no overall composition.',
            'All CIAN coordinates are source/map anchors; not verified buildings or entrances.',
            'Illustrative work destination, budgets and time thresholds; not population preferences.']}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    _,engine=create_session_factory()
    try:
        with engine.connect().execution_options(isolation_level='REPEATABLE READ',postgresql_readonly=True) as conn:
            with conn.begin(),Session(bind=conn) as session:report=verify(session)
    finally:engine.dispose()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8')
    print(json.dumps({'candidate_count':report['candidate_count'],'performance':report['performance']}))


if __name__=='__main__':main()
