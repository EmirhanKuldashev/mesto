"""Active V2, canonical parity, explicit historical replay and integration gates."""
import hashlib
import json
from decimal import Decimal
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select, text
from sqlalchemy.orm import Session

from app import models
from app.api import get_session
from app.analytics.objective.components import contracts
from app.analytics.objective.engine import WEIGHTS, ComponentScore, aggregate
from app.analytics.objective.provider import ARTIFACT_PATH, ARTIFACT_SHA256, ObjectiveProvider, read_precomputed
from app.analytics.service import AnalyticsService, LegacyAnalyticsService
from app.db import create_session_factory
from app.main import app
from app.recommendations.models import MatchProfile
from app.recommendations.ranking import personal_match

EXPECTED = {"osm-centralny": 59.22, "osm-kirovsky": 63.64, "osm-leninsky": 57.67,
            "osm-oktyabrsky": 45.58, "osm-sovetsky": 46.75, "osm-sverdlovsky": 41.50,
            "osm-zheleznodorozhny": 76.45}
RANK = ["osm-zheleznodorozhny", "osm-kirovsky", "osm-centralny", "osm-leninsky",
        "osm-sovetsky", "osm-oktyabrsky", "osm-sverdlovsky"]


def inputs(values=(10, 20, 30, 40, 50)):
    return {name: ComponentScore(score=value, normalization_version=ref.NORMALIZATION_VERSION,
        sampling_version=ref.SAMPLING_VERSION, evidence_version=m.EVIDENCE_VERSION,
        eligibility_version=m.ELIGIBILITY_VERSION, reference_id=ref.REFERENCE_ID,
        reference_checksum=ref.REFERENCE_SHA256) for (name, _, _, ref, m), value in zip(contracts(), values)}


def test_equal_formula_fixed_order_and_determinism():
    components = inputs()
    result = aggregate(components, provenance={"snapshot": "test"})
    assert dict(WEIGHTS) == dict.fromkeys(components, .20)
    assert result.score == 30 and result.coverage == 1
    assert result.weights == dict(WEIGHTS) and result.calculation_version == "objective-mesto-v2"
    assert result == aggregate(dict(reversed(list(components.items()))), provenance={"snapshot": "test"})
    assert result == aggregate(components, provenance={"snapshot": "test"})
    assert result.provenance == {"snapshot": "test"}
    for name, _, _, ref, m in contracts():
        c = result.components[name]
        assert (c.normalization_version,c.sampling_version,c.evidence_version,c.eligibility_version) == (
            ref.NORMALIZATION_VERSION,ref.SAMPLING_VERSION,m.EVIDENCE_VERSION,m.ELIGIBILITY_VERSION)


@pytest.mark.parametrize("name", tuple(WEIGHTS))
@pytest.mark.parametrize("missing", ["omitted", "null", "unavailable"])
def test_five_required_no_renormalization_or_zero(name, missing):
    components = inputs((100,100,100,100,100))
    if missing == "omitted":
        del components[name]
    elif missing == "null":
        components[name] = components[name].model_copy(update={"score": None})
    else:
        components[name] = components[name].model_copy(update={"unavailable_reason": "invalid_source"})
    result = aggregate(components)
    assert result.score is None and result.coverage == .8
    assert result.availability == "UNAVAILABLE" and name in result.unavailable_reason
    assert result.weights == dict(WEIGHTS)


def test_zero_is_valid_only_as_a_real_normalized_output():
    assert aggregate(inputs((0,0,0,0,0))).score == 0
    assert aggregate({}).score is None


@pytest.mark.parametrize("foreign", ["infrastructure", "transport", "lifestyle", "match", "market", "future_growth", "affordability"])
def test_foreign_categories_cannot_enter_aggregate(foreign):
    with pytest.raises(ValueError, match="canonical"):
        aggregate({**inputs(), foreign: next(iter(inputs().values()))})


def test_precomputed_contract_versions_pins_and_no_raw_public_arrays():
    artifact = read_precomputed()
    assert hashlib.sha256(ARTIFACT_PATH.read_bytes()).hexdigest() == ARTIFACT_SHA256
    assert set(artifact["districts"]) == set(EXPECTED)
    for slug,item in artifact["districts"].items():
        components = {}
        from app.analytics.objective.provider import component_score
        for name, model, _, ref, m in contracts():
            c = model.model_validate({**item["components"][name], "district_id": 999})
            assert c.reference_checksum == ref.REFERENCE_SHA256
            assert c.raw.snapshot.model_dump(mode="json") == artifact["snapshot"]
            assert c.raw.valid_evidence_count == c.raw.sample_count
            assert c.availability == "AVAILABLE"
            components[name] = component_score(c,m)
        result = aggregate(components)
        assert result.score == EXPECTED[slug]
        assert "distances_m" not in result.model_dump_json() and '"raw"' not in result.model_dump_json()


def test_corrupt_precomputed_fails_closed(tmp_path):
    path = tmp_path / "invalid.json"
    path.write_text("{}")
    with pytest.raises(ValueError, match="checksum"):
        read_precomputed(path)


@pytest.fixture
def session(test_database_url):
    _, engine = create_session_factory(test_database_url)
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                with Session(bind=connection, join_transaction_mode="create_savepoint") as s:
                    yield s
            finally:
                transaction.rollback()
    finally:
        engine.dispose()


def district_ids(session):
    return list(session.scalars(select(models.District.id).where(models.District.source_id == "osm")))


def profile(session):
    p = models.UserProfile(data_processing_consent=True,housing_goal="buy",purchase_budget=8000000)
    session.add(p); session.flush()
    return p


@pytest.mark.integration
def test_live_active_v2_ranking_no_legacy_calls_and_one_light_query(session, monkeypatch):
    ids = district_ids(session)
    queries = []
    conn = session.connection()
    capture = lambda *a: queries.append(a[2])
    event.listen(conn,"before_cursor_execute",capture)
    try:
        first = ObjectiveProvider(session).districts(ids)
    finally:
        event.remove(conn,"before_cursor_execute",capture)
    assert len(queries) == 1
    assert "ST_Distance" not in queries[0] and "generate_series" not in queries[0]
    assert first == ObjectiveProvider(session).districts(list(reversed(ids)))
    p = profile(session)
    service = AnalyticsService(session)
    def forbidden(*args, **kwargs):
        raise AssertionError("Active V2 must never calculate legacy current or spatial components")
    monkeypatch.setattr(service.engine,"calculate_current",forbidden)
    monkeypatch.setattr(service.engine,"calculate_outlook",forbidden)
    for _,_,cls,_,_ in contracts():
        monkeypatch.setattr(cls,"districts",forbidden)
    scores = service.calculate(p.public_id,ids)
    assert {s.district.slug:s.score for s in scores} == EXPECTED
    assert [s.district.slug for s in sorted(scores,key=lambda s:-s.score)] == RANK
    assert all(s.score == s.current_score == s.objective.score for s in scores)
    assert all(s.calculation_version == "objective-mesto-v2" and s.confidence == 1 for s in scores)
    assert scores == service.calculate(p.public_id,ids)


@pytest.mark.integration
def test_canonical_reproduction_every_component(session):
    """Full offline parity, including Parks; executed once, never on requests."""
    artifact = read_precomputed()
    ids = district_ids(session)
    slugs = dict(session.execute(select(models.District.id,models.District.slug).where(models.District.id.in_(ids))).all())
    for name, _, service, _, _ in contracts():
        for output in service(session,scope_id="krasnoyarsk").districts(ids):
            assert output.model_dump(mode="json",exclude={"district_id"}) == artifact["districts"][slugs[output.district_id]]["components"][name]


@pytest.mark.integration
@pytest.mark.parametrize("change", ["missing_dataset", "deleted_binding", "synthetic_poi", "poi_location", "geometry", "synthetic_district"])
def test_stale_or_invalid_source_never_uses_precomputed_or_legacy(session, change):
    ids = district_ids(session)
    assert ObjectiveProvider(session).districts(ids)[ids[0]].score is not None
    statements = {
        "missing_dataset": "UPDATE osm_datasets SET active_snapshot_id=NULL",
        "deleted_binding": "DELETE FROM osm_active_pois WHERE poi_id=(SELECT min(poi_id) FROM osm_active_pois)",
        "synthetic_poi": "UPDATE pois SET is_synthetic=true WHERE id=(SELECT min(poi_id) FROM osm_active_pois)",
        "poi_location": "UPDATE pois SET location=ST_SetSRID(ST_MakePoint(90,55),4326) WHERE id=(SELECT min(poi_id) FROM osm_active_pois)",
        "geometry": "UPDATE districts SET geometry=ST_Translate(geometry,.001,0) WHERE source_id='osm'",
        "synthetic_district": "UPDATE districts SET is_synthetic=true WHERE source_id='osm'",
    }
    session.execute(text(statements[change])); session.flush()
    result = ObjectiveProvider(session).districts(ids)[ids[0]]
    assert result.score is None and result.availability == "UNAVAILABLE" and result.unavailable_reason
    assert result.weights == dict(WEIGHTS) and result.coverage == 0


@pytest.mark.integration
@pytest.mark.parametrize("field,value", [("quality", {}), ("quality", {"quality_status":"INVALID"}),
    ("version", "unpublished-baseline"), ("canonical_checksum", "f"*64),
    ("query_hash", "f"*64), ("foundation_policy", "unknown-v2"), ("fingerprint", "0"*32)])
def test_adapter_rejects_unsupported_source_contract_without_mutating_sealed_history(session, field, value):
    from app.analytics.objective.provider import PARITY_QUERY
    ids = district_ids(session)
    rows = [dict(r) for r in session.execute(PARITY_QUERY,{"district_ids":ids}).mappings()]
    for r in rows:
        r[field] = value
    mocked = Mock()
    mocked.execute.return_value.mappings.return_value = rows
    assert all(r.score is None and r.unavailable_reason for r in ObjectiveProvider(mocked).districts(ids).values())


@pytest.mark.integration
def test_component_version_mismatch_is_unavailable_not_legacy(session, monkeypatch):
    import app.analytics.objective.provider as provider
    artifact = read_precomputed()
    for item in artifact["districts"].values():
        item["components"]["parks"]["normalization_version"] = "parks-unreviewed-v2"
    monkeypatch.setattr(provider,"read_precomputed",lambda:artifact)
    result = provider.ObjectiveProvider(session).districts(district_ids(session))
    assert all(r.score is None and r.coverage == .8 and "parks:component_version_or_contract_mismatch" in
               r.unavailable_reason for r in result.values())


@pytest.mark.integration
def test_legacy_and_synthetic_catalogue_are_unavailable(legacy_session, session):
    old = ObjectiveProvider(legacy_session).districts(district_ids(legacy_session))
    assert old and all(x.score is None for x in old.values())
    ids = list(session.scalars(select(models.District.id).where(models.District.is_synthetic)))
    assert ids and all(x.score is None for x in ObjectiveProvider(session).districts(ids).values())


@pytest.mark.integration
def test_v2_api_persists_provenance_without_rewriting_history(session):
    p = profile(session)
    ids = district_ids(session)
    historical = LegacyAnalyticsService(session).score(p.public_id,ids)
    before = [(r.id,r.score,r.calculation_version) for r in historical]
    app.dependency_overrides[get_session] = lambda: session
    try:
        with TestClient(app) as client:
            response = client.post('/api/analytics/score',json={"profile_id":str(p.public_id),"district_ids":ids})
        assert response.status_code == 200, response.text
        rows = response.json()
        assert {r['district']['slug']:r['score'] for r in rows} == EXPECTED
        for r in rows:
            stored = session.get(models.DistrictScore,r['id'])
            assert stored.objective_evidence == r['objective']
            assert stored.calculation_version == r['calculation_version'] == 'objective-mesto-v2'
            assert r['objective']['weights'] == dict(WEIGHTS)
            assert len(r['objective']['components']) == 5
            assert '"distances_m"' not in json.dumps(r)
        assert [(r.id,float(r.total_score),r.calculation_version) for r in (
            session.get(models.DistrictScore,r.id) for r in historical)] == before
        assert all(session.get(models.DistrictScore,r.id).objective_evidence is None for r in historical)
    finally:
        app.dependency_overrides.clear()


@pytest.mark.integration
def test_match_growth_market_affordability_and_personal_answers_are_independent(session):
    p = profile(session)
    ids = district_ids(session)
    v2 = AnalyticsService(session)
    legacy = LegacyAnalyticsService(session)
    first = v2.calculate(p.public_id,ids)
    old = legacy.calculate(p.public_id,ids)
    mp = MatchProfile(household_type="single",has_purchase_budget=True)
    assert [r.categories for r in first] == [r.categories for r in old]
    assert [personal_match(r.categories,mp) for r in first] == [personal_match(r.categories,mp) for r in old]
    assert [r.future_growth_score for r in first] == [r.future_growth_score for r in old]
    for budget in (1000000,20000000):
        p.purchase_budget = Decimal(budget)
        p.household_type = "family"; p.children = [{"age":4},{"age":12}]
        session.add(models.UserPreferences(user_profile_id=p.id,preference_values={})) if not session.scalar(
            select(models.UserPreferences).where(models.UserPreferences.user_profile_id==p.id)) else None
        session.flush()
        prefs = session.scalar(select(models.UserPreferences).where(models.UserPreferences.user_profile_id==p.id))
        prefs.preference_values = {"housing_price_weight":{"value":budget%100,"is_answered":True},
                                  "future_growth_weight":{"value":100,"is_answered":True}}
        session.flush()
        after = v2.calculate(p.public_id,ids)
        assert [r.objective for r in after] == [r.objective for r in first]
    session.add(models.ExternalSignal(district_id=ids[0],source_type="government_plan",title="Test plan",
        category="education",impact_direction="positive",impact_value=25,confidence=1,is_demo=True))
    session.flush()
    after = v2.calculate(p.public_id,ids)
    assert [r.objective for r in after] == [r.objective for r in first]
    assert after[0].future_growth_score == 25 and after[0].is_synthetic
    assert after[0].future_score == min(100,round(after[0].score+.15*25,2))
