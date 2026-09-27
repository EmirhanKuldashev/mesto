"""Load the seven administrative districts of Krasnoyarsk from cached OSM boundaries."""

import hashlib
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from sqlalchemy import cast, func, select
from geoalchemy2 import Geography

from app import models
from app.db import create_session_factory


RAW_PATH = Path(__file__).resolve().parents[1] / "raw" / "osm" / "krasnoyarsk_districts.json"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
DISTRICTS = {
    "Центральный": "centralny",
    "Советский": "sovetsky",
    "Октябрьский": "oktyabrsky",
    "Железнодорожный": "zheleznodorozhny",
    "Свердловский": "sverdlovsky",
    "Ленинский": "leninsky",
    "Кировский": "kirovsky",
}
logger = logging.getLogger(__name__)


def as_multipolygon(geometry: dict) -> dict:
    """Keep actual OSM rings and normalize Polygon to the PostGIS column type."""
    if geometry.get("type") == "Polygon":
        coordinates = [geometry.get("coordinates")]
    elif geometry.get("type") == "MultiPolygon":
        coordinates = geometry.get("coordinates")
    else:
        raise ValueError("District boundary must be a Polygon or MultiPolygon")
    if not isinstance(coordinates, list) or not coordinates:
        raise ValueError("District boundary is empty")
    return {"type": "MultiPolygon", "coordinates": coordinates}


def validate_record(record: dict) -> None:
    if record.get("name") not in DISTRICTS or record.get("slug") != DISTRICTS[record["name"]]:
        raise ValueError("Unexpected Krasnoyarsk district")
    if not isinstance(record.get("osm_id"), int) or record["osm_id"] <= 0:
        raise ValueError("District has no OSM relation id")
    as_multipolygon(record.get("geometry") or {})


def fetch_raw(path: Path = RAW_PATH) -> Path:
    """Fetch and cache seven exact district relations in a single thread at <=1 req/s."""
    if path.exists():
        logger.info("Using cached district boundaries: %s", path)
        return path
    records = []
    for index, (name, slug) in enumerate(DISTRICTS.items()):
        if index:
            time.sleep(1.2)
        query = urlencode({
            "q": f"{name} район, Красноярск", "format": "jsonv2", "polygon_geojson": 1,
            "addressdetails": 1, "limit": 5, "countrycodes": "ru",
        })
        request = Request(
            f"{NOMINATIM_URL}?{query}",
            headers={"User-Agent": "MESTO/0.1 (https://github.com/EmirhanKuldashev/mesto)"},
        )
        with urlopen(request, timeout=45) as response:
            results = json.load(response)
        matches = [item for item in results if item.get("osm_type") == "relation"
                   and item.get("category") == "boundary" and item.get("type") == "administrative"
                   and item.get("display_name", "").startswith(f"{name} район, Красноярск,")]
        if len(matches) != 1:
            raise ValueError(f"Could not verify a unique administrative boundary for {name}: {len(matches)} matches")
        match = matches[0]
        record = {
            "name": name, "slug": slug, "osm_id": match["osm_id"],
            "geometry": as_multipolygon(match["geojson"]),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "source_url": f"https://www.openstreetmap.org/relation/{match['osm_id']}",
        }
        validate_record(record)
        records.append(record)
        logger.info("Fetched %s (%s)", name, record["source_url"])
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)
    return path


def assign_complex_districts(session) -> tuple[int, int]:
    """Assign each located Cian complex only when exactly one OSM district covers it."""
    complexes = session.scalars(select(models.ResidentialComplex).where(
        models.ResidentialComplex.source_id == "cian", models.ResidentialComplex.location.is_not(None),
    )).all()
    assigned = 0
    for complex_item in complexes:
        owners = session.scalars(select(models.District.id).where(
            models.District.source_id == "osm",
            func.ST_Covers(models.District.geometry, complex_item.location),
        )).all()
        complex_item.district_id = owners[0] if len(owners) == 1 else None
        assigned += int(len(owners) == 1)
    return assigned, len(complexes)


def load_districts(session, path: Path = RAW_PATH) -> dict[str, int]:
    raw = path.read_bytes()
    records = json.loads(raw)
    if not isinstance(records, list) or len(records) != len(DISTRICTS):
        raise ValueError("Expected exactly seven Krasnoyarsk administrative districts")
    for record in records:
        validate_record(record)
    if {record["name"] for record in records} != set(DISTRICTS):
        raise ValueError("District boundaries are duplicated or missing")
    source = session.scalar(select(models.DataSource).where(models.DataSource.source_id == "osm"))
    if source is None:
        session.add(models.DataSource(
            source_id="osm", source_type="openstreetmap", name="OpenStreetMap",
            url="https://www.openstreetmap.org/", is_synthetic=False,
        ))
        session.flush()
    checksum = hashlib.sha256(raw).hexdigest()
    version_name = f"district-{checksum[:20]}"
    version = session.scalar(select(models.SourceVersion).where(
        models.SourceVersion.source_id == "osm", models.SourceVersion.source_version == version_name,
    ))
    if version is None:
        session.add(models.SourceVersion(
            source_id="osm", source_version=version_name, checksum=checksum,
            fetched_at=max(datetime.fromisoformat(item["fetched_at"]) for item in records),
            record_count=len(records),
        ))
    created = updated = 0
    for record in records:
        slug = f"osm-{record['slug']}"
        district = session.scalar(select(models.District).where(models.District.slug == slug))
        if district is None:
            district = models.District(slug=slug)
            session.add(district)
            created += 1
        else:
            updated += 1
        district.name = record["name"]
        district.source_id = "osm"
        district.source_type = "openstreetmap"
        district.source_version = version_name
        district.fetched_at = datetime.fromisoformat(record["fetched_at"])
        district.is_synthetic = False
        geometry = json.dumps(record["geometry"])
        district.geometry = func.ST_SetSRID(func.ST_GeomFromGeoJSON(geometry), 4326)
        district.boundary = func.ST_SetSRID(func.ST_GeomFromGeoJSON(geometry), 4326)
        district.centroid = func.ST_PointOnSurface(func.ST_SetSRID(func.ST_GeomFromGeoJSON(geometry), 4326))
    session.flush()
    areas = session.execute(select(
        models.District.id,
        func.ST_Area(cast(models.District.geometry, Geography(srid=4326))) / 1_000_000,
    ).where(models.District.source_id == "osm")).all()
    for district_id, area_km2 in areas:
        session.get(models.District, district_id).area_km2 = round(area_km2, 2)
    session.flush()
    invalid = session.scalar(select(func.count()).select_from(models.District).where(
        models.District.source_id == "osm", func.ST_IsValid(models.District.geometry).is_(False),
    ))
    if invalid:
        raise ValueError(f"{invalid} OSM district polygons are invalid")
    # Only a unique containing polygon may own a complex. Border/overlap ambiguity stays unassigned.
    assigned, total = assign_complex_districts(session)
    logger.info("OSM districts: created=%s updated=%s complexes_assigned=%s/%s", created, updated, assigned, total)
    return {"created": created, "updated": updated, "complexes_assigned": assigned, "complexes_total": total}


def main() -> None:
    path = fetch_raw()
    factory, engine = create_session_factory()
    try:
        with factory.begin() as session:
            print(load_districts(session, path))
    finally:
        engine.dispose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    main()
