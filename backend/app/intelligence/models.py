"""Persistent external signal provenance and bounded impact metadata."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ExternalSignal(Base):
    __tablename__ = "external_signals"
    __table_args__ = (
        CheckConstraint("source_type IN ('news', 'tender', 'construction', 'government_plan', 'other')",
                        name="ck_external_signals_source_type"),
        CheckConstraint("category IN ('education', 'transport', 'healthcare', 'environment', 'commercial', 'housing')",
                        name="ck_external_signals_category"),
        CheckConstraint("impact_direction IN ('positive', 'negative', 'neutral')",
                        name="ck_external_signals_direction"),
        CheckConstraint("impact_value >= -100 AND impact_value <= 100",
                        name="ck_external_signals_impact_range"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_external_signals_confidence"),
        CheckConstraint("(impact_direction = 'positive' AND impact_value > 0) OR "
                        "(impact_direction = 'negative' AND impact_value < 0) OR "
                        "(impact_direction = 'neutral' AND impact_value = 0)",
                        name="ck_external_signals_direction_value"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    district_id: Mapped[int] = mapped_column(ForeignKey("districts.id"), nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(30), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(30), nullable=False)
    impact_direction: Mapped[str] = mapped_column(String(10), nullable=False)
    impact_value: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    confidence: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    event_date: Mapped[date | None] = mapped_column(Date)
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
