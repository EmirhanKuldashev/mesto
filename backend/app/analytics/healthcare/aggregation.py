"""Raw Healthcare distribution; coverage denominator contains only valid evidence."""
import math
from collections import Counter
from collections.abc import Sequence

from app.analytics.healthcare.models import LIMITATIONS, CoveragePoint, PointHealthcareAvailabilityEvidence, HealthcareAvailabilitySummary
from app.analytics.stop_availability.aggregation import _percentile_cont


def summarize(points: Sequence[PointHealthcareAvailabilityEvidence], *, sampling_version: str,
              radii_m: Sequence[float] = (500,1000,1500)) -> HealthcareAvailabilitySummary:
    points = tuple(PointHealthcareAvailabilityEvidence.model_validate(p) for p in points)
    if any(type(r) not in (int,float) or not math.isfinite(r) or r < 0 for r in radii_m):
        raise ValueError("Coverage radii must be finite nonnegative meters")
    if points and any((p.snapshot,p.source_quality) != (points[0].snapshot,points[0].source_quality) for p in points):
        raise ValueError("Cannot aggregate different source snapshots or quality states")
    distances = sorted(p.nearest_healthcare.distance_m for p in points if p.availability == "AVAILABLE")
    valid,missing = len(distances),len(points)-len(distances)
    curve = tuple(CoveragePoint(radius_m=radius,covered_count=sum(d <= radius for d in distances),
        valid_sample_count=valid,share=sum(d <= radius for d in distances)/valid if valid else None)
        for radius in sorted(set(radii_m)))
    return HealthcareAvailabilitySummary(
        sampling_version=sampling_version,snapshot=points[0].snapshot if points else None,
        source_quality=points[0].source_quality if points else None,
        sample_count=len(points),valid_evidence_count=valid,missing_evidence_count=missing,
        availability="UNAVAILABLE" if not valid else "PARTIAL" if missing else "AVAILABLE",
        missing_reasons=dict(sorted(Counter(p.unavailable_reason for p in points if p.unavailable_reason).items())),
        nearest_category_counts={category:sum(p.availability == "AVAILABLE" and
            p.nearest_healthcare.source_category == category for p in points)
            for category in ("clinic", "hospital")},
        median_m=_percentile_cont(distances,.5),p90_m=_percentile_cont(distances,.9),coverage_curve=curve,
        limitations=tuple(sorted(set(LIMITATIONS) | {s for p in points for s in p.limitations})),
    )
