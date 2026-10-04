"""Raw evidence regressions on real PostGIS; grid500 is RESEARCH_ONLY."""
from collections import Counter
from datetime import datetime, timezone

import pytest
from geoalchemy2.elements import WKTElement
from sqlalchemy import event, select, text
from sqlalchemy.orm import Session

from app import models
from app.analytics.stop_availability.aggregation import summarize
from app.analytics.stop_availability.models import (
    Coordinate, NearestStop, PointStopAvailabilityEvidence, SnapshotIdentity,
)
from app.analytics.stop_availability.research import administrative_grid_500, district_research
from app.analytics.stop_availability.service import StopAvailabilityService
from app.db import create_session_factory
from data.osm.builder import build
from data.osm.collection import collect
from data.osm.contracts import Quality, canonical_bytes, checksum
from data.osm.legacy import LEGACY_EXTENT
from data.osm.lifecycle import activate_snapshot, persist_candidate, review_for_activation

SCOPE = "stop-evidence-regression"
ID = 2000000000000
POINT = Coordinate(longitude=92.85,latitude=56.01)


@pytest.fixture
def session(test_database_url):
    _, engine = create_session_factory(test_database_url)
    try:
        with engine.connect() as connection:
            outer = connection.begin()
            try:
                with Session(bind=connection,join_transaction_mode="create_savepoint") as session:
                    yield session
            finally:
                outer.rollback()
    finally:
        engine.dispose()


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def denied(*args,**kwargs):
        pytest.fail("Stop evidence must not collect external data")
    monkeypatch.setattr("data.osm.collection.urlopen",denied)
    monkeypatch.setattr("data.loaders.osm_district_loader.urlopen",denied)


def node(ident,*,lon=92.85,lat=56.011,tags=None):
    return {"type":"node","id":ident,"lon":lon,"lat":lat,
            "tags":tags if tags is not None else {"highway":"bus_stop"}}


def candidate(session,tmp_path,version,elements):
    root=tmp_path/version
    response=canonical_bytes({"version":.6,"generator":"Overpass API",
        "osm3s":{"timestamp_osm_base":"2026-10-01T00:00:00Z"},"elements":elements})
    manifest=collect(dataset_id="stop-test",scope_id=SCOPE,snapshot_id=version,extent=LEGACY_EXTENT,
        parts={"full":LEGACY_EXTENT},output_dir=root,transport=lambda _: (200,response),
        clock=lambda:datetime(2026,10,2,tzinfo=timezone.utc))
    return persist_candidate(session,build(manifest,root),manifest=manifest)


def activate(session,tmp_path,version,elements):
    snapshot=candidate(session,tmp_path,version,elements)
    review_for_activation(session,snapshot.id,reviewer="stop-regression",
        reason="Disposable source evidence only; source completeness remains UNKNOWN")
    activate_snapshot(session,snapshot.id)
    return snapshot


def service(session):
    return StopAvailabilityService(session,scope_id=SCOPE)


@pytest.mark.integration
def test_nearest_meters_unnamed_location_geometry_null_and_identity(session,tmp_path):
    snapshot=activate(session,tmp_path,"nearest",[node(ID+1),node(ID+2,lat=56.02)])
    point=session.scalar(select(models.POI).where(models.POI.external_id==f"node:{ID+1}"))
    assert point.name is None and point.geometry is None and point.location is not None
    evidence=service(session).point(POINT)
    assert evidence.availability=="AVAILABLE"
    assert (evidence.nearest_stop.osm_type,evidence.nearest_stop.osm_id,evidence.nearest_stop.name)==("node",ID+1,None)
    assert 110 < evidence.nearest_stop.distance_m < 112  # .001 degree latitude is ~111 meters.
    assert evidence.eligible_stop_count==2
    assert evidence.snapshot.snapshot_version==snapshot.version
    assert evidence.snapshot.canonical_checksum==snapshot.canonical_checksum
    assert evidence.snapshot.query_hash==snapshot.query_hash
    assert evidence.snapshot.foundation_eligibility_version=="osm-poi-eligibility-v1"
    assert evidence.source_quality.source_completeness_status=="UNKNOWN"
    assert evidence.source_quality.real_world_completeness_status=="UNKNOWN"
    # The point is independent of both district ID and user profile.
    assert "district_id" not in PointStopAvailabilityEvidence.model_fields
    assert "profile_id" not in PointStopAvailabilityEvidence.model_fields
    invalid=service(session).point(Coordinate(longitude=181,latitude=56))
    assert invalid.unavailable_reason=="invalid_coordinate" and invalid.snapshot==evidence.snapshot
    assert invalid.nearest_stop is None and invalid.eligible_stop_count==2


@pytest.mark.integration
def test_non_stop_platform_synthetic_other_source_and_unmanaged_pois_excluded(session,tmp_path):
    activate(session,tmp_path,"isolation",[
        node(ID+1),node(ID+2,lat=56.01,tags={"amenity":"school"}),
        node(ID+3,lat=56.01,tags={"public_transport":"platform","bus":"yes"}),
    ])
    for number,(source,synthetic) in enumerate((("osm",True),("other-stop-source",False),("osm",False))):
        session.add(models.POI(name="Unmanaged nearer point",category="bus_stop",source_id=source,
            source_type="test",source_version="test",fetched_at=datetime(2026,10,2,tzinfo=timezone.utc),
            is_synthetic=synthetic,external_id=f"node:{ID+100+number}",
            location=WKTElement("POINT(92.85 56.01)",srid=4326),metadata_json={"highway":"bus_stop"}))
    session.flush()
    evidence=service(session).point(POINT)
    assert evidence.eligible_stop_count==1 and evidence.nearest_stop.osm_id==ID+1


@pytest.mark.integration
@pytest.mark.parametrize("changed",["synthetic","source"])
def test_bound_projection_source_and_synthetic_filters(session,tmp_path,changed):
    activate(session,tmp_path,"bound-isolation",[node(ID+1)])
    point=session.scalar(select(models.POI).where(models.POI.external_id==f"node:{ID+1}"))
    if changed=="synthetic": point.is_synthetic=True
    else: point.source_id="other-stop-source"
    session.flush()
    evidence=service(session).point(POINT)
    assert evidence.availability=="UNAVAILABLE" and evidence.nearest_stop is None
    assert evidence.eligible_stop_count==0 and evidence.unavailable_reason=="no_eligible_observations"


@pytest.mark.integration
@pytest.mark.parametrize("assigned",[True,False])
def test_across_district_border_or_unassigned_stop_can_be_nearest(session,tmp_path,assigned):
    source=dict(source_id="osm",source_type="test",source_version="stop-border",
        fetched_at=datetime(2026,10,2,tzinfo=timezone.utc),is_synthetic=False)
    a=models.District(name="Point side",geometry=WKTElement(
        "MULTIPOLYGON(((92.849 56.009,92.8505 56.009,92.8505 56.012,92.849 56.012,92.849 56.009)))",srid=4326),**source)
    b=models.District(name="Stop side",geometry=WKTElement(
        "MULTIPOLYGON(((92.8505 56.009,92.852 56.009,92.852 56.012,92.8505 56.012,92.8505 56.009)))",srid=4326),**source)
    session.add_all([a,b]); session.flush()
    activate(session,tmp_path,"border",[node(ID+1,lon=92.851,lat=56.01),node(ID+2,lat=56.02)])
    nearest=session.scalar(select(models.POI).where(models.POI.external_id==f"node:{ID+1}"))
    nearest.district_id=b.id if assigned else None
    session.flush()
    assert session.scalar(text("SELECT ST_Covers(geometry,ST_SetSRID(ST_MakePoint(92.85,56.01),4326)) FROM districts WHERE id=:id"),{"id":a.id})
    assert service(session).point(POINT).nearest_stop.osm_id==ID+1


@pytest.mark.integration
def test_retired_and_candidate_history_do_not_leak(session,tmp_path):
    old=activate(session,tmp_path,"old",[node(ID+1,lat=56.01)])
    fresh=activate(session,tmp_path,"fresh",[node(ID+2,lat=56.02)])
    pending=candidate(session,tmp_path,"pending",[node(ID+3,lat=56.01)])
    evidence=service(session).point(POINT)
    assert old.status=="RETIRED" and fresh.status=="ACTIVE" and pending.status=="CANDIDATE"
    assert evidence.eligible_stop_count==1 and evidence.nearest_stop.osm_id==ID+2
    assert evidence.snapshot.snapshot_version=="fresh"
    assert session.scalar(text("SELECT count(*) FROM osm_snapshot_observations WHERE snapshot_id=ANY(:ids)"),
        {"ids":[old.id,fresh.id,pending.id]})==3


@pytest.mark.integration
def test_exact_tie_identity_order_and_batch_order(session,tmp_path):
    way={"type":"way","id":ID+1,"center":{"lon":92.85,"lat":56.01},"tags":{"highway":"bus_stop"}}
    activate(session,tmp_path,"ties",[node(ID+2,lat=56.01),way,node(ID+1,lat=56.01)])
    points=(POINT,Coordinate(longitude=92.85,latitude=56.0101),POINT)
    results=service(session).points(points)
    assert tuple(r.coordinate for r in results)==points
    assert all((r.nearest_stop.osm_type,r.nearest_stop.osm_id)==("node",ID+1) for r in results)
    assert results[0].nearest_stop.distance_m==0  # Known coincidence is valid zero.
    assert results==service(session).points(points)
    assert service(session).points(())==()


@pytest.mark.integration
def test_no_eligible_observation_is_unavailable_null(session,tmp_path):
    activate(session,tmp_path,"no-stops",[node(ID+1,tags={"amenity":"school"})])
    result=service(session).point(POINT)
    assert result.availability=="UNAVAILABLE" and result.unavailable_reason=="no_eligible_observations"
    assert result.nearest_stop is None and result.eligible_stop_count==0 and result.snapshot is not None


@pytest.mark.integration
def test_dataset_unavailable_is_null(session):
    result=service(session).point(POINT)
    assert result.unavailable_reason=="dataset_unavailable"
    assert result.snapshot is None and result.nearest_stop is None and result.eligible_stop_count is None


@pytest.mark.integration
@pytest.mark.parametrize("longitude,latitude",[(181,56),(92,91),(float("nan"),56),(92,float("inf")),(None,56),(True,56)])
def test_invalid_coordinate_is_explicit_and_json_safe(session,longitude,latitude):
    result=service(session).point(Coordinate(longitude=longitude,latitude=latitude))
    assert result.availability=="UNAVAILABLE" and result.unavailable_reason=="invalid_coordinate"
    assert result.nearest_stop is None
    assert "NaN" not in result.model_dump_json() and "Infinity" not in result.model_dump_json()


REFERENCE=SnapshotIdentity(dataset_key="test",scope_id="test",snapshot_version="test-v1",
    canonical_checksum="a"*64,query_version="test-query",query_hash="b"*64,foundation_eligibility_version=None)


def evidence(distance):
    return PointStopAvailabilityEvidence(coordinate=POINT if distance is not None else Coordinate(longitude=None,latitude=None),
        snapshot=REFERENCE,source_quality=Quality(),
        eligible_stop_count=1,availability="AVAILABLE" if distance is not None else "UNAVAILABLE",
        unavailable_reason=None if distance is not None else "invalid_coordinate",
        nearest_stop=NearestStop(osm_type="node",osm_id=1,name=None,distance_m=distance) if distance is not None else None)


def test_summary_median_p90_coverage_missing_and_input_order():
    points=tuple(evidence(d) for d in (1400,100,800,500,None))
    result=summarize(points,sampling_version="unit-samples-v1",radii_m=(1000,500,0,500))
    assert (result.sample_count,result.valid_evidence_count,result.missing_evidence_count)==(5,4,1)
    assert result.availability=="PARTIAL" and result.missing_reasons=={"invalid_coordinate":1}
    assert result.median_m==650 and result.p90_m==pytest.approx(1220,abs=1e-12,rel=0)
    assert result.p90_m>=result.median_m
    assert [(p.radius_m,p.covered_count,p.valid_sample_count,p.share) for p in result.coverage_curve]==[
        (0,0,4,0),(500,2,4,.5),(1000,3,4,.75)]
    assert result.coverage_curve[2].share>=result.coverage_curve[1].share
    assert summarize(tuple(reversed(points)),sampling_version="unit-samples-v1",radii_m=(0,500,1000))==result


@pytest.mark.parametrize("points",[(),(evidence(None),evidence(None))])
def test_all_missing_or_empty_summary_has_null_distances_and_coverage(points):
    result=summarize(points,sampling_version="unit-samples-v1")
    assert result.availability=="UNAVAILABLE" and result.valid_evidence_count==0
    assert result.missing_evidence_count==len(points)
    assert result.median_m is None and result.p90_m is None
    assert all(p.share is None and p.valid_sample_count==0 for p in result.coverage_curve)


def test_single_sample_and_boundary_inclusion():
    result=summarize((evidence(500),),sampling_version="unit-samples-v1")
    assert result.median_m==result.p90_m==500
    assert result.coverage_curve[0].share==1


@pytest.mark.parametrize("radius",[-1,float("inf"),float("nan"),True,None])
def test_invalid_radii_rejected(radius):
    with pytest.raises(ValueError,match="radii"):
        summarize((evidence(100),),sampling_version="unit",radii_m=(radius,))


def test_mixed_snapshot_summary_rejected():
    first=evidence(100)
    second=first.model_copy(update={"snapshot":REFERENCE.model_copy(update={"snapshot_version":"other"})})
    with pytest.raises(ValueError,match="different source snapshots"):
        summarize((first,second),sampling_version="unit")


# Accepted unrounded research replay values; 1 micrometer absolute tolerance
# allows only floating-point geodesic/interpolation noise, not methodology drift.
RESEARCH_REFERENCE={
    "osm-centralny":(138,440.5187594,1305.22781203,73,109),
    "osm-kirovsky":(91,383.59528186,978.52775837,56,82),
    "osm-leninsky":(217,503.496604,1255.958092274,108,176),
    "osm-oktyabrsky":(363,520.68105891,1611.767669822,175,280),
    "osm-sovetsky":(360,466.46478933,1498.151919924,190,281),
    "osm-sverdlovsky":(308,636.84240014,2571.366579186,131,198),
    "osm-zheleznodorozhny":(46,244.412846555,687.82858805,38,46),
}


@pytest.mark.integration
def test_research_only_fresh_grid500_seven_districts_exact_sampling_batch_queries(session):
    districts={d.id:d.slug for d in session.scalars(select(models.District).where(models.District.source_id=="osm"))}
    statements=[]
    def capture(connection,cursor,statement,parameters,context,executemany):
        statements.append(statement)
    connection=session.connection()
    event.listen(connection,"before_cursor_execute",capture)
    try:
        results=district_research(session,list(districts),scope_id="krasnoyarsk")
    finally:
        event.remove(connection,"before_cursor_execute",capture)
    assert len(statements)==2  # One grid statement + one canonical spatial batch.
    assert sum(row.summary.sample_count for row in results)==1523
    for row in results:
        expected=RESEARCH_REFERENCE[districts[row.district_id]]
        summary=row.summary
        assert row.purpose=="RESEARCH_ONLY" and summary.sampling_version=="admin-grid-500-v1"
        assert summary.snapshot.snapshot_version=="fresh-20261004T132116Z"
        assert summary.availability=="AVAILABLE" and summary.missing_evidence_count==0
        assert summary.sample_count==summary.valid_evidence_count==expected[0]
        assert summary.median_m==pytest.approx(expected[1],abs=1e-6,rel=0)
        assert summary.p90_m==pytest.approx(expected[2],abs=1e-6,rel=0)
        assert [p.covered_count for p in summary.coverage_curve]==list(expected[3:])
        assert [p.share for p in summary.coverage_curve]==[n/expected[0] for n in expected[3:]]
    samples=administrative_grid_500(session,list(reversed(districts)))
    assert Counter(districts[s.district_id] for s in samples)=={s:r[0] for s,r in RESEARCH_REFERENCE.items()}
    grid=sorted([[districts[s.district_id],s.coordinate.longitude,s.coordinate.latitude] for s in samples])
    assert checksum(canonical_bytes(grid))=="4e5d80adf7de9d5a8bf74198531390daefee987d3f24c1a938aaf928c7082925"
    assert StopAvailabilityService(session,scope_id="krasnoyarsk").point(POINT).eligible_stop_count==1360


@pytest.mark.integration
def test_research_missing_district_boundary_is_rejected(session):
    with pytest.raises(ValueError,match="unavailable"):
        administrative_grid_500(session,[2147483647])
    district=models.District(name="No polygon",source_id="test-grid",source_type="test",source_version="v1",
        fetched_at=datetime(2026,10,2,tzinfo=timezone.utc),is_synthetic=False)
    session.add(district);session.flush()
    with pytest.raises(ValueError,match="unavailable"):
        administrative_grid_500(session,[district.id])
