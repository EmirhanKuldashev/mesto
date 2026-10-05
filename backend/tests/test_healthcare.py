"""Canonical Healthcare raw evidence on disposable PostgreSQL/PostGIS, entirely offline."""
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from geoalchemy2.elements import WKTElement
from pydantic import ValidationError
from sqlalchemy import event, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import models
from app.analytics.healthcare.aggregation import summarize
from app.analytics.healthcare.models import Coordinate, PointHealthcareAvailabilityEvidence, HealthcareObservation, SnapshotIdentity
from app.analytics.healthcare.service import HealthcareAvailabilityService
from app.db import create_session_factory
from data.osm.builder import build
from data.osm.collection import collect
from data.osm.contracts import Quality, canonical_bytes
from data.osm.legacy import LEGACY_EXTENT
from data.osm.lifecycle import activate_snapshot, persist_candidate, review_for_activation

SCOPE = "healthcare-evidence-regression"
ID = 3000000000000
POINT = Coordinate(longitude=92.85,latitude=56.01)


@pytest.fixture
def session(test_database_url):
    _,engine = create_session_factory(test_database_url)
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                with Session(bind=connection,join_transaction_mode="create_savepoint") as session:
                    yield session
            finally:
                transaction.rollback()
    finally:
        engine.dispose()


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def denied(*args,**kwargs):
        pytest.fail("Healthcare evidence must not collect external data")
    monkeypatch.setattr("data.osm.collection.urlopen",denied)
    monkeypatch.setattr("data.loaders.osm_district_loader.urlopen",denied)


def element(ident, *, kind="node",lon=92.85,lat=56.011,tags=None):
    row = {"type":kind,"id":ident,"tags":tags if tags is not None else {"amenity":"clinic"}}
    if kind == "node": row.update(lon=lon,lat=lat)
    else: row["center"] = {"lon":lon,"lat":lat}
    return row


def candidate(session,tmp_path,version,elements):
    root = tmp_path/version
    response = canonical_bytes({"version":.6,"generator":"Overpass API",
        "osm3s":{"timestamp_osm_base":"2026-10-01T00:00:00Z"},"elements":elements})
    manifest = collect(dataset_id="healthcare-test",scope_id=SCOPE,snapshot_id=version,extent=LEGACY_EXTENT,
        parts={"full":LEGACY_EXTENT},output_dir=root,transport=lambda _: (200,response),
        clock=lambda:datetime(2026,10,2,tzinfo=timezone.utc))
    return persist_candidate(session,build(manifest,root),manifest=manifest)


def activate(session,tmp_path,version,elements):
    snapshot = candidate(session,tmp_path,version,elements)
    review_for_activation(session,snapshot.id,reviewer="healthcare-regression",reason="Disposable observed proximity regression")
    activate_snapshot(session,snapshot.id)
    return snapshot


def service(session):
    return HealthcareAvailabilityService(session,scope_id=SCOPE)


@pytest.mark.integration
@pytest.mark.parametrize("kind",["node","way","relation"])
@pytest.mark.parametrize("category",["clinic","hospital"])
def test_nearest_meters_unnamed_geometry_null_representation_and_snapshot(session,tmp_path,kind,category):
    snapshot = activate(session,tmp_path,"nearest",[element(ID+1,kind=kind,tags={"amenity":category}),element(ID+2,lat=56.02)])
    poi = session.scalar(select(models.POI).where(models.POI.external_id==f"{kind}:{ID+1}"))
    assert poi.name is None and poi.geometry is None and poi.location is not None
    result = service(session).point(POINT)
    assert result.availability == "AVAILABLE" and result.eligible_healthcare_count == 2
    assert (result.nearest_healthcare.osm_type,result.nearest_healthcare.osm_id,result.nearest_healthcare.name) == (kind,ID+1,None)
    assert result.nearest_healthcare.source_category == category
    assert result.nearest_healthcare.coordinate_representation == ("node_coordinate" if kind=="node" else "overpass_center")
    assert 110 < result.nearest_healthcare.distance_m < 112
    expected = session.scalar(text("SELECT ST_Distance(ST_SetSRID(ST_MakePoint(92.85,56.01),4326)::geography,"
                                   "ST_SetSRID(ST_MakePoint(92.85,56.011),4326)::geography,true)"))
    assert result.nearest_healthcare.distance_m == expected
    assert result.snapshot.snapshot_version == snapshot.version
    assert result.snapshot.canonical_checksum == snapshot.canonical_checksum
    assert result.snapshot.foundation_eligibility_version == "osm-poi-eligibility-v1"
    assert result.source_quality.freshness_status == "UNKNOWN"
    assert result.source_quality.source_completeness_status == "UNKNOWN"
    assert "district_id" not in type(result).model_fields and "profile_id" not in type(result).model_fields
    assert "score" not in type(result).model_fields


@pytest.mark.integration
def test_exact_union_excludes_other_medical_tags_and_preserves_subtype(session,tmp_path):
    tags=[{"amenity":v} for v in ("doctors","pharmacy","dentist","veterinary","school","kindergarten")]
    tags += [{"healthcare":"clinic"},{"healthcare":"hospital"},{"healthcare":"doctor"},
        {"building":"hospital"},{"amenity":"clinic;hospital"}]
    activate(session,tmp_path,"taxonomy",[element(ID+1),element(ID+2,lat=56.02,tags={"amenity":"hospital"})]
        + [element(ID+10+i,lat=56.01,tags=t) for i,t in enumerate(tags)])
    results=service(session).points((POINT,Coordinate(longitude=92.85,latitude=56.02)))
    assert all(r.eligible_healthcare_count==2 for r in results)
    assert [(r.nearest_healthcare.osm_id,r.nearest_healthcare.source_category) for r in results]==[(ID+1,"clinic"),(ID+2,"hospital")]


@pytest.mark.integration
def test_exact_amenity_policy_not_rewritten_from_name_building_or_healthcare_tag(session,tmp_path):
    activate(session,tmp_path,"laboratory",[element(ID+1,tags={"amenity":"clinic",
        "healthcare":"laboratory","name":"Clinical laboratory","building":"hospital"})])
    result=service(session).point(POINT)
    assert result.eligible_healthcare_count==1 and result.nearest_healthcare.name=="Clinical laboratory"
    assert result.nearest_healthcare.source_category=="clinic"


@pytest.mark.integration
@pytest.mark.parametrize("changed",["synthetic","source","category"])
def test_bound_projection_isolation(session,tmp_path,changed):
    activate(session,tmp_path,"isolation",[element(ID+1)])
    poi = session.scalar(select(models.POI).where(models.POI.external_id==f"node:{ID+1}"))
    if changed == "synthetic": poi.is_synthetic = True
    elif changed == "source": poi.source_id = "other-healthcare-source"
    else: poi.category = "hospital"  # Category must agree with canonical clinic tag.
    session.flush()
    result = service(session).point(POINT)
    assert result.unavailable_reason == "no_eligible_observations" and result.nearest_healthcare is None


@pytest.mark.integration
def test_unmanaged_pois_never_become_canonical_healthcare(session,tmp_path):
    activate(session,tmp_path,"unmanaged",[element(ID+1)])
    session.add(models.POI(name="Closer unmanaged healthcare",category="clinic",source_id="osm",source_type="test",
        source_version="test",fetched_at=datetime(2026,10,2,tzinfo=timezone.utc),is_synthetic=False,
        external_id=f"node:{ID+100}",location=WKTElement("POINT(92.85 56.01)",srid=4326),metadata_json={"amenity":"clinic"}))
    session.flush()
    assert service(session).point(POINT).nearest_healthcare.osm_id == ID+1


@pytest.mark.integration
@pytest.mark.parametrize("assigned",[True,False])
def test_healthcare_across_border_or_unassigned_may_be_nearest(session,tmp_path,assigned):
    source = dict(source_id="osm",source_type="test",source_version="healthcare-border",
                  fetched_at=datetime(2026,10,2,tzinfo=timezone.utc),is_synthetic=False)
    a = models.District(name="Point side",geometry=WKTElement(
        "MULTIPOLYGON(((92.849 56.009,92.8505 56.009,92.8505 56.012,92.849 56.012,92.849 56.009)))",srid=4326),**source)
    b = models.District(name="Healthcare side",geometry=WKTElement(
        "MULTIPOLYGON(((92.8505 56.009,92.852 56.009,92.852 56.012,92.8505 56.012,92.8505 56.009)))",srid=4326),**source)
    session.add_all([a,b]);session.flush()
    activate(session,tmp_path,"border",[element(ID+1,lon=92.851,lat=56.01),element(ID+2,lat=56.02)])
    poi = session.scalar(select(models.POI).where(models.POI.external_id==f"node:{ID+1}"))
    poi.district_id = b.id if assigned else None
    session.flush()
    assert session.scalar(text("SELECT ST_Covers(geometry,ST_SetSRID(ST_MakePoint(92.85,56.01),4326)) FROM districts WHERE id=:id"),{"id":a.id})
    assert service(session).point(POINT).nearest_healthcare.osm_id == ID+1


@pytest.mark.integration
def test_retired_candidate_and_other_dataset_excluded_active_switch_observed(session,tmp_path):
    old = activate(session,tmp_path,"old",[element(ID+1,lat=56.01)])
    fresh = activate(session,tmp_path,"fresh",[element(ID+2,lat=56.02)])
    pending = candidate(session,tmp_path,"pending",[element(ID+3,lat=56.01)])
    result = service(session).point(POINT)
    assert (old.status,fresh.status,pending.status) == ("RETIRED","ACTIVE","CANDIDATE")
    assert result.eligible_healthcare_count == 1 and result.nearest_healthcare.osm_id == ID+2
    assert result.snapshot.snapshot_version == "fresh"
    assert service(session).point(POINT) != HealthcareAvailabilityService(session,scope_id="krasnoyarsk").point(POINT)


@pytest.mark.integration
def test_tie_and_result_order_are_deterministic_one_batch_query(session,tmp_path):
    activate(session,tmp_path,"tie",[element(ID+2,lat=56.01),element(ID+1,kind="way",lat=56.01),
        element(ID+1,lat=56.01),element(ID+1,kind="relation",lat=56.01)])
    coords=(POINT,POINT,Coordinate(longitude=92.85,latitude=56.0101))
    statements=[]
    def capture(*args):statements.append(args[2])
    connection=session.connection();event.listen(connection,"before_cursor_execute",capture)
    try: results=service(session).points(coords)
    finally:event.remove(connection,"before_cursor_execute",capture)
    assert len(statements)==1 and tuple(r.coordinate for r in results)==coords
    assert all((r.nearest_healthcare.osm_type,r.nearest_healthcare.osm_id)==("node",ID+1) for r in results)
    assert results[0].nearest_healthcare.distance_m==0
    assert results==service(session).points(coords) and service(session).points(())==()


@pytest.mark.integration
def test_no_eligible_healthcare_null(session,tmp_path):
    activate(session,tmp_path,"no-healthcare",[element(ID+1,tags={"amenity":"school"})])
    result = service(session).point(POINT)
    assert result.unavailable_reason == "no_eligible_observations"
    assert result.nearest_healthcare is None and result.eligible_healthcare_count == 0 and result.snapshot is not None


@pytest.mark.integration
def test_dataset_unavailable_null(session):
    result = service(session).point(POINT)
    assert result.unavailable_reason == "dataset_unavailable"
    assert result.snapshot is None and result.nearest_healthcare is None and result.eligible_healthcare_count is None


@pytest.mark.integration
@pytest.mark.parametrize("lon,lat",[(181,56),(92,91),(float("nan"),56),(92,float("inf")),(None,56),(True,56),("92",56)])
def test_invalid_coordinate_explicit_json_safe(session,lon,lat):
    result = service(session).point(Coordinate(longitude=lon,latitude=lat))
    assert result.unavailable_reason == "invalid_coordinate" and result.nearest_healthcare is None
    assert "NaN" not in result.model_dump_json() and "Infinity" not in result.model_dump_json()


READY = Quality(query_completeness_status="VALIDATED",provenance_status="VALIDATED",eligibility_status="VALIDATED",
                temporal_status="VALIDATED",quality_status="VALIDATED")
SNAPSHOT = SnapshotIdentity(dataset_key="test",scope_id="test",snapshot_version="v1",canonical_checksum="a"*64,
                            query_version="test-query",query_hash="b"*64,foundation_eligibility_version="osm-poi-eligibility-v1")


def evidence(distance):
    return PointHealthcareAvailabilityEvidence(coordinate=POINT if distance is not None else Coordinate(longitude=None,latitude=None),
        snapshot=SNAPSHOT,source_quality=READY,eligible_healthcare_count=1,
        availability="AVAILABLE" if distance is not None else "UNAVAILABLE",
        unavailable_reason=None if distance is not None else "invalid_coordinate",
        nearest_healthcare=HealthcareObservation(osm_type="node",osm_id=1,name=None,source_category="clinic",coordinate_representation="node_coordinate",
                                         distance_m=distance) if distance is not None else None)


@pytest.mark.parametrize("field,value",[("foundation_policy","unknown-v2"),("quality",{}),("quality",{"quality_status":"INVALID"}),
                                        ("query_version",None)])
def test_version_or_quality_failure_is_explicit_null(field,value):
    row={"position":0,"dataset_key":"test","scope_id":"test","version":"v1","canonical_checksum":"a"*64,
         "query_version":"test","query_hash":"b"*64,"foundation_policy":"osm-poi-eligibility-v1",
         "quality":READY.model_dump(mode="json"),"eligible_count":1,
         "observation":evidence(100).nearest_healthcare.model_dump(mode="json")}
    row[field]=value
    class Rows:
        def mappings(self): return [row]
    class FakeSession:
        def execute(self,*args): return Rows()
    result=HealthcareAvailabilityService(FakeSession(),scope_id="test").point(POINT)
    assert result.unavailable_reason=="version_quality_failure" and result.nearest_healthcare is None


def test_aggregation_median_p90_coverage_missing_and_order():
    points=tuple(evidence(d) for d in (1400,100,800,500,None))
    result=summarize(points,sampling_version="unit-v1",radii_m=(1000,500,0,500))
    assert (result.sample_count,result.valid_evidence_count,result.missing_evidence_count)==(5,4,1)
    assert result.availability=="PARTIAL" and result.missing_reasons=={"invalid_coordinate":1}
    assert result.median_m==650 and result.p90_m==pytest.approx(1220,abs=1e-12,rel=0)
    assert [(c.radius_m,c.covered_count,c.valid_sample_count,c.share) for c in result.coverage_curve]==[(0,0,4,0),(500,2,4,.5),(1000,3,4,.75)]
    assert result.coverage_curve[-1].share >= result.coverage_curve[-2].share
    assert summarize(tuple(reversed(points)),sampling_version="unit-v1",radii_m=(0,500,1000))==result


@pytest.mark.parametrize("points",[(),(evidence(None),evidence(None))])
def test_empty_or_all_missing_null_summary(points):
    result=summarize(points,sampling_version="unit-v1")
    assert result.median_m is None and result.p90_m is None
    assert result.valid_evidence_count==0 and result.missing_evidence_count==len(points)
    assert all(c.share is None for c in result.coverage_curve)


def test_single_sample_inclusive_coverage():
    result=summarize((evidence(500),),sampling_version="unit-v1")
    assert result.median_m==result.p90_m==500 and result.coverage_curve[0].share==1


@pytest.mark.parametrize("radius",[-1,True,None,float("inf"),float("nan")])
def test_invalid_radii_rejected(radius):
    with pytest.raises(ValueError,match="radii"):
        summarize((evidence(100),),sampling_version="unit-v1",radii_m=(radius,))


def test_mixed_snapshot_or_quality_rejected():
    point=evidence(100)
    for changed in ({"snapshot":SNAPSHOT.model_copy(update={"snapshot_version":"other"})},
                    {"source_quality":READY.model_copy(update={"freshness_status":"PARTIAL"})}):
        with pytest.raises(ValueError,match="different source snapshots"):
            summarize((point,point.model_copy(update=changed)),sampling_version="unit-v1")


def test_representation_and_available_contract_reject_invalid_states():
    with pytest.raises(ValidationError):
        HealthcareObservation(osm_type="way",osm_id=1,name=None,source_category="clinic",coordinate_representation="node_coordinate",distance_m=1)
    bad=evidence(100).model_dump();bad['source_quality']=Quality().model_dump()
    with pytest.raises(ValidationError): PointHealthcareAvailabilityEvidence.model_validate(bad)
    bad=evidence(None).model_dump();bad['nearest_healthcare']=evidence(100).nearest_healthcare.model_dump()
    with pytest.raises(ValidationError): PointHealthcareAvailabilityEvidence.model_validate(bad)



@pytest.mark.integration
@pytest.mark.parametrize("mutation",["source_synthetic","invalid_location"])
def test_active_dataset_and_location_safety_gates(session,tmp_path,mutation):
    snapshot=activate(session,tmp_path,"safety",[element(ID+1)])
    if mutation=="source_synthetic":
        source=session.scalar(select(models.DataSource).where(models.DataSource.source_id=="osm"))
        source.is_synthetic=True
    else:
        poi=session.scalar(select(models.POI).where(models.POI.external_id==f"node:{ID+1}"))
        poi.location=WKTElement("POINT(181 56)",srid=4326)
    session.flush()
    result=service(session).point(POINT)
    assert result.nearest_healthcare is None
    assert result.unavailable_reason==("dataset_unavailable" if mutation=="source_synthetic" else "no_eligible_observations")


@pytest.mark.integration
def test_database_rejects_missing_location_without_weakening_schema(session,tmp_path):
    activate(session,tmp_path,"missing-location",[element(ID+1)])
    with pytest.raises(IntegrityError,match="not-null constraint"):
        with session.begin_nested():
            poi=session.scalar(select(models.POI).where(models.POI.external_id==f"node:{ID+1}"))
            poi.location=None
            session.flush()
    assert service(session).point(POINT).availability=="AVAILABLE"


@pytest.mark.integration
def test_legacy_baseline_never_becomes_canonical(legacy_session):
    result=HealthcareAvailabilityService(legacy_session,scope_id="krasnoyarsk").point(POINT)
    assert result.unavailable_reason=="dataset_unavailable" and result.nearest_healthcare is None

def test_raw_subtype_breakdown_valid_missing_and_no_service_equivalence_claim():
    clinic=evidence(100)
    hospital=evidence(700).model_copy(update={"nearest_healthcare":evidence(700).nearest_healthcare.model_copy(update={"source_category":"hospital"})})
    result=summarize((clinic,hospital,evidence(None)),sampling_version="unit-v1")
    assert result.nearest_category_counts=={"clinic":1,"hospital":1}
    assert result.sample_count==3 and result.valid_evidence_count==2 and result.missing_evidence_count==1
    assert result.median_m==400 and result.coverage_curve[0].share==.5
    with pytest.raises(ValidationError):
        HealthcareObservation(osm_type="node",osm_id=1,name=None,source_category="dentist",coordinate_representation="node_coordinate",distance_m=100)
    with pytest.raises(ValidationError):
        type(result).model_validate(result.model_dump() | {"nearest_category_counts":{"clinic":2,"hospital":1}})
