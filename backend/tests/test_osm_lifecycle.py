"""Lifecycle integration with mocked source responses and disposable PostGIS only."""
from datetime import datetime, timezone
from pathlib import Path

import pytest
from geoalchemy2.elements import WKTElement
from sqlalchemy import event, func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app import models
from app.api import catalogue
from app.db import create_session_factory
from data.loaders.osm_poi_loader import load_dataset, load_pois
from data.osm.builder import build
from data.osm.collection import collect
from data.osm.contracts import canonical_bytes
from data.osm.legacy import LEGACY_EXTENT
from data.osm.lifecycle import activate_snapshot, persist_candidate, review_for_activation

pytestmark = pytest.mark.integration
FIXTURE = Path(__file__).resolve().parents[1]/"data/fixtures/osm/poi.json"


@pytest.fixture
def session(test_database_url):
    _, engine = create_session_factory(test_database_url)
    try:
        with engine.connect() as connection:
            outer = connection.begin()
            try:
                with Session(bind=connection, join_transaction_mode="create_savepoint") as value:
                    yield value
            finally:
                outer.rollback()
    finally:
        engine.dispose()


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("Lifecycle tests must not collect real OSM data")
    monkeypatch.setattr("data.osm.collection.urlopen", denied)


def node(id_, name="A", lon=92.85):
    return {"type":"node","id":id_,"lat":56.01,"lon":lon,
            "tags":{"highway":"bus_stop", **({"name":name} if name is not None else {})}}


def candidate(session, tmp_path, version, elements, scope="lifecycle-test", failure=None):
    def response(base, items):
        return canonical_bytes({"version":0.6,"generator":"Overpass API",
            "osm3s":{"timestamp_osm_base":base},"elements":items})
    parts = {"full":LEGACY_EXTENT}
    responses = [(500 if failure=="http" else 200, response("2026-10-01T00:00:00Z",elements))]
    if failure=="mixed":
        parts["second"] = LEGACY_EXTENT
        responses.append((200,response("2026-10-01T00:00:01Z",elements)))
    if failure=="conflict":
        parts["second"] = LEGACY_EXTENT
        responses.append((200,response("2026-10-01T00:00:00Z",[node(elements[0]["id"],name="Conflict")])))
    iterator = iter(responses)
    root = tmp_path/version
    manifest = collect(dataset_id="test-osm",scope_id=scope,snapshot_id=version,extent=LEGACY_EXTENT,
        parts=parts,output_dir=root,transport=lambda _:next(iterator),
        clock=lambda:datetime(2026,10,2,tzinfo=timezone.utc))
    if failure=="provenance":
        manifest = manifest.model_copy(update={"parts":tuple(p.model_copy(update={"fetched_at":None}) for p in manifest.parts)})
    result = build(manifest,root)
    return persist_candidate(session,result,manifest=manifest), result


def approved(session, snapshot):
    return review_for_activation(session,snapshot.id,reviewer="lifecycle-regression",reason="Explicit acceptance of UNKNOWN proxy quality in disposable test")


def force_constraints(session):
    session.flush()
    session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    session.execute(text("SET CONSTRAINTS ALL DEFERRED"))


def active_rows(session, dataset_id):
    return list(session.scalars(select(models.POI).join(models.OsmActivePoi,models.OsmActivePoi.poi_id==models.POI.id)
        .where(models.OsmActivePoi.dataset_id==dataset_id).order_by(models.POI.external_id)))


def history(session, snapshot):
    return list(session.scalars(select(models.OsmSnapshotObservation).where(
        models.OsmSnapshotObservation.snapshot_id==snapshot.id).order_by(models.OsmSnapshotObservation.osm_id)))


def test_candidate_is_invisible_and_version_is_immutable(session,tmp_path):
    before = session.scalar(select(func.count()).select_from(models.POI))
    snapshot,result = candidate(session,tmp_path,"A",[node(123)])
    assert session.get(models.OsmDataset,snapshot.dataset_id).active_snapshot_id is None
    assert session.scalar(select(func.count()).select_from(models.POI)) == before
    assert persist_candidate(session,result).id == snapshot.id
    _,different = candidate(session,tmp_path,"different",[node(123,name="Different")])
    # Same version with a different valid build must fail, even with a valid hash.
    changed_canonical = {**different.canonical,"snapshot_id":"A",
        "observations":[{**r.model_dump(mode="json"),"snapshot_id":"A"} for r in different.observations]}
    from data.osm.contracts import Observation, checksum
    changed = different.model_copy(update={"canonical":changed_canonical,
        "observations":tuple(Observation.model_validate(r) for r in changed_canonical["observations"]),
        "canonical_checksum":checksum(canonical_bytes(changed_canonical))})
    with pytest.raises(ValueError,match="different content"):
        persist_candidate(session,changed)
    changed = result.model_copy(update={"canonical_checksum":"0"*64})
    with pytest.raises(ValueError,match="checksum"):
        persist_candidate(session,changed)
    with pytest.raises(ValueError,match="reviewed"):
        activate_snapshot(session,snapshot.id)
    force_constraints(session)


def test_activation_versions_removal_retirement_and_bbox(session,tmp_path):
    a,_ = candidate(session,tmp_path,"A",[node(1),node(2),node(123)])
    approved(session,a)
    activate_snapshot(session,a.id)
    before = [r.projection for r in history(session,a)]
    b,_ = candidate(session,tmp_path,"B",[node(2),node(3),node(123,name=None,lon=92.86)])
    assert [r.external_id for r in active_rows(session,a.dataset_id)]==["node:1","node:123","node:2"]
    approved(session,b)
    activate_snapshot(session,b.id)
    force_constraints(session)
    rows = active_rows(session,a.dataset_id)
    assert {r.external_id for r in rows}=={"node:2","node:3","node:123"}
    assert a.status=="RETIRED" and b.status=="ACTIVE"
    assert session.get(models.OsmDataset,a.dataset_id).active_snapshot_id==b.id
    assert [r.projection for r in history(session,a)]==before
    old = next(r for r in history(session,a) if r.osm_id==123)
    new = next(r for r in history(session,b) if r.osm_id==123)
    assert old.observation["name"]=="A" and old.observation["longitude"]==92.85
    assert new.observation["name"] is None and new.observation["longitude"]==92.86
    assert any(r.osm_id==1 for r in history(session,a))
    projected = next(r for r in rows if r.external_id=="node:123")
    assert projected.geometry is None and projected.name is None
    found = catalogue(session,models.POI,bbox="92.859,56.009,92.861,56.011",source_id="osm")
    assert projected.id in {r["id"] for r in found}
    assert len(rows)==3  # A+B are never counted together


@pytest.mark.parametrize("failure",["http","mixed","conflict","provenance"])
def test_failed_candidate_cannot_displace_active(session,tmp_path,failure):
    a,_ = candidate(session,tmp_path,"A",[node(1)])
    approved(session,a)
    activate_snapshot(session,a.id)
    c,_ = candidate(session,tmp_path,"C",[node(1)],failure=failure)
    assert c.status=="REJECTED"
    with pytest.raises(ValueError):
        review_for_activation(session,c.id,reviewer="test",reason="Cannot override required gates")
    with pytest.raises(ValueError):
        activate_snapshot(session,c.id)
    assert session.get(models.OsmDataset,a.dataset_id).active_snapshot_id==a.id
    assert a.status=="ACTIVE"
    force_constraints(session)


def test_atomic_failure_restores_pointer_payload_and_history(session,tmp_path):
    a,_ = candidate(session,tmp_path,"A",[node(1),node(123)])
    approved(session,a)
    activate_snapshot(session,a.id)
    b,_ = candidate(session,tmp_path,"B",[node(2),node(123,name="B")])
    approved(session,b)
    connection = session.connection()
    def fail(conn,cursor,statement,parameters,context,executemany):
        if statement.startswith("UPDATE osm_datasets SET active_snapshot_id"):
            raise RuntimeError("Injected pointer failure")
    event.listen(connection,"before_cursor_execute",fail)
    try:
        with pytest.raises(RuntimeError,match="Injected"):
            activate_snapshot(session,b.id)
    finally:
        event.remove(connection,"before_cursor_execute",fail)
    session.expire_all()
    assert session.get(models.OsmDataset,a.dataset_id).active_snapshot_id==a.id
    assert session.get(models.OsmSnapshot,a.id).status=="ACTIVE"
    assert session.get(models.OsmSnapshot,b.id).status=="VALIDATED"
    assert {r.external_id for r in active_rows(session,a.dataset_id)}=={"node:1","node:123"}
    assert all(r.name=="A" for r in active_rows(session,a.dataset_id))
    assert len(history(session,a))==len(history(session,b))==2
    force_constraints(session)


def test_other_scope_synthetic_and_other_source_are_untouched(session,tmp_path):
    synth = models.POI(name="Synthetic",category="bus_stop",location=WKTElement("POINT(92.85 56.01)",srid=4326),
        source_id="synthetic-independent",source_type="test",source_version="1",fetched_at=datetime.now(timezone.utc),is_synthetic=True)
    other = models.POI(name="Other",category="bus_stop",location=WKTElement("POINT(92.85 56.01)",srid=4326),
        external_id="node:1",source_id="other-source",source_type="test",source_version="1",fetched_at=datetime.now(timezone.utc),is_synthetic=False)
    session.add_all([synth,other]); session.flush()
    ids = (synth.id,other.id)
    a,_ = candidate(session,tmp_path,"A",[node(1)])
    approved(session,a); activate_snapshot(session,a.id)
    independent,_ = candidate(session,tmp_path,"X",[node(9)],scope="another-scope")
    approved(session,independent); activate_snapshot(session,independent.id)
    b,_ = candidate(session,tmp_path,"B",[node(2)])
    approved(session,b); activate_snapshot(session,b.id)
    assert session.get(models.POI,ids[0]).name=="Synthetic"
    assert session.get(models.POI,ids[0]).is_synthetic
    assert session.get(models.POI,ids[1]).name=="Other"
    assert independent.status=="ACTIVE"
    assert [r.external_id for r in active_rows(session,independent.dataset_id)]==["node:9"]
    force_constraints(session)


def test_synthetic_osm_identity_collision_is_rejected(session,tmp_path):
    point = models.POI(name="Synthetic OSM ID",category="bus_stop",location=WKTElement("POINT(92.85 56.01)",srid=4326),
        source_id="osm",source_type="test",source_version="test",external_id="node:123",
        fetched_at=datetime.now(timezone.utc),is_synthetic=True)
    session.add(point); session.flush()
    a,_ = candidate(session,tmp_path,"A",[node(123)])
    approved(session,a)
    with pytest.raises(ValueError,match="Synthetic"):
        activate_snapshot(session,a.id)
    assert point.name=="Synthetic OSM ID" and point.is_synthetic


def test_db_constraints_and_immutable_history(session,tmp_path):
    a,_ = candidate(session,tmp_path,"A",[node(123)])
    b,_ = candidate(session,tmp_path,"B",[node(124)],scope="another")
    approved(session,a); activate_snapshot(session,a.id)
    checks = [
        ("UPDATE osm_datasets SET scope_id='rewritten' WHERE id=:ds",{"ds":a.dataset_id}),
        ("UPDATE osm_datasets SET active_snapshot_id=:b WHERE id=:ds",{"b":b.id,"ds":a.dataset_id}),
        ("UPDATE osm_snapshots SET canonical_checksum='tamper' WHERE id=:id",{"id":a.id}),
        ("UPDATE osm_snapshot_observations SET observation='{}' WHERE snapshot_id=:id",{"id":a.id}),
        ("DELETE FROM osm_snapshot_observations WHERE snapshot_id=:id",{"id":a.id}),
        ("UPDATE osm_snapshots SET status='ACTIVE' WHERE id=:id",{"id":b.id}),
        ("INSERT INTO osm_snapshot_observations(snapshot_id,osm_type,osm_id,eligible,observation) VALUES (:id,'node',125,true,'{}')",{"id":a.id}),
    ]
    for statement,params in checks:
        with pytest.raises(DBAPIError):
            with session.begin_nested():
                session.execute(text(statement),params)
                force_constraints(session)
    assert session.get(models.OsmDataset,a.dataset_id).active_snapshot_id==a.id
    force_constraints(session)


def test_legacy_adoption_and_restart_do_not_change_payload(session):
    before = session.execute(text("SELECT id,to_jsonb(p) AS payload FROM pois p WHERE source_id='osm' ORDER BY id")).all()
    loaded = load_pois(session,FIXTURE)
    after = session.execute(text("SELECT id,to_jsonb(p) AS payload FROM pois p WHERE source_id='osm' ORDER BY id")).all()
    assert before==after and loaded["total"]==1988
    dataset = session.scalar(select(models.OsmDataset).where(models.OsmDataset.scope_id=="krasnoyarsk"))
    snapshot = session.get(models.OsmSnapshot,dataset.active_snapshot_id)
    assert snapshot.is_legacy and snapshot.status=="ACTIVE"
    assert snapshot.quality["provenance_status"]=="PARTIAL"
    assert snapshot.quality["temporal_status"]=="UNKNOWN"
    assert len(history(session,snapshot))==1988
    force_constraints(session)


def test_future_collector_label_and_bootstrap_cannot_resurrect_legacy(session,tmp_path):
    # Source/scope identity must accept collector osm-poi after legacy-poi adoption.
    scope = "krasnoyarsk"
    a,result = candidate(session,tmp_path,"test-future-candidate",[node(123)],scope=scope)
    approved(session,a)
    activate_snapshot(session,a.id)
    before = [(p.id,p.name,p.external_id) for p in active_rows(session,a.dataset_id)]
    loaded = load_pois(session,FIXTURE)
    assert loaded["total"]==1 and loaded["created"]==loaded["updated"]==0
    assert [(p.id,p.name,p.external_id) for p in active_rows(session,a.dataset_id)]==before
    assert a.status=="ACTIVE"
    force_constraints(session)


def test_empty_candidate_requires_separate_policy(session,tmp_path):
    snapshot,_ = candidate(session,tmp_path,"empty",[])
    with pytest.raises(ValueError,match="Empty"):
        approved(session,snapshot)


@pytest.mark.parametrize("quality",["RESEARCH_ONLY","PARTIAL","BLOCKED"])
def test_disallowed_quality_cannot_be_reviewed(session,tmp_path,quality):
    _,result = candidate(session,tmp_path,"original",[node(123)],scope="original")
    from data.osm.contracts import Quality,checksum
    new_quality = Quality.model_validate({**result.quality.model_dump(),"quality_status":quality})
    canonical = {**result.canonical,"quality":new_quality.model_dump(mode="json"),"scope_id":"blocked-scope",
        "observations":[{**r.model_dump(mode="json"),"scope_id":"blocked-scope"} for r in result.observations]}
    from data.osm.contracts import Observation
    rejected = result.model_copy(update={"quality":new_quality,"canonical":canonical,
        "observations":tuple(Observation.model_validate(r) for r in canonical["observations"]),
        "canonical_checksum":checksum(canonical_bytes(canonical))})
    snapshot = persist_candidate(session,rejected)
    assert snapshot.status=="REJECTED"
    with pytest.raises(ValueError):
        approved(session,snapshot)


def test_migration_existing_legacy_roundtrip_and_lossy_guard(test_database_url,tmp_path,monkeypatch):
    """Actual upgrade of persisted pre-lifecycle rows, not just empty create_all."""
    from uuid import uuid4
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine
    from sqlalchemy.engine import make_url
    from app.analytics.service import AnalyticsService
    database_name = "mesto_lifecycle_roundtrip_" + uuid4().hex
    assert database_name.startswith("mesto_lifecycle_roundtrip_")
    base_url = make_url(test_database_url)
    admin = create_engine(base_url,isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{database_name}"'))
    url = base_url.set(database=database_name).render_as_string(hide_password=False)
    monkeypatch.setenv("DATABASE_URL",url)
    config = Config(str(FIXTURE.parents[3]/"alembic.ini"))
    config.set_main_option("script_location",str(FIXTURE.parents[3]/"migrations"))
    factory, engine = create_session_factory(url)
    def current_payloads():
        with engine.connect() as connection:
            return connection.execute(text("SELECT id,to_jsonb(p) FROM pois p WHERE source_id='osm' ORDER BY id")).all()
    def scores():
        with factory() as session:
            profile = session.scalar(select(models.UserProfile))
            districts = list(session.scalars(select(models.District).order_by(models.District.slug)))
            return {r.district.slug:(r.score,r.categories.transport,r.categories.infrastructure)
                for r in AnalyticsService(session).calculate(profile.public_id,[d.id for d in districts])}
    try:
        command.upgrade(config,"head")
        from data.loaders.osm_district_loader import load_districts
        with factory.begin() as value:
            load_districts(value,FIXTURE.with_name("krasnoyarsk_districts.json"))
            load_pois(value,FIXTURE)
            value.add(models.UserProfile(data_processing_consent=True,housing_goal="buy",purchase_budget=8000000))
        before_first_downgrade = current_payloads()
        command.downgrade(config,"0013_poi_nullable_name")
        assert current_payloads()==before_first_downgrade
        with engine.begin() as connection:
            # Simulate the older deployed loader whose metadata lacked foundation.
            connection.execute(text("UPDATE pois SET metadata=metadata-'osm_foundation' WHERE source_id='osm'"))
        before = current_payloads()
        baseline = scores()
        assert len(before)==1988
        assert {k:v[0] for k,v in baseline.items()}=={
            "osm-centralny":73.94,"osm-kirovsky":87.67,"osm-leninsky":80.08,
            "osm-oktyabrsky":52.74,"osm-sovetsky":81.56,"osm-sverdlovsky":50.51,"osm-zheleznodorozhny":100}
        command.upgrade(config,"head")
        assert current_payloads()==before and scores()==baseline
        with factory.begin() as value:
            assert load_pois(value,FIXTURE)["total"]==1988
            dataset=value.scalar(select(models.OsmDataset))
            assert dataset.scope_id=="krasnoyarsk"
            snapshot=value.get(models.OsmSnapshot,dataset.active_snapshot_id)
            assert snapshot.is_legacy and snapshot.quality["provenance_status"]=="PARTIAL"
            assert snapshot.source_base_timestamp is None and snapshot.manifest_checksum is None
            assert len(history(value,snapshot))==1988
        assert current_payloads()==before
        command.downgrade(config,"0013_poi_nullable_name")
        assert current_payloads()==before
        command.upgrade(config,"head")
        assert current_payloads()==before and scores()==baseline
        with factory.begin() as value:
            candidate(value,tmp_path,"nonlegacy-history",[node(123)])
        with pytest.raises(ValueError,match="Lossy"):
            command.downgrade(config,"0013_poi_nullable_name")
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version"))=="0014_osm_snapshot_lifecycle"
        assert current_payloads()==before
        # Competing writers must serialize on the dataset and retire the actual
        # newly committed previous snapshot, not a stale identity-map pointer.
        with factory.begin() as value:
            a,_=candidate(value,tmp_path,"concurrent-A",[node(99001)],scope="concurrent-scope")
            approved(value,a); activate_snapshot(value,a.id)
            b,_=candidate(value,tmp_path,"concurrent-B",[node(99002)],scope="concurrent-scope")
            c,_=candidate(value,tmp_path,"concurrent-C",[node(99003)],scope="concurrent-scope")
            approved(value,b); approved(value,c)
            ids=(a.id,b.id,c.id,a.dataset_id)
        from concurrent.futures import ThreadPoolExecutor
        from threading import Event
        import time
        switched,release,started=Event(),Event(),Event()
        def first_writer():
            with factory.begin() as value:
                value.execute(text("SET LOCAL lock_timeout='10s'"))
                activate_snapshot(value,ids[1]); switched.set()
                if not release.wait(10):
                    raise RuntimeError("Concurrent test release timeout")
        def second_writer():
            with factory.begin() as value:
                value.execute(text("SET LOCAL lock_timeout='10s'"))
                started.set(); activate_snapshot(value,ids[2])
        with ThreadPoolExecutor(max_workers=2) as pool:
            first=pool.submit(first_writer)
            assert switched.wait(10)
            second=pool.submit(second_writer)
            try:
                assert started.wait(10)
                deadline=time.monotonic()+5
                blocked=False
                while time.monotonic()<deadline:
                    with engine.connect() as connection:
                        blocked=bool(connection.scalar(text("SELECT count(*) FROM pg_stat_activity WHERE datname=:db AND wait_event_type='Lock' AND query LIKE '%osm_datasets%'"),{"db":database_name}))
                    if blocked:
                        break
                    time.sleep(.05)
                assert blocked, "Second writer did not wait for the dataset lock"
            finally:
                release.set()
            first.result(timeout=10); second.result(timeout=10)
        with factory() as value:
            assert value.get(models.OsmDataset,ids[3]).active_snapshot_id==ids[2]
            assert [value.get(models.OsmSnapshot,id_).status for id_ in ids[:3]]==["RETIRED","RETIRED","ACTIVE"]
            assert [p.external_id for p in active_rows(value,ids[3])]==["node:99003"]
            assert all(len(history(value,value.get(models.OsmSnapshot,id_)))==1 for id_ in ids[:3])
    finally:
        engine.dispose()
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE "{database_name}"'))
        admin.dispose()
