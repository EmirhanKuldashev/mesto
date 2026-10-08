"""Thin orchestration of existing deterministic services; no copied calculators."""
import math
import json
from sqlalchemy import func, select

from app import models
from app.analytics.local.models import LocalResult
from app.market.service import assess_sample, summarize_observations
from app.mobility.models import Coordinate, MobilityRequest, PersonalDestination
from .models import (AffordabilityFit, Contribution, DestinationFit, InfrastructureFit,
                     MatchRequest, MatchResult, MobilityFit, Objective, PersonalFit)

KEYS = ('stop_availability','school','kindergarten','healthcare','parks')


def infrastructure_fit(local: LocalResult, importance) -> InfrastructureFit:
    values = {k: getattr(importance,'stop' if k=='stop_availability' else k) if importance else None for k in KEYS}
    incomplete = any(v is None for v in values.values())
    total = sum(v for v in values.values() if v is not None)
    contributions=[]
    for key in KEYS:
        component=local.components[key];weight=values[key]
        normalized=None if incomplete or not total else weight/total
        contribution=None if normalized is None else (0.0 if weight==0 else
            normalized*component.score if component.available else None)
        contributions.append(Contribution(component=key,utility=component.score,importance=weight,
            normalized_weight=normalized,contribution=contribution,
            availability='AVAILABLE' if component.available else 'UNAVAILABLE',
            provenance={**component.provenance,'normalization_version':component.normalization_version,
                'reference_id':component.reference_id,'reference_checksum':component.reference_checksum,
                'evidence_version':component.evidence_version,'eligibility_version':component.eligibility_version,
                'distance_method':component.distance_method,'unavailable_reason':component.unavailable_reason}))
    reason = 'importance_missing' if incomplete else 'all_importance_zero' if not total else (
        'positive_weight_component_unavailable' if any(c.contribution is None for c in contributions) else None)
    availability='NOT_CALCULATED' if incomplete or not total else 'UNAVAILABLE' if reason else 'AVAILABLE'
    return InfrastructureFit(availability=availability,score=math.fsum(c.contribution for c in contributions) if not reason else None,
        contributions=tuple(contributions),unavailable_reason=reason)


def mobility_fit(candidate, preferences, service) -> MobilityFit:
    if preferences is None or not preferences.destinations:
        return MobilityFit(availability='NOT_CALCULATED',destinations=(),unavailable_reason='destinations_missing')
    results=[]
    for destination in preferences.destinations:
        mode=preferences.preferred_mode
        if destination.importance==0 or mode is None:
            results.append(DestinationFit(destination=destination,mode=mode,availability='NOT_CALCULATED',
                unavailable_reason='destination_excluded' if destination.importance==0 else 'preferred_mode_missing'))
            continue
        request=MobilityRequest(origin=Coordinate(**candidate.model_dump()),mode=mode,
            destination=PersonalDestination(**destination.model_dump(exclude={'importance','max_acceptable_minutes'})))
        route=service.calculate(request)
        threshold=destination.max_acceptable_minutes
        delta=route.duration_seconds/60-threshold if route.availability=='AVAILABLE' and threshold is not None else None
        results.append(DestinationFit(destination=destination,mode=mode,availability=route.availability,route=route,
            within_threshold=delta<=0 if delta is not None else None,delta_minutes=delta,
            unavailable_reason=route.unavailable_reason,limitations=route.limitations))
    included=[r for r in results if r.destination.importance>0]
    availability='NOT_CALCULATED' if not included or preferences.preferred_mode is None else (
        'UNAVAILABLE' if any(r.availability=='UNAVAILABLE' for r in included) else 'AVAILABLE')
    return MobilityFit(availability=availability,destinations=tuple(results),
        unavailable_reason='required_route_unavailable' if availability=='UNAVAILABLE' else
            'preferred_mode_missing' if preferences.preferred_mode is None else 'all_destinations_excluded' if not included else None)


def affordability_fit(budget, candidate=None, *, reason=None) -> AffordabilityFit:
    metadata=dict(purchase_budget=budget)
    if candidate is not None:
        sample=summarize_observations(candidate.district_id,[candidate])
        assessment=assess_sample(sample,housing_goal='buy',purchase_budget=budget,rent_budget=None).affordability.purchase
        price=sample.context.min_starting_price
        metadata.update(observed_price_from=price,source=candidate.source_id,source_version=candidate.source_version,
            fetched_at=candidate.fetched_at.isoformat() if candidate.fetched_at else None,observed_affordability=assessment,
            limitations=AffordabilityFit.model_fields['limitations'].default+tuple(assessment.limitations))
        if budget is not None and price is not None:
            return AffordabilityFit(availability='AVAILABLE',within_budget=bool(assessment.within_budget_count),
                budget_delta=budget-price,**metadata)
    return AffordabilityFit(availability='NOT_APPLICABLE' if budget is None else 'UNAVAILABLE',
        unavailable_reason='budget_missing' if budget is None else reason or 'observed_price_missing',**metadata)


class MatchService:
    def __init__(self, local, mobility, session):
        self.local,self.mobility,self.session=local,mobility,session

    def calculate(self, request: MatchRequest) -> MatchResult:
        local=self.local.point(request.candidate)
        candidate=None;reason='market_candidate_missing'
        if request.market_candidate_id is not None:
            # A price belongs only to its real source anchor, never to an unrelated coordinate.
            row=self.session.execute(select(models.ResidentialComplex,
                func.ST_Y(models.ResidentialComplex.location),func.ST_X(models.ResidentialComplex.location),
                func.ST_AsGeoJSON(models.ResidentialComplex.location)).where(
                models.ResidentialComplex.id==request.market_candidate_id,
                models.ResidentialComplex.source_id=='cian',models.ResidentialComplex.is_synthetic.is_(False),
                func.lower(func.trim(models.ResidentialComplex.source_type)).not_like('synthetic%'))).first()
            reason='market_candidate_not_found_or_not_real'
            if row:
                # The existing catalogue emits ST_AsGeoJSON's nine-decimal
                # representation. Accept that exact representation OR original
                # coordinates; never introduce a proximity/tolerance radius.
                catalogue=json.loads(row[3]) if row[3] else None
                coordinates=(request.candidate.longitude,request.candidate.latitude)
                matches=coordinates==(row[2],row[1]) or bool(catalogue and coordinates==tuple(catalogue['coordinates']))
                if not matches:
                    reason='market_candidate_coordinate_mismatch'
                else:
                    if row[0].district_id is None:
                        reason='market_candidate_district_missing'
                    else:
                        candidate=row[0];reason=None
        return MatchResult(candidate=request.candidate,objective=Objective(mesto_local=local),personal_fit=PersonalFit(
            infrastructure=infrastructure_fit(local,request.profile.infrastructure),
            mobility=mobility_fit(request.candidate,request.profile.mobility,self.mobility),
            affordability=affordability_fit(request.profile.purchase_budget,candidate,reason=reason)))
