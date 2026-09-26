"""Determinism checks and opt-in PostGIS integration checks."""

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text

from app import models
from app.db import create_session_factory
from app.etl.seed import ADAPTERS, seed
from app.main import app


def test_synthetic_source_is_deterministic():
    for adapter in ADAPTERS:
        assert list(adapter.fetch()) == list(adapter.fetch())
        assert adapter.source_type == "synthetic"
    assert [len(list(adapter.fetch())) for adapter in ADAPTERS] == [7, 250, 152, 20, 8]


@pytest.fixture
def database(monkeypatch):
    url = os.getenv("MESTO_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set MESTO_TEST_DATABASE_URL for PostGIS integration checks")
    monkeypatch.setattr("app.api.create_session_factory", lambda: create_session_factory(url))
    factory, engine = create_session_factory(url)
    try:
        yield factory, engine
    finally:
        engine.dispose()


def test_migration_seed_geometry_and_metadata(database):
    factory, engine = database
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0007_cian_offer_loader"
        assert connection.scalar(text("SELECT PostGIS_Version()"))
    with factory.begin() as session:
        first = seed(session)
        second = seed(session)
        assert first == second == {
            "synthetic-districts": 7, "synthetic-poi": 250, "synthetic-real-estate": 152,
            "synthetic-future": 20, "synthetic-mortgage": 8,
        }
        for model, count in ((models.District, 7), (models.POI, 250),
                             (models.ResidentialComplex, 12), (models.PropertyOffer, 60),
                             (models.RentListing, 80), (models.FutureObject, 20),
                             (models.MortgageProgram, 8)):
            assert session.scalar(select(func.count()).select_from(model).where(model.is_synthetic.is_(True))) == count
        assert session.scalar(select(func.ST_IsValid(models.District.geometry)).limit(1)) is True
        assert session.scalar(select(func.ST_SRID(models.POI.location)).limit(1)) == 4326
        assert session.scalar(select(func.ST_SRID(models.POI.geometry)).limit(1)) == 4326
        assert session.scalar(select(func.count()).select_from(models.DataQuality)) == 437
        assert sum(source.is_synthetic and source.source_type == "synthetic"
                   for source in session.scalars(select(models.DataSource))) == 5
        assert all(version.record_count for version in session.scalars(select(models.SourceVersion)))


def test_catalogue_api_and_filters(database):
    client = TestClient(app)
    counts = {"districts": 7, "poi": 250, "residential-complexes": 12,
              "properties": 60, "rent": 80, "future-objects": 20,
              "mortgage-programs": 8, "data-sources": 5}
    for path, count in counts.items():
        response = client.get(f"/api/{path}")
        assert response.status_code == 200, response.text
        if path in ("properties", "data-sources"):
            assert len(response.json()) >= count
        else:
            assert len(response.json()) == count
    district = client.get("/api/districts").json()[0]
    assert client.get(f"/api/districts/{district['id']}").json()["id"] == district["id"]
    assert len(client.get("/api/poi", params={"category": "park"}).json()) > 0
    assert len(client.get("/api/properties", params={"min_price": 100000000}).json()) == 0
    assert len(client.get("/api/poi", params={"bbox": "92.7,55.9,93.1,56.1"}).json()) > 0
    assert client.get("/api/poi", params={"bbox": "invalid"}).status_code == 422
    assert client.get("/api/districts/9999").status_code == 404
    assert all(item["is_synthetic"] and item["source_type"] == "synthetic"
               for item in client.get("/api/poi").json())
