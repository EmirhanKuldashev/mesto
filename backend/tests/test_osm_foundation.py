"""Offline contracts using immutable temporary artifacts and mocked collection."""

from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError
from fastapi.testclient import TestClient
from geoalchemy2.elements import WKTElement
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models
from app.api import get_session
from app.analytics.service import LegacyAnalyticsService as AnalyticsService
from app.db import create_session_factory
from app.main import app
from data.loaders.osm_poi_loader import load_dataset, load_pois

from data.osm.builder import build
from data.osm.collection import collect
from data.osm.contracts import Extent, Manifest, Part, Status, canonical_bytes, checksum
from data.osm.legacy import LEGACY_EXTENT, build_legacy
from data.osm.query import load_definition, query_hash, render_query
from data.osm.validation import read_response

BASE = "2026-09-27T00:00:00Z"
FETCH = datetime(2026, 9, 28, tzinfo=timezone.utc)
FIXTURE = Path(__file__).resolve().parents[1] / "data/fixtures/osm/poi.json"


def node(id_=1, **tags):
    return {"type": "node", "id": id_, "lat": 56.01, "lon": 92.85,
            "tags": {"highway": "bus_stop", **tags}}


def response(elements, *, base=BASE, **extra):
    return canonical_bytes({"version": 0.6, "generator": "Overpass API",
        "osm3s": {"timestamp_osm_base": base}, "elements": elements, **extra})


@pytest.fixture(autouse=True)
def deny_network(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("OSM tests must never make external requests")
    monkeypatch.setattr("data.osm.collection.urlopen", denied)


def collected(tmp_path, responses, *, extents=None, extent=LEGACY_EXTENT,
              dataset="test-dataset", scope="test-scope", requested_as_of=None):
    iterator = iter(responses)
    parts = extents or {f"part-{index}": extent for index in range(len(responses))}
    root = tmp_path / "artifacts"
    manifest = collect(dataset_id=dataset, scope_id=scope, snapshot_id="test-snapshot", extent=extent,
        parts=parts, output_dir=root, transport=lambda query: next(iterator), clock=lambda: FETCH,
        requested_as_of=requested_as_of)
    return manifest, root


def updated_part(manifest, index=0, **changes):
    parts = list(manifest.parts)
    parts[index] = Part.model_validate({**parts[index].model_dump(), **changes})
    return Manifest.model_validate({**manifest.model_dump(), "parts": tuple(parts)})


def test_tracked_query_is_deterministic_and_exact_scope():
    spec = load_definition()
    reordered = spec.model_copy(update={"selectors": tuple(reversed(spec.selectors))})
    assert render_query(spec, LEGACY_EXTENT) == render_query(reordered, LEGACY_EXTENT)
    assert query_hash(spec, LEGACY_EXTENT) == query_hash(reordered, LEGACY_EXTENT)
    query = render_query(spec, LEGACY_EXTENT)
    assert 'nwr["highway"="bus_stop"]' in query and query.endswith("out center;")
    assert "name" not in query and "Krasnoyarsk" not in query


@pytest.mark.parametrize("change", ["timeout", "version", "extent", "as_of"])
def test_query_hash_changes_for_meaningful_inputs(change):
    spec = load_definition()
    extent, as_of = LEGACY_EXTENT, None
    before = query_hash(spec, extent)
    if change == "timeout":
        spec = spec.model_copy(update={"timeout_seconds": 61})
    elif change == "version":
        spec = spec.model_copy(update={"query_version": "osm-poi-query-v2"})
    elif change == "extent":
        extent = extent.model_copy(update={"west": 92.6})
    else:
        as_of = FETCH
    assert query_hash(spec, extent, as_of) != before


@pytest.mark.parametrize("missing", ["dataset_id", "scope_id", "snapshot_id", "parts", "query_hash", "extent"])
def test_manifest_requires_identity_query_and_parts(tmp_path, missing):
    manifest, _ = collected(tmp_path, [(200, response([node()]))])
    data = manifest.model_dump()
    data.pop(missing)
    with pytest.raises(ValidationError):
        Manifest.model_validate(data)


def test_manifest_rejects_empty_or_duplicate_parts_and_naive_time(tmp_path):
    manifest, _ = collected(tmp_path, [(200, response([node()]))])
    for parts in ([], [manifest.parts[0], manifest.parts[0]]):
        with pytest.raises(ValidationError):
            Manifest.model_validate({**manifest.model_dump(), "parts": parts})
    with pytest.raises(ValidationError):
        updated_part(manifest, fetched_at=datetime(2026, 9, 28))
    with pytest.raises(ValidationError):
        Extent(west=0, east=0, south=0, north=1)


@pytest.mark.parametrize("missing", ["fetched_at", "source_base_timestamp", "query_text", "query_hash",
                                    "request_reference", "artifact_reference", "artifact_checksum", "element_count"])
def test_missing_metadata_never_validates(tmp_path, missing):
    manifest, root = collected(tmp_path, [(200, response([node()]))])
    result = build(updated_part(manifest, **{missing: None}), root)
    assert result.quality.quality_status == Status.BLOCKED
    assert result.quality.normalized_score_status == "BLOCKED"


def test_builder_deterministic_manifest_order_and_built_at_independence(tmp_path):
    manifest, root = collected(tmp_path, [(200, response([node(2)])), (200, response([node(1)]))])
    before = {p.name: p.read_bytes() for p in root.iterdir()}
    first = build(manifest, root)
    second = build(manifest.model_copy(update={"parts": tuple(reversed(manifest.parts)), "built_at": FETCH}), root)
    assert first.quality.quality_status == Status.VALIDATED
    assert first.canonical == second.canonical and first.canonical_checksum == second.canonical_checksum
    assert first.report["built_at"] != second.report["built_at"]
    assert [row.osm_id for row in first.observations] == [1, 2]
    assert before == {p.name: p.read_bytes() for p in root.iterdir()}


def test_duplicate_identity_dedups_and_preserves_both_references(tmp_path):
    element = node(name="Stop", bus="yes")
    reordered = {"tags": dict(reversed(list(element["tags"].items()))), **{k: v for k, v in element.items() if k != "tags"}}
    manifest, root = collected(tmp_path, [(200, response([element])), (200, response([reordered]))])
    result = build(manifest, root)
    assert result.report["duplicate_count"] == 1 and len(result.observations) == 1
    assert result.quality.quality_status == Status.VALIDATED
    assert [ref.part_id for ref in result.observations[0].source_references] == ["part-0", "part-1"]


def test_conflicting_identity_blocks_and_reports_both_artifacts(tmp_path):
    manifest, root = collected(tmp_path, [(200, response([node(name="A")])), (200, response([node(name="B")]))])
    result = build(manifest, root)
    reverse = build(manifest.model_copy(update={"parts": tuple(reversed(manifest.parts))}), root)
    assert result.quality.quality_status == Status.BLOCKED
    assert result.canonical_checksum == reverse.canonical_checksum
    assert not result.observations
    conflict = result.report["conflicts"][0]
    assert (conflict["osm_type"], conflict["osm_id"]) == ("node", 1)
    assert {ref["artifact_reference"] for ref in conflict["source_references"]} == {
        "part-0.response.json", "part-1.response.json"}


def test_mixed_base_timestamps_block_without_fake_tolerance(tmp_path):
    manifest, root = collected(tmp_path, [(200, response([node(1)])),
        (200, response([node(2)], base="2026-09-27T00:00:01Z"))])
    result = build(manifest, root)
    assert result.quality.temporal_status == Status.MIXED
    assert result.quality.quality_status == Status.BLOCKED
    assert "mixed_temporal_snapshot" in result.quality.reasons
    assert result.observations[0].source_references[0].source_base_timestamp != result.observations[1].source_references[0].source_base_timestamp
    assert all(ref.fetched_at == FETCH for row in result.observations for ref in row.source_references)


@pytest.mark.parametrize("status,raw", [(500, response([])), (200, b"not json"),
    (200, b'[]'), (200, b'{"elements":{}}'), (200, b'{"elements":[]}'),
    (200, response([], remark="runtime error: timeout")), (200, response([], error="failed")),
    (200, b'{"elements":[],"elements":[]}')])
def test_invalid_response_or_failed_part_never_validates(tmp_path, status, raw):
    manifest, root = collected(tmp_path, [(status, raw)])
    assert manifest.parts[0].collection_status == "FAILED"
    result = build(manifest, root)
    assert result.quality.quality_status == Status.BLOCKED
    assert result.report["part_errors"]


def test_checksum_exact_request_and_part_identity_are_checked(tmp_path):
    manifest, root = collected(tmp_path, [(200, response([node()]))])
    for changes in ({"artifact_checksum": "0" * 64}, {"query_hash": "0" * 64},
                    {"element_count": 100}, {"artifact_reference": "../outside.json"}):
        assert build(updated_part(manifest, **changes), root).quality.quality_status == Status.BLOCKED
    (root / manifest.parts[0].request_reference).write_text("wrong query", encoding="utf-8")
    assert build(manifest, root).quality.quality_status == Status.BLOCKED


def test_partial_extent_coverage_blocks(tmp_path):
    partial = LEGACY_EXTENT.model_copy(update={"east": 92.9})
    manifest, root = collected(tmp_path, [(200, response([node()]))], extents={"west": partial})
    result = build(manifest, root)
    assert result.quality.query_completeness_status == Status.PARTIAL
    assert result.quality.quality_status == Status.BLOCKED


def test_partitioned_extent_is_validated(tmp_path):
    west = LEGACY_EXTENT.model_copy(update={"east": 92.9})
    east = LEGACY_EXTENT.model_copy(update={"west": 92.9})
    manifest, root = collected(tmp_path, [(200, response([node()])), (200, response([]))],
                               extents={"a-west": west, "b-east": east})
    assert build(manifest, root).quality.query_completeness_status == Status.VALIDATED


def test_unknown_freshness_and_completeness_never_become_normalized_score(tmp_path):
    manifest, root = collected(tmp_path, [(200, response([]))])
    result = build(manifest, root)
    assert result.quality.quality_status == Status.VALIDATED
    assert result.quality.freshness_status == result.quality.source_completeness_status == result.quality.real_world_completeness_status == Status.UNKNOWN
    assert result.quality.normalized_score_status == "BLOCKED"
    assert "normalization_not_implemented" in result.quality.reasons


@pytest.mark.parametrize("tags", [{}, {"name": None}, {"name": ""}, {"name": "  "}, {"name": "Остановка"}])
def test_name_independent_eligibility_and_source_identity(tmp_path, tags):
    manifest, root = collected(tmp_path, [(200, response([node(**tags)]))])
    row = build(manifest, root).observations[0]
    assert row.eligible and row.identity == ("node", 1)
    assert row.name == (tags.get("name") if (tags.get("name") or "").strip() else None)
    assert row.eligibility_policy_version == "osm-poi-eligibility-v1"


def test_representation_tags_and_no_semantic_dedup(tmp_path):
    elements = [node(1, name="Same", public_transport="platform", bus="yes", tram="no", trolleybus="yes"),
        node(2, name="Same"), {"type": "way", "id": 1, "center": {"lat": 56.01, "lon": 92.85},
                               "tags": {"leisure": "park", "access": "yes"}}]
    manifest, root = collected(tmp_path, [(200, response(elements))])
    rows = build(manifest, root).observations
    assert len(rows) == 3 and all(row.eligible for row in rows)
    assert rows[0].coordinate_representation == "node_coordinate"
    assert rows[2].coordinate_representation == "overpass_center"
    assert rows[0].tags == elements[0]["tags"]
    assert "overpass_center_is_not_boundary_or_entrance" in rows[2].limitations


@pytest.mark.parametrize("tags", [{"amenity": "school"}, {"amenity": "kindergarten"},
    {"amenity": "clinic"}, {"amenity": "hospital"}, {"leisure": "park"}, {"highway": "bus_stop"}])
def test_shared_six_category_mapping(tmp_path, tags):
    element = {**node(), "tags": tags}
    manifest, root = collected(tmp_path, [(200, response([element]))])
    row = build(manifest, root).observations[0]
    assert row.eligible and row.category in tags.values()


@pytest.mark.parametrize("changes", [{"is_synthetic": True}, {"id": True}, {"type": "fake"},
                                     {"tags": {"name": 42}}])
def test_invalid_identity_tags_and_synthetic_data_block(tmp_path, changes):
    manifest, root = collected(tmp_path, [(200, response([{**node(), **changes}]))])
    assert build(manifest, root).quality.quality_status == Status.BLOCKED


def test_non_bus_transport_roles_remain_outside_scope(tmp_path):
    element = {**node(), "tags": {"public_transport": "platform", "bus": "yes"}}
    manifest, root = collected(tmp_path, [(200, response([element]))])
    row = build(manifest, root).observations[0]
    assert not row.eligible and row.category is None and row.tags == element["tags"]


def test_legacy_readable_counts_and_honest_provenance():
    result = build_legacy(FIXTURE)
    assert len(result.observations) == result.report["eligible_count"] == 1988
    assert result.report["input_checksum"] == "9d166b3e123240e4d27d3e0ad56f2dc9bba2551292eca3e4785a9fed909c16ad"
    assert result.quality.provenance_status == result.quality.quality_status == Status.PARTIAL
    assert result.quality.query_completeness_status == result.quality.temporal_status == Status.UNKNOWN
    assert all(ref.source_base_timestamp is None and ref.fetched_at is None
               for row in result.observations for ref in row.source_references)
    assert result.canonical["legacy_snapshot_fetched_at"] is not None


def test_collection_transport_failure_retains_failed_manifest(tmp_path):
    def failed(query):
        raise OSError("mock offline")
    manifest = collect(dataset_id="test", scope_id="scope", snapshot_id="snapshot", extent=LEGACY_EXTENT,
        parts={"part": LEGACY_EXTENT}, output_dir=tmp_path / "raw", transport=failed, clock=lambda: FETCH)
    assert manifest.parts[0].collection_status == "FAILED"
    assert manifest.parts[0].artifact_reference is None and manifest.parts[0].error
    assert (tmp_path / "raw/manifest.json").exists()


def test_collection_is_write_once_and_retains_raw_bytes(tmp_path):
    raw = response([node()])
    manifest, root = collected(tmp_path, [(200, raw)])
    assert (root / manifest.parts[0].artifact_reference).read_bytes() == raw
    assert manifest.parts[0].artifact_checksum == checksum(raw)
    assert (root / manifest.parts[0].request_reference).read_text(encoding="utf-8") == manifest.parts[0].query_text
    with pytest.raises(FileExistsError):
        collected(tmp_path, [(200, raw)])


def test_response_nan_rejected():
    with pytest.raises(ValueError):
        read_response(b'{"elements":[],"coordinate":NaN}', require_header=False)


@pytest.fixture
def db_session(test_database_url):
    _, engine = create_session_factory(test_database_url)
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
                    yield session
            finally:
                transaction.rollback()
    finally:
        engine.dispose()


@pytest.mark.integration
def test_bbox_uses_location_including_boundary_and_ignores_geometry(db_session):
    source = dict(source_id="bbox-foundation-test", source_type="test", source_version="v1",
                  fetched_at=FETCH, is_synthetic=False)
    rows = [models.POI(name=None, category="bus_stop", external_id=f"bbox-{index}",
                       location=WKTElement(point, srid=4326),
                       geometry=WKTElement(geometry, srid=4326) if geometry else None, **source)
            for index, (point, geometry) in enumerate([
                ("POINT(92.85 56.01)", None), ("POINT(92.8 56.0)", None),
                ("POINT(92.86 56.02)", "POINT(90 55)"), ("POINT(90 55)", "POINT(92.85 56.01)")])]
    db_session.add_all(rows)
    db_session.flush()
    previous = app.dependency_overrides.get(get_session)
    app.dependency_overrides[get_session] = lambda: db_session
    try:
        with TestClient(app) as client:
            result = client.get("/api/poi", params={"source_id": source["source_id"], "bbox": "92.8,56,92.9,56.1"})
            assert result.status_code == 200, result.text
            assert [item["id"] for item in result.json()] == [row.id for row in rows[:3]]
            assert result.json()[0]["geometry"] is None
            assert client.get("/api/poi", params={"bbox": "nan,56,92.9,56.1"}).status_code == 422
        assert all(db_session.scalar(select(func.ST_SRID(models.POI.location)).where(models.POI.id == row.id)) == 4326 for row in rows)
    finally:
        if previous is None:
            app.dependency_overrides.pop(get_session, None)
        else:
            app.dependency_overrides[get_session] = previous


@pytest.mark.integration
def test_real_osm_fixture_bbox_regression(db_session):
    from app.api import catalogue
    result = catalogue(db_session, models.POI, source_id="osm", bbox="92.7,55.9,93.1,56.1")
    assert result and all(item["source_id"] == "osm" and item["geometry"] is None for item in result)


@pytest.mark.integration
def test_legacy_repeat_load_preserves_counts_and_seven_district_outputs(legacy_session):
    db_session = legacy_session
    profile = models.UserProfile(data_processing_consent=True, housing_goal="buy", purchase_budget=8000000)
    db_session.add(profile)
    db_session.flush()
    districts = list(db_session.scalars(select(models.District).where(models.District.source_id == "osm").order_by(models.District.slug)))
    service = AnalyticsService(db_session)
    before = [row.model_dump(mode="json") for row in service.calculate(profile.public_id, [d.id for d in districts])]
    assigned_before = db_session.scalar(select(func.count()).select_from(models.POI).where(
        models.POI.source_id == "osm", models.POI.district_id.is_not(None)))
    loaded = load_pois(db_session, FIXTURE)
    assert loaded == {"created": 0, "updated": 1988, "skipped": 0, "assigned": assigned_before, "total": 1988}
    db_session.expire_all()
    after = [row.model_dump(mode="json") for row in service.calculate(profile.public_id, [d.id for d in districts])]
    assert after == before
    expected = {"osm-centralny": (73.94, 89.84, 54.07), "osm-kirovsky": (87.67, 100, 72.25),
        "osm-leninsky": (80.08, 100, 55.19), "osm-oktyabrsky": (52.74, 63.88, 38.81),
        "osm-sovetsky": (81.56, 98.84, 59.96), "osm-sverdlovsky": (50.51, 55.05, 44.84),
        "osm-zheleznodorozhny": (100, 100, 100)}
    assert {row["district"]["slug"]: (row["score"], row["categories"]["infrastructure"], row["categories"]["transport"]) for row in after} == expected
    counts = dict(db_session.execute(select(models.POI.category, func.count()).where(
        models.POI.source_id == "osm", models.POI.is_synthetic.is_(False)).group_by(models.POI.category)).all())
    assert counts == {"bus_stop": 1318, "school": 160, "kindergarten": 262, "clinic": 114, "hospital": 75, "park": 59}
    point = db_session.scalar(select(models.POI).where(models.POI.source_id == "osm").limit(1))
    provenance = point.metadata_json["osm_foundation"]
    assert provenance["tags"] and provenance["quality"]["provenance_status"] == "PARTIAL"
    assert provenance["source_references"][0]["source_base_timestamp"] is None
    assert provenance["source_references"][0]["fetched_at"] is None


@pytest.mark.integration
def test_loader_accepts_unnamed_validated_evidence_and_preserves_metadata(db_session, tmp_path):
    from data.osm.lifecycle import activate_snapshot, review_for_activation
    item = node(9000000000001, bus="yes", trolleybus="yes")
    manifest, root = collected(tmp_path, [(200, response([item]))])
    result = build(manifest, root)
    loaded = load_dataset(db_session, result)
    assert loaded["observations"] == loaded["eligible"] == 1
    assert db_session.scalar(select(models.POI).where(models.POI.external_id == "node:9000000000001")) is None
    review_for_activation(db_session, loaded["snapshot_id"], reviewer="test", reason="Disposable proxy evidence")
    activate_snapshot(db_session, loaded["snapshot_id"])
    point = db_session.scalar(select(models.POI).where(models.POI.external_id == "node:9000000000001"))
    assert point.name is None and point.geometry is None and point.is_synthetic is False
    meta = point.metadata_json["osm_foundation"]
    assert meta["tags"] == item["tags"] and meta["scope_id"] == "test-scope"
    assert meta["coordinate_representation"] == "node_coordinate"
    assert meta["source_references"][0]["source_base_timestamp"] != meta["source_references"][0]["fetched_at"]
    assert load_dataset(db_session, result)["snapshot_id"] == loaded["snapshot_id"]


@pytest.mark.integration
@pytest.mark.parametrize("kind", ["failed", "mixed", "missing_provenance", "legacy"])
def test_unvalidated_build_is_rejected_before_database_changes(db_session, tmp_path, kind):
    before = db_session.scalar(select(func.count()).select_from(models.POI))
    if kind == "legacy":
        result = build_legacy(FIXTURE)
    else:
        responses = [(200, response([node(9000000000002)]))]
        if kind == "failed":
            responses = [(500, response([]))]
        if kind == "mixed":
            responses.append((200, response([node(9000000000003)], base="2026-09-27T00:00:01Z")))
        manifest, root = collected(tmp_path, responses)
        if kind == "missing_provenance":
            manifest = updated_part(manifest, fetched_at=None)
        result = build(manifest, root)
    with pytest.raises(ValueError, match="validated coherent"):
        load_dataset(db_session, result)
    assert db_session.scalar(select(func.count()).select_from(models.POI)) == before


@pytest.mark.integration
def test_loader_guards_other_scope_synthetic_identity_and_rollback(db_session, tmp_path):
    from data.osm.lifecycle import activate_snapshot, review_for_activation
    item = node(9000000000004)
    manifest, root = collected(tmp_path, [(200, response([item]))])
    result = build(manifest, root)
    before = db_session.scalar(select(func.count()).select_from(models.POI))
    savepoint = db_session.begin_nested()
    loaded = load_dataset(db_session, result)
    review_for_activation(db_session, loaded["snapshot_id"], reviewer="test", reason="Disposable evidence")
    activate_snapshot(db_session, loaded["snapshot_id"])
    savepoint.rollback()
    assert db_session.scalar(select(func.count()).select_from(models.POI)) == before
    loaded = load_dataset(db_session, result)
    review_for_activation(db_session, loaded["snapshot_id"], reviewer="test", reason="Disposable evidence")
    activate_snapshot(db_session, loaded["snapshot_id"])
    point = db_session.scalar(select(models.POI).where(models.POI.external_id == "node:9000000000004"))
    other_scope = build(manifest.model_copy(update={"scope_id": "another-city"}), root)
    other = load_dataset(db_session, other_scope)
    review_for_activation(db_session, other["snapshot_id"], reviewer="test", reason="Disposable evidence")
    with pytest.raises(ValueError, match="Cross-dataset/scope"):
        activate_snapshot(db_session, other["snapshot_id"])
    assert point.metadata_json["osm_foundation"]["scope_id"] == "test-scope"
    point.is_synthetic = True
    db_session.flush()
    # Candidate history can coexist; activation cannot overwrite synthetic POIs.
    with pytest.raises(ValueError, match="Synthetic"):
        activate_snapshot(db_session, other["snapshot_id"])
    assert point.is_synthetic is True


@pytest.mark.integration
def test_legacy_loader_has_no_name_gate(db_session, tmp_path):
    path = tmp_path / "legacy.json"
    path.write_bytes(canonical_bytes({"snapshot_fetched_at": FETCH.isoformat(), "elements": [node(9000000000005)]}))
    assert load_pois(db_session, path, scope_id="independent-legacy-test")["created"] == 1
    point = db_session.scalar(select(models.POI).where(models.POI.external_id == "node:9000000000005"))
    assert point.name is None and point.metadata_json["osm_foundation"]["quality"]["quality_status"] == "PARTIAL"


@pytest.mark.integration
def test_changed_partial_legacy_cannot_overwrite_existing_snapshot(legacy_session, tmp_path):
    db_session = legacy_session
    element = read_response(FIXTURE.read_bytes(), require_header=False)["elements"][0]
    path = tmp_path / "changed-legacy.json"
    path.write_bytes(canonical_bytes({"snapshot_fetched_at": FETCH.isoformat(), "elements": [
        {**element, "tags": {**element["tags"], "name": "Changed partial name"}}]}))
    point = db_session.scalar(select(models.POI).where(models.POI.source_id == "osm",
        models.POI.external_id == f"{element['type']}:{element['id']}"))
    before = (point.name, point.source_version, point.metadata_json)
    with pytest.raises(ValueError, match="partial legacy snapshot"):
        load_pois(db_session, path)
    db_session.refresh(point)
    assert (point.name, point.source_version, point.metadata_json) == before
