"""Recommendation domain records; calculated on demand, not persisted."""

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


@dataclass(frozen=True)
class MatchProfile:
    household_type: str
    children_ages: tuple[int, ...] = ()
    housing_goal: str = "compare"
    has_purchase_budget: bool = False
    has_rent_budget: bool = False
    planning_horizon: str | None = None
    transport_preferences: tuple[str, ...] = ()
    home_values: tuple[str, ...] = ()
    preferences: dict = field(default_factory=dict)
    life_point_kinds: tuple[str, ...] = ()
    work_point_priority: float = 0.0


class DistrictRecommendation(BaseModel):
    district_id: int
    district_name: str
    profile_id: UUID
    match_score: float = Field(ge=0, le=100)
    district_score: float | None = Field(default=None, ge=0, le=100)
    future_score: float | None = Field(default=None, ge=0, le=100)
    rank: int = Field(ge=1)
    reasons: list[str]
    warnings: list[str]
    created_at: datetime
