"""Persistent district score and public analytics contracts."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, Numeric, String, func, text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB

from app.analytics.future_growth.models import FutureFactor

from app.db import Base


class DistrictScore(Base):
    __tablename__ = "district_scores"
    __table_args__ = (
        CheckConstraint("total_score IS NULL OR (total_score >= 0 AND total_score <= 100)", name="ck_district_scores_total"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_district_scores_confidence"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("user_profiles.id"), index=True)
    district_id: Mapped[int] = mapped_column(ForeignKey("districts.id"), index=True)
    total_score: Mapped[float | None] = mapped_column(Numeric(5, 2))
    current_score: Mapped[float | None] = mapped_column(Numeric(5, 2))
    future_score: Mapped[float | None] = mapped_column(Numeric(5, 2))
    future_factors: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    lifestyle_score: Mapped[float | None] = mapped_column(Numeric(5, 2))
    infrastructure_score: Mapped[float | None] = mapped_column(Numeric(5, 2))
    transport_score: Mapped[float | None] = mapped_column(Numeric(5, 2))
    future_growth_score: Mapped[float | None] = mapped_column(Numeric(5, 2))
    market_score: Mapped[float | None] = mapped_column(Numeric(5, 2))
    confidence: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False)
    calculation_version: Mapped[str] = mapped_column(String(40), nullable=False, server_default="baseline-v1")
    is_synthetic: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ScoreRequest(BaseModel):
    profile_id: UUID
    district_ids: list[int] = Field(min_length=1, max_length=50)

    @field_validator("district_ids")
    @classmethod
    def valid_ids(cls, values: list[int]) -> list[int]:
        if any(value <= 0 for value in values) or len(values) != len(set(values)):
            raise ValueError("district_ids must be distinct positive integers")
        return values


class CategoryScores(BaseModel):
    lifestyle: float | None
    infrastructure: float | None
    transport: float | None
    future_growth: float | None
    market: float | None


class DistrictReference(BaseModel):
    id: int
    name: str
    slug: str | None


class DistrictScoreResponse(BaseModel):
    id: int
    district: DistrictReference
    score: float | None
    current_score: float | None
    future_score: float | None
    future_growth_score: float | None
    future_factors: list[FutureFactor]
    future_impacts: dict[str, float]
    categories: CategoryScores
    confidence: float
    reasons: list[str]
    warnings: list[str]
    is_synthetic: bool
    calculation_version: str
    created_at: datetime
