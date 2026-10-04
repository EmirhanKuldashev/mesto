"""Normalized domain records. Source metadata travels with every imported fact."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from geoalchemy2 import Geometry
from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
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
    name: Mapped[str | None] = mapped_column(String(120))
    public_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), unique=True, server_default=text("gen_random_uuid()"))
    household_type: Mapped[str] = mapped_column(String(40), server_default="single")
    adults_count: Mapped[int] = mapped_column(Integer, server_default="1")
    children_count: Mapped[int] = mapped_column(Integer, server_default="0")
    children: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    housing_goal: Mapped[str] = mapped_column(String(20), server_default="compare")
    purchase_budget: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    initial_payment: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    comfortable_monthly_payment: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    rent_budget: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    planning_horizon: Mapped[str | None] = mapped_column(String(30))
    commute_minutes: Mapped[int | None] = mapped_column(Integer)
    car_availability: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    transport_preferences: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    future_changes: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    home_values: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    good_home_text: Mapped[str | None] = mapped_column(Text)
    price_vs_time: Mapped[int | None] = mapped_column(Integer)
    today_vs_future: Mapped[int | None] = mapped_column(Integer)
    car_dependency: Mapped[int | None] = mapped_column(Integer)
    data_processing_consent: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    household_size: Mapped[int] = mapped_column(Integer, default=1)
    monthly_income: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PartnerProfile(IdMixin, Base):
    __tablename__ = "partner_profiles"
    user_profile_id: Mapped[int] = mapped_column(ForeignKey("user_profiles.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    monthly_income: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    work_location: Mapped[str | None] = mapped_column(Geometry("POINT", srid=4326))
    transport_preferences: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    preferences: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    life_goals: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))


class LifePoint(IdMixin, Base):
    __tablename__ = "life_points"
    __table_args__ = (CheckConstraint("(owner_type = 'primary_user' AND primary_user_id IS NOT NULL AND partner_profile_id IS NULL) OR (owner_type = 'partner' AND primary_user_id IS NULL AND partner_profile_id IS NOT NULL)", name="ck_life_points_owner"),)
    user_profile_id: Mapped[int] = mapped_column(ForeignKey("user_profiles.id"), index=True)
    owner_type: Mapped[str] = mapped_column(String(20), nullable=False)
    primary_user_id: Mapped[int | None] = mapped_column(ForeignKey("user_profiles.id"), index=True)
    partner_profile_id: Mapped[int | None] = mapped_column(ForeignKey("partner_profiles.id"), index=True)
    label: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(50))
    location: Mapped[str] = mapped_column(Geometry("POINT", srid=4326))
    visits_per_week: Mapped[int] = mapped_column(Integer, default=1)
    importance: Mapped[int] = mapped_column(Integer, server_default="5")


class UserPreferences(IdMixin, Base):
    __tablename__ = "user_preferences"
    user_profile_id: Mapped[int] = mapped_column(ForeignKey("user_profiles.id"), unique=True)
    budget_min: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    budget_max: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    purchase_mode: Mapped[str] = mapped_column(String(20), default="either")
    weights: Mapped[dict] = mapped_column(JSON, default=dict)
    preference_values: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    education_weight: Mapped[int | None] = mapped_column(Integer)
    kindergarten_weight: Mapped[int | None] = mapped_column(Integer)
    healthcare_weight: Mapped[int | None] = mapped_column(Integer)
    transport_weight: Mapped[int | None] = mapped_column(Integer)
    ecology_weight: Mapped[int | None] = mapped_column(Integer)
    safety_weight: Mapped[int | None] = mapped_column(Integer)
    parks_weight: Mapped[int | None] = mapped_column(Integer)
    shopping_weight: Mapped[int | None] = mapped_column(Integer)
    entertainment_weight: Mapped[int | None] = mapped_column(Integer)
    housing_price_weight: Mapped[int | None] = mapped_column(Integer)
    future_growth_weight: Mapped[int | None] = mapped_column(Integer)
    quiet_active: Mapped[int | None] = mapped_column(Integer)
    green_urban: Mapped[int | None] = mapped_column(Integer)
    center_calm: Mapped[int | None] = mapped_column(Integer)


class AnalysisRequest(IdMixin, Base):
    __tablename__ = "analysis_requests"
    user_profile_id: Mapped[int] = mapped_column(ForeignKey("user_profiles.id"), index=True)
    status: Mapped[str] = mapped_column(String(30), server_default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    profile_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    partner_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    life_points_snapshot: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    preferences_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    data_version_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    user_score: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    partner_score: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    family_score: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))


class District(IdMixin, SourceFields, Base):
    __tablename__ = "districts"
    name: Mapped[str] = mapped_column(String(150), index=True)
    boundary: Mapped[str | None] = mapped_column(Geometry("MULTIPOLYGON", srid=4326))
    slug: Mapped[str | None] = mapped_column(String(150), unique=True)
    geometry: Mapped[str | None] = mapped_column(Geometry("MULTIPOLYGON", srid=4326))
    centroid: Mapped[str | None] = mapped_column(Geometry("POINT", srid=4326))
    population: Mapped[int | None] = mapped_column(Integer)
    area_km2: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    density: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class DistrictMetrics(IdMixin, SourceFields, Base):
    __tablename__ = "district_metrics"
    district_id: Mapped[int] = mapped_column(ForeignKey("districts.id"), index=True)
    metric_key: Mapped[str] = mapped_column(String(80), index=True)
    value: Mapped[Decimal] = mapped_column(Numeric(16, 4))
    unit: Mapped[str] = mapped_column(String(30))
    measured_at: Mapped[date | None] = mapped_column(Date)


class POI(IdMixin, SourceFields, Base):
    __tablename__ = "pois"
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    category: Mapped[str] = mapped_column(String(80), index=True)
    location: Mapped[str] = mapped_column(Geometry("POINT", srid=4326))
    geometry: Mapped[str | None] = mapped_column(Geometry("POINT", srid=4326))
    external_id: Mapped[str | None] = mapped_column(String(120))
    subcategory: Mapped[str | None] = mapped_column(String(80))
    district_id: Mapped[int | None] = mapped_column(ForeignKey("districts.id"), index=True)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)


class ResidentialComplex(IdMixin, SourceFields, Base):
    __tablename__ = "residential_complexes"
    __table_args__ = (UniqueConstraint("source_id", "external_id", name="uq_residential_complex_source_external"),)
    name: Mapped[str] = mapped_column(String(200))
    external_id: Mapped[str | None] = mapped_column(String(120))
    url: Mapped[str | None] = mapped_column(Text)
    address: Mapped[str | None] = mapped_column(String(250))
    district_id: Mapped[int | None] = mapped_column(ForeignKey("districts.id"))
    location: Mapped[str | None] = mapped_column(Geometry("POINT", srid=4326))
    delivery_date: Mapped[date | None] = mapped_column(Date)
    developer: Mapped[str | None] = mapped_column(String(200))
    building_class: Mapped[str | None] = mapped_column(String(80))
    price_from: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    price_per_sqm: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    available_units: Mapped[int | None] = mapped_column(Integer)
    layouts: Mapped[list] = mapped_column(JSONB, default=list)


class PropertyOffer(IdMixin, SourceFields, Base):
    __tablename__ = "property_offers"
    __table_args__ = (UniqueConstraint("source_id", "external_id", name="uq_property_offers_source_external"),)
    source: Mapped[str] = mapped_column(String(100), default=lambda context: context.get_current_parameters()["source_id"])
    complex_id: Mapped[int | None] = mapped_column(ForeignKey("residential_complexes.id"))
    district_id: Mapped[int | None] = mapped_column(ForeignKey("districts.id"))
    price: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    area_sqm: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    rooms: Mapped[int | None] = mapped_column(Integer)
    external_id: Mapped[str | None] = mapped_column(String(120))
    floor: Mapped[int | None] = mapped_column(Integer)
    address: Mapped[str | None] = mapped_column(String(250))
    url: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(String(120))
    location: Mapped[str | None] = mapped_column(Geometry("POINT", srid=4326))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class RentListing(IdMixin, SourceFields, Base):
    __tablename__ = "rent_listings"
    district_id: Mapped[int | None] = mapped_column(ForeignKey("districts.id"))
    monthly_rent: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    area_sqm: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    rooms: Mapped[int | None] = mapped_column(Integer)
    location: Mapped[str | None] = mapped_column(Geometry("POINT", srid=4326))
    external_id: Mapped[str | None] = mapped_column(String(120))
    address: Mapped[str | None] = mapped_column(String(250))


class MortgageProgram(IdMixin, SourceFields, Base):
    __tablename__ = "mortgage_programs"
    name: Mapped[str] = mapped_column(String(200))
    annual_rate: Mapped[Decimal] = mapped_column(Numeric(6, 3))
    down_payment_percent: Mapped[Decimal] = mapped_column(Numeric(6, 3))
    max_loan: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    eligibility: Mapped[dict] = mapped_column(JSON, default=dict)
    provider: Mapped[str | None] = mapped_column(String(200))
    requirements: Mapped[dict] = mapped_column(JSONB, default=dict)
    region: Mapped[str | None] = mapped_column(String(100))
    official_url: Mapped[str | None] = mapped_column(Text)


class FutureObject(IdMixin, SourceFields, Base):
    __tablename__ = "future_objects"
    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(80))
    district_id: Mapped[int | None] = mapped_column(ForeignKey("districts.id"), index=True)
    location: Mapped[str | None] = mapped_column(Geometry("POINT", srid=4326))
    geometry: Mapped[str | None] = mapped_column(Geometry("POINT", srid=4326))
    expected_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(50), default="planned")
    planned_year: Mapped[int | None] = mapped_column(Integer)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    source: Mapped[str | None] = mapped_column(String(200))
    source_document: Mapped[str | None] = mapped_column(Text)
    source_date: Mapped[date | None] = mapped_column(Date)


class DataSource(IdMixin, Base):
    __tablename__ = "data_sources"
    source_id: Mapped[str] = mapped_column(String(100), unique=True)
    source_type: Mapped[str] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(String(200))
    url: Mapped[str | None] = mapped_column(Text)
    license: Mapped[str | None] = mapped_column(String(200))
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False)
    organization: Mapped[str | None] = mapped_column(String(200))


class SourceVersion(IdMixin, Base):
    __tablename__ = "source_versions"
    source_id: Mapped[str] = mapped_column(ForeignKey("data_sources.source_id"), index=True)
    source_version: Mapped[str] = mapped_column(String(100))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    checksum: Mapped[str | None] = mapped_column(String(128))
    record_count: Mapped[int | None] = mapped_column(Integer)


class DataQuality(IdMixin, Base):
    __tablename__ = "data_quality"
    source_version_id: Mapped[int] = mapped_column(ForeignKey("source_versions.id"), index=True)
    record_type: Mapped[str] = mapped_column(String(80))
    completeness: Mapped[Decimal] = mapped_column(Numeric(5, 4))
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    entity_type: Mapped[str | None] = mapped_column(String(80))
    entity_id: Mapped[int | None] = mapped_column(Integer)
    freshness: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    forecast_share: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    limitations: Mapped[list] = mapped_column(JSONB, default=list)


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

# Register the analytics table alongside existing SQLAlchemy models.
from app.analytics.models import DistrictScore  # noqa: E402,F401
from app.intelligence.models import ExternalSignal  # noqa: E402,F401
