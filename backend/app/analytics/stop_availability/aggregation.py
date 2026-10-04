"""Order-independent raw summaries; missing evidence never means uncovered."""
import math
from collections import Counter
from collections.abc import Sequence

from app.analytics.stop_availability.models import (
    LIMITATIONS, CoveragePoint, PointStopAvailabilityEvidence, StopAvailabilitySummary,
)


def _percentile_cont(sorted_values: list[float], quantile: float) -> float | None:
    """Linear interpolation at (N-1)*q, equivalent to PostgreSQL percentile_cont."""
    if not sorted_values:
        return None
    position = (len(sorted_values) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    return sorted_values[lower] + (sorted_values[upper] - sorted_values[lower]) * (position - lower)


def summarize(points: Sequence[PointStopAvailabilityEvidence], *, sampling_version: str,
              radii_m: Sequence[float] = (500, 1000)) -> StopAvailabilitySummary:
    """Each supplied sample has equal weight, including explicitly repeated coordinates."""
    points = tuple(points)
    if any(type(r) not in (int, float) or not math.isfinite(r) or r < 0 for r in radii_m):
        raise ValueError("Coverage radii must be finite nonnegative meters")
    radii = tuple(sorted(set(radii_m)))
    if points and any((p.snapshot, p.source_quality) != (points[0].snapshot, points[0].source_quality)
                      for p in points):
        raise ValueError("Cannot aggregate different source snapshots or quality states")
    distances = sorted(p.nearest_stop.distance_m for p in points if p.availability == "AVAILABLE")
    valid = len(distances)
    missing = len(points) - valid
    curve = tuple(CoveragePoint(radius_m=radius,
        covered_count=sum(distance <= radius for distance in distances), valid_sample_count=valid,
        share=sum(distance <= radius for distance in distances) / valid if valid else None)
        for radius in radii)
    return StopAvailabilitySummary(
        sampling_version=sampling_version, snapshot=points[0].snapshot if points else None,
        source_quality=points[0].source_quality if points else None,
        sample_count=len(points), valid_evidence_count=valid, missing_evidence_count=missing,
        availability="UNAVAILABLE" if not valid else "PARTIAL" if missing else "AVAILABLE",
        missing_reasons=dict(sorted(Counter(p.unavailable_reason for p in points if p.unavailable_reason).items())),
        median_m=_percentile_cont(distances, .5), p90_m=_percentile_cont(distances, .9),
        coverage_curve=curve, limitations=tuple(sorted(set(LIMITATIONS) | {s for p in points for s in p.limitations})),
    )
