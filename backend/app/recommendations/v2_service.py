"""Bounded, read-only catalogue ranking over canonical Local and CAR facts."""
import json
import math
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from decimal import Decimal
from threading import Lock
from time import monotonic

from fastapi import HTTPException
from sqlalchemy import case, func, select
from app import models
from app.analytics.match_v2.service import infrastructure_fit
from app.analytics.local.models import LocalRequest
from app.analytics.objective.provider import ObjectiveProvider
from app.mobility.models import Coordinate, MobilityRequest, PersonalDestination
from app.mobility.service import MobilityService
from .v2_math import compose, constraint, decreasing_utility, eligibility
from .v2_models import CandidateV2, DistrictGroup, ResponseV2

LIMITATIONS = (
    'Observed CIAN complexes are not the complete apartment market.',
    'Source map anchor, not a verified building or entrance.',
    'Starting asking price does not guarantee a currently available apartment.',
    'CAR uses a frozen road graph without current traffic or access time.',
    'OSM spatial availability does not measure service quality or capacity.',
    'Best observed candidate is not compatibility of the whole district; unequal sample sizes bias maxima.',
    'Importance 0..3 and linear utilities are explicit experimental preferences, not satisfaction probabilities.',
)


class BoundedCache:
    def __init__(self, capacity=1024, ttl=60):
        self.capacity, self.ttl = capacity, ttl
        self.rows = OrderedDict()
        self.lock = Lock()

    def get(self, key):
        with self.lock:
            row = self.rows.get(key)
            if row is None:
                return None
            if monotonic() - row[0] >= self.ttl:
                del self.rows[key]
                return None
            self.rows.move_to_end(key)
            return row[1]

    def put(self, key, value):
        with self.lock:
            self.rows[key] = (monotonic(), value)
            self.rows.move_to_end(key)
            while len(self.rows) > self.capacity:
                self.rows.popitem(last=False)


LOCAL_CACHE = BoundedCache()
ROUTE_CACHE = BoundedCache(capacity=2048)


class CachedCar:
    """Cache provider facts only; never reuse another user's labels or preferences."""
    def __init__(self, provider):
        self.provider = provider

    def route(self, origin, destination, mode, departure_time=None):
        # A fake/custom provider without a manifest is never shared between requests.
        manifest = getattr(self.provider, 'manifest', None)
        if not isinstance(manifest, dict):
            manifest = None
        key = (getattr(self.provider, 'base_url', None), json.dumps(manifest, sort_keys=True),
               mode, origin.latitude, origin.longitude, destination.latitude, destination.longitude)
        cached = ROUTE_CACHE.get(key) if manifest else None
        if cached is not None:
            return cached
        facts = self.provider.route(origin, destination, mode, departure_time)
        # Ranking needs time/distance/provenance/snaps, not thousands of polyline vertices.
        # Return the same compact facts on both cold and warm paths.
        if facts.availability == 'AVAILABLE':
            facts = facts.model_copy(update={'geometry':None})
        if manifest and facts.availability == 'AVAILABLE':
            ROUTE_CACHE.put(key, facts)
        return facts


@dataclass(frozen=True)
class Observation:
    id: int | None
    name: str
    location: LocalRequest | None
    district_id: int | None = None
    district_name: str | None = None
    price: Decimal | None = None
    source: dict | None = None


def evaluate(observation, local, profile, mobility, objective=None):
    checks = []
    fit = infrastructure_fit(local, profile.infrastructure) if local else None
    for key, limit in profile.max_distance_m.items():
        component = local.components[key] if local else None
        actual = component.distance_m if component and component.available else None
        checks.append(constraint('distance:' + key, actual, limit, 'straight_line_not_walking' if actual is not None else 'spatial_evidence_missing'))

    trips = []
    weighted = []
    mobility_reason = None
    for index, trip in enumerate(profile.trips):
        active = trip.importance not in (None, 0) and trip.visits_per_week not in (None, 0)
        needed = active and profile.weights.mobility not in (None, 0) or trip.hard_limit_minutes is not None
        route = None
        if needed and observation.location and profile.mode is not None:
            route = mobility.calculate(MobilityRequest(origin=Coordinate(**observation.location.model_dump()),
                destination=PersonalDestination(**trip.model_dump(include={'latitude','longitude','label','kind'})), mode=profile.mode))
        minutes = route.duration_seconds / 60 if route and route.availability == 'AVAILABLE' else None
        utility = decreasing_utility(minutes, trip.comfortable_minutes, trip.soft_limit_minutes)
        if trip.hard_limit_minutes is not None:
            checks.append(constraint('trip:' + str(index), minutes, trip.hard_limit_minutes,
                route.unavailable_reason if route and minutes is None else 'route_missing' if minutes is None else None))
        excluded = trip.importance == 0 or trip.visits_per_week == 0
        reason = 'trip_preferences_missing' if not excluded and (trip.importance is None or trip.visits_per_week is None) else None
        if active:
            if not profile.frequency_weighting_confirmed:
                reason = 'frequency_weighting_not_confirmed'
            elif utility is None:
                reason = route.unavailable_reason if route and minutes is None else 'soft_time_anchors_missing' if minutes is not None else 'route_missing'
            if reason:
                mobility_reason = reason
            else:
                weighted.append((trip.importance * trip.visits_per_week, utility))
        elif reason:
            mobility_reason = reason
        trips.append({'trip':trip.model_dump(mode='json'), 'minutes':minutes, 'utility':utility,
                      'effective_weight':trip.importance * trip.visits_per_week if active else None,
                      'route':route.model_dump(mode='json') if route else None, 'reason':reason})
    mobility_score = math.fsum(w*u for w,u in weighted)/sum(w for w,_ in weighted) if weighted and not mobility_reason else None
    mobility_reason = mobility_reason or (None if mobility_score is not None else 'no_included_soft_trips')

    price = observation.price if profile.housing_goal == 'buy' else None
    if profile.housing_goal != 'buy':
        checks.append(constraint('housing_goal', None, None, 'rent_and_compare_not_supported'))
    if profile.maximum_budget is not None:
        checks.append(constraint('budget', price, profile.maximum_budget,
            'observed_price_missing' if price is None else 'observed_starting_price_only'))
    elif observation.id is not None and profile.housing_goal == 'buy':
        checks.append(constraint('budget', None, None, 'maximum_budget_missing'))
    finance = decreasing_utility(price, profile.comfortable_price, profile.maximum_budget)
    domains, score, reason, coverage = compose({
        'infrastructure': (fit.score if fit else None, fit.unavailable_reason if fit else 'location_missing',
                           {'contributions': [c.model_dump(mode='json') for c in fit.contributions]} if fit else {}),
        'mobility': (mobility_score, mobility_reason, {'trips':trips,'weighting':'importance_times_visits_per_week'}),
        'affordability': (finance, None if finance is not None else 'price_or_comfortable_anchor_missing',
                          {'observed_price':str(price) if price is not None else None,
                           'comfortable_price':str(profile.comfortable_price) if profile.comfortable_price else None,
                           'maximum_budget':str(profile.maximum_budget) if profile.maximum_budget else None}),
    }, profile.weights)
    state = eligibility(checks)
    if profile.housing_goal != 'buy':
        score, reason = None, 'rent_and_compare_not_supported'
    explanations = [f'{key}: utility={d.score}, weight={d.weight}, contribution={d.contribution}; {d.reason or "available"}' for key,d in domains.items()]
    explanations += [f'{c.key}: {c.status}; actual={c.actual}, limit={c.limit}; {c.reason or "checked"}' for c in checks]
    return CandidateV2(id=observation.id,name=observation.name,location=observation.location,
        district_id=observation.district_id,district_name=observation.district_name,price_from=observation.price,
        source=observation.source or {},objective_local=local,objective_district=objective,infrastructure=fit,
        domains=domains,constraints=tuple(checks),eligibility=state,score=score,score_reason=reason,coverage=coverage,
        bucket='failed' if state=='FAIL' else 'verified' if state=='PASS' and score is not None else 'unknown',
        explanations=tuple(explanations),limitations=LIMITATIONS)


class RecommendationsV2Service:
    def __init__(self, session, local, mobility):
        self.session, self.local, self.mobility = session, local, mobility

    def observations(self, request):
        d, r = models.District, models.ResidentialComplex
        polygon = func.coalesce(d.geometry, d.boundary)
        valid_district = (d.source_id=='osm') & d.is_synthetic.is_(False) & func.ST_IsValid(polygon) & (func.ST_SRID(polygon)==4326)
        safe_polygon=case((valid_district,polygon),else_=None)
        if request.point:
            point = func.ST_SetSRID(func.ST_MakePoint(request.point.longitude, request.point.latitude),4326)
            matches = self.session.execute(select(d.id,d.name).where(valid_district,func.ST_Covers(safe_polygon,point)).limit(2)).all()
            district = matches[0] if len(matches)==1 else (None,None)
            return [Observation(None,'Выбранное место',request.point,*district,source={'type':'arbitrary_point','price_attached':False})]
        valid_location=(func.ST_SRID(r.location)==4326) & (func.ST_GeometryType(r.location)=='ST_Point') & func.ST_IsValid(r.location) & ~func.ST_IsEmpty(r.location)
        safe_location=case((valid_location,r.location),else_=None)
        query = select(r,func.ST_AsGeoJSON(safe_location),d.id,d.name).outerjoin(d,
            (d.id==r.district_id) & valid_district & func.ST_Covers(safe_polygon,safe_location)).where(
            r.source_id=='cian',r.is_synthetic.is_(False),func.lower(func.trim(r.source_type)).not_like('synthetic%'))
        if request.candidate_ids:
            query=query.where(r.id.in_(request.candidate_ids))
        rows=self.session.execute(query.order_by(r.id).limit(151)).all()
        if len(rows)>150:
            raise HTTPException(422,'Select at most 150 observed candidates; catalogue was not silently truncated')
        if request.candidate_ids and {row[0].id for row in rows} != set(request.candidate_ids):
            raise HTTPException(404,'Requested real CIAN candidate not found')
        result=[]
        for row,geometry,district_id,district_name in rows:
            try:
                shape=json.loads(geometry) if geometry else None
                location=LocalRequest(longitude=shape['coordinates'][0],latitude=shape['coordinates'][1]) if shape and shape['type']=='Point' else None
            except (ValueError,KeyError,TypeError,IndexError):
                location=None
            price=Decimal(str(row.price_from)) if row.price_from is not None else None
            if price is not None and (not price.is_finite() or price<=0 or location is None):
                price=None
            result.append(Observation(row.id,row.name,location,district_id,district_name,price,
                {'source_id':row.source_id,'external_id':row.external_id,'source_version':row.source_version,
                 'fetched_at':row.fetched_at.isoformat() if row.fetched_at else None,
                 'price_semantics':'observed_asking_starting_price_not_transaction','coordinate_binding':'same_catalogue_record'}))
        return result

    def calculate(self, request):
        observations=self.observations(request)
        district_ids=list(self.session.scalars(select(models.District.id).where(models.District.source_id=='osm',models.District.is_synthetic.is_(False))))
        objectives=ObjectiveProvider(self.session).districts(district_ids)
        # Live provider validates projection and all geometry/reference checks on every request.
        # Only a complete validated domain permits reuse of prior Local observations.
        valid=len(objectives)==7 and all(o.availability=='AVAILABLE' for o in objectives.values())
        identity=json.dumps({str(k):v.model_dump(mode='json') for k,v in objectives.items()},sort_keys=True) if valid else None
        points={json.dumps(o.location.model_dump(),sort_keys=True):o.location for o in observations if o.location}
        locals_by_key={}
        pending=[]
        for key,point in points.items():
            cached=LOCAL_CACHE.get((identity,key)) if valid else None
            if cached is not None:
                locals_by_key[key]=cached
            else:
                pending.append((key,point))
        if pending:
            values=self.local.points([p for _,p in pending])
            if len(values)!=len(pending):
                raise ValueError('Local batch length mismatch')
            for (key,_),value in zip(pending,values,strict=True):
                locals_by_key[key]=value
                if valid and value.availability=='AVAILABLE':
                    LOCAL_CACHE.put((identity,key),value)
        routing=MobilityService(CachedCar(self.mobility.providers['car']), self.mobility.providers['public_transport'])
        def evaluate_one(o):
            # All DB/spatial work is complete. Workers access immutable facts only;
            # never pass the SQLAlchemy session to concurrent workers.
            return evaluate(o,locals_by_key.get(json.dumps(o.location.model_dump(),sort_keys=True)) if o.location else None,
                request.profile,routing,objectives.get(o.district_id))
        # Always evaluate the entire bounded sample. Wall-clock cutoffs would make
        # ranking depend on cache warmth. Each provider call retains its timeout.
        with ThreadPoolExecutor(max_workers=8) as workers:
            candidates=list(workers.map(evaluate_one,observations))
        order={'verified':0,'unknown':1,'failed':2}
        candidates.sort(key=lambda c:(order[c.bucket],-(c.score if c.score is not None else -1),c.id or 0))
        groups=[]
        for district_id in sorted({c.district_id for c in candidates if c.district_id is not None}):
            rows=[c for c in candidates if c.district_id==district_id]
            verified=[c for c in rows if c.bucket=='verified']
            best=verified[0] if verified else None
            groups.append(DistrictGroup(district_id=district_id,district_name=rows[0].district_name,
                observed_count=len(rows),evaluated_count=sum(c.objective_local is not None and c.objective_local.availability=='AVAILABLE' for c in rows),
                verified_count=len(verified),unknown_count=sum(c.bucket=='unknown' for c in rows),failed_count=sum(c.bucket=='failed' for c in rows),
                best_candidate_id=best.id if best else None,best_observed_match=best.score if best else None))
        groups.sort(key=lambda g:(-(g.best_observed_match if g.best_observed_match is not None else -1),g.district_id))
        return ResponseV2(profile=request.profile,candidates=tuple(candidates),districts=tuple(groups),
            sample={'kind':'arbitrary_point' if request.point else 'observed_cian_catalogue','count':len(candidates),
                'candidate_ids':[c.id for c in candidates],'unassigned_count':sum(c.district_id is None for c in candidates),
                'selection':'explicit_ids' if request.candidate_ids else 'single_point' if request.point else 'all_observed',
                'complete_apartment_market':False,'routing_workers':8},limitations=LIMITATIONS)
