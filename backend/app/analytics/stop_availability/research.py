"""RESEARCH_ONLY administrative sampling; not the production district scoring basis."""
from collections import defaultdict
from collections.abc import Sequence
from typing import Literal

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.analytics.stop_availability.aggregation import summarize
from app.analytics.stop_availability.models import Coordinate, EvidenceModel, StopAvailabilitySummary
from app.analytics.stop_availability.service import StopAvailabilityService

SAMPLING_VERSION = "admin-grid-500-v1"
GRID_QUERY = text("""
WITH districts_selected AS (
    SELECT id, COALESCE(geometry,boundary) AS boundary
    FROM districts WHERE id=ANY(:district_ids)
), projected AS (
    SELECT *,ST_Envelope(ST_Transform(boundary,32646)) AS bounds FROM districts_selected
)
SELECT d.id AS district_id, d.boundary IS NOT NULL AS has_boundary,
       g.x, g.y, ST_X(g.location) AS longitude,ST_Y(g.location) AS latitude
FROM projected d LEFT JOIN LATERAL (
    SELECT x,y,location FROM (
        SELECT x,y,ST_Transform(ST_SetSRID(ST_MakePoint((x+0.5)*500,(y+0.5)*500),32646),4326) AS location
        FROM generate_series(floor(ST_XMin(d.bounds)/500)::int,ceil(ST_XMax(d.bounds)/500)::int) x
        CROSS JOIN generate_series(floor(ST_YMin(d.bounds)/500)::int,ceil(ST_YMax(d.bounds)/500)::int) y
    ) cells WHERE ST_Covers(d.boundary,location)
) g ON true ORDER BY d.id,g.x,g.y
""")


class ResearchSample(EvidenceModel):
    district_id: int
    cell_x: int
    cell_y: int
    coordinate: Coordinate


class ResearchDistrictSummary(EvidenceModel):
    purpose: Literal["RESEARCH_ONLY"] = "RESEARCH_ONLY"
    district_id: int
    summary: StopAvailabilitySummary


def administrative_grid_500(session: Session, district_ids: Sequence[int]) -> tuple[ResearchSample, ...]:
    """Global UTM46N centers; membership ST_Covers on the original WGS84 polygon."""
    ids = tuple(sorted(set(district_ids)))
    if not ids or any(type(i) is not int or i <= 0 for i in ids):
        raise ValueError("Supply positive district IDs for research sampling")
    rows = list(session.execute(GRID_QUERY, {"district_ids": list(ids)}).mappings())
    if {row["district_id"] for row in rows} != set(ids) or any(not row["has_boundary"] for row in rows):
        raise ValueError("Research district or boundary unavailable")
    return tuple(ResearchSample(district_id=row["district_id"], cell_x=row["x"], cell_y=row["y"],
        coordinate=Coordinate(longitude=row["longitude"],latitude=row["latitude"]))
        for row in rows if row["x"] is not None)


def district_research(session: Session, district_ids: Sequence[int], *, scope_id: str,
                      radii_m: Sequence[float] = (500, 1000)) -> tuple[ResearchDistrictSummary, ...]:
    samples = administrative_grid_500(session,district_ids)
    evidence = StopAvailabilityService(session,scope_id=scope_id).points(tuple(s.coordinate for s in samples))
    groups = defaultdict(list)
    for sample, point in zip(samples,evidence,strict=True):
        groups[sample.district_id].append(point)
    return tuple(ResearchDistrictSummary(district_id=ident,
        summary=summarize(groups[ident],sampling_version=SAMPLING_VERSION,radii_m=radii_m))
        for ident in sorted(set(district_ids)))
