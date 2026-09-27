"""Import the bundled, dated OpenStreetMap snapshot on application startup."""

from pathlib import Path

from app.db import create_session_factory
from data.loaders.osm_district_loader import load_districts
from data.loaders.osm_poi_loader import load_pois

SNAPSHOT = Path(__file__).resolve().parents[2] / "data" / "fixtures" / "osm"


def main() -> None:
    factory, engine = create_session_factory()
    try:
        with factory.begin() as session:
            districts = load_districts(session, SNAPSHOT / "krasnoyarsk_districts.json")
            pois = load_pois(session, SNAPSHOT / "poi.json")
            print({"districts": districts, "pois": pois})
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
