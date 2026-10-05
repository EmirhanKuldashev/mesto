"""Exact active School search: one MVCC SQL statement per coordinate batch."""
import json
from collections.abc import Sequence

from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.analytics.school.models import (
    Coordinate, PointSchoolAvailabilityEvidence, SchoolObservation, SchoolPointDiagnostics,
    SnapshotIdentity, source_ready,
)
from data.osm.contracts import Quality

# Same validated PostGIS spheroid semantics and batch pattern as Stop Availability.
# Materialize active membership once, never query unbound POIs or historical rows.
BATCH_QUERY = text("""
WITH active AS MATERIALIZED (
    SELECT d.id AS dataset_id,d.dataset_key,d.scope_id,s.id AS snapshot_id,
           s.version,s.canonical_checksum,s.query_version,s.query_hash,s.quality,
           s.canonical_json->'observations'->0->>'eligibility_policy_version' AS foundation_policy
    FROM osm_datasets d JOIN osm_snapshots s
      ON s.id=d.active_snapshot_id AND s.dataset_id=d.id
    WHERE d.source_id='osm' AND d.scope_id=:scope_id AND s.status='ACTIVE'
), eligible AS MATERIALIZED (
    SELECT b.osm_type,b.osm_id,p.name,p.location::geography AS location,
           o.observation->>'coordinate_representation' AS coordinate_representation
    FROM active a JOIN osm_active_pois b
      ON b.dataset_id=a.dataset_id AND b.snapshot_id=a.snapshot_id
    JOIN pois p ON p.id=b.poi_id
    JOIN osm_snapshot_observations o
      ON o.snapshot_id=b.snapshot_id AND o.osm_type=b.osm_type AND o.osm_id=b.osm_id
    WHERE p.source_id='osm' AND NOT p.is_synthetic AND o.eligible
      AND p.category='school' AND o.observation->>'category'='school'
      AND o.observation->'tags'->>'amenity'='school'
      AND o.observation->>'eligibility_policy_version'='osm-poi-eligibility-v1'
      AND o.observation->>'coordinate_representation'=CASE WHEN b.osm_type='node'
          THEN 'node_coordinate' ELSE 'overpass_center' END
      AND p.location IS NOT NULL AND ST_SRID(p.location)=4326 AND NOT ST_IsEmpty(p.location)
      AND ST_X(p.location) BETWEEN -180 AND 180 AND ST_Y(p.location) BETWEEN -90 AND 90
), inputs AS (
    SELECT i.*,CASE WHEN i.valid THEN
      ST_SetSRID(ST_MakePoint(i.longitude,i.latitude),4326)::geography END AS location
    FROM jsonb_to_recordset(CAST(:points AS jsonb))
      AS i(position integer,longitude double precision,latitude double precision,valid boolean)
)
SELECT i.position,a.dataset_key,a.scope_id,a.version,a.canonical_checksum,
       a.query_version,a.query_hash,a.foundation_policy,a.quality,
       CASE WHEN a.snapshot_id IS NOT NULL THEN (SELECT count(*) FROM eligible) END AS eligible_count,
       n.observations
FROM inputs i LEFT JOIN active a ON true
LEFT JOIN LATERAL (
    SELECT jsonb_agg(to_jsonb(r) ORDER BY r.distance_m,r.osm_type COLLATE "C",r.osm_id) AS observations
    FROM (
        SELECT e.osm_type,e.osm_id,e.name,e.coordinate_representation,
               ST_Distance(i.location,e.location,true) AS distance_m
        FROM eligible e WHERE i.valid
        ORDER BY distance_m,e.osm_type COLLATE "C",e.osm_id LIMIT :nearest_count
    ) r
) n ON true ORDER BY i.position
""")


class SchoolAvailabilityService:
    """Explicit dataset scope; district ownership never restricts school search."""

    def __init__(self, session: Session, *, scope_id: str):
        if not scope_id:
            raise ValueError("An explicit OSM dataset scope is required")
        self.session, self.scope_id = session, scope_id

    def point(self, coordinate: Coordinate) -> PointSchoolAvailabilityEvidence:
        return self.points((coordinate,))[0]

    def points(self, coordinates: Sequence[Coordinate]) -> tuple[PointSchoolAvailabilityEvidence, ...]:
        return tuple(evidence for evidence, _ in self._evaluate(coordinates,nearest_count=1))

    def diagnostics(self, coordinates: Sequence[Coordinate]) -> tuple[SchoolPointDiagnostics, ...]:
        """d1/d2/d3 are observation distances, not independent institutions or capacity."""
        return tuple(SchoolPointDiagnostics(evidence=evidence,nearest_observations=nearest)
                     for evidence,nearest in self._evaluate(coordinates,nearest_count=3))

    def _evaluate(self, coordinates, *, nearest_count):
        coordinates = tuple(Coordinate.model_validate(p) for p in coordinates)
        if not coordinates:
            return ()
        payload = [{"position":i,"longitude":p.longitude,"latitude":p.latitude,"valid":p.valid}
                   for i,p in enumerate(coordinates)]
        rows = self.session.execute(BATCH_QUERY,{
            "scope_id":self.scope_id,"points":json.dumps(payload,allow_nan=False),"nearest_count":nearest_count,
        }).mappings()
        results = []
        for row in rows:
            coordinate = coordinates[row["position"]]
            snapshot = None if row["version"] is None else SnapshotIdentity(
                dataset_key=row["dataset_key"],scope_id=row["scope_id"],snapshot_version=row["version"],
                canonical_checksum=row["canonical_checksum"],query_version=row["query_version"],
                query_hash=row["query_hash"],foundation_eligibility_version=row["foundation_policy"],
            )
            try:
                quality = Quality.model_validate(row["quality"]) if snapshot else None
            except ValidationError:
                quality = None
            reason = ("invalid_coordinate" if not coordinate.valid else
                      "dataset_unavailable" if snapshot is None else
                      "version_quality_failure" if not source_ready(snapshot,quality) else
                      "no_eligible_observations" if not row["observations"] else None)
            nearest = () if reason else tuple(SchoolObservation.model_validate(p) for p in row["observations"])
            evidence = PointSchoolAvailabilityEvidence(
                coordinate=coordinate,snapshot=snapshot,source_quality=quality,
                eligible_school_count=row["eligible_count"],availability="UNAVAILABLE" if reason else "AVAILABLE",
                unavailable_reason=reason,nearest_school=nearest[0] if nearest else None,
            )
            results.append((evidence,nearest))
        return tuple(results)
