"""Versioned source contracts, deliberately separate from DB entities/scores."""

import hashlib
import json
from datetime import datetime, timezone
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator

CATEGORIES = ("school", "kindergarten", "hospital", "clinic", "park", "bus_stop")
BUILDER_VERSION = "osm-foundation-v1"
ELIGIBILITY_VERSION = "osm-poi-eligibility-v1"


def canonical_bytes(value) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def checksum(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")


class Extent(Contract):
    """WGS84 rectangle, explicit west/south/east/north; no city special cases."""
    west: float
    south: float
    east: float
    north: float

    @model_validator(mode="after")
    def valid(self):
        if not (-180 <= self.west < self.east <= 180 and -90 <= self.south < self.north <= 90):
            raise ValueError("Invalid WGS84 extent")
        return self

    def contains(self, longitude: float, latitude: float) -> bool:
        return self.west <= longitude <= self.east and self.south <= latitude <= self.north


class Selector(Contract):
    key: str
    values: tuple[str, ...]


class QueryDefinition(Contract):
    query_version: str = Field(min_length=1)
    source: Literal["OSM/Overpass"]
    timeout_seconds: int = Field(ge=1, le=300)
    output_mode: Literal["center"]
    selectors: tuple[Selector, ...]

    @model_validator(mode="after")
    def scope(self):
        # No taxonomy expansion or arbitrary query injection through config.
        mapping = {s.key: s.values for s in self.selectors}
        expected = {"amenity": {"school", "kindergarten", "hospital", "clinic"},
                    "leisure": {"park"}, "highway": {"bus_stop"}}
        if len(mapping) != len(self.selectors) or set(mapping) != set(expected):
            raise ValueError("Unsupported selector keys")
        if any(set(mapping[k]) != values or len(mapping[k]) != len(values) for k, values in expected.items()):
            raise ValueError("Foundation V1 retains the six existing categories")
        return self


class Part(Contract):
    part_id: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    extent: Extent
    query_text: str | None = None
    query_hash: str | None = None
    request_reference: str | None = None
    artifact_reference: str | None = None
    artifact_checksum: str | None = None
    source_base_timestamp: datetime | None = None
    fetched_at: datetime | None = None
    collection_status: Literal["SUCCESS", "FAILED", "PARTIAL", "UNKNOWN"]
    http_status: int | None = None
    element_count: StrictInt | None = Field(default=None, ge=0)
    remark: str | None = None
    error: str | None = None

    @field_validator("source_base_timestamp", "fetched_at")
    @classmethod
    def aware(cls, value):
        if value is not None and value.utcoffset() is None:
            raise ValueError("Source timestamps must include a timezone")
        return value.astimezone(timezone.utc) if value is not None else None


class Manifest(Contract):
    dataset_id: str = Field(min_length=1, max_length=100)
    scope_id: str = Field(min_length=1, max_length=100)
    snapshot_id: str = Field(min_length=1, max_length=100)
    source_id: Literal["osm"] = "osm"
    query_definition: QueryDefinition
    query_version: str
    query_hash: str
    extent: Extent
    requested_as_of: datetime | None = None
    parts: tuple[Part, ...] = Field(min_length=1)
    built_at: datetime | None = None
    builder_version: Literal["osm-foundation-v1"] = BUILDER_VERSION
    category_scope: tuple[str, ...] = CATEGORIES
    known_limitations: tuple[str, ...] = ()

    @field_validator("requested_as_of", "built_at")
    @classmethod
    def aware(cls, value):
        return Part.aware(value)

    @model_validator(mode="after")
    def identities(self):
        if len({p.part_id for p in self.parts}) != len(self.parts):
            raise ValueError("Duplicate part identity")
        if self.query_version != self.query_definition.query_version:
            raise ValueError("Query version mismatch")
        if set(self.category_scope) != set(CATEGORIES) or len(self.category_scope) != len(CATEGORIES):
            raise ValueError("Unsupported category scope")
        return self


class Status(StrEnum):
    VALIDATED = "VALIDATED"
    PARTIAL = "PARTIAL"
    MIXED = "MIXED"
    UNKNOWN = "UNKNOWN"
    BLOCKED = "BLOCKED"
    RESEARCH_ONLY = "RESEARCH_ONLY"


class Quality(Contract):
    freshness_status: Status = Status.UNKNOWN
    query_completeness_status: Status = Status.UNKNOWN
    source_completeness_status: Status = Status.UNKNOWN
    real_world_completeness_status: Status = Status.UNKNOWN
    provenance_status: Status = Status.UNKNOWN
    eligibility_status: Status = Status.UNKNOWN
    temporal_status: Status = Status.UNKNOWN
    quality_status: Status = Status.BLOCKED
    normalized_score_status: Literal["BLOCKED"] = "BLOCKED"
    reasons: tuple[str, ...] = ()


class SourceReference(Contract):
    part_id: str
    artifact_reference: str | None
    artifact_checksum: str
    source_base_timestamp: datetime | None
    fetched_at: datetime | None


class Observation(Contract):
    osm_type: Literal["node", "way", "relation"]
    osm_id: StrictInt = Field(gt=0)
    name: str | None
    tags: dict[str, str | None]
    dataset_id: str
    scope_id: str
    snapshot_id: str
    source_references: tuple[SourceReference, ...]
    coordinate_representation: Literal["node_coordinate", "overpass_center", "missing"]
    longitude: float | None
    latitude: float | None
    category: str | None
    eligible: bool
    eligibility_policy_version: str = ELIGIBILITY_VERSION
    limitations: tuple[str, ...] = ()
    exclusions: tuple[str, ...] = ()

    @property
    def identity(self):
        return self.osm_type, self.osm_id


class BuildResult(Contract):
    canonical: dict
    canonical_checksum: str
    observations: tuple[Observation, ...]
    quality: Quality
    report: dict
