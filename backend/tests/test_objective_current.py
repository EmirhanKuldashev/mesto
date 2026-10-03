"""Objective MESTO contract, using real district/profile evidence on PostGIS."""

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from geoalchemy2.elements import WKTElement
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.api import get_session
from app.ai.service import SummaryRuntime, build_context
from app.analytics.scoring.calculators import DistrictFacts, InfrastructureCalculator
from app.analytics.explanation.generator import ExplanationGenerator
from app.analytics.future_growth.models import FutureGrowthResult
from app.analytics.scoring.engine import ScoringEngine
from app.analytics.service import AnalyticsService
from app.analytics.models import DistrictScoreResponse
from app.db import create_session_factory
from app.main import app
from app.profile_api import save_profile
from app.profile_schemas import ProfileCreate
from app.recommendations.models import MatchProfile
from app.recommendations.ranking import personal_match


def answer(value):
    return {"value": value, "is_answered": True, "source": "user", "confidence": 1}


@pytest.fixture
def objective_case(test_database_url):
    _, engine = create_session_factory(test_database_url)
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
                    source = dict(source_id="objective-test", source_type="test", source_version="v1",
                                  fetched_at=datetime.now(timezone.utc), is_synthetic=False)
                    districts = []
                    for index, counts in enumerate((
                        {"school": 2, "kindergarten": 1, "clinic": 3, "hospital": 1,
                         "park": 1, "shop": 2, "transport_stop": 1},
                        {"school": 1, "clinic": 1, "shop": 1, "transport_stop": 2},
                    )):
                        district = models.District(
                            name=f"Objective control {index}", population=10000,
                            geometry=WKTElement("MULTIPOLYGON(((92.8 56,92.9 56,92.9 56.1,92.8 56.1,92.8 56)))", srid=4326),
                            **source,
                        )
                        session.add(district)
                        session.flush()
                        districts.append(district)
                        for category, count in counts.items():
                            for number in range(count):
                                session.add(models.POI(name=f"{category} {number}", category=category,
                                    district_id=district.id, location=WKTElement("POINT(92.85 56.05)", srid=4326), **source))
                        session.add(models.PropertyOffer(district_id=district.id, price=Decimal("10000000"),
                                    area_sqm=Decimal("65"), rooms=2, **source))
                        session.add(models.RentListing(district_id=district.id, monthly_rent=Decimal("60000"), **source))
                    profiles = []
                    for values in (
                        dict(household_type="family", adults_count=2, children_count=2,
                             children=[{"age": 4}, {"age": 12}], purchase_budget=18000000,
                             preferences={"education_weight": answer(90), "parks_weight": answer(90)}),
                        dict(household_type="single", housing_goal="rent", rent_budget=60000,
                             transport_preferences=["walking"], preferences={"shopping_weight": answer(100)}),
                        dict(household_type="single", purchase_budget=1000000, planning_horizon="long_term",
                             preferences={"housing_price_weight": answer(100), "future_growth_weight": answer(100)}),
                        dict(household_type="single", purchase_budget=8000000, commute_minutes=30,
                             transport_preferences=["public_transport"], preferences={"transport_weight": answer(100)},
                             life_points=[dict(owner_type="primary_user", type="work", name="Test work",
                                               latitude=56.01, longitude=92.85, importance=8, frequency_per_week=5)]),
                    ):
                        values.setdefault("housing_goal", "buy")
                        saved = save_profile(ProfileCreate(data_processing_consent=True, **values), session)
                        profiles.append(session.scalar(select(models.UserProfile).where(
                            models.UserProfile.public_id == UUID(saved["id"]))))
                    yield session, districts, profiles
            finally:
                transaction.rollback()
    finally:
        engine.dispose()


def projection(results):
    return [(row.score, row.current_score, row.confidence,
             row.categories.infrastructure, row.categories.transport) for row in results]


@pytest.mark.integration
def test_mesto_is_equal_for_family_urban_price_future_and_transit(objective_case):
    session, controls, profiles = objective_case
    district_ids = list(session.scalars(select(models.District.id).where(
        models.District.is_synthetic.is_(False)).order_by(models.District.id)))
    assert len(district_ids) == 9  # Seven bootstrap districts plus non-saturated controls.
    service = AnalyticsService(session)
    results = [service.calculate(profile.public_id, district_ids) for profile in profiles]
    assert all(projection(rows) == projection(results[0]) for rows in results[1:])
    for rows in results:
        for row in rows:
            assert row.score == row.current_score == round(
                (5 * row.categories.infrastructure + 4 * row.categories.transport) / 9, 2)
            assert row.confidence == 1
    # Personal evidence is still present and genuinely differs between profiles.
    control_index = district_ids.index(controls[0].id)
    categories = [rows[control_index].categories for rows in results]
    assert len({row.market for row in categories}) > 1
    assert len({row.lifestyle for row in categories}) > 1
    matches = [personal_match(row, MatchProfile(household_type="single", has_purchase_budget=True)).score for row in categories]
    assert all(value is not None for value in matches) and len(set(matches)) > 1


@pytest.mark.integration
@pytest.mark.parametrize("change", ["budget", "preferences", "children", "work_coordinate",
                                    "commute", "transport_mode", "future_preference", "housing_goal",
                                    "partner", "life_points"])
def test_individual_profile_changes_do_not_change_mesto(objective_case, change):
    session, districts, profiles = objective_case
    profile = profiles[3]
    preferences = session.scalar(select(models.UserPreferences).where(models.UserPreferences.user_profile_id == profile.id))
    point = session.scalar(select(models.LifePoint).where(models.LifePoint.user_profile_id == profile.id))
    if change == "future_preference":
        preferences.preference_values = {"future_growth_weight": answer(0)}
    session.flush()
    service = AnalyticsService(session)
    before = service.calculate(profile.public_id, [district.id for district in districts])
    if change == "budget":
        profile.purchase_budget = Decimal("1000000")
    elif change == "preferences":
        preferences.preference_values = {"education_weight": answer(100), "housing_price_weight": answer(100)}
    elif change == "children":
        profile.children = [{"age": 3}, {"age": 14}]
        profile.children_count = 2
        profile.household_type = "family"
    elif change == "work_coordinate":
        point.location = WKTElement("POINT(90 55)", srid=4326)
    elif change == "commute":
        profile.commute_minutes = 120
    elif change == "transport_mode":
        profile.transport_preferences = ["car"]
        profile.car_availability = True
    elif change == "future_preference":
        preferences.preference_values = {"future_growth_weight": answer(100)}
    elif change == "housing_goal":
        profile.housing_goal = "rent"
        profile.rent_budget = Decimal("20000")
    elif change == "partner":
        session.add(models.PartnerProfile(user_profile_id=profile.id, name="Test partner", work_location=WKTElement("POINT(91 55)", srid=4326),
                    preferences={"transport_weight": answer(100)}, transport_preferences=["walking"]))
    elif change == "life_points":
        point.kind, point.importance, point.visits_per_week = "school", 10, 7
    session.flush()
    after = service.calculate(profile.public_id, [district.id for district in districts])
    assert projection(after) == projection(before)
    if change in ("budget", "housing_goal"):
        assert after[0].categories.market != before[0].categories.market


@pytest.mark.parametrize("infrastructure,transport,coverage", [(None, 60, .5), (80, None, .5), (None, None, 0)])
def test_missing_required_component_never_becomes_full_mesto(infrastructure, transport, coverage):
    engine = ScoringEngine()
    categories = dict(infrastructure=infrastructure, transport=transport, market=100, lifestyle=100, future_growth=100)
    current = engine.calculate_current(categories)
    assert current.total_score is None and current.coverage == coverage
    assert engine.calculate_outlook(categories) == (None, None)


@pytest.mark.parametrize("infrastructure,transport", [(0, 0), (80, 60), (12.34, 98.76), (100, 100)])
def test_mesto_formula_uses_only_fixed_territorial_weights(infrastructure, transport):
    result = ScoringEngine().calculate_current(dict(infrastructure=infrastructure, transport=transport))
    assert result.total_score == round((5 * infrastructure + 4 * transport) / 9, 2)
    assert result.coverage == 1


def test_mesto_explanations_only_describe_objective_components():
    categories = dict(infrastructure=50, transport=50, lifestyle=100, market=100, future_growth=100)
    reasons, warnings = ExplanationGenerator().generate(categories, DistrictFacts(population=10000),
        unsupported_preferences=True, future_result=FutureGrowthResult(score=100))
    assert reasons == []
    assert not any("профиля" in text or "бюджет" in text or "Нет данных" in text for text in warnings)
    assert any("proxy-порогов" in text for text in warnings)


@pytest.mark.integration
def test_raw_infrastructure_components_are_preserved(objective_case):
    session, districts, _ = objective_case
    service = AnalyticsService(session)
    facts = service._facts(districts[0])
    assert facts.raw_poi_counts == {"school": 2, "kindergarten": 1, "clinic": 3,
                                   "hospital": 1, "park": 1, "shop": 2, "transport_stop": 1}
    assert service.infrastructure.components(facts) == dict(education=100, healthcare=100, parks=100, shopping=50)
    assert service.infrastructure.calculate(facts) == 87.5
    area_facts = DistrictFacts(population=None, area_km2=10)
    area_facts.poi_counts.update(education=5, healthcare=2, park=1)
    assert InfrastructureCalculator().components(area_facts) == dict(education=50, healthcare=50, parks=pytest.approx(66.6666667))
    assert InfrastructureCalculator().calculate(area_facts) == 55.56


@pytest.mark.integration
def test_unavailable_mesto_growth_and_old_snapshots_are_independent(objective_case):
    session, districts, profiles = objective_case
    district, profile = districts[0], profiles[0]
    old = models.DistrictScore(profile_id=profile.id, district_id=district.id, total_score=17,
                              confidence=.25, calculation_version="future-signals-v4", is_synthetic=False)
    session.add(old)
    session.flush()
    old_id = old.id
    district.population = None
    session.add(models.ExternalSignal(district_id=district.id, source_type="government_plan", title="Future plan",
                category="education", impact_direction="positive", impact_value=25, confidence=1, is_demo=False))
    session.flush()
    app.dependency_overrides[get_session] = lambda: session
    try:
        with TestClient(app) as client:
            response = client.post("/api/analytics/score", json={
                "profile_id": str(profile.public_id), "district_ids": [district.id],
            })
        assert response.status_code == 200, response.text
        assert response.json()[0]["score"] is None
        score = DistrictScoreResponse.model_validate(response.json()[0])
    finally:
        app.dependency_overrides.clear()
    assert score.score is None and score.current_score is None and score.future_score is None
    assert score.future_growth_score == score.categories.future_growth == 25
    assert score.confidence == 0 and score.calculation_version == "objective-current-v1"
    saved = session.get(models.DistrictScore, score.id)
    assert saved.total_score is None and saved.current_score is None and saved.confidence == 0
    previous = session.get(models.DistrictScore, old_id)
    assert previous.total_score == 17 and previous.confidence == Decimal(".25")
    assert previous.calculation_version == "future-signals-v4"
    match = personal_match(score.categories, MatchProfile(household_type="single", preferences={"future_growth_weight": answer(100)}))
    assert "future_growth" in match.used_categories and match.score is not None


@pytest.mark.integration
def test_ai_context_and_cache_preserve_methodology_semantics(objective_case):
    session, districts, profiles = objective_case
    context = build_context(session, profiles[0].public_id, districts[0].id)
    analytics = context["analytics"]
    assert analytics["score"] == analytics["current_score"]
    assert analytics["calculation_version"] == "objective-current-v1" and analytics["confidence"] == 1
    assert any("два" in line or "двух" in line for line in context["limitations"])
    runtime = SummaryRuntime()
    config = SimpleNamespace(model="test-model")
    generator = lambda *_: "Test summary"
    assert runtime.generate(context, config, profiles[0].public_id, districts[0].id, generator)["cached"] is False
    assert runtime.generate(context, config, profiles[0].public_id, districts[0].id, generator)["cached"] is True
    old_context = {**context, "analytics": {**analytics, "calculation_version": "future-signals-v4"}}
    assert runtime.generate(old_context, config, profiles[0].public_id, districts[0].id, generator)["cached"] is False
