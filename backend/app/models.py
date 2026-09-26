"""Normalized domain records. Source metadata travels with every imported fact."""

from datetime import date, datetime
from decimal import Decimal

from geoalchemy2 import Geometry
from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class IdMixin:
    id: Mapped[int] = mapped_column(Integer, primary_key=True)


class SourceFields:
    source_id: Mapped[str] = mapped_column(String(100), index=True)
    source_type: Mapped[str] = mapped_column(String(50))
    source_version: Mapped[str] = mapped_column(String(100))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False)


class UserProfile(IdMixin, Base):
    __tablename__ = "user_profiles"
    name: Mapped[str] = mapped_column(String(120))
    household_size: Mapped[int] = mapped_column(Integer, default=1)
    monthly_income: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PartnerProfile(IdMixin, Base):
    __tablename__ = "partner_profiles"
    user_profile_id: Mapped[int] = mapped_column(ForeignKey("user_profiles.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    monthly_income: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))


class LifePoint(IdMixin, Base):
    __tablename__ = "life_points"
    user_profile_id: Mapped[int] = mapped_column(ForeignKey("user_profiles.id"), index=True)
    label: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(50))
    location: Mapped[str] = mapped_column(Geometry("POINT", srid=4326))
    visits_per_week: Mapped[int] = mapped_column(Integer, default=1)


class UserPreferences(IdMixin, Base):
    __tablename__ = "user_preferences"
    user_profile_id: Mapped[int] = mapped_column(ForeignKey("user_profiles.id"), unique=True)
    budget_min: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    budget_max: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    purchase_mode: Mapped[str] = mapped_column(String(20), default="either")
    weights: Mapped[dict] = mapped_column(JSON, default=dict)


class District(IdMixin, SourceFields, Base):
    __tablename__ = "districts"
    name: Mapped[str] = mapped_column(String(150), index=True)
    boundary: Mapped[str | None] = mapped_column(Geometry("MULTIPOLYGON", srid=4326))


class DistrictMetrics(IdMixin, SourceFields, Base):
    __tablename__ = "district_metrics"
    district_id: Mapped[int] = mapped_column(ForeignKey("districts.id"), index=True)
    metric_key: Mapped[str] = mapped_column(String(80), index=True)
    value: Mapped[Decimal] = mapped_column(Numeric(16, 4))
    unit: Mapped[str] = mapped_column(String(30))
    measured_at: Mapped[date | None] = mapped_column(Date)


class POI(IdMixin, SourceFields, Base):
    __tablename__ = "pois"
    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(80), index=True)
    location: Mapped[str] = mapped_column(Geometry("POINT", srid=4326))


class ResidentialComplex(IdMixin, SourceFields, Base):
    __tablename__ = "residential_complexes"
    name: Mapped[str] = mapped_column(String(200))
    district_id: Mapped[int | None] = mapped_column(ForeignKey("districts.id"))
    location: Mapped[str | None] = mapped_column(Geometry("POINT", srid=4326))
    delivery_date: Mapped[date | None] = mapped_column(Date)


class PropertyOffer(IdMixin, SourceFields, Base):
    __tablename__ = "property_offers"
    complex_id: Mapped[int | None] = mapped_column(ForeignKey("residential_complexes.id"))
    district_id: Mapped[int | None] = mapped_column(ForeignKey("districts.id"))
    price: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    area_sqm: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    rooms: Mapped[int | None] = mapped_column(Integer)
    external_id: Mapped[str | None] = mapped_column(String(120))


class RentListing(IdMixin, SourceFields, Base):
    __tablename__ = "rent_listings"
    district_id: Mapped[int | None] = mapped_column(ForeignKey("districts.id"))
    monthly_rent: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    area_sqm: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    rooms: Mapped[int | None] = mapped_column(Integer)
    location: Mapped[str | None] = mapped_column(Geometry("POINT", srid=4326))
    external_id: Mapped[str | None] = mapped_column(String(120))


class MortgageProgram(IdMixin, SourceFields, Base):
    __tablename__ = "mortgage_programs"
    name: Mapped[str] = mapped_column(String(200))
    annual_rate: Mapped[Decimal] = mapped_column(Numeric(6, 3))
    down_payment_percent: Mapped[Decimal] = mapped_column(Numeric(6, 3))
    max_loan: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    eligibility: Mapped[dict] = mapped_column(JSON, default=dict)


class FutureObject(IdMixin, SourceFields, Base):
    __tablename__ = "future_objects"
    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(80))
    location: Mapped[str | None] = mapped_column(Geometry("POINT", srid=4326))
    expected_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(50), default="planned")


class DataSource(IdMixin, Base):
    __tablename__ = "data_sources"
    source_id: Mapped[str] = mapped_column(String(100), unique=True)
    source_type: Mapped[str] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(String(200))
    url: Mapped[str | None] = mapped_column(Text)
    license: Mapped[str | None] = mapped_column(String(200))
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False)


class SourceVersion(IdMixin, Base):
    __tablename__ = "source_versions"
    source_id: Mapped[str] = mapped_column(ForeignKey("data_sources.source_id"), index=True)
    source_version: Mapped[str] = mapped_column(String(100))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    checksum: Mapped[str | None] = mapped_column(String(128))


class DataQuality(IdMixin, Base):
    __tablename__ = "data_quality"
    source_version_id: Mapped[int] = mapped_column(ForeignKey("source_versions.id"), index=True)
    record_type: Mapped[str] = mapped_column(String(80))
    completeness: Mapped[Decimal] = mapped_column(Numeric(5, 4))
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    warnings: Mapped[list] = mapped_column(JSON, default=list)


class AnalysisSession(IdMixin, Base):
    __tablename__ = "analysis_sessions"
    user_profile_id: Mapped[int] = mapped_column(ForeignKey("user_profiles.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    assumptions: Mapped[dict] = mapped_column(JSON, default=dict)


class Scenario(IdMixin, Base):
    __tablename__ = "scenarios"
    analysis_session_id: Mapped[int] = mapped_column(ForeignKey("analysis_sessions.id"), index=True)
    name: Mapped[str] = mapped_column(String(150))
    parameters: Mapped[dict] = mapped_column(JSON, default=dict)
    results: Mapped[dict] = mapped_column(JSON, default=dict)
    calculation_version: Mapped[str] = mapped_column(String(100))


class Report(IdMixin, Base):
    __tablename__ = "reports"
    analysis_session_id: Mapped[int] = mapped_column(ForeignKey("analysis_sessions.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
