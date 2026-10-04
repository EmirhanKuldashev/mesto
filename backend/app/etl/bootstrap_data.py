"""Import dated OSM and Cian snapshots on application startup."""

from pathlib import Path

from app.db import create_session_factory
from data.loaders.cian_complex_loader import load_cian_complexes
from data.loaders.cian_loader import load_cian_json
from data.loaders.osm_district_loader import load_districts
from data.osm.baseline import load_current_baseline

FIXTURES = Path(__file__).resolve().parents[2] / "data" / "fixtures"


def main() -> None:
    factory, engine = create_session_factory()
    try:
        with factory.begin() as session:
            districts = load_districts(session, FIXTURES / "osm" / "krasnoyarsk_districts.json")
            pois = load_current_baseline(session)
            complexes = load_cian_complexes(session, FIXTURES / "cian" / "complexes.json")
            listings = load_cian_json(session, FIXTURES / "cian" / "listings.json")
            print({"districts": districts, "pois": pois, "complexes": complexes,
                   "listings": listings})
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
