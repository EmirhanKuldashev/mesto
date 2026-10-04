"""Separate market facts and descriptive affordability on real PostGIS."""

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from geoalchemy2.elements import WKTElement
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models
from app.ai.service import build_context
from app.analytics.scoring.calculators import DistrictFacts, MarketCalculator
from app.analytics.service import AnalyticsService
from app.api import get_session
from app.db import create_session_factory
from app.main import app
from app.market.models import MarketAssessment, MarketContext
from app.market.service import MarketService, assess_sample, summarize_observations
from app.recommendations.service import RecommendationService

DATE = datetime(2026, 9, 27, tzinfo=timezone.utc)


def sample(prices):
    return summarize_observations(7, [SimpleNamespace(price_from=price, fetched_at=DATE,
        source_id="cian", source_version="snapshot-v1") for price in prices])


def assessment(prices, budget=Decimal("8000000"), goal="buy"):
    return assess_sample(sample(prices), housing_goal=goal, purchase_budget=budget, rent_budget=Decimal("30000"))


@pytest.mark.parametrize("budget,count,status", [(Decimal("8000000"), 2, "known_value"),
                                               (Decimal("3000000"), 0, "known_zero")])
def test_positive_and_zero_matches_are_descriptive(budget, count, status):
    result = assessment([Decimal("4000000"), Decimal("8000000"), Decimal("12000000"), None], budget)
    context, purchase = result.market_context, result.affordability.purchase
    assert (context.observed_count, context.known_price_count, context.unknown_price_count) == (4, 3, 1)
    assert (context.min_starting_price, context.median_starting_price, context.max_starting_price) == (4000000, 8000000, 12000000)
    assert purchase.status == status and purchase.within_budget_count == count
    assert purchase.within_budget_share == count / 3
    assert purchase.budget_to_median_ratio == float(budget / Decimal("8000000"))
    assert purchase.ranking_eligible is False and "score" not in purchase.model_dump()
    assert purchase.sample_metadata.source_version == ["snapshot-v1"]


@pytest.mark.parametrize("prices", [[], [None], [None, Decimal("0"), Decimal("-1")],
                                    [Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")]])
def test_no_usable_prices_remain_unknown_not_zero(prices):
    result = assessment(prices)
    assert result.market_context.known_price_count == 0
    assert result.market_context.unknown_price_count == len(prices)
    assert result.market_context.min_starting_price is None
    assert result.market_context.median_starting_price is None
    assert result.market_context.max_starting_price is None
    purchase = result.affordability.purchase
    assert (purchase.status, purchase.reason_code) == ("unknown", "no_observations")
    assert purchase.within_budget_count is purchase.within_budget_share is purchase.budget_to_median_ratio is None


def test_budget_missing_keeps_nonpersonal_context():
    result = assessment([Decimal("4000000"), None], budget=None)
    assert result.market_context.min_starting_price == 4000000
    purchase = result.affordability.purchase
    assert (purchase.status, purchase.reason_code) == ("unknown", "budget_missing")
    assert purchase.within_budget_count is purchase.within_budget_share is purchase.budget_to_median_ratio is None


def test_snapshot_range_is_record_provenance_not_price_history():
    earlier = datetime(2026, 9, 1, tzinfo=timezone.utc)
    sample_data = summarize_observations(7, [
        SimpleNamespace(price_from=Decimal("5000000"), fetched_at=earlier, source_id="cian", source_version="v1"),
        SimpleNamespace(price_from=None, fetched_at=DATE, source_id="cian", source_version="v2"),
    ])
    assert sample_data.context.snapshot_date_from == earlier
    assert sample_data.context.snapshot_date_to == DATE
    assert sample_data.context.source_version == ["v1", "v2"]
    assert sample_data.context.unknown_price_count == 1


@pytest.mark.parametrize("size", [1, 3, 30])
def test_sample_sizes_remain_descriptive(size):
    purchase = assessment([Decimal("4000000")] * size).affordability.purchase
    assert purchase.within_budget_count == size and purchase.within_budget_share == 1
    assert purchase.ranking_eligible is False
    if size == 1:
        assert any("одного ЖК" in limitation for limitation in purchase.limitations)
    if size == 3:
        assert any("малой выборкой" in limitation for limitation in purchase.limitations)


@pytest.mark.parametrize("goal,purchase_status,rent_status", [
    ("buy", "known_value", "not_applicable"), ("rent", "not_applicable", "unknown"), ("compare", "known_value", "unknown"),
])
def test_purchase_and_rent_are_independent(goal, purchase_status, rent_status):
    result = assessment([Decimal("4000000")], goal=goal)
    assert result.affordability.purchase.status == purchase_status
    rent = result.affordability.rent
    assert rent.status == rent_status and rent.within_budget_count is rent.within_budget_share is None
    assert rent.observed_count == rent.known_price_count == rent.unknown_price_count == 0
    assert rent.observation_unit == "listing" and rent.price_basis == "monthly_rent"
    if goal != "buy":
        assert rent.reason_code == "no_observations"
    assert set(result.affordability.model_dump()) == {"purchase", "rent"}


@pytest.mark.parametrize("goal,sale,rent,buy_budget,rent_budget,expected", [
    ("buy", [8000000], [], 8000000, None, 75),
    ("buy", [6000000], [], 8000000, None, 100),
    ("compare", [8000000], [60000], 8000000, 30000, 56.25),
    ("rent", [8000000], [], None, 30000, None),
])
def test_legacy_market_formula_remains_unchanged(goal, sale, rent, buy_budget, rent_budget, expected):
    assert MarketCalculator().calculate(DistrictFacts(None, sale_prices=sale, rent_prices=rent),
        goal=goal, purchase_budget=buy_budget, rent_budget=rent_budget) == expected


@pytest.fixture
def market_case(test_database_url):
    _, engine = create_session_factory(test_database_url)
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
                    source = dict(source_id="market-test", source_type="real_estate_portal", source_version="v1",
                                  fetched_at=DATE, is_synthetic=False)
                    district = models.District(name="Market control", population=10000, **source)
                    other = models.District(name="Other market control", population=10000, **source)
                    synthetic = models.District(name="Synthetic market", **{**source, "is_synthetic": True})
                    synthetic_type = models.District(name="Synthetic type market", **{**source, "source_type": "synthetic"})
                    session.add_all([district, other, synthetic, synthetic_type]); session.flush()
                    for index, price in enumerate((Decimal("4000000"), Decimal("8000000"), Decimal("12000000"), None, Decimal("0"), Decimal("-1"))):
                        session.add(models.ResidentialComplex(name=f"Real control {index}", district_id=district.id, price_from=price, **source))
                    for values in ({"is_synthetic": True}, {"source_type": "synthetic"},
                                   {"source_id": "synthetic-hidden", "source_type": "real_estate_portal"}):
                        session.add(models.ResidentialComplex(name="Excluded demo", district_id=district.id, price_from=1, **{**source, **values}))
                    session.add(models.ResidentialComplex(name="Different district", district_id=other.id, price_from=1, **source))
                    session.add(models.ResidentialComplex(name="Unassigned", price_from=1, **source))
                    profile = models.UserProfile(housing_goal="buy", purchase_budget=Decimal("8000000"),
                        initial_payment=Decimal("1000000"), comfortable_monthly_payment=Decimal("50000"), data_processing_consent=True)
                    session.add(profile)
                    for category in ("school", "transport_stop"):
                        session.add(models.POI(name="Current evidence", category=category, district_id=district.id,
                            location=WKTElement("POINT(92.85 56.05)", srid=4326), **source))
                    session.add(models.ExternalSignal(district_id=district.id, source_type="government_plan", title="Plan",
                        category="education", impact_direction="positive", impact_value=25, confidence=1, is_demo=False))
                    session.flush()
                    yield session, district, other, synthetic, synthetic_type, profile
            finally:
                transaction.rollback()
    finally:
        engine.dispose()


@pytest.mark.integration
def test_service_filters_real_observations_and_preserves_unknowns(market_case):
    session, district, _, synthetic, synthetic_type, profile = market_case
    service = MarketService(session)
    context = service.context(district.id)
    assert (context.observed_count, context.known_price_count, context.unknown_price_count) == (6, 3, 3)
    assert context.min_starting_price == 4000000 and context.median_starting_price == 8000000 and context.max_starting_price == 12000000
    assert context.source == ["market-test"] and context.source_version == ["v1"]
    assert context.snapshot_date_from == context.snapshot_date_to == DATE
    assert any("не гарантируют дату конкретной цены" in line for line in context.limitations)
    before = service.assessment(profile.public_id, district.id)
    profile.initial_payment, profile.comfortable_monthly_payment = Decimal("7000000"), Decimal("1")
    session.flush()
    assert service.assessment(profile.public_id, district.id) == before
    app.dependency_overrides[get_session] = lambda: session
    try:
        with TestClient(app) as client:
            for rejected in (synthetic.id, synthetic_type.id, 2147483647):
                assert client.get(f"/api/market/districts/{rejected}").status_code == 404
    finally:
        app.dependency_overrides.clear()


@pytest.mark.integration
def test_public_context_and_personal_api_schema_consent_and_no_writes(market_case):
    session, district, _, _, _, profile = market_case
    snapshot_count = session.scalar(select(func.count()).select_from(models.DistrictScore))
    app.dependency_overrides[get_session] = lambda: session
    try:
        with TestClient(app) as client:
            public = client.get(f"/api/market/districts/{district.id}")
            assert public.status_code == 200 and public.headers["cache-control"] == "no-store"
            assert MarketContext.model_validate(public.json()).known_price_count == 3
            assert public.json()["median_starting_price"] == 8000000
            response = client.post("/api/market/affordability", json={"profile_id": str(profile.public_id), "district_id": district.id})
            assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
            result = MarketAssessment.model_validate(response.json())
            assert result.affordability.purchase.within_budget_count == 2
            assert response.json()["affordability"]["purchase"]["budget"] == 8000000
            assert client.post("/api/market/affordability", json={"profile_id": "bad", "district_id": 0}).status_code == 422
            assert client.post("/api/market/affordability", json={"profile_id": str(uuid4()), "district_id": district.id}).status_code == 404
            profile.purchase_budget = None; session.flush()
            missing = client.post("/api/market/affordability", json={"profile_id": str(profile.public_id), "district_id": district.id}).json()
            assert missing["affordability"]["purchase"]["reason_code"] == "budget_missing"
            assert missing["market_context"]["known_price_count"] == 3
            profile.data_processing_consent = False; session.flush()
            assert client.post("/api/market/affordability", json={"profile_id": str(profile.public_id), "district_id": district.id}).status_code == 403
    finally:
        app.dependency_overrides.clear()
    assert session.scalar(select(func.count()).select_from(models.DistrictScore)) == snapshot_count


@pytest.mark.integration
@pytest.mark.parametrize("with_legacy_offer", [False, True])
def test_affordability_does_not_enter_mesto_growth_or_recommendations(market_case, monkeypatch, with_legacy_offer):
    session, district, _, _, _, profile = market_case
    if with_legacy_offer:
        session.add(models.PropertyOffer(district_id=district.id, price=10000000, area_sqm=60,
            source_id="market-test", source_type="test", source_version="v1", fetched_at=DATE, is_synthetic=False))
        session.flush()
    analytics, market = AnalyticsService(session), MarketService(session)
    low = analytics.calculate(profile.public_id, [district.id])[0]
    low_affordability = market.assessment(profile.public_id, district.id)
    low_ranking = RecommendationService(session).recommend(profile.public_id)
    profile.purchase_budget = Decimal("16000000"); session.flush()
    high = analytics.calculate(profile.public_id, [district.id])[0]
    high_affordability = market.assessment(profile.public_id, district.id)
    assert low_affordability.market_context == high_affordability.market_context
    assert low_affordability.affordability.purchase.within_budget_count == 2
    assert high_affordability.affordability.purchase.within_budget_count == 3
    assert low.score is not None and low.score == high.score and low.current_score == high.current_score and low.confidence == high.confidence
    assert low.future_growth_score == high.future_growth_score == 25
    assert low.future_score == high.future_score
    if with_legacy_offer:
        assert low.categories.market == 60 and high.categories.market == 100  # Existing behavior, not replaced.
    high_ranking = RecommendationService(session).recommend(profile.public_id)
    def forbidden(*args, **kwargs):
        raise AssertionError("Recommendation must not consume the new market component")
    monkeypatch.setattr(MarketService, "assessment", forbidden)
    monkeypatch.setattr(MarketService, "context", forbidden)
    after = RecommendationService(session).recommend(profile.public_id)
    projection = lambda rows: [(row.district_id, row.rank, row.match_score, row.district_score, row.future_score) for row in rows]
    assert projection(after) == projection(high_ranking)
    assert analytics.calculate(profile.public_id, [district.id])[0] == high
    if not with_legacy_offer:
        assert projection(low_ranking) == projection(high_ranking)


@pytest.mark.integration
def test_ai_housing_uses_structured_starting_price_contract(market_case):
    session, district, _, _, _, profile = market_case
    context = build_context(session, profile.public_id, district.id)
    housing = context["district"]["housing"]
    assert housing["market_context"]["observed_count"] == 6
    assert housing["market_context"]["unknown_price_count"] == 3
    assert housing["market_context"]["price_basis"] == "starting_price"
    purchase = housing["affordability"]["purchase"]
    assert purchase["within_budget_count"] == 2 and purchase["ranking_eligible"] is False
    assert any("не вероятность" in line for line in context["limitations"])
    assert context["analytics"]["calculation_version"] == "objective-current-v1"
