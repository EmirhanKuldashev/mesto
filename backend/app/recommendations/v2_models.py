"""Request-level Match profile: no migration and no change to Foundation V1."""
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import Field, model_validator
from app.analytics.stop_availability.models import EvidenceModel
from app.analytics.local.models import LocalRequest, LocalResult
from app.analytics.match_v2.models import InfrastructureImportance, InfrastructureFit, Importance
from app.analytics.objective.engine import ObjectiveScore
from app.mobility.models import PersonalDestination, Mode

Number = Annotated[float, Field(ge=0, allow_inf_nan=False, strict=True)]
Fraction = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False, strict=True)]
Score = Annotated[float, Field(ge=0, le=100, allow_inf_nan=False, strict=True)]
Money = Annotated[Decimal, Field(gt=0, le=Decimal('1000000000000000'), allow_inf_nan=False)]
Status = Literal['PASS', 'FAIL', 'UNKNOWN']


class DomainWeights(EvidenceModel):
    infrastructure: Fraction | None = None
    mobility: Fraction | None = None
    affordability: Fraction | None = None

    @model_validator(mode='after')
    def proportions(self):
        values = list(self.model_dump().values())
        if all(v is not None for v in values):
            import math
            total = math.fsum(values)
            if total != 0 and not math.isclose(total, 1, rel_tol=0, abs_tol=1e-12):
                raise ValueError('Explicit domain weights must sum to one, or all be zero')
        return self


class Trip(PersonalDestination):
    importance: Importance | None = None
    visits_per_week: Annotated[int, Field(strict=True, ge=0, le=14)] | None = None
    comfortable_minutes: Number | None = None
    soft_limit_minutes: Number | None = None
    hard_limit_minutes: Number | None = None

    @model_validator(mode='after')
    def thresholds(self):
        if any(v is not None and v <= 0 for v in (self.soft_limit_minutes, self.hard_limit_minutes)):
            raise ValueError('Time limits must be positive')
        if (self.comfortable_minutes is None) != (self.soft_limit_minutes is None):
            raise ValueError('Soft utility requires both comfortable and soft limit times')
        if self.soft_limit_minutes is not None and self.soft_limit_minutes <= self.comfortable_minutes:
            raise ValueError('Soft limit must exceed comfortable time')
        if any(v is not None and v > 1440 for v in (self.comfortable_minutes, self.soft_limit_minutes, self.hard_limit_minutes)):
            raise ValueError('Time limit exceeds one day')
        return self


class ProfileV2(EvidenceModel):
    version: Literal['personal-match-v2'] = 'personal-match-v2'
    housing_goal: Literal['buy', 'rent', 'compare'] = 'buy'
    weights: DomainWeights = Field(default_factory=DomainWeights)
    infrastructure: InfrastructureImportance | None = None
    max_distance_m: dict[Literal['stop_availability','school','kindergarten','healthcare','parks'], Number] = Field(default_factory=dict)
    mode: Mode | None = None
    trips: tuple[Trip, ...] = Field(default=(), max_length=5)
    frequency_weighting_confirmed: bool = False
    maximum_budget: Money | None = None
    comfortable_price: Money | None = None

    @model_validator(mode='after')
    def price_anchors(self):
        if self.comfortable_price is not None and (self.maximum_budget is None or self.comfortable_price >= self.maximum_budget):
            raise ValueError('Comfortable price requires a larger maximum budget')
        return self


class RequestV2(EvidenceModel):
    profile: ProfileV2
    candidate_ids: tuple[Annotated[int, Field(strict=True, gt=0)], ...] | None = Field(default=None, min_length=1, max_length=150)
    point: LocalRequest | None = None

    @model_validator(mode='after')
    def selection(self):
        if self.point is not None and self.candidate_ids is not None:
            raise ValueError('Choose a point or catalogue IDs')
        if self.candidate_ids and len(set(self.candidate_ids)) != len(self.candidate_ids):
            raise ValueError('Duplicate candidate IDs')
        return self


class Constraint(EvidenceModel):
    key: str
    status: Status
    actual: Number | Money | None = None
    limit: Number | Money | None = None
    reason: str | None = None


class Domain(EvidenceModel):
    score: Score | None = None
    weight: Fraction | None
    contribution: Score | None = None
    reason: str | None = None
    evidence: dict = Field(default_factory=dict)


class CandidateV2(EvidenceModel):
    id: int | None
    name: str
    location: LocalRequest | None
    district_id: int | None
    district_name: str | None
    price_from: Money | None
    source: dict
    objective_local: LocalResult | None = None
    objective_district: ObjectiveScore | None = None
    infrastructure: InfrastructureFit | None = None
    domains: dict[str, Domain]
    constraints: tuple[Constraint, ...]
    eligibility: Status
    score: Score | None
    score_reason: str | None
    coverage: Fraction
    bucket: Literal['verified', 'unknown', 'failed']
    explanations: tuple[str, ...]
    limitations: tuple[str, ...]


class DistrictGroup(EvidenceModel):
    district_id: int
    district_name: str
    observed_count: int
    evaluated_count: int
    verified_count: int
    unknown_count: int
    failed_count: int
    best_candidate_id: int | None
    best_observed_match: Score | None


class ResponseV2(EvidenceModel):
    version: Literal['match-recommendations-v2'] = 'match-recommendations-v2'
    profile: ProfileV2
    sample: dict
    candidates: tuple[CandidateV2, ...]
    districts: tuple[DistrictGroup, ...]
    limitations: tuple[str, ...]
