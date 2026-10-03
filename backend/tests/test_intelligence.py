"""External signals are bounded, explicit and never treated as current conditions."""

from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import models
from app.analytics.future_growth.calculator import FutureGrowthCalculator
from app.analytics.future_growth.service import FutureGrowthService
from app.analytics.explanation.generator import ExplanationGenerator
from app.analytics.scoring.calculators import DistrictFacts
from app.intelligence.api import get_intelligence_service
from app.intelligence.impact import SignalEvidence, SignalImpactCalculator
from app.intelligence.models import ExternalSignal
from app.intelligence.schemas import SignalResponse, SignalsResponse
from app.intelligence.service import IntelligenceService
from app.intelligence.sources import seed_demo_signals
from app.main import app


def signal(value: float = 20, *, district_id: int = 7, confidence: float = 1,
           is_demo: bool = False) -> SignalEvidence:
    return SignalEvidence(id=11, district_id=district_id, source_type="government_plan",
        title="Школа", category="education",
        impact_direction="positive" if value > 0 else "negative" if value < 0 else "neutral",
        impact_value=value, confidence=confidence, event_date=date(2028, 1, 1), is_demo=is_demo)


def test_external_signal_model_and_signed_impact():
    row = ExternalSignal(district_id=7, source_type="government_plan", title="Школа",
        category="education", impact_direction="positive", impact_value=Decimal("25"),
        confidence=Decimal("0.5"), is_demo=True)
    assert row.district_id == 7 and row.is_demo is True
    assert {constraint.name for constraint in ExternalSignal.__table__.constraints} >= {
        "ck_external_signals_impact_range", "ck_external_signals_confidence",
        "ck_external_signals_direction_value"}
    calculator = SignalImpactCalculator()
    impact = calculator.calculate(signal(20, confidence=.5, is_demo=True))
    assert impact.future_growth_impact == 10 and impact.is_demo is True
    assert calculator.calculate(signal(-30, confidence=.5)).future_growth_impact == -15
    assert calculator.calculate(signal(0)).future_growth_impact == 0
    with pytest.raises(ValueError):
        calculator.calculate(signal(101))
    with pytest.raises(ValueError):
        calculator.calculate(signal(20, confidence=1.2))


def test_future_growth_includes_only_linked_signals_and_clamps_negative_impact():
    calculator = FutureGrowthCalculator()
    empty = calculator.calculate(7, [], as_of=date(2026, 9, 27))
    positive = calculator.calculate(7, [], signals=[signal(25, confidence=.5), signal(60, district_id=8)],
                                    as_of=date(2026, 9, 27))
    negative = calculator.calculate(7, [], signals=[signal(-30)], as_of=date(2026, 9, 27))
    assert empty.score is None
    assert positive.score == 12.5 and len(positive.signal_impacts) == 1
    assert negative.score == 0 and negative.signal_impacts[0].future_growth_impact == -30


def test_future_growth_service_reads_persisted_signals_and_explains_demo():
    row = ExternalSignal(id=11, district_id=7, source_type="government_plan", title="Школа",
        category="education", impact_direction="positive", impact_value=Decimal("25"),
        confidence=Decimal("0.5"), is_demo=True, event_date=date(2028, 1, 1))
    session = Mock()
    session.execute.return_value = []
    session.scalars.return_value = [row]
    result = FutureGrowthService(session).calculate(models.District(id=7))
    assert result.score == 12.5 and result.signal_impacts[0].is_demo
    categories = {"lifestyle": None, "infrastructure": None, "transport": None,
                  "future_growth": result.score, "market": None}
    reasons, warnings = ExplanationGenerator().generate(categories, DistrictFacts(population=None),
        unsupported_preferences=False, future_result=result)
    assert reasons == []  # Future signals do not explain objective Current.
    assert any("демонстрационные" in warning for warning in warnings)


def test_read_only_signal_api_response():
    now = datetime.now(timezone.utc)

    class FakeService:
        def get_signals(self, district_id):
            assert district_id == 7
            return SignalsResponse(signals=[SignalResponse(id=11, district_id=7,
                source_type="government_plan", title="Строительство школы", description="Demo",
                category="education", impact_direction="positive", impact_value=25,
                impact="+25", future_growth_impact=12.5, confidence=.5,
                event_date=date(2028, 1, 1), is_demo=True, created_at=now)])

    app.dependency_overrides[get_intelligence_service] = lambda: FakeService()
    try:
        client = TestClient(app)
        response = client.get("/api/intelligence/signals/7")
        assert response.status_code == 200, response.text
        item = response.json()["signals"][0]
        assert item["title"] == "Строительство школы" and item["impact"] == "+25"
        assert item["future_growth_impact"] == 12.5 and item["is_demo"] is True
        assert client.get("/api/intelligence/signals/0").status_code == 422
    finally:
        app.dependency_overrides.clear()
def test_intelligence_service_maps_stored_record_and_checks_district():
    row = ExternalSignal(id=11, district_id=7, source_type="government_plan", title="Школа",
        description="Demo", category="education", impact_direction="positive",
        impact_value=Decimal("25"), confidence=Decimal("0.5"),
        is_demo=True, event_date=date(2028, 1, 1), created_at=datetime.now(timezone.utc))
    session = Mock()
    session.scalar.return_value = 7
    session.scalars.return_value.all.return_value = [row]
    result = IntelligenceService(session).get_signals(7)
    assert result.signals[0].impact == "+25"
    assert result.signals[0].future_growth_impact == 12.5
    session.scalar.return_value = None
    with pytest.raises(HTTPException) as error:
        IntelligenceService(session).get_signals(7)
    assert error.value.status_code == 404
def test_demo_signals_are_explicit_and_seed_idempotently():
    session = Mock()
    session.scalar.side_effect = [None, None, None, 1, 2, 3]
    assert seed_demo_signals(session, [7, 8, 9]) == 3
    assert session.add.call_count == 3
    assert all(call.args[0].is_demo is True for call in session.add.call_args_list)
    assert seed_demo_signals(session, [7, 8, 9]) == 3
    assert session.add.call_count == 3
