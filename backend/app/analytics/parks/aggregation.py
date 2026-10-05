"""Raw Parks distribution; coverage denominator contains only valid evidence."""
import math
from collections import Counter
from collections.abc import Sequence

from app.analytics.parks.models import LIMITATIONS, CoveragePoint, PointParksAvailabilityEvidence, ParksAvailabilitySummary
from app.analytics.stop_availability.aggregation import _percentile_cont


def summarize(points: Sequence[PointParksAvailabilityEvidence], *, sampling_version: str,
              radii_m: Sequence[float] = (500,1000,1500)) -> ParksAvailabilitySummary:
    points = tuple(PointParksAvailabilityEvidence.model_validate(p) for p in points)
    if any(type(r) not in (int,float) or not math.isfinite(r) or r < 0 for r in radii_m):
        raise ValueError("Coverage radii must be finite nonnegative meters")
    if points and any((p.snapshot,p.source_quality,p.geometry_snapshot) != (points[0].snapshot,points[0].source_quality,points[0].geometry_snapshot) for p in points):
        raise ValueError("Cannot aggregate different source snapshots or quality states")
    distances = sorted(p.nearest_parks.distance_m for p in points if p.availability == "AVAILABLE")
    valid,missing = len(distances),len(points)-len(distances)
    curve = tuple(CoveragePoint(radius_m=radius,covered_count=sum(d <= radius for d in distances),
        valid_sample_count=valid,share=sum(d <= radius for d in distances)/valid if valid else None)
        for radius in sorted(set(radii_m)))
    return ParksAvailabilitySummary(
        sampling_version=sampling_version,snapshot=points[0].snapshot if points else None,
        source_quality=points[0].source_quality if points else None,
        geometry_snapshot=points[0].geometry_snapshot if points else None,
        sample_count=len(points),valid_evidence_count=valid,missing_evidence_count=missing,
        availability="UNAVAILABLE" if not valid else "PARTIAL" if missing else "AVAILABLE",
        missing_reasons=dict(sorted(Counter(p.unavailable_reason for p in points if p.unavailable_reason).items())),
        inside_park_count=sum(d == 0 for d in distances),
        share_inside_park_geometry=sum(d == 0 for d in distances)/valid if valid else None,
        median_m=_percentile_cont(distances,.5),p90_m=_percentile_cont(distances,.9),coverage_curve=curve,
        limitations=tuple(sorted(set(LIMITATIONS) | {s for p in points for s in p.limitations})),
    )
