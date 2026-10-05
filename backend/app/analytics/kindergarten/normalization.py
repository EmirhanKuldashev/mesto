"""Point-first relative normalization; no session, ORM, POI query or sampling."""
import bisect
import math
from typing import Literal

from pydantic import Field, model_validator

from app.analytics.kindergarten.models import (
    DISTANCE_METHOD, ELIGIBILITY_VERSION, EVIDENCE_VERSION, EvidenceModel,
    PointKindergartenAvailabilityEvidence,
    source_ready,
)
from app.analytics.kindergarten.reference import (
    NORMALIZATION_VERSION, REFERENCE_ID, REFERENCE_PATH, REFERENCE_SHA256,
    ReferenceError, read_reference,
)


class NormalizedPoint(EvidenceModel):
    normalization_version: Literal["kindergarten-krasnoyarsk-relative-v1"] = NORMALIZATION_VERSION
    evidence_version: Literal["kindergarten-evidence-v1"] = EVIDENCE_VERSION
    reference_id: str = REFERENCE_ID
    reference_checksum: str = REFERENCE_SHA256
    raw_distance_m: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    normalized_value: float | None = Field(default=None, ge=0, le=100, allow_inf_nan=False)
    availability: Literal["AVAILABLE", "UNAVAILABLE"]
    quality_state: Literal["VALIDATED", "UNAVAILABLE"]
    unavailable_reason: str | None = None
    limitations: tuple[str, ...]

    @model_validator(mode="after")
    def consistent(self):
        if self.availability == "AVAILABLE":
            if (self.normalized_value is None or self.raw_distance_m is None or
                    self.unavailable_reason is not None or self.quality_state != "VALIDATED"):
                raise ValueError("Available normalized point requires validated evidence and value")
        elif self.normalized_value is not None or not self.unavailable_reason or self.quality_state != "UNAVAILABLE":
            raise ValueError("Unavailable normalized point requires null value and reason")
        return self


def evidence_failure(point: PointKindergartenAvailabilityEvidence) -> str | None:
    if (point.evidence_version != EVIDENCE_VERSION or point.eligibility_version != ELIGIBILITY_VERSION or
            point.distance_method != DISTANCE_METHOD or
            point.snapshot is not None and point.snapshot.foundation_eligibility_version != "osm-poi-eligibility-v1"):
        return "version_mismatch"
    if point.availability != "AVAILABLE":
        return "dataset_unavailable" if point.unavailable_reason == "dataset_unavailable" else "point_evidence_missing"
    if point.snapshot is None:
        return "dataset_unavailable"
    if point.snapshot.scope_id != "krasnoyarsk" or point.snapshot.dataset_key != "osm-poi":
        return "normalization_scope_unvalidated"
    if point.nearest_kindergarten is None or not point.coordinate.valid:
        return "point_evidence_missing"
    quality = point.source_quality
    if not source_ready(point.snapshot, quality):
        return "quality_unavailable"
    return None


class PointNormalizer:
    """One frozen reference read per instance; scoring itself is pure and reusable."""

    def __init__(self, *, reference_path=REFERENCE_PATH):
        self.reference = None
        self.failure_reason = None
        try:
            self.reference = read_reference(reference_path)
        except ReferenceError as exc:
            self.failure_reason = exc.reason

    def distance_value(self, distance_m: float) -> float:
        """Exact research midrank CDF, without interpolation or rounding."""
        if self.reference is None:
            raise ReferenceError(self.failure_reason)
        if type(distance_m) not in (int, float) or not math.isfinite(distance_m) or distance_m < 0:
            raise ValueError("Distance must be finite nonnegative meters")
        values = self.reference.contract.distances_m
        below = bisect.bisect_left(values, distance_m)
        at_or_below = bisect.bisect_right(values, distance_m)
        return 100 * (1 - (below + at_or_below) / (2 * len(values)))

    def normalize(self, point: PointKindergartenAvailabilityEvidence) -> NormalizedPoint:
        reason = self.failure_reason or evidence_failure(point)
        distance = point.nearest_kindergarten.distance_m if point.nearest_kindergarten else None
        extra = self.reference.contract.limitations if self.reference else (
            "krasnoyarsk_relative_frozen_reference_not_universal",)
        # The foundation's generic normalization status remains untouched. It is
        # not the readiness status of this separately reviewed component.
        quality_limits = tuple(r for r in point.source_quality.reasons if r != "normalization_not_implemented") if point.source_quality else ()
        return NormalizedPoint(
            raw_distance_m=distance, normalized_value=None if reason else self.distance_value(distance),
            availability="UNAVAILABLE" if reason else "AVAILABLE",
            quality_state="UNAVAILABLE" if reason else "VALIDATED", unavailable_reason=reason,
            limitations=tuple(sorted(set(point.limitations) | set(extra) | set(quality_limits))),
        )
