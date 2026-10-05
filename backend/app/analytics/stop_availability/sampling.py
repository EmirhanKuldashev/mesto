"""Approved District territorial grid; separate from coordinate normalization."""
import json
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.analytics.stop_availability.models import Coordinate
from app.analytics.stop_availability.reference import LoadedReference, SAMPLING_VERSION

MINIMUM_VALID_SAMPLES = 180  # Lower edge of validated District domain, not a population law.

GRID_250_QUERY = text("""
WITH accepted AS (
    SELECT * FROM jsonb_to_recordset(CAST(:district_reference AS jsonb))
      AS r(slug text, geometry_ewkb_md5 text, sample_count integer)
), selected AS (
    SELECT d.id, d.slug, COALESCE(d.geometry,d.boundary) AS polygon,
           d.source_id='osm' AND NOT d.is_synthetic AS real_osm,
           r.geometry_ewkb_md5 AS expected_geometry, r.sample_count AS expected_count
    FROM districts d LEFT JOIN accepted r ON r.slug=d.slug WHERE d.id=ANY(:district_ids)
), checked AS MATERIALIZED (
    SELECT *, polygon IS NOT NULL AND NOT ST_IsEmpty(polygon) AND
      ST_SRID(polygon)=4326 AND ST_GeometryType(polygon)='ST_MultiPolygon' AND
      ST_IsValid(polygon) AS geometry_valid,
      real_osm AND md5(ST_AsEWKB(polygon))=expected_geometry AS domain_valid
    FROM selected
), projected AS MATERIALIZED (
    SELECT *, CASE WHEN geometry_valid AND domain_valid THEN
      ST_Envelope(ST_Transform(polygon,32646)) END AS bounds FROM checked
)
SELECT d.id, d.slug, d.geometry_valid, d.domain_valid, d.expected_count,
       g.x, g.y, ST_X(g.location) AS longitude, ST_Y(g.location) AS latitude
FROM projected d LEFT JOIN LATERAL (
    SELECT x,y,location FROM (
        SELECT x,y,ST_Transform(ST_SetSRID(ST_MakePoint(250*x+125,250*y+125),32646),4326) AS location
        FROM generate_series(floor(ST_XMin(d.bounds)/250)::int,ceil(ST_XMax(d.bounds)/250)::int) x
        CROSS JOIN generate_series(floor(ST_YMin(d.bounds)/250)::int,ceil(ST_YMax(d.bounds)/250)::int) y
    ) cells WHERE ST_Covers(d.polygon,location)
) g ON true ORDER BY d.id,g.x,g.y
""")


@dataclass(frozen=True)
class TerritorialSample:
    cell_x: int
    cell_y: int
    coordinate: Coordinate


@dataclass(frozen=True)
class DistrictSampling:
    district_id: int
    samples: tuple[TerritorialSample, ...] = ()
    sampling_version: str = SAMPLING_VERSION
    unavailable_reason: str | None = None


def district_grid_250(session: Session, district_ids: Sequence[int], *,
                      reference: LoadedReference) -> tuple[DistrictSampling, ...]:
    """One SQL query, fixed centers, original polygon ST_Covers; no POI lookup."""
    ids = tuple(sorted(set(district_ids)))
    if not ids or any(type(i) is not int or i <= 0 for i in ids):
        raise ValueError("Supply positive District IDs")
    payload = [d.model_dump() for d in reference.contract.districts]
    groups = {}
    for row in session.execute(GRID_250_QUERY, {
            "district_ids": list(ids), "district_reference": json.dumps(payload)}).mappings():
        groups.setdefault(row["id"], []).append(row)
    results = []
    for ident in ids:
        rows = groups.get(ident, [])
        reason = None
        if not rows or not rows[0]["geometry_valid"]:
            reason = "sampling_unavailable"
        elif not rows[0]["domain_valid"]:
            reason = "sampling_domain_unvalidated"
        samples = tuple(TerritorialSample(row["x"], row["y"],
            Coordinate(longitude=row["longitude"], latitude=row["latitude"]))
            for row in rows if row["x"] is not None) if reason is None else ()
        if reason is None and len(samples) < MINIMUM_VALID_SAMPLES:
            reason = "insufficient_samples"
        elif reason is None and len(samples) != rows[0]["expected_count"]:
            reason = "sampling_contract_mismatch"
        results.append(DistrictSampling(ident, samples, unavailable_reason=reason))
    return tuple(results)
