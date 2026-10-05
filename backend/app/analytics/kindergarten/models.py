"""Observed kindergarten proximity, not capacity, admission or childcare quality."""
from typing import Literal

from pydantic import Field, StrictInt, model_validator

# Reuse only generic immutable contracts; no dependency on StopAvailabilityService.
from app.analytics.stop_availability.models import (
    DISTANCE_METHOD, Coordinate, CoveragePoint, EvidenceModel, SnapshotIdentity,
)
from data.osm.contracts import Quality
from app.analytics.school.models import source_ready  # Generic foundation quality gate only.

EVIDENCE_VERSION = "kindergarten-evidence-v1"
ELIGIBILITY_VERSION = "kindergarten-osm-eligibility-v1"
LIMITATIONS = (
    "observed_osm_amenity_kindergarten_only",
    "source_and_real_world_completeness_and_freshness_unknown",
    "canonical_observation_point_not_entrance_or_boundary",
    "straight_line_spheroidal_distance_not_walking_distance_or_travel_time",
    "dataset_extent_limits_search",
    "no_capacity_places_public_private_cost_age_groups_or_kindergarten_quality",
    "no_semantic_kindergarten_deduplication",
)


class KindergartenObservation(EvidenceModel):
    osm_type: Literal["node", "way", "relation"]
    osm_id: StrictInt = Field(gt=0)
    name: str | None
    coordinate_representation: Literal["node_coordinate", "overpass_center"]
    distance_m: float = Field(ge=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def representation(self):
        expected = "node_coordinate" if self.osm_type == "node" else "overpass_center"
        if self.coordinate_representation != expected:
            raise ValueError("OSM type and coordinate representation must agree")
        return self


class PointKindergartenAvailabilityEvidence(EvidenceModel):
    evidence_version: Literal["kindergarten-evidence-v1"] = EVIDENCE_VERSION
    eligibility_version: Literal["kindergarten-osm-eligibility-v1"] = ELIGIBILITY_VERSION
    distance_method: Literal["postgis-geography-wgs84-spheroid-v1"] = DISTANCE_METHOD
    coordinate: Coordinate
    snapshot: SnapshotIdentity | None
    source_quality: Quality | None
    eligible_kindergarten_count: int | None = Field(ge=0)
    availability: Literal["AVAILABLE", "UNAVAILABLE"]
    unavailable_reason: Literal["invalid_coordinate", "dataset_unavailable", "no_eligible_observations",
                                "version_quality_failure"] | None = None
    nearest_kindergarten: KindergartenObservation | None
    limitations: tuple[str, ...] = LIMITATIONS

    @model_validator(mode="after")
    def consistent(self):
        if self.availability == "AVAILABLE":
            if (not self.coordinate.valid or self.snapshot is None or not source_ready(self.snapshot,self.source_quality)
                    or self.nearest_kindergarten is None or self.unavailable_reason is not None or not self.eligible_kindergarten_count):
                raise ValueError("Available Kindergarten evidence requires validated source and nearest observation")
        elif self.nearest_kindergarten is not None or self.unavailable_reason is None:
            raise ValueError("Unavailable Kindergarten evidence requires reason and null nearest kindergarten")
        elif self.unavailable_reason == "invalid_coordinate" and self.coordinate.valid:
            raise ValueError("invalid_coordinate requires invalid input")
        elif self.unavailable_reason == "dataset_unavailable" and self.snapshot is not None:
            raise ValueError("dataset_unavailable requires null snapshot")
        elif self.unavailable_reason == "no_eligible_observations" and (
                self.snapshot is None or self.eligible_kindergarten_count != 0):
            raise ValueError("no_eligible_observations requires active dataset and zero eligible observations")
        elif self.unavailable_reason == "version_quality_failure" and (
                self.snapshot is None or source_ready(self.snapshot,self.source_quality)):
            raise ValueError("version_quality_failure requires an unsupported source contract")
        return self


class KindergartenAvailabilitySummary(EvidenceModel):
    evidence_version: Literal["kindergarten-evidence-v1"] = EVIDENCE_VERSION
    eligibility_version: Literal["kindergarten-osm-eligibility-v1"] = ELIGIBILITY_VERSION
    distance_method: Literal["postgis-geography-wgs84-spheroid-v1"] = DISTANCE_METHOD
    sampling_version: str = Field(min_length=1)
    snapshot: SnapshotIdentity | None
    source_quality: Quality | None
    sample_count: int = Field(ge=0)
    valid_evidence_count: int = Field(ge=0)
    missing_evidence_count: int = Field(ge=0)
    availability: Literal["AVAILABLE", "PARTIAL", "UNAVAILABLE"]
    missing_reasons: dict[str, int]
    median_m: float | None
    p90_m: float | None
    coverage_curve: tuple[CoveragePoint, ...]
    limitations: tuple[str, ...]
