"""Published fresh baseline, isolated clean installs and upgraded-history parity."""
from collections import Counter
import json
from pathlib import Path
import shutil
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url

from app import models
from app.api import get_session
from app.db import create_session_factory
from app.etl.seed import seed
from app.main import app
from data.loaders.osm_district_loader import load_districts
from data.loaders.osm_poi_loader import load_pois
from data.osm.baseline import CURRENT_BASELINE, load_current_baseline, read_packaged_baseline

BACKEND = Path(__file__).resolve().parents[1]
SNAPSHOT = "fresh-20261004T132116Z"
CATEGORIES = {"school":205,"kindergarten":323,"clinic":127,"hospital":89,"park":283,"bus_stop":1360}
UNNAMED = {"school":45,"kindergarten":61,"clinic":12,"hospital":14,"park":224,"bus_stop":38}
SCORES = {"osm-centralny":(80.45,100,56.01),"osm-kirovsky":(87.67,100,72.25),
    "osm-leninsky":(80.36,100,55.82),"osm-oktyabrsky":(63.84,83.86,38.81),
    "osm-sovetsky":(82.53,100,60.70),"osm-sverdlovsky":(65.64,82.11,45.06),
    "osm-zheleznodorozhny":(100,100,100)}


@pytest.fixture(autouse=True)
def no_osm_network(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("Packaged bootstrap must not collect or fetch OSM")
    monkeypatch.setattr("data.osm.collection.urlopen", denied)
    monkeypatch.setattr("data.loaders.osm_district_loader.urlopen", denied)
    monkeypatch.setattr("urllib.request.urlopen", denied)


def fingerprint(session, table, where="true"):
    return session.execute(text("SELECT count(*),md5(coalesce(string_agg(to_jsonb(t)::text,'|' ORDER BY id),'')) FROM "
                                + table + " t WHERE " + where)).one()


def test_packaged_exact_identity_and_quality_without_raw_storage():
    contract, manifest, result = read_packaged_baseline()
    assert contract.snapshot_id == manifest.snapshot_id == SNAPSHOT
    assert contract.canonical_checksum == result.canonical_checksum == "c1ad85a1d071749c84e31541d104cdaee25d94881ac908ea0838433cbba306e7"
    assert contract.manifest_checksum == "2330b5fe0f5d807dba58493be8edc2f3dc92213d9607491ae55b5be6b963981a"
    assert contract.raw_response_checksum == "cf98ce519e9d3fbe5d0735230cbe7e8a02ed881ee0dfa0901b19365ead8375c4"
    assert contract.query_version == "osm-poi-query-v1"
    assert contract.query_hash == "5dd8b0b1555d83e35b3694375fbb595ef62074ff1545065f1779d5e8e6df0c09"
    assert contract.observation_count == contract.eligible_count == len(result.observations) == 2387
    assert contract.category_counts == CATEGORIES and contract.unnamed_counts == UNNAMED
    assert all(row.eligible for row in result.observations)
    assert manifest.parts[0].fetched_at.isoformat() == "2026-10-04T13:21:20.464482+00:00"
    assert manifest.parts[0].source_base_timestamp.isoformat() == "2026-10-04T13:19:51+00:00"
    for key in ("freshness_status","source_completeness_status","real_world_completeness_status"):
        assert getattr(result.quality,key) == "UNKNOWN"
    assert result.quality.normalized_score_status == "BLOCKED"
    assert not (CURRENT_BASELINE.parent/contract.bundle/manifest.parts[0].artifact_reference).exists()


@pytest.mark.parametrize("change", ["canonical.json.gz","manifest.json","build-report.json","snapshot_id","query_hash","bundle"])
def test_checksum_and_version_fail_before_database_mutations(tmp_path,change):
    contract=json.loads(CURRENT_BASELINE.read_bytes())
    shutil.copytree(CURRENT_BASELINE.parent/contract["bundle"],tmp_path/contract["bundle"])
    if change in ("canonical.json.gz","manifest.json","build-report.json"):
        path=tmp_path/contract["bundle"]/change
        path.write_bytes(path.read_bytes()+b"tampered")
    elif change=="bundle":
        contract[change]="../outside"
    else:
        contract[change]="wrong-version" if change=="snapshot_id" else "0"*64
    path=tmp_path/"current-baseline.json"
    path.write_text(json.dumps(contract),encoding="utf-8")
    with pytest.raises(ValueError,match="checksum|identity|escapes"):
        load_current_baseline(object(),path)


@pytest.fixture
def clean_database(test_database_url,monkeypatch):
    base=make_url(test_database_url)
    name="mesto_publication_"+uuid4().hex
    admin=create_engine(base,isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    url=base.set(database=name).render_as_string(hide_password=False)
    factory,engine=create_session_factory(url)
    try:
        monkeypatch.setenv("DATABASE_URL",url)
        config=Config(str(BACKEND/"alembic.ini"))
        config.set_main_option("script_location",str(BACKEND/"migrations"))
        command.upgrade(config,"head")
        yield factory
    finally:
        engine.dispose()
        assert name.startswith("mesto_publication_") and name!=base.database
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE "{name}"'))
        admin.dispose()


@pytest.mark.integration
def test_clean_bootstrap_fresh_counts_idempotency_scores_and_bbox(clean_database):
    factory=clean_database
    with factory.begin() as session:
        assert session.scalar(text("SELECT version_num FROM alembic_version"))=="0014_osm_snapshot_lifecycle"
        assert session.scalar(text("SELECT count(*) FROM osm_snapshots"))==0
        seed(session)
        load_districts(session,BACKEND/"data/fixtures/osm/krasnoyarsk_districts.json")
        synthetic=fingerprint(session,"pois","is_synthetic")
        assert synthetic[0]>0
        first=load_current_baseline(session)
        assert first["snapshot"]==SNAPSHOT and first["total"]==2387 and first["state"]=="activated"
        snapshot=session.get(models.OsmSnapshot,first["snapshot_id"])
        dataset=session.get(models.OsmDataset,snapshot.dataset_id)
        assert (dataset.source_id,dataset.scope_id,dataset.active_snapshot_id)==("osm","krasnoyarsk",snapshot.id)
        assert snapshot.status=="ACTIVE" and not snapshot.is_legacy
        assert session.scalar(text("SELECT count(*) FROM osm_snapshots"))==1  # Policy B: fresh initial.
        rows=list(session.scalars(select(models.POI).where(models.POI.source_id=="osm",models.POI.is_synthetic.is_(False))))
        assert len(rows)==2387 and Counter(row.category for row in rows)==CATEGORIES
        assert Counter(row.category for row in rows if row.name is None)==UNNAMED
        assert sum(row.name is None for row in rows)==394
        assert all(row.location is not None and row.geometry is None for row in rows)
        before={table:fingerprint(session,table) for table in ("pois","osm_snapshots","osm_snapshot_observations")}
        assert load_current_baseline(session)["state"]=="unchanged"
        assert {table:fingerprint(session,table) for table in before}==before
        assert fingerprint(session,"pois","is_synthetic")==synthetic
        profile=models.UserProfile(data_processing_consent=True,housing_goal="buy",purchase_budget=8000000)
        session.add(profile); session.flush()
        profile_id=str(profile.public_id)
        district_ids=list(session.scalars(select(models.District.id).where(models.District.source_id=="osm")))
        point=session.execute(text("SELECT id,ST_X(location),ST_Y(location) FROM pois WHERE source_id='osm' AND name IS NULL ORDER BY id LIMIT 1")).one()
    previous=app.dependency_overrides.get(get_session)
    def override():
        with factory() as session:
            yield session
    app.dependency_overrides[get_session]=override
    try:
        with TestClient(app) as client:
            response=client.post("/api/analytics/score",json={"profile_id":profile_id,"district_ids":district_ids})
            assert response.status_code==200,response.text
            results=response.json()
            assert {row["district"]["slug"]:(row["score"],row["categories"]["infrastructure"],row["categories"]["transport"]) for row in results}==SCORES
            assert all(row["calculation_version"]=="objective-current-v1" for row in results)
            bbox=f"{point[1]-.00001},{point[2]-.00001},{point[1]+.00001},{point[2]+.00001}"
            response=client.get("/api/poi",params={"source_id":"osm","bbox":bbox})
            assert response.status_code==200 and point[0] in {row["id"] for row in response.json()}
    finally:
        if previous is None: app.dependency_overrides.pop(get_session,None)
        else: app.dependency_overrides[get_session]=previous


@pytest.mark.integration
def test_upgraded_legacy_history_and_fresh_active_restart_are_stable(legacy_session):
    session=legacy_session
    legacy=session.scalar(select(models.OsmSnapshot).where(models.OsmSnapshot.is_legacy))
    assert legacy.status=="ACTIVE"
    history=fingerprint(session,"osm_snapshot_observations",f"snapshot_id={legacy.id}")
    assert history[0]==1988
    fresh=load_current_baseline(session)
    assert fresh["total"]==2387 and legacy.status=="RETIRED"
    before={table:fingerprint(session,table) for table in ("pois","osm_snapshots","osm_snapshot_observations")}
    review=session.get(models.OsmSnapshot,fresh["snapshot_id"]).activation_review.copy()
    assert load_current_baseline(session)["state"]=="unchanged"
    # Old explicit legacy loader also cannot resurrect after activation.
    assert load_pois(session,BACKEND/"data/fixtures/osm/poi.json")["total"]==2387
    assert {table:fingerprint(session,table) for table in before}==before
    assert fingerprint(session,"osm_snapshot_observations",f"snapshot_id={legacy.id}")==history
    assert session.get(models.OsmSnapshot,fresh["snapshot_id"]).activation_review==review
    assert session.scalar(text("SELECT count(*) FROM osm_snapshots"))==2
