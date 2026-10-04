"""On-demand market DTOs. No database tables or score fields."""

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_serializer


class SampleMetadata(BaseModel):
    observed_count: int = Field(ge=0)
    known_price_count: int = Field(ge=0)
    unknown_price_count: int = Field(ge=0)
    source: list[str]
    source_version: list[str]
    snapshot_date_from: datetime | None
    snapshot_date_to: datetime | None


class MarketContext(SampleMetadata):
    district_id: int
    min_starting_price: Decimal | None
    median_starting_price: Decimal | None
    max_starting_price: Decimal | None
    currency: Literal["RUB"] = "RUB"
    observation_unit: Literal["residential_complex"] = "residential_complex"
    price_basis: Literal["starting_price"] = "starting_price"
    limitations: list[str]

    @field_serializer("min_starting_price", "median_starting_price", "max_starting_price", when_used="json")
    def serialize_price(self, value: Decimal | None):
        return float(value) if value is not None else None


class ObservedAffordability(BaseModel):
    methodology_version: Literal["observed-starting-price-v1"] = "observed-starting-price-v1"
    goal: Literal["purchase", "rent"]
    status: Literal["known_value", "known_zero", "unknown", "not_applicable"]
    reason_code: Literal["observed_prices", "no_matches", "budget_missing", "no_observations", "goal_not_selected"]
    budget: Decimal | None
    currency: Literal["RUB"] = "RUB"
    observation_unit: Literal["residential_complex", "listing"]
    price_basis: Literal["starting_price", "monthly_rent"]
    within_budget_count: int | None = Field(ge=0)
    known_price_count: int = Field(ge=0)
    observed_count: int = Field(ge=0)
    unknown_price_count: int = Field(ge=0)
    within_budget_share: float | None = Field(ge=0, le=1)
    budget_to_median_ratio: float | None
    sample_metadata: SampleMetadata
    limitations: list[str]
    ranking_eligible: Literal[False] = False

    @field_serializer("budget", when_used="json")
    def serialize_budget(self, value: Decimal | None):
        return float(value) if value is not None else None


class AffordabilityResults(BaseModel):
    purchase: ObservedAffordability
    rent: ObservedAffordability


class MarketAssessment(BaseModel):
    market_context: MarketContext
    affordability: AffordabilityResults


class AffordabilityRequest(BaseModel):
    profile_id: UUID
    district_id: int = Field(gt=0)
