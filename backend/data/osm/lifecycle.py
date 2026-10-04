"""Caller-owned transactions: immutable candidates, reviewed atomic projection."""
from datetime import datetime, timezone

from geoalchemy2.elements import WKTElement
from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert

from app import models
from data.osm.contracts import BuildResult, Manifest, canonical_bytes, checksum
from data.osm.query import load_definition, render_query
from data.osm.validation import timestamp

REQUIRED = ("quality_status", "query_completeness_status", "provenance_status",
            "eligibility_status", "temporal_status")


def _dataset(session, key, scope):
    source = session.scalar(select(models.DataSource).where(models.DataSource.source_id == "osm"))
    if source is None:
        session.add(models.DataSource(source_id="osm", source_type="openstreetmap",
            name="OpenStreetMap", is_synthetic=False))
        session.flush()
    elif source.is_synthetic:
        raise ValueError("Synthetic OSM DataSource cannot enter lifecycle")
    session.execute(insert(models.OsmDataset).values(source_id="osm", dataset_key=key, scope_id=scope)
        .on_conflict_do_nothing(index_elements=["source_id", "scope_id"]))
    row = session.scalar(select(models.OsmDataset).where(models.OsmDataset.source_id == "osm",
        models.OsmDataset.scope_id == scope).with_for_update().execution_options(populate_existing=True))
    # Identity is SOURCE/SCOPE. The bootstrap label 'legacy-poi' and collector
    # label 'osm-poi' describe versions of that SAME managed source scope.
    return row


def _lock(session, snapshot_id):
    dataset_id = session.scalar(select(models.OsmSnapshot.dataset_id).where(models.OsmSnapshot.id == snapshot_id))
    if dataset_id is None:
        raise ValueError("Snapshot not found")
    dataset = session.scalar(select(models.OsmDataset).where(models.OsmDataset.id == dataset_id)
        .with_for_update().execution_options(populate_existing=True))
    snapshot = session.scalar(select(models.OsmSnapshot).where(models.OsmSnapshot.id == snapshot_id)
        .execution_options(populate_existing=True))
    return dataset, snapshot


def _check_result(result):
    result = BuildResult.model_validate(result)
    if checksum(canonical_bytes(result.canonical)) != result.canonical_checksum or result.canonical.get("observations") != [
        row.model_dump(mode="json") for row in result.observations] or result.canonical.get("quality") != result.quality.model_dump(mode="json"):
        raise ValueError("Build result content/checksum mismatch")
    return result


def _quality_gate(snapshot):
    if snapshot.is_legacy or any(snapshot.quality.get(key) != "VALIDATED" for key in REQUIRED):
        raise ValueError("Activation requires validated coherent non-legacy evidence")
    if snapshot.build_report.get("part_errors") or snapshot.build_report.get("conflicts"):
        raise ValueError("Activation blocked by failed build/conflicts")
    if not snapshot.sealed or not snapshot.manifest_checksum:
        raise ValueError("Activation requires sealed manifest provenance")
    if snapshot.build_report.get("eligible_count", 0) == 0:
        raise ValueError("Empty snapshot activation requires a separate reviewed policy")
    for key in ("freshness_status", "source_completeness_status", "real_world_completeness_status"):
        if snapshot.quality.get(key) not in ("UNKNOWN", "VALIDATED"):
            raise ValueError("Activation quality policy does not permit " + key)


def _projection(row, result):
    if not row.eligible:
        return None
    fetched = max(ref.fetched_at for ref in row.source_references if ref.fetched_at is not None)
    return {
        "source_id":"osm", "source_type":"openstreetmap",
        "source_version":"osm-snapshot-"+result.canonical_checksum[:32],
        "fetched_at":fetched.isoformat(), "valid_from":None,"valid_to":None,"is_synthetic":False,
        "name":row.name[:200] if row.name is not None else None, "category":row.category,
        "external_id":f"{row.osm_type}:{row.osm_id}", "subcategory":None,
        "district_id":None, "location_wkt":f"SRID=4326;POINT({row.longitude} {row.latitude})", "geometry_wkt":None,
        "metadata":{"osm_type":row.osm_type,"osm_id":row.osm_id,"osm_foundation":{
            **row.model_dump(mode="json"),"quality":result.quality.model_dump(mode="json"),
            "canonical_checksum":result.canonical_checksum,"fetched_at_semantics":"latest_artifact_fetch",
            "query_version":result.canonical["query_version"],"query_hash":result.canonical["query_hash"],
            "extent":result.canonical["extent"],"legacy_snapshot_fetched_at":None}},
    }


def persist_candidate(session, result: BuildResult, *, manifest: Manifest | None = None):
    """Store build identity/history only. Never write consumer POIs or activate."""
    result = _check_result(result)
    canonical = result.canonical
    derived = Manifest.model_validate({key: canonical[key] for key in (
        "dataset_id","scope_id","snapshot_id","query_version","query_hash","extent",
        "requested_as_of","parts","builder_version","category_scope")}
        | {"query_definition":load_definition().model_dump()})
    origin = "provided_manifest" if manifest is not None else "reconstructed_builder_input"
    if manifest is not None:
        manifest = Manifest.model_validate(manifest)
        for key in ("dataset_id","scope_id","snapshot_id","query_version","query_hash","extent",
                    "requested_as_of","builder_version"):
            if getattr(manifest,key) != getattr(derived,key):
                raise ValueError("Manifest does not match canonical build")
        if (set(manifest.category_scope) != set(derived.category_scope) or
            sorted(manifest.parts,key=lambda p:p.part_id) != sorted(derived.parts,key=lambda p:p.part_id) or
            render_query(manifest.query_definition,manifest.extent,manifest.requested_as_of) !=
            render_query(derived.query_definition,derived.extent,derived.requested_as_of)):
            raise ValueError("Manifest does not match canonical build")
    else:
        manifest = derived
    manifest_json = manifest.model_dump(mode="json")
    with session.begin_nested():
        dataset = _dataset(session, manifest.dataset_id, manifest.scope_id)
        existing = session.scalar(select(models.OsmSnapshot).where(models.OsmSnapshot.dataset_id == dataset.id,
            models.OsmSnapshot.version == manifest.snapshot_id))
        if existing:
            if existing.canonical_checksum != result.canonical_checksum:
                raise ValueError("Immutable snapshot version already has different content")
            return existing
        fetches = [part.fetched_at for part in manifest.parts if part.fetched_at]
        bases = {part.source_base_timestamp for part in manifest.parts if part.source_base_timestamp}
        snapshot = models.OsmSnapshot(dataset_id=dataset.id, version=manifest.snapshot_id,
            status="CANDIDATE" if result.quality.quality_status == "VALIDATED" else "REJECTED",
            is_legacy=False, sealed=False, canonical_checksum=result.canonical_checksum,
            manifest_checksum=checksum(canonical_bytes(manifest_json)), manifest_json=manifest_json,
            canonical_json=canonical, build_report={**result.report,"manifest_identity_origin":origin}, quality=result.quality.model_dump(mode="json"),
            query_version=manifest.query_version, query_hash=manifest.query_hash,
            collected_at=max(fetches) if fetches else None,
            source_base_timestamp=next(iter(bases)) if len(bases)==1 else None)
        session.add(snapshot)
        session.flush()
        for row in result.observations:
            payload = _projection(row, result) if result.quality.quality_status == "VALIDATED" else None
            if payload:
                owners = list(session.scalars(select(models.District.id).where(models.District.source_id == "osm",
                    models.District.is_synthetic.is_(False), func.ST_Covers(models.District.geometry,
                        WKTElement(payload["location_wkt"], extended=True)))))
                payload["district_id"] = owners[0] if len(owners)==1 else None
            session.add(models.OsmSnapshotObservation(snapshot_id=snapshot.id, osm_type=row.osm_type,
                osm_id=row.osm_id, eligible=row.eligible, observation=row.model_dump(mode="json"),
                projection=payload, location=WKTElement(f"POINT({row.longitude} {row.latitude})",srid=4326)
                    if row.longitude is not None and row.latitude is not None else None))
        session.flush()
        snapshot.sealed = True
        session.flush()
        return snapshot


def review_for_activation(session, snapshot_id, *, reviewer: str, reason: str):
    """Explicit reviewed acceptance of UNKNOWN proxy quality; not fabricated freshness."""
    if not reviewer.strip() or not reason.strip():
        raise ValueError("Named reviewer and justification are required")
    with session.begin_nested():
        _, snapshot = _lock(session, snapshot_id)
        if snapshot.status != "CANDIDATE":
            raise ValueError("Only a candidate may receive activation review")
        _quality_gate(snapshot)
        snapshot.activation_review = {"policy":"osm-proxy-reviewed-unknown-v1", "reviewer":reviewer,
            "reason":reason,"reviewed_at":datetime.now(timezone.utc).isoformat(),
            "accepted_unknowns":[key for key in ("freshness_status","source_completeness_status",
                "real_world_completeness_status") if snapshot.quality[key]=="UNKNOWN"]}
        snapshot.status = "VALIDATED"
        session.flush()
        return snapshot


def activate_snapshot(session, snapshot_id):
    """Atomic savepoint; commit belongs to caller. Dataset row serializes switches."""
    with session.begin_nested():
        dataset, snapshot = _lock(session, snapshot_id)
        if session.scalar(select(models.DataSource.is_synthetic).where(models.DataSource.source_id==dataset.source_id)) is not False:
            raise ValueError("Activation requires a real OSM DataSource")
        if snapshot.status != "VALIDATED" or not snapshot.activation_review:
            raise ValueError("Activation requires an explicitly reviewed VALIDATED candidate")
        _quality_gate(snapshot)
        observations = list(session.scalars(select(models.OsmSnapshotObservation).where(
            models.OsmSnapshotObservation.snapshot_id == snapshot.id,
            models.OsmSnapshotObservation.eligible.is_(True))))
        if len(observations) != snapshot.build_report["eligible_count"] or any(not row.projection for row in observations):
            raise ValueError("Snapshot membership/projection does not match validated build")
        bindings = list(session.scalars(select(models.OsmActivePoi).where(models.OsmActivePoi.dataset_id == dataset.id)))
        current = {(row.osm_type,row.osm_id):row for row in bindings}
        for binding in bindings:
            if session.get(models.POI,binding.poi_id).is_synthetic:
                raise ValueError("Synthetic POI cannot be retired or reassigned")
        for row in observations:
            points = list(session.scalars(select(models.POI).where(models.POI.source_id=="osm",
                models.POI.external_id==f"{row.osm_type}:{row.osm_id}")))
            binding = current.get((row.osm_type,row.osm_id))
            if any(point.is_synthetic for point in points):
                raise ValueError("Synthetic OSM identity cannot be overwritten")
            if any(not binding or point.id != binding.poi_id for point in points):
                raise ValueError("Cross-dataset/scope or unmanaged OSM projection collision")
        incoming = {(row.osm_type,row.osm_id) for row in observations}
        for identity,binding in current.items():
            if identity not in incoming:
                point = session.get(models.POI,binding.poi_id)
                session.delete(binding)
                session.flush()
                session.delete(point)  # remove CURRENT materialization, never source history
        session.flush()
        if dataset.active_snapshot_id is not None:
            previous = session.get(models.OsmSnapshot,dataset.active_snapshot_id)
            previous.status = "RETIRED"
            session.flush()
        snapshot.status = "ACTIVE"
        session.flush()
        for row in observations:
            binding = current.get((row.osm_type,row.osm_id))
            point = session.get(models.POI,binding.poi_id) if binding else models.POI()
            payload = row.projection
            for key in ("name","category","external_id","subcategory","district_id","source_id",
                        "source_type","source_version","is_synthetic","valid_from","valid_to"):
                setattr(point,key,payload[key])
            point.fetched_at = timestamp(payload["fetched_at"])
            point.metadata_json = payload["metadata"]
            point.location = WKTElement(payload["location_wkt"],extended=True)
            point.geometry = WKTElement(payload["geometry_wkt"],extended=True) if payload["geometry_wkt"] else None
            session.add(point)
            session.flush()
            if binding:
                binding.snapshot_id = snapshot.id
            else:
                session.add(models.OsmActivePoi(poi_id=point.id,dataset_id=dataset.id,snapshot_id=snapshot.id,
                    osm_type=row.osm_type,osm_id=row.osm_id))
        dataset.active_snapshot_id = snapshot.id
        session.flush()
        return snapshot


def adopt_legacy(session, result, version_name):
    """First offline bootstrap only; existing projection payload remains byte-for-byte."""
    with session.begin_nested():
        dataset = _dataset(session,result.canonical["dataset_id"],result.canonical["scope_id"])
        if dataset.active_snapshot_id is not None:
            raise ValueError("Legacy adoption cannot replace a managed active snapshot")
        snapshot = models.OsmSnapshot(dataset_id=dataset.id,version="legacy-source-version:"+version_name,
            status="ACTIVE",is_legacy=True,sealed=False,canonical_checksum=result.canonical_checksum,
            canonical_json=result.canonical,build_report=result.report,quality=result.quality.model_dump(mode="json"))
        session.add(snapshot)
        session.flush()
        for row in result.observations:
            if not row.eligible:
                continue
            point = session.scalar(select(models.POI).where(models.POI.source_id=="osm",
                models.POI.external_id==f"{row.osm_type}:{row.osm_id}"))
            payload = session.execute(text("""SELECT to_jsonb(p)-'location'-'geometry' AS payload,
                ST_AsEWKT(location) AS location_wkt,ST_AsEWKT(geometry) AS geometry_wkt FROM pois p WHERE id=:id"""),
                {"id":point.id}).mappings().one()
            projection = dict(payload["payload"]) | {"location_wkt":payload["location_wkt"],"geometry_wkt":payload["geometry_wkt"]}
            session.add(models.OsmSnapshotObservation(snapshot_id=snapshot.id,osm_type=row.osm_type,
                osm_id=row.osm_id,eligible=True,observation=row.model_dump(mode="json"),
                projection=projection,location=point.location))
            session.flush()
            session.add(models.OsmActivePoi(poi_id=point.id,dataset_id=dataset.id,snapshot_id=snapshot.id,
                osm_type=row.osm_type,osm_id=row.osm_id))
        session.flush()
        snapshot.sealed = True
        dataset.active_snapshot_id = snapshot.id
        session.flush()
        return snapshot


def legacy_bootstrap_state(session, result, version_name):
    """No resurrection on restart; changed partial content cannot replace history."""
    dataset = session.scalar(select(models.OsmDataset).where(models.OsmDataset.source_id=="osm",
        models.OsmDataset.scope_id==result.canonical["scope_id"]).with_for_update().execution_options(populate_existing=True))
    if dataset is None or dataset.active_snapshot_id is None:
        return None
    active = session.get(models.OsmSnapshot,dataset.active_snapshot_id)
    rows = list(session.scalars(select(models.POI).join(models.OsmActivePoi,
        models.OsmActivePoi.poi_id==models.POI.id).where(models.OsmActivePoi.dataset_id==dataset.id)))
    if active.is_legacy and (dataset.dataset_key != result.canonical["dataset_id"] or
        active.version != "legacy-source-version:"+version_name):
        raise ValueError("A partial legacy snapshot cannot replace existing evidence")
    return {"created":0,"updated":len(rows) if active.is_legacy else 0,"skipped":0,
        "assigned":sum(row.district_id is not None for row in rows),"total":len(rows)}
