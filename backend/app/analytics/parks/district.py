"""Parallel internal component; never changes objective-current-v1 scoring."""
import statistics
from collections.abc import Sequence
from typing import Literal

from pydantic import Field, model_validator
from sqlalchemy.orm import Session

from app.analytics.parks.aggregation import summarize
from app.analytics.parks.models import EvidenceModel, PointParksAvailabilityEvidence, ParksAvailabilitySummary
from app.analytics.parks.normalization import PointNormalizer
from app.analytics.parks.reference import NORMALIZATION_VERSION, REFERENCE_ID, REFERENCE_SHA256, SAMPLING_VERSION
from app.analytics.parks.sampling import DistrictSampling, MINIMUM_VALID_SAMPLES, district_grid_250
from app.analytics.parks.service import ParksAvailabilityService


class DistrictParksAvailability(EvidenceModel):
    district_id: int
    normalization_version: Literal["parks-krasnoyarsk-relative-v1"] = NORMALIZATION_VERSION
    sampling_version: Literal["parks-district-territorial-grid250-v1"] = SAMPLING_VERSION
    reference_id: str = REFERENCE_ID
    reference_checksum: str = REFERENCE_SHA256
    availability: Literal["AVAILABLE", "UNAVAILABLE"]
    score: float | None = Field(default=None, ge=0, le=100, allow_inf_nan=False)
    unavailable_reason: str | None = None
    raw: ParksAvailabilitySummary | None = None
    limitations: tuple[str, ...]

    @model_validator(mode="after")
    def consistent(self):
        if self.availability == "AVAILABLE":
            if self.score is None or self.raw is None or self.unavailable_reason is not None:
                raise ValueError("Available component requires score and explanatory raw evidence")
        elif self.score is not None or not self.unavailable_reason:
            raise ValueError("Unavailable component requires null score and reason")
        return self


def aggregate_district(sampling: DistrictSampling, points: Sequence[PointParksAvailabilityEvidence], *,
                       normalizer: PointNormalizer) -> DistrictParksAvailability:
    """Equal mean of all selected point utilities; partial evidence never scores."""
    raw = None
    reason = normalizer.failure_reason or sampling.unavailable_reason
    if not reason and sampling.sampling_version != SAMPLING_VERSION:
        reason = "version_mismatch"
    if not reason:
        sample_coords = [s.coordinate for s in sampling.samples]
        # Coordinate association is explicit and order independent; duplicates cannot add weight.
        key = lambda c: (c.longitude, c.latitude)
        if (len(points) != len(sample_coords) or len(set(map(key, sample_coords))) != len(sample_coords) or
                set(map(key, sample_coords)) != {key(p.coordinate) for p in points}):
            reason = "sampling_contract_mismatch"
    if not reason:
        try:
            raw = summarize(points, sampling_version=SAMPLING_VERSION, radii_m=(500,1000,1500))
        except ValueError:
            reason = "inconsistent_evidence"
    normalized = ()
    if not reason:
        normalized = tuple(normalizer.normalize(p) for p in points)
        reason = next((p.unavailable_reason for p in normalized if p.availability != "AVAILABLE"), None)
        if reason is None and raw.valid_evidence_count < MINIMUM_VALID_SAMPLES:
            reason = "insufficient_samples"
    reference_limits = normalizer.reference.contract.limitations if normalizer.reference else (
        "krasnoyarsk_relative_frozen_reference_not_universal",)
    limitations = set(reference_limits) | (set(raw.limitations) if raw else set())
    for point in normalized:
        limitations.update(point.limitations)
    return DistrictParksAvailability(
        district_id=sampling.district_id, raw=raw, availability="UNAVAILABLE" if reason else "AVAILABLE",
        score=None if reason else statistics.mean(p.normalized_value for p in normalized),
        unavailable_reason=reason, limitations=tuple(sorted(limitations)),
    )


class DistrictParksAvailabilityService:
    def __init__(self, session: Session, *, scope_id: str):
        self.session = session
        self.scope_id = scope_id

    def districts(self, district_ids: Sequence[int]) -> tuple[DistrictParksAvailability, ...]:
        ids = tuple(sorted(set(district_ids)))
        if not ids or any(type(i) is not int or i <= 0 for i in ids):
            raise ValueError("Supply positive District IDs")
        normalizer = PointNormalizer()
        if normalizer.failure_reason or self.scope_id != "krasnoyarsk":
            reason = normalizer.failure_reason or "sampling_domain_unvalidated"
            return tuple(aggregate_district(DistrictSampling(i, unavailable_reason=reason), (),
                normalizer=normalizer) for i in ids)
        samplings = district_grid_250(self.session, ids, reference=normalizer.reference)
        selected = tuple(s for group in samplings if group.unavailable_reason is None for s in group.samples)
        # One canonical statement for all accepted districts; not one query per point.
        evidence = ParksAvailabilityService(self.session, scope_id=self.scope_id).points(
            tuple(s.coordinate for s in selected))
        results = []
        offset = 0
        for group in samplings:
            count = len(group.samples) if group.unavailable_reason is None else 0
            results.append(aggregate_district(group, evidence[offset:offset + count], normalizer=normalizer))
            offset += count
        return tuple(results)
