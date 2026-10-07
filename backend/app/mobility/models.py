from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

Mode = Literal["car", "public_transport"]
FiniteNumber = Annotated[float, Field(strict=True, allow_inf_nan=False)]


class Coordinate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False, strict=True)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False, strict=True)


class PersonalDestination(Coordinate):
    label: str = Field(default="", max_length=80, strict=True)
    kind: Literal["work", "university", "school", "relatives", "other"] = "other"


class MobilityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    origin: Coordinate
    destination: PersonalDestination
    mode: Mode
    departure_time: AwareDatetime | None = None

    @model_validator(mode="after")
    def car_is_static(self):
        if self.mode == "car" and self.departure_time is not None:
            raise ValueError("CAR V1 does not support departure_time or traffic")
        return self


class Snap(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    location: Coordinate
    distance_meters: float = Field(ge=0, allow_inf_nan=False, strict=True)


class RouteGeometry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    type: Literal["LineString"] = "LineString"
    # Each pair is longitude, latitude, as specified by GeoJSON.
    coordinates: tuple[tuple[FiniteNumber, FiniteNumber], ...] = Field(min_length=2, max_length=20000)

    @model_validator(mode="after")
    def wgs84(self):
        for longitude, latitude in self.coordinates:
            Coordinate(latitude=latitude, longitude=longitude)
        return self


class RouteFacts(BaseModel):
    """Provider-neutral facts. Failure contains no residual route metrics."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    availability: Literal["AVAILABLE", "UNAVAILABLE"]
    duration_seconds: float | None = Field(default=None, ge=0, allow_inf_nan=False, strict=True)
    distance_meters: float | None = Field(default=None, ge=0, allow_inf_nan=False, strict=True)
    provider: str | None = None
    provider_version: str | None = None
    data_timestamp: AwareDatetime | None = None
    dataset_id: str | None = None
    dataset_sha256: str | None = None
    geometry: RouteGeometry | None = None
    origin_snap: Snap | None = None
    destination_snap: Snap | None = None
    limitations: tuple[str, ...] = ()
    unavailable_reason: str | None = None

    @model_validator(mode="after")
    def consistent(self):
        metrics = (self.duration_seconds, self.distance_meters)
        if self.availability == "AVAILABLE":
            if any(v is None for v in metrics) or not self.provider or not self.provider_version or self.unavailable_reason is not None:
                raise ValueError("Available route requires real metrics and provenance")
        elif not self.unavailable_reason or any(v is not None for v in (*metrics, self.geometry, self.origin_snap, self.destination_snap)):
            raise ValueError("Unavailable route must have a reason and null metrics")
        return self


class MobilityResult(RouteFacts):
    version: Literal["mobility-v1"] = "mobility-v1"
    mode: Mode
    origin: Coordinate
    destination: PersonalDestination
    departure_time: AwareDatetime | None = None
    traffic: Literal["not_included", "not_available"]
