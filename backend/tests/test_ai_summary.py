"""AI provider failures, grounding boundaries and cache isolation."""
import json
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.ai import api, service
from app.ai.provider import OrcaConfig, generate_summary
from app.ai.service import SummaryRuntime, public_preferences
from app.api import get_session
from app.main import app

CONFIG = OrcaConfig("test-key", "https://api.orcarouter.ai/v1", "test-model")


def test_provider_sends_context_and_uses_server_credentials():
    context = {"district": {"name": "Советский"}, "questionnaire": {"purchase_budget": 8000000}}
    def handler(request):
        assert request.headers["authorization"] == "Bearer test-key"
        payload = json.loads(request.content)
        assert json.loads(payload["messages"][1]["content"]) == context
        assert payload["model"] == "test-model"
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": "Район соответствует вашим приоритетам."}}]})
    assert generate_summary(context, CONFIG, httpx.MockTransport(handler)).startswith("Район")


@pytest.mark.parametrize("status, expected", [(401, 502), (500, 502), (429, 429), (302, 502)])
def test_upstream_errors_never_expose_secrets(status, expected):
    def handler(request):
        return httpx.Response(status, text="secret-provider-body-test-key")
    with pytest.raises(HTTPException) as error:
        generate_summary({}, CONFIG, httpx.MockTransport(handler))
    assert error.value.status_code == expected
    assert "test-key" not in str(error.value.detail)


def test_timeout_and_truncated_model_output_are_errors():
    def timeout(request):
        raise httpx.ReadTimeout("secret", request=request)
    with pytest.raises(HTTPException) as error:
        generate_summary({}, CONFIG, httpx.MockTransport(timeout))
    assert error.value.status_code == 504
    def truncated(request):
        return httpx.Response(200, json={"choices": [{"finish_reason": "length", "message": {"content": "partial"}}]})
    with pytest.raises(HTTPException):
        generate_summary({}, CONFIG, httpx.MockTransport(truncated))


def test_cache_depends_on_profile_answers_district_data_and_model():
    runtime = SummaryRuntime()
    calls = []
    def generate(context, config):
        calls.append(context)
        return "Краткая сводка"
    profile = uuid4()
    context = {"budget": 5, "source_version": "v1"}
    assert runtime.generate(context, CONFIG, profile, 8, generate)["cached"] is False
    assert runtime.generate(context, CONFIG, profile, 8, generate)["cached"] is True
    for changed, owner, district in [({"budget": 6}, profile, 8), (context, uuid4(), 8), (context, profile, 9)]:
        assert runtime.generate(changed, CONFIG, owner, district, generate)["cached"] is False
    assert len(calls) == 4


def test_profile_context_omits_identifiers_and_coordinates():
    result = public_preferences({"name": "private", "id": "private-id", "purchase_budget": 5,
        "partner": {"name": "private", "work_point": {"latitude": 55}, "preferences": {"parks": 90}},
        "life_points": [{"name": "private address", "longitude": 90}]})
    serialized = json.dumps(result)
    assert "private" not in serialized and "latitude" not in serialized and "longitude" not in serialized
    assert result["purchase_budget"] == 5
    assert result["partner"]["preferences"] == {"parks": 90}


def test_consent_is_checked_before_any_provider_call(monkeypatch):
    monkeypatch.setattr(service, "find_profile", lambda *_: SimpleNamespace(data_processing_consent=False))
    with pytest.raises(HTTPException) as error:
        service.build_context(None, uuid4(), 8)
    assert error.value.status_code == 403


def test_rate_budget_and_configuration(monkeypatch):
    runtime = SummaryRuntime()
    profile = uuid4()
    for _ in range(20):
        runtime.check_rate(profile)
    with pytest.raises(HTTPException) as error:
        runtime.check_rate(profile)
    assert error.value.status_code == 429
    monkeypatch.delenv("ORCA_API_KEY", raising=False)
    with pytest.raises(HTTPException) as error:
        OrcaConfig.from_env()
    assert error.value.status_code == 503


def test_api_schema_and_invalid_identifiers(monkeypatch):
    profile = uuid4()
    monkeypatch.setenv("ORCA_API_KEY", "test-key")
    monkeypatch.setattr(api, "runtime", SummaryRuntime())
    monkeypatch.setattr(api, "build_context", lambda *_: {})
    monkeypatch.setattr(api.runtime, "generate", lambda *args: {"district_id": 8,
        "summary": "Сводка", "generated_at": "2026-09-27T00:00:00Z", "cached": False})
    app.dependency_overrides[get_session] = lambda: None
    try:
        with TestClient(app) as client:
            response = client.post('/api/ai/district-summary', json={"profile_id": str(profile), "district_id": 8})
            assert response.status_code == 200 and response.json()["summary"] == "Сводка"
            assert response.headers["cache-control"] == "no-store"
            assert client.post('/api/ai/district-summary', json={"profile_id": "bad", "district_id": 0}).status_code == 422
    finally:
        app.dependency_overrides.clear()

def test_free_access_denied_is_not_presented_as_retryable_throttling():
    def handler(request):
        return httpx.Response(429, json={"error": {"metadata": {"reason": "err_free_access_denied"}}})
    with pytest.raises(HTTPException) as error:
        generate_summary({}, CONFIG, httpx.MockTransport(handler))
    assert error.value.status_code == 503

@pytest.mark.integration
def test_database_context_keeps_commute_without_names_or_coordinates(test_database_url):
    from sqlalchemy import select
    from sqlalchemy.orm import Session
    from app import models
    from app.db import create_session_factory
    from app.profile_api import save_profile
    from app.profile_schemas import ProfileCreate
    from uuid import UUID
    url = test_database_url
    _, engine = create_session_factory(url)
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                with Session(bind=connection, join_transaction_mode='create_savepoint') as session:
                    district = session.scalar(select(models.District).where(
                        models.District.is_synthetic.is_(False), models.District.centroid.is_not(None)))
                    assert district is not None, "OSM test district with a centroid must be loaded"
                    profile = save_profile(ProfileCreate(name='private-name', housing_goal='buy',
                        purchase_budget=8000000, commute_minutes=30, data_processing_consent=True,
                        life_points=[{'owner_type':'primary_user','type':'work','name':'private-address',
                            'latitude':56.01,'longitude':92.85,'importance':8,'frequency_per_week':5}]), session)
                    context = service.build_context(session, UUID(profile['id']), district.id)
                    assert context['questionnaire']['commute_minutes'] == 30
                    assert context['questionnaire']['life_points'][0]['straight_line_distance_to_district_center_km'] is not None
                    serialized = json.dumps(context)
                    for private in ('private-name', 'private-address', 'latitude', 'longitude'):
                        assert private not in serialized
            finally:
                transaction.rollback()
    finally:
        engine.dispose()
