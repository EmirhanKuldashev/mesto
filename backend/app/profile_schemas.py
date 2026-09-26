"""Validation contracts for the Stage 3 onboarding flow."""

from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

HouseholdType = Literal["single", "couple", "family", "family_with_relatives"]
HousingGoal = Literal["buy", "rent", "compare"]
Transport = Literal["car", "public_transport", "walking", "bicycle"]
LifePointType = Literal["work", "partner_work", "school", "kindergarten", "parents", "university", "other"]
FutureChange = Literal["child", "new_job", "no_car", "bigger_family", "relocation", "longer_horizon"]
HomeValue = Literal[
    "family_time", "calm", "financial_stability", "mobility", "green_environment",
    "district_growth", "nearby_infrastructure", "personal_space",
]
PlanningHorizon = Literal["1_2_years", "3_5_years", "5_10_years", "long_term"]


class Child(BaseModel):
    age: int = Field(ge=0, le=17)


class Coordinates(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class LifePointInput(Coordinates):
    type: LifePointType
    name: str = Field(min_length=1, max_length=120)
    importance: int = Field(default=5, ge=1, le=10)
    frequency_per_week: int = Field(default=1, ge=0, le=7)


class LifePointUpsert(LifePointInput):
    profile_id: UUID
    id: int | None = None


class PartnerInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    work_point: Coordinates | None = None
    transport_preferences: list[Transport] = Field(default_factory=list)
    preferences: dict[str, int] = Field(default_factory=dict)
    life_goals: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_preferences(self):
        if any(not 0 <= value <= 100 for value in self.preferences.values()):
            raise ValueError("Partner preference weights must be between 0 and 100")
        return self


class PreferencesInput(BaseModel):
    education_weight: int = Field(default=50, ge=0, le=100)
    kindergarten_weight: int = Field(default=50, ge=0, le=100)
    healthcare_weight: int = Field(default=50, ge=0, le=100)
    transport_weight: int = Field(default=50, ge=0, le=100)
    ecology_weight: int = Field(default=50, ge=0, le=100)
    safety_weight: int = Field(default=50, ge=0, le=100)
    parks_weight: int = Field(default=50, ge=0, le=100)
    shopping_weight: int = Field(default=50, ge=0, le=100)
    entertainment_weight: int = Field(default=50, ge=0, le=100)
    housing_price_weight: int = Field(default=50, ge=0, le=100)
    future_growth_weight: int = Field(default=50, ge=0, le=100)
    quiet_active: int = Field(default=50, ge=0, le=100)
    green_urban: int = Field(default=50, ge=0, le=100)
    center_calm: int = Field(default=50, ge=0, le=100)


class ProfileCreate(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    household_type: HouseholdType = "single"
    adults_count: int = Field(default=1, ge=1, le=12)
    children_count: int = Field(default=0, ge=0, le=12)
    children: list[Child] = Field(default_factory=list)
    housing_goal: HousingGoal = "compare"
    purchase_budget: Decimal | None = Field(default=None, gt=0)
    initial_payment: Decimal | None = Field(default=None, ge=0)
    comfortable_monthly_payment: Decimal | None = Field(default=None, gt=0)
    rent_budget: Decimal | None = Field(default=None, gt=0)
    planning_horizon: PlanningHorizon = "3_5_years"
    car_availability: bool = False
    transport_preferences: list[Transport] = Field(default_factory=lambda: ["public_transport"])
    preferences: PreferencesInput = Field(default_factory=PreferencesInput)
    price_vs_time: int = Field(default=50, ge=0, le=100)
    today_vs_future: int = Field(default=50, ge=0, le=100)
    car_dependency: int = Field(default=50, ge=0, le=100)
    future_changes: list[FutureChange] = Field(default_factory=list)
    home_values: list[HomeValue] = Field(default_factory=list, max_length=3)
    good_home_text: str | None = Field(default=None, max_length=2000)
    partner: PartnerInput | None = None
    life_points: list[LifePointInput] = Field(default_factory=list)
    data_processing_consent: bool

    @model_validator(mode="after")
    def check_profile(self):
        if not self.data_processing_consent:
            raise ValueError("Data processing consent is required to save a profile")
        if self.children_count != len(self.children):
            raise ValueError("children_count must match children")
        if self.household_type == "couple" and (self.adults_count < 2 or self.partner is None):
            raise ValueError("Couple profile needs at least two adults and a partner")
        if self.housing_goal in ("buy", "compare") and self.purchase_budget is None:
            raise ValueError("purchase_budget is required for buy or compare")
        if self.housing_goal in ("rent", "compare") and self.rent_budget is None:
            raise ValueError("rent_budget is required for rent or compare")
        if self.initial_payment is not None and self.purchase_budget is not None and self.initial_payment > self.purchase_budget:
            raise ValueError("initial_payment must not exceed purchase_budget")
        if not self.transport_preferences or len(set(self.transport_preferences)) != len(self.transport_preferences):
            raise ValueError("Choose unique transport preferences")
        if len(set(self.home_values)) != len(self.home_values):
            raise ValueError("Choose unique home values")
        return self


class AnalysisRequestCreate(BaseModel):
    profile_id: UUID
