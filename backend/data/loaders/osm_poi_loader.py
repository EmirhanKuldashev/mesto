"""One-off OpenStreetMap POI import for evidence-based ЖК scoring."""

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from geoalchemy2.elements import WKTElement
from sqlalchemy import select

from app import models
from app.db import create_session_factory


RAW_PATH = Path(__file__).resolve().parents[1] / "raw" / "osm" / "poi.json"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
BBOX = "55.8,92.5,56.25,93.45"  # South, west, north, east; includes Krasnoyarsk and nearby outskirts.
QUERY = f'''[out:json][timeout:60];(
  nwr["amenity"~"^(school|kindergarten|hospital|clinic)$"]({BBOX});
  nwr["leisure"="park"]({BBOX});
  nwr["highway"="bus_stop"]({BBOX});
);out center;'''
logger = logging.getLogger(__name__)


def fetch_raw(path: Path = RAW_PATH) -> Path:
    """Make one bounded Overpass request; no retries or background polling."""
    request = Request(
        OVERPASS_URL,
        data=urlencode({"data": QUERY}).encode(),
        headers={"User-Agent": "MESTO/0.1 (https://github.com/EmirhanKuldashev/mesto)"},
        method="POST",
    )
    with urlopen(request, timeout=90) as response:
        payload = response.read()
    parsed = json.loads(payload)
    if not isinstance(parsed.get("elements"), list):
        raise ValueError("Overpass response has no elements")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    logger.info("Saved %s OSM elements to %s", len(parsed["elements"]), path)
    return path


def load_pois(session, path: Path = RAW_PATH) -> dict[str, int]:
    raw = path.read_bytes()
    payload = json.loads(raw)
    if not isinstance(payload.get("elements"), list):
        raise ValueError("Invalid OSM POI RAW file")
    fetched_at = datetime.now(timezone.utc)
    checksum = hashlib.sha256(raw).hexdigest()
    version_name = f"krasnoyarsk-{checksum[:20]}"
    source = session.scalar(select(models.DataSource).where(models.DataSource.source_id == "osm"))
    if source is None:
        session.add(models.DataSource(
            source_id="osm", source_type="openstreetmap", name="OpenStreetMap",
            url="https://www.openstreetmap.org/", is_synthetic=False,
        ))
        session.flush()
    existing_version = session.scalar(select(models.SourceVersion).where(
        models.SourceVersion.source_id == "osm", models.SourceVersion.source_version == version_name,
    ))
    if existing_version is None:
        session.add(models.SourceVersion(
            source_id="osm", source_version=version_name, fetched_at=fetched_at,
            checksum=checksum, record_count=len(payload["elements"]),
        ))
    created = updated = skipped = 0
    for item in payload["elements"]:
        tags = item.get("tags") or {}
        category = tags.get("amenity") or tags.get("leisure") or tags.get("highway")
        if category not in {"school", "kindergarten", "hospital", "clinic", "park", "bus_stop"}:
            skipped += 1
            continue
        name = tags.get("name")
        location = item.get("center") or item
        lat, lon = location.get("lat"), location.get("lon")
        if not isinstance(name, str) or not name.strip() or not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
            skipped += 1
            continue
        if not (55.8 <= lat <= 56.25 and 92.5 <= lon <= 93.45):
            skipped += 1
            continue
        external_id = f"{item['type']}:{item['id']}"
        point = session.scalar(select(models.POI).where(
            models.POI.source_id == "osm", models.POI.external_id == external_id,
        ))
        if point is None:
            point = models.POI(source_id="osm", external_id=external_id)
            session.add(point)
            created += 1
        else:
            updated += 1
        point.source_type = "openstreetmap"
        point.source_version = version_name
        point.fetched_at = fetched_at
        point.is_synthetic = False
        point.name = name[:200]
        point.category = category
        point.location = WKTElement(f"POINT({lon} {lat})", srid=4326)
        point.metadata_json = {"osm_type": item["type"], "osm_id": item["id"]}
    logger.info("OSM POIs: created=%s updated=%s skipped=%s", created, updated, skipped)
    return {"created": created, "updated": updated, "skipped": skipped}


def main() -> None:
    path = fetch_raw()
    factory, engine = create_session_factory()
    try:
        with factory.begin() as session:
            print(load_pois(session, path))
    finally:
        engine.dispose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    main()
