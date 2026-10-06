"""Geometry-aware Parks and frozen normalization, entirely offline PostGIS."""
import bisect
import json
import time
from pathlib import Path

import pytest
from sqlalchemy import event, select, text
from sqlalchemy.orm import Session
from pydantic import ValidationError
from app import models
from app.db import create_session_factory
from app.analytics.parks.models import Coordinate
from app.analytics.parks.service import ParksAvailabilityService
from app.analytics.parks.district import DistrictParksAvailabilityService
from app.analytics.parks.normalization import PointNormalizer
from app.analytics.parks.reference import REFERENCE_PATH, REFERENCE_SHA256, ReferenceContract, ReferenceError, read_reference
from data.osm.park_geometry import read_geometry


@pytest.fixture
def session(test_database_url):
    _,engine = create_session_factory(test_database_url)
    with engine.connect() as conn:
        transaction = conn.begin()
        try:
            with Session(bind=conn,join_transaction_mode="create_savepoint") as s:
                yield s
        finally: transaction.rollback()
    engine.dispose()


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def denied(*args,**kwargs): pytest.fail("Parks runtime must not collect data")
    monkeypatch.setattr("data.osm.collection.urlopen",denied)


@pytest.mark.integration
@pytest.mark.parametrize("kind",["node","way","relation"])
def test_real_nearest_point_area_inside_and_outside(session,kind):
    f = next(f for f in read_geometry().features if f["osm_type"] == kind)
    geometry = f["point_location"] or f["area_geometry"]
    session.execute(text("UPDATE pois SET category='not-a-park' WHERE category='park' AND external_id != :id"),
                    {"id":f'{kind}:{f["osm_id"]}'})
    coords = session.execute(text("""WITH g AS (SELECT ST_SetSRID(ST_GeomFromGeoJSON(:g),4326) AS g)
      SELECT ST_X(ST_PointOnSurface(g)) AS x,ST_Y(ST_PointOnSurface(g)) AS y,
        ST_XMax(Box3D(g))+0.02 AS outside_x FROM g"""),{"g":json.dumps(geometry)}).one()
    service = ParksAvailabilityService(session,scope_id="krasnoyarsk")
    points = (Coordinate(longitude=coords.x,latitude=coords.y),Coordinate(longitude=coords.outside_x,latitude=coords.y))
    inside,outside = service.points(points)
    assert inside.availability == outside.availability == "AVAILABLE"
    assert inside.nearest_parks.distance_m == 0
    assert inside.nearest_parks.inside_park_geometry == (kind != "node")
    assert inside.nearest_parks.osm_id == f["osm_id"] and inside.eligible_parks_count == 1
    assert outside.nearest_parks.distance_m > 1000 and not outside.nearest_parks.inside_park_geometry
    expected = session.scalar(text("SELECT ST_Distance(ST_SetSRID(ST_GeomFromGeoJSON(:g),4326)::geography,"
        "ST_SetSRID(ST_MakePoint(:x,:y),4326)::geography,true)"),{"g":json.dumps(geometry),"x":coords.outside_x,"y":coords.y})
    assert outside.nearest_parks.distance_m == expected
    assert service.points(points) == (inside,outside)
    assert inside.geometry_snapshot.snapshot_version == "parks-geometry-20261005T134520Z"
    assert inside.snapshot.snapshot_version == "fresh-20261004T132116Z"


@pytest.mark.integration
@pytest.mark.parametrize("changed",["synthetic","source","category"])
def test_active_projection_real_exact_category_only(session,changed):
    poi = session.scalar(select(models.POI).where(models.POI.category == "park",models.POI.source_id == "osm"))
    if changed == "synthetic": poi.is_synthetic = True
    elif changed == "source": poi.source_id = "other-park-source"
    else: poi.category = "garden"
    session.flush()
    result = ParksAvailabilityService(session,scope_id="krasnoyarsk").point(Coordinate(longitude=92.85,latitude=56.01))
    assert result.eligible_parks_count == 282


@pytest.mark.integration
def test_unmanaged_history_wrong_category_not_destinations_and_unnamed_preserved(session):
    poi = session.scalar(select(models.POI).where(models.POI.category == "park",models.POI.name.is_(None)))
    session.execute(text("UPDATE pois SET category='garden' WHERE category='park' AND id != :id"),{"id":poi.id})
    result = ParksAvailabilityService(session,scope_id="krasnoyarsk").point(Coordinate(longitude=92.85,latitude=56.01))
    assert result.availability == "AVAILABLE" and result.eligible_parks_count == 1
    assert result.nearest_parks.name is None
    assert session.scalar(text("SELECT ST_GeometryType(location) FROM pois WHERE id=:id"),{"id":poi.id}) == "ST_Point"
    assert poi.geometry is None


@pytest.mark.integration
def test_no_eligible_missing_dataset_invalid_coordinate_and_geometry_fail_closed(session,tmp_path):
    point = Coordinate(longitude=92.85,latitude=56.01)
    service = ParksAvailabilityService(session,scope_id="krasnoyarsk")
    result = service.point(Coordinate(longitude=None,latitude=56))
    assert result.unavailable_reason == "invalid_coordinate" and result.nearest_parks is None
    assert PointNormalizer().normalize(result).normalized_value is None
    result = ParksAvailabilityService(session,scope_id="unknown").point(point)
    assert result.unavailable_reason == "dataset_unavailable"
    result = ParksAvailabilityService(session,scope_id="krasnoyarsk",geometry_root=tmp_path).point(point)
    assert result.unavailable_reason == "geometry_unavailable" and result.nearest_parks is None
    session.execute(text("UPDATE pois SET category='garden' WHERE category='park'"))
    result = service.point(point)
    assert result.unavailable_reason == "no_eligible_observations" and result.eligible_parks_count == 0
    assert PointNormalizer().normalize(result).normalized_value is None


@pytest.mark.integration
def test_future_or_retired_snapshot_cannot_silently_use_geometry(session):
    from data.osm.baseline import read_packaged_baseline
    from data.osm.contracts import BuildResult, canonical_bytes, checksum
    from data.osm.lifecycle import activate_snapshot, persist_candidate, review_for_activation
    _,manifest,baseline = read_packaged_baseline()
    version = "parks-future-regression"
    observations = tuple(o.model_copy(update={"snapshot_id":version}) for o in baseline.observations)
    canonical = {**baseline.canonical,"snapshot_id":version,"observations":[o.model_dump(mode="json") for o in observations]}
    sha = checksum(canonical_bytes(canonical))
    report = {**baseline.report,"canonical_checksum":sha}
    result = BuildResult(canonical=canonical,canonical_checksum=sha,observations=observations,quality=baseline.quality,report=report)
    snapshot = persist_candidate(session,result,manifest=manifest.model_copy(update={"snapshot_id":version}))
    review_for_activation(session,snapshot.id,reviewer="parks-test",reason="Disposable future-version guard")
    activate_snapshot(session,snapshot.id)
    point = ParksAvailabilityService(session,scope_id="krasnoyarsk").point(Coordinate(longitude=92.85,latitude=56.01))
    assert point.unavailable_reason == "geometry_baseline_mismatch" and point.nearest_parks is None
    assert PointNormalizer().normalize(point).normalized_value is None


def test_frozen_normalization_zero_ties_bounds_monotonicity():
    ref = read_reference().contract
    normalizer = PointNormalizer()
    assert len(ref.distances_m) == 6065 and ref.distances_m.count(0) == 171
    assert normalizer.distance_value(0) == 100*(1-171/(2*6065))
    for d in (0,ref.distances_m[200],100,500,1000,100000):
        expected = 100*(1-(bisect.bisect_left(ref.distances_m,d)+bisect.bisect_right(ref.distances_m,d))/(2*6065))
        assert normalizer.distance_value(d) == expected
    sequence = [normalizer.distance_value(d) for d in (0,1,10,100,500,1000,100000)]
    assert all(0 <= v <= 100 for v in sequence) and sequence == sorted(sequence,reverse=True)
    assert sequence[-1] == 0


@pytest.mark.parametrize("value",[-1,float("nan"),float("inf"),None,True,"1"])
def test_invalid_distance_does_not_normalize_to_zero(value):
    with pytest.raises(ValueError): PointNormalizer().distance_value(value)


def test_reference_corruption_and_missing_fail_closed(tmp_path):
    bad = tmp_path/"reference.json"
    bad.write_bytes(REFERENCE_PATH.read_bytes()+b" ")
    with pytest.raises(ReferenceError): read_reference(bad)
    assert PointNormalizer(reference_path=bad).failure_reason == "reference_checksum_mismatch"
    assert PointNormalizer(reference_path=tmp_path/"missing").failure_reason == "reference_unavailable"


@pytest.mark.parametrize("field",["contract_version","normalization_version","sampling_version"])
def test_reference_version_rejected(field):
    data = read_reference().contract.model_dump(mode="json")
    data[field] = "unsupported-v99"
    with pytest.raises(ValidationError): ReferenceContract.model_validate(data)


@pytest.mark.integration
def test_synthetic_source_cannot_supply_active_park_evidence(session):
    source = session.scalar(select(models.DataSource).where(models.DataSource.source_id == "osm"))
    source.is_synthetic = True
    session.flush()
    result = ParksAvailabilityService(session,scope_id="krasnoyarsk").point(Coordinate(longitude=92.85,latitude=56.01))
    assert result.unavailable_reason == "dataset_unavailable" and result.nearest_parks is None


@pytest.mark.integration
def test_normalizer_has_no_sql_and_temporal_versions_guarded(session):
    point = ParksAvailabilityService(session,scope_id="krasnoyarsk").point(Coordinate(longitude=92.85,latitude=56.01))
    captured = []
    def capture(*args): captured.append(args[2])
    conn = session.connection()
    event.listen(conn,"before_cursor_execute",capture)
    try:
        n = PointNormalizer()
        assert n.normalize(point).availability == "AVAILABLE"
        wrong = point.model_copy(update={"snapshot":point.snapshot.model_copy(update={"snapshot_version":"other"})})
        assert n.normalize(wrong).normalized_value is None
        assert n.normalize(wrong).unavailable_reason == "geometry_baseline_mismatch"
    finally: event.remove(conn,"before_cursor_execute",capture)
    assert captured == []


@pytest.mark.integration
def test_district_all_seven_regressions_two_queries_and_mesto_unchanged(session):
    districts = {d.id:d.slug for d in session.scalars(select(models.District).where(models.District.source_id == "osm"))}
    captured = []
    conn = session.connection()
    def capture(*args): captured.append(args[2])
    event.listen(conn,"before_cursor_execute",capture)
    started = time.perf_counter()
    try: results = DistrictParksAvailabilityService(session,scope_id="krasnoyarsk").districts(list(districts))
    finally: event.remove(conn,"before_cursor_execute",capture)
    print(f"Parks runtime: {time.perf_counter()-started:.6f}s, queries={len(captured)}, N=6065")
    assert len(captured) == 2
    assert sum(r.raw.sample_count for r in results) == 6065
    assert sum(r.raw.inside_park_count for r in results) == 171
    for r in results:
        n,score,median,p90,c500,c1000,c1500,inside = ACCEPTED[districts[r.district_id]]
        assert r.availability == "AVAILABLE" and r.score == score and r.reference_checksum == REFERENCE_SHA256
        assert r.raw.sample_count == r.raw.valid_evidence_count == n and r.raw.missing_evidence_count == 0
        assert r.raw.median_m == pytest.approx(median,abs=1e-6,rel=0)
        assert r.raw.p90_m == pytest.approx(p90,abs=1e-6,rel=0)
        assert [c.covered_count for c in r.raw.coverage_curve] == [c500,c1000,c1500]
        assert r.raw.inside_park_count == inside and r.raw.share_inside_park_geometry == inside/n
    from app.analytics.service import LegacyAnalyticsService as AnalyticsService
    profile = models.UserProfile(data_processing_consent=True,housing_goal="buy",purchase_budget=8000000)
    session.add(profile);session.flush()
    expected = {"osm-centralny":80.45,"osm-kirovsky":87.67,"osm-leninsky":80.36,"osm-oktyabrsky":63.84,
                "osm-sovetsky":82.53,"osm-sverdlovsky":65.64,"osm-zheleznodorozhny":100}
    response = AnalyticsService(session).calculate(profile.public_id,list(districts))
    assert {r.district.slug:float(r.score) for r in response} == expected


ACCEPTED = {'osm-oktyabrsky': (1461, 48.23091503013498, 1014.84441997, 2399.26820568, 408, 722, 973, 15), 'osm-zheleznodorozhny': (180, 71.9729779243382, 377.65276426, 987.5379292289999, 118, 164, 180, 2), 'osm-centralny': (553, 54.58308052159472, 741.95151041, 2393.1218358339997, 199, 351, 413, 6), 'osm-sovetsky': (1437, 47.71623923386234, 936.10226183, 4876.926827814001, 518, 741, 859, 118), 'osm-sverdlovsky': (1215, 38.83478367072761, 1489.45120348, 3727.9528847020038, 252, 445, 609, 6), 'osm-leninsky': (843, 56.98921040252934, 687.27546997, 1751.3701155900003, 296, 583, 715, 8), 'osm-kirovsky': (376, 68.75173212187121, 468.83928791000005, 1053.561673005, 204, 325, 375, 16)}
