"""Future-object impact rules and current/future score behavior."""

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from geoalchemy2.elements import WKTElement
from sqlalchemy.orm import Session

from app import models
from app.analytics.service import AnalyticsService
from app.db import create_session_factory

from app.analytics.future_growth.calculator import FutureGrowthCalculator
from app.analytics.future_growth.models import FutureObjectEvidence
from app.analytics.scoring.engine import ScoringEngine
from app.analytics.scoring.weights import ScoringWeights

AS_OF = date(2026, 9, 27)


def planned(category: str, *, district_id: int | None = 7, confidence: float | None = 1,
            distance_km: float | None = 0, year: int = 2028, status: str = "planned") -> FutureObjectEvidence:
    return FutureObjectEvidence(id=1, district_id=district_id, name=category, category=category,
                                status=status, planned_year=year, confidence=confidence,
                                distance_km=distance_km)


def test_school_increases_growth_score_and_exposes_education_family_infrastructure():
    calculator = FutureGrowthCalculator()
    empty = calculator.calculate(7, [], as_of=AS_OF)
    school = calculator.calculate(7, [planned("school")], as_of=AS_OF)
    assert empty.score is None
    assert school.score is not None and school.score > 0
    assert school.category_impacts["education"] > 0
    assert school.category_impacts["family"] > 0
    assert school.category_impacts["infrastructure"] > 0
    assert school.factors[0].year == 2028
    assert school.factors[0].reason


def test_road_adds_transport_potential_without_changing_current_transport():
    calculator = FutureGrowthCalculator()
    school = calculator.calculate(7, [planned("school")], as_of=AS_OF)
    with_road = calculator.calculate(7, [planned("school"), planned("road")], as_of=AS_OF)
    assert with_road.score > school.score
    assert with_road.category_impacts["transport"] > 0
    assert with_road.factors[1].impact["transport"] > 0


def test_orphan_distant_stale_or_unconfident_objects_do_not_raise_score():
    calculator = FutureGrowthCalculator()
    objects = [planned("school", district_id=None), planned("road", distance_km=6),
               planned("park", year=2024), planned("hospital", confidence=None)]
    result = calculator.calculate(7, objects, as_of=AS_OF)
    assert result.score is None
    assert result.factors == []
    assert any("confidence" in warning for warning in result.warnings)


def test_status_time_distance_and_confidence_reduce_impact():
    calculator = FutureGrowthCalculator()
    near = calculator.calculate(7, [planned("transport_stop", status="under_construction")], as_of=AS_OF)
    uncertain = calculator.calculate(7, [planned("transport_stop", confidence=.4, distance_km=4,
                                                year=2034, status="planned")], as_of=AS_OF)
    assert near.score > uncertain.score > 0
    assert near.category_impacts["transport"] > uncertain.category_impacts["transport"]


def test_configurable_future_weight_adds_uplift_to_current_score():
    weights = ScoringWeights(lifestyle=.3, infrastructure=.25, transport=.2,
                             future_growth=.15, market=.1)
    engine = ScoringEngine(weights)
    categories = {"lifestyle": 70, "infrastructure": 80, "transport": 60,
                  "future_growth": None, "market": 75}
    current, no_future = engine.calculate_outlook(categories)
    assert current is not None and no_future is None
    categories["future_growth"] = 80
    same_current, future = engine.calculate_outlook(categories)
    assert same_current == current
    assert future == round(current + .15 * 80, 2)


@pytest.fixture
def current_isolation_case(test_database_url):
    """Real current/future evidence in a rollback-only PostGIS transaction."""
    _, engine = create_session_factory(test_database_url)
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
                    source = dict(source_id="current-isolation-test", source_type="test",
                                  source_version="v1", fetched_at=datetime.now(timezone.utc),
                                  is_synthetic=False)
                    district = models.District(
                        name="Current isolation", population=20000,
                        geometry=WKTElement(
                            "MULTIPOLYGON(((92.8 56,92.9 56,92.9 56.1,92.8 56.1,92.8 56)))",
                            srid=4326), **source,
                    )
                    profile = models.UserProfile(
                        data_processing_consent=True, housing_goal="buy",
                        purchase_budget=Decimal("8000000"),
                    )
                    session.add_all([district, profile])
                    session.flush()
                    # At 20,000 residents these counts produce I=T=50.
                    for category, count in (("education", 2), ("healthcare", 3),
                                            ("park", 1), ("shop", 4), ("transport_stop", 3)):
                        for index in range(count):
                            session.add(models.POI(
                                name=f"{category} {index}", category=category,
                                district_id=district.id,
                                location=WKTElement("POINT(92.85 56.05)", srid=4326), **source,
                            ))
                    preferences = models.UserPreferences(
                        user_profile_id=profile.id, preference_values={},
                    )
                    session.add(preferences)
                    session.flush()
                    yield session, district, profile, preferences, source
            finally:
                transaction.rollback()
    finally:
        engine.dispose()


def _answer(value):
    return {"value": value, "is_answered": True, "source": "user", "confidence": 1}


def _add_growth_evidence(session, district, source, evidence_kind):
    source = {**source, "is_synthetic": evidence_kind.endswith("demo")}
    if evidence_kind.startswith("objects"):
        # Two approved schools saturate the unchanged future-growth formula.
        for index in range(2):
            session.add(models.FutureObject(
                name=f"Future school {index}", district_id=district.id,
                category="school", status="approved", planned_year=date.today().year + 1,
                confidence=Decimal("1"),
                location=WKTElement("POINT(92.85 56.05)", srid=4326), **source,
            ))
    else:
        session.add(models.ExternalSignal(
            district_id=district.id, source_type="government_plan", title="Future plan",
            category="education", impact_direction="positive", impact_value=Decimal("100"),
            confidence=Decimal("1"), is_demo=evidence_kind.endswith("demo"),
        ))
    session.flush()


def _current_projection(result, engine):
    categories = result.categories.model_dump()
    categories["future_growth"] = None
    # No separate Current coverage field exists in the public API.
    return result.current_score, result.score, categories, result.confidence, engine.calculate_current(categories).coverage


@pytest.mark.integration
@pytest.mark.parametrize("evidence_kind", ["objects", "signals", "objects_demo", "signals_demo"])
@pytest.mark.parametrize("with_current_preference", [False, True])
def test_future_evidence_cannot_change_current(current_isolation_case, evidence_kind,
                                             with_current_preference):
    session, district, profile, preferences, source = current_isolation_case
    answers = {"future_growth_weight": _answer(100)}
    if with_current_preference:
        answers["transport_weight"] = _answer(80)
    preferences.preference_values = answers
    session.flush()
    service = AnalyticsService(session)
    before = service.calculate(profile.public_id, [district.id])[0]
    _add_growth_evidence(session, district, source, evidence_kind)
    after = service.calculate(profile.public_id, [district.id])[0]

    assert before.current_score == after.current_score == 50
    assert _current_projection(before, service.engine) == _current_projection(after, service.engine)
    assert after.categories.lifestyle == (50 if with_current_preference else None)
    assert before.confidence == after.confidence == 1
    assert before.future_growth_score is None and before.future_score is None
    assert after.future_growth_score == after.categories.future_growth == 100
    assert after.future_score == 65 and before.score == after.score == 50
    if evidence_kind.startswith("objects"):
        assert len(after.future_factors) == 2
        assert all(factor.distance_km == 0 for factor in after.future_factors)
        assert after.future_impacts["education"] > 0
    else:
        assert after.external_signal_impacts[0].future_growth_impact == 100


@pytest.mark.integration
@pytest.mark.parametrize("evidence_kind", ["objects", "signals"])
def test_future_preference_cannot_change_current(current_isolation_case, evidence_kind):
    session, district, profile, preferences, source = current_isolation_case
    _add_growth_evidence(session, district, source, evidence_kind)
    service = AnalyticsService(session)
    baseline = service.calculate(profile.public_id, [district.id])[0]
    for value in (0, 100):
        preferences.preference_values = {"future_growth_weight": _answer(value)}
        session.flush()
        result = service.calculate(profile.public_id, [district.id])[0]
        assert _current_projection(result, service.engine) == _current_projection(baseline, service.engine)
        assert result.current_score == 50 and result.categories.lifestyle is None
        assert result.future_growth_score == 100 and result.future_score == 65 and result.score == 50
