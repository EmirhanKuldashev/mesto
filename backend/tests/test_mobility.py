"""Network-free provider contract tests using recorded real road routes."""
from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.mobility.api import get_mobility_service
from app.mobility.models import Coordinate, MobilityRequest, RouteFacts
from app.mobility.osrm import CarRoutingProvider, MAX_RESPONSE_BYTES, separation
from app.mobility.service import MobilityService
from data.routing.contract import ROOT, load_manifest

CASES = json.loads((Path(__file__).parent / "fixtures/mobility_osrm.json").read_text())["cases"]
ORIGIN = Coordinate(latitude=56.01, longitude=92.85)
ENDS = {"short": (56.012, 92.862), "medium": (56.06, 92.91), "river": (55.985, 92.90), "same": (56.01, 92.85)}


def destination(name="short"):
    lat, lon = ENDS[name]
    return Coordinate(latitude=lat, longitude=lon)


def provider(payload=None, *, status=200, handler=None):
    return CarRoutingProvider("http://routing:5000", load_manifest(), transport=httpx.MockTransport(
        handler or (lambda _: httpx.Response(status, json=payload if payload is not None else CASES["short"]))))


def assert_unavailable(result, reason):
    assert result.availability == "UNAVAILABLE"
    assert result.unavailable_reason == reason
    assert result.duration_seconds is result.distance_meters is result.geometry is result.origin_snap is result.destination_snap is None


@pytest.mark.parametrize("name", ENDS)
def test_real_recorded_routes_deterministic_and_not_straight_line(name):
    engine = provider(CASES[name])
    result = engine.route(ORIGIN, destination(name), "car")
    assert result == engine.route(ORIGIN, destination(name), "car")
    assert result.availability == "AVAILABLE"
    assert result.duration_seconds == CASES[name]["routes"][0]["duration"]
    assert result.distance_meters == CASES[name]["routes"][0]["distance"]
    assert result.dataset_sha256 == load_manifest()["pbf_sha256"]
    assert result.data_timestamp == datetime.fromisoformat("2026-10-06T20:21:06+00:00")
    assert separation(result.origin_snap.location, Coordinate(latitude=result.geometry.coordinates[0][1], longitude=result.geometry.coordinates[0][0])) < 2
    assert separation(result.destination_snap.location, Coordinate(latitude=result.geometry.coordinates[-1][1], longitude=result.geometry.coordinates[-1][0])) < 2
    if name == "same":
        assert result.distance_meters == result.duration_seconds == 0
    else:
        assert result.duration_seconds > 0
        assert result.distance_meters > separation(ORIGIN, destination(name)) + 20


def test_one_bounded_request_mode_coordinates_and_no_personal_metadata():
    calls = []
    def handle(request):
        calls.append(request)
        assert request.url.path == "/route/v1/driving/92.85,56.01;92.862,56.012"
        assert dict(request.url.params) == {"alternatives": "false", "steps": "false", "overview": "full",
            "geometries": "geojson", "generate_hints": "false", "radiuses": "250;250"}
        assert request.extensions["timeout"] == {"connect": 1, "read": 5, "write": 5, "pool": 5}
        assert not request.content
        return httpx.Response(200, json=CASES["short"])
    service = MobilityService(provider(handler=handle))
    request = MobilityRequest(origin=ORIGIN, destination={**destination().model_dump(), "label": "Work secret", "kind": "work"}, mode="car")
    first = service.calculate(request)
    second = service.calculate(request.model_copy(update={"destination": request.destination.model_copy(update={"label": "University", "kind": "university"})}))
    assert len(calls) == 2
    assert calls[0].url == calls[1].url
    assert first.duration_seconds == second.duration_seconds
    assert first.destination.label == "Work secret" and second.destination.label == "University"
    assert first.traffic == "not_included" and first.departure_time is None


@pytest.mark.parametrize("status,reason", [(429, "provider_rate_limited"), (403, "provider_access_denied"),
    (401, "provider_access_denied"), (500, "provider_error"), (503, "provider_error"), (302, "provider_redirect_rejected")])
def test_status_errors_no_retry_or_fallback(status, reason):
    calls = []
    def handle(request):
        calls.append(request)
        return httpx.Response(status, json=CASES["short"], headers={"Location": "https://untrusted.example/"})
    assert_unavailable(provider(handler=handle).route(ORIGIN, destination(), "car"), reason)
    assert len(calls) == 1


@pytest.mark.parametrize("exception,reason", [(httpx.ReadTimeout, "provider_timeout"), (httpx.ConnectError, "provider_unreachable")])
def test_transport_failures(exception, reason):
    calls = []
    def handle(request):
        calls.append(request)
        raise exception("Do not expose provider internals", request=request)
    result = provider(handler=handle).route(ORIGIN, destination(), "car")
    assert_unavailable(result, reason)
    assert len(calls) == 1
    assert "internals" not in result.model_dump_json()


def test_body_deadline_does_not_accept_a_slow_success(monkeypatch):
    clock = iter([0, 6])
    monkeypatch.setattr("app.mobility.osrm.monotonic", lambda: next(clock))
    assert_unavailable(provider().route(ORIGIN, destination(), "car"), "provider_timeout")


@pytest.mark.parametrize("code,reason", [("NoRoute", "no_route"), ("NoSegment", "no_road_segment")])
@pytest.mark.parametrize("status", [200, 400])
def test_no_route_and_no_segment(code, reason, status):
    assert_unavailable(provider({"code": code}, status=status).route(ORIGIN, destination(), "car"), reason)


@pytest.mark.parametrize("metric", ["duration", "distance"])
@pytest.mark.parametrize("bad", [-1, float("nan"), float("inf"), True, "42", None])
def test_malformed_metrics(metric, bad):
    payload = deepcopy(CASES["short"])
    payload["routes"][0][metric] = bad
    # json.dumps intentionally permits NaN to test fail-closed provider parsing.
    response = httpx.Response(200, content=json.dumps(payload).encode())
    assert_unavailable(provider(handler=lambda _: response).route(ORIGIN, destination(), "car"), "provider_response_invalid")


@pytest.mark.parametrize("mutation", ["geometry_end", "geometry_type", "geometry_bool", "geometry_wgs84", "waypoint", "snap_radius", "routes", "zero_time", "chord"])
def test_malformed_provider_shapes(mutation):
    payload = deepcopy(CASES["short"])
    route = payload["routes"][0]
    if mutation == "geometry_end": route["geometry"]["coordinates"][-1] = [92.85, 56.01]
    if mutation == "geometry_type": route["geometry"]["type"] = "Point"
    if mutation == "geometry_bool": route["geometry"]["coordinates"][0] = [True, 56.01]
    if mutation == "geometry_wgs84": route["geometry"]["coordinates"][0] = [200, 100]
    if mutation == "waypoint": payload["waypoints"] = []
    if mutation == "snap_radius": payload["waypoints"][0]["distance"] = 251
    if mutation == "routes": payload["routes"] = []
    if mutation == "zero_time": route["duration"] = 0
    if mutation == "chord": route["distance"] = 1
    assert_unavailable(provider(payload).route(ORIGIN, destination(), "car"), "provider_response_invalid")


@pytest.mark.parametrize("content", [b"not-json", b"[]", b"{}", b"x" * (MAX_RESPONSE_BYTES + 1)], ids=["not-json", "array", "empty-object", "oversize"])
def test_invalid_json_and_bounded_body(content):
    result = provider(handler=lambda _: httpx.Response(200, content=content)).route(ORIGIN, destination(), "car")
    assert result.availability == "UNAVAILABLE"
    assert result.duration_seconds is result.distance_meters is None


def test_graph_version_must_match_actual_prepared_snapshot():
    for version in (None, "another-graph"):
        payload = deepcopy(CASES["short"])
        payload["data_version"] = version
        assert_unavailable(provider(payload).route(ORIGIN, destination(), "car"), "dataset_version_mismatch")


def test_unsupported_location_and_pt_make_no_car_calls():
    def unexpected(_):
        pytest.fail("Unsupported geography/PT must not contact car engine")
    engine = provider(handler=unexpected)
    assert_unavailable(engine.route(Coordinate(latitude=0, longitude=0), destination(), "car"), "unsupported_geography")
    assert_unavailable(engine.route(ORIGIN, Coordinate(latitude=0, longitude=0), "car"), "unsupported_geography")
    service = MobilityService(engine)
    result = service.calculate(MobilityRequest(origin=ORIGIN, destination=destination().model_dump(), mode="public_transport", departure_time="2026-10-08T08:00:00+07:00"))
    assert_unavailable(result, "public_transport_source_unavailable")
    assert result.traffic == "not_available" and result.departure_time.utcoffset().total_seconds() == 25200


@pytest.mark.parametrize("url", ["", "http://remote.example", "https://user:secret@remote.example", "https://routing.example/?key=secret", "https://routing.example/#fragment", "https://routing.example/path", "http://[invalid"])
def test_invalid_server_configuration(url):
    assert_unavailable(CarRoutingProvider(url, load_manifest()).route(ORIGIN, destination(), "car"), "routing_configuration_invalid")


def test_missing_dataset_fails_closed(monkeypatch):
    monkeypatch.setattr("app.mobility.osrm.load_manifest", lambda: (_ for _ in ()).throw(ValueError("bad checksum")))
    assert_unavailable(CarRoutingProvider.from_environment().route(ORIGIN, destination(), "car"), "routing_dataset_unavailable")


def test_packaged_snapshot_and_docker_graph_identity():
    manifest = load_manifest()
    assert manifest["selected_restrictions"] > 1000 and manifest["selected_ways"] > 50000
    assert (ROOT / "krasnoyarsk-car-v1.osm.pbf").stat().st_size == manifest["bytes"]
    dockerfile = (ROOT.parents[1] / "routing/Dockerfile").read_text()
    for key in ("engine_image", "pbf_sha256", "car_profile_sha256", "data_version"):
        assert manifest[key] in dockerfile
    assert "--profile /opt/car.lua" in dockerfile


@pytest.fixture
def client():
    app.dependency_overrides[get_mobility_service] = lambda: MobilityService(provider())
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_mobility_service, None)


def request_body():
    return {"origin": ORIGIN.model_dump(), "destination": {**destination().model_dump(), "label": "Work", "kind": "work"}, "mode": "car"}


def test_api_correct_schema_no_db_or_scoring(client):
    response = client.post("/api/analytics/mobility", json=request_body())
    assert response.status_code == 200
    result = response.json()
    assert result["version"] == "mobility-v1" and result["availability"] == "AVAILABLE"
    assert result["duration_seconds"] == 219.3 and result["distance_meters"] == 2214.8
    assert result["origin"] == request_body()["origin"]
    assert result["destination"] == request_body()["destination"]
    assert not any("score" in key or "match" in key for key in result)
    assert result["traffic"] == "not_included"
    assert result["unavailable_reason"] is None


def test_api_public_transport_unavailable_not_fake_walking(client):
    body = {**request_body(), "mode": "public_transport"}
    response = client.post("/api/analytics/mobility", json=body)
    assert response.status_code == 200
    result = response.json()
    assert result["unavailable_reason"] == "public_transport_source_unavailable"
    assert result["duration_seconds"] is result["distance_meters"] is None
    assert "transfers" not in result and "legs" not in result


@pytest.mark.parametrize("change", ["latitude", "longitude", "nonfinite", "bool", "string", "mode", "time", "naive_pt_time", "extra", "label"])
def test_api_invalid_inputs(client, change):
    body = request_body()
    if change == "latitude": body["origin"]["latitude"] = 91
    if change == "longitude": body["destination"]["longitude"] = -181
    if change == "nonfinite": body["origin"]["latitude"] = "NaN"
    if change == "bool": body["origin"]["latitude"] = True
    if change == "string": body["origin"]["latitude"] = "56.01"
    if change == "mode": body["mode"] = "walk"
    if change == "time": body["departure_time"] = "2026-10-08T08:00:00+07:00"
    if change == "naive_pt_time": body.update(mode="public_transport", departure_time="2026-10-08T08:00:00")
    if change == "extra": body["provider_url"] = "https://untrusted.example"
    if change == "label": body["destination"]["label"] = "x" * 81
    assert client.post("/api/analytics/mobility", json=body).status_code == 422


def test_unavailable_contract_rejects_stale_metrics():
    with pytest.raises(ValidationError):
        RouteFacts(availability="UNAVAILABLE", unavailable_reason="no_route", duration_seconds=10)


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity"])
def test_nonfinite_json_coordinates_return_validation_error_not_500(client, value):
    payload = request_body()
    payload["origin"]["latitude"] = float(value)
    body = json.dumps(payload)
    response = client.post("/api/analytics/mobility", content=body, headers={"Content-Type": "application/json"})
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "origin", "latitude"]
