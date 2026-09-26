"""CIAN RAW validation and database upsert checks."""

import json
import os
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import create_session_factory
from app.models import PropertyOffer
from data.loaders.cian_loader import CianListing, load_cian_json


def test_cian_listing_requires_importable_fields():
    base = {
        "listing_id": "123456789",
        "source": "cian",
        "url": "https://www.cian.ru/sale/flat/123456789/",
        "price": 4500000,
        "area": 42.5,
        "city": "Красноярск",
        "parsed_at": "2026-09-27T00:00:00Z",
    }
    assert CianListing.model_validate(base).listing_id == "123456789"
    for changed in ({"area": None}, {"price": "4500000"}, {"city": "Москва"},
                    {"url": "https://www.cian.ru/sale/flat/999/"}, {"listing_id": None}):
        with pytest.raises(ValueError):
            CianListing.model_validate({**base, **changed})


def test_cian_loader_upserts_without_duplicates(tmp_path):
    url = os.getenv("MESTO_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set MESTO_TEST_DATABASE_URL for database integration checks")

    listing_id = str(uuid4().int)[:15]
    record = {
        "listing_id": listing_id,
        "source": "cian",
        "url": f"https://www.cian.ru/sale/flat/{listing_id}/",
        "title": "Квартира",
        "price": 4500000,
        "rooms": 2,
        "area": 42.5,
        "floor": 3,
        "address": "Красноярск, ул. Ленина, 1",
        "city": "Красноярск",
        "parsed_at": "2026-09-27T00:00:00Z",
    }
    raw_path = tmp_path / "listings.json"
    raw_path.write_text(json.dumps([record, {**record, "area": None}, record]), encoding="utf-8")

    _, engine = create_session_factory(url)
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
                    first = load_cian_json(session, raw_path)
                    assert (first.read, first.created, first.updated, first.skipped) == (3, 1, 0, 2)
                    session.flush()
                    query = select(PropertyOffer).where(
                        PropertyOffer.source_id == "cian", PropertyOffer.external_id == listing_id)
                    offer = session.scalar(query)
                    assert offer is not None
                    assert (offer.source, offer.source_id, offer.external_id) == ("cian", "cian", listing_id)
                    assert offer.created_at is not None and offer.updated_at is not None
                    created_at = offer.created_at
                    old_updated_at = offer.updated_at

                    raw_path.write_text(json.dumps([{**record, "price": 4700000}]), encoding="utf-8")
                    second = load_cian_json(session, raw_path)
                    assert (second.read, second.created, second.updated, second.skipped) == (1, 0, 1, 0)
                    session.flush()
                    session.expire_all()
                    offers = session.scalars(query).all()
                    assert len(offers) == 1
                    assert int(offers[0].price) == 4700000
                    assert offers[0].created_at == created_at
                    assert offers[0].updated_at >= old_updated_at
            finally:
                transaction.rollback()
    finally:
        engine.dispose()
