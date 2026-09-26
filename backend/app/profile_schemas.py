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
LifePointOwner = Literal["primary_user", "partner"]
PreferenceName = Literal[
    "education_weight", "kindergarten_weight", "healthcare_weight", "transport_weight",
    "ecology_weight", "safety_weight", "parks_weight", "shopping_weight",
    "entertainment_weight", "housing_price_weight", "future_growth_weight",
    "quiet_active", "green_urban", "center_calm",
    "price_vs_time", "today_vs_future", "car_dependency",
]


class PreferenceValue(BaseModel):
    value: int | None = Field(default=None, ge=0, le=100)
    is_answered: bool = False
    source: Literal["user", "partner", "default"] = "default"
    confidence: float = Field(default=0, ge=0, le=1)

    @model_validator(mode="after")
    def check_answer(self):
        if self.is_answered:
            if self.value is None or self.source == "default" or self.confidence <= 0:
                raise ValueError("Answered preferences need a value, respondent source and positive confidence")
        elif self.value is not None or self.confidence != 0 or self.source != "default":
            raise ValueError("Unanswered preferences must have null value, default source and zero confidence")
        return self


def unanswered_preference() -> PreferenceValue:
    return PreferenceValue()


class Child(BaseModel):
    age: int = Field(ge=0, le=17)


class Coordinates(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class LifePointInput(Coordinates):
    owner_type: LifePointOwner
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
    preferences: dict[PreferenceName, PreferenceValue] = Field(default_factory=dict)
    life_goals: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_preferences(self):
        if any(value.is_answered and value.source != "partner" for value in self.preferences.values()):
            raise ValueError("Answered partner preferences must have partner source")
        return self


class PreferencesInput(BaseModel):
    education_weight: PreferenceValue = Field(default_factory=unanswered_preference)
    kindergarten_weight: PreferenceValue = Field(default_factory=unanswered_preference)
    healthcare_weight: PreferenceValue = Field(default_factory=unanswered_preference)
    transport_weight: PreferenceValue = Field(default_factory=unanswered_preference)
    ecology_weight: PreferenceValue = Field(default_factory=unanswered_preference)
    safety_weight: PreferenceValue = Field(default_factory=unanswered_preference)
    parks_weight: PreferenceValue = Field(default_factory=unanswered_preference)
    shopping_weight: PreferenceValue = Field(default_factory=unanswered_preference)
    entertainment_weight: PreferenceValue = Field(default_factory=unanswered_preference)
    housing_price_weight: PreferenceValue = Field(default_factory=unanswered_preference)
    future_growth_weight: PreferenceValue = Field(default_factory=unanswered_preference)
    quiet_active: PreferenceValue = Field(default_factory=unanswered_preference)
    green_urban: PreferenceValue = Field(default_factory=unanswered_preference)
    center_calm: PreferenceValue = Field(default_factory=unanswered_preference)
    price_vs_time: PreferenceValue = Field(default_factory=unanswered_preference)
    today_vs_future: PreferenceValue = Field(default_factory=unanswered_preference)
    car_dependency: PreferenceValue = Field(default_factory=unanswered_preference)

    @model_validator(mode="after")
    def check_sources(self):
        if any(value.is_answered and value.source != "user" for value in self.__dict__.values()):
            raise ValueError("Answered user preferences must have user source")
        return self


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
        if any(point.owner_type == "partner" for point in self.life_points) and self.partner is None:
            raise ValueError("Partner life points require a partner profile")
        return self


class AnalysisRequestCreate(BaseModel):
    profile_id: UUID
