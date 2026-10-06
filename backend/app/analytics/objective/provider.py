"""Small precomputed canonical snapshot, with live source and geometry parity gates.

This adapter validates provenance only; spatial scoring stays in the canonical
component services used by the offline builder. Never computes on a user request.
"""
import hashlib
import json
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.analytics.objective.components import contracts
from app.analytics.objective.engine import ComponentScore, aggregate
from app.analytics.school.models import source_ready
from app.analytics.stop_availability.models import SnapshotIdentity
from data.osm.contracts import Quality
from data.osm.park_geometry import read_geometry

ARTIFACT_PATH = Path(__file__).resolve().parents[3] / "data/fixtures/analytics/objective-mesto-v2.json"
ARTIFACT_SHA256 = "80d5d166aceef8f6a9c2e6dc84d30e32549fe2e91f1f9f2dec764630c13859c6"

# Same active bindings consumed by components. Detect edits/deletions/synthetic
# substitutions, even if someone bypasses the immutable snapshot lifecycle.
# IDs and district assignment do not affect city-wide nearest-object components.
# The container label can be legacy-poi after an upgrade. Fresh provenance uses
# the sealed active payload's dataset_id; migration-adopted legacy keeps its label.
PARITY_QUERY = text("""
WITH active AS MATERIALIZED (
 SELECT d.id dataset_id, s.id snapshot_id,
 CASE WHEN s.is_legacy THEN d.dataset_key ELSE s.canonical_json->>'dataset_id' END dataset_key,
 d.scope_id, s.version,
 s.canonical_checksum, s.query_version, s.query_hash, s.quality,
 s.canonical_json->'observations'->0->>'eligibility_policy_version' foundation_policy
 FROM osm_datasets d JOIN osm_snapshots s ON s.id=d.active_snapshot_id AND s.dataset_id=d.id
 WHERE d.source_id='osm' AND d.scope_id='krasnoyarsk' AND s.status='ACTIVE'
), projection AS (
 SELECT md5(string_agg(concat_ws('|', b.osm_type, b.osm_id, p.source_id,
 p.is_synthetic::text, encode(ST_AsEWKB(p.location),'hex'), o.eligible::text,
 o.observation::text), E'\n' ORDER BY b.osm_type COLLATE "C", b.osm_id)) fingerprint
 FROM active a JOIN osm_active_pois b ON b.dataset_id=a.dataset_id AND b.snapshot_id=a.snapshot_id
 JOIN pois p ON p.id=b.poi_id JOIN osm_snapshot_observations o
 ON o.snapshot_id=b.snapshot_id AND o.osm_type=b.osm_type AND o.osm_id=b.osm_id
)
SELECT d.id, d.slug, d.source_id, d.is_synthetic,
 md5(ST_AsEWKB(COALESCE(d.geometry,d.boundary))) geometry_checksum,
 a.*, p.fingerprint
FROM districts d LEFT JOIN active a ON true CROSS JOIN projection p
WHERE d.id=ANY(:district_ids) ORDER BY d.id
""")


def component_score(result, models) -> ComponentScore:
    """Public explanation excludes raw summaries and distance distributions."""
    raw = result.raw
    provenance = {} if raw is None else {
        "snapshot": raw.snapshot.model_dump(mode="json") if raw.snapshot else None,
        "sample_count": raw.sample_count,
        "distance_method": raw.distance_method,
    }
    if raw is not None and hasattr(raw, "geometry_snapshot") and raw.geometry_snapshot:
        provenance["geometry_snapshot"] = raw.geometry_snapshot.model_dump(mode="json")
    return ComponentScore(score=result.score, normalization_version=result.normalization_version,
        sampling_version=result.sampling_version, evidence_version=models.EVIDENCE_VERSION,
        eligibility_version=models.ELIGIBILITY_VERSION, reference_id=result.reference_id,
        reference_checksum=result.reference_checksum, unavailable_reason=result.unavailable_reason,
        limitations=result.limitations, provenance=provenance)


def read_precomputed(path=ARTIFACT_PATH):
    payload = Path(path).read_bytes()
    if hashlib.sha256(payload).hexdigest() != ARTIFACT_SHA256:
        raise ValueError("component_snapshot_checksum_mismatch")
    artifact = json.loads(payload)
    if artifact["version"] != "objective-canonical-district-snapshot-v1":
        raise ValueError("component_snapshot_version_mismatch")
    return artifact


class ObjectiveProvider:
    def __init__(self, session: Session):
        self.session = session

    def districts(self, district_ids):
        registry = tuple(contracts())
        artifact = None
        failure = None
        try:
            artifact = read_precomputed()
            # Preserve component-layer checksum/version gates, including Parks geometry.
            for _, _, _, ref, _ in registry:
                ref.read_reference()
            read_geometry()
        except (OSError, ValueError, KeyError) as exc:
            failure = "component_snapshot_unavailable_or_invalid:" + str(exc)
        rows = self.session.execute(PARITY_QUERY, {"district_ids": list(district_ids)}).mappings()
        results = {}
        for row in rows:
            reason = failure
            item = artifact["districts"].get(row["slug"]) if artifact else None
            snapshot = None
            if not reason:
                if row["version"] is None:
                    reason = "dataset_unavailable"
                else:
                    snapshot = SnapshotIdentity(dataset_key=row["dataset_key"], scope_id=row["scope_id"],
                        snapshot_version=row["version"], canonical_checksum=row["canonical_checksum"],
                        query_version=row["query_version"], query_hash=row["query_hash"],
                        foundation_eligibility_version=row["foundation_policy"])
                    try:
                        ready = source_ready(snapshot, Quality.model_validate(row["quality"]))
                    except (ValueError, TypeError):
                        ready = False
                    if not ready:
                        reason = "version_quality_failure"
                    elif snapshot.model_dump(mode="json") != artifact["snapshot"]:
                        reason = "component_snapshot_baseline_mismatch"
                    elif row["fingerprint"] != artifact["projection_fingerprint"]:
                        reason = "component_snapshot_projection_mismatch"
            if not reason and (not item or row["source_id"] != "osm" or row["is_synthetic"] or
                               row["geometry_checksum"] != item["geometry_ewkb_md5"]):
                reason = "sampling_domain_unvalidated"
            components = {}
            for name, model, _, ref, models in registry:
                component_reason = reason
                if not component_reason:
                    try:
                        result = model.model_validate({**item["components"][name], "district_id": row["id"]})
                        if (result.normalization_version != ref.NORMALIZATION_VERSION or
                            result.sampling_version != ref.SAMPLING_VERSION or
                            result.reference_id != ref.REFERENCE_ID or result.reference_checksum != ref.REFERENCE_SHA256):
                            raise ValueError("Unsupported component contract")
                        components[name] = component_score(result, models)
                    except (ValueError, KeyError, TypeError):
                        component_reason = "component_version_or_contract_mismatch"
                if component_reason:
                    components[name] = ComponentScore(normalization_version=ref.NORMALIZATION_VERSION,
                        sampling_version=ref.SAMPLING_VERSION, evidence_version=models.EVIDENCE_VERSION,
                        eligibility_version=models.ELIGIBILITY_VERSION, reference_id=ref.REFERENCE_ID,
                        reference_checksum=ref.REFERENCE_SHA256, unavailable_reason=component_reason)
            results[row["id"]] = aggregate(components, provenance={
                "computation_path": "precomputed_canonical_components",
                "component_snapshot_checksum": ARTIFACT_SHA256,
                "snapshot": snapshot.model_dump(mode="json") if snapshot else None,
                "geometry_ewkb_md5": row["geometry_checksum"],
            })
        return results
