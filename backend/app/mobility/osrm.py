"""One bounded OSRM request; no estimates, redirects, retries or fallback."""
import math
import os
from time import monotonic
from urllib.parse import urlsplit

import httpx
from pydantic import ValidationError

from data.routing.contract import load_manifest
from .models import Coordinate, RouteFacts, RouteGeometry, Snap

MAX_RESPONSE_BYTES = 4 * 1024 * 1024
SNAP_RADIUS_METERS = 250
LIMITATIONS = (
    "Calculated road travel time; current traffic, weather and closures are not included.",
    "Route starts/ends at snapped road locations (maximum 250 m); point access time is not included.",
    "Frozen OSM road extract; map completeness and edge effects may affect routes.",
)


def separation(a: Coordinate, b: Coordinate) -> float:
    """Geodesic plausibility check only, never a routing distance or time."""
    lat1, lat2 = math.radians(a.latitude), math.radians(b.latitude)
    dlat, dlon = lat2 - lat1, math.radians(b.longitude - a.longitude)
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371008.8 * 2 * math.asin(math.sqrt(min(1, h)))


def number(value):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError("Invalid nonnegative provider metric")
    return float(value)


def coordinate(pair):
    if not isinstance(pair, list) or len(pair) != 2 or any(type(v) not in (int, float) for v in pair):
        raise ValueError("Invalid provider coordinate")
    return Coordinate(longitude=pair[0], latitude=pair[1])


class CarRoutingProvider:
    def __init__(self, base_url: str, manifest: dict | None, *, transport=None):
        self.base_url = None
        try:
            parsed = urlsplit(base_url)
            trusted = bool(parsed.hostname) and (parsed.scheme == "https" or (parsed.scheme == "http" and parsed.hostname in {"routing", "localhost", "127.0.0.1", "::1"}))
            if trusted and not (parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ("", "/")):
                _ = parsed.port  # also reject malformed/out-of-range ports
                self.base_url = base_url.rstrip("/")
        except ValueError:
            pass
        self.manifest = manifest
        self.transport = transport

    @classmethod
    def from_environment(cls):
        try:
            manifest = load_manifest()
        except (OSError, ValueError, KeyError, TypeError):
            manifest = None
        return cls(os.getenv("MESTO_CAR_ROUTING_URL", "http://routing:5000"), manifest)

    def unavailable(self, reason):
        return RouteFacts(availability="UNAVAILABLE", provider="osrm", provider_version="osrm-http-v1",
                          limitations=LIMITATIONS, unavailable_reason=reason)

    def route(self, origin, destination, mode, departure_time=None) -> RouteFacts:
        if mode != "car" or departure_time is not None:
            return self.unavailable("unsupported_mode_or_time")
        if not self.manifest:
            return self.unavailable("routing_dataset_unavailable")
        if not self.base_url:
            return self.unavailable("routing_configuration_invalid")
        west, south, east, north = self.manifest["endpoint_bounds"]
        if any(not (west <= p.longitude <= east and south <= p.latitude <= north) for p in (origin, destination)):
            return self.unavailable("unsupported_geography")
        path = f"/route/v1/driving/{origin.longitude},{origin.latitude};{destination.longitude},{destination.latitude}"
        deadline = monotonic() + 5
        try:
            with httpx.Client(transport=self.transport, timeout=httpx.Timeout(5, connect=1), follow_redirects=False, trust_env=False) as client:
                with client.stream("GET", self.base_url + path, params={
                    "alternatives": "false", "steps": "false", "overview": "full", "geometries": "geojson",
                    "generate_hints": "false", "radiuses": f"{SNAP_RADIUS_METERS};{SNAP_RADIUS_METERS}",
                }) as response:
                    if response.status_code == 429:
                        return self.unavailable("provider_rate_limited")
                    if response.status_code in (401, 403):
                        return self.unavailable("provider_access_denied")
                    if 300 <= response.status_code < 400:
                        return self.unavailable("provider_redirect_rejected")
                    if response.status_code not in (200, 400):
                        return self.unavailable("provider_error")
                    body = bytearray()
                    for chunk in response.iter_bytes():
                        if monotonic() > deadline:
                            return self.unavailable("provider_timeout")
                        body.extend(chunk)
                        if len(body) > MAX_RESPONSE_BYTES:
                            return self.unavailable("provider_response_invalid")
                    import json
                    payload = json.loads(body)
                    if not isinstance(payload, dict):
                        raise ValueError("Invalid provider object")
                    if payload.get("code") in ("NoRoute", "NoSegment"):
                        return self.unavailable("no_route" if payload["code"] == "NoRoute" else "no_road_segment")
                    if response.status_code != 200 or payload.get("code") != "Ok":
                        return self.unavailable("provider_error")
                    return self.parse(payload, origin, destination)
        except httpx.TimeoutException:
            return self.unavailable("provider_timeout")
        except httpx.HTTPError:
            return self.unavailable("provider_unreachable")
        except (ValueError, TypeError, KeyError, IndexError, ValidationError):
            return self.unavailable("provider_response_invalid")

    def parse(self, payload, origin, destination):
        if payload.get("data_version") != self.manifest["data_version"]:
            return self.unavailable("dataset_version_mismatch")
        routes, waypoints = payload["routes"], payload["waypoints"]
        if not isinstance(routes, list) or len(routes) != 1 or not isinstance(waypoints, list) or len(waypoints) != 2:
            raise ValueError("Expected exactly one point-to-point route")
        route = routes[0]
        duration, distance = number(route["duration"]), number(route["distance"])
        snaps = []
        for waypoint, requested in zip(waypoints, (origin, destination)):
            snap = Snap(location=coordinate(waypoint["location"]), distance_meters=number(waypoint["distance"]))
            if snap.distance_meters > SNAP_RADIUS_METERS or separation(requested, snap.location) > SNAP_RADIUS_METERS + 2:
                raise ValueError("Snap outside requested radius")
            snaps.append(snap)
        geometry = route["geometry"]
        if not isinstance(geometry, dict) or geometry.get("type") != "LineString" or not isinstance(geometry.get("coordinates"), list):
            raise ValueError("Invalid route geometry")
        points = [coordinate(pair) for pair in geometry["coordinates"]]
        shape = RouteGeometry(coordinates=tuple((p.longitude, p.latitude) for p in points))
        if separation(points[0], snaps[0].location) > 2 or separation(points[-1], snaps[1].location) > 2:
            raise ValueError("Geometry endpoints do not match snapped route")
        if distance + 2 < separation(snaps[0].location, snaps[1].location):
            raise ValueError("Route shorter than its endpoints")
        if distance > 0 and duration <= 0:
            raise ValueError("Nonzero route with zero duration")
        return RouteFacts(availability="AVAILABLE", duration_seconds=duration, distance_meters=distance,
                          provider="osrm", provider_version="osrm-" + self.manifest["engine_version"] + "/car-v1",
                          data_timestamp=self.manifest["source_timestamp"], dataset_id=self.manifest["dataset_id"],
                          dataset_sha256=self.manifest["pbf_sha256"], geometry=shape,
                          origin_snap=snaps[0], destination_snap=snaps[1], limitations=LIMITATIONS)
