"""Checks for Cian residential complex extraction and import."""

import json
import os
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import create_session_factory
from app.models import ResidentialComplex
from data.loaders.cian_complex_loader import CianComplex, load_cian_complexes
from scrapers.cian import extract_complex_details


def test_complex_details_accept_optional_map_parameters():
    html = ('<img src="https://api.cian.ru/map-preview/v1/get-map-preview/'
            '?latitude=56.0002&amp;longitude=92.9479&amp;size=M&amp;newbuildingId=5780222">'
            '<script>"minPrice":"5267760.00"</script>')
    assert extract_complex_details(html) == {
        "latitude": 56.0002, "longitude": 92.9479, "price_from": 5267760.0,
    }
    assert extract_complex_details("<html>no map or price</html>") == {
        "latitude": None, "longitude": None, "price_from": None,
    }


def test_complex_validation_requires_verified_identity_and_coordinate_pair():
    record = {
        "complex_id": "zhk-example-krasnoyarsk-i.cian.ru",
        "source": "cian",
        "url": "https://zhk-example-krasnoyarsk-i.cian.ru/",
        "name": "ЖК Пример",
        "city": "Красноярск",
        "latitude": 56.0,
        "longitude": 92.9,
        "price_from": 5000000,
        "parsed_at": "2026-09-27T00:00:00Z",
    }
    assert CianComplex.model_validate(record).complex_id == record["complex_id"]
    for change in ({"longitude": None}, {"city": "Москва"},
                   {"url": "https://zhk-other.cian.ru/"}, {"price_from": -1}):
        with pytest.raises(ValueError):
            CianComplex.model_validate({**record, **change})


def test_complex_loader_upserts_without_duplicates(tmp_path):
    url = os.getenv("MESTO_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set MESTO_TEST_DATABASE_URL for database integration checks")
    name = f"zhk-test-{uuid4().hex[:12]}-krasnoyarsk-i.cian.ru"
    record = {
        "complex_id": name, "source": "cian", "url": f"https://{name}/",
        "name": "ЖК Тест", "city": "Красноярск", "latitude": 56.0,
        "longitude": 92.9, "price_from": 5000000,
        "parsed_at": "2026-09-27T00:00:00Z",
    }
    path = tmp_path / "complexes.json"
    path.write_text(json.dumps([record], ensure_ascii=False), encoding="utf-8")
    _, engine = create_session_factory(url)
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
                    assert load_cian_complexes(session, path) == {"read": 1, "created": 1, "updated": 0}
                    session.flush()
                    query = select(ResidentialComplex).where(ResidentialComplex.external_id == name)
                    item = session.scalar(query)
                    assert item is not None and item.source_id == "cian"
                    assert item.is_synthetic is False
                    assert item.fetched_at is not None and item.source_version is not None
                    fetched_at = item.fetched_at
                    assert session.scalar(select(func.ST_Y(ResidentialComplex.location)).where(
                        ResidentialComplex.external_id == name)) == pytest.approx(56.0)
                    path.write_text(json.dumps([{**record, "price_from": 6200000}], ensure_ascii=False), encoding="utf-8")
                    assert load_cian_complexes(session, path) == {"read": 1, "created": 0, "updated": 1}
                    session.flush()
                    session.expire_all()
                    assert session.scalar(select(func.count()).select_from(ResidentialComplex).where(
                        ResidentialComplex.external_id == name)) == 1
                    updated = session.scalar(query)
                    assert int(updated.price_from) == 6200000
                    assert updated.fetched_at == fetched_at
            finally:
                transaction.rollback()
    finally:
        engine.dispose()
