"""API and adapter contracts. GeoJSON coordinates use longitude, latitude order."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Schema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class SourceMetadata(Schema):
    source_id: str
    source_type: str
    source_version: str
    fetched_at: datetime
    valid_from: date | None = None
    valid_to: date | None = None
    is_synthetic: bool = False

    @model_validator(mode="after")
    def validate_dates(self):
        if self.valid_from and self.valid_to and self.valid_from > self.valid_to:
            raise ValueError("valid_from must be on or before valid_to")
        return self


class GeoPoint(Schema):
    longitude: float = Field(ge=-180, le=180)
    latitude: float = Field(ge=-90, le=90)


class UserProfile(Schema):
    id: int | None = None
    name: str
    household_size: int = Field(default=1, ge=1)
    monthly_income: Decimal | None = Field(default=None, ge=0)


class PartnerProfile(Schema):
    id: int | None = None
    user_profile_id: int
    name: str
    monthly_income: Decimal | None = Field(default=None, ge=0)


class LifePoint(Schema):
    id: int | None = None
    user_profile_id: int
    label: str
    kind: str
    location: GeoPoint
    visits_per_week: int = Field(default=1, ge=0)


class UserPreferences(Schema):
    id: int | None = None
    user_profile_id: int
    budget_min: Decimal | None = Field(default=None, ge=0)
    budget_max: Decimal | None = Field(default=None, ge=0)
    purchase_mode: str = "either"
    weights: dict[str, float] = Field(default_factory=dict)


class District(SourceMetadata):
    id: int | None = None
    name: str
    boundary_geojson: dict[str, Any] | None = None


class DistrictMetrics(SourceMetadata):
    id: int | None = None
    district_id: int
    metric_key: str
    value: Decimal
    unit: str
    measured_at: date | None = None


class POI(SourceMetadata):
    id: int | None = None
    name: str
    category: str
    location: GeoPoint


class ResidentialComplex(SourceMetadata):
    id: int | None = None
    name: str
    district_id: int | None = None
    location: GeoPoint | None = None
    delivery_date: date | None = None


class PropertyOffer(SourceMetadata):
    id: int | None = None
    complex_id: int | None = None
    district_id: int | None = None
    price: Decimal = Field(ge=0)
    area_sqm: Decimal = Field(gt=0)
    rooms: int | None = Field(default=None, ge=0)
    external_id: str | None = None


class RentListing(SourceMetadata):
    id: int | None = None
    district_id: int | None = None
    monthly_rent: Decimal = Field(ge=0)
    area_sqm: Decimal | None = Field(default=None, gt=0)
    rooms: int | None = Field(default=None, ge=0)
    location: GeoPoint | None = None
    external_id: str | None = None


class MortgageProgram(SourceMetadata):
    id: int | None = None
    name: str
    annual_rate: Decimal = Field(ge=0)
    down_payment_percent: Decimal = Field(ge=0, le=100)
    max_loan: Decimal | None = Field(default=None, ge=0)
    eligibility: dict[str, Any] = Field(default_factory=dict)


class FutureObject(SourceMetadata):
    id: int | None = None
    name: str
    category: str
    location: GeoPoint | None = None
    expected_date: date | None = None
    status: str = "planned"


class DataSource(Schema):
    id: int | None = None
    source_id: str
    source_type: str
    name: str
    url: str | None = None
    license: str | None = None
    is_synthetic: bool = False


class SourceVersion(Schema):
    id: int | None = None
    source_id: str
    source_version: str
    fetched_at: datetime
    valid_from: date | None = None
    valid_to: date | None = None
    checksum: str | None = None


class DataQuality(Schema):
    id: int | None = None
    source_version_id: int
    record_type: str
    completeness: Decimal = Field(ge=0, le=1)
    checked_at: datetime | None = None
    warnings: list[str] = Field(default_factory=list)


class AnalysisSession(Schema):
    id: int | None = None
    user_profile_id: int
    created_at: datetime | None = None
    assumptions: dict[str, Any] = Field(default_factory=dict)


class Scenario(Schema):
    id: int | None = None
    analysis_session_id: int
    name: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    results: dict[str, Any] = Field(default_factory=dict)
    calculation_version: str


class Report(Schema):
    id: int | None = None
    analysis_session_id: int
    title: str
    snapshot: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
