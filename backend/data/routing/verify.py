"""Explicit real-engine verification. Never part of ordinary network-free pytest.

Run against a separately started local routing container, with an ignored output
directory. Responses are OSM-derived data (ODbL); personal labels are not sent.
"""
import argparse
import json
from pathlib import Path
from time import perf_counter

import httpx

from app.mobility.models import Coordinate
from app.mobility.osrm import CarRoutingProvider, separation
from app.mobility.service import PublicTransportRoutingProvider
from data.routing.contract import load_manifest

CASES = {
    "short": ((56.01, 92.85), (56.012, 92.862)),
    "medium": ((56.01, 92.85), (56.06, 92.91)),
    "river": ((56.01, 92.85), (55.985, 92.90)),
    "same": ((56.01, 92.85), (56.01, 92.85)),
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    provider = CarRoutingProvider(args.url, load_manifest())
    report = {"provider": "local self-hosted OSRM", "cases": [], "outbound_vendor_calls": 0}
    for name, (start, end) in CASES.items():
        origin = Coordinate(latitude=start[0], longitude=start[1])
        destination = Coordinate(latitude=end[0], longitude=end[1])
        durations = []
        results = []
        for _ in range(3):
            begin = perf_counter()
            result = provider.route(origin, destination, "car")
            durations.append(round((perf_counter() - begin) * 1000, 3))
            assert result.availability == "AVAILABLE", (name, result.unavailable_reason)
            results.append(result.model_dump(mode="json"))
        assert results[0] == results[1] == results[2], name
        assert result.distance_meters >= separation(result.origin_snap.location, result.destination_snap.location) - 2
        if name != "same":
            assert result.duration_seconds > 0 and result.distance_meters > 0
            assert result.distance_meters > separation(origin, destination) + 20
        else:
            assert result.duration_seconds == result.distance_meters == 0
        path = f"/route/v1/driving/{origin.longitude},{origin.latitude};{destination.longitude},{destination.latitude}"
        # One extra explicit inspection request per case, including bridge names.
        raw = httpx.get(args.url + path, params={"alternatives": "false", "steps": "true", "overview": "full",
            "geometries": "geojson", "generate_hints": "false", "radiuses": "250;250"}, timeout=5, trust_env=False)
        raw.raise_for_status()
        payload = raw.json()
        assert payload["routes"][0]["duration"] == result.duration_seconds
        assert payload["routes"][0]["distance"] == result.distance_meters
        if name == "river":
            names = [step["name"] for leg in payload["routes"][0]["legs"] for step in leg["steps"]]
            assert any("мост" in road.casefold() for road in names), names
            report["bridge_roads"] = [road for road in names if "мост" in road.casefold()]
        (args.output / (name + ".json")).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        report["cases"].append({"name": name, "origin": origin.model_dump(), "destination": destination.model_dump(),
            "distance_meters": result.distance_meters, "duration_seconds": result.duration_seconds,
            "first_then_warm_latency_ms": durations, "route_requests": 3, "inspection_requests": 1,
            "straight_line_meters_for_sanity_only": round(separation(origin, destination), 2),
            "origin_snap_m": result.origin_snap.distance_meters, "destination_snap_m": result.destination_snap.distance_meters})
    begin = perf_counter()
    pt = PublicTransportRoutingProvider().route(origin, destination, "public_transport")
    report["pt"] = {"availability": pt.availability, "reason": pt.unavailable_reason,
        "latency_ms": round((perf_counter() - begin) * 1000, 3), "provider_calls": 0}
    (args.output / "verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=True))


if __name__ == "__main__":
    main()
