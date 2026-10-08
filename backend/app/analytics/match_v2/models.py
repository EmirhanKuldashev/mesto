from decimal import Decimal
from typing import Annotated, Literal

from pydantic import Field

from app.analytics.local.models import LocalRequest, LocalResult
from app.analytics.stop_availability.models import EvidenceModel
from app.market.models import ObservedAffordability
from app.mobility.models import Mode, PersonalDestination, MobilityResult

VERSION = 'match-v2-foundation-v1'
Importance = Annotated[int, Field(strict=True,ge=0,le=3)]
Availability = Literal['AVAILABLE','UNAVAILABLE','NOT_CALCULATED','NOT_APPLICABLE']


class InfrastructureImportance(EvidenceModel):
    stop: Importance | None = None
    school: Importance | None = None
    kindergarten: Importance | None = None
    healthcare: Importance | None = None
    parks: Importance | None = None


class Destination(PersonalDestination):
    importance: Importance
    max_acceptable_minutes: float | None = Field(default=None,gt=0,le=1440,strict=True,allow_inf_nan=False)


class MobilityPreferences(EvidenceModel):
    preferred_mode: Mode | None = None
    destinations: tuple[Destination,...] = Field(default=(),max_length=5)


class PersonalProfile(EvidenceModel):
    version: Literal['personal-profile-v1'] = 'personal-profile-v1'
    infrastructure: InfrastructureImportance | None = None
    mobility: MobilityPreferences | None = None
    purchase_budget: Decimal | None = Field(default=None,gt=0,le=Decimal('1000000000000000'),allow_inf_nan=False)


class MatchRequest(EvidenceModel):
    candidate: LocalRequest
    profile: PersonalProfile
    market_candidate_id: int | None = Field(default=None,strict=True,gt=0)


class Contribution(EvidenceModel):
    component: str
    utility: float | None = Field(ge=0,le=100,allow_inf_nan=False)
    importance: Importance | None
    normalized_weight: float | None = Field(ge=0,le=1,allow_inf_nan=False)
    contribution: float | None = Field(ge=0,le=100,allow_inf_nan=False)
    availability: Literal['AVAILABLE','UNAVAILABLE']
    provenance: dict


class InfrastructureFit(EvidenceModel):
    version: Literal['infrastructure-fit-experimental-v1'] = 'infrastructure-fit-experimental-v1'
    availability: Availability
    score: float | None = Field(default=None,ge=0,le=100,allow_inf_nan=False)
    contributions: tuple[Contribution,...]
    unavailable_reason: str | None = None
    limitations: tuple[str,...] = ('Experimental importance scale; no validated housing recommendation claim.',
        'Same Local utilities; never add Local and Fit as independent dimensions.')


class DestinationFit(EvidenceModel):
    destination: Destination
    mode: Mode | None
    availability: Availability
    route: MobilityResult | None = None
    within_threshold: bool | None = None
    delta_minutes: float | None = Field(default=None,allow_inf_nan=False)
    unavailable_reason: str | None = None
    limitations: tuple[str,...] = ()


class MobilityFit(EvidenceModel):
    availability: Availability
    destinations: tuple[DestinationFit,...]
    unavailable_reason: str | None = None


class AffordabilityFit(EvidenceModel):
    availability: Availability
    observed_price_from: Decimal | None = None
    purchase_budget: Decimal | None
    within_budget: bool | None = None
    budget_delta: Decimal | None = None
    source: str | None = None
    source_version: str | None = None
    fetched_at: str | None = None
    observed_at: str | None = None
    price_semantics: Literal['observed_asking_starting_price_not_transaction'] = 'observed_asking_starting_price_not_transaction'
    observed_affordability: ObservedAffordability | None = None
    unavailable_reason: str | None = None
    limitations: tuple[str,...] = ('Source map anchor, not verified building/entrance.',
        'Record fetched_at is not a verified price observation date; current availability/price not guaranteed.')


class HousingFit(EvidenceModel):
    availability: Literal['NOT_IMPLEMENTED'] = 'NOT_IMPLEMENTED'
    unavailable_reason: Literal['waiting_for_eiszh_access'] = 'waiting_for_eiszh_access'


class Objective(EvidenceModel):
    mesto_local: LocalResult


class PersonalFit(EvidenceModel):
    infrastructure: InfrastructureFit
    mobility: MobilityFit
    affordability: AffordabilityFit
    housing: HousingFit = Field(default_factory=HousingFit)


class MatchResult(EvidenceModel):
    version: Literal['match-v2-foundation-v1'] = VERSION
    research_gate: Literal['B'] = 'B'
    candidate: LocalRequest
    objective: Objective
    personal_fit: PersonalFit
    overall_match: None = None
    limitations: tuple[str,...] = ('Experimental foundation, not a calibrated overall Match.',
        'Independent domain availability; no missing-dimension renormalization.',
        'No Housing Fit, public transit routing, traffic, mortgage or AI synthesis.')
