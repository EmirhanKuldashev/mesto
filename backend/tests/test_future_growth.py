"""Future-object impact rules and current/future score behavior."""

from datetime import date

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
