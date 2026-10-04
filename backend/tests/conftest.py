"""PostGIS baseline using a disposable, migrated test database only."""
import os
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.config import Config
from alembic import command
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.db import create_session_factory
from app.etl.seed import seed
from data.loaders.osm_district_loader import load_districts
from data.loaders.osm_poi_loader import load_pois
from data.osm.baseline import load_current_baseline

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
            load_current_baseline(session)
        return url
    finally:
        engine.dispose()


@pytest.fixture(scope="session")
def legacy_test_database_url(test_database_url):
    """Explicit historical regression environment; default CI baseline is fresh."""
    base = make_url(test_database_url)
    name = "mesto_legacy_baseline_" + uuid4().hex
    admin = create_engine(base, isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    url = base.set(database=name).render_as_string(hide_password=False)
    factory, engine = create_session_factory(url)
    previous = os.environ.get("DATABASE_URL")
    try:
        os.environ["DATABASE_URL"] = url
        config = Config(str(BACKEND / "alembic.ini"))
        config.set_main_option("script_location", str(BACKEND / "migrations"))
        command.upgrade(config, "head")
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous
        with factory.begin() as session:
            load_districts(session, BACKEND / "data/fixtures/osm/krasnoyarsk_districts.json")
            load_pois(session, BACKEND / "data/fixtures/osm/poi.json")
        yield url
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous
        engine.dispose()
        assert name.startswith("mesto_legacy_baseline_") and name != base.database
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE "{name}"'))
        admin.dispose()


@pytest.fixture
def legacy_session(legacy_test_database_url):
    _, engine = create_session_factory(legacy_test_database_url)
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
                    yield session
            finally:
                transaction.rollback()
    finally:
        engine.dispose()
