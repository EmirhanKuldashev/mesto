"""One SQL statement per batch; exact spheroidal distance across the active scope."""
import json
from collections.abc import Sequence

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.analytics.stop_availability.models import (
    Coordinate, NearestStop, PointStopAvailabilityEvidence, SnapshotIdentity,
)
from data.osm.contracts import Quality

# The pointer, source identity and all point results share one MVCC statement
# snapshot. Materialize the eligible set once; no approximate KNN preselection.
BATCH_QUERY = text("""
WITH active AS MATERIALIZED (
    SELECT d.id AS dataset_id,
           CASE WHEN s.is_legacy THEN d.dataset_key ELSE s.canonical_json->>'dataset_id' END AS dataset_key,
           d.scope_id, s.id AS snapshot_id,
           s.version, s.canonical_checksum, s.query_version, s.query_hash, s.quality,
           s.canonical_json->'observations'->0->>'eligibility_policy_version' AS foundation_policy
    FROM osm_datasets d JOIN osm_snapshots s
      ON s.id=d.active_snapshot_id AND s.dataset_id=d.id
    WHERE d.source_id='osm' AND d.scope_id=:scope_id AND s.status='ACTIVE'
), eligible AS MATERIALIZED (
    SELECT b.osm_type, b.osm_id, p.name, p.location::geography AS location
    FROM active a JOIN osm_active_pois b
      ON b.dataset_id=a.dataset_id AND b.snapshot_id=a.snapshot_id
    JOIN pois p ON p.id=b.poi_id
    JOIN osm_snapshot_observations o
      ON o.snapshot_id=b.snapshot_id AND o.osm_type=b.osm_type AND o.osm_id=b.osm_id
    WHERE p.source_id='osm' AND p.is_synthetic=false AND o.eligible=true
      AND o.observation->'tags'->>'highway'='bus_stop'
      AND p.location IS NOT NULL AND ST_SRID(p.location)=4326
      AND NOT ST_IsEmpty(p.location)
), inputs AS (
    SELECT i.*, CASE WHEN i.valid THEN
      ST_SetSRID(ST_MakePoint(i.longitude,i.latitude),4326)::geography END AS location
    FROM jsonb_to_recordset(CAST(:points AS jsonb))
      AS i(position integer, longitude double precision, latitude double precision, valid boolean)
)
SELECT i.position, a.dataset_key, a.scope_id, a.version, a.canonical_checksum,
       a.query_version, a.query_hash, a.foundation_policy, a.quality,
       CASE WHEN a.snapshot_id IS NOT NULL THEN (SELECT count(*) FROM eligible) END AS eligible_count,
       n.osm_type, n.osm_id, n.name, n.distance_m
FROM inputs i LEFT JOIN active a ON true
LEFT JOIN LATERAL (
    SELECT e.osm_type,e.osm_id,e.name,
           ST_Distance(i.location,e.location,true) AS distance_m
    FROM eligible e WHERE i.valid
    ORDER BY distance_m,e.osm_type COLLATE "C",e.osm_id LIMIT 1
) n ON true
ORDER BY i.position
""")


class StopAvailabilityService:
    """Scope selects a source dataset; it never restricts stops by district ownership."""

    def __init__(self, session: Session, *, scope_id: str):
        if not scope_id:
            raise ValueError("An explicit OSM dataset scope is required")
        self.session = session
        self.scope_id = scope_id

    def point(self, coordinate: Coordinate) -> PointStopAvailabilityEvidence:
        return self.points((coordinate,))[0]

    def points(self, coordinates: Sequence[Coordinate]) -> tuple[PointStopAvailabilityEvidence, ...]:
        coordinates = tuple(Coordinate.model_validate(point) for point in coordinates)
        if not coordinates:
            return ()
        payload = [{"position": i, "longitude": p.longitude, "latitude": p.latitude, "valid": p.valid}
                   for i, p in enumerate(coordinates)]
        rows = self.session.execute(BATCH_QUERY, {
            "scope_id": self.scope_id, "points": json.dumps(payload, allow_nan=False),
        }).mappings()
        results = []
        for row in rows:
            coordinate = coordinates[row["position"]]
            snapshot = None if row["version"] is None else SnapshotIdentity(
                dataset_key=row["dataset_key"], scope_id=row["scope_id"], snapshot_version=row["version"],
                canonical_checksum=row["canonical_checksum"], query_version=row["query_version"],
                query_hash=row["query_hash"], foundation_eligibility_version=row["foundation_policy"],
            )
            reason = ("invalid_coordinate" if not coordinate.valid else
                      "dataset_unavailable" if snapshot is None else
                      "no_eligible_observations" if row["osm_id"] is None else None)
            nearest = None if reason else NearestStop(
                osm_type=row["osm_type"], osm_id=row["osm_id"], name=row["name"], distance_m=row["distance_m"],
            )
            results.append(PointStopAvailabilityEvidence(
                coordinate=coordinate, snapshot=snapshot,
                source_quality=Quality.model_validate(row["quality"]) if snapshot else None,
                eligible_stop_count=row["eligible_count"], nearest_stop=nearest,
                availability="UNAVAILABLE" if reason else "AVAILABLE", unavailable_reason=reason,
            ))
        return tuple(results)
