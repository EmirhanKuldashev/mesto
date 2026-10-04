"""Shared OSM evidence persistence; legacy bootstrap remains explicitly partial."""

import logging
from datetime import datetime, timezone
from pathlib import Path

from geoalchemy2.elements import WKTElement
from sqlalchemy import func, select, update

from app import models
from app.db import create_session_factory
from data.osm.collection import collect
from data.osm.contracts import BuildResult, Status, canonical_bytes, checksum
from data.osm.legacy import LEGACY_EXTENT, build_legacy
from data.osm.validation import timestamp

RAW_PATH = Path(__file__).resolve().parents[1] / "raw" / "osm" / "poi.json"
logger = logging.getLogger(__name__)


def fetch_raw(path: Path = RAW_PATH) -> Path:
    """Explicit future collection; never overwrite a historical artifact."""
    manifest = collect(dataset_id="osm-poi", scope_id="krasnoyarsk",
        snapshot_id=path.parent.name, extent=LEGACY_EXTENT, parts={"full": LEGACY_EXTENT},
        output_dir=path.parent / path.stem)
    return path.parent / path.stem / manifest.parts[0].artifact_reference


def _persist(session, result: BuildResult, *, version_name: str, version_fetched_at: datetime,
             legacy: bool) -> dict[str, int]:
    """Upsert only, in the caller's transaction. No replacement/retirement claim."""
    incoming = [row for row in result.observations if row.eligible]
    existing = {}
    # Preflight every identity before mutations. No cross-scope/synthetic overwrite.
    for row in incoming:
        external_id = f"{row.osm_type}:{row.osm_id}"
        candidates = list(session.scalars(select(models.POI).where(
            models.POI.source_id == "osm", models.POI.external_id == external_id)))
        if len(candidates) > 1:
            raise ValueError(f"Ambiguous persisted OSM identity: {external_id}")
        point = candidates[0] if candidates else None
        if point is not None:
            foundation = (point.metadata_json or {}).get("osm_foundation", {})
            if point.is_synthetic:
                raise ValueError("Synthetic OSM identity cannot be overwritten")
            if legacy and point.source_version != version_name:
                raise ValueError("A partial legacy snapshot cannot replace existing evidence")
            if foundation and (foundation.get("dataset_id"), foundation.get("scope_id")) != (row.dataset_id, row.scope_id):
                raise ValueError("Cross-dataset/scope overwrite requires a reviewed lifecycle schema")
            if not foundation and not legacy:
                raise ValueError("Legacy identity adoption requires explicit migration/lifecycle review")
        existing[row.identity] = point
    source = session.scalar(select(models.DataSource).where(models.DataSource.source_id == "osm"))
    if source is None:
        session.add(models.DataSource(source_id="osm", source_type="openstreetmap", name="OpenStreetMap",
            url="https://www.openstreetmap.org/", is_synthetic=False))
        session.flush()
    elif source.is_synthetic:
        raise ValueError("OSM DataSource is unexpectedly synthetic")
    version = session.scalar(select(models.SourceVersion).where(
        models.SourceVersion.source_id == "osm", models.SourceVersion.source_version == version_name))
    if version is None:
        session.add(models.SourceVersion(source_id="osm", source_version=version_name,
            fetched_at=version_fetched_at, checksum=result.report.get("input_checksum", result.canonical_checksum),
            record_count=len(result.observations)))
    created = updated = 0
    persisted = []
    for row in incoming:
        point = existing[row.identity]
        if point is None:
            point = models.POI(source_id="osm", external_id=f"{row.osm_type}:{row.osm_id}")
            session.add(point)
            created += 1
        else:
            updated += 1
        point.source_type = "openstreetmap"
        point.source_version = version_name
        fetches = [ref.fetched_at for ref in row.source_references if ref.fetched_at is not None]
        point.fetched_at = max(fetches) if fetches else version_fetched_at
        point.is_synthetic = False
        point.name = row.name[:200] if row.name is not None else None
        point.category = row.category
        point.location = WKTElement(f"POINT({row.longitude} {row.latitude})", srid=4326)
        point.metadata_json = {"osm_type": row.osm_type, "osm_id": row.osm_id,
            "osm_foundation": {**row.model_dump(mode="json"), "quality": result.quality.model_dump(mode="json"),
                "canonical_checksum": result.canonical_checksum,
                "fetched_at_semantics": "legacy_aggregate_or_import_time" if legacy else "latest_artifact_fetch",
                "query_version": result.canonical.get("query_version"),
                "query_hash": result.canonical.get("query_hash"), "extent": result.canonical["extent"],
                "legacy_snapshot_fetched_at": result.canonical.get("legacy_snapshot_fetched_at")}}
        persisted.append(point)
    session.flush()
    ids = [point.id for point in persisted]
    owners = {}
    if ids:
        for poi_id, district_id in session.execute(select(models.POI.id, models.District.id).join(
            models.District, func.ST_Covers(models.District.geometry, models.POI.location)
        ).where(models.POI.id.in_(ids), models.District.source_id == "osm", models.District.is_synthetic.is_(False))):
            owners.setdefault(poi_id, []).append(district_id)
    assignments = [{"id": id_, "district_id": owners[id_][0] if len(owners.get(id_, [])) == 1 else None} for id_ in ids]
    if assignments:
        session.execute(update(models.POI), assignments)
    return {"created": created, "updated": updated,
        "skipped": len(result.observations) - len(incoming),
        "assigned": sum(item["district_id"] is not None for item in assignments), "total": len(ids)}


def load_dataset(session, result: BuildResult) -> dict[str, int]:
    """Accept validated evidence for upsert only; retirement is NOT implemented."""
    if result.quality.quality_status != Status.VALIDATED:
        raise ValueError("Only a validated coherent build may be persisted through load_dataset")
    if checksum(canonical_bytes(result.canonical)) != result.canonical_checksum or result.canonical["observations"] != [
            row.model_dump(mode="json") for row in result.observations] or result.canonical["quality"] != result.quality.model_dump(mode="json"):
        raise ValueError("Build result content/checksum mismatch")
    fetches = [timestamp(part.get("fetched_at")) for part in result.canonical["parts"] if part.get("fetched_at")]
    if not fetches:
        raise ValueError("No per-part fetched_at available")
    scope_hash = checksum(canonical_bytes([result.canonical["dataset_id"], result.canonical["scope_id"]]))[:12]
    return _persist(session, result, version_name=f"osm-v1-{scope_hash}-{result.canonical_checksum[:32]}",
                    version_fetched_at=max(fetches), legacy=False)


def load_pois(session, path: Path = RAW_PATH, *, extent=LEGACY_EXTENT,
              dataset_id="legacy-poi", scope_id="krasnoyarsk") -> dict[str, int]:
    """Read the existing snapshot honestly; no fabricated original provenance."""
    result = build_legacy(path, extent=extent, dataset_id=dataset_id, scope_id=scope_id)
    # Existing non-null DB field retains aggregate/import time, not original fetch/base.
    snapshot_time = result.canonical.get("legacy_snapshot_fetched_at")
    fetched_at = timestamp(snapshot_time)
    if snapshot_time is not None and fetched_at is None:
        raise ValueError("Invalid legacy aggregate timestamp")
    fetched_at = fetched_at or datetime.now(timezone.utc)
    version_name = f"{scope_id}-{result.report['input_checksum'][:20]}"
    if len(version_name) > 100:
        raise ValueError("Legacy source version exceeds storage contract")
    return _persist(session, result, version_name=version_name, version_fetched_at=fetched_at, legacy=True)


def main() -> None:
    # Offline by default. Fresh collection/build is a separate phase.
    factory, engine = create_session_factory()
    try:
        with factory.begin() as session:
            print(load_pois(session))
    finally:
        engine.dispose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    main()
