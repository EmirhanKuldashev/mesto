"""Thin point orchestration: no grid, district scores, refit or personal weights."""
import json
import math
from importlib import import_module

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.analytics.local.models import LIMITATIONS, LocalComponent, LocalRequest, LocalResult, NearestObject
from app.analytics.objective.components import COMPONENTS
from app.analytics.objective.engine import WEIGHTS
from app.analytics.objective.provider import PARITY_QUERY, read_precomputed
from app.analytics.school.models import source_ready
from app.analytics.stop_availability.models import Coordinate, SnapshotIdentity
from data.osm.contracts import Quality

COVERAGE_QUERY = text("""
WITH accepted AS (
 SELECT * FROM jsonb_to_recordset(CAST(:districts AS jsonb))
 AS r(slug text, geometry_ewkb_md5 text)
), checked AS MATERIALIZED (
 SELECT d.id,r.slug,COALESCE(d.geometry,d.boundary) AS polygon,
 COALESCE(d.source_id='osm' AND NOT d.is_synthetic AND
   ST_SRID(COALESCE(d.geometry,d.boundary))=4326 AND
   ST_GeometryType(COALESCE(d.geometry,d.boundary))='ST_MultiPolygon' AND
   ST_IsValid(COALESCE(d.geometry,d.boundary)) AND NOT ST_IsEmpty(COALESCE(d.geometry,d.boundary)) AND
   md5(ST_AsEWKB(COALESCE(d.geometry,d.boundary)))=r.geometry_ewkb_md5,false) AS valid
 FROM accepted r LEFT JOIN districts d ON d.slug=r.slug
), inputs AS (
 SELECT i.position,ST_SetSRID(ST_MakePoint(i.longitude,i.latitude),4326) AS point
 FROM jsonb_to_recordset(CAST(:points AS jsonb))
 AS i(position integer, longitude double precision, latitude double precision)
)
SELECT i.position,(SELECT bool_and(valid) AND count(*)=7 FROM checked) AS domain_valid,
 EXISTS(SELECT 1 FROM checked d WHERE ST_Covers(CASE WHEN d.valid THEN d.polygon END,i.point)) AS supported,
 (SELECT array_agg(id ORDER BY id) FROM checked WHERE valid) AS district_ids
FROM inputs i ORDER BY i.position
""")


def unavailable_component(key, reason):
    ref = import_module(f"app.analytics.{key}.reference")
    models = import_module(f"app.analytics.{key}.models")
    return LocalComponent(key=key, available=False, unavailable_reason=reason,
        normalization_version=ref.NORMALIZATION_VERSION, reference_id=ref.REFERENCE_ID,
        reference_checksum=ref.REFERENCE_SHA256, evidence_version=models.EVIDENCE_VERSION,
        eligibility_version=models.ELIGIBILITY_VERSION, distance_method=models.DISTANCE_METHOD)


def compose(location, components, *, provenance=None):
    """Fixed 20% of every required utility, with no intermediate rounding."""
    if set(components) - WEIGHTS.keys():
        raise ValueError("Only canonical Local components are accepted")
    components = {key:components[key] if key in components else unavailable_component(key, "component_missing") for key in WEIGHTS}
    missing = [key for key in WEIGHTS if not components[key].available]
    reason = "; ".join(f"{key}:{components[key].unavailable_reason}" for key in missing)
    return LocalResult(location=location, components=components,
        availability="UNAVAILABLE" if missing else "AVAILABLE",
        score=None if missing else math.fsum(WEIGHTS[key] * components[key].score for key in WEIGHTS),
        unavailable_reason=reason or None, provenance=provenance or {},
        limitations=tuple(sorted(set(LIMITATIONS).union(*(c.limitations for c in components.values())))))


class LocalAnalyticsService:
    def __init__(self, session: Session):
        self.session = session
        # Frozen bytes validated once per service/batch, never regenerated.
        self.contracts = {}
        for key, title in COMPONENTS.items():
            ref = import_module(f"app.analytics.{key}.reference")
            models = import_module(f"app.analytics.{key}.models")
            normalizer = import_module(f"app.analytics.{key}.normalization").PointNormalizer()
            service = getattr(import_module(f"app.analytics.{key}.service"), title + "AvailabilityService")
            self.contracts[key] = (ref, models, normalizer, service)

    def point(self, location: LocalRequest) -> LocalResult:
        return self.points((location,))[0]

    def _unavailable_component(self, key, reason):
        return unavailable_component(key, reason)

    def _unavailable(self, location, reason):
        result = compose(location, {key:self._unavailable_component(key, reason) for key in WEIGHTS})
        return result.model_copy(update={"unavailable_reason":reason})

    def _source_guard(self, ids, expected_snapshot):
        """Reuse the live active projection guard, without using district scores."""
        try:
            artifact = read_precomputed()
            rows = list(self.session.execute(PARITY_QUERY, {"district_ids":ids}).mappings())
            if len(rows) != 7:
                return "sampling_domain_unvalidated"
            for row in rows:
                if row["version"] is None:
                    return "dataset_unavailable"
                snapshot = SnapshotIdentity(dataset_key=row["dataset_key"],scope_id=row["scope_id"],
                    snapshot_version=row["version"],canonical_checksum=row["canonical_checksum"],
                    query_version=row["query_version"],query_hash=row["query_hash"],
                    foundation_eligibility_version=row["foundation_policy"])
                if not source_ready(snapshot, Quality.model_validate(row["quality"])):
                    return "version_quality_failure"
                if snapshot != expected_snapshot or snapshot.model_dump(mode="json") != artifact["snapshot"]:
                    return "snapshot_mismatch"
                if row["fingerprint"] != artifact["projection_fingerprint"]:
                    return "active_projection_mismatch"
            return None
        except (ValueError, KeyError, TypeError, OSError):
            return "provenance_invalid"

    def points(self, locations) -> tuple[LocalResult, ...]:
        """Internal batch also provides parity proof; public API accepts one point."""
        locations = tuple(LocalRequest.model_validate(p) for p in locations)
        if not locations:
            return ()
        refs = [n.reference for _, _, n, _ in self.contracts.values()]
        failure = next((n.failure_reason for _, _, n, _ in self.contracts.values() if n.failure_reason), None)
        if not failure:
            first = refs[0].contract
            # DistrictReference classes differ between components; compare immutable payloads.
            if any(r.contract.osm_snapshot != first.osm_snapshot or
                   [d.model_dump() for d in r.contract.districts] != [d.model_dump() for d in first.districts] for r in refs):
                failure = "reference_domain_mismatch"
        if failure:
            return tuple(self._unavailable(p, failure) for p in locations)
        first = refs[0].contract
        rows = list(self.session.execute(COVERAGE_QUERY, {
            "districts":json.dumps([d.model_dump() for d in first.districts]),
            "points":json.dumps([{"position":i,**p.model_dump()} for i,p in enumerate(locations)]),
        }).mappings())
        results = [None] * len(locations)
        supported = []
        for row in rows:
            i = row["position"]
            reason = "sampling_domain_unvalidated" if not row["domain_valid"] else (
                None if row["supported"] else "unsupported_geography")
            if reason:
                results[i] = self._unavailable(locations[i], reason)
            else:
                supported.append(i)
        if not supported:
            return tuple(results)
        failure = self._source_guard(rows[0]["district_ids"], first.osm_snapshot)
        if failure:
            for i in supported:
                results[i] = self._unavailable(locations[i], failure)
            return tuple(results)
        coordinates = tuple(Coordinate(**locations[i].model_dump()) for i in supported)
        components = {i:{} for i in supported}
        snapshots = {}
        for key, (ref, models, normalizer, service_type) in self.contracts.items():
            try:
                evidence = service_type(self.session, scope_id="krasnoyarsk").points(coordinates)
            except (ValueError, TypeError):
                evidence = ()
            if len(evidence) != len(coordinates):
                for i in supported:
                    components[i][key] = self._unavailable_component(key, "invalid_component_evidence")
                continue
            for i, coordinate, point in zip(supported, coordinates, evidence, strict=True):
                try:
                    normalized = normalizer.normalize(point)
                    reason = point.unavailable_reason or normalized.unavailable_reason
                    if point.coordinate != coordinate or point.snapshot != first.osm_snapshot:
                        reason = "snapshot_or_coordinate_mismatch"
                    elif (normalized.normalization_version != ref.NORMALIZATION_VERSION or
                          normalized.reference_id != ref.REFERENCE_ID or normalized.reference_checksum != ref.REFERENCE_SHA256 or
                          normalized.evidence_version != models.EVIDENCE_VERSION):
                        reason = "reference_or_version_mismatch"
                    if reason:
                        component = self._unavailable_component(key, reason)
                    else:
                        nearest = getattr(point, "nearest_" + ("stop" if key == "stop_availability" else key))
                        category = nearest.source_category if key == "healthcare" else ("bus_stop" if key == "stop_availability" else "park" if key == "parks" else key)
                        provenance = {"snapshot":point.snapshot.model_dump(mode="json")}
                        if key == "parks":
                            provenance["geometry_snapshot"] = point.geometry_snapshot.model_dump(mode="json")
                        component = LocalComponent(key=key, score=normalized.normalized_value,
                            distance_m=normalized.raw_distance_m, available=True,
                            normalization_version=normalized.normalization_version,
                            evidence_version=point.evidence_version, eligibility_version=point.eligibility_version,
                            reference_id=normalized.reference_id, reference_checksum=normalized.reference_checksum,
                            distance_method=point.distance_method, limitations=normalized.limitations,
                            nearest=NearestObject(osm_type=nearest.osm_type,osm_id=nearest.osm_id,name=nearest.name,
                                category=category,distance_m=nearest.distance_m,
                                coordinate_representation=getattr(nearest,"coordinate_representation",None)),
                            inside_geometry=nearest.inside_park_geometry if key == "parks" else None,
                            provenance=provenance)
                        snapshots[i] = point.snapshot.model_dump(mode="json")
                except (ValueError, TypeError, AttributeError):
                    component = self._unavailable_component(key, "invalid_component_evidence")
                components[i][key] = component
        for i in supported:
            results[i] = compose(locations[i], components[i], provenance={
                "snapshot":snapshots.get(i), "scope_id":"krasnoyarsk",
                "coverage_rule":"st_covers_validated_district_union_v1",
                "computation_path":"canonical_point_services_frozen_references",
            })
        return tuple(results)
