"""Typed evidence and output for a future-development signal."""

from dataclasses import dataclass, field
from datetime import date

from pydantic import BaseModel, Field
from app.intelligence.impact import SignalImpact


@dataclass(frozen=True)
class FutureObjectEvidence:
    id: int
    district_id: int | None
    name: str
    category: str
    status: str
    planned_year: int | None = None
    expected_date: date | None = None
    confidence: float | None = None
    distance_km: float | None = None
    is_synthetic: bool = False


class FutureFactor(BaseModel):
    object_id: int
    name: str
    type: str
    year: int | None
    status: str
    impact: dict[str, float]
    reason: str
    distance_km: float | None = Field(default=None, ge=0)
    confidence: float = Field(ge=0, le=1)
    is_synthetic: bool


@dataclass
class FutureGrowthResult:
    score: float | None
    factors: list[FutureFactor] = field(default_factory=list)
    category_impacts: dict[str, float] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    signal_impacts: list[SignalImpact] = field(default_factory=list)
