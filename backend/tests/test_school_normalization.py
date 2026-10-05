"""Accepted frozen CDF and approved District V1; actual PostGIS regressions."""
import bisect
import hashlib
import json
import statistics
import time
from dataclasses import replace

import pytest
from sqlalchemy import event, select, text
from sqlalchemy.orm import Session

from app import models
from app.analytics.school.district import DistrictSchoolAvailabilityService, aggregate_district
from app.analytics.school.models import Coordinate, SchoolObservation, PointSchoolAvailabilityEvidence, SnapshotIdentity
from app.analytics.school.normalization import PointNormalizer
from app.analytics.school.reference import (
    DISTANCES_SHA256, NORMALIZATION_VERSION, REFERENCE_ID, REFERENCE_PATH, REFERENCE_SHA256,
    SAMPLING_VERSION, ReferenceError, read_reference,
)
from app.analytics.school.sampling import DistrictSampling, TerritorialSample, district_grid_250
from app.db import create_session_factory
from data.osm.contracts import Quality

# Exact accepted research OUTPUTS, never normalizer inputs. Full precision values
# were reproduced from the original ignored research bytes before implementation.
ACCEPTED = {'osm-centralny': (553, 63.04532423757694, 782.1248402, 1722.8328854160002, 146, 361, 463),
 'osm-kirovsky': (376, 65.11616179333812, 684.481077805, 2141.09214627, 149, 239, 292),
 'osm-leninsky': (843, 60.56257878518501, 895.94509293, 1827.1670670480007, 213, 468, 687),
 'osm-oktyabrsky': (1461, 42.58901259625786, 1598.03960313, 4755.0377618, 214, 481, 692),
 'osm-sovetsky': (1437, 44.77990982633624, 1417.04782013, 6392.560931572, 344, 583, 755),
 'osm-sverdlovsky': (1215, 42.889350282773385, 1774.73617647, 4371.604454372001, 196, 412, 542),
 'osm-zheleznodorozhny': (180, 78.70092516259045, 440.24998911, 962.443596746, 101, 164, 180)}
QUALITY = Quality(quality_status="VALIDATED",query_completeness_status="VALIDATED",
    provenance_status="VALIDATED",eligibility_status="VALIDATED",temporal_status="VALIDATED",
    reasons=("freshness_policy_not_defined","source_completeness_unknown","real_world_completeness_unknown"))
SNAPSHOT = SnapshotIdentity(dataset_key="osm-poi",scope_id="krasnoyarsk",
    snapshot_version="fresh-20261004T132116Z",canonical_checksum="c1ad85a1d071749c84e31541d104cdaee25d94881ac908ea0838433cbba306e7",
    query_version="osm-poi-query-v1",query_hash="5dd8b0b1555d83e35b3694375fbb595ef62074ff1545065f1779d5e8e6df0c09",
    foundation_eligibility_version="osm-poi-eligibility-v1")


def point(distance=500.0, coordinate=None):
    return PointSchoolAvailabilityEvidence(coordinate=coordinate or Coordinate(longitude=92.85,latitude=56.01),
        snapshot=SNAPSHOT,source_quality=QUALITY,eligible_school_count=205,availability="AVAILABLE",
        nearest_school=SchoolObservation(osm_type="node",osm_id=1,name=None,coordinate_representation="node_coordinate",distance_m=distance))


def sample_evidence(n=180):
    samples=tuple(TerritorialSample(i,0,Coordinate(longitude=92.8+i/10000,latitude=56.0)) for i in range(n))
    return DistrictSampling(1,samples),tuple(point(100+i*10,s.coordinate) for i,s in enumerate(samples))


@pytest.fixture
def session(test_database_url):
    _,engine=create_session_factory(test_database_url)
    try:
        with engine.connect() as connection:
            transaction=connection.begin()
            try:
                with Session(bind=connection,join_transaction_mode="create_savepoint") as session:
                    yield session
            finally: transaction.rollback()
    finally: engine.dispose()


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def denied(*args,**kwargs):pytest.fail("Normalization cannot collect external data")
    monkeypatch.setattr("data.osm.collection.urlopen",denied)
    monkeypatch.setattr("data.loaders.osm_district_loader.urlopen",denied)


def test_packaged_reference_exact_identity_distribution_and_no_ignored_dependency():
    loaded=read_reference();r=loaded.contract
    assert REFERENCE_PATH.is_file() and "raw" not in REFERENCE_PATH.parts
    assert loaded.checksum==hashlib.sha256(REFERENCE_PATH.read_bytes()).hexdigest()==REFERENCE_SHA256
    assert r.reference_id==REFERENCE_ID and r.normalization_version==NORMALIZATION_VERSION
    assert r.sampling_version==SAMPLING_VERSION and r.sample_count==len(r.distances_m)==6065
    assert r.distances_sha256==DISTANCES_SHA256
    assert sum(d.sample_count for d in r.districts)==6065
    assert r.osm_snapshot==SNAPSHOT and r.reference_city=="Krasnoyarsk"


def test_exact_midrank_ties_gaps_endpoints_and_monotonic_bounded_deterministic():
    normalizer=PointNormalizer();values=normalizer.reference.contract.distances_m
    probes=sorted(set(values+(0.0,values[-1]+1)+(tuple((a+b)/2 for a,b in zip(values,values[1:])))))
    scores=[normalizer.distance_value(d) for d in probes]
    for d,s in zip(probes,scores):
        assert s==100*(1-(bisect.bisect_left(values,d)+bisect.bisect_right(values,d))/(2*6065))
        assert 0<=s<=100 and s==normalizer.distance_value(d)
    assert all(a>=b for a,b in zip(scores,scores[1:]))
    assert normalizer.distance_value(0)==100 and normalizer.distance_value(values[-1]+1)==0
    assert 0<normalizer.distance_value(values[-1])<normalizer.distance_value(values[0])<100
    # Exact empirical matches receive the CDF jump midpoint. This accepted
    # distribution has unique distances; bisect also handles whole tie groups.
    match=values[len(values)//2]
    lo,hi=bisect.bisect_left(values,match),bisect.bisect_right(values,match)
    assert hi>lo and normalizer.distance_value(match)==100*(1-(lo+hi)/(2*6065))


@pytest.mark.parametrize("distance",[-1,float("nan"),float("inf"),None,True,"500"])
def test_invalid_direct_distance_is_not_a_score(distance):
    with pytest.raises(ValueError):PointNormalizer().distance_value(distance)


@pytest.mark.parametrize("failure",["missing","corrupt"])
def test_reference_failure_is_unavailable_not_zero(tmp_path,failure):
    path=tmp_path/"reference.json"
    if failure=="corrupt":path.write_bytes(REFERENCE_PATH.read_bytes()+b" ")
    result=PointNormalizer(reference_path=path).normalize(point())
    assert result.availability=="UNAVAILABLE" and result.normalized_value is None
    assert result.unavailable_reason==("reference_unavailable" if failure=="missing" else "reference_checksum_mismatch")


@pytest.mark.parametrize("field",["contract_version","normalization_version","reference_id","evidence_version",
    "eligibility_version","distance_method","sampling_version","cdf_method"])
def test_wrong_reference_versions_rejected_even_with_rehashed_bytes(tmp_path,monkeypatch,field):
    data=json.loads(REFERENCE_PATH.read_bytes());data[field]="wrong-v9"
    raw=json.dumps(data).encode();path=tmp_path/"wrong.json";path.write_bytes(raw)
    monkeypatch.setattr("app.analytics.school.reference.REFERENCE_SHA256",hashlib.sha256(raw).hexdigest())
    with pytest.raises(ReferenceError,match="reference_version_or_contract_mismatch"):read_reference(path)


@pytest.mark.parametrize("field",["evidence_version","eligibility_version","distance_method"])
def test_wrong_point_version_unavailable(field):
    result=PointNormalizer().normalize(point().model_copy(update={field:"wrong-v9"}))
    assert result.normalized_value is None and result.unavailable_reason=="version_mismatch"


@pytest.mark.parametrize("field",["quality_status","query_completeness_status","provenance_status","eligibility_status","temporal_status"])
def test_required_quality_gate_fails_closed(field):
    bad=point().model_copy(update={"source_quality":QUALITY.model_copy(update={field:"UNKNOWN"})})
    result=PointNormalizer().normalize(bad)
    assert result.normalized_value is None and result.unavailable_reason=="quality_unavailable"


def test_missing_evidence_null_and_unknown_completeness_not_penalty():
    normalizer=PointNormalizer()
    missing=point().model_copy(update={"availability":"UNAVAILABLE","nearest_school":None,
        "eligible_school_count":0,"unavailable_reason":"no_eligible_observations"})
    assert normalizer.normalize(missing).normalized_value is None
    unknown=normalizer.normalize(point())
    known=normalizer.normalize(point().model_copy(update={"source_quality":QUALITY.model_copy(update={
        "freshness_status":"VALIDATED","source_completeness_status":"VALIDATED","real_world_completeness_status":"VALIDATED"})}))
    assert unknown.normalized_value==known.normalized_value
    assert "source_completeness_unknown" in unknown.limitations


def test_source_refresh_keeps_frozen_reference_and_coordinate_reuse():
    n=PointNormalizer();original=n.normalize(point())
    refreshed=point().model_copy(update={"snapshot":SNAPSHOT.model_copy(update={"snapshot_version":"future-v2",
        "canonical_checksum":"a"*64,"scope_id":"krasnoyarsk"})})
    result=n.normalize(refreshed)
    assert result.normalized_value==original.normalized_value and result.reference_checksum==REFERENCE_SHA256
    assert result.reference_id==REFERENCE_ID


def test_district_mean_order_invariance_raw_explanation_and_minimum_gate():
    sampling,points=sample_evidence();n=PointNormalizer()
    result=aggregate_district(sampling,points,normalizer=n)
    assert result.availability=="AVAILABLE" and result.score==statistics.mean(n.distance_value(p.nearest_school.distance_m) for p in points)
    reverse=aggregate_district(replace(sampling,samples=tuple(reversed(sampling.samples))),tuple(reversed(points)),normalizer=n)
    assert result==reverse
    assert result.raw.sample_count==result.raw.valid_evidence_count==180
    assert result.raw.median_m is not None and result.raw.p90_m is not None
    assert [c.radius_m for c in result.raw.coverage_curve]==[500,1000,1500]
    small,evidence=sample_evidence(179);unavailable=aggregate_district(small,evidence,normalizer=n)
    assert unavailable.score is None and unavailable.unavailable_reason=="insufficient_samples"


def test_district_partial_dataset_sampling_and_reference_fail_closed(tmp_path):
    sampling,points=sample_evidence();n=PointNormalizer()
    missing=points[0].model_copy(update={"availability":"UNAVAILABLE","nearest_school":None,
        "eligible_school_count":0,"unavailable_reason":"no_eligible_observations"})
    result=aggregate_district(sampling,(missing,)+points[1:],normalizer=n)
    assert result.score is None and result.unavailable_reason=="point_evidence_missing"
    assert result.raw.missing_evidence_count==1
    no_dataset=[p.model_copy(update={"availability":"UNAVAILABLE","nearest_school":None,"snapshot":None,
        "source_quality":None,"eligible_school_count":None,"unavailable_reason":"dataset_unavailable"}) for p in points]
    result=aggregate_district(sampling,no_dataset,normalizer=n)
    assert result.score is None and result.unavailable_reason=="dataset_unavailable"
    bad=aggregate_district(replace(sampling,sampling_version="wrong-v9"),points,normalizer=n)
    assert bad.score is None and bad.unavailable_reason=="version_mismatch"
    no_ref=aggregate_district(sampling,points,normalizer=PointNormalizer(reference_path=tmp_path/"absent"))
    assert no_ref.score is None and no_ref.unavailable_reason=="reference_unavailable"


def test_mixed_source_or_duplicate_or_unpaired_samples_cannot_score():
    sampling,points=sample_evidence();n=PointNormalizer()
    changed=points[0].model_copy(update={"snapshot":SNAPSHOT.model_copy(update={"snapshot_version":"other"})})
    result=aggregate_district(sampling,(changed,)+points[1:],normalizer=n)
    assert result.score is None and result.unavailable_reason=="inconsistent_evidence"
    duplicate=replace(sampling,samples=(sampling.samples[0],)*180)
    assert aggregate_district(duplicate,points,normalizer=n).unavailable_reason=="sampling_contract_mismatch"
    assert aggregate_district(sampling,points[:-1],normalizer=n).score is None


@pytest.mark.integration
def test_point_normalizer_performs_no_database_query(session):
    statements=[];connection=session.connection()
    def capture(*args):statements.append(args[2])
    event.listen(connection,"before_cursor_execute",capture)
    try:
        result=PointNormalizer().normalize(point())
    finally:event.remove(connection,"before_cursor_execute",capture)
    assert result.availability=="AVAILABLE" and statements==[]


@pytest.mark.integration
def test_grid250_fresh_all_seven_full_precision_two_queries_and_invariance(session):
    districts={d.id:d.slug for d in session.scalars(select(models.District).where(models.District.source_id=="osm"))}
    connection=session.connection();statements=[]
    def capture(*args):statements.append(args[2])
    event.listen(connection,"before_cursor_execute",capture)
    started=time.perf_counter()
    try:
        results=DistrictSchoolAvailabilityService(session,scope_id="krasnoyarsk").districts(list(reversed(districts)))
    finally:event.remove(connection,"before_cursor_execute",capture)
    elapsed=time.perf_counter()-started
    print(f"School normalized runtime: {elapsed:.6f}s, queries={len(statements)}, samples=6065")
    assert len(statements)==2
    assert sum(r.raw.sample_count for r in results)==6065
    for r in results:
        count,score,median,p90,c500,c1000,c1500=ACCEPTED[districts[r.district_id]]
        assert r.availability=="AVAILABLE" and r.score==score
        assert round(r.score,2)==round(score,2)
        assert r.reference_checksum==REFERENCE_SHA256 and r.normalization_version==NORMALIZATION_VERSION
        assert r.raw.sample_count==r.raw.valid_evidence_count==count and r.raw.missing_evidence_count==0
        assert r.raw.median_m==pytest.approx(median,abs=1e-6,rel=0)
        assert r.raw.p90_m==pytest.approx(p90,abs=1e-6,rel=0)
        assert [c.covered_count for c in r.raw.coverage_curve]==[c500,c1000,c1500]
        assert r.raw.source_quality.source_completeness_status=="UNKNOWN"
        assert r.raw.source_quality.real_world_completeness_status=="UNKNOWN"
    samples=district_grid_250(session,list(districts),reference=read_reference())
    assert samples==district_grid_250(session,list(reversed(districts)),reference=read_reference())
    # Runtime point/geometry association and original polygon predicate.
    payload=[{"id":g.district_id,"lon":s.coordinate.longitude,"lat":s.coordinate.latitude} for g in samples for s in g.samples]
    assert session.scalar(text("""SELECT bool_and(ST_Covers(d.geometry,ST_SetSRID(ST_MakePoint(p.lon,p.lat),4326)))
        FROM jsonb_to_recordset(CAST(:p AS jsonb)) p(id integer,lon double precision,lat double precision)
        JOIN districts d ON d.id=p.id"""),{"p":json.dumps(payload)})
    from app.analytics.service import AnalyticsService
    profile=models.UserProfile(data_processing_consent=True,housing_goal="buy",purchase_budget=8000000)
    session.add(profile);session.flush()
    expected={"osm-centralny":(80.45,100,56.01),"osm-kirovsky":(87.67,100,72.25),"osm-leninsky":(80.36,100,55.82),
        "osm-oktyabrsky":(63.84,83.86,38.81),"osm-sovetsky":(82.53,100,60.70),"osm-sverdlovsky":(65.64,82.11,45.06),
        "osm-zheleznodorozhny":(100,100,100)}
    old=AnalyticsService(session).calculate(profile.public_id,list(districts))
    assert {r.district.slug:(r.score,r.categories.infrastructure,r.categories.transport) for r in old}==expected


@pytest.mark.integration
def test_sampling_unknown_domain_missing_invalid_geometry_and_scope(session):
    service=DistrictSchoolAvailabilityService(session,scope_id="krasnoyarsk")
    assert service.districts([2147483647])[0].unavailable_reason=="sampling_unavailable"
    d=session.scalar(select(models.District).where(models.District.slug=="osm-centralny"))
    assert DistrictSchoolAvailabilityService(session,scope_id="city2").districts([d.id])[0].unavailable_reason=="sampling_domain_unvalidated"
    session.execute(text("UPDATE districts SET geometry=NULL,boundary=NULL WHERE id=:id"),{"id":d.id})
    assert service.districts([d.id])[0].unavailable_reason=="sampling_unavailable"
    session.execute(text("UPDATE districts SET geometry=ST_GeomFromText('MULTIPOLYGON(((0 0,1 1,1 0,0 1,0 0)))',4326) WHERE id=:id"),{"id":d.id})
    assert service.districts([d.id])[0].unavailable_reason=="sampling_unavailable"
    session.execute(text("UPDATE districts SET geometry=ST_GeomFromText('MULTIPOLYGON(((0 0,1 0,1 1,0 1,0 0)))',4326) WHERE id=:id"),{"id":d.id})
    assert service.districts([d.id])[0].unavailable_reason=="sampling_domain_unvalidated"



def test_future_city_cannot_silently_use_krasnoyarsk_normalization():
    other=point().model_copy(update={"snapshot":SNAPSHOT.model_copy(update={"scope_id":"city2"})})
    result=PointNormalizer().normalize(other)
    assert result.normalized_value is None and result.unavailable_reason=="normalization_scope_unvalidated"


def test_reference_self_calibration_mean_is_fifty():
    n=PointNormalizer()
    assert statistics.mean(n.distance_value(d) for d in n.reference.contract.distances_m)==pytest.approx(50,abs=1e-12,rel=0)


def test_reference_is_school_specific_not_stop_distribution():
    from app.analytics.stop_availability.reference import read_reference as stops
    assert read_reference().contract.distances_m!=stops().contract.distances_m
    assert read_reference().checksum!=stops().checksum
