"""Observed OSM park geometry proximity, not recreational provision or quality."""
from typing import Literal

from pydantic import Field, StrictInt, model_validator

# Reuse only generic immutable contracts; no dependency on StopAvailabilityService.
from app.analytics.stop_availability.models import (
    DISTANCE_METHOD, Coordinate, CoveragePoint, EvidenceModel, SnapshotIdentity,
)
from data.osm.park_geometry import GEOMETRY_SNAPSHOT, GEOMETRY_SHA256, RAW_SHA256, BASELINE_VERSION, BASELINE_SHA256
from data.osm.contracts import Quality
from app.analytics.school.models import source_ready  # Generic foundation quality gate only.

EVIDENCE_VERSION = "parks-evidence-v1"
ELIGIBILITY_VERSION = "parks-osm-eligibility-v1"
LIMITATIONS = (
    "observed_osm_leisure_park_geometry_only",
    "geometry_timestamp_20261005T134520Z_differs_from_baseline_20261004T131951Z",
    "baseline_identity_set_only_no_new_park_discovery",
    "source_and_real_world_completeness_and_freshness_unknown",
    "straight_line_spheroidal_distance_not_walking_distance_or_travel_time",
    "no_quality_safety_landscaping_entrance_access_routes_vegetation_or_green_area_per_capita",
    "no_population_weighted_green_provision_or_semantic_deduplication",
    "way_31959413_leisure_park_and_landuse_cemetery_retained",
)


class GeometrySnapshotIdentity(EvidenceModel):
    dataset_id: Literal["osm-park-geometry"] = "osm-park-geometry"
    geometry_version: Literal["parks-geometry-v1"] = "parks-geometry-v1"
    snapshot_version: str = GEOMETRY_SNAPSHOT
    canonical_checksum: str = GEOMETRY_SHA256
    raw_checksum: str = RAW_SHA256
    source_timestamp: Literal["2026-10-05T13:45:20Z"] = "2026-10-05T13:45:20Z"
    baseline_version: str = BASELINE_VERSION
    baseline_checksum: str = BASELINE_SHA256

    @model_validator(mode="after")
    def accepted(self):
        if (self.snapshot_version != GEOMETRY_SNAPSHOT or self.canonical_checksum != GEOMETRY_SHA256
                or self.raw_checksum != RAW_SHA256 or self.baseline_version != BASELINE_VERSION
                or self.baseline_checksum != BASELINE_SHA256):
            raise ValueError("Unsupported geometry snapshot identity")
        return self



class ParksObservation(EvidenceModel):
    osm_type: Literal["node", "way", "relation"]
    osm_id: StrictInt = Field(gt=0)
    name: str | None
    coordinate_representation: Literal["node_coordinate", "osm_polygon", "osm_multipolygon"]
    inside_park_geometry: bool
    distance_m: float = Field(ge=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def representation(self):
        expected = {"node":"node_coordinate", "way":"osm_polygon", "relation":"osm_multipolygon"}[self.osm_type]
        if self.coordinate_representation != expected:
            raise ValueError("OSM type and coordinate representation must agree")
        if self.inside_park_geometry and (self.osm_type == "node" or self.distance_m != 0):
            raise ValueError("Inside park requires area geometry and zero distance")
        return self


class PointParksAvailabilityEvidence(EvidenceModel):
    evidence_version: Literal["parks-evidence-v1"] = EVIDENCE_VERSION
    eligibility_version: Literal["parks-osm-eligibility-v1"] = ELIGIBILITY_VERSION
    distance_method: Literal["postgis-geography-wgs84-spheroid-v1"] = DISTANCE_METHOD
    coordinate: Coordinate
    snapshot: SnapshotIdentity | None
    source_quality: Quality | None
    geometry_snapshot: GeometrySnapshotIdentity | None
    eligible_parks_count: int | None = Field(ge=0)
    availability: Literal["AVAILABLE", "UNAVAILABLE"]
    unavailable_reason: Literal["invalid_coordinate", "dataset_unavailable", "no_eligible_observations",
                                "version_quality_failure", "geometry_unavailable", "geometry_baseline_mismatch", "geometry_invalid"] | None = None
    nearest_parks: ParksObservation | None
    limitations: tuple[str, ...] = LIMITATIONS

    @model_validator(mode="after")
    def consistent(self):
        if self.availability == "AVAILABLE":
            if (not self.coordinate.valid or self.snapshot is None or not source_ready(self.snapshot,self.source_quality)
                    or self.geometry_snapshot is None or self.nearest_parks is None or self.unavailable_reason is not None or not self.eligible_parks_count):
                raise ValueError("Available Parks evidence requires validated source and nearest observation")
            if (self.snapshot.snapshot_version,self.snapshot.canonical_checksum) != (
                    self.geometry_snapshot.baseline_version,self.geometry_snapshot.baseline_checksum):
                raise ValueError("Geometry belongs to a different baseline")
        elif self.nearest_parks is not None or self.unavailable_reason is None:
            raise ValueError("Unavailable Parks evidence requires reason and null nearest parks")
        elif self.unavailable_reason == "invalid_coordinate" and self.coordinate.valid:
            raise ValueError("invalid_coordinate requires invalid input")
        elif self.unavailable_reason == "dataset_unavailable" and self.snapshot is not None:
            raise ValueError("dataset_unavailable requires null snapshot")
        elif self.unavailable_reason == "no_eligible_observations" and (
                self.snapshot is None or self.eligible_parks_count != 0):
            raise ValueError("no_eligible_observations requires active dataset and zero eligible observations")
        elif self.unavailable_reason == "version_quality_failure" and (
                self.snapshot is None or source_ready(self.snapshot,self.source_quality)):
            raise ValueError("version_quality_failure requires an unsupported source contract")
        return self


class ParksAvailabilitySummary(EvidenceModel):
    evidence_version: Literal["parks-evidence-v1"] = EVIDENCE_VERSION
    eligibility_version: Literal["parks-osm-eligibility-v1"] = ELIGIBILITY_VERSION
    distance_method: Literal["postgis-geography-wgs84-spheroid-v1"] = DISTANCE_METHOD
    sampling_version: str = Field(min_length=1)
    snapshot: SnapshotIdentity | None
    source_quality: Quality | None
    geometry_snapshot: GeometrySnapshotIdentity | None
    sample_count: int = Field(ge=0)
    valid_evidence_count: int = Field(ge=0)
    missing_evidence_count: int = Field(ge=0)
    availability: Literal["AVAILABLE", "PARTIAL", "UNAVAILABLE"]
    missing_reasons: dict[str, int]
    median_m: float | None
    p90_m: float | None
    inside_park_count: int = Field(ge=0)
    share_inside_park_geometry: float | None = Field(ge=0, le=1)
    coverage_curve: tuple[CoveragePoint, ...]
    limitations: tuple[str, ...]

    @model_validator(mode="after")
    def counts_consistent(self):
        expected = self.inside_park_count/self.valid_evidence_count if self.valid_evidence_count else None
        if (self.inside_park_count > self.valid_evidence_count or
                self.valid_evidence_count+self.missing_evidence_count != self.sample_count or
                self.share_inside_park_geometry != expected):
            raise ValueError("Raw counts and zero-distance share disagree")
        return self
