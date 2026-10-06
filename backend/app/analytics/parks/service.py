"""Active baseline park identities and independently frozen geometry, one batch."""
import json
from collections.abc import Sequence
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.analytics.parks.models import (Coordinate, GeometrySnapshotIdentity, ParksObservation,
    PointParksAvailabilityEvidence, SnapshotIdentity, source_ready)
from data.osm.contracts import Quality
from data.osm.park_geometry import BASELINE_SHA256, BASELINE_VERSION, ROOT, GeometryError, read_geometry

BATCH_QUERY = text("""
WITH active AS MATERIALIZED (
 SELECT d.id AS dataset_id,
        CASE WHEN s.is_legacy THEN d.dataset_key ELSE s.canonical_json->>'dataset_id' END AS dataset_key,
        d.scope_id,s.id AS snapshot_id,
        s.version,s.canonical_checksum,s.query_version,s.query_hash,s.quality,
        s.canonical_json->'observations'->0->>'eligibility_policy_version' AS foundation_policy
 FROM osm_datasets d JOIN osm_snapshots s ON s.id=d.active_snapshot_id AND s.dataset_id=d.id
 JOIN data_sources source ON source.source_id=d.source_id
 WHERE d.source_id='osm' AND NOT source.is_synthetic AND d.scope_id=:scope_id
   AND s.status='ACTIVE' AND NOT s.is_legacy
), shapes AS MATERIALIZED (
 SELECT f.osm_type,f.osm_id,ST_SetSRID(ST_GeomFromGeoJSON(
   CASE WHEN f.osm_type='node' THEN f.point_location ELSE f.area_geometry END),4326) AS geom
 FROM jsonb_to_recordset(CAST(:features AS jsonb))
   AS f(osm_type text,osm_id bigint,point_location jsonb,area_geometry jsonb)
), valid_shapes AS MATERIALIZED (
 SELECT *,geom::geography AS location,
   CASE osm_type WHEN 'node' THEN 'node_coordinate' WHEN 'way' THEN 'osm_polygon'
                 ELSE 'osm_multipolygon' END AS coordinate_representation
 FROM shapes WHERE geom IS NOT NULL AND ST_IsValid(geom) AND NOT ST_IsEmpty(geom)
   AND ST_SRID(geom)=4326 AND ST_GeometryType(geom)=CASE osm_type
     WHEN 'node' THEN 'ST_Point' WHEN 'way' THEN 'ST_Polygon' ELSE 'ST_MultiPolygon' END
), eligible AS MATERIALIZED (
 SELECT b.osm_type,b.osm_id,p.name,g.location,g.coordinate_representation
 FROM active a JOIN osm_active_pois b ON b.dataset_id=a.dataset_id AND b.snapshot_id=a.snapshot_id
 JOIN pois p ON p.id=b.poi_id
 JOIN osm_snapshot_observations o ON o.snapshot_id=b.snapshot_id AND o.osm_type=b.osm_type AND o.osm_id=b.osm_id
 JOIN valid_shapes g ON g.osm_type=b.osm_type AND g.osm_id=b.osm_id
 WHERE a.version=:baseline_version AND a.canonical_checksum=:baseline_checksum
   AND p.source_id='osm' AND NOT p.is_synthetic AND o.eligible
   AND p.category='park' AND o.observation->>'category'='park'
   AND o.observation->'tags'->>'leisure'='park'
   AND o.observation->>'eligibility_policy_version'='osm-poi-eligibility-v1'
   AND o.observation->>'coordinate_representation'=CASE WHEN b.osm_type='node'
       THEN 'node_coordinate' ELSE 'overpass_center' END
), inputs AS (
 SELECT i.*,CASE WHEN i.valid THEN ST_SetSRID(ST_MakePoint(i.longitude,i.latitude),4326)::geography END AS location
 FROM jsonb_to_recordset(CAST(:points AS jsonb))
   AS i(position integer,longitude double precision,latitude double precision,valid boolean)
)
SELECT i.position,a.dataset_key,a.scope_id,a.version,a.canonical_checksum,
       a.query_version,a.query_hash,a.foundation_policy,a.quality,
       (SELECT count(*) FROM shapes)=(SELECT count(*) FROM valid_shapes) AS geometry_valid,
       CASE WHEN a.snapshot_id IS NOT NULL THEN (SELECT count(*) FROM eligible) END AS eligible_count,
       n.observation
FROM inputs i LEFT JOIN active a ON true
LEFT JOIN LATERAL (
 SELECT to_jsonb(r) AS observation FROM (
   SELECT e.osm_type,e.osm_id,e.name,e.coordinate_representation,
          CASE WHEN e.osm_type='node' THEN false ELSE ST_Covers(e.location,i.location) END AS inside_park_geometry,
          ST_Distance(i.location,e.location,true) AS distance_m
   FROM eligible e WHERE i.valid
   ORDER BY distance_m,e.osm_type COLLATE "C",e.osm_id LIMIT 1
 ) r
) n ON true ORDER BY i.position
""")

class ParksAvailabilityService:
    def __init__(self, session: Session, *, scope_id: str, geometry_root=ROOT):
        if not scope_id:
            raise ValueError("An explicit OSM dataset scope is required")
        self.session, self.scope_id = session, scope_id
        self.geometry, self.geometry_error = None, None
        try:
            self.geometry = read_geometry(geometry_root)
        except GeometryError:
            self.geometry_error = "geometry_unavailable"

    def point(self, coordinate: Coordinate) -> PointParksAvailabilityEvidence:
        return self.points((coordinate,))[0]

    def points(self, coordinates: Sequence[Coordinate]) -> tuple[PointParksAvailabilityEvidence, ...]:
        coordinates = tuple(Coordinate.model_validate(p) for p in coordinates)
        if not coordinates:
            return ()
        if self.geometry_error:
            return tuple(PointParksAvailabilityEvidence(coordinate=p,snapshot=None,source_quality=None,
                geometry_snapshot=None,eligible_parks_count=None,availability="UNAVAILABLE",
                unavailable_reason="invalid_coordinate" if not p.valid else self.geometry_error,nearest_parks=None)
                for p in coordinates)
        geometry_identity = GeometrySnapshotIdentity()
        rows = self.session.execute(BATCH_QUERY, {
            "scope_id": self.scope_id, "features": json.dumps(self.geometry.features, allow_nan=False),
            "baseline_version": BASELINE_VERSION, "baseline_checksum": BASELINE_SHA256,
            "points": json.dumps([{"position":i,"longitude":p.longitude,"latitude":p.latitude,"valid":p.valid}
                                   for i,p in enumerate(coordinates)], allow_nan=False),
        }).mappings()
        results = []
        for row in rows:
            p = coordinates[row["position"]]
            snapshot = None if row["version"] is None else SnapshotIdentity(
                dataset_key=row["dataset_key"],scope_id=row["scope_id"],snapshot_version=row["version"],
                canonical_checksum=row["canonical_checksum"],query_version=row["query_version"],
                query_hash=row["query_hash"],foundation_eligibility_version=row["foundation_policy"])
            try:
                quality = Quality.model_validate(row["quality"]) if snapshot else None
            except ValidationError:
                quality = None
            reason = ("invalid_coordinate" if not p.valid else "dataset_unavailable" if snapshot is None else
                "version_quality_failure" if not source_ready(snapshot,quality) else
                "geometry_baseline_mismatch" if (snapshot.snapshot_version,snapshot.canonical_checksum) != (BASELINE_VERSION,BASELINE_SHA256) else
                "geometry_invalid" if not row["geometry_valid"] else
                "no_eligible_observations" if not row["observation"] else None)
            results.append(PointParksAvailabilityEvidence(coordinate=p,snapshot=snapshot,source_quality=quality,
                geometry_snapshot=geometry_identity,eligible_parks_count=row["eligible_count"],
                availability="UNAVAILABLE" if reason else "AVAILABLE",unavailable_reason=reason,
                nearest_parks=None if reason else ParksObservation.model_validate(row["observation"])))
        return tuple(results)
