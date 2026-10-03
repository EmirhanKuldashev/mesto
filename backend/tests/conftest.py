"""PostGIS baseline using a disposable, migrated test database only."""
import os
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import text

from app.db import create_session_factory
from app.etl.seed import seed
from data.loaders.osm_district_loader import load_districts
from data.loaders.osm_poi_loader import load_pois

BACKEND = Path(__file__).resolve().parents[1]


def require_database():
    return os.getenv("MESTO_REQUIRE_TEST_DATABASE") == "1"


def pytest_configure(config):
    if require_database() and not os.getenv("MESTO_TEST_DATABASE_URL"):
        raise pytest.UsageError("MESTO_TEST_DATABASE_URL is required for the CI backend baseline")


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    result = yield
    report = result.get_result()
    if require_database() and item.get_closest_marker("integration") and report.skipped:
        report.outcome = "failed"
        report.longrepr = f"Integration tests must run in CI; skip rejected: {report.longrepr}"


@pytest.fixture(scope="session")
def alembic_heads():
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "migrations"))
    heads = set(ScriptDirectory.from_config(config).get_heads())
    assert len(heads) == 1, f"Expected one Alembic head, found {heads}"
    return heads


@pytest.fixture(scope="session")
def test_database_url(alembic_heads):
    url = os.getenv("MESTO_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set MESTO_TEST_DATABASE_URL to a disposable migrated PostGIS test database")
    factory, engine = create_session_factory(url)
    try:
        with engine.connect() as connection:
            assert set(MigrationContext.configure(connection).get_current_heads()) == alembic_heads
            assert connection.scalar(text("SELECT PostGIS_Version()"))
        # Existing catalogue/profile checks require the demo sources, and the AI
        # context check needs a non-synthetic district. Use committed snapshots;
        # never scrape or contact external APIs during test setup.
        with factory.begin() as session:
            seed(session)
            load_districts(session, BACKEND / "data/fixtures/osm/krasnoyarsk_districts.json")
            load_pois(session, BACKEND / "data/fixtures/osm/poi.json")
        return url
    finally:
        engine.dispose()
