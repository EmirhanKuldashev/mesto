"""Local point contracts and full canonical parity on migrated real PostGIS."""
import importlib
import json
import math
import statistics
import time
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import event, select, text
from sqlalchemy.orm import Session

from app import models
from app.analytics.api import get_local_service
from app.analytics.local.models import LocalComponent, LocalRequest, NearestObject
from app.analytics.local.service import LocalAnalyticsService, compose, unavailable_component
from app.analytics.objective.engine import WEIGHTS
from app.analytics.objective.provider import ObjectiveProvider, read_precomputed
from app.analytics.school.sampling import district_grid_250
from app.analytics.stop_availability.models import Coordinate
from app.db import create_session_factory
from app.main import app
from data.osm.park_geometry import read_geometry

POINT = LocalRequest(latitude=56.01, longitude=92.85)


def inputs(values=(10.123456, 20, 30, 40, 50)):
    result = {}
    for key, value in zip(WEIGHTS, values):
        category = "clinic" if key == "healthcare" else "bus_stop" if key == "stop_availability" else "park" if key == "parks" else key
        metadata = unavailable_component(key, "test").model_dump()
        result[key] = LocalComponent(**{**metadata, "available":True, "unavailable_reason":None,
            "score":value,"distance_m":100,"inside_geometry":False if key == "parks" else None,
            "nearest":NearestObject(osm_type="node",osm_id=1,name=None,category=category,distance_m=100)})
    return result


def test_full_precision_equal_formula_and_zero_valid():
    components = inputs()
    result = compose(POINT, components)
    assert result.version == "local-objective-v1" and result.availability == "AVAILABLE"
    assert result.score == math.fsum(.2*c.score for c in components.values())
    assert result.score != round(result.score, 2)
    assert result == compose(POINT, dict(reversed(list(components.items()))))
    assert result.weights == dict(WEIGHTS) and compose(POINT, inputs((0,)*5)).score == 0


@pytest.mark.parametrize("key", tuple(WEIGHTS))
@pytest.mark.parametrize("missing", ["omitted", "unavailable"])
def test_all_five_required_no_zero_or_renormalization(key, missing):
    components = inputs((100,)*5)
    if missing == "omitted":
        del components[key]
    else:
        components[key] = unavailable_component(key, "no_eligible_observations")
    result = compose(POINT, components)
    assert result.score is None and result.availability == "UNAVAILABLE"
    assert key in result.unavailable_reason and len(result.components) == 5
    assert result.weights == dict(WEIGHTS)


@pytest.mark.parametrize("key", ["market", "growth", "affordability", "transport", "infrastructure", "match"])
def test_foreign_layers_rejected(key):
    with pytest.raises(ValueError, match="canonical"):
        compose(POINT, {**inputs(),key:next(iter(inputs().values()))})


@pytest.mark.parametrize("changes", [{"latitude":91},{"latitude":-91},{"longitude":181},
    {"longitude":-181},{"latitude":None},{"latitude":True},{"longitude":"92.85"},
    {"latitude":float("nan")},{"longitude":float("inf")},{"profile_id":"forbidden"}])
def test_invalid_input(changes):
    with pytest.raises(ValidationError):
        LocalRequest.model_validate({**POINT.model_dump(),**changes})


def test_frozen_reference_reuse_and_monotonicity():
    service = LocalAnalyticsService(Mock())
    for ref, m, n, _ in service.contracts.values():
        assert n.failure_reason is None and n.reference.checksum == ref.REFERENCE_SHA256
        assert n.reference.contract.normalization_version == ref.NORMALIZATION_VERSION
        assert n.reference.contract.evidence_version == m.EVIDENCE_VERSION
        values = [n.distance_value(d) for d in (0,1,10,100,500,1000,100000)]
        assert values == sorted(values, reverse=True) and all(0 <= v <= 100 for v in values)
    parks = service.contracts["parks"][2]
    assert parks.distance_value(0) == 100*(1-171/(2*6065))


@pytest.mark.parametrize("key", tuple(WEIGHTS))
def test_corrupt_reference_is_unavailable_without_any_sql(key, monkeypatch, tmp_path):
    module = importlib.import_module(f"app.analytics.{key}.normalization")
    corrupt = tmp_path / "reference.json"
    corrupt.write_bytes(module.REFERENCE_PATH.read_bytes()+b" ")
    cls = module.PointNormalizer
    monkeypatch.setattr(module,"PointNormalizer",lambda:cls(reference_path=corrupt))
    session = Mock()
    result = LocalAnalyticsService(session).point(POINT)
    assert result.score is None and result.unavailable_reason == "reference_checksum_mismatch"
    session.execute.assert_not_called()


def test_api_invalid_input_and_contract_without_database():
    fake = Mock()
    fake.point.side_effect = lambda p:compose(p,inputs())
    app.dependency_overrides[get_local_service] = lambda:fake
    try:
        with TestClient(app) as client:
            for field,value in (("latitude",91),("longitude",181),("latitude",None),("longitude",True)):
                assert client.post('/api/analytics/local',json={**POINT.model_dump(),field:value}).status_code == 422
            response = client.post('/api/analytics/local',json=POINT.model_dump())
            assert response.status_code == 200
            body = response.json()
            assert body['version'] == 'local-objective-v1' and set(body['components']) == set(WEIGHTS)
            assert body['components']['school']['nearest']['name'] is None
            assert 'district_id' not in body and 'profile_id' not in body
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def session(test_database_url):
    _,engine = create_session_factory(test_database_url)
    try:
        with engine.connect() as connection:
            outer = connection.begin()
            try:
                with Session(bind=connection,join_transaction_mode="create_savepoint") as s:
                    yield s
            finally:
                outer.rollback()
    finally:
        engine.dispose()


@pytest.fixture(autouse=True)
def no_runtime_collection(monkeypatch):
    def denied(*args,**kwargs):pytest.fail("Local must not collect or regenerate reference data")
    monkeypatch.setattr("data.osm.collection.urlopen",denied)


@pytest.mark.integration
def test_point_nearest_evidence_determinism_seven_queries_no_grid(session):
    service = LocalAnalyticsService(session)
    captured = []
    conn = session.connection()
    def capture(*args):captured.append(args[2])
    event.listen(conn,"before_cursor_execute",capture)
    started = time.perf_counter()
    try:
        result = service.point(POINT)
    finally:
        event.remove(conn,"before_cursor_execute",capture)
    print(f"Local point runtime={time.perf_counter()-started:.6f}s SQL={len(captured)}")
    assert result.availability == "AVAILABLE" and len(captured) == 7
    assert all('generate_series' not in q and '32646' not in q for q in captured)
    assert result == service.point(POINT)
    for key, (ref, _, normalizer, cls) in service.contracts.items():
        c = result.components[key]
        p = cls(session,scope_id='krasnoyarsk').point(Coordinate(**POINT.model_dump()))
        n = normalizer.normalize(p)
        assert c.score == n.normalized_value and c.distance_m == n.raw_distance_m
        assert c.reference_checksum == ref.REFERENCE_SHA256
        nearest = getattr(p,'nearest_'+('stop' if key == 'stop_availability' else key))
        assert (c.nearest.osm_type,c.nearest.osm_id,c.nearest.name)==(nearest.osm_type,nearest.osm_id,nearest.name)
        if key == 'healthcare':assert c.nearest.category == nearest.source_category


@pytest.mark.integration
def test_union_boundary_covered_outside_unsupported_no_clamping(session):
    boundary = session.execute(text("""SELECT ST_X(p) x,ST_Y(p) y FROM
      (SELECT ST_PointN(ST_ExteriorRing(ST_GeometryN(geometry,1)),1) p
       FROM districts WHERE slug='osm-centralny') s""")).one()
    location = LocalRequest(latitude=boundary.y,longitude=boundary.x)
    result = LocalAnalyticsService(session).points((location, LocalRequest(latitude=0,longitude=0)))
    assert result[0].availability == 'AVAILABLE' and result[0].location == location
    assert result[1].score is None and result[1].unavailable_reason == 'unsupported_geography'
    assert result[1].location == LocalRequest(latitude=0,longitude=0)


@pytest.mark.integration
def test_invalid_polygon_fails_closed_without_distance_queries(session):
    session.execute(text("""UPDATE districts SET geometry=ST_GeomFromText(
      'MULTIPOLYGON(((92.8 56,92.9 56.1,92.8 56.1,92.9 56,92.8 56)))',4326)
      WHERE slug='osm-centralny'"""))
    result = LocalAnalyticsService(session).point(POINT)
    assert result.score is None and result.unavailable_reason == 'sampling_domain_unvalidated'
    assert all(not c.available for c in result.components.values())


@pytest.mark.integration
@pytest.mark.parametrize('mutation',[
    "UPDATE osm_datasets SET active_snapshot_id=NULL",
    "UPDATE pois SET is_synthetic=true WHERE id=(SELECT min(poi_id) FROM osm_active_pois)",
    "DELETE FROM osm_active_pois WHERE poi_id=(SELECT min(poi_id) FROM osm_active_pois)",
    "UPDATE districts SET geometry=ST_Translate(geometry,.001,0) WHERE source_id='osm'",
])
def test_invalid_live_provenance_never_falls_back(session,mutation):
    session.execute(text(mutation))
    result = LocalAnalyticsService(session).point(POINT)
    assert result.score is None and result.availability == 'UNAVAILABLE' and result.unavailable_reason
    assert all(not c.available and c.score is None for c in result.components.values())


@pytest.mark.integration
@pytest.mark.parametrize('key',tuple(WEIGHTS))
@pytest.mark.parametrize('field',['snapshot','evidence_version'])
def test_point_contract_mismatch_fail_closed(session,monkeypatch,key,field):
    service = LocalAnalyticsService(session)
    cls = service.contracts[key][3]
    original = cls.points
    def wrong(self,coordinates):
        points = original(self,coordinates)
        return tuple(p.model_copy(update={field:p.snapshot.model_copy(update={'snapshot_version':'wrong'}) if field == 'snapshot' else 'wrong'}) for p in points)
    monkeypatch.setattr(cls,'points',wrong)
    result = service.point(POINT)
    assert result.score is None and not result.components[key].available
    assert all(c.available for k,c in result.components.items() if k != key)


@pytest.mark.integration
@pytest.mark.parametrize('field',['normalization_version','reference_id','reference_checksum','evidence_version'])
def test_normalization_output_contract_guard(session,monkeypatch,field):
    service = LocalAnalyticsService(session)
    cls = type(service.contracts['school'][2]); original = cls.normalize
    monkeypatch.setattr(cls,'normalize',lambda self,p:original(self,p).model_copy(update={field:'wrong'}))
    result = service.point(POINT)
    assert result.score is None and result.components['school'].unavailable_reason == 'reference_or_version_mismatch'


@pytest.mark.integration
def test_missing_point_evidence_is_unavailable_not_a_partial_weighted_score(session,monkeypatch):
    service = LocalAnalyticsService(session)
    monkeypatch.setattr(service.contracts['kindergarten'][3],'points',lambda *a:())
    result = service.point(POINT)
    assert result.score is None and result.components['kindergarten'].unavailable_reason == 'invalid_component_evidence'
    assert result.weights == dict(WEIGHTS)


@pytest.mark.integration
def test_unnamed_and_unmanaged_synthetic_not_destinations(session):
    # Unmanaged synthetic and historical facts never enter active bindings.
    from datetime import datetime,timezone
    from geoalchemy2.elements import WKTElement
    session.add(models.POI(name='Synthetic nearer school',category='school',location=WKTElement('POINT(92.85 56.01)',srid=4326),
        source_id='demo',source_type='test',source_version='local-test',fetched_at=datetime.now(timezone.utc),is_synthetic=True))
    session.flush()
    result = LocalAnalyticsService(session).point(POINT)
    assert result.components['school'].nearest.name != 'Synthetic nearer school'
    # Null names are already present in active real OSM. Select one observed school directly.
    row = session.execute(text("""SELECT ST_X(p.location) x,ST_Y(p.location) y FROM pois p
      JOIN osm_active_pois b ON b.poi_id=p.id
      WHERE p.category='school' AND p.name IS NULL AND NOT p.is_synthetic LIMIT 1""")).one()
    result = LocalAnalyticsService(session).point(LocalRequest(latitude=row.y,longitude=row.x))
    assert result.availability == 'AVAILABLE' and result.components['school'].nearest.name is None
    assert result.components['school'].distance_m == 0


@pytest.mark.integration
def test_geometry_aware_parks_polygon_boundary_outside_and_node(session):
    service = LocalAnalyticsService(session)
    features = read_geometry().features
    for kind in ('way','relation','node'):
        # Collection extent is wider than the accepted district union. Test actual
        # supported shapes, without weakening Local's calibration geography gate.
        row = session.execute(text("""WITH shapes AS (
          SELECT ST_SetSRID(ST_GeomFromGeoJSON(CASE WHEN osm_type='node' THEN point_location ELSE area_geometry END),4326) g,osm_id
          FROM jsonb_to_recordset(CAST(:features AS jsonb)) AS f(osm_type text,osm_id bigint,point_location jsonb,area_geometry jsonb)
          WHERE osm_type=:kind), g AS (
          SELECT *,CASE WHEN ST_GeometryType(g)='ST_Point' THEN g ELSE ST_PointN(ST_ExteriorRing(ST_GeometryN(g,1)),1) END b FROM shapes)
          SELECT ST_X(ST_PointOnSurface(g)) x,ST_Y(ST_PointOnSurface(g)) y,
          ST_X(b) bx,ST_Y(b) by FROM g
          WHERE EXISTS(SELECT 1 FROM districts d WHERE d.source_id='osm' AND ST_Covers(d.geometry,ST_PointOnSurface(g)))
            AND EXISTS(SELECT 1 FROM districts d WHERE d.source_id='osm' AND ST_Covers(d.geometry,b))
          ORDER BY osm_id LIMIT 1"""),{'features':json.dumps(features),'kind':kind}).one()
        for x,y in ((row.x,row.y),(row.bx,row.by)):
            result = service.point(LocalRequest(latitude=y,longitude=x))
            assert result.availability == 'AVAILABLE',result.unavailable_reason
            parks = result.components['parks']
            assert parks.distance_m == 0 and parks.inside_geometry == (kind != 'node')
    outside = service.point(POINT).components['parks']
    assert outside.distance_m > 0 and outside.inside_geometry is False


@pytest.mark.integration
def test_real_api_repeatable_read_only_transaction(test_database_url,monkeypatch):
    monkeypatch.setenv('DATABASE_URL',test_database_url)
    original = LocalAnalyticsService.point
    def check(self,p):
        assert self.session.scalar(text('SHOW transaction_isolation')) == 'repeatable read'
        assert self.session.scalar(text('SHOW transaction_read_only')) == 'on'
        return original(self,p)
    monkeypatch.setattr(LocalAnalyticsService,'point',check)
    with TestClient(app) as client:
        response = client.post('/api/analytics/local',json=POINT.model_dump())
    assert response.status_code == 200 and response.json()['availability'] == 'AVAILABLE'


@pytest.mark.integration
def test_all_6065_points_35_component_means_7_objectives_parity_and_invariance(session):
    artifact = read_precomputed()
    service = LocalAnalyticsService(session)
    districts = dict(session.execute(select(models.District.id,models.District.slug).where(models.District.source_id=='osm')).all())
    ids = list(districts)
    before = ObjectiveProvider(session).districts(ids)
    grid = district_grid_250(session,ids,reference=service.contracts['school'][2].reference)
    membership = [districts[g.district_id] for g in grid for _ in g.samples]
    points = [LocalRequest(**s.coordinate.model_dump()) for g in grid for s in g.samples]
    assert len(points) == 6065
    results = service.points(points)
    assert len(results) == 6065 and all(r.availability == 'AVAILABLE' for r in results)
    for ident,slug in districts.items():
        rows = [r for r,m in zip(results,membership) if m == slug]
        for key in WEIGHTS:
            mean = statistics.mean(r.components[key].score for r in rows)
            assert mean == pytest.approx(artifact['districts'][slug]['components'][key]['score'],rel=0,abs=1e-12)
        objective = statistics.mean(r.score for r in rows)
        expected = math.fsum(.2*artifact['districts'][slug]['components'][key]['score'] for key in WEIGHTS)
        assert objective == pytest.approx(expected,rel=0,abs=1e-12)
        assert round(objective,2) == before[ident].score
    assert ObjectiveProvider(session).districts(ids) == before
