"""Read-only public signal contract, including explicit demo provenance."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


class SignalResponse(BaseModel):
    id: int
    district_id: int
    source_type: Literal["news", "tender", "construction", "government_plan", "other"]
    title: str
    description: str | None
    category: Literal["education", "transport", "healthcare", "environment", "commercial", "housing"]
    impact_direction: Literal["positive", "negative", "neutral"]
    impact_value: float = Field(ge=-100, le=100)
    impact: str
    future_growth_impact: float
    confidence: float = Field(ge=0, le=1)
    event_date: date | None
    is_demo: bool
    created_at: datetime


class SignalsResponse(BaseModel):
    signals: list[SignalResponse]

class SignalImpactResponse(BaseModel):
    signal_id: int
    source_type: str
    title: str
    category: str
    future_growth_impact: float
    confidence: float = Field(ge=0, le=1)
    is_demo: bool
