"""Internal, immutable evidence contracts; no score or normalization."""
import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator

from data.osm.contracts import Quality

EVIDENCE_VERSION = "stop-availability-evidence-v1"
ELIGIBILITY_VERSION = "osm-highway-bus-stop-v1"
DISTANCE_METHOD = "postgis-geography-wgs84-spheroid-v1"
LIMITATIONS = (
    "observed_osm_highway_bus_stop_only",
    "source_and_real_world_completeness_unknown",
    "straight_line_distance_not_walking_or_route_distance",
    "dataset_extent_limits_search",
    "no_routes_frequency_schedules_or_service_quality",
    "no_semantic_stop_grouping",
)


class EvidenceModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Coordinate(EvidenceModel):
    """WGS84 lon/lat; malformed/nonfinite input is represented as null, never zero."""
    longitude: float | None
    latitude: float | None

    @field_validator("longitude", "latitude", mode="before")
    @classmethod
    def finite_input(cls, value):
        if type(value) not in (int, float) or not math.isfinite(value):
            return None
        return value

    @property
    def valid(self) -> bool:
        return (self.longitude is not None and self.latitude is not None and
                -180 <= self.longitude <= 180 and -90 <= self.latitude <= 90)


class SnapshotIdentity(EvidenceModel):
    source_id: Literal["osm"] = "osm"
    dataset_key: str
    scope_id: str
    snapshot_version: str
    canonical_checksum: str
    query_version: str | None
    query_hash: str | None
    foundation_eligibility_version: str | None


class NearestStop(EvidenceModel):
    osm_type: Literal["node", "way", "relation"]
    osm_id: StrictInt = Field(gt=0)
    name: str | None
    distance_m: float = Field(ge=0, allow_inf_nan=False)


class PointStopAvailabilityEvidence(EvidenceModel):
    evidence_version: Literal["stop-availability-evidence-v1"] = EVIDENCE_VERSION
    eligibility_version: Literal["osm-highway-bus-stop-v1"] = ELIGIBILITY_VERSION
    distance_method: Literal["postgis-geography-wgs84-spheroid-v1"] = DISTANCE_METHOD
    coordinate: Coordinate
    snapshot: SnapshotIdentity | None
    source_quality: Quality | None
    eligible_stop_count: int | None = Field(ge=0)
    availability: Literal["AVAILABLE", "UNAVAILABLE"]
    unavailable_reason: Literal["invalid_coordinate", "dataset_unavailable", "no_eligible_observations"] | None = None
    nearest_stop: NearestStop | None
    limitations: tuple[str, ...] = LIMITATIONS

    @model_validator(mode="after")
    def consistent(self):
        if self.availability == "AVAILABLE":
            if (not self.coordinate.valid or self.snapshot is None or self.source_quality is None or self.nearest_stop is None or
                    self.unavailable_reason is not None or not self.eligible_stop_count):
                raise ValueError("Available evidence requires coordinate, snapshot and nearest stop")
        elif self.nearest_stop is not None or self.unavailable_reason is None:
            raise ValueError("Unavailable evidence must have a reason and null nearest stop")
        elif self.unavailable_reason == "invalid_coordinate" and self.coordinate.valid:
            raise ValueError("invalid_coordinate requires invalid input")
        elif self.unavailable_reason == "dataset_unavailable" and self.snapshot is not None:
            raise ValueError("dataset_unavailable requires null source snapshot")
        elif self.unavailable_reason == "no_eligible_observations" and (
                self.snapshot is None or self.eligible_stop_count != 0):
            raise ValueError("no_eligible_observations requires an active dataset with no eligible stops")
        return self


class CoveragePoint(EvidenceModel):
    radius_m: float = Field(ge=0, allow_inf_nan=False)
    covered_count: int = Field(ge=0)
    valid_sample_count: int = Field(ge=0)
    share: float | None = Field(ge=0, le=1)


class StopAvailabilitySummary(EvidenceModel):
    evidence_version: Literal["stop-availability-evidence-v1"] = EVIDENCE_VERSION
    eligibility_version: Literal["osm-highway-bus-stop-v1"] = ELIGIBILITY_VERSION
    distance_method: Literal["postgis-geography-wgs84-spheroid-v1"] = DISTANCE_METHOD
    sampling_version: str = Field(min_length=1)
    snapshot: SnapshotIdentity | None
    source_quality: Quality | None
    sample_count: int
    valid_evidence_count: int
    missing_evidence_count: int
    availability: Literal["AVAILABLE", "PARTIAL", "UNAVAILABLE"]
    missing_reasons: dict[str, int]
    median_m: float | None
    p90_m: float | None
    coverage_curve: tuple[CoveragePoint, ...]
    limitations: tuple[str, ...]
