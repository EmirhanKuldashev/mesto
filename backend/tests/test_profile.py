"""Stage 3 profile validation and database-backed API behavior."""

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api import get_session
from app.db import create_session_factory
from app.main import app
from app.profile_schemas import ProfileCreate


@pytest.fixture
def client():
    url = os.getenv("MESTO_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set MESTO_TEST_DATABASE_URL for profile integration checks")
    _, engine = create_session_factory(url)
    connection = engine.connect()
    transaction = connection.begin()

    def override_session():
        with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        yield TestClient(app), connection
    finally:
        app.dependency_overrides.clear()
        transaction.rollback()
        connection.close()
        engine.dispose()


def base_profile(**changes):
    data = {"household_type": "single", "adults_count": 1, "children_count": 0,
            "children": [], "housing_goal": "rent", "rent_budget": 45000,
            "transport_preferences": ["public_transport"], "data_processing_consent": True}
    data.update(changes)
    return data


def test_validation_and_consent():
    with pytest.raises(ValueError):
        ProfileCreate.model_validate(base_profile(data_processing_consent=False))
    with pytest.raises(ValueError):
        ProfileCreate.model_validate(base_profile(rent_budget=0))
    with pytest.raises(ValueError):
        ProfileCreate.model_validate(base_profile(housing_goal="buy", purchase_budget=100,
                                                   initial_payment=101))
    with pytest.raises(ValueError):
        ProfileCreate.model_validate(base_profile(life_points=[{"type": "work", "name": "Office",
                                                    "latitude": 91, "longitude": 92.8}]))
    with pytest.raises(ValueError):
        ProfileCreate.model_validate(base_profile(life_points=[{"type": "work", "name": "Office",
                                                    "latitude": 56, "longitude": 92.8}]))
    with pytest.raises(ValueError):
        ProfileCreate.model_validate(base_profile(preferences={"parks_weight": {
            "value": 50, "is_answered": False, "source": "default", "confidence": 0}}))
    with pytest.raises(ValueError):
        ProfileCreate.model_validate(base_profile(preferences={"parks_weight": {
            "value": 90, "is_answered": True, "source": "default", "confidence": 1}}))


def test_single_family_couple_and_life_points(client):
    api, connection = client
    single = api.post("/api/profile", json=base_profile(name="Single"))
    assert single.status_code == 201, single.text
    single_data = single.json()
    assert single_data["household_type"] == "single"
    assert single_data["consent_at"]
    assert api.get(f"/api/profile/{single_data['id']}").json()["name"] == "Single"

    family = api.post("/api/profile", json=base_profile(
        household_type="family", adults_count=2, children_count=1, children=[{"age": 7}],
        name="Family", future_changes=["bigger_family"], home_values=["family_time", "calm"],
    ))
    assert family.status_code == 201, family.text
    assert family.json()["children"] == [{"age": 7}]

    couple = api.post("/api/couple/profile", json=base_profile(
        household_type="couple", adults_count=2, name="Maxim", housing_goal="compare",
        purchase_budget=12000000, initial_payment=3000000, rent_budget=55000,
        partner={"name": "Anna", "work_point": {"latitude": 56.04, "longitude": 93.01},
                 "transport_preferences": ["public_transport"],
                 "preferences": {"parks_weight": {"value": 90, "is_answered": True,
                                                   "source": "partner", "confidence": 1}},
                 "life_goals": ["green_environment"]},
        preferences={"parks_weight": {"value": 85, "is_answered": True,
                                       "source": "user", "confidence": 1}},
        life_points=[{"owner_type": "primary_user", "type": "work", "name": "Maxim work", "latitude": 56.01,
                      "longitude": 92.87, "importance": 10, "frequency_per_week": 5},
                     {"owner_type": "partner", "type": "partner_work", "name": "Anna work", "latitude": 56.04,
                      "longitude": 93.01, "importance": 9, "frequency_per_week": 5}],
    ))
    assert couple.status_code == 201, couple.text
    data = couple.json()
    assert data["partner"]["name"] == "Anna"
    assert data["partner"]["preferences"]["parks_weight"] == {"value": 90, "is_answered": True,
                                                               "source": "partner", "confidence": 1.0}
    assert data["partner"]["preferences"]["transport_weight"] == {"value": None, "is_answered": False,
                                                                   "source": "default", "confidence": 0}
    assert data["preferences"]["parks_weight"]["value"] == 85
    assert data["preferences"]["parks_weight"]["confidence"] == 1
    assert data["preferences"]["transport_weight"] == {"value": None, "is_answered": False,
                                                       "source": "default", "confidence": 0}
    assert data["preferences"]["price_vs_time"]["value"] is None
    assert data["life_points"][0]["frequency_per_week"] == 5
    assert data["life_points"][0]["longitude"] == pytest.approx(92.87)
    assert data["life_points"][0]["owner_type"] == "primary_user"
    assert data["life_points"][1]["owner_type"] == "partner"

    point = api.post("/api/life-points", json={"profile_id": data["id"], "owner_type": "primary_user", "type": "school",
                    "name": "School", "latitude": 56.02, "longitude": 92.9,
                    "importance": 10, "frequency_per_week": 5})
    assert point.status_code == 201, point.text
    moved = api.post("/api/life-points", json={"id": point.json()["id"], "profile_id": data["id"], "owner_type": "primary_user",
                    "type": "school", "name": "School", "latitude": 56.03,
                    "longitude": 92.91, "importance": 10, "frequency_per_week": 5})
    assert moved.status_code == 201, moved.text
    assert moved.json()["longitude"] == pytest.approx(92.91)
    assert len(api.get(f"/api/profile/{data['id']}").json()["life_points"]) == 3

    request = api.post("/api/analysis/request", json={"profile_id": data["id"]})
    assert request.status_code == 202, request.text
    assert request.json()["status"] == "pending"
    assert request.json()["life_points_snapshot"][2]["longitude"] == pytest.approx(92.91)
    assert len(request.json()["data_version_snapshot"]["sources"]) == 5
    assert request.json()["preferences_snapshot"]["parks_weight"]["value"] == 85
    assert all(request.json()[name] is None for name in ("user_score", "partner_score", "family_score"))

    connection.execute(text("UPDATE user_profiles SET data_processing_consent=false WHERE public_id=:id"), {"id": data["id"]})
    assert api.post("/api/analysis/request", json={"profile_id": data["id"]}).status_code == 403


def test_api_rejects_invalid_payload(client):
    api, connection = client
    assert api.post("/api/profile", json=base_profile(data_processing_consent=False)).status_code == 422
    assert api.post("/api/couple/profile", json=base_profile()).status_code == 422
    assert api.post("/api/profile", json=base_profile(rent_budget=-1)).status_code == 422
    profile = api.post("/api/profile", json=base_profile()).json()
    assert api.post("/api/life-points", json={"profile_id": profile["id"], "type": "work",
        "name": "No owner", "latitude": 56.0, "longitude": 93.0}).status_code == 422
    assert api.post("/api/life-points", json={"profile_id": profile["id"], "owner_type": "partner",
        "type": "work", "name": "No partner", "latitude": 56.0, "longitude": 93.0}).status_code == 422
    profile_id = connection.execute(text("SELECT id FROM user_profiles WHERE public_id=:id"), {"id": profile["id"]}).scalar_one()
    with pytest.raises(IntegrityError):
        with connection.begin_nested():
            connection.execute(text("""INSERT INTO life_points (user_profile_id, label, kind, location, visits_per_week, importance)
                VALUES (:id, 'orphan', 'other', ST_GeomFromText('POINT(93 56)', 4326), 1, 5)"""), {"id": profile_id})


def test_analysis_snapshot_is_immutable_after_life_point_change(client):
    api, connection = client
    created = api.post("/api/profile", json=base_profile(
        life_points=[{"owner_type": "primary_user", "type": "work", "name": "Office",
                      "latitude": 56.01, "longitude": 92.87}]))
    assert created.status_code == 201, created.text
    profile = created.json()
    request = api.post("/api/analysis/request", json={"profile_id": profile["id"]})
    assert request.status_code == 202, request.text
    request_id = request.json()["id"]
    original = request.json()["life_points_snapshot"][0]
    assert original["longitude"] == pytest.approx(92.87)
    changed = api.post("/api/life-points", json={"profile_id": profile["id"], "id": original["id"],
        "owner_type": "primary_user", "type": "work", "name": "New office",
        "latitude": 56.02, "longitude": 93.12})
    assert changed.status_code == 201, changed.text
    assert api.get(f"/api/profile/{profile['id']}").json()["life_points"][0]["longitude"] == pytest.approx(93.12)
    connection.execute(text("UPDATE user_profiles SET name='Changed' WHERE public_id=:id"), {"id": profile["id"]})
    stored = connection.execute(text("SELECT life_points_snapshot FROM analysis_requests WHERE id=:id"), {"id": request_id}).scalar_one()
    assert stored[0]["longitude"] == pytest.approx(92.87)
    assert stored[0]["name"] == "Office"
    stored_profile = connection.execute(text("SELECT profile_snapshot FROM analysis_requests WHERE id=:id"), {"id": request_id}).scalar_one()
    assert stored_profile["name"] is None
