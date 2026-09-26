"""Personal ranking and public API contract without a database."""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import Mock
from uuid import uuid4

from fastapi.testclient import TestClient

from app import models
from app.analytics.models import CategoryScores, DistrictScoreResponse
from app.main import app
from app.recommendations.api import get_recommendation_service
from app.recommendations.models import DistrictRecommendation, MatchProfile
from app.recommendations.ranking import personal_match
from app.recommendations.service import RecommendationService


def score(district_id: int, name: str, *, infrastructure: float,
          transport: float, future_growth: float) -> DistrictScoreResponse:
    return DistrictScoreResponse(
        id=district_id, district={"id": district_id, "name": name, "slug": None},
        score=75, current_score=72, future_score=75, future_growth_score=future_growth,
        future_factors=[], future_impacts={},
        categories=CategoryScores(lifestyle=70, infrastructure=infrastructure,
                                  transport=transport, future_growth=future_growth, market=70),
        confidence=.8, reasons=[], warnings=[], is_synthetic=False,
        calculation_version="future-v2", created_at=datetime.now(timezone.utc),
    )


def test_personal_match_adapts_to_family_and_work_priorities():
    family = MatchProfile(household_type="family", children_ages=(5,),
        preferences={"education_weight": {"value": 90, "is_answered": True}})
    commuter = MatchProfile(household_type="single", life_point_kinds=("work",), work_point_priority=1.0,
        preferences={"transport_weight": {"value": 100, "is_answered": True}})
    school = score(1, "School district", infrastructure=95, transport=45, future_growth=40)
    transit = score(2, "Transit district", infrastructure=45, transport=95, future_growth=90)
    assert personal_match(school.categories, family).score > personal_match(transit.categories, family).score
    assert personal_match(transit.categories, commuter).score > personal_match(school.categories, commuter).score
    assert personal_match(school.categories, family).weights["infrastructure"] > \
        personal_match(school.categories, commuter).weights["infrastructure"]


def test_service_returns_ranked_districts_and_profile_specific_reasons():
    public_id = uuid4()
    profile = models.UserProfile(id=4, public_id=public_id, data_processing_consent=True,
        household_type="family", children=[{"age": 5}], housing_goal="buy",
        purchase_budget=Decimal("10000000"), planning_horizon="long_term",
        transport_preferences=["public_transport"], home_values=["district_growth"])
    preferences = models.UserPreferences(user_profile_id=4, preference_values={
        "education_weight": {"value": 90, "is_answered": True},
        "future_growth_weight": {"value": 80, "is_answered": True},
    })
    point = models.LifePoint(kind="school")
    session = Mock()
    session.scalar.side_effect = [profile, preferences]
    session.scalars.side_effect = [[point], [1, 2]]
    service = RecommendationService(session)
    service.analytics.score = Mock(return_value=[
        score(2, "Transit district", infrastructure=45, transport=95, future_growth=90),
        score(1, "School district", infrastructure=95, transport=45, future_growth=40),
    ])
    result = service.recommend(public_id)
    assert [item.district_id for item in result] == [1, 2]
    assert [item.rank for item in result] == [1, 2]
    assert result[0].match_score > result[1].match_score
    assert result[0].profile_id == public_id and result[0].district_score == 75
    assert any("семейн" in reason for reason in result[0].reasons)
    assert any("Время в пути" in warning for warning in result[0].warnings)
    service.analytics.score.assert_called_once_with(public_id, [1, 2])


def test_api_returns_recommendation_schema():
    profile_id = uuid4()

    class FakeService:
        def recommend(self, received_id):
            assert received_id == profile_id
            return [DistrictRecommendation(district_id=7, district_name="Советский",
                profile_id=profile_id, match_score=91, district_score=87, future_score=94,
                rank=1, reasons=["Высокая оценка инфраструктуры"], warnings=[],
                created_at=datetime.now(timezone.utc))]

    app.dependency_overrides[get_recommendation_service] = lambda: FakeService()
    try:
        client = TestClient(app)
        response = client.post("/api/recommendations", json={"profile_id": str(profile_id)})
        assert response.status_code == 200, response.text
        data = response.json()["recommendations"][0]
        assert data["district_id"] == 7 and data["district_name"] == "Советский"
        assert data["match_score"] == 91 and data["rank"] == 1
        assert data["reasons"] and data["profile_id"] == str(profile_id)
        assert client.post("/api/recommendations", json={"profile_id": "invalid"}).status_code == 422
    finally:
        app.dependency_overrides.clear()
