"""Public Local contracts. Scores retain full precision; presentation rounds."""
import math
from typing import Literal

from pydantic import Field, model_validator

from app.analytics.objective.engine import WEIGHTS
from app.analytics.stop_availability.models import EvidenceModel, SnapshotIdentity

VERSION = "local-objective-v1"
LIMITATIONS = (
    "objective_spatial_characteristic_not_personal_match_or_housing_quality",
    "relative_to_frozen_krasnoyarsk_reference_not_universal",
    "straight_line_distance_not_walking_accessibility_or_travel_time",
    "no_service_quality_capacity_safety_affordability_market_or_growth",
)


class LocalRequest(EvidenceModel):
    latitude: float = Field(strict=True, ge=-90, le=90, allow_inf_nan=False)
    longitude: float = Field(strict=True, ge=-180, le=180, allow_inf_nan=False)


class NearestObject(EvidenceModel):
    source_id: Literal["osm"] = "osm"
    osm_type: Literal["node", "way", "relation"]
    osm_id: int = Field(gt=0)
    name: str | None
    category: Literal["bus_stop", "school", "kindergarten", "clinic", "hospital", "park"]
    distance_m: float = Field(ge=0, allow_inf_nan=False)
    coordinate_representation: str | None = None


class LocalComponent(EvidenceModel):
    key: Literal["stop_availability", "school", "kindergarten", "healthcare", "parks"]
    score: float | None = Field(default=None, ge=0, le=100, allow_inf_nan=False)
    distance_m: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    available: bool
    normalization_version: str
    evidence_version: str
    eligibility_version: str
    reference_id: str
    reference_checksum: str
    distance_method: str
    unavailable_reason: str | None = None
    nearest: NearestObject | None = None
    inside_geometry: bool | None = None
    limitations: tuple[str, ...] = ()
    provenance: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def consistent(self):
        if self.available:
            if self.score is None or self.distance_m is None or self.nearest is None or self.unavailable_reason:
                raise ValueError("Available component requires score, distance and nearest evidence")
            if self.distance_m != self.nearest.distance_m:
                raise ValueError("Nearest and component distances must agree")
            if self.key == "parks" and (self.inside_geometry is None or self.inside_geometry and
                (self.distance_m != 0 or self.nearest.osm_type == "node")):
                raise ValueError("Inside Parks requires area geometry and zero distance")
        elif self.score is not None or not self.unavailable_reason or self.nearest is not None:
            raise ValueError("Unavailable component requires null score/nearest and explicit reason")
        if self.key != "parks" and self.inside_geometry is not None:
            raise ValueError("Inside geometry is a Parks-only statement")
        return self


class LocalResult(EvidenceModel):
    version: Literal["local-objective-v1"] = VERSION
    availability: Literal["AVAILABLE", "UNAVAILABLE"]
    score: float | None = Field(default=None, ge=0, le=100, allow_inf_nan=False)
    location: LocalRequest
    components: dict[str, LocalComponent]
    weights: dict[str, float] = Field(default_factory=lambda: dict(WEIGHTS))
    provenance: dict = Field(default_factory=dict)
    limitations: tuple[str, ...] = LIMITATIONS
    unavailable_reason: str | None = None

    @model_validator(mode="after")
    def consistent(self):
        if set(self.components) != set(WEIGHTS) or any(k != c.key for k, c in self.components.items()):
            raise ValueError("Local requires exactly the five canonical components")
        if self.weights != dict(WEIGHTS):
            raise ValueError("Local uses fixed equal objective weights")
        ready = all(c.available for c in self.components.values())
        if self.availability == "AVAILABLE":
            if not ready or self.score is None or self.unavailable_reason:
                raise ValueError("Available Local requires all five components")
            if not math.isclose(self.score, math.fsum(WEIGHTS[k]*self.components[k].score for k in WEIGHTS), rel_tol=0, abs_tol=1e-12):
                raise ValueError("Local score must equal the full-precision fixed objective formula")
        elif self.score is not None or not self.unavailable_reason or ready:
            raise ValueError("Unavailable Local requires missing evidence and an explicit reason")
        return self
