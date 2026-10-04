"""Nullable-name migration and POI contracts on disposable PostGIS only."""

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
import json

import pytest
from alembic.config import Config
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient
from geoalchemy2.elements import WKTElement
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import models, schemas
from app.api import get_session
from app.db import create_session_factory
from app.main import app

BACKEND = Path(__file__).resolve().parents[1]


@pytest.fixture
def migration_case(test_database_url):
    """Run the revision against an isolated pre-change table, then roll back."""
    _, engine = create_session_factory(test_database_url)
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "migrations"))
    migration = ScriptDirectory.from_config(config).get_revision("0013_poi_nullable_name").module
    assert migration.down_revision == "0012_profile_commute"
    schema = f"poi_name_test_{uuid4().hex}"
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                connection.execute(text(f'CREATE SCHEMA "{schema}"'))
                connection.execute(text(f'SET LOCAL search_path TO "{schema}", public'))
                connection.execute(text("CREATE TABLE pois (id integer PRIMARY KEY, name varchar(200) NOT NULL, category text NOT NULL)"))
                connection.execute(text("INSERT INTO pois VALUES (1, :name, 'school')"), {"name": "Школа №1"})
                with Operations.context(MigrationContext.configure(connection)):
                    yield connection, migration, schema
            finally:
                transaction.rollback()
    finally:
        engine.dispose()


@pytest.mark.integration
def test_name_migration_roundtrip_preserves_named_records(migration_case):
    connection, migration, schema = migration_case
    before_columns = inspect(connection).get_columns("pois", schema=schema)
    before_rows = connection.execute(text("SELECT * FROM pois ORDER BY id")).all()
    assert next(c for c in before_columns if c["name"] == "name")["nullable"] is False

    migration.upgrade()
    after_columns = inspect(connection).get_columns("pois", schema=schema)
    for before, after in zip(before_columns, after_columns, strict=True):
        assert str(before["type"]) == str(after["type"])
        assert before["name"] == after["name"] and before["default"] == after["default"]
        assert after["nullable"] == (True if after["name"] == "name" else before["nullable"])
    assert connection.execute(text("SELECT * FROM pois ORDER BY id")).all() == before_rows

    migration.downgrade()
    assert next(c for c in inspect(connection).get_columns("pois", schema=schema) if c["name"] == "name")["nullable"] is False
    assert connection.execute(text("SELECT * FROM pois ORDER BY id")).all() == before_rows
    migration.upgrade()
    assert next(c for c in inspect(connection).get_columns("pois", schema=schema) if c["name"] == "name")["nullable"] is True


@pytest.mark.integration
def test_downgrade_with_null_names_fails_without_backfill(migration_case):
    connection, migration, schema = migration_case
    migration.upgrade()
    connection.execute(text("INSERT INTO pois VALUES (2, NULL, 'bus_stop')"))
    with pytest.raises(IntegrityError):
        with connection.begin_nested():
            migration.downgrade()
    assert connection.execute(text("SELECT id, name FROM pois ORDER BY id")).all() == [(1, "Школа №1"), (2, None)]
    assert next(c for c in inspect(connection).get_columns("pois", schema=schema) if c["name"] == "name")["nullable"] is True


@pytest.mark.integration
@pytest.mark.parametrize("synthetic", [False, True])
def test_nullable_poi_orm_schema_and_api(test_database_url, synthetic):
    _, engine = create_session_factory(test_database_url)
    source = dict(source_id=f"poi-contract-{uuid4().hex}", source_type="test",
                  source_version="v1", fetched_at=datetime.now(timezone.utc), is_synthetic=synthetic)
    previous_override = app.dependency_overrides.get(get_session)
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                name_column = next(c for c in inspect(connection).get_columns("pois") if c["name"] == "name")
                assert name_column["nullable"] is True and str(name_column["type"]) == "VARCHAR(200)"
                with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
                    records = [models.POI(name=name, category="bus_stop",
                        location=WKTElement("POINT(92.85 56.01)", srid=4326), **source)
                        for name in (None, "Остановка")]
                    session.add_all(records)
                    session.commit()
                    ids = [record.id for record in records]
                    session.expunge_all()
                    reread = [session.get(models.POI, id_) for id_ in ids]
                    assert [record.name for record in reread] == [None, "Остановка"]
                    assert all(record.is_synthetic is synthetic for record in reread)

                def override_session():
                    with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
                        yield session

                app.dependency_overrides[get_session] = override_session
                with TestClient(app) as client:
                    response = client.get("/api/poi", params={"source_id": source["source_id"]})
                assert response.status_code == 200, response.text
                payload = response.json()
                assert [record["name"] for record in payload] == [None, "Остановка"]
                assert [record["id"] for record in payload] == ids
                assert all(record["is_synthetic"] is synthetic for record in payload)
                for name in (None, "Остановка"):
                    contract = schemas.POI(name=name, category="bus_stop",
                        location={"longitude": 92.85, "latitude": 56.01}, **source)
                    assert contract.model_dump(mode="json")["name"] == name
            finally:
                transaction.rollback()
    finally:
        if previous_override is None:
            app.dependency_overrides.pop(get_session, None)
        else:
            app.dependency_overrides[get_session] = previous_override
        engine.dispose()


@pytest.mark.integration
def test_legacy_osm_fixture_counts_are_unchanged(legacy_test_database_url):
    fixture = json.loads((BACKEND / "data/fixtures/osm/poi.json").read_text(encoding="utf-8"))
    expected = Counter(bus_stop=1318, school=160, kindergarten=262, clinic=114, hospital=75, park=59)
    assert Counter(e["tags"].get("amenity") or e["tags"].get("leisure") or e["tags"].get("highway")
                   for e in fixture["elements"]) == expected
    _, engine = create_session_factory(legacy_test_database_url)
    try:
        with Session(engine) as session:
            rows = session.scalars(select(models.POI).where(models.POI.source_id == "osm", models.POI.is_synthetic.is_(False))).all()
            assert Counter(row.category for row in rows) == expected
            assert all(row.name is not None for row in rows)
    finally:
        engine.dispose()
