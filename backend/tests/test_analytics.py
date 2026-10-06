"""Deterministic scoring and API-contract checks without a database."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.analytics.api import get_analytics_service
from app.analytics.models import DistrictScoreResponse
from app.analytics.future_growth.models import FutureFactor, FutureGrowthResult
from app.intelligence.impact import SignalImpact
from app.analytics.scoring.calculators import (
    DistrictFacts, InfrastructureCalculator, MarketCalculator,
    TransportCalculator, lifestyle_score,
)
from app.analytics.scoring.engine import ScoringEngine
from app.analytics.scoring.weights import ScoringWeights
from app.main import app


def test_engine_applies_weights_and_reports_coverage():
    engine = ScoringEngine(ScoringWeights(lifestyle=.1, infrastructure=.4, transport=.2,
                                          future_growth=.1, market=.2))
    result = engine.calculate({"lifestyle": 100, "infrastructure": 50, "transport": 0,
                               "future_growth": 100, "market": 50})
    assert result.total_score == 50
    assert result.coverage == 1
    partial = engine.calculate({"lifestyle": None, "infrastructure": 80, "transport": None,
                                "future_growth": None, "market": None})
    assert partial.total_score == 80
    assert partial.coverage == .4
    empty = engine.calculate(dict.fromkeys(engine.weights))
    assert empty.total_score is None and empty.coverage == 0
    with pytest.raises(ValueError):
        engine.calculate({"lifestyle": 110, "infrastructure": 50, "transport": 50,
                          "future_growth": 50, "market": 50})
    with pytest.raises(ValueError):
        ScoringWeights(lifestyle=.9).as_dict()


def test_calculators_use_area_when_population_is_unknown():
    facts = DistrictFacts(population=None, area_km2=10)
    facts.poi_counts.update({
        "education": 10, "healthcare": 4, "park": 2, "transport_stop": 60,
    })
    assert InfrastructureCalculator().calculate(facts) == 100
    assert TransportCalculator().calculate(facts) == 100


def test_calculators_use_recorded_facts_not_default_scores():
    facts = DistrictFacts(population=10000)
    assert InfrastructureCalculator().calculate(facts) is None
    assert TransportCalculator().calculate(facts) is None
    assert MarketCalculator().calculate(facts, goal="rent", purchase_budget=None, rent_budget=50000) is None
    facts.poi_counts.update({"education": 2, "healthcare": 3, "park": 1, "shop": 4,
                             "transport_stop": 3})
    facts.rent_prices.extend([40000, 60000])
    assert InfrastructureCalculator().calculate(facts) == 100
    assert TransportCalculator().calculate(facts) == 100
    assert MarketCalculator().calculate(facts, goal="rent", purchase_budget=None, rent_budget=50000) == 75
    categories = {"infrastructure": 100, "transport": 100, "future_growth": 50, "market": 75}
    lifestyle, unsupported = lifestyle_score({
        "education_weight": {"is_answered": True, "value": 80},
        "transport_weight": {"is_answered": True, "value": 20},
        "safety_weight": {"is_answered": True, "value": 90},
    }, categories)
    assert lifestyle == 100 and unsupported is True


def test_score_api_response_schema_and_input_validation():
    profile_id = uuid4()

    class FakeService:
        def score(self, received_profile_id, district_ids):
            assert received_profile_id == profile_id
            assert district_ids == [7]
            return [DistrictScoreResponse(
                id=9, district={"id": 7, "name": "Советский", "slug": "sovetsky"}, score=82,
                current_score=78, future_score=82, future_growth_score=80,
                future_factors=[FutureFactor(object_id=2, name="School", type="education", year=2028,
                    status="planned", impact={"education": 5}, reason="New school",
                    distance_km=0, confidence=.5, is_synthetic=True)],
                future_impacts={"education": 5},
                categories={"lifestyle": 80, "infrastructure": 90, "transport": 70,
                            "future_growth": 80, "market": 85}, confidence=.4,
                reasons=["В районе учтены остановки общественного транспорта"],
                warnings=["Нет данных для категорий: future_growth"],
                is_synthetic=True, calculation_version="future-signals-v3",
                created_at=datetime.now(timezone.utc))]

    app.dependency_overrides[get_analytics_service] = lambda: FakeService()
    try:
        client = TestClient(app)
        response = client.post("/api/analytics/score", json={"profile_id": str(profile_id), "district_ids": [7]})
        assert response.status_code == 200, response.text
        data = response.json()[0]
        assert data["district"] == {"id": 7, "name": "Советский", "slug": "sovetsky"}
        assert data["score"] == 82 and data["categories"]["future_growth"] == 80
        assert data["future_score"] == 82 and data["current_score"] == 78
        assert data["future_growth_score"] == 80 and data["future_factors"][0]["type"] == "education"
        assert data["confidence"] == .4 and data["is_synthetic"] is True
        assert data["reasons"] and data["warnings"] and data["id"] == 9
        assert client.post("/api/analytics/score", json={"profile_id": str(profile_id),
                    "district_ids": [7, 7]}).status_code == 422
        assert client.post("/api/analytics/score", json={"profile_id": str(profile_id),
                    "district_ids": []}).status_code == 422
    finally:
        app.dependency_overrides.clear()

@pytest.mark.integration
def test_score_api_persists_snapshot_with_postgis(test_database_url, alembic_heads):
    """Runs when MESTO_TEST_DATABASE_URL points to a migrated PostGIS database."""
    from sqlalchemy import text
    from sqlalchemy.orm import Session
    from app.api import get_session
    from app.db import create_session_factory
    from app.etl.seed import seed

    url = test_database_url
    _, engine = create_session_factory(url)
    connection = engine.connect()
    transaction = connection.begin()

    def override_session():
        with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        assert set(connection.scalars(text("SELECT version_num FROM alembic_version"))) == alembic_heads
        with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
            seed(session)
            session.commit()
        client = TestClient(app)
        created = client.post("/api/profile", json={
            "household_type": "single", "adults_count": 1, "children_count": 0,
            "children": [], "housing_goal": "rent", "rent_budget": 45000,
            "transport_preferences": ["public_transport"], "data_processing_consent": True,
            "preferences": {"transport_weight": {"value": 80, "is_answered": True,
                                                   "source": "user", "confidence": 1}},
        })
        assert created.status_code == 201, created.text
        # Explicit demo district: V2 never substitutes synthetic catalogue evidence.
        district_id = connection.scalar(text("SELECT id FROM districts WHERE is_synthetic ORDER BY id LIMIT 1"))
        response = client.post("/api/analytics/score", json={
            "profile_id": created.json()["id"], "district_ids": [district_id],
        })
        assert response.status_code == 200, response.text
        result = response.json()[0]
        assert result["district"]["id"] == district_id
        assert result["score"] is None
        assert result["current_score"] is None and result["future_score"] is None
        assert result["objective"]["availability"] == "UNAVAILABLE"
        assert result["future_factors"]
        assert result["objective"]["unavailable_reason"]
        assert result["confidence"] == 0 and result["is_synthetic"] is True
        stored = connection.execute(text("SELECT total_score, calculation_version FROM district_scores WHERE id=:id"),
                                    {"id": result["id"]}).one()
        assert stored.total_score is None and result["score"] is None
        assert stored.calculation_version == "objective-mesto-v2"
    finally:
        app.dependency_overrides.clear()
        transaction.rollback()
        connection.close()
        engine.dispose()


def test_service_calculates_and_saves_a_versioned_snapshot(monkeypatch):
    """Exercise the real orchestration with deterministic in-memory query results."""
    from decimal import Decimal
    from unittest.mock import Mock
    from app import models
    from app.analytics.service import LegacyAnalyticsService as AnalyticsService

    public_id = uuid4()
    profile = models.UserProfile(id=4, public_id=public_id, data_processing_consent=True,
                                 housing_goal="rent", rent_budget=Decimal("50000"))
    district = models.District(id=7, name="Советский", slug="sovetsky", population=10000,
                               is_synthetic=True)
    preferences = models.UserPreferences(user_profile_id=4, preference_values={
        "transport_weight": {"is_answered": True, "value": 80},
    })
    facts = DistrictFacts(population=10000, synthetic=True)
    facts.poi_counts.update({"education": 2, "healthcare": 3, "park": 1,
                             "shop": 4, "transport_stop": 3})
    facts.rent_prices.extend([40000, 60000])
    session = Mock()
    session.scalar.side_effect = [profile, preferences]
    session.scalars.return_value = [district]

    def assign_generated_values():
        row = session.add.call_args.args[0]
        row.id = 42
        row.created_at = datetime.now(timezone.utc)

    session.flush.side_effect = assign_generated_values
    service = AnalyticsService(session)
    monkeypatch.setattr(service, "_facts", lambda _: facts)
    monkeypatch.setattr(service.future, "calculate", lambda _: FutureGrowthResult(
        score=50, factors=[FutureFactor(object_id=2, name="School", type="education", year=2028,
            status="planned", impact={"education": 5}, reason="New school",
            distance_km=0, confidence=.5, is_synthetic=True)],
        category_impacts={"education": 5},
        signal_impacts=[SignalImpact(signal_id=3, source_type="government_plan",
            title="Plan", category="education", future_growth_impact=10,
            confidence=.5, is_demo=True)]))
    result = service.score(public_id, [7])[0]
    assert result.id == 42 and result.district.id == 7
    assert result.current_score == 100
    assert result.future_score == 100
    assert result.score == 100 and result.future_factors
    assert result.categories.market == 75
    assert result.categories.future_growth == 50
    assert result.external_signal_impacts[0].future_growth_impact == 10
    assert result.confidence == 1
    assert result.is_synthetic and any("синтетические" in warning for warning in result.warnings)
    saved = session.add.call_args.args[0]
    assert isinstance(saved, models.DistrictScore)
    assert saved.profile_id == 4 and saved.calculation_version == "objective-current-v1"
    assert saved.future_factors[-1]["kind"] == "external_signal"
    assert saved.future_factors[-1]["future_growth_impact"] == 10
    session.commit.assert_called_once()
