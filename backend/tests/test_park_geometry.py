"""Real recovered source plus incomplete-ring and hole regressions, offline."""
import gzip
import hashlib
import json
from pathlib import Path

import pytest
from sqlalchemy import text
from app.db import create_session_factory
from data.osm.baseline import read_packaged_baseline
from data.osm.park_geometry import (
    ROOT, RAW_SHA256, GeometryError, assemble_rings, coordinates, read_geometry, reconstruct,
)


def points(coords):
    return [{"lon":x,"lat":y} for x,y in coords]


def member(ident, coords, role="outer"):
    return {"type":"way","ref":ident,"role":role,"geometry":points(coords)}


def test_frozen_real_source_identity_tags_provenance_and_reconstruction():
    loaded = read_geometry()
    raw = gzip.decompress((ROOT/"raw.json.gz").read_bytes())
    assert hashlib.sha256(raw).hexdigest() == RAW_SHA256
    manifest = loaded.manifest
    assert manifest["geometry_source_timestamp"] == "2026-10-05T13:45:20Z"
    assert manifest["baseline_source_timestamp"] == "2026-10-04T13:19:51Z"
    assert manifest["requested_as_of"] is None and manifest["temporal_mode"] == "separate_current_geometry_dataset"
    assert hashlib.sha256(manifest["query_text"].encode()).hexdigest() == manifest["query_sha256"]
    _,_,baseline = read_packaged_baseline()
    expected = {o.identity:o for o in baseline.observations if o.category == "park"}
    received = {(e["type"],e["id"]):e for e in json.loads(raw)["elements"]}
    assert received.keys() == expected.keys() and len(received) == 283
    for f in loaded.features:
        identity = f["osm_type"],f["osm_id"]
        e = received[identity]
        assert f["tags"] == e["tags"] == expected[identity].tags
        assert f["osm_version"] == e["version"] and f["osm_timestamp"] == e["timestamp"]
        actual = f["point_location"] if f["osm_type"] == "node" else f["area_geometry"]
        assert actual == json.loads(json.dumps(reconstruct(e)))
        assert (f["point_location"] is None) == (f["osm_type"] != "node")
    cemetery = next(f for f in loaded.features if (f["osm_type"],f["osm_id"]) == ("way",31959413))
    assert cemetery["tags"]["leisure"] == "park" and cemetery["tags"]["landuse"] == "cemetery"


def test_multipolygon_split_reversed_segments_holes_and_order_deterministic():
    members = [member(1,[(0,0),(4,0),(4,4)]), member(2,[(0,0),(0,4),(4,4)]),
               member(3,[(1,1),(1,2),(2,2),(2,1),(1,1)],"inner"),
               member(4,[(10,0),(11,0),(11,1),(10,1),(10,0)])]
    row = {"type":"relation","tags":{"type":"multipolygon"},"members":members}
    geometry = reconstruct(row)
    assert geometry["type"] == "MultiPolygon" and len(geometry["coordinates"]) == 2
    assert sorted(len(p) for p in geometry["coordinates"]) == [1,2]
    reverse = [{**m,"geometry":list(reversed(m["geometry"]))} for m in reversed(members)]
    assert reconstruct({**row,"members":reverse}) == geometry


@pytest.mark.parametrize("members",[
    [member(1,[(0,0),(1,0)])],
    [member(1,[(0,0),(1,0)]),member(2,[(0,0),(1,0)]),member(3,[(0,0),(1,0)])],
    [{"type":"way","ref":1,"role":"outer"}],
    [member(1,[(0,0),(1,0)]),member(1,[(1,0),(0,0)])],
    [member(1,[(0,0),(0,0)])],
])
def test_incomplete_ambiguous_or_degenerate_rings_rejected(members):
    with pytest.raises((GeometryError,KeyError)):
        assemble_rings(members)


@pytest.mark.parametrize("point",[{"lon":181,"lat":0},{"lon":0,"lat":91},
                                  {"lon":float("nan"),"lat":0},{"lon":"0","lat":0}])
def test_invalid_wgs84_source_coordinates_rejected(point):
    with pytest.raises(GeometryError): coordinates([point])


def test_orphan_hole_and_unsupported_role_fail_closed():
    row = {"type":"relation","tags":{"type":"multipolygon"},"members":[
        member(1,[(0,0),(2,0),(2,2),(0,2),(0,0)]),
        member(2,[(3,3),(4,3),(4,4),(3,4),(3,3)],"inner")]}
    with pytest.raises(GeometryError): reconstruct(row)
    row["members"][1]["role"] = "label"
    with pytest.raises(GeometryError): reconstruct(row)


@pytest.mark.parametrize("which",["missing","manifest","canonical"])
def test_geometry_integrity_fails_closed(tmp_path,which):
    if which != "missing":
        (tmp_path/"manifest.json").write_bytes((ROOT/"manifest.json").read_bytes())
        (tmp_path/"canonical.json.gz").write_bytes((ROOT/"canonical.json.gz").read_bytes())
        p = tmp_path/("manifest.json" if which == "manifest" else "canonical.json.gz")
        p.write_bytes(b"corrupt")
    with pytest.raises(GeometryError): read_geometry(tmp_path)


@pytest.mark.integration
def test_all_frozen_geometries_valid_nonempty_on_real_postgis(test_database_url):
    _,engine = create_session_factory(test_database_url)
    with engine.connect() as conn:
        rows = conn.execute(text("""WITH f AS (
          SELECT osm_type,ST_SetSRID(ST_GeomFromGeoJSON(CASE WHEN osm_type='node'
            THEN point_location ELSE area_geometry END),4326) AS g
          FROM jsonb_to_recordset(CAST(:features AS jsonb))
            f(osm_type text,point_location jsonb,area_geometry jsonb)
        ) SELECT osm_type,count(*) AS n,bool_and(ST_IsValid(g) AND NOT ST_IsEmpty(g)) AS valid
          FROM f GROUP BY osm_type"""),{"features":json.dumps(read_geometry().features)}).mappings().all()
        assert {r["osm_type"]:r["n"] for r in rows} == {"node":3,"way":266,"relation":14}
        assert all(r["valid"] for r in rows)
    engine.dispose()


@pytest.mark.integration
def test_hole_and_boundary_spheroid_semantics(test_database_url):
    outer = [(92,56),(92.02,56),(92.02,56.02),(92,56.02),(92,56)]
    hole = [(92.005,56.005),(92.015,56.005),(92.015,56.015),(92.005,56.015),(92.005,56.005)]
    g = reconstruct({"type":"relation","tags":{"type":"multipolygon"},"members":[member(1,outer),member(2,hole,"inner")]})
    _,engine = create_session_factory(test_database_url)
    with engine.connect() as conn:
        values = conn.execute(text("""WITH g AS (SELECT ST_SetSRID(ST_GeomFromGeoJSON(:g),4326)::geography AS area)
          SELECT x,y,ST_Covers(area,ST_SetSRID(ST_MakePoint(x,y),4326)::geography) AS inside,
            ST_Distance(area,ST_SetSRID(ST_MakePoint(x,y),4326)::geography,true) AS d
          FROM g CROSS JOIN (VALUES (92.002,56.002),(92.01,56.01),(92.04,56.01),(92.0,56.0)) p(x,y)
          ORDER BY x,y"""),{"g":json.dumps(g)}).mappings().all()
        by_point = {(float(r["x"]),float(r["y"])):r for r in values}
        assert by_point[92.002,56.002]["d"] == 0 and by_point[92.002,56.002]["inside"]
        assert by_point[92.01,56.01]["d"] > 300 and not by_point[92.01,56.01]["inside"]
        assert by_point[92.04,56.01]["d"] > 1000 and not by_point[92.04,56.01]["inside"]
        assert by_point[92,56]["d"] == 0 and by_point[92,56]["inside"]
    engine.dispose()
